# Metrics, load and cost

## Stored operational evidence

SQLite stores content-free product events, request template/status/latency/request ID, job failures and per-operation provider usage. Raw passwords, credentials, request bodies and speech are excluded from general logs. Usage and event history can be exported in JSON or CSV using the operator bearer credential. Exports are bounded to 10000 rows; `/api/operator/metrics` aggregates the current Moscow calendar day.

DAU is the number of distinct authenticated users who start a practice or open an owned report that day, timezone `Europe/Moscow`. It is an activity definition, not simply login count. Deleting a practice retains content-free activity events with its practice ID removed, so DAU does not shrink. Practice starts, recordings saved, reports ready/opened, repeat starts and feedback permit frequency/funnel analysis. The current repeat action creates a normal new practice; repeat intent is not a distinct event, so a dedicated repeat-conversion metric needs explicit linking in a future iteration.

Provider usage records include model, operation, prompt version, latency, attempts and reported input/output token counts. Missing provider counts are null. Failed responses, validation failures and retries preserve available usage. A timed-out request may still be billed remotely: neither a timeout nor a restart proves zero provider cost. The app cannot reconstruct unknown provider billing.

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

## Cost per active user

Provider tariffs have not been supplied or independently verified. No currency cost is claimed. Let `P_in` and `P_out` be actual currency per million input/output tokens and `P_audio` be currency per audio minute. For the measured 58.98-second speech-only sample:

`C_practice = (2340 × P_in + 163 × P_out) / 1,000,000 + 0.983 × P_audio`.

For the measured speech-plus-answers sample:

`C_practice = (4467 × P_in + 205 × P_out) / 1,000,000 + 1.63225 × P_audio`.

`Cost/DAU = practices per active user per day × C_practice + billed retry/failure cost per active user`.

| Assumed frequency | Daily cost expression |
|---:|---|
| 1 practice/day | `C_practice + retries` |
| 2 practices/day | `2 × C_practice + retries` |
| 5 practices/day | `5 × C_practice + retries` |

These samples are shorter than a typical five-minute speech. Re-measure typical speech and answers before forecasting production spend: fixed prompts, transcript length and answer duration make blind linear extrapolation unreliable. If the aggregator bills transcription differently, replace the audio-price term with its actual billing rule.
