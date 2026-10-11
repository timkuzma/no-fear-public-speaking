"""Bounded actual-HTTP API load on a disposable local database; no LLM calls."""
import argparse
import asyncio
import json
import os
import platform
import resource
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx


def percentile(samples, percent):
    values = sorted(samples)
    return round(values[min(len(values) - 1, int((len(values) - 1) * percent))], 2) if values else None


async def phase(client, urls, rps, seconds):
    began = time.monotonic()
    latency, status = [], []

    async def one(number):
        started = time.monotonic()
        try:
            response = await client.get(urls[number % len(urls)])
            status.append(response.status_code)
        except httpx.HTTPError:
            status.append(0)
        latency.append((time.monotonic() - started) * 1000)

    tasks = []
    for number in range(int(rps * seconds)):
        delay = began + number / rps - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        tasks.append(asyncio.create_task(one(number)))
    await asyncio.gather(*tasks)
    elapsed = time.monotonic() - began
    return {'target_rps': rps, 'scheduled_seconds': seconds, 'requests': len(status),
            'elapsed_seconds': round(elapsed, 3), 'achieved_rps': round(len(status) / elapsed, 2),
            'errors': sum(code != 200 for code in status),
            'status_counts': {str(code): status.count(code) for code in sorted(set(status))},
            'p50_ms': percentile(latency, .5), 'p95_ms': percentile(latency, .95), 'p99_ms': percentile(latency, .99)}


async def main(args):
    root = Path(__file__).resolve().parent.parent
    with socket.socket() as reserve:
        reserve.bind(('127.0.0.1', 0))
        port = reserve.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='stage-load-') as directory:
        env = {**os.environ, 'DATA_DIR': directory, 'APP_ENV': 'development',
               'APP_ORIGIN': f'http://127.0.0.1:{port}', 'REQUIRE_INVITE': '0'}
        env.pop('LLM_API_KEY', None)
        env.pop('OPERATOR_TOKEN', None)
        process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'server.app:app', '--host', '127.0.0.1',
                                    '--port', str(port), '--workers', '1', '--no-access-log', '--log-level', 'warning'],
                                   cwd=root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            async with httpx.AsyncClient(base_url=env['APP_ORIGIN'], timeout=15,
                                         limits=httpx.Limits(max_connections=100, max_keepalive_connections=100)) as client:
                for _ in range(100):
                    try:
                        if (await client.get('/api/health')).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(.1)
                else:
                    raise RuntimeError('Disposable server did not start')
                account = await client.post('/api/auth/register', json={'email':'load@example.test', 'name':'Load fixture',
                                          'password':secrets.token_urlsafe(24), 'role':'other', 'consent':True})
                account.raise_for_status()
                client.headers['X-CSRF-Token'] = account.json()['csrf_token']
                practice = await client.post('/api/practices', json={'scenario':'speech', 'topic':'Load fixture',
                                              'duration':1, 'questions':False, 'criteria':''})
                practice.raise_for_status()
                urls = ['/api/auth/me', '/api/practices', '/api/practices/' + practice.json()['id'], '/api/health']
                results = []
                for rps in [1, 5, 10, 20, 40]:
                    result = await phase(client, urls, rps, args.seconds if rps <= 10 else args.stress_seconds)
                    results.append(result)
                    print(json.dumps(result), flush=True)
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        report = {'timestamp_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                  'environment': {'platform':platform.platform(), 'python':platform.python_version(),
                                  'server_workers':1, 'peak_child_rss_mb':round(peak / (1024**2 if sys.platform == 'darwin' else 1024), 2)},
                  'profile':'Equal mix: authenticated me, owned history, owned practice, health. Actual HTTP. Every API request persists a request metric. Disposable SQLite. No uploads or AI processing.',
                  'provider_calls':0, 'provider_tpm':None, 'provider_tps':None, 'phases':results}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=20)
    parser.add_argument('--stress-seconds', type=int, default=10)
    parser.add_argument('--output', type=Path, default=Path('outputs/load-report.json'))
    options = parser.parse_args()
    if not 1 <= options.seconds <= 60 or not 1 <= options.stress_seconds <= 30:
        parser.error('Bounded test only: seconds 1–60, stress-seconds 1–30')
    asyncio.run(main(options))
