"""Actual provider smoke using an explicitly synthetic local recording."""
import argparse
import json
import os
import time
from pathlib import Path

import httpx


def run(options):
    if not options.base_url.startswith(('http://localhost:', 'http://127.0.0.1:')):
        raise ValueError('This fixture script is restricted to local test environments')
    with httpx.Client(base_url=options.base_url, timeout=120) as client:
        response = client.post('/api/auth/register', json={'email':options.email, 'name':'Проверка пилота',
            'password':os.environ['SMOKE_PASSWORD'], 'role':'other', 'consent':True})
        if response.status_code == 409:
            response = client.post('/api/auth/login', json={'email':options.email, 'password':os.environ['SMOKE_PASSWORD']})
        response.raise_for_status()
        client.headers['X-CSRF-Token'] = response.json()['csrf_token']
        config = {'scenario':'defense' if options.questions else 'speech', 'topic':'Подготовка к защите проекта',
                  'duration':1, 'questions':options.questions, 'criteria':'Ясно назвать предложение и привести конкретный пример.'}
        response = client.get('/api/practices/' + options.practice_id) if options.practice_id else client.post('/api/practices', json=config)
        response.raise_for_status()
        practice_id = response.json()['id']

        def upload(file, kind, index):
            with file.open('rb') as source:
                response = client.post('/api/practices/' + practice_id + '/segments',
                    files={'file':(file.name, source, 'audio/wav')}, data={'kind':kind, 'index':index})
            response.raise_for_status()
            return response.json()

        def job(kind):
            response = client.post('/api/practices/' + practice_id + '/jobs', json={'kind':kind})
            response.raise_for_status()
            identifier = response.json()['id']
            began = time.monotonic()
            while time.monotonic() - began < 300:
                response = client.get('/api/jobs/' + identifier)
                response.raise_for_status()
                value = response.json()
                if value['status'] in ('succeeded', 'failed'):
                    return value, round(time.monotonic() - began, 3)
                time.sleep(2)
            raise TimeoutError('Job still pending/running after 300 seconds; inspect saved practice before retry')

        existing = response.json().get('segments', [])
        speech = next((segment for segment in existing if segment['index'] == 0), None) or upload(options.audio, 'speech', 0)
        results = {'synthetic':True, 'practice_id':practice_id, 'speech_seconds':speech['duration_seconds'], 'questions_enabled':options.questions}
        if options.questions:
            questions, duration = job('questions')
            results['questions_job'] = {'status':questions['status'], 'elapsed_seconds':duration, 'error':questions['error']}
            if questions['status'] == 'succeeded':
                results['questions_count'] = len(questions['result']['questions'])
                for index in range(1, 4):
                    if not any(segment['index'] == index for segment in existing):
                        upload(options.answer or options.audio, 'answer', index)
            else:
                options.output.parent.mkdir(parents=True, exist_ok=True)
                options.output.write_text(json.dumps(results, ensure_ascii=False, indent=2))
                raise SystemExit('Synthetic questions smoke failed; inspect the saved job error before retry')
        report, duration = job('report')
        results['report_job'] = {'status':report['status'], 'elapsed_seconds':duration, 'error':report['error']}
        if report['status'] == 'succeeded':
            result = report['result']
            results.update({'transcript_characters':len(result['transcript']), 'strengths':len(result['strengths']),
                            'recommendations':len(result['recommendations']), 'metrics':result['metrics'], 'demo':result['demo']})
        current = client.get('/api/practices/' + practice_id)
        current.raise_for_status()
        results['saved_status'] = current.json()['status']
        results['saved_segments'] = len(current.json()['segments'])
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(results, ensure_ascii=False), flush=True)
        if report['status'] != 'succeeded':
            raise SystemExit('Synthetic report smoke failed; inspect the saved job error before retry')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://localhost:8080')
    parser.add_argument('--email', default='qa-pilot@example.test')
    parser.add_argument('--audio', type=Path, required=True)
    parser.add_argument('--answer', type=Path)
    parser.add_argument('--practice-id', help='Resume an explicitly synthetic existing fixture; do not recreate segments')
    parser.add_argument('--questions', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('outputs/ai-smoke-report.json'))
    run(parser.parse_args())
