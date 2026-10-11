"""Same-origin application for a bounded private pilot."""
import asyncio
import contextlib
import csv
import hashlib
import io
import json
import logging
import mimetypes
import os
import re
import secrets
import sqlite3
import time
import wave
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .store import Store, now, uid
from .worker import run

ROOT = Path(__file__).resolve().parent.parent
ph = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
DUMMY_HASH = ph.hash('This is not an account password.')
log = logging.getLogger('pilot.requests')


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def fail(status, code, message):
    raise HTTPException(status, detail={'code': code, 'message': message})


class Register(BaseModel):
    email: str = Field(max_length=254)
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=10, max_length=128)
    role: str = Field(default='other', max_length=40)
    invite_code: str | None = Field(default=None, max_length=200)
    consent: bool

    @field_validator('email')
    @classmethod
    def email_valid(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            raise ValueError('invalid email')
        return value

    @field_validator('name')
    @classmethod
    def name_valid(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('empty name')
        return value


class Login(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)


class Reset(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(min_length=10, max_length=128)


class Profile(BaseModel):
    onboarding_completed: bool


class Practice(BaseModel):
    scenario: Literal['speech', 'defense', 'free']
    topic: str = Field(default='', max_length=1000)
    duration: float = Field(ge=0.5, le=10)
    questions: bool = False
    criteria: str = Field(default='', max_length=5000)
    idempotency_key: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')


class JobRequest(BaseModel):
    kind: Literal['questions', 'report']


class Feedback(BaseModel):
    rating: int = Field(ge=1, le=5)
    text: str = Field(default='', max_length=3000)


def public_user(row):
    return {'id': row['id'], 'email': row['email'], 'name': row['name'], 'role': row['role'], 'onboarding_completed': bool(row['onboarding_completed'])}


def provider_ready():
    base = os.environ.get('LLM_BASE_URL', 'https://shared1.multitool.works:4000/v1')
    return bool(os.environ.get('LLM_API_KEY') and base.startswith(('https://', 'http://')))


def job_json(row):
    return {'id': row['id'], 'practice_id': row['practice_id'], 'kind': row['kind'], 'status': row['status'], 'stage': row['stage'], 'result': json.loads(row['result']) if row['result'] else None, 'error': json.loads(row['error']) if row['error'] else None}


def segment_json(row):
    return {'id': row['id'], 'kind': row['kind'], 'index': row['segment_index'], 'media_url': '/api/practices/' + row['practice_id'] + '/segments/' + row['id'] + '/media', 'duration_seconds': row['duration'], 'transcript': row['transcript'], 'has_video': '.video.' in row['filename']}


async def decoded_duration(path):
    from .ai import probe_media, ProviderError
    try:
        return await probe_media(path)
    except ProviderError as exc:
        fail(413 if exc.code == 'MEDIA_TOO_LONG' else 422, exc.code, exc.message)


def create_app(data_dir=None, start_worker=True):
    production = os.environ.get('APP_ENV', 'development') == 'production'
    origin = os.environ.get('APP_ORIGIN', '').rstrip('/')
    if production and not origin.startswith('https://'):
        raise RuntimeError('Production requires HTTPS APP_ORIGIN')
    if production and len(os.environ.get('OPERATOR_TOKEN', '')) < 24:
        raise RuntimeError('Production requires OPERATOR_TOKEN of at least 24 characters')
    store = Store(data_dir or os.environ.get('DATA_DIR', ROOT / 'data'))

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(run(store)) if start_worker else None
        app.state.worker_task = task
        yield
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title='Сцена без страха', lifespan=lifespan, docs_url=None if production else '/api/docs', redoc_url=None, openapi_url=None if production else '/api/openapi.json')
    app.state.store = store
    app.state.production = production
    app.state.origin = origin
    app.state.worker_task = None
    app.state.worker_enabled = start_worker

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        detail = exc.detail if isinstance(exc.detail, dict) else {'code': 'REQUEST_FAILED', 'message': 'Не удалось выполнить запрос.'}
        return JSONResponse({'error': detail}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse({'error': {'code': 'VALIDATION_ERROR', 'message': 'Проверьте заполненные поля. Пароль должен содержать от 10 до 128 символов, тренировка — от 30 секунд до 10 минут.'}}, status_code=422)

    @app.middleware('http')
    async def request_metrics(request, call_next):
        began = time.monotonic()
        request_id = uid()
        try:
            response = await call_next(request)
        except Exception:
            log.error('request_failed id=%s', request_id)
            store.event('service_failure', data={'code': 'INTERNAL_ERROR', 'request_id': request_id})
            response = JSONResponse({'error': {'code': 'INTERNAL_ERROR', 'message': 'Сервис временно недоступен. Попробуйте ещё раз.'}}, status_code=500)
        elapsed = round((time.monotonic() - began) * 1000, 1)
        if request.url.path.startswith('/api/'):
            route = request.scope.get('route')
            template = getattr(route, 'path', 'unknown')
            store.event('request', data={'request_id': request_id, 'route': template, 'method': request.method, 'status': response.status_code, 'latency_ms': elapsed})
            log.info('request id=%s route=%s status=%s latency_ms=%s', request_id, template, response.status_code, elapsed)
        response.headers['X-Request-ID'] = request_id
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Permissions-Policy'] = 'microphone=(self), camera=(self)'
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        if production:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response

    def check_origin(request):
        supplied = request.headers.get('origin')
        expected = origin or str(request.base_url).rstrip('/')
        # No Origin means a non-browser client; authenticated mutations still require CSRF.
        if supplied and supplied != expected:
            fail(403, 'ORIGIN_DENIED', 'Запрос с другого сайта отклонён.')
        if request.headers.get('sec-fetch-site') == 'cross-site':
            fail(403, 'ORIGIN_DENIED', 'Запрос с другого сайта отклонён.')

    def auth(request, mutate=False):
        token = request.cookies.get('nfs_session', '')
        session = store.one('SELECT s.*,u.email,u.name,u.role,u.onboarding_completed,u.consent FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>?', (digest(token), now())) if token else None
        if not session:
            fail(401, 'AUTH_REQUIRED', 'Войдите в аккаунт, чтобы продолжить.')
        if mutate:
            check_origin(request)
            if not secrets.compare_digest(request.headers.get('x-csrf-token', ''), session['csrf']):
                fail(403, 'CSRF_INVALID', 'Обновите страницу и попробуйте ещё раз.')
        return {**session, 'id': session['user_id']}

    def owned(practice_id, user_id):
        row = store.one('SELECT * FROM practices WHERE id=? AND user_id=?', (practice_id, user_id))
        if not row:
            fail(404, 'NOT_FOUND', 'Тренировка не найдена.')
        return row

    def practice_json(row):
        segments = store.all('SELECT * FROM segments WHERE practice_id=? ORDER BY segment_index', (row['id'],))
        active = store.one("SELECT * FROM jobs WHERE practice_id=? AND status IN ('pending','running') ORDER BY created DESC LIMIT 1", (row['id'],))
        latest = store.one('SELECT * FROM jobs WHERE practice_id=? ORDER BY created DESC LIMIT 1', (row['id'],))
        return {'id': row['id'], 'config': json.loads(row['config']), 'created_at': datetime.fromtimestamp(row['created'], ZoneInfo('UTC')).isoformat(), 'status': row['status'], 'questions': json.loads(row['questions']), 'report': json.loads(row['report']) if row['report'] else None, 'segments': [segment_json(s) for s in segments], 'active_job': job_json(active) if active else None, 'latest_job': job_json(latest) if latest else None}

    def session_response(user):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        store.execute('INSERT INTO sessions VALUES(?,?,?,?)', (digest(token), user['id'], csrf, now() + 7 * 86400))
        response = JSONResponse({'user': public_user(user), 'csrf_token': csrf})
        response.set_cookie('nfs_session', token, max_age=7 * 86400, httponly=True, secure=production, samesite='strict', path='/')
        return response

    def entry_limit(request):
        ip = request.client.host if request.client else 'unknown'
        if store.limited('auth:' + ip, 20, 300):
            fail(429, 'RATE_LIMIT', 'Слишком много попыток входа. Подождите пять минут.')
        check_origin(request)

    @app.get('/api/auth/me')
    async def me(request: Request):
        try:
            user = auth(request)
        except HTTPException:
            user = None
        return {'user': public_user(user) if user else None, 'csrf_token': user['csrf'] if user else None, 'provider_ready': provider_ready(), 'registration_requires_invite': production or os.environ.get('REQUIRE_INVITE') == '1'}

    @app.post('/api/auth/register')
    async def register(body: Register, request: Request):
        entry_limit(request)
        if not body.consent:
            fail(422, 'CONSENT_REQUIRED', 'Подтвердите согласие на сохранение записи и обработку речи внешним AI-сервисом.')
        require_invite = production or os.environ.get('REQUIRE_INVITE') == '1'
        user = {'id': uid(), 'email': body.email, 'name': body.name, 'password': await asyncio.to_thread(ph.hash, body.password), 'role': body.role, 'onboarding_completed': False, 'consent': True, 'created': now()}
        try:
            with store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                if require_invite or body.invite_code:
                    invite = db.execute('SELECT * FROM invites WHERE token=? AND expires>? AND uses_left>0', (digest(body.invite_code or ''), now())).fetchone()
                    if not invite:
                        fail(403, 'INVITE_INVALID', 'Для регистрации нужен действующий код приглашения.')
                    db.execute('UPDATE invites SET uses_left=uses_left-1 WHERE token=?', (invite['token'],))
                db.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?,?)', (user['id'], user['email'], user['name'], user['password'], user['role'], 0, 1, user['created']))
        except sqlite3.IntegrityError:
            fail(409, 'ACCOUNT_EXISTS', 'Не удалось создать аккаунт. Попробуйте войти или обратитесь к организатору тестирования.')
        store.event('registered', user['id'])
        return session_response(user)

    @app.post('/api/auth/login')
    async def login(body: Login, request: Request):
        entry_limit(request)
        email = body.email.strip().lower()
        if store.limited('login_email:' + digest(email), 12, 300):
            fail(429, 'RATE_LIMIT', 'Слишком много попыток входа. Подождите пять минут.')
        user = store.one('SELECT * FROM users WHERE email=?', (email,))
        try:
            await asyncio.to_thread(ph.verify, user['password'] if user else DUMMY_HASH, body.password)
        except (VerifyMismatchError, InvalidHashError):
            fail(401, 'LOGIN_INVALID', 'Почта или пароль не подходят. Проверьте их и попробуйте ещё раз.')
        if not user:
            fail(401, 'LOGIN_INVALID', 'Почта или пароль не подходят. Проверьте их и попробуйте ещё раз.')
        store.event('login', user['id'])
        return session_response(user)

    @app.post('/api/auth/logout')
    async def logout(request: Request):
        auth(request, True)
        store.execute('DELETE FROM sessions WHERE token=?', (digest(request.cookies['nfs_session']),))
        response = JSONResponse({'ok': True})
        response.delete_cookie('nfs_session', path='/', secure=production, httponly=True, samesite='strict')
        return response

    @app.post('/api/auth/reset')
    async def reset(body: Reset, request: Request):
        entry_limit(request)
        password = await asyncio.to_thread(ph.hash, body.password)
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            token = db.execute('SELECT * FROM resets WHERE token=? AND expires>?', (digest(body.token), now())).fetchone()
            if not token:
                fail(400, 'RESET_INVALID', 'Код восстановления недействителен. Запросите новый у организатора тестирования.')
            db.execute('UPDATE users SET password=? WHERE id=?', (password, token['user_id']))
            db.execute('DELETE FROM sessions WHERE user_id=?', (token['user_id'],))
            db.execute('DELETE FROM resets WHERE user_id=?', (token['user_id'],))
        return {'ok': True}

    @app.patch('/api/auth/me')
    async def update_me(body: Profile, request: Request):
        user = auth(request, True)
        store.execute('UPDATE users SET onboarding_completed=? WHERE id=?', (int(body.onboarding_completed), user['id']))
        return {'user': public_user(store.one('SELECT * FROM users WHERE id=?', (user['id'],)))}

    @app.post('/api/practices')
    async def create_practice(body: Practice, request: Request):
        user = auth(request, True)
        config = body.model_dump(exclude={'idempotency_key'})
        practice_id = digest(user['id'] + ':' + body.idempotency_key)[:32] if body.idempotency_key else uid()
        def existing():
            row = store.one('SELECT * FROM practices WHERE id=? AND user_id=?', (practice_id, user['id']))
            if row and json.loads(row['config']) != config:
                fail(409, 'PRACTICE_KEY_CONFLICT', 'Эта запись уже относится к другой тренировке.')
            return practice_json(row) if row else None
        if body.idempotency_key and (saved := existing()):
            return saved
        if store.limited('practice:' + user['id'], 30, 86400):
            fail(429, 'PRACTICE_QUOTA', 'Лимит на сегодня достигнут. Продолжите завтра.')
        try:
            store.execute('INSERT INTO practices(id,user_id,config,created) VALUES(?,?,?,?)', (practice_id, user['id'], json.dumps(config, ensure_ascii=False), now()))
        except sqlite3.IntegrityError:
            if body.idempotency_key and (saved := existing()):
                return saved
            raise
        store.event('practice_started', user['id'], practice_id)
        return practice_json(owned(practice_id, user['id']))

    @app.get('/api/practices')
    async def practices(request: Request, limit: int = 30, offset: int = 0):
        user = auth(request)
        limit, offset = min(max(limit, 1), 100), max(offset, 0)
        items = store.all('SELECT * FROM practices WHERE user_id=? ORDER BY created DESC LIMIT ? OFFSET ?', (user['id'], limit, offset))
        total = store.one('SELECT COUNT(*) AS n FROM practices WHERE user_id=?', (user['id'],))['n']
        return {'items': [practice_json(row) for row in items], 'total': total}

    @app.get('/api/practices/{practice_id}')
    async def get_practice(practice_id: str, request: Request):
        user = auth(request)
        row = owned(practice_id, user['id'])
        if row['report']:
            store.event('report_opened', user['id'], practice_id)
        return practice_json(row)

    @app.post('/api/practices/{practice_id}/segments')
    async def upload(practice_id: str, request: Request, file: UploadFile = File(...), kind: str = Form(...), index: int = Form(...)):
        user = auth(request, True)
        practice = owned(practice_id, user['id'])
        if not user['consent']:
            fail(403, 'CONSENT_REQUIRED', 'Подтвердите согласие на обработку записи.')
        if practice['status'] in ('processing', 'ready'):
            fail(409, 'PRACTICE_LOCKED', 'Эта тренировка уже обрабатывается или завершена.')
        questions = json.loads(practice['questions'])
        if (kind == 'speech' and index != 0) or (kind == 'answer' and not (1 <= index <= len(questions))) or kind not in ('speech', 'answer'):
            fail(422, 'SEGMENT_INVALID', 'Запись не соответствует этапу тренировки.')
        if store.one('SELECT id FROM segments WHERE practice_id=? AND segment_index=?', (practice_id, index)):
            fail(409, 'SEGMENT_EXISTS', 'Эта запись уже сохранена.')
        if store.limited('upload:' + user['id'], 60, 86400):
            fail(429, 'UPLOAD_QUOTA', 'Лимит загрузок на сегодня достигнут.')
        segment_id = uid()
        filename = segment_id + '.media'
        path = store.media / filename
        keep = False
        try:
            size = 0
            with path.open('xb') as destination:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > int(os.environ.get('MAX_UPLOAD_BYTES', 32 * 1024 * 1024)):
                        fail(413, 'MEDIA_TOO_LARGE', 'Файл слишком большой. Запишите более короткую тренировку без видео.')
                    destination.write(chunk)
                destination.flush()
                os.fsync(destination.fileno())
            probe = await decoded_duration(path)
            duration = probe['duration_seconds']
            video = (file.content_type or '').startswith('video/') and probe['extension'] in ('.webm', '.mp4')
            filename = segment_id + ('.video' if video else '') + probe['extension']
            verified_path = store.media / filename
            path.rename(verified_path)
            path = verified_path
            os.chmod(path, 0o600)
            from .media import finalize_webm
            from .ai import ProviderError
            try:
                await finalize_webm(path)
            except ProviderError as exc:
                fail(413 if exc.code == 'MEDIA_TOO_LARGE' else 422, exc.code, exc.message)
            try:
                with store.connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    current = db.execute('SELECT status FROM practices WHERE id=? AND user_id=?', (practice_id, user['id'])).fetchone()
                    if not current or current['status'] in ('processing', 'ready'):
                        fail(409, 'PRACTICE_LOCKED', 'Состояние тренировки изменилось. Обновите страницу.')
                    total = db.execute('SELECT COALESCE(SUM(duration),0) FROM segments WHERE practice_id=?', (practice_id,)).fetchone()[0]
                    if total + duration > 600:
                        fail(413, 'MEDIA_TOO_LONG', 'Общая длительность тренировки — не больше 10 минут.')
                    db.execute('INSERT INTO segments VALUES(?,?,?,?,?,?,?,?)', (segment_id, practice_id, kind, index, filename, duration, None, now()))
            except sqlite3.IntegrityError:
                fail(409, 'SEGMENT_EXISTS', 'Эта запись уже сохранена.')
            keep = True
            store.event('recording_saved', user['id'], practice_id, {'segment_index': index, 'duration_seconds': duration})
            return segment_json(store.one('SELECT * FROM segments WHERE id=?', (segment_id,)))
        finally:
            await file.close()
            if not keep:
                path.unlink(missing_ok=True)

    @app.post('/api/practices/{practice_id}/jobs')
    async def create_job(practice_id: str, body: JobRequest, request: Request):
        user = auth(request, True)
        practice = owned(practice_id, user['id'])
        active = store.one("SELECT * FROM jobs WHERE practice_id=? AND status IN ('pending','running')", (practice_id,))
        if active:
            return job_json(active)
        if not provider_ready():
            fail(503, 'AI_NOT_CONFIGURED', 'Анализ пока не подключён. Запись сохранена; обратитесь к организатору тестирования.')
        speech = store.one("SELECT * FROM segments WHERE practice_id=? AND kind='speech'", (practice_id,))
        if not speech:
            fail(409, 'SPEECH_REQUIRED', 'Сначала сохраните запись выступления.')
        if body.kind == 'questions' and not json.loads(practice['config'])['questions']:
            fail(409, 'QUESTIONS_DISABLED', 'Вопросы выключены в настройках этой тренировки.')
        completed = store.one("SELECT * FROM jobs WHERE practice_id=? AND kind=? AND status='succeeded' ORDER BY created DESC LIMIT 1", (practice_id, body.kind))
        if completed:
            return job_json(completed)
        if practice['report']:
            fail(409, 'PRACTICE_COMPLETE', 'Тренировка уже завершена.')
        if store.limited('job:' + user['id'], int(os.environ.get('DAILY_JOB_LIMIT', '20')), 86400):
            fail(429, 'AI_QUOTA', 'Лимит анализа на сегодня достигнут. Продолжите завтра.')
        job_id = uid()
        try:
            with store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                current = db.execute('SELECT id FROM practices WHERE id=? AND user_id=?', (practice_id, user['id'])).fetchone()
                if not current:
                    fail(404, 'NOT_FOUND', 'Тренировка не найдена.')
                db.execute('INSERT INTO jobs(id,practice_id,kind,status,stage,created) VALUES(?,?,?,?,?,?)', (job_id, practice_id, body.kind, 'pending', 'queued', now()))
                db.execute("UPDATE practices SET status='processing' WHERE id=?", (practice_id,))
        except sqlite3.IntegrityError:
            active = store.one("SELECT * FROM jobs WHERE practice_id=? AND status IN ('pending','running')", (practice_id,))
            if active:
                return job_json(active)
            raise
        return job_json(store.one('SELECT * FROM jobs WHERE id=?', (job_id,)))

    @app.get('/api/jobs/{job_id}')
    async def get_job(job_id: str, request: Request):
        user = auth(request)
        row = store.one('SELECT j.* FROM jobs j JOIN practices p ON p.id=j.practice_id WHERE j.id=? AND p.user_id=?', (job_id, user['id']))
        if not row:
            fail(404, 'NOT_FOUND', 'Задание не найдено.')
        return job_json(row)

    @app.delete('/api/practices/{practice_id}')
    async def delete_practice(practice_id: str, request: Request):
        user = auth(request, True)
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            practice = db.execute('SELECT * FROM practices WHERE id=? AND user_id=?', (practice_id, user['id'])).fetchone()
            if not practice:
                fail(404, 'NOT_FOUND', 'Тренировка не найдена.')
            if db.execute("SELECT id FROM jobs WHERE practice_id=? AND status IN ('pending','running')", (practice_id,)).fetchone():
                fail(409, 'PRACTICE_BUSY', 'Дождитесь завершения обработки, затем удалите тренировку.')
            files = db.execute('SELECT filename FROM segments WHERE practice_id=?', (practice_id,)).fetchall()
            # Retain rows on filesystem failure so the deletion can be retried.
            for row in files:
                (store.media / row['filename']).unlink(missing_ok=True)
            db.execute('DELETE FROM segments WHERE practice_id=?', (practice_id,))
            db.execute('DELETE FROM feedback WHERE practice_id=?', (practice_id,))
            db.execute('DELETE FROM jobs WHERE practice_id=?', (practice_id,))
            db.execute('UPDATE events SET practice_id=NULL WHERE practice_id=?', (practice_id,))
            db.execute('DELETE FROM practices WHERE id=?', (practice_id,))
        return {'ok': True}

    @app.get('/api/practices/{practice_id}/segments/{segment_id}/media')
    async def media(practice_id: str, segment_id: str, request: Request, download: bool = False):
        user = auth(request)
        owned(practice_id, user['id'])
        row = store.one('SELECT * FROM segments WHERE id=? AND practice_id=?', (segment_id, practice_id))
        if not row or not (store.media / row['filename']).is_file():
            fail(404, 'NOT_FOUND', 'Запись не найдена.')
        return FileResponse(store.media / row['filename'], media_type=mimetypes.guess_type(row['filename'])[0] or 'application/octet-stream', filename='practice-recording' + Path(row['filename']).suffix if download else None, content_disposition_type='attachment' if download else 'inline')

    @app.post('/api/practices/{practice_id}/feedback')
    async def feedback(practice_id: str, body: Feedback, request: Request):
        user = auth(request, True)
        owned(practice_id, user['id'])
        if store.limited('feedback:' + user['id'], 30, 86400):
            fail(429, 'RATE_LIMIT', 'Лимит отзывов на сегодня достигнут.')
        store.execute('INSERT INTO feedback VALUES(?,?,?,?,?,?)', (uid(), user['id'], practice_id, body.rating, body.text, now()))
        store.event('feedback', user['id'], practice_id, {'rating': body.rating})
        return {'ok': True}

    @app.get('/api/health')
    async def health():
        return {'ok': True}

    @app.get('/api/readiness')
    async def readiness():
        try:
            store.one('SELECT 1')
            disk_ok = os.access(store.media, os.W_OK)
        except sqlite3.Error:
            disk_ok = False
        task = app.state.worker_task
        worker_alive = bool(task and not task.done())
        worker_ok = worker_alive or not start_worker
        ready = disk_ok and provider_ready() and worker_ok
        return JSONResponse({'ok': ready, 'storage_ready': disk_ok, 'provider_configured': provider_ready(), 'worker_enabled': start_worker, 'worker_alive': worker_alive}, status_code=200 if ready else 503)

    def operator(request):
        configured = os.environ.get('OPERATOR_TOKEN', '')
        supplied = request.headers.get('authorization', '')
        if not configured or not secrets.compare_digest(supplied, 'Bearer ' + configured):
            fail(401, 'OPERATOR_REQUIRED', 'Требуется доступ оператора.')

    def metrics_payload():
        moscow = ZoneInfo('Europe/Moscow')
        day = datetime.now(moscow).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        dau = store.one("SELECT COUNT(DISTINCT user_id) AS n FROM events WHERE created>=? AND kind IN ('practice_started','report_opened')", (day,))['n']
        grouped = store.all('SELECT kind,COUNT(*) AS count FROM events WHERE created>=? GROUP BY kind', (day,))
        usage_rows = store.all('SELECT created,data FROM usage WHERE created>=?', (day,))
        usage = [dict(json.loads(row['data']), recorded_at=row['created']) for row in usage_rows]
        token_count = sum(sum((attempt.get('input_tokens') or 0) + (attempt.get('output_tokens') or 0) for attempt in u['attempts']) if u.get('attempts') else (u.get('input_tokens') or 0) + (u.get('output_tokens') or 0) for u in usage)
        unknown = sum(u.get('input_tokens') is None or u.get('output_tokens') is None for u in usage)
        return {'timezone': 'Europe/Moscow', 'period_start': day, 'dau': dau, 'events': grouped, 'job_statuses': store.all('SELECT status,COUNT(*) AS count FROM jobs GROUP BY status'), 'usage': usage, 'known_tokens': token_count, 'calls_with_unknown_token_counts': unknown, 'audio_seconds': sum(u.get('audio_seconds') or 0 for u in usage), 'pricing_configured': False}

    @app.get('/api/operator/metrics')
    async def metrics(request: Request):
        operator(request)
        return metrics_payload()

    @app.get('/api/operator/export')
    async def export(request: Request, format: str = 'json', kind: str = 'usage', limit: int = 10000):
        operator(request)
        if kind not in ('usage', 'events'):
            fail(422, 'FORMAT_INVALID', 'Выберите usage или events.')
        limit = min(max(limit, 1), 10000)
        if kind == 'events':
            rows = store.all('SELECT id,user_id,practice_id,kind,created,data FROM events ORDER BY created DESC LIMIT ?', (limit,))
            if format == 'json':
                return {'items': [{**row, 'data': json.loads(row['data'])} for row in rows]}
            if format == 'csv':
                buffer = io.StringIO()
                writer = csv.DictWriter(buffer, fieldnames=['id', 'user_id', 'practice_id', 'kind', 'created', 'data'])
                writer.writeheader()
                writer.writerows(rows)
                return Response(buffer.getvalue(), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="events.csv"'})
        if format == 'json':
            rows = store.all('SELECT created,job_id,user_id,data FROM usage ORDER BY created DESC LIMIT ?', (limit,))
            return {'items': [{**row, 'data': json.loads(row['data'])} for row in rows]}
        if format != 'csv':
            fail(422, 'FORMAT_INVALID', 'Выберите json или csv.')
        buffer = io.StringIO()
        fields = ['created', 'job_id', 'user_id', 'model', 'operation', 'input_tokens', 'output_tokens', 'audio_seconds', 'latency_ms']
        writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for row in store.all('SELECT created,job_id,user_id,data FROM usage ORDER BY created DESC LIMIT ?', (limit,)):
            writer.writerow({**json.loads(row.pop('data')), **row})
        return Response(buffer.getvalue(), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="usage.csv"'})

    class UploadGuard:
        # Runs outside FastAPI's multipart parser: unauthorized or oversized bodies
        # never reach its temporary-file spool. At most three uploads decode at once.
        def __init__(self, app):
            self.app = app
            self.slots = asyncio.Semaphore(3)

        async def __call__(self, scope, receive, send):
            if scope['type'] != 'http' or scope['method'] not in ('POST', 'PATCH', 'DELETE') or not scope['path'].startswith('/api/'):
                return await self.app(scope, receive, send)
            is_upload = bool(re.fullmatch(r'/api/practices/[^/]+/segments', scope['path']))
            request = Request(scope)
            began = time.monotonic()
            request_id = uid()
            route_template = '/api/practices/{practice_id}/segments' if is_upload else scope['path'] if scope['path'] in ('/api/auth/register', '/api/auth/login', '/api/auth/reset', '/api/auth/logout', '/api/auth/me', '/api/practices') else 'guarded_mutation'

            async def reject(status, error, disconnected=False):
                elapsed = round((time.monotonic() - began) * 1000, 1)
                store.event('request', data={'request_id': request_id, 'route': route_template, 'method': scope['method'], 'status': status, 'latency_ms': elapsed, 'error_code': error['code']})
                log.info('request id=%s route=%s status=%s latency_ms=%s', request_id, route_template, status, elapsed)
                if disconnected:
                    return
                response = JSONResponse({'error': error}, status_code=status, headers={'Cache-Control': 'no-store', 'X-Request-ID': request_id, 'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY', 'Referrer-Policy': 'same-origin'})
                if production:
                    response.headers['Strict-Transport-Security'] = 'max-age=31536000'
                await response(scope, receive, send)

            try:
                if scope['path'] in ('/api/auth/register', '/api/auth/login', '/api/auth/reset'):
                    check_origin(request)
                else:
                    auth(request, True)
                maximum = int(os.environ.get('MAX_UPLOAD_BYTES', 32 * 1024 * 1024)) + 16384 if is_upload else 65536
                content_length = request.headers.get('content-length')
                if content_length and int(content_length) > maximum:
                    fail(413, 'MEDIA_TOO_LARGE', 'Файл слишком большой. Запишите более короткую тренировку без видео.')
            except (HTTPException, ValueError) as exc:
                error = exc.detail if isinstance(exc, HTTPException) else {'code': 'REQUEST_INVALID', 'message': 'Не удалось прочитать запрос.'}
                return await reject(exc.status_code if isinstance(exc, HTTPException) else 400, error)
            async with self.slots:
                chunks, size = [], 0
                deadline = time.monotonic() + 120
                while True:
                    try:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise asyncio.TimeoutError
                        message = await asyncio.wait_for(receive(), timeout=min(30, remaining))
                    except asyncio.TimeoutError:
                        return await reject(408, {'code': 'UPLOAD_TIMEOUT', 'message': 'Загрузка прервалась. Попробуйте сохранить запись ещё раз.'})
                    if message['type'] == 'http.disconnect':
                        return await reject(499, {'code': 'UPLOAD_DISCONNECTED', 'message': 'Загрузка прервалась.'}, disconnected=True)
                    chunk = message.get('body', b'')
                    size += len(chunk)
                    if size > maximum:
                        return await reject(413, {'code': 'MEDIA_TOO_LARGE', 'message': 'Файл слишком большой. Запишите более короткую тренировку без видео.'})
                    chunks.append(chunk)
                    if not message.get('more_body', False):
                        break
                payload = b''.join(chunks)
                chunks.clear()
                delivered = False

                async def replay():
                    nonlocal delivered, payload
                    if not delivered:
                        delivered = True
                        body, payload = payload, b''
                        return {'type': 'http.request', 'body': body, 'more_body': False}
                    return await receive()

                return await self.app(scope, replay, send)

    app.add_middleware(UploadGuard)
    app.mount('/', StaticFiles(directory=ROOT / 'public', html=True), name='public')
    return app


app = create_app()
