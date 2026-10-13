import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from server import ai, limits, monitoring
from server.app import create_app
from server.locking import data_lock
from server.store import Store, now
from scripts.backup import backup, restore
from scripts.monitor import alerts, transition
from tests.test_backend import account, practice, upload


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.setenv('LLM_API_KEY', 'synthetic-test-key')
    monkeypatch.setenv('LLM_BASE_URL', 'https://provider.test/v1')
    monkeypatch.delenv('APP_ORIGIN', raising=False)
    monkeypatch.delenv('REQUIRE_INVITE', raising=False)
    return Store(tmp_path / 'data')


def test_atomic_global_budget_and_account_deletion_cannot_refund(store, monkeypatch):
    monkeypatch.setenv('AI_DAILY_ATTEMPTS', '3')
    def reserve(_):
        with limits.provider_scope(store, 'user', 'job'):
            try:
                limits.reserve_attempt('report', input_chars=100, output_tokens=3000)
                return True
            except limits.LimitError:
                return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        accepted = list(pool.map(reserve, range(12)))
    assert sum(accepted) == 3
    store.execute('DELETE FROM practices')
    store.execute('DELETE FROM jobs')
    assert limits.totals(store)['attempts'] == 3
    with limits.provider_scope(store, 'user', 'another-job'), pytest.raises(limits.LimitError):
        limits.reserve_attempt('transcription', audio_seconds=1)
    rebuilt = Store(store.directory)
    assert limits.totals(rebuilt)['attempts'] == 3


@pytest.mark.parametrize('setting,first,second', [
    ('AI_DAILY_AUDIO_SECONDS', {'audio_seconds': 8}, {'audio_seconds': 3}),
    ('AI_DAILY_INPUT_CHARS', {'input_chars': 8}, {'input_chars': 3}),
    ('AI_DAILY_OUTPUT_TOKENS', {'output_tokens': 8}, {'output_tokens': 3}),
])
def test_conservative_resource_reservation(store, monkeypatch, setting, first, second):
    monkeypatch.setenv(setting, '10')
    with limits.provider_scope(store, 'user', 'job'):
        reservation = limits.reserve_attempt('fixture', **first)
        limits.finish_attempt(reservation, None, 100)  # Unknown upstream result remains charged to guard.
        with pytest.raises(limits.LimitError):
            limits.reserve_attempt('fixture', **second)
    assert limits.totals(store)['attempts'] == 1


def test_provider_retries_share_durable_budget_and_usage(store, monkeypatch):
    monkeypatch.setenv('AI_DAILY_ATTEMPTS', '1')
    original = httpx.AsyncClient
    received = []
    def handler(request):
        received.append(request)
        return httpx.Response(503)
    async def run():
        with limits.provider_scope(store, 'user', 'job'):
            with patch.object(ai.httpx, 'AsyncClient', side_effect=lambda **kw: original(transport=httpx.MockTransport(handler), **kw)):
                with pytest.raises(ai.ProviderError) as failure:
                    await ai._request('/chat/completions', 'fixture', 'report', payload={'messages':[{'content':'test'}],'max_tokens':3000})
                assert failure.value.code == 'AI_SERVICE_LIMIT'
                assert len(failure.value.usage['attempts']) == 1
    asyncio.run(run())
    assert len(received) == 1
    assert store.one('SELECT status FROM ai_attempts')['status'] == 503


def test_provider_production_requires_scope_and_pause_prevents_network(store, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    async def run():
        with pytest.raises(ai.ProviderError) as error:
            await ai._request('/chat/completions', 'fixture', 'report')
        assert error.value.code == 'AI_CONTEXT_REQUIRED'
        store.execute("INSERT INTO operational_state VALUES('ai_enabled','false',?)", (now(),))
        with limits.provider_scope(store, 'user', 'job'), pytest.raises(ai.ProviderError) as error:
            await ai._request('/chat/completions', 'fixture', 'report')
        assert error.value.code == 'AI_PAUSED'
    asyncio.run(run())
    assert not store.all('SELECT * FROM ai_attempts')


def test_queue_limits_keep_recording_and_replay_active_job(store, monkeypatch):
    monkeypatch.setenv('MAX_PENDING_JOBS', '1')
    app = create_app(store.directory, start_worker=False)
    client = TestClient(app)
    headers = account(client)
    first, second = practice(client, headers), practice(client, headers)
    assert upload(client, headers, first).status_code == 200
    assert upload(client, headers, second).status_code == 200
    first_job = client.post(f'/api/practices/{first}/jobs', headers=headers, json={'kind':'report'})
    assert first_job.status_code == 200
    rejected = client.post(f'/api/practices/{second}/jobs', headers=headers, json={'kind':'report'})
    assert rejected.status_code == 503 and rejected.json()['error']['code'] == 'AI_QUEUE_FULL'
    assert len(client.get('/api/practices/'+second).json()['segments']) == 1
    replay = client.post(f'/api/practices/{first}/jobs', headers=headers, json={'kind':'report'})
    assert replay.json()['id'] == first_job.json()['id']
    assert store.one("SELECT COUNT(*) AS n FROM rate_limits WHERE key LIKE 'job:%'")['n'] == 1


def test_offline_lease_blocks_backup_and_second_application(store):
    with data_lock(store.directory):
        with pytest.raises(RuntimeError, match='in use'):
            backup(store.directory, store.directory.parent / 'backup')
        with pytest.raises(RuntimeError, match='in use'):
            with TestClient(create_app(store.directory, start_worker=False)):
                pass
    saved = store.directory.parent / 'saved'
    backup(store.directory, saved)
    restore(saved, store.directory.parent / 'restored')
    assert (saved/'manifest.json').stat().st_mode & 0o077 == 0


def test_maintenance_blocks_mutations_and_provider_worker_but_allows_status(store, monkeypatch):
    monkeypatch.setenv('OPERATOR_TOKEN', 'operator-fixture-token-long-enough')
    (store.directory/'.maintenance').touch()
    app = create_app(store.directory)
    with TestClient(app) as client:
        assert client.post('/api/auth/register', json={}).status_code == 503
        assert client.get('/api/readiness').json()['maintenance'] is True
        assert client.get('/api/operator/status').status_code == 401
        status = client.get('/api/operator/status', headers={'Authorization':'Bearer operator-fixture-token-long-enough'})
        assert status.status_code == 200
        assert status.json()['workers']['ready'] is True
        assert 'operator-fixture-token-long-enough' not in status.text
        assert client.post('/api/operator/ai', headers={'Authorization':'Bearer operator-fixture-token-long-enough'}, json={'enabled':False}).json()['enabled'] is False


def test_monitor_detects_capacity_queue_errors_and_backup_and_deduplicates(store, monkeypatch):
    monkeypatch.setenv('MIN_FREE_DISK_BYTES', '10000000000000')
    store.execute("INSERT INTO operational_state VALUES('heartbeat',?,?)", (json.dumps({'final_alive':False,'live_alive':True}), now()))
    store.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)', ('job','practice','report','pending','queued',now()-400,None,None,None,None))
    status = monitoring.snapshot(store)
    codes = alerts(status, now())
    assert {'STORAGE_UNAVAILABLE','WORKER_UNAVAILABLE','QUEUE_STALLED','BACKUP_STALE','ENCRYPTED_BACKUP_STALE'} <= set(codes)
    previous = {}
    for _ in range(2):
        previous, change = transition(previous, codes)
        assert change['opened'] == []
    previous, change = transition(previous, codes)
    assert change['opened'] == codes
    previous, change = transition(previous, codes)
    assert change == {'opened':[],'resolved':[]}
    previous, change = transition(previous, [])
    assert change['resolved'] == codes


@pytest.mark.parametrize('bad', ['nan','-1','0','text','1.5'])
def test_invalid_limits_fail_closed(store, monkeypatch, bad):
    monkeypatch.setenv('AI_DAILY_ATTEMPTS', bad)
    with pytest.raises(RuntimeError, match='AI_DAILY_ATTEMPTS'):
        create_app(store.directory)


def test_instance_exclusion_preserves_online_operator_access(store):
    from server.locking import instance_lock
    with instance_lock(store.directory), data_lock(store.directory, shared=True):
        with data_lock(store.directory, shared=True):
            Store(store.directory).execute("INSERT INTO invites VALUES('fixture',?,1)", (now()+60,))
        with pytest.raises(RuntimeError):
            with instance_lock(store.directory):
                pass
        with pytest.raises(RuntimeError):
            backup(store.directory, store.directory.parent/'unsafe')


@pytest.mark.parametrize('setting,code', [('AI_REQUESTS_PER_MINUTE','AI_RATE_LIMIT'),('AI_USER_DAILY_ATTEMPTS','AI_USER_LIMIT')])
def test_minute_and_user_limits_and_rolling_window(store, monkeypatch, setting, code):
    monkeypatch.setenv(setting, '1')
    with limits.provider_scope(store, 'user', 'job'):
        limits.reserve_attempt('fixture')
        with pytest.raises(limits.LimitError) as failure:
            limits.reserve_attempt('fixture')
        assert failure.value.code == code
        store.execute('UPDATE ai_attempts SET created=?', (now()-86401,))
        limits.reserve_attempt('fixture')
    assert limits.totals(store)['attempts'] == 1


def test_live_queue_full_retains_full_recording_fallback(store, monkeypatch):
    from tests.test_live_transcription import send
    monkeypatch.setenv('MAX_PENDING_LIVE_CHUNKS','1')
    app = create_app(store.directory,start_worker=False)
    client = TestClient(app)
    headers = account(client)
    pid = practice(client,headers)
    assert send(client,headers,pid).status_code == 200
    assert send(client,headers,pid).status_code == 200
    response = send(client,headers,pid,index=1,offset=1)
    assert response.status_code == 503 and response.json()['error']['code']=='AI_QUEUE_FULL'
    assert upload(client,headers,pid).status_code == 200
    assert len(store.all('SELECT * FROM live_chunks'))==1


def test_worker_timeout_keeps_saved_segment_and_marks_retryable_failure(store,monkeypatch):
    from server.worker import process
    app=create_app(store.directory,start_worker=False)
    client=TestClient(app)
    headers=account(client)
    pid=practice(client,headers)
    assert upload(client,headers,pid).status_code==200
    job=client.post(f'/api/practices/{pid}/jobs',headers=headers,json={'kind':'report'}).json()
    claimed=store.claim_job()
    async def slow(*args):
        await asyncio.sleep(1)
    monkeypatch.setattr(ai,'transcribe',slow)
    original=limits.setting
    monkeypatch.setattr(limits,'setting',lambda name:0.01 if name=='JOB_TIMEOUT_SECONDS' else original(name))
    asyncio.run(process(store,claimed))
    row=store.one('SELECT * FROM jobs WHERE id=?',(job['id'],))
    assert row['status']=='failed' and json.loads(row['error'])['code']=='PROCESSING_TIMEOUT'
    assert len(client.get('/api/practices/'+pid).json()['segments'])==1


def test_actual_dead_worker_fails_readiness_and_maintenance_does_not_claim(store):
    import time
    app = create_app(store.directory, start_worker=False)
    client = TestClient(app)
    headers = account(client)
    pid = practice(client, headers)
    assert upload(client, headers, pid).status_code == 200
    job = client.post(f'/api/practices/{pid}/jobs', headers=headers, json={'kind':'report'}).json()
    (store.directory/'.maintenance').touch()
    with TestClient(create_app(store.directory)) as live_client:
        time.sleep(0.65)
        assert store.one('SELECT status FROM jobs WHERE id=?', (job['id'],))['status'] == 'pending'
        assert not store.all('SELECT * FROM ai_attempts')
        assert live_client.get('/api/readiness').status_code == 200
        async def kill_worker():
            live_client.app.state.worker_task.cancel()
            try:
                await live_client.app.state.worker_task
            except asyncio.CancelledError:
                pass
        live_client.portal.call(kill_worker)
        response = live_client.get('/api/readiness')
        assert response.status_code == 503 and response.json()['worker_alive'] is False
