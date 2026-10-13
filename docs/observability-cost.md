# Metrics, load and cost

## Stored operational evidence

SQLite stores content-free product events, request template/status/latency/request ID, job failures and per-operation provider usage. Raw passwords, credentials, request bodies and speech are excluded from general logs. Usage and event history can be exported in JSON or CSV using the operator bearer credential. Exports are bounded to 10000 rows; `/api/operator/metrics` aggregates the current Moscow calendar day.

DAU is the number of distinct authenticated users who start a practice or open an owned report that day, timezone `Europe/Moscow`. It is an activity definition, not simply login count. Deleting a practice retains content-free activity events with its practice ID removed, so DAU does not shrink. Practice starts, recordings saved, reports ready/opened, repeat starts and feedback permit frequency/funnel analysis. The current repeat action creates a normal new practice; repeat intent is not a distinct event, so a dedicated repeat-conversion metric needs explicit linking in a future iteration.

Provider usage records include model, operation, prompt version, latency, attempts and reported input/output token counts. Missing provider counts are null. Failed responses, validation failures and retries preserve available usage. A timed-out request may still be billed remotely: neither a timeout nor a restart proves zero provider cost. The app cannot reconstruct unknown provider billing.

Incremental ASR stores one usage row per independently transcribed chunk; `job_id` is the private chunk ID for those rows. A speech of `S` seconds normally needs `ceil(S / 5)` transcription requests. Complete cached speech avoids another whole-speech ASR request; incomplete/failed capture may add a full `S`-second transcription. Include both chunk calls and fallback/retry calls in cost, and check the provider's minimum per-request billing before comparing this path with a single full upload. The default daily live limit is 360 new chunks per account; it does not replace the final-job quota.

## Verified bounded API load

See `outputs/load-report.json`. Actual local HTTP test on macOS ARM, Python 3.12.14, one Uvicorn worker, disposable SQLite. Equal endpoint mix: authenticated current user, owned history, owned practice and health. Every request also persists a metric. No AI generation or upload in this load profile.

| Target RPS | Scheduled duration | Requests | Errors | p95 ms | p99 ms |
|---:|---:|---:|---:|---:|---:|
| 1 | 20 s | 20 | 0 | 14.76 | 14.76 |
| 5 | 20 s | 100 | 0 | 14.04 | 14.50 |
| 10 | 20 s | 200 | 0 | 14.05 | 15.22 |
| 20 | 10 s | 200 | 0 | 12.67 | 15.64 |
| 40 | 10 s | 400 | 0 | 8.36 | 10.44 |

Total 920 requests, no errors. Peak server-child RSS approximately 71.17 MiB. The bounded stress ramp found no failure point up to 40 RPS on this light profile. These are local results, not production latency or an upload/provider capacity claim. Load tests on the eventual host and separate upload/storage/provider tests remain necessary before scaling.

## Real provider samples

Synthetic Russian speech only. Models verified against the current aggregator model list: `whisper-large-v3`, `gigachat-3-pro`. No private user recording was used in development tests.

| Successful core sample | Audio | LLM input/output tokens | Measured operations |
|---|---:|---:|---|
| Speech only, uploaded WAV | 26.235 s | Report 2044 / 159 | Final report latency 1.802 s; transcription 1.694 s from retained stage |
| Speech plus three answers | 97.935 s | Questions 1484 / 43; final report 2983 / 162 | Questions 0.926 s; report 1.951 s; four transcriptions total 3.276 s |
| Browser MediaRecorder speech | 58.98 s | Report 2340 / 163 | Transcription 2.280 s; report 1.759 s; full worker job 4.212 s |

The final successful report is prompt version `pilot-evidence-v3`. Earlier failed report attempts were retained with their real token counts and are additional development cost, not included in the successful-path table. Two direct diagnostic report calls also occurred outside the worker; their cost is not included in stored usage, so stored development usage is not an exhaustive billing ledger.

For the uninterrupted browser sample, observed LLM prompt+completion volume is 2503 tokens over a 4.212-second worker job: normalized **35655 tokens/minute** for this short sample. Output tokens divided by full nonstreaming report response latency gives **92.7 output tokens/second**. These ratios describe a tiny measured sample. They do not establish sustained TPM quota, streaming generation TPS or capacity under concurrent provider load. The provider did not return transcription token counts; audio duration is tracked separately.

## Reconciled aggregator accounting, 12 October 2026

A separate synthetic Russian audio practice completed through the application's actual authenticated API and both durable workers in an isolated database. Speech was exactly 180 seconds, followed by three 30-second answers. Twelve independent 15-second WAV chunks were recognized during the speech stage. Questions reused that complete transcript; the final report reused it again and recognized only the three answers. Both jobs succeeded and the persisted practice reached `ready`. This checks the server core loop; it is not a browser/microphone interaction test or a statistical average across users.

The provided key's own `/spend/logs` rows were matched to the 17 local provider usage records by the isolated run's time interval, models and token counts. No additional provider calls, fallback or retries occurred. Chat response cost headers independently matched the two corresponding ledger rows.

| Operation | Real provider calls | Audio / reported tokens | Recorded gateway `spend` |
|---|---:|---|---:|
| Incremental speech recognition | 12 | 180 seconds | 0.00000000 |
| Answer recognition | 3 | 90 seconds | 0.00000000 |
| Three audience questions | 1 | 4080 input / 94 output tokens | 0.19886354 |
| Final report | 1 | 4998 input / 186 output tokens | 0.27278512 |
| **Complete practice** | **17** | **270 seconds of audio** | **0.47164866** |

The key's cumulative `spend` initially read `4.380966206199998` and, after asynchronous accounting flushed, read `4.852614866199998`. Their difference, `0.4716486599999996`, matches the sum of all 17 ledger entries within floating-point precision. Two later key readbacks confirmed the updated total. An initial read immediately after completion was stale; an unrelated TLS failure during the first ledger read was resolved with GET requests only, without repeating any generation.

The gateway reports upstream prompt caching: 1584 question input tokens and 1712 report input tokens were cached. Its cost breakdown charges 2496 question input tokens and 3286 report input tokens, with no additional cached-input cost. This helps explain why a full-input token estimate overstates this particular run. The ledger's `cache_hit` field is the string `None`; it does not describe upstream prompt-token caching. Use `metadata.usage_object.prompt_tokens_details.cached_tokens` instead.

Amortizing this complete practice over its 180-second speech gives **0.15721622 accounting units per speech minute** and **0.0026202703 per speech second**, including all three answers, questions and the report. Amortizing over all 270 recorded seconds gives 0.10481081 per audio minute and 0.0017468469 per audio second. These are allocations of one measured run's cost, not tariffs for independent one-second or one-minute practices.

**Accounting scope:** the API does not declare a currency. The observed GigaChat rate numbers match Cloud.ru's published RUB rates, but that does not establish the gateway's account denomination or final monetary settlement. Do not label these confirmed ledger units as RUB or USD without operator confirmation. All 15 transcription rows contain zero `spend`; their recorded audio durations sum to 270 seconds. This establishes zero recognition expense in the gateway's current meter for this run, not free upstream recognition. Its Whisper model metadata supplies a token output rate rather than an audio-seconds rate, while transcription usage contains seconds and no tokens; this is consistent with missing audio cost accounting and requires operator verification before production cost forecasting.

Sanitized local evidence is retained in ignored `outputs/test-artifacts/billing-audit-fb141800/evidence.json`: per-request identifiers, costs, usage, audio durations and reconciliation. Credentials, identities, raw provider payloads and voice content are excluded from this evidence file; the synthetic media and disposable application database remain outside the maintained application and Git. API documentation: [LiteLLM spend tracking](https://docs.litellm.ai/docs/proxy/cost_tracking).

## Cost per active user

Public upstream tariffs and gateway model-rate metadata were checked on 12 October 2026, but the gateway's settlement currency and upstream transcription charges remain unconfirmed. The reconciled gateway accounting above supersedes tariff-only estimates for that specific run. For uncached planning estimates, let `P_in` and `P_out` be actual currency per million input/output tokens and `P_audio` be currency per audio minute. For the older measured 58.98-second speech-only sample:

`C_practice = (2340 × P_in + 163 × P_out) / 1,000,000 + 0.983 × P_audio`.

For the measured speech-plus-answers sample:

`C_practice = (4467 × P_in + 205 × P_out) / 1,000,000 + 1.63225 × P_audio`.

`Cost/DAU = practices per active user per day × C_practice + billed retry/failure cost per active user`.

| Assumed frequency | Daily cost expression |
|---:|---|
| 1 practice/day | `C_practice + retries` |
| 2 practices/day | `2 × C_practice + retries` |
| 5 practices/day | `5 × C_practice + retries` |

The formula samples are shorter than a typical five-minute speech. Re-measure representative speech and answers before forecasting production spend: fixed prompts, transcript length, caching and answer duration make blind linear extrapolation unreliable. If the aggregator bills transcription differently, replace the audio-price term with its verified billing rule. Do not treat the observed zero audio meter as a permanent tariff.

## Production guards and telemetry

`/api/operator/status` exposes content-free queue/worker/storage health, recent failures, rolling 24-hour `ai_attempts` reservations, configured caps and backup/operation state. `scripts/monitor.py` confirms incidents over three checks, deduplicates changes and retries private HTTPS notification delivery; the external public-only probe runs independently of the application host. See `docs/operations.md` for alert codes, schedules and recovery.

The ledger reserves one attempt, actual audio duration, input character volume and the requested output-token ceiling BEFORE each HTTP transmission, including retries. Failed/unknown outcomes remain counted; crashes can repeat upstream work. It is a conservative work guard and cannot assert a currency, monetary spend or provider billing completeness. `usage` continues to record provider-reported token counts separately. Attempts are retained 48 hours, events/usage 90 days, with hourly pruning; protected exports are required for longer accounting history. No new real provider calls or billing measurements are implied by infrastructure acceptance.
