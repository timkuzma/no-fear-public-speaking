"""Password-only analytics reader; never an account or an analytics owner."""
import asyncio
import hashlib
import json
import secrets
import time
import uuid

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

ACCESS = 'analytics_view_access'
PREFIX = 'analytics_view_session:'
COOKIE = 'nfs_analytics_view'
PATH = '/api/analytics-view'
TTL = 8 * 3600
PASSWORDS = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)


def configure(store, password=None):
    if password is not None and (not isinstance(password, str) or not 12 <= len(password) <= 128):
        raise ValueError('Password must contain 12–128 characters')
    value = {'password_hash': PASSWORDS.hash(password), 'generation': uuid.uuid4().hex} if password is not None else None
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM operational_state WHERE key=? OR key LIKE ?', (ACCESS, PREFIX+'%'))
        if value:
            db.execute('INSERT INTO operational_state VALUES(?,?,?)', (ACCESS, json.dumps(value), time.time()))


def install(app, store, check_origin):
    password_slots = asyncio.Semaphore(2)

    def fail(status, code, message):
        raise HTTPException(status, detail={'code': code, 'message': message})

    def access():
        row = store.one('SELECT value FROM operational_state WHERE key=?', (ACCESS,))
        return json.loads(row['value']) if row else None

    def mutation(request):
        check_origin(request)
        if not request.headers.get('origin'):
            fail(403, 'ORIGIN_DENIED', 'Обновите страницу и попробуйте ещё раз.')

    def session(request, config):
        raw = request.cookies.get(COOKIE, '')
        if not config or not 32 <= len(raw) <= 100:
            return None
        key = PREFIX + hashlib.sha256(raw.encode()).hexdigest()
        row = store.one('SELECT value FROM operational_state WHERE key=?', (key,))
        value = json.loads(row['value']) if row else {}
        return key if value.get('generation') == config['generation'] and value.get('expires', 0) > time.time() else None

    @app.get(PATH+'/session')
    async def status(request: Request):
        check_origin(request)
        config = access()
        return {'enabled': bool(config), 'authenticated': bool(session(request, config))}

    @app.post(PATH+'/session')
    async def login(request: Request):
        mutation(request)
        config = access()
        if not config:
            fail(404, 'VIEW_DISABLED', 'Доступ по ссылке отключён.')
        remote = hashlib.sha256((request.client.host if request.client else 'unknown').encode()).hexdigest()
        if store.limited('analytics-view-ip:'+remote, 10, 900) or store.limited('analytics-view-login', 100, 900):
            fail(429, 'LOGIN_LIMIT', 'Слишком много попыток. Попробуйте позже.')
        try:
            raw = bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw) > 1024:
                    raise ValueError()
            body = json.loads(raw)
            password = body.get('password') if isinstance(body, dict) else None
            if not isinstance(password, str) or not 1 <= len(password) <= 128:
                raise ValueError()
        except (ValueError, UnicodeError):
            fail(422, 'PASSWORD_INVALID', 'Введите пароль.')
        try:
            async with password_slots:
                await asyncio.to_thread(PASSWORDS.verify, config['password_hash'], password)
        except (VerificationError, InvalidHashError):
            fail(401, 'PASSWORD_INVALID', 'Неверный пароль.')
        raw = secrets.token_urlsafe(32)
        key = PREFIX + hashlib.sha256(raw.encode()).hexdigest()
        now = time.time()
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT value FROM operational_state WHERE key=?', (ACCESS,)).fetchone()
            if not current or json.loads(current['value'])['generation'] != config['generation']:
                fail(401, 'PASSWORD_INVALID', 'Пароль изменён. Введите новый пароль.')
            db.execute("DELETE FROM operational_state WHERE key LIKE ? AND json_extract(value,'$.expires')<=?", (PREFIX+'%', now))
            previous = session(request, config)
            if previous:
                db.execute('DELETE FROM operational_state WHERE key=?', (previous,))
            db.execute('INSERT INTO operational_state VALUES(?,?,?)', (key, json.dumps({'generation': config['generation'], 'expires': now+TTL}), now))
        response = JSONResponse({'authenticated': True})
        response.set_cookie(COOKIE, raw, max_age=TTL, httponly=True, secure=app.state.production, samesite='strict', path=PATH)
        return response

    @app.delete(PATH+'/session')
    async def logout(request: Request):
        mutation(request)
        key = session(request, access())
        if key:
            store.execute('DELETE FROM operational_state WHERE key=?', (key,))
        response = JSONResponse({'authenticated': False})
        response.delete_cookie(COOKIE, path=PATH, secure=app.state.production, httponly=True, samesite='strict')
        return response

    def authorize(request):
        check_origin(request)
        config = access()
        if not config:
            fail(404, 'VIEW_DISABLED', 'Доступ по ссылке отключён.')
        if not session(request, config):
            fail(401, 'VIEW_PASSWORD_REQUIRED', 'Введите пароль для просмотра аналитики.')
        return {'id': None, 'analytics_view': True}

    return authorize
