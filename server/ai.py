"""Bounded, evidence-checked transcription and analysis for the single-host pilot."""

import asyncio
import hashlib
import json
import math
import os
import re
import shutil
import struct
import tempfile
import time
import wave
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from . import limits, feedback_prompts, wording_prompts


MAX_DURATION = 600
MAX_TEXT = 60000
MAX_MEDIA_BYTES = 100 * 1024 * 1024
PROMPT_VERSION = feedback_prompts.REPORT_VERSION


class ProviderError(Exception):
    """Only safe codes and user-facing messages cross the API boundary."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def _setting_number(name, default, minimum, maximum):
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def _provider():
    base = os.getenv("LLM_BASE_URL", "https://shared1.multitool.works:4000/v1").rstrip("/")
    key = os.getenv("LLM_API_KEY", "")
    if not key or not base.startswith(("https://", "http://")):
        raise ProviderError("AI_NOT_CONFIGURED", "Сервис разбора ещё не подключён. Запись сохранена; попробуйте позже.")
    try:
        parsed = urlsplit(base)
    except ValueError:
        raise ProviderError('AI_NOT_CONFIGURED', 'Настройки сервиса разбора недоступны. Запись сохранена.') from None
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or (os.getenv('APP_ENV') == 'production' and parsed.scheme != 'https'):
        raise ProviderError('AI_NOT_CONFIGURED', 'Настройки сервиса разбора недоступны. Запись сохранена.')
    return base, key


def _tokens(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _usage(model, operation, attempts, audio_seconds=0):
    def total(field):
        values = [attempt[field] for attempt in attempts]
        return sum(values) if all(value is not None for value in values) else None

    return {
        "model": model,
        "operation": operation,
        "input_tokens": total("input_tokens"),
        "output_tokens": total("output_tokens"),
        "audio_seconds": audio_seconds,
        "latency_ms": sum(attempt["latency_ms"] for attempt in attempts),
        "attempts": attempts,
        "prompt_version": wording_prompts.VERSION if operation.endswith('_wording') else feedback_prompts.QUESTIONS_VERSION if operation == "questions" else
                          feedback_prompts.REPORT_VERSION if operation == "report" else "asr-v1",
    }


def _failed_response(message, usage):
    error = ProviderError("AI_INVALID_RESPONSE", message)
    error.usage = usage
    return error


def _invalid_model(response):
    if response is None or response.status_code not in (400, 404):
        return False
    try:
        body = response.json()
        error = body.get("error", {}) if isinstance(body, dict) else {}
        if not isinstance(error, dict):
            return False
        code = str(error.get("code", "")).lower()
        message = str(error.get("message", "")).lower()
        return code in ("invalid_model", "model_not_found", "unknown_model") or "invalid model name" in message
    except (ValueError, UnicodeError, RecursionError):
        return False


async def _request(endpoint, model, operation, *, payload=None, audio=None, audio_seconds=0):
    base, key = _provider()
    attempts = []
    retry_count = int(_setting_number("LLM_MAX_ATTEMPTS", 2, 1, 3))
    timeout = _setting_number("LLM_TIMEOUT_SECONDS", 120, 5, 180)
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10), follow_redirects=False) as client:
        for number in range(retry_count):
            try:
                reservation = limits.reserve_attempt(operation, audio_seconds, sum(len(m.get('content', '')) for m in (payload or {}).get('messages', [])), (payload or {}).get('max_tokens', 0))
            except limits.LimitError as exc:
                error = ProviderError(exc.code, exc.message)
                if attempts:
                    error.usage = _usage(model, operation, attempts, audio_seconds)
                raise error from None
            start = time.monotonic()
            status = None
            response = None
            oversized = False
            try:
                arguments = {"headers": {"Authorization": "Bearer " + key}}
                if audio is not None:
                    arguments.update(data={"model": model, "language": "ru", "response_format": "json"},
                                     files={"file": ("speech.wav", audio, "audio/wav")})
                else:
                    arguments["json"] = payload
                async with client.stream("POST", base + endpoint, **arguments) as incoming:
                    status = incoming.status_code
                    response_bytes = bytearray()
                    body_limit = 1024 * 1024 if 200 <= status < 300 else 4096 if status in (400, 404) else 0
                    if body_limit:
                        async for chunk in incoming.aiter_bytes():
                            if len(response_bytes) + len(chunk) > body_limit:
                                oversized = 200 <= status < 300
                                break
                            response_bytes.extend(chunk)
                    response = httpx.Response(status, content=bytes(response_bytes))
            except (httpx.TimeoutException, httpx.TransportError):
                # Neither response text nor exception details may contain safe user-facing data.
                status = None
                response = None
            attempt = {"status": status, "latency_ms": round((time.monotonic() - start) * 1000),
                       "input_tokens": None, "output_tokens": None}
            limits.finish_attempt(reservation, status, attempt['latency_ms'])
            attempts.append(attempt)
            if response is not None and 200 <= status < 300:
                if oversized:
                    raise _failed_response("Сервис разбора вернул слишком большой ответ. Попробуйте ещё раз.",
                                           _usage(model, operation, attempts, audio_seconds))
                try:
                    body = response.json()
                except (ValueError, UnicodeError, RecursionError):
                    raise _failed_response("Не удалось прочитать ответ сервиса разбора. Попробуйте ещё раз.",
                                           _usage(model, operation, attempts, audio_seconds)) from None
                if not isinstance(body, dict):
                    raise _failed_response("Сервис разбора вернул ответ в неподходящем формате. Попробуйте ещё раз.",
                                           _usage(model, operation, attempts, audio_seconds))
                counts = body.get("usage")
                if isinstance(counts, dict):
                    attempt["input_tokens"] = _tokens(counts.get("prompt_tokens", counts.get("input_tokens")))
                    attempt["output_tokens"] = _tokens(counts.get("completion_tokens", counts.get("output_tokens")))
                return body, _usage(model, operation, attempts, audio_seconds)
            transient = status is None or status == 429 or (status is not None and 500 <= status < 600)
            if transient and number + 1 < retry_count:
                await asyncio.sleep(0.5 * (number + 1))
                continue
            if _invalid_model(response):
                error = ProviderError("AI_MODEL_INVALID", "Выбранная модель недоступна. Запись сохранена; попросите организатора проверить настройки моделей.")
            elif status in (401, 403):
                error = ProviderError("AI_ACCESS_DENIED", "Сервис разбора временно недоступен. Запись сохранена; сообщите об ошибке организатору.")
            elif status == 429:
                error = ProviderError("AI_BUSY", "Сервис разбора занят. Запись сохранена; повторите попытку чуть позже.")
            else:
                error = ProviderError("AI_UNAVAILABLE", "Не удалось связаться с сервисом разбора. Запись сохранена; попробуйте ещё раз.")
            error.usage = _usage(model, operation, attempts, audio_seconds)
            raise error


def _ffmpeg():
    configured = os.getenv("FFMPEG_BINARY")
    if configured:
        return configured
    installed = shutil.which("ffmpeg")
    if installed:
        return installed
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        raise ProviderError("MEDIA_NOT_CONFIGURED", "Обработка записи временно недоступна. Сообщите организатору.") from None


async def _decode(path: Path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_MEDIA_BYTES:
        raise ProviderError("MEDIA_INVALID", "Не удалось прочитать запись: файл отсутствует или слишком большой.")
    with path.open("rb") as source:
        header = source.read(16)
    known_container = (header.startswith((b"\x1aE\xdf\xa3", b"OggS", b"ID3")) or
                       (header.startswith(b"RIFF") and header[8:12] == b"WAVE") or
                       header[4:8] == b"ftyp" or
                       (len(header) >= 2 and header[0] == 255 and header[1] & 224 == 224))
    if not known_container:
        raise ProviderError("MEDIA_INVALID", "Формат записи не поддерживается. Запишите речь в браузере ещё раз.")
    with tempfile.TemporaryDirectory(prefix="stage-audio-") as directory:
        target = Path(directory) / "audio.wav"
        try:
            process = await asyncio.create_subprocess_exec(
                _ffmpeg(), "-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe",
                "-format_whitelist", "matroska,webm,mov,mp4,m4a,3gp,3g2,mj2,wav,ogg,mp3",
                "-i", str(path.resolve()),
                "-map", "0:a:0", "-vn", "-t", str(MAX_DURATION + 1), "-ac", "1",
                "-ar", "16000", "-c:a", "pcm_s16le", "-y", str(target),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                await asyncio.wait_for(process.wait(), timeout=45)
            except asyncio.TimeoutError:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
                raise ProviderError("MEDIA_INVALID", "Не удалось обработать запись. Попробуйте записать речь ещё раз.") from None
            except asyncio.CancelledError:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
                raise
            if process.returncode != 0:
                raise ProviderError("MEDIA_INVALID", "В файле не найдена доступная звуковая дорожка. Запишите речь ещё раз.")
            with wave.open(str(target), "rb") as decoded:
                duration = decoded.getnframes() / decoded.getframerate()
                frames = decoded.readframes(decoded.getnframes())
            if duration > MAX_DURATION:
                raise ProviderError("MEDIA_TOO_LONG", "Запись длиннее 10 минут. Сделайте более короткую тренировку.")
            if duration < 0.2:
                raise ProviderError("MEDIA_TOO_SHORT", "Запись слишком короткая. Запишите хотя бы несколько секунд речи.")
            # PCM energy only excludes effectively silent files; it is not a speech classifier.
            energy = sum(sample * sample for (sample,) in struct.iter_unpack("<h", frames))
            rms = math.sqrt(energy / max(1, len(frames) // 2))
            return target.read_bytes(), round(duration, 3), rms
        except (OSError, wave.Error, EOFError):
            raise ProviderError("MEDIA_INVALID", "Не удалось прочитать звук в записи. Запишите речь ещё раз.") from None


async def probe_media(path: Path):
    """Validate real audio during upload; transcript/ownership remain the worker's concern."""
    _, duration, _ = await _decode(path)
    with Path(path).open("rb") as source:
        header = source.read(16)
    if header.startswith(b"RIFF"):
        mime, extension = "audio/wav", ".wav"
    elif header.startswith(b"\x1aE\xdf\xa3"):
        mime, extension = "video/webm", ".webm"
    elif header.startswith(b"OggS"):
        mime, extension = "audio/ogg", ".ogg"
    elif header[4:8] == b"ftyp":
        mime, extension = "video/mp4", ".mp4"
    else:
        mime, extension = "audio/mpeg", ".mp3"
    return {"duration_seconds": duration, "mime_type": mime, "extension": extension}


async def transcribe(path: Path):
    audio, duration, rms = await _decode(path)
    if rms < 8:
        raise ProviderError("NO_SPEECH", "В записи не слышно речи. Проверьте микрофон и запишите речь ещё раз.")
    model = os.getenv("TRANSCRIPTION_MODEL", "whisper-large-v3")
    body, usage = await _request("/audio/transcriptions", model, "transcription", audio=audio, audio_seconds=duration)
    text = body.get("text")
    if not isinstance(text, str) or not text.strip() or not re.search(r"[^\W\d_]", text, re.UNICODE):
        error = ProviderError("NO_SPEECH", "Не удалось распознать речь. Проверьте звук и запишите речь ещё раз.")
        error.usage = usage
        raise error
    if len(text) > MAX_TEXT:
        raise _failed_response("Расшифровка слишком большая. Попробуйте более короткую тренировку.", usage)
    return {"text": text.strip(), "duration_seconds": duration, "usage": usage}


def _input(config, text):
    if not isinstance(config, dict):
        raise ProviderError("AI_INPUT_INVALID", "Не удалось прочитать настройки тренировки. Повторите попытку.")
    if not isinstance(text, str) or not text.strip():
        raise ProviderError("NO_SPEECH", "Сначала запишите речь для разбора.")
    if len(text) > MAX_TEXT:
        raise ProviderError("AI_INPUT_TOO_LONG", "Речь слишком большая для разбора. Сделайте более короткую тренировку.")
    safe = {key: str(config.get(key, ""))[:5000 if key == "criteria" else 3000]
            for key in ("scenario", "topic", "criteria")}
    # The API resolves this optional focus against an owned persisted report; it is
    # user-selected practice context, never an automatically imposed criterion.
    if isinstance(config.get('repeat_focus'), dict):
        focus = config['repeat_focus']
        safe['repeat_focus'] = {key: focus[key] for key in
                                ('source_practice_id', 'recommendation_index', 'title', 'action', 'transcript_revision')
                                if key in focus}
    return safe


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


async def _chat(operation, system, data, *, model=None):
    model = model or os.getenv("LLM_MODEL", "gpt-5.4")
    payload = {
        "model": model, "temperature": 0.2, "max_tokens": limits.setting('AI_MAX_OUTPUT_TOKENS'),
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": json.dumps(data, ensure_ascii=False)}],
    }
    body, usage = await _request("/chat/completions", model, operation, payload=payload)
    try:
        choice = body["choices"][0]
        if choice.get("finish_reason") == "length":
            raise ValueError()
        content = choice["message"]["content"]
        if not isinstance(content, str):
            raise ValueError()
        parsed = json.loads(content, object_pairs_hook=_unique_json_object)
        if not isinstance(parsed, dict):
            raise ValueError()
    except (KeyError, IndexError, TypeError, ValueError, RecursionError):
        error = ProviderError("AI_INVALID_RESPONSE", "Сервис разбора вернул неполный ответ. Запись сохранена; попробуйте ещё раз.")
        error.usage = usage
        raise error from None
    return parsed, usage


DATA_RULE = feedback_prompts.DATA_RULE


def _string(value, maximum=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError()
    return value.strip()


def transcript_revision(text):
    """Hash exact text, including whitespace; offsets are Python Unicode code points."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _quote_candidates(segments):
    """Canonical contiguous spans with exact offsets, origin and content revision."""
    quotes = []
    for segment in segments:
        segment_quotes = []
        text = segment['text']
        revision = transcript_revision(text)
        number = 0
        origin = 'speech' if segment['index'] == 0 else 'answer'
        boundaries = list(re.finditer(r'(?<=[.!?])\s+|\n+', text))
        cursor = 0
        for boundary in [*boundaries, None]:
            end = boundary.start() if boundary else len(text)
            start = cursor
            while start < end:
                while start < end and text[start].isspace():
                    start += 1
                stop = min(start + feedback_prompts.CAPS['quote'], end)
                if stop < end:
                    split = text.rfind(' ', start + 1, stop)
                    if split > start:
                        stop = split
                trimmed_stop = stop
                while trimmed_stop > start and text[trimmed_stop - 1].isspace():
                    trimmed_stop -= 1
                if trimmed_stop > start:
                    span = {'id': f"s{segment['index']}-q{number}",
                                   'segment_index': segment['index'], 'origin': origin,
                                   'text': text[start:trimmed_stop], 'transcript_revision': revision,
                                   'start_char': start, 'end_char': trimmed_stop}
                    quotes.append(span)
                    segment_quotes.append(span)
                    number += 1
                start = stop
            cursor = boundary.end() if boundary else end
        # A relation across adjacent statements needs a contiguous relational span,
        # not a model-created concatenation. Single q IDs retain their stable ordering.
        for index, (first, second) in enumerate(zip(segment_quotes, segment_quotes[1:])):
            start, end = first['start_char'], second['end_char']
            if end - start <= feedback_prompts.CAPS['quote']:
                quotes.append({**first, 'id': f"s{segment['index']}-p{index}",
                               'text': text[start:end], 'end_char': end})
    return quotes


_UNAVAILABLE_MODALITY = re.compile(
    r'\bголос(?:а|ом|е|у)?\b|громк|интонац|\bжест(?:ы|ов|ами|ах)?\b|мимик|\bпоз(?:а|ы|у|е|ой)\b|'
    r'эмоци|психолог|уверенн|взгляд|контакт.*глаз|пауз|тембр|дикци', re.I)


def _criterion_candidates(criteria):
    labels = [value.strip() for value in re.split(r'[;\n]+', criteria) if value.strip()]
    if len(labels) > 12:
        raise ProviderError('AI_INPUT_INVALID', 'Для одной тренировки можно задать не больше 12 критериев.')
    return [{'id': f'c{index}', 'text': label,
             'observability': 'unavailable_modality' if _UNAVAILABLE_MODALITY.search(label) else 'text_uncertain'}
            for index, label in enumerate(labels)]


def build_context(operation, config, segments):
    """Server-issued data envelope, shared by runtime and offline evaluation."""
    full_text = '\n\n'.join(segment['text'] for segment in segments)
    safe_config = _input(config, full_text)
    canonical = []
    saved_questions = []
    for segment in segments:
        item = {key: segment[key] for key in ('index', 'kind', 'text')}
        if 'duration_seconds' in segment:
            item['duration_seconds'] = segment['duration_seconds']
        model = segment.get('asr_model')
        item['asr_model'] = model if isinstance(model, str) and 0 < len(model) <= 300 else None
        item['capture_complete'] = segment.get('capture_complete') if type(segment.get('capture_complete')) is bool else None
        item['asr_quality'] = segment.get('asr_quality') if segment.get('asr_quality') in ('uncertain', 'unverified') else 'unknown'
        item.update(origin=segment['kind'], transcript_revision=transcript_revision(segment['text']),
                    lexical_completeness='unknown')
        canonical.append(item)
        if 'question' in segment:
            saved_questions.append({'answer_segment_index': segment['index'], 'text': segment['question'],
                                    'provenance': segment.get('question_provenance')})
    revision = transcript_revision(json.dumps(
        [{'index': s['index'], 'kind': s['kind'], 'text': s['text']} for s in segments],
        ensure_ascii=False, separators=(',', ':')))
    return {'schema_version': feedback_prompts.CONTEXT_VERSION, 'operation': operation,
            'prompt_version': feedback_prompts.QUESTIONS_VERSION if operation == 'questions' else feedback_prompts.REPORT_VERSION,
            'rubric_version': feedback_prompts.RUBRIC_VERSION, 'transcript_revision': revision,
            'context': safe_config, 'segments': canonical, 'saved_questions': saved_questions,
            'evidence': _quote_candidates(segments),
            'requested_criteria': _criterion_candidates(safe_config['criteria'])}


def _provenance(span):
    return {'evidence': span['text'], 'evidence_id': span['id'],
            **{key: span[key] for key in ('segment_index', 'origin', 'transcript_revision', 'start_char', 'end_char')}}


def question_provenance_matches(evidence, question, speech_text):
    """Question cache is reusable only for its exact source speech revision."""
    if not isinstance(evidence, dict) or not isinstance(speech_text, str):
        return False
    start, end = evidence.get('start_char'), evidence.get('end_char')
    selected = next((q for q in _quote_candidates([{'index': 0, 'text': speech_text}])
                     if q['id'] == evidence.get('evidence_id')), None)
    return (selected is not None and
            all(evidence.get(key) == selected[key] for key in ('segment_index', 'origin', 'transcript_revision', 'start_char', 'end_char')) and
            evidence.get('evidence') == selected['text'] and evidence.get('text') == question and evidence.get('segment_index') == 0 and
            evidence.get('origin') == 'speech' and
            evidence.get('transcript_revision') == transcript_revision(speech_text) and
            isinstance(start, int) and not isinstance(start, bool) and
            isinstance(end, int) and not isinstance(end, bool) and 0 <= start < end <= len(speech_text) and
            speech_text[start:end] == evidence.get('evidence'))


def _keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError()


async def generate_questions(config: dict, transcript: str):
    context = build_context('questions', config, [{'index': 0, 'kind': 'speech', 'text': transcript}])
    quote_map = {quote['id']: quote for quote in context['evidence']}
    result, usage = await _chat('questions', feedback_prompts.question_prompt(), context)
    try:
        _keys(result, ('questions',))
        items = result['questions']
        if not isinstance(items, list) or len(items) != 3:
            raise ValueError()
        questions, provenance = [], []
        for item in items:
            _keys(item, ('text', 'evidence_id'))
            evidence_id = item['evidence_id']
            if not isinstance(evidence_id, str) or evidence_id not in quote_map:
                raise ValueError()
            question = _string(item['text'], feedback_prompts.CAPS['question'])
            if len(question) < 8 or question.count('?') > 1:
                raise ValueError()
            _check_inline_quotations(question, quote_map[evidence_id]['text'])
            questions.append(question)
            provenance.append({'text': question, **_provenance(quote_map[evidence_id])})
        if len({question.casefold() for question in questions}) != 3:
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        error = ProviderError('AI_INVALID_RESPONSE', 'Не удалось подготовить три вопроса по вашей речи. Попробуйте ещё раз.')
        error.usage = usage
        raise error from None
    return {'questions': questions, 'usage': usage,
            'provenance': {'context_schema_version': feedback_prompts.CONTEXT_VERSION,
                           'prompt_version': feedback_prompts.QUESTIONS_VERSION,
                           'transcript_revision': context['transcript_revision'],
                           'chat_model': usage.get('model'), 'items': provenance}}


def _check_inline_quotations(text, evidence):
    # Literal source membership only; this does not prove the entailment of other claims.
    quoted = re.findall(r'''«([^»]+)»|“([^”]+)”|"([^"\n]+)"|'([^'\n]+)' ''', text, re.X)
    source = evidence.casefold()
    for groups in quoted:
        term = next(value for value in groups if value).strip()
        if term and term.casefold() not in source:
            raise ValueError('Inline source quotation is outside selected evidence')


def _findings(items, quotes, recommendation=False):
    cap = feedback_prompts.CAPS['recommendations' if recommendation else 'strengths']
    if not isinstance(items, list) or len(items) > cap:
        raise ValueError()
    checked = []
    for item in items:
        _keys(item, ('title', 'observation', 'action', 'example', 'evidence_id') if recommendation
              else ('title', 'observation', 'evidence_id'))
        evidence_id = item['evidence_id']
        if not isinstance(evidence_id, str) or evidence_id not in quotes:
            raise ValueError()
        finding = {'title': _string(item['title'], feedback_prompts.CAPS['title']),
                   'observation': _string(item['observation'], feedback_prompts.CAPS['observation']),
                   **_provenance(quotes[evidence_id])}
        _check_inline_quotations(finding['observation'], finding['evidence'])
        finding['text'] = finding['observation']
        if recommendation:
            finding['action'] = _string(item['action'], feedback_prompts.CAPS['action'])
            _check_inline_quotations(finding['action'], finding['evidence'])
            # Validate the raw draft before withholding it: malformed fields still fail.
            # Quote provenance does not establish factual safety of a rewritten example.
            if item['example'] is not None:
                _string(item['example'], feedback_prompts.CAPS['example'])
            finding['example'] = None
            finding['text'] = ' '.join([finding['observation'], finding['action']])
        checked.append(finding)
    return checked


def _criteria(items, requested, quotes):
    if not isinstance(items, list) or len(items) != len(requested):
        raise ValueError()
    criterion_map = {item['id']: item for item in requested}
    checked, selected = [], set()
    for item in items:
        _keys(item, ('criterion_id', 'status', 'basis', 'reason', 'evidence_id'))
        criterion_id = item['criterion_id']
        if not isinstance(criterion_id, str) or criterion_id not in criterion_map or criterion_id in selected:
            raise ValueError()
        selected.add(criterion_id)
        status, basis, evidence_id = item['status'], item['basis'], item['evidence_id']
        if status not in ('met', 'partial', 'not_met', 'unknown') or basis not in ('present', 'absent', 'unknown'):
            raise ValueError()
        reason = _string(item['reason'], feedback_prompts.CAPS['reason'])
        if basis == 'present':
            if status == 'unknown' or not isinstance(evidence_id, str) or evidence_id not in quotes:
                raise ValueError()
            provenance = _provenance(quotes[evidence_id])
        elif evidence_id is not None or (basis == 'unknown' and status != 'unknown') or (basis == 'absent' and status not in ('partial', 'not_met')):
            raise ValueError()
        else:
            provenance = {'evidence': '', 'evidence_id': None, 'segment_index': None, 'origin': None,
                          'transcript_revision': None, 'start_char': None, 'end_char': None}
        # No currently available ASR source establishes reliable lexical coverage. Even a
        # complete capture cannot distinguish an omitted word from recognition loss.
        if basis == 'absent' or criterion_map[criterion_id]['observability'] == 'unavailable_modality':
            status, basis = 'unknown', 'unknown'
            reason = ('По текстовой расшифровке нельзя оценить этот критерий.' if
                      criterion_map[criterion_id]['observability'] == 'unavailable_modality' else
                      'В доступной расшифровке нет достаточного основания: возможен пропуск при распознавании.')
            provenance = {'evidence': '', 'evidence_id': None, 'segment_index': None, 'origin': None,
                          'transcript_revision': None, 'start_char': None, 'end_char': None}
        checked.append({'criterion': criterion_map[criterion_id]['text'], 'status': status,
                        'basis': basis, 'reason': reason, **provenance})
    return checked


async def analyze(config: dict, segments: list):
    clean_segments = []
    try:
        if not isinstance(segments, list) or not segments or len(segments) > 4:
            raise ValueError()
        for segment in segments:
            index = segment['index']
            duration = segment['duration_seconds']
            if (not isinstance(index, int) or isinstance(index, bool) or not 0 <= index <= 3 or
                    not isinstance(duration, (int, float)) or isinstance(duration, bool) or
                    not math.isfinite(duration) or not 0 < duration <= MAX_DURATION or
                    segment.get('kind') != ('speech' if index == 0 else 'answer')):
                raise ValueError()
            # Preserve exact recognized text, including boundary whitespace, for hash/offset identity.
            text = segment.get('text')
            _string(text, MAX_TEXT)
            item = {'index': index, 'kind': segment['kind'], 'text': text, 'duration_seconds': duration,
                    'asr_model': segment.get('asr_model'),
                    'capture_complete': segment.get('capture_complete'), 'asr_quality': segment.get('asr_quality')}
            if 'question' in segment:
                if segment['kind'] != 'answer':
                    raise ValueError()
                item['question'] = _string(segment['question'], 600)
                item['question_provenance'] = segment.get('question_provenance')
            clean_segments.append(item)
        if len({item['index'] for item in clean_segments}) != len(clean_segments):
            raise ValueError()
        clean_segments.sort(key=lambda item: item['index'])
        if clean_segments[0]['index'] != 0:
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise ProviderError('AI_INPUT_INVALID', 'Для разбора нужна сохранённая речь с расшифровкой. Повторите обработку записи.') from None
    full_text = '\n\n'.join(segment['text'] for segment in clean_segments)
    context = build_context('report', config, clean_segments)
    quote_map = {quote['id']: quote for quote in context['evidence']}
    result, usage = await _chat('report', feedback_prompts.report_prompt(), context)
    try:
        _keys(result, ('strengths', 'recommendations', 'primary_recommendation_index', 'criteria'))
        strengths = _findings(result['strengths'], quote_map)
        recommendations = _findings(result['recommendations'], quote_map, recommendation=True)
        primary = result['primary_recommendation_index']
        if primary is not None and (not isinstance(primary, int) or isinstance(primary, bool) or not 0 <= primary < len(recommendations)):
            raise ValueError()
        checked_criteria = _criteria(result['criteria'], context['requested_criteria'], quote_map)
    except (KeyError, TypeError, ValueError):
        error = ProviderError('AI_UNGROUNDED_REPORT', 'Не удалось подтвердить выводы разбора вашей речью. Запись сохранена; повторите разбор.')
        error.usage = usage
        raise error from None
    words = len(re.findall(r"[^\W_]+(?:[-’'][^\W_]+)*", full_text, re.UNICODE))
    duration = sum(segment['duration_seconds'] for segment in clean_segments)
    metrics = [
        {'title': 'Продолжительность записей', 'text': f'{round(duration)} с', 'label': 'Речь и ответы без ожидания обработки'},
        {'title': 'Объём расшифровки', 'text': f'{words} слов', 'label': 'По распознанному тексту'},
        {'title': 'Средний темп записи', 'text': f'{round(words * 60 / duration)} слов/мин', 'label': 'Слова / длительность записи; включает молчание'},
    ]
    public_segments = []
    for segment in context['segments']:
        public = dict(segment)
        if segment['index'] > 0:
            question = next((q for q in context['saved_questions'] if q['answer_segment_index'] == segment['index']), None)
            if question:
                public['question'] = question['text']
        public_segments.append(public)
    return {'report': {'schema_version': 2, 'demo': False,
                       'primary_recommendation_index': primary,
                       'insight': recommendations[primary]['action'] if primary is not None else None,
                       'metrics': metrics, 'strengths': strengths, 'recommendations': recommendations,
                       'criteria': checked_criteria, 'transcript': full_text, 'transcript_segments': public_segments,
                       'transcript_revision': context['transcript_revision'],
                       'provenance': {'publisher_policy': 'withhold_unreviewed_rewrites-v1',
                                      'context_schema_version': feedback_prompts.CONTEXT_VERSION,
                                      'report_prompt_version': feedback_prompts.REPORT_VERSION,
                                      'rubric_version': feedback_prompts.RUBRIC_VERSION,
                                      'coaching_context_version': feedback_prompts.coaching_context.VERSION,
                                      'chat_model': usage.get('model'),
                                      'asr_models': sorted({s['asr_model'] for s in context['segments'] if s['asr_model']}),
                                      'asr_model_unknown': any(s['asr_model'] is None for s in context['segments'])},
                       'limitations': ['Расшифровка может содержать ошибки.',
                                       'Голос, интонация, паузы, жесты и психологическая уверенность не оцениваются.']}, 'usage': usage}


def editor_model():
    return os.getenv('FEEDBACK_EDITOR_MODEL', '').strip()


def can_reword_report(config, segments, report):
    """Reuse a compatible assessment only when its exact sources still match."""
    if not editor_model() or not isinstance(report, dict) or report.get('schema_version') != 2:
        return False
    if report.get('provenance', {}).get('report_prompt_version') not in ('speech-feedback-v2.3', 'speech-feedback-v2.4'):
        return False
    context = build_context('report', config, segments)
    if report.get('transcript_revision') != context['transcript_revision']:
        return False
    quotes = {q['id']: _provenance(q) for q in context['evidence']}
    for item in report.get('strengths', []) + report.get('recommendations', []) + report.get('criteria', []):
        if item.get('evidence_id') is None:
            continue
        expected = quotes.get(item['evidence_id'])
        if expected is None or any(item.get(k) != v for k, v in expected.items()):
            return False
    return True


async def _edited_fields(kind, fields):
    result, usage = await _chat(kind + '_wording', wording_prompts.SYSTEM,
                                {'fields': fields}, model=editor_model())
    try:
        _keys(result, ('fields',))
        items = result['fields']
        if not isinstance(items, list) or len(items) != len(fields):
            raise ValueError()
        originals = {f['id']: f for f in fields}
        edited = {}
        for item in items:
            if not isinstance(item, dict) or set(item) not in ({'id', 'text'}, {'id', 'text', 'max_chars'}):
                raise ValueError()
            key = item['id']
            if not isinstance(key, str) or key not in originals or key in edited:
                raise ValueError()
            original = originals[key]
            # Some adapters echo the read-only input cap. It cannot change policy.
            if 'max_chars' in item and (type(item['max_chars']) is not int or item['max_chars'] != original['max_chars']):
                raise ValueError()
            text = _string(item['text'], original['max_chars'])
            numbers = r'[+-]?\d+(?:[.,]\d+)?%?'
            if re.findall(numbers, text) != re.findall(numbers, original['text']):
                raise ValueError()
            if '**' in text or '```' in text:
                raise ValueError()
            if original['source']:
                _check_inline_quotations(text, original['source'])
            if kind == 'questions' and (len(text) < 8 or text.count('?') != 1 or not text.endswith('?')):
                raise ValueError()
            edited[key] = text
        if kind == 'questions' and len({v.casefold() for v in edited.values()}) != len(edited):
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        error = ProviderError('AI_WORDING_INVALID', 'Не удалось подготовить текст обратной связи. Запись сохранена; попробуйте ещё раз.')
        error.usage = usage
        raise error from None
    return edited, usage


async def reword_report(report):
    fields = []
    for group, names in [('strengths', ('title', 'observation')),
                         ('recommendations', ('title', 'observation', 'action')),
                         ('criteria', ('reason',))]:
        for index, item in enumerate(report[group]):
            for name in names:
                fields.append({'id': f'{group}/{index}/{name}', 'text': item[name],
                               'source': item.get('evidence', ''),
                               'max_chars': feedback_prompts.CAPS[name]})
    updated = json.loads(json.dumps(report))
    usage = None
    if fields:
        edited, usage = await _edited_fields('report', fields)
        for key, text in edited.items():
            group, index, name = key.split('/')
            updated[group][int(index)][name] = text
    for item in updated['strengths']:
        item['text'] = item['observation']
    for item in updated['recommendations']:
        item['text'] = ' '.join([item['observation'], item['action']])
    primary = updated['primary_recommendation_index']
    updated['insight'] = updated['recommendations'][primary]['action'] if primary is not None else None
    provenance = updated['provenance']
    provenance.setdefault('analysis_report_prompt_version', provenance['report_prompt_version'])
    provenance['report_prompt_version'] = feedback_prompts.REPORT_VERSION
    provenance['wording_editor'] = {'version': wording_prompts.VERSION,
                                    'model': usage['model'] if usage else None,
                                    'status': 'applied' if fields else 'not_needed'}
    return {'report': updated, 'usage': usage}


async def reword_questions(response):
    fields = [{'id': f'questions/{i}/text', 'text': text, 'source': response['provenance']['items'][i]['evidence'],
               'max_chars': feedback_prompts.CAPS['question']} for i, text in enumerate(response['questions'])]
    edited, usage = await _edited_fields('questions', fields)
    updated = json.loads(json.dumps(response))
    updated['questions'] = [edited[f'questions/{i}/text'] for i in range(len(fields))]
    for i, item in enumerate(updated['provenance']['items']):
        item['text'] = updated['questions'][i]
    updated['provenance']['wording_editor'] = {'version': wording_prompts.VERSION,
                                               'model': usage['model'], 'status': 'applied'}
    updated['usage'] = usage
    return updated
