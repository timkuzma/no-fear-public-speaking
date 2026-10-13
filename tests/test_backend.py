import asyncio
import hashlib
import io
import json
import wave
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from server.app import create_app
from server.store import now
from server.worker import process


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.delenv('REQUIRE_INVITE', raising=False)
    monkeypatch.delenv('APP_ORIGIN', raising=False)
    monkeypatch.delenv('LLM_API_KEY', raising=False)
    return create_app(tmp_path, start_worker=False)


def account(client, email='one@example.org'):
    response = client.post('/api/auth/register', json={'email': email, 'name': 'Тестовый пользователь', 'password': 'LongEnoughPassword123', 'role': 'student'})
    assert response.status_code == 200, response.text
    return {'X-CSRF-Token': response.json()['csrf_token']}


def practice(client, headers, questions=False):
    response = client.post('/api/practices', headers=headers, json={'scenario': 'speech', 'topic': 'Защита идеи', 'duration': 1, 'questions': questions, 'criteria': ''})
    assert response.status_code == 200, response.text
    return response.json()['id']


def wav_bytes(seconds=1):
    destination = io.BytesIO()
    with wave.open(destination, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b'\x00\x01' * int(seconds * 16000))
    return destination.getvalue()


def upload(client, headers, pid, data=None, kind='speech', index=0):
    return client.post(f'/api/practices/{pid}/segments', headers=headers, data={'kind': kind, 'index': index}, files={'file': ('sample.wav', wav_bytes() if data is None else data, 'audio/wav')})


@pytest.mark.parametrize('field,value,expected', [
    ('password', 'short', 'Пароль'),
    ('email', 'not-an-email', 'электронную почту'),
    ('name', ' ', 'имя'),
])
def test_registration_errors_only_describe_the_invalid_field(app, field, value, expected):
    client = TestClient(app)
    body = {'email': 'person@example.org', 'name': 'Имя', 'password': 'LongEnoughPassword123'}
    body[field] = value
    response = client.post('/api/auth/register', json=body)
    assert response.status_code == 422
    error = response.json()['error']
    assert expected in error['message']
    assert 'трениров' not in error['message'].lower()
    assert 'минут' not in error['message']
    assert [item['field'] for item in error['fields']] == [field]
    assert not app.state.store.one('SELECT id FROM users')


@pytest.mark.parametrize('duration', [0.5, 1, 3, 4.25, 5, 10])
def test_user_chosen_speech_time_and_topic_are_saved(app, duration):
    client = TestClient(app)
    headers = account(client)
    response = client.post('/api/practices', headers=headers, json={
        'scenario': 'speech', 'topic': 'Открытие новой библиотеки',
        'duration': duration, 'questions': True, 'criteria': '',
    })
    assert response.status_code == 200
    assert response.json()['config']['duration'] == duration
    assert response.json()['config']['topic'] == 'Открытие новой библиотеки'
    assert response.json()['config']['criteria'] == ''


def test_ten_minute_speech_reserves_time_for_all_three_answers(app, monkeypatch):
    client = TestClient(app)
    headers = account(client)
    response = client.post('/api/practices', headers=headers, json={
        'scenario': 'speech', 'duration': 10, 'questions': True,
    })
    pid = response.json()['id']
    # Decoding itself has real-media tests; exercise measured durations here.
    probe = AsyncMock(return_value={'duration_seconds': 600, 'extension': '.wav', 'mime_type': 'audio/wav'})
    monkeypatch.setattr('server.app.decoded_duration', probe)
    assert upload(client, headers, pid).status_code == 200
    app.state.store.execute('UPDATE practices SET questions=? WHERE id=?',
                            (json.dumps(['Первый вопрос?', 'Второй вопрос?', 'Третий вопрос?']), pid))
    probe.return_value['duration_seconds'] = 60
    for index in (1, 2):
        assert upload(client, headers, pid, kind='answer', index=index).status_code == 200
    probe.return_value['duration_seconds'] = 61
    assert upload(client, headers, pid, kind='answer', index=3).status_code == 413
    probe.return_value['duration_seconds'] = 60
    assert upload(client, headers, pid, kind='answer', index=3).status_code == 200
    saved = client.get('/api/practices/' + pid).json()['segments']
    assert len(saved) == 4
    assert sum(item['duration_seconds'] for item in saved) == 780


def test_auth_csrf_and_isolation(app):
    one, two = TestClient(app), TestClient(app)
    assert one.get('/api/auth/me').json()['user'] is None
    headers = account(one)
    h2 = account(two, 'two@example.org')
    pid = practice(one, headers)
    assert one.post('/api/practices', json={'scenario': 'speech', 'duration': 1}).status_code == 403
    assert one.post('/api/practices', headers={**headers, 'Origin': 'https://attacker.invalid'}, json={'scenario': 'speech', 'duration': 1}).status_code == 403
    assert two.get('/api/practices/' + pid).status_code == 404
    assert two.delete('/api/practices/' + pid, headers=h2).status_code == 404
    assert two.get('/api/practices').json()['total'] == 0
    assert one.get('/api/auth/me').json()['user']['email'] == 'one@example.org'
    assert one.post('/api/auth/logout', headers=headers).status_code == 200
    assert one.get('/api/practices').status_code == 401


def test_no_local_password_and_login(app):
    client = TestClient(app)
    headers = account(client)
    row = app.state.store.one('SELECT * FROM users')
    assert row['password'].startswith('$argon2id$')
    client.post('/api/auth/logout', headers=headers)
    assert client.post('/api/auth/login', json={'email': 'one@example.org', 'password': 'wrong'}).status_code == 401
    response = client.post('/api/auth/login', json={'email': 'ONE@example.org', 'password': 'LongEnoughPassword123'})
    assert response.status_code == 200
    assert response.json()['provider_ready'] is False
    assert response.json()['registration_requires_invite'] is False
    assert 'httponly' in response.headers['set-cookie'].lower()


def test_upload_private_persist_duplicate_and_delete(app, monkeypatch):
    # Actual FFmpeg upload validation runs in the separate real media test.
    monkeypatch.setattr('server.app.decoded_duration', AsyncMock(return_value={'duration_seconds': 1, 'extension': '.wav', 'mime_type': 'audio/wav'}))
    one, two = TestClient(app), TestClient(app)
    headers = account(one)
    account(two, 'two@example.org')
    pid = practice(one, headers)
    response = upload(one, headers, pid)
    assert response.status_code == 200
    segment = response.json()
    assert upload(one, headers, pid).status_code == 409
    assert len(list(app.state.store.media.iterdir())) == 1
    assert two.get(segment['media_url']).status_code == 404
    assert one.get(segment['media_url']).content == wav_bytes()
    assert one.get('/data/pilot.sqlite3').status_code == 404
    recreated = create_app(app.state.store.directory, start_worker=False)
    # Existing session is persisted in SQLite across application recreation.
    again = TestClient(recreated)
    again.cookies.update(one.cookies)
    assert again.get('/api/practices/' + pid).json()['segments'][0]['id'] == segment['id']
    assert again.delete('/api/practices/' + pid, headers=headers).status_code == 200
    assert not list(app.state.store.media.iterdir())
    assert again.get(segment['media_url']).status_code == 404


def test_actual_media_decode_and_invalid(app):
    client = TestClient(app)
    headers = account(client)
    pid = practice(client, headers)
    assert upload(client, headers, pid, b'not an audio file').status_code == 422
    assert not list(app.state.store.media.iterdir())
    response = upload(client, headers, pid)
    assert response.status_code == 200, response.text
    assert response.json()['duration_seconds'] == pytest.approx(1, abs=0.03)


def test_limits_and_quota(app, monkeypatch):
    client = TestClient(app)
    headers = account(client)
    assert app.state.store.one('SELECT consent FROM users')['consent'] == 0
    monkeypatch.setattr('server.app.decoded_duration', AsyncMock(return_value={'duration_seconds': 599, 'extension': '.wav', 'mime_type': 'audio/wav'}))
    pid = practice(client, headers, questions=True)
    assert upload(client, headers, pid).status_code == 200
    app.state.store.execute('UPDATE practices SET questions=? WHERE id=?', (json.dumps(['Один?', 'Два?', 'Три?']), pid))
    assert upload(client, headers, pid, kind='answer', index=1).status_code == 413
    assert len(list(app.state.store.media.iterdir())) == 1
    monkeypatch.setenv('MAX_UPLOAD_BYTES', '5')
    pid2 = practice(client, headers)
    assert upload(client, headers, pid2).status_code == 413
    for _ in range(28):
        practice(client, headers)
    assert client.post('/api/practices', headers=headers, json={'scenario': 'speech', 'duration': 1}).status_code == 429


def test_reset_single_use_invalidates_sessions_and_invite(app, monkeypatch):
    client = TestClient(app)
    account(client)
    store = app.state.store
    user = store.one('SELECT id FROM users')
    token = 'OperatorRecoveryToken123'
    store.execute('INSERT INTO resets VALUES(?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), user['id'], now() + 60))
    assert client.post('/api/auth/reset', json={'token': token, 'password': 'ReplacementPassword123'}).status_code == 200
    assert client.get('/api/auth/me').json()['user'] is None
    assert client.post('/api/auth/reset', json={'token': token, 'password': 'ReplacementPassword123'}).status_code == 400
    assert client.post('/api/auth/login', json={'email': 'one@example.org', 'password': 'ReplacementPassword123'}).status_code == 200
    monkeypatch.setenv('REQUIRE_INVITE', '1')
    second = TestClient(app)
    body = {'email': 'invite@example.org', 'name': 'Новый', 'password': 'LongEnoughPassword123', 'consent': True}
    assert second.post('/api/auth/register', json=body).status_code == 403
    invitation = 'OneUseInvitation123'
    store.execute('INSERT INTO invites VALUES(?,?,?)', (hashlib.sha256(invitation.encode()).hexdigest(), now() + 60, 1))
    assert second.post('/api/auth/register', json={**body, 'invite_code': invitation}).status_code == 200
    assert second.post('/api/auth/register', json={**body, 'email': 'another@example.org', 'invite_code': invitation}).status_code == 403


def test_jobs_persist_transcript_retry_recovery(app, monkeypatch):
    import server.ai as ai
    monkeypatch.setenv('LLM_API_KEY', 'synthetic-test-key')
    monkeypatch.setenv('LLM_BASE_URL', 'https://provider.test/v1')
    monkeypatch.setattr('server.app.decoded_duration', AsyncMock(return_value={'duration_seconds': 1, 'extension': '.wav', 'mime_type': 'audio/wav'}))
    client = TestClient(app)
    headers = account(client)
    pid = practice(client, headers)
    upload(client, headers, pid)
    usage = {'model': 'test', 'input_tokens': 4, 'output_tokens': 5, 'audio_seconds': 1, 'latency_ms': 10, 'operation': 'test'}
    transcriber = AsyncMock(return_value={'text': 'Моя речь о проекте.', 'duration_seconds': 1, 'usage': usage})
    monkeypatch.setattr(ai, 'transcribe', transcriber)
    monkeypatch.setattr(ai, 'analyze', AsyncMock(side_effect=ai.ProviderError('TEMPORARY', 'Попробуйте ещё раз.')))
    job_response = client.post(f'/api/practices/{pid}/jobs', headers=headers, json={'kind': 'report'})
    assert job_response.status_code == 200
    assert client.post(f'/api/practices/{pid}/jobs', headers=headers, json={'kind': 'report'}).json()['id'] == job_response.json()['id']
    assert client.delete('/api/practices/' + pid, headers=headers).status_code == 409
    job = app.state.store.claim_job()
    asyncio.run(process(app.state.store, job))
    assert client.get('/api/jobs/' + job['id']).json()['status'] == 'failed'
    assert app.state.store.one('SELECT * FROM segments')['transcript'] == 'Моя речь о проекте.'
    assert len(app.state.store.all('SELECT * FROM usage')) == 1
    report = {'demo': False, 'insight': 'Достаточно ясное начало.', 'transcript': 'Моя речь о проекте.'}
    monkeypatch.setattr(ai, 'analyze', AsyncMock(return_value={'report': report, 'usage': usage}))
    retry = client.post(f'/api/practices/{pid}/jobs', headers=headers, json={'kind': 'report'}).json()
    job = app.state.store.claim_job()
    app.state.store.recover_jobs()
    recovered = app.state.store.claim_job()
    assert recovered['id'] == retry['id']
    asyncio.run(process(app.state.store, recovered))
    assert transcriber.await_count == 1
    assert client.get('/api/practices/' + pid).json()['report'] == report
    assert client.post(f'/api/practices/{pid}/jobs', headers=headers, json={'kind': 'report'}).json()['id'] == retry['id']
    assert len(app.state.store.all('SELECT * FROM usage')) == 2


def test_operator_metrics_and_production_fail_closed(app, monkeypatch, tmp_path):
    client = TestClient(app)
    assert client.get('/api/operator/metrics').status_code == 401
    monkeypatch.setenv('OPERATOR_TOKEN', 'operator-test-token-long-enough')
    headers = account(client)
    practice(client, headers)
    response = client.get('/api/operator/metrics', headers={'Authorization': 'Bearer operator-test-token-long-enough'})
    assert response.status_code == 200
    assert response.json()['dau'] == 1
    assert 'password' not in response.text
    monkeypatch.setenv('APP_ENV', 'production')
    with pytest.raises(RuntimeError):
        create_app(tmp_path / 'prod', start_worker=False)
    monkeypatch.setenv('APP_ORIGIN', 'https://pilot.example.org')
    production = TestClient(create_app(tmp_path / 'prod', start_worker=False), base_url='https://pilot.example.org')
    assert production.get('/api/auth/me').json()['registration_requires_invite'] is True


def test_upload_guard_auth_and_chunked_limit_before_parser(app, monkeypatch):
    client = TestClient(app)
    response = client.post('/api/practices/nonexistent/segments', content=b'x' * 100000, headers={'Content-Type': 'multipart/form-data; boundary=none'})
    assert response.status_code == 401
    headers = account(client)
    pid = practice(client, headers)
    monkeypatch.setenv('MAX_UPLOAD_BYTES', '5')
    response = client.post(f'/api/practices/{pid}/segments', headers={**headers, 'Content-Type': 'application/octet-stream'}, content=iter([b'x' * 9000, b'y' * 9000]))
    assert response.status_code == 413
    assert not list(app.state.store.media.iterdir())
    assert client.post('/api/auth/login', content=b'x' * 70000, headers={'Content-Type': 'application/json'}).status_code == 413


def test_usage_failure_and_events_export(app, monkeypatch):
    import server.ai as ai
    monkeypatch.setenv('LLM_API_KEY', 'synthetic-test-key')
    monkeypatch.setenv('LLM_BASE_URL', 'https://provider.test/v1')
    monkeypatch.setenv('OPERATOR_TOKEN', 'operator-test-token-long-enough')
    monkeypatch.setattr('server.app.decoded_duration', AsyncMock(return_value={'duration_seconds': 1, 'extension': '.wav', 'mime_type': 'audio/wav'}))
    client = TestClient(app)
    headers = account(client)
    pid = practice(client, headers)
    upload(client, headers, pid)
    failure_usage = {'model': 'test', 'operation': 'transcription', 'input_tokens': None, 'output_tokens': None, 'audio_seconds': 1, 'latency_ms': 20}
    exc = ai.ProviderError('PROVIDER_TIMEOUT', 'Попробуйте ещё раз.')
    exc.usage = failure_usage
    monkeypatch.setattr(ai, 'transcribe', AsyncMock(side_effect=exc))
    client.post(f'/api/practices/{pid}/jobs', headers=headers, json={'kind': 'report'})
    asyncio.run(process(app.state.store, app.state.store.claim_job()))
    assert len(app.state.store.all('SELECT * FROM usage')) == 1
    operator = {'Authorization': 'Bearer operator-test-token-long-enough'}
    exported = client.get('/api/operator/export?kind=events', headers=operator).json()['items']
    assert any(row['kind'] == 'service_failure' and row['data']['code'] == 'PROVIDER_TIMEOUT' for row in exported)
    assert any(row['kind'] == 'request' and 'latency_ms' in row['data'] for row in exported)
    assert client.get('/api/operator/export?kind=events&format=csv', headers=operator).status_code == 200


def test_delete_failure_keeps_retryable_metadata(app, monkeypatch):
    monkeypatch.setattr('server.app.decoded_duration', AsyncMock(return_value={'duration_seconds': 1, 'extension': '.wav', 'mime_type': 'audio/wav'}))
    client = TestClient(app)
    headers = account(client)
    pid = practice(client, headers)
    upload(client, headers, pid)
    original = Path.unlink

    def blocked(path, *args, **kwargs):
        if path.parent == app.state.store.media:
            raise OSError('Synthetic filesystem failure')
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'unlink', blocked)
    assert client.delete('/api/practices/' + pid, headers=headers).status_code == 500
    assert client.get('/api/practices/' + pid).status_code == 200
    monkeypatch.setattr(Path, 'unlink', original)
    assert client.delete('/api/practices/' + pid, headers=headers).status_code == 200
    assert not list(app.state.store.media.iterdir())


def test_private_permissions_and_export_limit(app, monkeypatch):
    assert app.state.store.directory.stat().st_mode & 0o077 == 0
    assert app.state.store.media.stat().st_mode & 0o077 == 0
    assert app.state.store.path.stat().st_mode & 0o077 == 0
    monkeypatch.setenv('OPERATOR_TOKEN', 'operator-test-token-long-enough')
    headers = {'Authorization': 'Bearer operator-test-token-long-enough'}
    client = TestClient(app)
    for _ in range(3):
        app.state.store.event('test')
    assert len(client.get('/api/operator/export?kind=events&limit=1', headers=headers).json()['items']) == 1
    csrf = account(client)
    pid = practice(client, csrf)
    assert client.delete('/api/practices/' + pid, headers=csrf).status_code == 200
    assert client.get('/api/operator/metrics', headers=headers).json()['dau'] == 1


def test_streaming_webm_upload_finalized_seekable(app):
    import subprocess
    import imageio_ffmpeg
    binary = imageio_ffmpeg.get_ffmpeg_exe()
    streaming = subprocess.run([binary, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=16000', '-t', '1', '-c:a', 'libopus', '-f', 'webm', '-live', '1', 'pipe:1'], capture_output=True, check=True, timeout=10).stdout
    # The streaming container has no EBML Duration field, like browser MediaRecorder.
    assert b'\x44\x89' not in streaming
    client = TestClient(app)
    headers = account(client)
    pid = practice(client, headers)
    response = client.post(f'/api/practices/{pid}/segments', headers=headers, data={'kind': 'speech', 'index': 0}, files={'file': ('stream.webm', streaming, 'audio/webm')})
    assert response.status_code == 200, response.text
    persisted = client.get(response.json()['media_url']).content
    # Final file now contains Duration metadata and Cues for seeking.
    assert b'\x44\x89' in persisted
    assert b'\x1c\x53\xbb\x6b' in persisted
    assert 'webm' in client.get(response.json()['media_url']).headers['content-type']
    assert len(list(app.state.store.media.iterdir())) == 1
    assert next(app.state.store.media.iterdir()).stat().st_mode & 0o077 == 0


def test_guard_errors_logged_once_and_redacted(app, monkeypatch):
    client = TestClient(app)
    before = app.state.store.one("SELECT COUNT(*) AS n FROM events WHERE kind='request'")['n']
    response = client.post('/api/practices/private-id/segments?secret=never-log', content=b'private audio contents', headers={'Content-Type': 'audio/webm'})
    assert response.status_code == 401
    rows = app.state.store.all("SELECT data FROM events WHERE kind='request'")
    assert len(rows) == before + 1
    data = json.loads(rows[-1]['data'])
    assert data['route'] == '/api/practices/{practice_id}/segments'
    assert data['status'] == 401
    assert data['error_code'] == 'AUTH_REQUIRED'
    assert data['request_id'] == response.headers['x-request-id']
    assert 'private-id' not in rows[-1]['data']
    assert 'never-log' not in rows[-1]['data']
    assert 'private audio' not in rows[-1]['data']


def test_webm_cancel_when_child_already_exited(tmp_path, monkeypatch):
    import server.media as media
    path = tmp_path / 'cancel.webm'
    path.write_bytes(b'synthetic-container')

    class ExitedChild:
        returncode = 0
        calls = 0
        kills = 0

        async def wait(self):
            self.calls += 1
            if self.calls == 1:
                raise asyncio.CancelledError
            return 0

        def kill(self):
            self.kills += 1
            raise ProcessLookupError

    child = ExitedChild()
    monkeypatch.setattr(media.asyncio, 'create_subprocess_exec', AsyncMock(return_value=child))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(media.finalize_webm(path))
    assert child.kills == 1
    assert child.calls == 2
    assert path.is_file()
    assert not (tmp_path / 'cancel.finalizing.webm').exists()


def test_practice_import_replay_is_scoped_and_idempotent(app):
    one, two = TestClient(app), TestClient(app)
    headers = account(one)
    other_headers = account(two, 'second-import@example.org')
    body = {'scenario': 'speech', 'topic': 'Запись до регистрации', 'duration': 1, 'idempotency_key': 'a' * 32}
    first = one.post('/api/practices', headers=headers, json=body)
    replay = one.post('/api/practices', headers=headers, json=body)
    other = two.post('/api/practices', headers=other_headers, json=body)
    assert first.status_code == replay.status_code == other.status_code == 200
    assert first.json()['id'] == replay.json()['id'] != other.json()['id']
    assert 'idempotency_key' not in first.json()['config']
    assert one.get('/api/practices').json()['total'] == 1
    assert app.state.store.one("SELECT COUNT(*) AS n FROM events WHERE kind='practice_started'")['n'] == 2
    assert two.get('/api/practices/' + first.json()['id']).status_code == 404
    changed = one.post('/api/practices', headers=headers, json={**body, 'topic': 'Другая тема'})
    assert changed.status_code == 409
    assert one.post('/api/practices', json=body).status_code == 403


def test_practice_import_can_resume_after_upload_and_quota(app, monkeypatch):
    monkeypatch.setattr('server.app.decoded_duration', AsyncMock(return_value={'duration_seconds': 1, 'extension': '.wav'}))
    client = TestClient(app)
    headers = account(client)
    body = {'scenario': 'speech', 'topic': 'Гостевой импорт', 'duration': 1, 'idempotency_key': 'b' * 32}
    first = client.post('/api/practices', headers=headers, json=body).json()
    assert upload(client, headers, first['id']).status_code == 200
    user_id = client.get('/api/auth/me').json()['user']['id']
    for _ in range(30):
        app.state.store.limited('practice:' + user_id, 100, 86400)
    replay = client.post('/api/practices', headers=headers, json=body)
    assert replay.status_code == 200
    assert replay.json()['id'] == first['id']
    assert len(replay.json()['segments']) == 1
    assert client.get('/api/practices').json()['total'] == 1
    assert client.post('/api/practices', headers=headers, json={**body, 'idempotency_key': 'not-a-key'}).status_code == 422


def test_upload_key_replays_after_restart_and_processing_without_quota(app, monkeypatch):
    monkeypatch.setattr('server.app.decoded_duration', AsyncMock(return_value={'duration_seconds': 1, 'extension': '.wav', 'mime_type': 'audio/wav'}))
    client = TestClient(app)
    headers = account(client)
    pid = practice(client, headers)
    key = 'a' * 32
    def send(target=client, content=None):
        return target.post(f'/api/practices/{pid}/segments', headers=headers,
            data={'kind': 'speech', 'index': 0, 'client_key': key},
            files={'file': ('sample.wav', wav_bytes() if content is None else content, 'audio/wav')})
    first = send()
    assert first.status_code == 200
    segment = first.json()
    assert segment['client_key'] == key
    assert client.get('/api/practices/' + pid).json()['segments'][0]['client_key'] == key
    app.state.store.execute("UPDATE practices SET status='processing' WHERE id=?", (pid,))
    recreated = create_app(app.state.store.directory, start_worker=False)
    restarted = TestClient(recreated)
    restarted.cookies.update(client.cookies)
    replay = send(restarted)
    assert replay.status_code == 200 and replay.json()['id'] == segment['id']
    assert recreated.state.store.one("SELECT COUNT(*) AS n FROM rate_limits WHERE key LIKE 'upload:%'")['n'] == 1
    assert len(list(recreated.state.store.media.iterdir())) == 1
    conflict = send(restarted, b'different bytes')
    assert conflict.status_code == 409
    assert conflict.json()['error']['code'] == 'UPLOAD_KEY_CONFLICT'
    app.state.store.execute("UPDATE practices SET status='draft' WHERE id=?", (pid,))
    assert restarted.delete('/api/practices/' + pid, headers=headers).status_code == 200
    assert not recreated.state.store.all('SELECT * FROM segment_uploads')


def test_upload_key_cannot_reuse_another_stage_or_account(app, monkeypatch):
    monkeypatch.setattr('server.app.decoded_duration', AsyncMock(return_value={'duration_seconds': 1, 'extension': '.wav', 'mime_type': 'audio/wav'}))
    one, two = TestClient(app), TestClient(app)
    h1, h2 = account(one), account(two, 'second@example.org')
    pid = practice(one, h1, questions=True)
    key = 'b' * 32
    def send(client, headers, kind='speech', index=0, client_key=key):
        return client.post(f'/api/practices/{pid}/segments', headers=headers,
            data={'kind': kind, 'index': index, 'client_key': client_key},
            files={'file': ('sample.wav', wav_bytes(), 'audio/wav')})
    assert send(one, h1).status_code == 200
    assert send(two, h2).status_code == 404
    assert send(one, h1, client_key='c' * 32).json()['error']['code'] == 'SEGMENT_EXISTS'
    app.state.store.execute('UPDATE practices SET questions=? WHERE id=?', (json.dumps(['Вопрос?']), pid))
    assert send(one, h1, 'answer', 1).json()['error']['code'] == 'UPLOAD_KEY_CONFLICT'
    assert send(one, h1, 'answer', 1, 'invalid-key').status_code == 422
    assert len(app.state.store.all('SELECT * FROM segments')) == 1
