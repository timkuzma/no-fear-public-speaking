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

`POST /api/practices/{id}/segments` multipart `{file,kind:"speech"|"answer",index:0|1|2|3}` -> segment `{id,kind,index,media_url,duration_seconds,transcript?}`. Speech index is 0; answer indexes 1–3. Server uses persisted questions to identify answers. Stream/bound upload, confirm real decodable audio, generated private filenames. Return success only after disk and database persistence. Repeated same segment index is a conflict, not a second billable upload.

`POST /api/practices/{id}/jobs` body `{kind:"questions"|"report"}` -> job `{id,practice_id,kind,status:"pending"|"running"|"succeeded"|"failed",stage,result:null|object,error:null|{code,message}}`. Duplicate active job returns existing job.

`GET /api/jobs/{id}` -> job. Questions success result is `{questions:[string,string,string]}`. Report success result is the Report object. Poll every 1.5–2 seconds. Durable jobs recover on server restart, bounded worker concurrency, never hold a SQLite transaction during a remote call.

`DELETE /api/practices/{id}` -> `{ok:true}`. Refuse deletion while processing or coordinate cancellation safely. Delete private media and persisted personal content.

`GET /api/practices/{id}/segments/{segment_id}/media` -> ownership-protected media response supporting playback and download.

`POST /api/practices/{id}/feedback` body `{rating:1..5,text:string}` -> `{ok:true}`.

`GET /api/health` -> `{ok:true}`. `GET /api/readiness` -> readiness status.

`GET /api/operator/metrics` and `/api/operator/export?format=json|csv`: operator bearer credential, no credentials in URL, no raw speech in general logs.

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
- `async transcribe(path: Path) -> dict`: `{text:string,duration_seconds:number,usage:Usage}`. Decode using environment `FFMPEG_BINARY` or imageio-ffmpeg binary fallback; enforce ten-minute media limit. Provider config from `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` (default GigaChat), `TRANSCRIPTION_MODEL` (default whisper-1), optional timeout settings. No secret files or logs.
- `async generate_questions(config:dict, transcript:str) -> dict`: `{questions:[string,string,string],usage:Usage}`.
- `async analyze(config:dict, segments:list[dict]) -> dict`: `{report:Report,usage:Usage}`. Segments include `{kind,index,text,duration_seconds}`. Module does not access DB or private ownership.
- `Usage`: `{model:string,input_tokens:int,output_tokens:int,audio_seconds:number,latency_ms:number,operation:string}`. Real provider counts when available; unknown counts remain null rather than fake zero. Retries bounded, record attempts if possible.

Backend worker stores transcripts and usage immediately after each successful stage. AI agent owns only `server/ai.py`, `tests/test_ai.py`, `docs/llm.md`; backend agent owns remaining `server/` and `tests/test_backend.py`. Frontend agent owns only `public/`. Root owns tooling, integration tests, dependencies, operations/docs and root agent instructions. No subagent commits or Git operations.
