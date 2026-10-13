"""Durable serialized queue; successful transcription survives a failed report."""
import asyncio
import json
import logging
from .store import now
from . import limits, monitoring

log = logging.getLogger('pilot.jobs')


async def process(store, job):
    try:
        with limits.provider_scope(store, job['user_id'], job['id']):
            async with asyncio.timeout(limits.setting('JOB_TIMEOUT_SECONDS')):
                await _process(store, job)
    except TimeoutError:
        error = {'code': 'PROCESSING_TIMEOUT', 'message': 'Разбор занял слишком много времени. Запись сохранена; попробуйте ещё раз.'}
        with store.connect() as db:
            db.execute("UPDATE jobs SET status='failed',error=?,finished=? WHERE id=?", (json.dumps(error, ensure_ascii=False), now(), job['id']))
            db.execute("UPDATE practices SET status='failed' WHERE id=?", (job['practice_id'],))
        store.event('service_failure', job['user_id'], job['practice_id'], {'code': error['code']})


async def _process(store, job):
    from . import ai
    practice_id = job['practice_id']
    try:
        segments = store.all('SELECT * FROM segments WHERE practice_id=? ORDER BY segment_index', (practice_id,))
        selected = [s for s in segments if s['kind'] == 'speech'] if job['kind'] == 'questions' else segments
        questions = []
        if job['kind'] == 'report':
            practice = store.one('SELECT questions FROM practices WHERE id=?', (practice_id,))
            questions = json.loads(practice['questions'])
        prepared = []
        for segment in selected:
            text = segment['transcript']
            if text is None:
                store.execute('UPDATE jobs SET stage=? WHERE id=?', ('transcription_' + str(segment['segment_index']), job['id']))
                from .live import reusable_transcript
                text = await reusable_transcript(store, segment) if segment['kind'] == 'speech' else None
                result = None
                if text is None:
                    result = await ai.transcribe(store.media / segment['filename'])
                    text = result['text']
                with store.connect() as db:
                    db.execute('UPDATE segments SET transcript=? WHERE id=?', (text, segment['id']))
                    if result:
                        db.execute('INSERT INTO usage VALUES(?,?,?,?,?)', (__import__('uuid').uuid4().hex, job['id'], job['user_id'], now(), json.dumps(result['usage'])))
            item = {'kind': segment['kind'], 'index': segment['segment_index'], 'text': text, 'duration_seconds': segment['duration']}
            if segment['kind'] == 'answer':
                index = segment['segment_index']
                if not isinstance(questions, list) or not 1 <= index <= len(questions):
                    raise ai.ProviderError('AI_INPUT_INVALID', 'Не удалось связать ответ с вопросом. Запись сохранена; повторите разбор.')
                item['question'] = questions[index - 1]
            prepared.append(item)
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
        if monitoring.maintenance(store) is not None or not limits.enabled(store):
            await asyncio.sleep(0.5)
            continue
        job = store.claim_job()
        if job:
            await process(store, job)
        else:
            await asyncio.sleep(0.5)
