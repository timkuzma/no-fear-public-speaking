"""Incremental queue isolation, accounting and whole-speech cache completeness."""
import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from server.app import create_app
from server.live import completed_transcript, process_chunk, snapshot
from server.store import Store
from server.worker import process
from tests.test_backend import account, practice, wav_bytes


@pytest.fixture
def live_app(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.setenv('LLM_API_KEY', 'isolated-test-key')
    monkeypatch.delenv('REQUIRE_INVITE', raising=False)
    monkeypatch.delenv('APP_ORIGIN', raising=False)
    return create_app(tmp_path, start_worker=False)


def send(client, headers, pid, index=0, offset=0, seconds=15, session='a' * 32, audio=None):
    return client.post(f'/api/practices/{pid}/live-chunks', headers=headers, data={'session_id': session, 'index': index, 'offset_seconds': offset}, files={'file': ('chunk.wav', wav_bytes(seconds) if audio is None else audio, 'audio/wav')})


def test_isolation_csrf_and_no_anonymous_upload(live_app):
    one, two = TestClient(live_app), TestClient(live_app)
    headers = account(one)
    other = account(two, 'other@example.org')
    pid = practice(one, headers)
    assert send(TestClient(live_app), {}, pid).status_code == 401
    assert send(one, {}, pid).status_code == 403
    assert send(one, {**headers, 'Origin': 'https://other.invalid'}, pid).status_code == 403
    assert send(two, other, pid).status_code == 404
    assert two.get(f'/api/practices/{pid}/live-transcript?session_id=' + 'a' * 32).status_code == 404
    assert not list(live_app.state.store.media.iterdir())
    assert send(one, headers, pid).status_code == 200


def test_format_sequence_retry_and_quota(live_app, monkeypatch):
    client = TestClient(live_app)
    headers = account(client)
    pid = practice(client, headers)
    assert send(client, headers, pid, audio=b'bad').status_code == 422
    assert send(client, headers, pid, seconds=17).status_code == 413
    assert send(client, headers, pid, index=1).status_code == 409
    assert send(client, headers, pid).status_code == 200
    monkeypatch.setenv('DAILY_LIVE_CHUNK_LIMIT', '1')
    assert send(client, headers, pid).status_code == 200  # identical retry consumes no quota
    assert send(client, headers, pid, audio=wav_bytes(14)).status_code == 409
    assert send(client, headers, pid, index=1, offset=14).status_code == 409
    assert send(client, headers, pid, index=1, offset=15).status_code == 429
    assert len(list(live_app.state.store.media.iterdir())) == 1
    assert client.delete('/api/practices/' + pid, headers=headers).status_code == 200
    pid = practice(client, headers)
    assert send(client, headers, pid).status_code == 429  # deletion cannot reset daily budget


def test_recovery_failures_and_safe_state(live_app, monkeypatch):
    from server import ai
    client = TestClient(live_app)
    headers = account(client)
    pid = practice(client, headers)
    send(client, headers, pid)
    store = live_app.state.store
    chunk = store.claim_live_chunk()
    assert store.claim_live_chunk() is None
    reopened = Store(store.directory)
    reopened.recover_live_chunks()
    assert reopened.claim_live_chunk()['id'] == chunk['id']
    failure = ai.ProviderError('AI_TIMEOUT', 'Не удалось распознать фрагмент.')
    failure.usage = {'operation': 'transcription', 'audio_seconds': 15, 'input_tokens': None, 'output_tokens': None}
    monkeypatch.setattr(ai, 'transcribe', AsyncMock(side_effect=failure))
    asyncio.run(process_chunk(store, chunk))
    result = client.get(f'/api/practices/{pid}/live-transcript?session_id=' + 'a' * 32).json()
    assert result['status'] == 'failed' and result['completed_chunks'] == 0
    assert result['error']['code'] == 'AI_TIMEOUT'
    assert len(store.all('SELECT * FROM usage')) == 1
    assert client.delete('/api/practices/' + pid, headers=headers).status_code == 200
    assert not list(store.media.iterdir())


def test_superseded_session_and_running_delete(live_app, monkeypatch):
    client = TestClient(live_app)
    headers = account(client)
    pid = practice(client, headers)
    send(client, headers, pid)
    chunk = live_app.state.store.claim_live_chunk()
    assert client.delete('/api/practices/' + pid, headers=headers).status_code == 409
    assert send(client, headers, pid, session='b' * 32).status_code == 200
    assert send(client, headers, pid, index=1, offset=15).status_code == 409
    monkeypatch.setattr('server.ai.transcribe', AsyncMock(return_value={'text': 'Старое выступление', 'usage': {'audio_seconds': 15}}))
    asyncio.run(process_chunk(live_app.state.store, chunk))
    assert snapshot(live_app.state.store, pid, 'a' * 32)['status'] == 'obsolete'
    assert not (live_app.state.store.media / chunk['filename']).exists()
    assert len(live_app.state.store.all('SELECT * FROM usage')) == 1
    assert client.delete('/api/practices/' + pid, headers=headers).status_code == 200


def bind(client, headers, pid, seconds, session='a' * 32, chunk_count=2):
    return client.post(f'/api/practices/{pid}/segments', headers=headers, data={'kind': 'speech', 'index': 0, 'live_session_id': session, 'live_chunk_count': chunk_count}, files={'file': ('speech.wav', wav_bytes(seconds), 'audio/wav')})


def test_complete_cache_reused_and_partial_falls_back(live_app, monkeypatch):
    from server import ai
    client = TestClient(live_app)
    headers = account(client)
    store = live_app.state.store
    usage = {'operation': 'transcription', 'audio_seconds': 15}
    transcriber = AsyncMock(side_effect=[{'text': 'Речь о нашем проекте.', 'usage': usage}, {'text': 'Его польза для клиентов.', 'usage': usage}])
    monkeypatch.setattr(ai, 'transcribe', transcriber)
    pid = practice(client, headers, questions=True)
    send(client, headers, pid)
    send(client, headers, pid, index=1, offset=15, seconds=5)
    asyncio.run(process_chunk(store, store.claim_live_chunk()))
    asyncio.run(process_chunk(store, store.claim_live_chunk()))
    assert bind(client, headers, pid, 20).status_code == 200
    segment = store.one('SELECT * FROM segments WHERE practice_id=?', (pid,))
    assert completed_transcript(store, segment) == 'Речь о нашем проекте. Его польза для клиентов.'
    generator = AsyncMock(return_value={'questions': ['Как?', 'Почему?', 'Зачем?'], 'usage': {'operation': 'questions'}})
    monkeypatch.setattr(ai, 'generate_questions', generator)
    job_id = client.post(f'/api/practices/{pid}/jobs', headers=headers, json={'kind': 'questions'}).json()['id']
    asyncio.run(process(store, store.claim_job()))
    assert store.one('SELECT status FROM jobs WHERE id=?', (job_id,))['status'] == 'succeeded'
    assert transcriber.await_count == 2  # no duplicate full media ASR
    assert generator.await_args.args[1] == completed_transcript(store, segment)

    # A successful prefix is insufficient to generate questions on the whole speech.
    pid2 = practice(client, headers, questions=True)
    send(client, headers, pid2)
    transcriber.side_effect = None
    transcriber.return_value = {'text': 'Полная речь вместо префикса.', 'usage': usage}
    asyncio.run(process_chunk(store, store.claim_live_chunk()))
    assert bind(client, headers, pid2, 20).status_code == 200
    segment2 = store.one('SELECT * FROM segments WHERE practice_id=?', (pid2,))
    assert completed_transcript(store, segment2) is None
    client.post(f'/api/practices/{pid2}/jobs', headers=headers, json={'kind': 'questions'})
    before = transcriber.await_count
    asyncio.run(process(store, store.claim_job()))
    assert transcriber.await_count == before + 1
    assert generator.await_args.args[1] == 'Полная речь вместо префикса.'


def test_binding_rejects_foreign_or_answer_session(live_app):
    client = TestClient(live_app)
    headers = account(client)
    pid = practice(client, headers)
    send(client, headers, pid)
    assert bind(client, headers, pid, 15, session='b' * 32).status_code == 409
    assert not live_app.state.store.all('SELECT * FROM segments')
    assert len(list(live_app.state.store.media.iterdir())) == 1


def test_missing_short_tail_cannot_match_by_duration_tolerance(live_app, monkeypatch):
    client = TestClient(live_app)
    headers = account(client)
    pid = practice(client, headers)
    store = live_app.state.store
    send(client, headers, pid)
    monkeypatch.setattr('server.ai.transcribe', AsyncMock(return_value={'text': 'Основная речь.', 'usage': {'audio_seconds': 15}}))
    asyncio.run(process_chunk(store, store.claim_live_chunk()))
    assert bind(client, headers, pid, 15.6, chunk_count=2).status_code == 200
    assert completed_transcript(store, store.one('SELECT * FROM segments WHERE practice_id=?', (pid,))) is None


def test_single_sample_final_tail_is_accepted(live_app):
    client = TestClient(live_app)
    headers = account(client)
    pid = practice(client, headers)
    assert send(client, headers, pid).status_code == 200
    assert send(client, headers, pid, index=1, offset=15, seconds=1 / 16000).status_code == 200


def test_quiet_final_chunk_completes_coverage_without_fake_usage(live_app, monkeypatch):
    from server import ai
    client = TestClient(live_app)
    headers = account(client)
    pid = practice(client, headers)
    store = live_app.state.store
    send(client, headers, pid)
    send(client, headers, pid, index=1, offset=15, seconds=2.7)
    no_speech = ai.ProviderError('NO_SPEECH', 'В записи не слышно речи.')
    monkeypatch.setattr(ai, 'transcribe', AsyncMock(side_effect=[{'text': 'Выступление о проекте.', 'usage': {'audio_seconds': 15}}, no_speech]))
    asyncio.run(process_chunk(store, store.claim_live_chunk()))
    asyncio.run(process_chunk(store, store.claim_live_chunk()))
    assert bind(client, headers, pid, 17.7).status_code == 200
    result = snapshot(store, pid, 'a' * 32)
    assert result['status'] == 'ready' and result['completed_chunks'] == 2
    assert 'error' not in result
    assert completed_transcript(store, store.one('SELECT * FROM segments WHERE practice_id=?', (pid,))) == 'Выступление о проекте.'
    assert len(store.all('SELECT * FROM usage')) == 1  # local silence detection has no provider bill
    assert not store.all("SELECT * FROM events WHERE kind='service_failure'")


def test_all_quiet_chunks_fall_back_and_provider_empty_usage_is_retained(live_app, monkeypatch):
    from server import ai
    client = TestClient(live_app)
    headers = account(client)
    pid = practice(client, headers, questions=True)
    store = live_app.state.store
    send(client, headers, pid)
    no_speech = ai.ProviderError('NO_SPEECH', 'Речь не распознана.')
    no_speech.usage = {'audio_seconds': 15, 'input_tokens': None, 'output_tokens': None, 'operation': 'transcription'}
    transcriber = AsyncMock(side_effect=no_speech)
    monkeypatch.setattr(ai, 'transcribe', transcriber)
    asyncio.run(process_chunk(store, store.claim_live_chunk()))
    assert bind(client, headers, pid, 15, chunk_count=1).status_code == 200
    assert completed_transcript(store, store.one('SELECT * FROM segments WHERE practice_id=?', (pid,))) is None
    assert len(store.all('SELECT * FROM usage')) == 1
    response = client.post(f'/api/practices/{pid}/jobs', headers=headers, json={'kind': 'questions'})
    asyncio.run(process(store, store.claim_job()))
    job = store.one('SELECT * FROM jobs WHERE id=?', (response.json()['id'],))
    assert job['status'] == 'failed' and json.loads(job['error'])['code'] == 'NO_SPEECH'
    assert transcriber.await_count == 2  # full recording validates the entirely silent session
    assert len(store.all('SELECT * FROM usage')) == 2


@pytest.mark.parametrize('active_samples', [0, 257])
def test_negligible_boundary_impulse_never_calls_provider(live_app, monkeypatch, active_samples):
    import io
    import struct
    import wave
    client = TestClient(live_app)
    headers = account(client)
    pid = practice(client, headers)
    destination = io.BytesIO()
    # Loud 16ms residual can pass RMS detection, but has no meaningful speech span.
    with wave.open(destination, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(struct.pack('<h', 12000) * active_samples + b'\0\0' * (15 * 16000 - active_samples))
    assert send(client, headers, pid, audio=destination.getvalue()).status_code == 200
    transcriber = AsyncMock()
    monkeypatch.setattr('server.ai.transcribe', transcriber)
    store = live_app.state.store
    asyncio.run(process_chunk(store, store.claim_live_chunk()))
    assert transcriber.await_count == 0
    assert snapshot(store, pid, 'a' * 32)['completed_chunks'] == 1
    assert store.one('SELECT transcript FROM live_chunks')['transcript'] == ''
    assert not store.all('SELECT * FROM usage')
    assert bind(client, headers, pid, 15, chunk_count=1).status_code == 200
    assert completed_transcript(store, store.one('SELECT * FROM segments')) is None


@pytest.mark.parametrize('amplitude', [64, 256])
def test_activity_gate_preserves_short_sustained_tail(live_app, monkeypatch, amplitude):
    import io
    import struct
    import wave
    client = TestClient(live_app)
    headers = account(client)
    pid = practice(client, headers)
    destination = io.BytesIO()
    with wave.open(destination, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(struct.pack('<h', amplitude) * 3200)
    assert send(client, headers, pid, audio=destination.getvalue()).status_code == 200
    transcriber = AsyncMock(return_value={'text': 'Да.', 'usage': {'audio_seconds': 0.2}})
    monkeypatch.setattr('server.ai.transcribe', transcriber)
    store = live_app.state.store
    asyncio.run(process_chunk(store, store.claim_live_chunk()))
    assert transcriber.await_count == 1
    assert snapshot(store, pid, 'a' * 32)['transcript'] == 'Да.'


def test_five_second_chunks_cover_ten_minutes_and_replay_without_extra_quota(live_app):
    client = TestClient(live_app)
    headers = account(client)
    response = client.post('/api/practices', headers=headers, json={
        'scenario': 'speech', 'topic': 'Длинное выступление', 'duration': 10,
        'questions': True, 'criteria': '',
    })
    assert response.status_code == 200
    pid = response.json()['id']
    audio = wav_bytes(5)
    for index in range(120):
        response = send(client, headers, pid, index=index, offset=index * 5, audio=audio)
        assert response.status_code == 200, (index, response.text)
    store = live_app.state.store
    assert send(client, headers, pid, index=119, offset=595, audio=audio).status_code == 200
    assert len(store.all('SELECT * FROM live_chunks WHERE practice_id=?', (pid,))) == 120
    assert store.one("SELECT COUNT(*) AS n FROM rate_limits WHERE key LIKE 'live:%'")['n'] == 120
    assert send(client, headers, pid, index=128, offset=600, audio=audio).status_code == 422
    assert bind(client, headers, pid, 600, chunk_count=120).status_code == 200
    store.execute("UPDATE live_chunks SET status='succeeded',transcript='Слова выступления.' WHERE practice_id=?", (pid,))
    segment = store.one('SELECT * FROM segments WHERE practice_id=?', (pid,))
    assert completed_transcript(store, segment) == ' '.join(['Слова выступления.'] * 120)


def test_five_second_transcript_and_tail_are_reused_without_full_asr(live_app, monkeypatch):
    from server import ai
    client = TestClient(live_app)
    headers = account(client)
    pid = practice(client, headers, questions=True)
    transcriber = AsyncMock(side_effect=[
        {'text': text, 'usage': {'operation': 'transcription', 'audio_seconds': seconds}}
        for text, seconds in [('Начало речи.', 5), ('Продолжение мысли.', 5), ('Вывод.', 2)]
    ])
    monkeypatch.setattr(ai, 'transcribe', transcriber)
    store = live_app.state.store
    for index, seconds in enumerate([5, 5, 2]):
        assert send(client, headers, pid, index=index, offset=index * 5, seconds=seconds).status_code == 200
        asyncio.run(process_chunk(store, store.claim_live_chunk()))
    assert bind(client, headers, pid, 12, chunk_count=3).status_code == 200
    generator = AsyncMock(return_value={'questions': ['Как?', 'Почему?', 'Зачем?'], 'usage': {'operation': 'questions'}})
    monkeypatch.setattr(ai, 'generate_questions', generator)
    assert client.post(f'/api/practices/{pid}/jobs', headers=headers, json={'kind': 'questions'}).status_code == 200
    asyncio.run(process(store, store.claim_job()))
    assert transcriber.await_count == 3
    assert generator.await_args.args[1] == 'Начало речи. Продолжение мысли. Вывод.'
