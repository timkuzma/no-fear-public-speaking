"""Loopback-only UI acceptance fixture; synthetic accounts/media, no real AI calls.

Run: .venv/bin/python tests/browser_flow_server.py
All data is temporary and removed on shutdown. Fault endpoints are test-only.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def create_fixture(directory):
    os.environ.update(APP_ENV='development', APP_ORIGIN='http://localhost:8094',
                      DATA_DIR=directory, LLM_API_KEY='synthetic-fixture-only',
                      LLM_BASE_URL='https://provider.invalid/v1')
    os.environ.pop('REQUIRE_INVITE', None)
    from fastapi.responses import JSONResponse
    from server import ai
    from server.app import create_app

    text = ('Мой проект помогает студентам готовиться к защите. '
            'Студент записывает выступление и получает вопросы по содержанию. '
            'Например, он объясняет решение задачи и проверяет, понятны ли аргументы.')
    usage = {'model': 'fixture', 'operation': 'fixture', 'input_tokens': 10,
             'output_tokens': 5, 'audio_seconds': 1, 'latency_ms': 1, 'attempts': []}

    async def transcribe(*args, **kwargs):
        return {'text': text, 'duration_seconds': 1, 'usage': usage}

    async def questions(*args, **kwargs):
        return {'questions': ['Как проект помогает студенту подготовиться к защите?',
                              'Какой пример объясняет решение задачи?',
                              'Как студент проверяет свои аргументы?'], 'usage': usage}

    async def analyze(*args, **kwargs):
        return {'report': {'demo': False, 'insight': 'Подкрепи главную мысль конкретным примером',
                'metrics': [{'title': 'Структура', 'text': 'Идея и пример сохранены в расшифровке', 'label': 'По тексту'}],
                'strengths': [{'title': 'Понятная задача', 'text': 'Ты объясняешь, кому помогает проект',
                               'evidence': 'Мой проект помогает студентам готовиться к защите.'}],
                'recommendations': [{'title': 'Раскрой пример', 'text': 'Опиши одну задачу студента и результат подготовки',
                                    'evidence': 'Например, он объясняет решение задачи и проверяет, понятны ли аргументы.'}],
                'criteria': [], 'limitations': ['Тестовый провайдер: проверяется путь пользователя, а не качество AI'],
                'transcript': text}, 'usage': usage}

    ai.transcribe, ai.generate_questions, ai.analyze = transcribe, questions, analyze
    app = create_app()
    faults = {'fail': False, 'lose': False}

    @app.middleware('http')
    async def fault(request, call_next):
        upload = request.method == 'POST' and request.url.path.endswith('/segments')
        if upload and faults['fail']:
            faults['fail'] = False
            return JSONResponse({'error': {'code': 'TEST_NETWORK', 'message': 'Тестовый обрыв загрузки'}}, status_code=503)
        response = await call_next(request)
        if upload and faults['lose'] and response.status_code == 200:
            faults['lose'] = False
            return JSONResponse({'error': {'code': 'TEST_LOST_RESPONSE', 'message': 'Тестовая потеря ответа после сохранения'}}, status_code=502)
        return response

    @app.post('/__test__/fail')
    async def fail():
        faults['fail'] = True
        return {'ok': True}

    @app.post('/__test__/lose')
    async def lose():
        faults['lose'] = True
        return {'ok': True}

    @app.post('/__test__/expire')
    async def expire():
        app.state.store.execute('UPDATE sessions SET expires=0')
        return {'ok': True}

    # Test routes must precede the maintained application's catch-all static mount.
    static_route = next(r for r in app.router.routes if getattr(r, 'name', '') == 'public')
    app.router.routes.remove(static_route)
    app.router.routes.append(static_route)
    return app


if __name__ == '__main__':
    import uvicorn
    with tempfile.TemporaryDirectory(prefix='nfs-browser-flow-') as directory:
        uvicorn.run(create_fixture(directory), host='127.0.0.1', port=8094, access_log=False)
