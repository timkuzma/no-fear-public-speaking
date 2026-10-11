"""Full HTTP flow through a running durable worker, with a bounded provider fixture."""
import io
import time
import wave
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from server.app import create_app


def test_configured_provider_uses_documented_default_base(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.setenv('LLM_API_KEY', 'mock-provider-credential')
    monkeypatch.delenv('LLM_BASE_URL', raising=False)
    with TestClient(create_app(tmp_path, start_worker=False)) as client:
        assert client.get('/api/auth/me').json()['provider_ready'] is True
        assert client.get('/api/readiness').status_code == 200


def test_complete_questions_answers_report_reload(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.delenv('APP_ORIGIN', raising=False)
    monkeypatch.delenv('REQUIRE_INVITE', raising=False)
    monkeypatch.setenv('LLM_API_KEY', 'mock-provider-credential')
    monkeypatch.setenv('LLM_BASE_URL', 'https://provider.invalid/v1')
    usage = {'model':'fixture', 'operation':'fixture', 'input_tokens':10, 'output_tokens':5,
             'audio_seconds':1, 'latency_ms':1, 'attempts':[]}
    monkeypatch.setattr('server.ai.transcribe', AsyncMock(return_value={'text':'Конкретный пример для слушателя.', 'duration_seconds':1, 'usage':usage}))
    monkeypatch.setattr('server.ai.generate_questions', AsyncMock(return_value={'questions':['Первый вопрос?', 'Второй вопрос?', 'Третий вопрос?'], 'usage':usage}))
    report = {'demo':False, 'insight':'Добавь один пример.', 'metrics':[], 'strengths':[],
              'recommendations':[], 'criteria':[], 'limitations':['Только текст'], 'transcript':'Конкретный пример для слушателя.'}
    monkeypatch.setattr('server.ai.analyze', AsyncMock(return_value={'report':report, 'usage':usage}))
    raw = io.BytesIO()
    with wave.open(raw, 'wb') as media:
        media.setnchannels(1)
        media.setsampwidth(2)
        media.setframerate(16000)
        media.writeframes(b'\x00\x01' * 16000)
    app = create_app(tmp_path)
    with TestClient(app) as client:
        registered = client.post('/api/auth/register', json={'email':'flow@example.test', 'name':'Flow fixture',
            'password':'SyntheticPassword123', 'role':'other', 'consent':True})
        assert registered.status_code == 200
        headers = {'X-CSRF-Token':registered.json()['csrf_token']}
        response = client.post('/api/practices', headers=headers, json={'scenario':'defense', 'topic':'Idea', 'duration':1, 'questions':True, 'criteria':''})
        assert response.status_code == 200
        identifier = response.json()['id']

        def upload(index):
            response = client.post(f'/api/practices/{identifier}/segments', headers=headers,
                data={'kind':'speech' if index == 0 else 'answer', 'index':index},
                files={'file':('fixture.wav', raw.getvalue(), 'audio/wav')})
            assert response.status_code == 200, response.text
            assert client.get(response.json()['media_url'], headers={'Range':'bytes=0-31'}).status_code == 206

        def finish(kind):
            response = client.post(f'/api/practices/{identifier}/jobs', headers=headers, json={'kind':kind})
            assert response.status_code == 200, response.text
            job = response.json()['id']
            for _ in range(100):
                value = client.get('/api/jobs/' + job).json()
                if value['status'] in ('succeeded', 'failed'):
                    assert value['status'] == 'succeeded', value
                    return value
                time.sleep(.02)
            raise AssertionError('Worker did not finish')

        upload(0)
        assert len(finish('questions')['result']['questions']) == 3
        for index in range(1, 4):
            upload(index)
        assert finish('report')['result']['demo'] is False
        current = client.get('/api/practices/' + identifier).json()
        assert current['status'] == 'ready' and len(current['segments']) == 4
        assert all(segment['transcript'] for segment in current['segments'])
        assert client.post('/api/practices/' + identifier + '/feedback', headers=headers, json={'rating':5, 'text':'Fixture feedback'}).status_code == 200
        assert client.patch('/api/auth/me', headers=headers, json={'onboarding_completed':True}).json()['user']['onboarding_completed']
        cookies = dict(client.cookies)
    with TestClient(create_app(tmp_path)) as restarted:
        restarted.cookies.update(cookies)
        assert restarted.get('/api/auth/me').json()['user']['onboarding_completed']
        assert restarted.get('/api/practices/' + identifier).json()['report'] == report
        assert restarted.get('/api/practices').json()['total'] == 1
