"""Private, serialized incremental ASR; partial transcripts never replace full speech."""
import asyncio
import json
import re
import struct
import wave


def has_audio_activity(path):
    """Exclude negligible PCM slivers; this gate is not proof of spoken words."""
    with wave.open(str(path), 'rb') as audio:
        if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 16000) or audio.getnframes() > 257600:
            raise ValueError('Invalid private PCM chunk')
        frames = audio.readframes(audio.getnframes())
    active = 0
    for (sample,) in struct.iter_unpack('<h', frames):
        if abs(sample) > 8:
            active += 1
            if active >= 1600:  # 100ms cumulative activity at the validated 16kHz rate
                return True
    return False


async def process_chunk(store, chunk):
    from . import ai
    path = store.media / chunk['filename']
    try:
        if not has_audio_activity(path):
            store.execute("UPDATE live_chunks SET status='succeeded',transcript='',error=NULL WHERE id=? AND EXISTS(SELECT 1 FROM live_sessions s WHERE s.practice_id=live_chunks.practice_id AND s.session_id=live_chunks.session_id AND s.status IN ('open','bound'))", (chunk['id'],))
            return
        response = await ai.transcribe(path)
        # Keep provider accounting even if a session was replaced during the call.
        store.usage(chunk, response['usage'])
        store.execute("UPDATE live_chunks SET status='succeeded',transcript=?,error=NULL WHERE id=? AND EXISTS(SELECT 1 FROM live_sessions s WHERE s.practice_id=live_chunks.practice_id AND s.session_id=live_chunks.session_id AND s.status IN ('open','bound'))", (response['text'], chunk['id']))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if isinstance(exc, ai.ProviderError) and getattr(exc, 'usage', None):
            store.usage(chunk, exc.usage)
        if isinstance(exc, ai.ProviderError) and exc.code == 'NO_SPEECH':
            # A quiet interval is complete audio coverage, with no words to add.
            # An entirely empty session still falls back to whole-recording ASR.
            store.execute("UPDATE live_chunks SET status='succeeded',transcript='',error=NULL WHERE id=? AND EXISTS(SELECT 1 FROM live_sessions s WHERE s.practice_id=live_chunks.practice_id AND s.session_id=live_chunks.session_id AND s.status IN ('open','bound'))", (chunk['id'],))
            return
        error = {'code': exc.code, 'message': exc.message} if isinstance(exc, ai.ProviderError) else {'code': 'LIVE_TRANSCRIPTION_FAILED', 'message': 'Промежуточная расшифровка недоступна. Запись будет обработана после выступления.'}
        store.execute("UPDATE live_chunks SET status='failed',error=? WHERE id=? AND status='running'", (json.dumps(error, ensure_ascii=False), chunk['id']))
        store.event('service_failure', chunk['user_id'], chunk['practice_id'], {'code': error['code'], 'operation': 'live_transcription'})
    finally:
        # No upload endpoint can reuse a replaced session. Remove only its own file.
        row = store.one('SELECT c.status,s.status AS session_status FROM live_chunks c JOIN live_sessions s ON s.practice_id=c.practice_id AND s.session_id=c.session_id WHERE c.id=?', (chunk['id'],))
        if not row or row['session_status'] == 'obsolete':
            path.unlink(missing_ok=True)
            store.execute("UPDATE live_chunks SET status='cancelled' WHERE id=? AND status='running'", (chunk['id'],))


async def run(store):
    store.recover_live_chunks()
    while True:
        chunk = store.claim_live_chunk()
        if chunk:
            await process_chunk(store, chunk)
        else:
            await asyncio.sleep(0.5)


def snapshot(store, practice_id, session_id):
    session = store.one('SELECT * FROM live_sessions WHERE practice_id=? AND session_id=?', (practice_id, session_id))
    if not session:
        return {'session_id': session_id, 'status': 'waiting', 'completed_chunks': 0, 'recognized_words': 0, 'transcript': ''}
    chunks = store.all('SELECT * FROM live_chunks WHERE practice_id=? AND session_id=? ORDER BY chunk_index', (practice_id, session_id))
    # Show only the contiguous successful prefix, never reorder delayed fragments.
    prefix = []
    for index, chunk in enumerate(chunks):
        if chunk['chunk_index'] != index or chunk['status'] != 'succeeded':
            break
        prefix.append(chunk['transcript'] or '')
    text = ' '.join(text for text in prefix if text).strip()
    failed = next((chunk for chunk in chunks if chunk['status'] == 'failed'), None)
    status = 'obsolete' if session['status'] == 'obsolete' else 'failed' if failed else 'processing' if any(chunk['status'] in ('pending', 'running') for chunk in chunks) else 'ready'
    result = {'session_id': session_id, 'status': status, 'completed_chunks': len(prefix), 'recognized_words': len(re.findall(r'[^\W_]+', text, re.UNICODE)), 'transcript': text}
    if failed:
        result['error'] = json.loads(failed['error'])
    return result


def completed_transcript(store, segment):
    session = store.one("SELECT * FROM live_sessions WHERE segment_id=? AND status='bound'", (segment['id'],))
    if not session:
        return None
    chunks = store.all('SELECT * FROM live_chunks WHERE practice_id=? AND session_id=? ORDER BY chunk_index', (segment['practice_id'], session['session_id']))
    end = 0.0
    if not chunks or session['expected_chunks'] != len(chunks):
        return None
    for index, chunk in enumerate(chunks):
        if chunk['chunk_index'] != index or chunk['status'] != 'succeeded' or abs(chunk['offset_seconds'] - end) > 0.05:
            return None
        end += chunk['duration']
    if abs(end - segment['duration']) > 0.75:
        return None
    text = ' '.join(chunk['transcript'] for chunk in chunks if chunk['transcript']).strip()
    # Empty recognition is not successful speech; allow full ASR to diagnose it.
    return text or None


async def reusable_transcript(store, segment, wait_seconds=20):
    session = store.one("SELECT session_id FROM live_sessions WHERE segment_id=? AND status='bound'", (segment['id'],))
    if not session:
        return None
    deadline = asyncio.get_running_loop().time() + wait_seconds
    while True:
        cached = completed_transcript(store, segment)
        if cached is not None:
            return cached
        pending = store.one("SELECT id FROM live_chunks WHERE practice_id=? AND session_id=? AND status IN ('pending','running') LIMIT 1", (segment['practice_id'], session['session_id']))
        if not pending or asyncio.get_running_loop().time() >= deadline:
            return None
        await asyncio.sleep(0.25)
