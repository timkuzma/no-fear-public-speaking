# AI pipeline and limitations

`server/ai.py` contains no database or authorization logic. The worker persists each transcript, question set, report and usage record before advancing. Recordings stay private; the worker sends normalized audio to the configured external provider and sends transcript text to the chat model. Actual provider access and pricing must be checked by the operator.

## Environment

| Variable | Default | Meaning |
| --- | --- | --- |
| `LLM_BASE_URL` | `https://shared1.multitool.works:4000/v1` | OpenAI-compatible API root; never a browser setting. |
| `LLM_API_KEY` | None | Required server-only provider credential. |
| `LLM_MODEL` | `gigachat-3-pro` | Chat model supporting `/chat/completions` and `response_format: json_object`. |
| `TRANSCRIPTION_MODEL` | `whisper-large-v3` | Model supporting `/audio/transcriptions`, Russian language and JSON text output. |
| `LLM_TIMEOUT_SECONDS` | `120` | Per-attempt HTTP timeout, clamped to 5–180 seconds; connection timeout 10 seconds. |
| `LLM_MAX_ATTEMPTS` | `2` | Attempts including the initial call; clamped to 1–3. |
| `FFMPEG_BINARY` | PATH, then imageio-ffmpeg | Optional trusted binary path; never user input. |

Model listing alone does not establish support for either endpoint, JSON mode, transcription quality, tariffs or available quotas. Keep credentials out of source, general logs and exported browser configuration. No remote redirects are followed.

## Media

`await probe_media(Path)` returns `{duration_seconds,mime_type,extension}` after actual decoding. MIME and extension describe the verified container, not a user filename or whether an optional video track exists. It accepts supported WebM, MP4, WAV, Ogg and MP3 containers; rejects manifest/playlist input and disables network protocols during decoding. FFmpeg runs without a shell, with a 45-second wall-time bound and a 601-second PCM output cap. Recordings longer than 600 seconds, smaller than 0.2 seconds, invalid or over 100 MiB are rejected. The backend may impose a lower upload byte cap.

`await transcribe(Path)` converts audio to mono 16 kHz PCM WAV, rejects effectively silent decoded samples, then calls transcription. Energy is only a silence gate, not proof of speech: music/noise may still confuse ASR. Empty or nonalphabetic recognition fails honestly. No timestamps are requested or invented. The worker can retain the original browser recording for playback while sending only normalized audio externally.

## Questions and reports

`generate_questions(config, transcript)` supplies the actual speech and server-generated exact sentence/chunk candidates to the model. The model must return exactly three distinct objects with `text` and one canonical `evidence_id`. Unknown, missing, multiple or altered IDs, extra provenance fields, plain-string legacy responses, invalid lengths and duplicate question text fail without publishing questions. A failed validation retains the completed call's usage. The public result remains `questions: string[]`, so existing meeting and answer flows do not change.

The question prompt requires a concrete point from the selected speech fragment, with three different angles rather than paraphrases. Configured topic is context only, never evidence that the speaker discussed it. Sparse speech can reuse the same fragment for three clarifications without inventing technologies, plans or claims. Verified IDs establish that each selected fragment exists; they do not independently prove that a model's question is semantically relevant to it. Actual question quality still requires live model checks and human pilot feedback.

`analyze(config, segments)` accepts one speech and up to three answer segments with their real durations. The report follows `docs/api-contract.md`. The server extracts contiguous sentence/chunk candidates, preserving exact source characters and segment identity. The model selects one canonical `evidence_id` per finding; the server derives the exposed quote and segment index from its own candidate map. Unknown IDs, multiple IDs and mismatched segment claims fail. This avoids model-concatenated or retyped quotations without accepting paraphrases or fuzzy matches.

Caller criteria split on newline/semicolon only; otherwise the entire text is one criterion. The model selects server-assigned `criterion_id` values, and the server publishes the caller's original labels. Duplicate, missing or invented criteria fail. When the caller supplied none, unsolicited model criteria are discarded. `unknown` criteria may have no evidence.

Legacy exact-quote report results are also accepted: one matching decorative outer quote pair (`«»`, `“”`, or double quotes) is removed, then the inner substring must still match exactly. Legacy criteria require an exact caller label; a missing label can be derived only for one unambiguous caller criterion. Missing or fabricated evidence fails rather than publishing a demo. Quote provenance proves that a quote exists, not that every model interpretation is correct. The report prompt requests one concrete next-practice action and prohibits invented numeric achievements in examples; semantic usefulness still needs pilot review. Current prompt version: `pilot-evidence-v5` (the question grounding update; report validation remains unchanged).

The module derives recording duration, recognized word count and average words per minute itself. Words per minute includes silence within recorded segments and ASR mistakes; it is not articulation rate. Provider-created metrics are discarded. Voice, intonation, pauses, gestures, emotions and psychological confidence cannot be assessed by this text-only pipeline. Its fixed limitations are included in every report.

User criteria, topic and transcript are JSON data in a separate user message. System instructions explicitly reject instructions embedded in that data. Schema and quote checks constrain output, but cannot guarantee immunity to semantic prompt injection. The frontend must escape all strings.

## Errors, retries and accounting

Timeouts, transport errors, HTTP 429 and 5xx may retry with bounded backoff of 0.5 then 1 second. Authentication errors, other 4xx, invalid JSON and invalid report evidence are not retried automatically. The worker/user can retry a failed saved practice. Remote timeouts can still incur provider charges even when no response was received; there is no provider idempotency guarantee.

Usage contains model, operation, nullable input/output token counts, original audio seconds, total HTTP latency, prompt version and an `attempts` array. Each attempt records only status, latency and nullable token counts. Aggregate token counts are null if any attempt has unknown usage; known successful counts remain available inside the array. Original audio duration is not multiplied by retry count; estimate possibly billable audio as duration times the number of transcription attempts and clearly mark that as a bound, not a measured invoice. Audio-only providers commonly omit token usage.

Provider errors carry safe Russian `code`/`message` and, where a provider call completed, `.usage`. Neither raw provider error bodies nor transport exception details reach users or logs. Up to 4 KiB of HTTP 400/404 JSON is read solely to classify explicit unavailable-model diagnostics as `AI_MODEL_INVALID`; other error bodies are discarded unread. The response still contains only fixed safe Russian wording. Persist failed-call usage too. An invalid response after a successful call can still be billable. There are no hardcoded currency prices; compute cost only from verified tariffs and measured usage.

## Checks

`python -m pytest tests/test_ai.py tests/test_question_context.py` uses mocked HTTP transport for AI calls. Tests cover invalid JSON/shape, canonical question provenance and failed-call usage, sparse speech, exact report quote/segment grounding, model metric replacement, prompt data separation and escaping, retry accounting, error redaction, no-speech failures and actual FFmpeg duration/playlist validation. Answer questions remain context, never report evidence or recognized word counts. These checks do not establish live model quality or provider capacity. A separate small real synthetic-speech smoke test is required before first-user launch.
