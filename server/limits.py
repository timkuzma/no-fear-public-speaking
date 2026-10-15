"""Durable, conservative work limits; no inference of billing currency or cost."""
from contextlib import contextmanager
from contextvars import ContextVar
import math
import os

from .store import now, uid

_context = ContextVar('provider_accounting', default=None)
DEFAULTS = {
    'AI_DAILY_ATTEMPTS': (500, 1, 1000000),
    'AI_USER_DAILY_ATTEMPTS': (300, 1, 100000),
    'AI_REQUESTS_PER_MINUTE': (30, 1, 10000),
    'AI_DAILY_AUDIO_SECONDS': (18000, 1, 10000000),
    'AI_DAILY_INPUT_CHARS': (5000000, 1, 1000000000),
    'AI_DAILY_OUTPUT_TOKENS': (600000, 1, 1000000000),
    'AI_MAX_OUTPUT_TOKENS': (3000, 100, 3000),
    'MAX_PENDING_JOBS': (20, 1, 1000),
    'MAX_PENDING_LIVE_CHUNKS': (120, 1, 10000),
    'JOB_TIMEOUT_SECONDS': (900, 10, 3600),
    'LIVE_JOB_TIMEOUT_SECONDS': (180, 5, 600),
    'MIN_FREE_DISK_BYTES': (268435456, 0, 10000000000000),
    'QUEUE_ALERT_SECONDS': (300, 1, 3600),
    'BACKUP_MAX_AGE_SECONDS': (93600, 60, 604800),
    'DAILY_JOB_LIMIT': (20, 1, 1000),
    'DAILY_LIVE_CHUNK_LIMIT': (360, 1, 10000),
    'MAX_UPLOAD_BYTES': (33554432, 1, 104857600),
    'LLM_MAX_ATTEMPTS': (2, 1, 3),
    'LLM_TIMEOUT_SECONDS': (120, 5, 180),
}


class LimitError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def setting(name):
    default, low, high = DEFAULTS[name]
    try:
        value = float(os.getenv(name, str(default)))
        if not math.isfinite(value) or value != int(value) or not low <= value <= high:
            raise ValueError()
        return int(value)
    except (ValueError, OverflowError):
        raise RuntimeError('Invalid production limit: ' + name) from None


def validate():
    for name in DEFAULTS:
        setting(name)
    if os.getenv('AI_ENABLED', '1') not in ('0', '1'):
        raise RuntimeError('AI_ENABLED must be 0 or 1')


@contextmanager
def provider_scope(store, user_id, job_id):
    token = _context.set((store, user_id, job_id))
    try:
        yield
    finally:
        _context.reset(token)


def enabled(store):
    row = store.one("SELECT value FROM operational_state WHERE key='ai_enabled'")
    return os.getenv('AI_ENABLED', '1') == '1' and (not row or row['value'] != 'false')


def totals(store):
    return store.one('SELECT COUNT(*) AS attempts,COALESCE(SUM(audio_seconds),0) AS audio_seconds,COALESCE(SUM(input_chars),0) AS input_chars,COALESCE(SUM(output_tokens),0) AS output_tokens FROM ai_attempts WHERE created>?', (now() - 86400,))


def ensure_accepting(store):
    if not enabled(store):
        raise LimitError('AI_PAUSED', 'Разбор временно приостановлен. Запись сохранена; попробуйте позже.')
    current = totals(store)
    for key, name in [('attempts', 'AI_DAILY_ATTEMPTS'), ('audio_seconds', 'AI_DAILY_AUDIO_SECONDS'), ('input_chars', 'AI_DAILY_INPUT_CHARS'), ('output_tokens', 'AI_DAILY_OUTPUT_TOKENS')]:
        if current[key] >= setting(name):
            raise LimitError('AI_SERVICE_LIMIT', 'Общий лимит разбора на сегодня достигнут. Запись сохранена; продолжите позже.')


def reserve_attempt(operation, audio_seconds=0, input_chars=0, output_tokens=0):
    scope = _context.get()
    if scope is None:
        if os.getenv('APP_ENV') == 'production':
            raise LimitError('AI_CONTEXT_REQUIRED', 'Разбор временно недоступен. Запись сохранена.')
        return None
    store, user_id, job_id = scope
    ensure_accepting(store)
    if not math.isfinite(audio_seconds) or audio_seconds < 0 or input_chars < 0 or output_tokens < 0:
        raise LimitError('AI_INPUT_INVALID', 'Не удалось проверить объём разбора. Запись сохранена.')
    moment = now()
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        control = db.execute("SELECT value FROM operational_state WHERE key='ai_enabled'").fetchone()
        if control and control['value'] == 'false':
            raise LimitError('AI_PAUSED', 'Разбор временно приостановлен. Запись сохранена; попробуйте позже.')
        current = db.execute('SELECT COUNT(*),COALESCE(SUM(audio_seconds),0),COALESCE(SUM(input_chars),0),COALESCE(SUM(output_tokens),0) FROM ai_attempts WHERE created>?', (moment - 86400,)).fetchone()
        additions = (1, audio_seconds, input_chars, output_tokens)
        names = ('AI_DAILY_ATTEMPTS', 'AI_DAILY_AUDIO_SECONDS', 'AI_DAILY_INPUT_CHARS', 'AI_DAILY_OUTPUT_TOKENS')
        if any(current[i] + additions[i] > setting(name) for i, name in enumerate(names)):
            raise LimitError('AI_SERVICE_LIMIT', 'Общий лимит разбора на сегодня достигнут. Запись сохранена; продолжите позже.')
        user_count = db.execute('SELECT COUNT(*) FROM ai_attempts WHERE user_id=? AND created>?', (user_id, moment - 86400)).fetchone()[0]
        minute_count = db.execute('SELECT COUNT(*) FROM ai_attempts WHERE created>?', (moment - 60,)).fetchone()[0]
        if user_count >= setting('AI_USER_DAILY_ATTEMPTS'):
            raise LimitError('AI_USER_LIMIT', 'Лимит обработки аккаунта на сегодня достигнут. Запись сохранена.')
        if minute_count >= setting('AI_REQUESTS_PER_MINUTE'):
            raise LimitError('AI_RATE_LIMIT', 'Сервис разбора занят. Запись сохранена; повторите чуть позже.')
        attempt_id = uid()
        db.execute('INSERT INTO ai_attempts(id,user_id,job_id,operation,created,audio_seconds,input_chars,output_tokens) VALUES(?,?,?,?,?,?,?,?)', (attempt_id, user_id, job_id, operation, moment, audio_seconds, input_chars, output_tokens))
    return store, attempt_id


def finish_attempt(reservation, status, latency_ms, gateway_cost=None, provider_request_id=None):
    if reservation:
        store, attempt_id = reservation
        with store.connect() as db:
            db.execute('UPDATE ai_attempts SET status=?,latency_ms=? WHERE id=?', (status, latency_ms, attempt_id))
            attempt = db.execute('SELECT * FROM ai_attempts WHERE id=?', (attempt_id,)).fetchone()
            practice = db.execute('SELECT practice_id FROM jobs WHERE id=? UNION ALL SELECT practice_id FROM live_chunks WHERE id=? LIMIT 1', (attempt['job_id'], attempt['job_id'])).fetchone()
            from .analytics_events import record
            record(db, 'provider_cost_recorded', attempt['user_id'], practice[0] if practice else None,
                   {'attempt_id': attempt_id, 'job_id': attempt['job_id'], 'operation': attempt['operation'],
                    'gateway_cost': gateway_cost, 'cost_unit': 'gateway_unit',
                    'provider_request_id': provider_request_id}, event_id='cost:'+attempt_id)


def queue_capacity(db, kind):
    table = 'jobs' if kind == 'jobs' else 'live_chunks'
    limit = setting('MAX_PENDING_JOBS' if kind == 'jobs' else 'MAX_PENDING_LIVE_CHUNKS')
    if db.execute(f"SELECT COUNT(*) FROM {table} WHERE status IN ('pending','running')").fetchone()[0] >= limit:
        raise LimitError('AI_QUEUE_FULL', 'Очередь разбора заполнена. Запись сохранена; попробуйте чуть позже.')
