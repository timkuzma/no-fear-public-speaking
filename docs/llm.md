# AI pipeline and limitations

`server/ai.py` contains no database or authorization logic. The worker persists each transcript, question set, report and usage record before advancing. Recordings stay private; the worker sends normalized audio to the configured external provider and sends transcript text to the chat model. Actual provider access and pricing must be checked by the operator.

## Environment

| Variable | Default | Meaning |
| --- | --- | --- |
| `LLM_BASE_URL` | `https://shared1.multitool.works:4000/v1` | OpenAI-compatible API root; never a browser setting. |
| `LLM_API_KEY` | None | Required server-only provider credential. |
| `LLM_MODEL` | `gpt-5.4` | Chat model supporting `/chat/completions` and `response_format: json_object`. |
| `FEEDBACK_EDITOR_MODEL` | Empty (disabled) | Optional wording editor; production/bootstrap select `gpt-5.4-mini` through the same provider. |
| `TRANSCRIPTION_MODEL` | `whisper-large-v3` | Model supporting `/audio/transcriptions`, Russian language and JSON text output. |
| `LLM_TIMEOUT_SECONDS` | `120` | Per-attempt HTTP timeout, clamped to 5–180 seconds; connection timeout 10 seconds. |
| `LLM_MAX_ATTEMPTS` | `2` | Attempts including the initial call; clamped to 1–3. |
| `FFMPEG_BINARY` | PATH, then imageio-ffmpeg | Optional trusted binary path; never user input. |

Model listing alone does not establish support for either endpoint, JSON mode, transcription quality, tariffs or available quotas. Keep credentials out of source, general logs and exported browser configuration. No remote redirects are followed.

## Media

`await probe_media(Path)` returns `{duration_seconds,mime_type,extension}` after actual decoding. MIME and extension describe the verified container, not a user filename or whether an optional video track exists. It accepts supported WebM, MP4, WAV, Ogg and MP3 containers; rejects manifest/playlist input and disables network protocols during decoding. FFmpeg runs without a shell, with a 45-second wall-time bound and a 601-second PCM output cap. Recordings longer than 600 seconds, smaller than 0.2 seconds, invalid or over 100 MiB are rejected. The backend may impose a lower upload byte cap.

`await transcribe(Path)` converts audio to mono 16 kHz PCM WAV, rejects effectively silent decoded samples, then calls transcription. Energy is only a silence gate, not proof of speech: music/noise may still confuse ASR. Empty or nonalphabetic recognition fails honestly. No timestamps are requested or invented. The worker can retain the original browser recording for playback while sending only normalized audio externally.

## Questions and reports

The candidate v2 context/draft/public contracts are documented in [ai-quality-contract.md](ai-quality-contract.md). Application-owned versioned prompts and shared caps live in `server/feedback_prompts.py`: question `questions-v2.3`, report `speech-feedback-v2.4`, context `speech-context-v2`, rubric `contextual-text-v2`. They remain tool-free calls under the existing reservation scope; no runtime critic is added.

`generate_questions(config, transcript)` compiles speech-only exact contiguous evidence with content hashes and Unicode offsets. It requires three distinct question objects with one valid evidence ID and closed keys. Multiple question marks and inline quotations outside the selected source fail validation. The prompt asks for natural questions without quotation prefixes. Private question provenance is persisted separately; public questions remain strings. Answer processing binds the real saved question by index and rechecks its exact speech revision/ID/span where v2 provenance exists. Legacy saved questions without provenance remain usable with unknown origin metadata.

`analyze(config, segments)` separately receives the original speech, saved question context and confirmed answer text. Topic/scenario are weak context; optional repeat focus is user-selected context, never automatically substituted into formal criteria. Topic and criteria are optional in the shared duration/topic setup. The contextual prompt avoids imposed project-defense outlines, compulsory statistics and invented example facts. Prompt policy guides behavior but cannot guarantee semantic compliance.

The report prompt now requests `example:null`. Under fixed publisher policy `withhold_unreviewed_rewrites-v1`, the compiler validates a raw example's type/length but withholds it from new public reports, compatibility text and derived fields. Old stored examples remain readable. An exploratory earlier prompt still invented causal benefits despite explicit fact-preserving instructions; the policy contains that field rather than proving semantic truth. Observation/action can still be unsupported, and raw-draft failures must remain separate from compiled-report metrics. No critic or automatic paid repair is added.

Fresh report drafts use strict v2 IDs and closed fields. Strengths permit 0–2 and recommendations 0–3. Main focus is an index into checked recommendations or null; public `insight` is derived solely from that action. Empty findings do not force praise or a made-up coaching action. Old **stored** reports remain unchanged/readable; obsolete provider draft shapes are not accepted on new calls.

Criteria are exactly the original user-selected list. Presence requires a canonical quote; absence is downgraded to unknown because current ASR cannot certify lexical completeness. A complete audio/chunk manifest does not mean every word was recognized. Common non-observable modalities conservatively compile to unknown; the heuristic is neither complete nor a semantic classifier. Unknown is insufficient evidence, not poor performance.

The module calculates duration, recognized word count and descriptive words/minute locally. Questions are not spoken text. WPM includes silence and ASR errors and does not establish articulation rate. Voice, intonation, pauses, gestures, emotions and psychological confidence are outside the text-only pipeline. All rendered strings remain escaped. IDs/hashes establish exact provenance, not entailment, external truth, fact-preserving examples, usefulness or immunity to semantic prompt injection; those require separate evaluation.

## Errors, retries and accounting

Timeouts, transport errors, HTTP 429 and 5xx may retry with bounded backoff of 0.5 then 1 second. Authentication errors, other 4xx, invalid JSON and invalid report evidence are not retried automatically. The worker/user can retry a failed saved practice. Remote timeouts can still incur provider charges even when no response was received; there is no provider idempotency guarantee.

Usage records the producing question/report prompt version separately, or `asr-v1` for transcription; this is pipeline versioning, not proof of an immutable upstream model. Usage contains model, operation, nullable input/output token counts, original audio seconds, total HTTP latency, prompt version and an `attempts` array. Each attempt records only status, latency and nullable token counts. Aggregate token counts are null if any attempt has unknown usage; known successful counts remain available inside the array. Original audio duration is not multiplied by retry count; estimate possibly billable audio as duration times the number of transcription attempts and clearly mark that as a bound, not a measured invoice. Audio-only providers commonly omit token usage.

Provider errors carry safe Russian `code`/`message` and, where a provider call completed, `.usage`. Neither raw provider error bodies nor transport exception details reach users or logs. Up to 4 KiB of HTTP 400/404 JSON is read solely to classify explicit unavailable-model diagnostics as `AI_MODEL_INVALID`; other error bodies are discarded unread. The response still contains only fixed safe Russian wording. Persist failed-call usage too. An invalid response after a successful call can still be billable. There are no hardcoded currency prices; compute cost only from verified tariffs and measured usage.

## Checks

`python -m pytest tests/test_ai.py tests/test_question_context.py tests/test_feedback_contract.py` uses mocked AI HTTP transport/functions. It checks strict fields/counts/lengths, primary-action mapping, exact canonical source hashes/offsets, adjacent contiguous evidence, private question-cache revision integrity, sparse/null output, unknown criteria, context separation, retries/accounting, no-speech failures, error redaction and real local FFmpeg decoding bounds. These checks establish deterministic contract behavior, not live coaching quality or provider capacity. Baseline/candidate human-reviewed evaluation, a bounded real-provider smoke and actual user comprehension checks remain separate acceptance gates.

## Coaching guidance and explicit report update

General analysis remains independent of optional user criteria, with trusted condensed guidance in `server/coaching_context.py`; see [research](research/coaching-question-feedback.md). Transcript punctuation is not speaker behavior. Inline source-word checks in observations/actions contain literal quotation errors only, not unquoted unsupported advice. See [bounded model checks](feedback23-validation.md) for actual provider observations and their limits.

An owner may update a report from an older prompt version without re-recording. The existing generation ledger and quotas still apply. Preserve the old report until success and its previous successful job result afterward; failed updates leave recordings and the old report intact.

## DeepSeek wording stage

The user originally requested editing model-authored formulations through DeepSeek, then requested a faster replacement without sacrificing wording quality. Production now selects `gpt-5.4-mini` after a [bounded comparison](wording-editor-comparison.md). The worker makes one additional bounded `questions_wording` or `report_wording` call when `FEEDBACK_EDITOR_MODEL` is nonempty. Analysis stays with `LLM_MODEL`. No new service, browser credential, audio transmission or assessment critic is added.

The editor receives only allowlisted display strings and their exact source excerpt. It returns exactly the same field IDs once each. Unknown/missing/duplicate IDs, excess fields, invalid lengths, changed digit sequences (including signs/percent), unsupported inline quotations and compound/duplicate edited questions fail publication. Assessment status, criteria labels, number/order of findings, primary choice, transcript/recordings, metrics and canonical evidence are not offered as editable fields. Compatibility text/insight are derived from the edited observation/action.

These are structural safeguards, not a semantic-equivalence proof. The prompt forbids changing meaning, evidence, uncertainty, facts or advice direction; actual wording needs review. Version `speech-wording-v2` explicitly preserves the author/listener distinction, local scope and uncertainty, a heading's original intent and observable verification actions. It requests minimal changes to already clear text. Failure keeps the previous report/recording and offers the existing retry. A successful assessment's usage is persisted before editing, so failed editing does not lose accounting. Both requests still reserve work before transmission; an editor adds latency and usage.

A compatible saved v2.3/v2.4 report with matching transcript revision and exact evidence is reworded without another assessment or ASR call. Previous successful job results retain the earlier text. New report provenance records `analysis_report_prompt_version` and `wording_editor:{version,model,status}`. Fresh reports use `speech-feedback-v2.4`; questions use `questions-v2.3`, and new editor usage uses `speech-wording-v2`. Existing reports retain their stored editor version.

Default daily reserved output capacity increases from 300,000 to 600,000 to accommodate the added stage at the same bounded job capacity. Attempts, per-user caps, per-call 3,000 output limit, daily job count and audio caps remain unchanged. This is a work cap, not a monetary budget or a quoted tariff. Unknown provider prices/currency stay unknown. Explicit installations can choose a lower capacity.
