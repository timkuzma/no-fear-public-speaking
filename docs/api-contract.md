# Pilot integration contract

All JSON endpoints use same-origin `/api`. JSON success bodies are flat; errors are `{error:{code,message}}` with Russian user-facing messages and appropriate HTTP status. All media and user data require server-side ownership checks. No frontend credentials, session tokens or passwords in localStorage.

## Authentication

- `GET /api/auth/me` -> `{user:null|{id,email,name,role,onboarding_completed},csrf_token:null|string,provider_ready:boolean,registration_requires_invite:boolean}`. Return 200 when anonymous.
- `POST /api/auth/register` body `{email,name,password,role,invite_code?,consent:true}` -> `{user,csrf_token}` and session cookie.
- `POST /api/auth/login` body `{email,password}` -> `{user,csrf_token}` and session cookie.
- `POST /api/auth/logout` -> `{ok:true}`. Authenticated mutations carry `X-CSRF-Token`; auth entry endpoints validate Origin.
- `POST /api/auth/reset` body `{token,password}` consumes an operator-issued one-use token -> `{ok:true}`. Never reveal an existing password. Operator CLI issues tokens only after identity checking outside the application.
- `PATCH /api/auth/me` body `{onboarding_completed:true}` -> `{user}`.

Development registration may omit an invite; production must fail closed without explicit invite configuration. Provider readiness means configured, not proven healthy.

## Practices, segments and jobs

`POST /api/practices` body `{scenario: "speech"|"defense"|"free",topic:string,duration:number,questions:boolean,criteria:string}` -> full practice.

`GET /api/practices?limit=30&offset=0` -> `{items:[practice],total:number}`.

`GET /api/practices/{id}` -> full practice:
```
{id,config,created_at,status:"draft"|"processing"|"ready"|"failed",
 questions:[],report:null|Report,segments:[],active_job:null|Job}
```

`POST /api/practices/{id}/segments` multipart `{file,kind:"speech"|"answer",index:0|1|2|3,live_session_id?:string,live_chunk_count?:number}` -> segment `{id,kind,index,media_url,duration_seconds,has_video:boolean,transcript?}`. Speech index is 0; answer indexes 1–3. Server uses persisted questions to identify answers. Stream/bound upload, confirm real decodable audio, generated private filenames. Return success only after disk and database persistence. Repeated same segment index is a conflict, not a second billable upload. Optional live fields bind the exact speech recording to an incremental transcript manifest; omit both when incremental capture/upload was incomplete.

`POST /api/practices/{id}/jobs` body `{kind:"questions"|"report"}` -> job `{id,practice_id,kind,status:"pending"|"running"|"succeeded"|"failed",stage,result:null|object,error:null|{code,message}}`. Duplicate active job returns existing job.

`GET /api/jobs/{id}` -> job. Questions success result is `{questions:[string,string,string]}`. Report success result is the Report object. Poll every 1.5–2 seconds. Durable jobs recover on server restart, bounded worker concurrency, never hold a SQLite transaction during a remote call.

`DELETE /api/practices/{id}` -> `{ok:true}`. Refuse deletion while processing or coordinate cancellation safely. Delete private media and persisted personal content.

`GET /api/practices/{id}/segments/{segment_id}/media` -> ownership-protected media response supporting playback and download.

`POST /api/practices/{id}/feedback` body `{rating:1..5,text:string}` -> `{ok:true}`.

`GET /api/health` -> `{ok:true}`. `GET /api/readiness` -> readiness status.

`GET /api/operator/metrics` and `/api/operator/export?format=json|csv`: operator bearer credential, no credentials in URL, no raw speech in general logs.

Export also accepts `kind=usage|events` and `limit` capped at 10000. JSON is `{items:[row]}`; metrics is a separate aggregate. Media download uses `?download=true`, a validated container extension and MIME. Browser streaming WebM is losslessly finalized before persistence for finite duration and seeking, preserving required audio and optional video. Video is available for private playback; the analysis pipeline uses only audio and transcript. Total audio across all segments is capped at 600 seconds.

## Incremental speech transcription

Authenticated, consenting users can upload speech audio while the meeting continues. Guests never call a provider before registration and consent; their imported full recording uses the existing durable job. Questions remain in the same meeting chat after speech completion.

- `POST /api/practices/{id}/live-chunks` multipart `{file,session_id,index,offset_seconds}` -> `{session_id,index,status:"pending"|"running"|"succeeded"|"failed"}`. A session is 32 lowercase hexadecimal characters generated for one recording attempt. Each file is an independently decodable mono, 16kHz, signed 16-bit PCM WAV. Send approximately 15-second chunks and a final shorter tail, up to 16.1 seconds / 512 KiB each. Even a one-sample tail is valid. Uploads are sequential, indexes start at zero and offsets equal the preceding chunks' cumulative decoded duration (50ms tolerance). At most 64 chunks; aggregate duration cannot exceed configured speech duration plus 750ms, or ten minutes plus 750ms. Same-index retries require identical bytes and offset, return the existing status and consume no additional quota.
- `GET /api/practices/{id}/live-transcript?session_id=...` -> `{session_id,status:"waiting"|"processing"|"ready"|"failed"|"obsolete",completed_chunks,recognized_words,transcript,error?:{code,message}}`. Text and counts cover only the contiguous successful prefix. `ready` describes currently accepted chunks; it does not imply the speaker has stopped or that an unsubmitted final tail was received. A missing session returns `waiting`. Both endpoints enforce practice ownership. Mutations also enforce same-origin, CSRF and consent; the request-body guard runs before multipart parsing.
- A new session's first chunk supersedes previous open sessions for that practice. Late old chunks return `409 LIVE_SESSION_STALE`; submitted chunks cannot be changed (`409 LIVE_CHUNK_CONFLICT`) or reordered (`409 LIVE_CHUNK_ORDER`). Bound/saved speeches accept no new chunks. Provider configuration is required for chunk admission, and a default account quota of 120 new chunks per 24 hours (`DAILY_LIVE_CHUNK_LIMIT`) remains effective after practice deletion. At the maximum chunk size this permits at most 1,932 seconds of incremental audio daily.

The browser finishes its tail and awaits upload acknowledgment before speech autosave. `live_chunk_count` records the final exact manifest length. The job worker reuses a live transcript only if every expected chunk succeeded, indexes and offsets are contiguous from zero, and cumulative decoded duration matches the saved full recording within 750ms. Missing manifest, missing tail, failed chunk, empty transcript or mismatched duration falls back to transcription of the entire saved audio. A successful prefix is never treated as a complete speech. The worker may wait up to 20 seconds for pending chunks before using that fallback.

A chunk with `NO_SPEECH` completes successfully with empty text: silent pauses/tails still provide confirmed audio coverage. Such a chunk creates no service-failure event. Provider usage is retained if recognition made a remote call; local silence detection does not invent billable usage. A wholly empty concatenated transcript is never reusable and falls back to full-recording ASR, which can fail honestly with `NO_SPEECH`.

Before a live ASR call, a local PCM activity gate also suppresses boundary slivers: a chunk must contain at least 1,600 samples with absolute amplitude above 8 (100ms cumulative activity at 16kHz, using the existing silence floor). Otherwise it completes with empty text and no provider call/usage row. This reduces hallucinated filler on nearly silent chunks but cannot distinguish speech from music/noise, and may omit extremely brief fragments or audio below the silence floor. It does not alter full-recording transcription or claim acoustic speech analysis.

Live chunks use a separate SQLite queue, with one serialized live ASR worker and startup recovery of interrupted calls. The existing serialized job worker can run concurrently (up to two provider operations total). Never run multiple application processes sharing the database. Chunk media stays private; successful/failure provider usage is persisted per chunk with unknown token counts left unknown. No transcript or provider response text enters general logs. Deletion refuses running jobs/live calls, and otherwise removes chunk files and rows; obsolete in-flight calls finish accounting then remove their private chunk. `/api/readiness` includes `live_worker_alive` and requires both workers when workers are enabled.

## Report shape shared by worker and UI

```
{demo:false,insight:string,
 metrics:[{title,text,label}],
 strengths:[{title,text,evidence:string,segment_index?:number}],
 recommendations:[{title,text,evidence:string,segment_index?:number}],
 criteria:[{criterion,status:"met"|"partial"|"not_met"|"unknown",evidence:string}],
 limitations:[string],transcript:string}
```

Transcript evidence must be verified against actual supplied segment text. No invented psychological, gesture or acoustic assessment. Derive words/minute only from word count and measured audio duration, identify pauses/silence limits. No invented timestamps. UI escapes all provider/user strings and labels public examples explicitly.

## AI module contract (owned by AI agent)

`server/ai.py` exports:

- `ProviderError(code: str, message: str)`; messages are safe and Russian, never contain key/provider response bodies.
- `async transcribe(path: Path) -> dict`: `{text:string,duration_seconds:number,usage:Usage}`. Decode using environment `FFMPEG_BINARY` or imageio-ffmpeg binary fallback; enforce ten-minute media limit. Provider config from `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` (default gigachat-3-pro), `TRANSCRIPTION_MODEL` (default whisper-large-v3), optional timeout settings. No secret files or logs.
- `async generate_questions(config:dict, transcript:str) -> dict`: `{questions:[string,string,string],usage:Usage}`.
- `async analyze(config:dict, segments:list[dict]) -> dict`: `{report:Report,usage:Usage}`. Segments include `{kind,index,text,duration_seconds,question?}`. The worker binds each answer to its persisted question by index. Question text is untrusted context, excluded from transcript evidence and word counts. Module does not access DB or private ownership.
- `Usage`: `{model:string,input_tokens:int,output_tokens:int,audio_seconds:number,latency_ms:number,operation:string}`. Real provider counts when available; unknown counts remain null rather than fake zero. Retries bounded, record attempts if possible.

Backend worker stores transcripts and usage immediately after each successful stage. AI agent owns only `server/ai.py`, `tests/test_ai.py`, `docs/llm.md`; backend agent owns remaining `server/` and `tests/test_backend.py`. Frontend agent owns only `public/`. Root owns tooling, integration tests, dependencies, operations/docs and root agent instructions. No subagent commits or Git operations.

## Recording before authentication

Guest drafts remain client-side until registration/login and consent. No anonymous API exposes private media or report data. The browser resumes the same configuration and uploads the same audio after authentication.

`POST /api/practices` accepts an optional `idempotency_key` of 32 lowercase hexadecimal characters. Replaying the same configuration/key for the same account returns the existing practice, including any uploaded segments. A changed configuration returns `409 PRACTICE_KEY_CONFLICT`. The key is scoped to the authenticated account and omitted from stored/returned configuration. Existing authentication, origin and CSRF checks still apply. This supports recovery from an ambiguous creation/upload response without creating another practice.
