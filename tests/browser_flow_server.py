"""Loopback-only UI acceptance fixture; synthetic accounts/media, no real AI calls.

Run: .venv/bin/python tests/browser_flow_server.py
All data is temporary and removed on shutdown. Fault endpoints are test-only.
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def create_fixture(directory, origin='http://localhost:8094'):
    os.environ.update(APP_ENV='development', APP_ORIGIN=origin,
                      DATA_DIR=directory, LLM_API_KEY='synthetic-fixture-only',
                      LLM_BASE_URL='https://provider.invalid/v1')
    os.environ.pop('REQUIRE_INVITE', None)
    from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
    from server import ai
    from server.app import create_app

    text = ('Мой проект помогает студентам готовиться к защите. '
            'Студент записывает выступление и получает вопросы по содержанию. '
            'Например, он объясняет решение задачи и проверяет, понятны ли аргументы.')
    usage = {'model': 'fixture', 'operation': 'fixture', 'input_tokens': 10,
             'output_tokens': 5, 'audio_seconds': 1, 'latency_ms': 1, 'attempts': []}

    async def transcribe(*args, **kwargs):
        return {'text': text, 'duration_seconds': 1, 'usage': usage}

    async def questions(config, transcript, **kwargs):
        texts = ['Как проект помогает студенту подготовиться к защите?',
                 'Какой пример объясняет решение задачи?',
                 'Как студент проверяет свои аргументы?']
        candidates = ai._quote_candidates([{'index': 0, 'kind': 'speech', 'text': transcript}])
        items = []
        for index, question in enumerate(texts):
            quote = candidates[min(index, len(candidates) - 1)]
            items.append({'text': question, 'evidence': quote['text'], 'evidence_id': quote['id'],
                          **{key: quote[key] for key in ('segment_index', 'origin', 'transcript_revision', 'start_char', 'end_char')}})
        return {'questions': texts, 'usage': usage,
                'provenance': {'context_schema_version': ai.feedback_prompts.CONTEXT_VERSION,
                               'prompt_version': ai.feedback_prompts.QUESTIONS_VERSION,
                               'transcript_revision': ai.build_context('questions', config, [{'index': 0, 'kind': 'speech', 'text': transcript}])['transcript_revision'],
                               'chat_model': 'fixture', 'items': items}}

    faults = {'fail': False, 'lose': False, 'report': 'normal', 'upload_delay': 0, 'report_delay': 0}

    async def analyze(config, segments, **kwargs):
        if faults['report_delay']:
            await asyncio.sleep(faults['report_delay'])
        # Synthetic contract fixtures: these test UI states, not coaching quality.
        candidates = ai._quote_candidates(segments)
        first = candidates[0]
        provenance = lambda q: {'evidence': q['text'], 'evidence_id': q['id'],
                                'segment_index': q['segment_index'], 'origin': q['origin'],
                                'transcript_revision': q['transcript_revision'],
                                'start_char': q['start_char'], 'end_char': q['end_char']}
        recommendations = [{'title': 'Уточни связь идеи и применения',
                            'observation': 'Ты называешь, кому помогает проект.',
                            'action': 'Повтори эту мысль в одной фразе, сохранив смысл.',
                            'example': None, **provenance(first)}]
        answer = next((q for q in candidates if q['origin'] == 'answer'), None)
        if answer:
            recommendations.append({'title': 'Сделай ответ короче',
                                    'observation': 'В ответе есть самостоятельная мысль.',
                                    'action': 'Повтори эту мысль отдельно от остальных деталей.',
                                    'example': None, **provenance(answer)})
        for item in recommendations:
            item['text'] = f"{item['observation']} {item['action']}"
        report = {'schema_version': 2, 'demo': False,
                  'primary_recommendation_index': len(recommendations) - 1,
                  'insight': recommendations[-1]['action'],
                  'metrics': [{'title': 'Объём расшифровки', 'text': 'Тестовые данные', 'label': 'По распознанному тексту'}],
                  'strengths': [{'title': 'Назван адресат', 'observation': 'В этой фразе назван студент.',
                                 'text': 'В этой фразе назван студент.', **provenance(first)}],
                  'recommendations': recommendations,
                  'criteria': [],
                  'provenance': {'publisher_policy': 'withhold_unreviewed_rewrites-v1',
                                 'report_prompt_version': ai.feedback_prompts.REPORT_VERSION},
                  'limitations': ['Тестовый провайдер: проверяется путь пользователя, а не качество AI'],
                  'transcript': '\n\n'.join(s['text'] for s in segments),
                  'transcript_segments': [{**s, 'origin': 'speech' if s['index'] == 0 else 'answer',
                                           'transcript_revision': ai.transcript_revision(s['text'])} for s in segments]}
        if faults['report'] == 'sparse':
            report.update(strengths=[], recommendations=[], primary_recommendation_index=None, insight=None)
        if faults['report'] == 'unknown' or config.get('criteria'):
            report['criteria'] = [{'criterion': config.get('criteria') or 'Жесты', 'status': 'unknown',
                                   'basis': 'unknown', 'reason': 'В разборе доступна только расшифровка.',
                                   'evidence': ''}]
        if faults['report'] == 'legacy':
            report.pop('schema_version')
            report.pop('primary_recommendation_index')
            report.pop('transcript_segments')
            report.pop('provenance')
            report['insight'] = 'Сохранённый главный вывод старого отчёта'
            report['recommendations'][0]['example'] = first['text']
        return {'report': report, 'usage': usage}

    ai.transcribe, ai.generate_questions, ai.analyze = transcribe, questions, analyze
    app = create_app()

    @app.get('/__test__/meeting')
    async def synthetic_meeting():
        # Native MediaRecorder/AudioWorklet with generated media; never opens
        # physical devices or changes the maintained production entry point.
        html = (Path(__file__).resolve().parent.parent / 'public/index.html').read_text()
        html = html.replace('<script type="module" src="/app.js',
                            '<script type="module" src="/__test__/synthetic-media.js"></script>\n'
                            '    <script type="module" src="/app.js')
        return HTMLResponse(html)

    @app.get('/__test__/synthetic-media.js')
    async def synthetic_media():
        return FileResponse(Path(__file__).with_name('synthetic-media.js'),
                            media_type='text/javascript')

    @app.middleware('http')
    async def fault(request, call_next):
        upload = request.method == 'POST' and request.url.path.endswith('/segments')
        if upload and faults['upload_delay']:
            await asyncio.sleep(faults['upload_delay'])
        if upload and faults['fail']:
            faults['fail'] = False
            return JSONResponse({'error': {'code': 'TEST_NETWORK', 'message': 'Тестовый обрыв загрузки'}}, status_code=503)
        response = await call_next(request)
        if upload and faults['lose'] and response.status_code == 200:
            faults['lose'] = False
            return JSONResponse({'error': {'code': 'TEST_LOST_RESPONSE', 'message': 'Тестовая потеря ответа после сохранения'}}, status_code=502)
        return response

    @app.post('/__test__/report-kind/{kind}')
    async def report_kind(kind: str):
        if kind not in {'normal', 'sparse', 'unknown', 'legacy'}:
            return JSONResponse({'error': 'Unknown synthetic report state'}, status_code=400)
        faults['report'] = kind
        return {'ok': True}

    @app.post('/__test__/report-delay/{seconds}')
    async def report_delay(seconds: int):
        if not 0 <= seconds <= 15:
            return JSONResponse({'error': 'Invalid delay'}, status_code=400)
        faults['report_delay'] = seconds
        return {'ok': True}

    @app.post('/__test__/upload-delay/{seconds}')
    async def upload_delay(seconds: int):
        if not 0 <= seconds <= 15:
            return JSONResponse({'error': 'Invalid delay'}, status_code=400)
        faults['upload_delay'] = seconds
        return {'ok': True}

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
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8094)
    parser.add_argument('--origin', default='http://localhost:8094')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='nfs-browser-flow-') as directory:
        uvicorn.run(create_fixture(directory, args.origin), host='127.0.0.1', port=args.port, access_log=False)
