"""Content-free operational status, liveness supervision and bounded telemetry."""
import asyncio
import json
import os
import shutil
import sqlite3
import tempfile

from . import limits
from .store import now


def maintenance(store):
    path = store.directory / '.maintenance'
    try:
        return max(0, now() - path.stat().st_mtime)
    except FileNotFoundError:
        return None


def storage_health(store):
    try:
        free = shutil.disk_usage(store.directory).free
        with store.connect() as db:
            db.execute('UPDATE operational_state SET updated=updated WHERE key=?', ('heartbeat',))
        with tempfile.TemporaryFile(dir=store.media) as probe:
            probe.write(b'1')
            probe.flush()
        return {'ready': free >= limits.setting('MIN_FREE_DISK_BYTES'), 'free_bytes': free}
    except (OSError, sqlite3.Error):
        return {'ready': False, 'free_bytes': None}


def snapshot(store, worker_enabled=True):
    moment = now()
    pulse = store.one("SELECT value,updated FROM operational_state WHERE key='heartbeat'")
    workers = json.loads(pulse['value']) if pulse else {'final_alive': False, 'live_alive': False}
    workers['heartbeat_age_seconds'] = max(0, moment - pulse['updated']) if pulse else None
    workers['ready'] = not worker_enabled or bool(pulse and moment - pulse['updated'] < 20 and workers['final_alive'] and workers['live_alive'])
    queues = {}
    for name, table in [('final', 'jobs'), ('live', 'live_chunks')]:
        row = store.one(f"SELECT COUNT(*) AS count,MIN(created) AS oldest FROM {table} WHERE status IN ('pending','running')")
        queues[name] = {'count': row['count'], 'oldest_age_seconds': max(0, moment - row['oldest']) if row['oldest'] else 0}
    failures = store.one("SELECT COUNT(*) AS count FROM events WHERE kind='service_failure' AND created>?", (moment - 900,))['count']
    requests = store.one("SELECT COUNT(*) AS count FROM events WHERE kind='request' AND created>? AND CAST(json_extract(data,'$.status') AS INTEGER)>=500", (moment - 900,))['count']
    attempts = store.one('SELECT COUNT(*) AS count,AVG(latency_ms) AS average_ms FROM ai_attempts WHERE created>? AND (status IS NULL OR status>=400)', (moment - 900,))
    backup = None
    operation = None
    try:
        saved = json.loads((store.directory / '.backup-status.json').read_text())
        backup = {key: saved.get(key) for key in ('verified_at', 'encrypted_at', 'restore_verified_at', 'offsite_configured')}
    except (OSError, ValueError, TypeError):
        pass
    try:
        saved = json.loads((store.directory / '.operation-status.json').read_text())
        operation = {key: saved.get(key) for key in ('action', 'finished_at', 'ok')}
    except (OSError, ValueError, TypeError):
        pass
    budget = {'enabled': limits.enabled(store), 'used': limits.totals(store), 'limits': {name: limits.setting(name) for name in limits.DEFAULTS if name.startswith('AI_')}}
    return {'storage': storage_health(store), 'workers': workers, 'queues': queues, 'maintenance_age_seconds': maintenance(store), 'budget': budget, 'failures_last_15m': failures, 'http_5xx_last_15m': requests, 'provider_failures_last_15m': attempts['count'], 'failed_provider_average_ms': attempts['average_ms'], 'backup': backup, 'last_operation': operation, 'queue_alert_seconds': limits.setting('QUEUE_ALERT_SECONDS'), 'backup_max_age_seconds': limits.setting('BACKUP_MAX_AGE_SECONDS')}


async def supervise(app, store):
    last_prune = 0
    while True:
        workers = {'final_alive': bool(app.state.worker_task and not app.state.worker_task.done()), 'live_alive': bool(app.state.live_worker_task and not app.state.live_worker_task.done())}
        store.execute("INSERT INTO operational_state VALUES('heartbeat',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated=excluded.updated", (json.dumps(workers), now()))
        if now() - last_prune >= 3600:
            with store.connect() as db:
                db.execute('DELETE FROM ai_attempts WHERE created<?', (now() - 2 * 86400,))
                db.execute("DELETE FROM events WHERE created<?", (now() - 90 * 86400,))
                db.execute("DELETE FROM usage WHERE created<?", (now() - 90 * 86400,))
                db.execute('DELETE FROM sessions WHERE expires<?', (now(),))
                db.execute('DELETE FROM resets WHERE expires<?', (now(),))
                db.execute('DELETE FROM invites WHERE expires<?', (now(),))
            last_prune = now()
        await asyncio.sleep(5)
