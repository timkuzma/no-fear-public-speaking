"""Durable serialized queue; successful transcription survives a failed report."""
import asyncio
import json
import logging
from .store import now

log = logging.getLogger('pilot.jobs')


async def process(store, job):
    from . import ai
    practice_id = job['practice_id']
    try:
        segments = store.all('SELECT * FROM segments WHERE practice_id=? ORDER BY segment_index', (practice_id,))
        selected = [s for s in segments if s['kind'] == 'speech'] if job['kind'] == 'questions' else segments
        prepared = []
        for segment in selected:
            text = segment['transcript']
            if text is None:
                store.execute('UPDATE jobs SET stage=? WHERE id=?', ('transcription_' + str(segment['segment_index']), job['id']))
                result = await ai.transcribe(store.media / segment['filename'])
                text = result['text']
                with store.connect() as db:
                    db.execute('UPDATE segments SET transcript=? WHERE id=?', (text, segment['id']))
                    db.execute('INSERT INTO usage VALUES(?,?,?,?,?)', (__import__('uuid').uuid4().hex, job['id'], job['user_id'], now(), json.dumps(result['usage'])))
            prepared.append({'kind': segment['kind'], 'index': segment['segment_index'], 'text': text, 'duration_seconds': segment['duration']})
        config = json.loads(job['config'])
        store.execute('UPDATE jobs SET stage=? WHERE id=?', (job['kind'], job['id']))
        if job['kind'] == 'questions':
            response = await ai.generate_questions(config, prepared[0]['text'])
            result = {'questions': response['questions']}
        else:
            response = await ai.analyze(config, prepared)
            result = response['report']
        with store.connect() as db:
            db.execute('INSERT INTO usage VALUES(?,?,?,?,?)', (__import__('uuid').uuid4().hex, job['id'], job['user_id'], now(), json.dumps(response['usage'])))
            if job['kind'] == 'questions':
                db.execute("UPDATE practices SET questions=?,status='draft' WHERE id=?", (json.dumps(result['questions'], ensure_ascii=False), practice_id))
            else:
                db.execute("UPDATE practices SET report=?,status='ready' WHERE id=?", (json.dumps(result, ensure_ascii=False), practice_id))
            db.execute("UPDATE jobs SET status='succeeded',stage='complete',result=?,finished=? WHERE id=?", (json.dumps(result, ensure_ascii=False), now(), job['id']))
        store.event('questions_ready' if job['kind'] == 'questions' else 'report_ready', job['user_id'], practice_id)
    except asyncio.CancelledError:
        # Leave running row for startup recovery. Never report cancellation as success.
        raise
    except Exception as exc:
        if isinstance(exc, ai.ProviderError) and getattr(exc, 'usage', None):
            store.usage(job, exc.usage)
        error = {'code': exc.code, 'message': exc.message} if isinstance(exc, ai.ProviderError) else {'code': 'PROCESSING_FAILED', 'message': 'Не удалось обработать запись. Она сохранена: попробуйте ещё раз.'}
        with store.connect() as db:
            db.execute("UPDATE jobs SET status='failed',error=?,finished=? WHERE id=?", (json.dumps(error, ensure_ascii=False), now(), job['id']))
            db.execute("UPDATE practices SET status='failed' WHERE id=?", (practice_id,))
        store.event('service_failure', job['user_id'], practice_id, {'code': error['code'], 'job_id': job['id']})
        log.warning('job_failed id=%s code=%s', job['id'], error['code'])


async def run(store):
    store.recover_jobs()
    while True:
        job = store.claim_job()
        if job:
            await process(store, job)
        else:
            await asyncio.sleep(0.5)
