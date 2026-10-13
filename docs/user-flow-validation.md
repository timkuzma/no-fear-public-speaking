# Recording recovery acceptance

Validated locally on 13 October 2026. This is a user-flow acceptance result, not an external release or a claim about AI quality.

## Automated regression checks

Final result: 92 pytest tests passed. The recording harness exercised 16 lifecycle/recovery cases; the unchanged live-audio harness also passed. All five frontend/worklet modules passed Node syntax checks, changed frontend files passed Prettier checks, and `git diff --check` was clean.

`pytest -q` covers backend authentication/ownership, stable upload keys, original-byte conflicts, restart replay without additional upload quota, deletion of upload manifests, workers, media decoding and backup/restore. The Node recording harness covers completion, automatic saving, guest storage, failed upload retry, answer review, reload recovery, same-account reauthentication, other-account isolation, matching server acknowledgement, conflicting server media, unavailable browser storage and interrupted capture checkpoints. Live-audio tests still verify ordered standalone PCM WAV uploads and full-recording fallback.

Run with the project's Python 3.12 virtual environment, Node syntax checks for all five frontend/worklet modules, and `git diff --check`.

## Browser acceptance

The actual maintained frontend and API ran on an isolated loopback fixture with temporary SQLite/private media. Chromium used native MediaRecorder and an AudioContext oscillator in place of microphone hardware. Test provider functions returned fixed transcripts/questions/reports; no audio, credentials or requests went to an external AI provider. Native IndexedDB and FFmpeg upload validation were exercised. The meeting scene remained in place through speech save/question generation.

The fixture database confirmed two completed practices, eight saved segments, two successful report jobs and zero duplicate stage rows. Each practice ended with one speech, three answers and one report. The repeat preserved the explicitly selected recommendation. The following faults and continuations were checked:

- Guest recording survived a page reload and moved to a newly registered account without another capture.
- An expired session rejected answer upload; the original answer survived navigation to login and reauthentication, then uploaded and continued at the next question.
- A lost server response after accepting an answer left a local draft; reload recognized the same server capture and continued without a second segment.
- An unconfirmed answer survived reload on its existing review screen.
- Reload during speech restored an interrupted aggregate recording. Explicit confirmation uploaded a decodable Chromium WebM fragment and continued to questions.
- Signing in to another account showed no recording or continuation from the original owner. Signing back in exposed the original owner's unfinished practice and draft.
- A rejected upload survived leaving for the workspace and reloading; its continuation card resumed the upload and the next question.
- Both completed reports remained available in history; accepted account and guest drafts were gone.
- Native IndexedDB expired an older-than-24-hours draft and preserved a newer capture when asked to clear the older capture key.

Screenshots and disposable session evidence are under ignored `outputs/test-artifacts/user-flow-recovery/`; no test accounts, cookies, databases or media are committed.

## Repeat the manual acceptance

Run `.venv/bin/python tests/browser_flow_server.py` and open `http://localhost:8094/`. This fixture binds loopback only, replaces all AI operations with synthetic results, and deletes temporary data on shutdown. Register only synthetic accounts and use synthetic or non-sensitive test audio. It has three explicit fault controls:

```sh
curl -X POST http://localhost:8094/__test__/expire
curl -X POST http://localhost:8094/__test__/fail
curl -X POST http://localhost:8094/__test__/lose
```

The first expires fixture sessions; the other two affect the next segment upload. These endpoints exist only in the test fixture, never in `server/app.py` or the production container. End-to-end provider content validation has separate unit/integration coverage; the fixture intentionally isolates user-flow behavior.

## Remaining verification boundaries

Real microphone/camera hardware, iOS/Safari/Android, external HTTPS, production disk limits and real provider quality were not revalidated here. Completed drafts require available browser storage and the same origin/browser profile. Browser data deletion and unsaved trailing seconds of an abruptly terminated recording cannot be recovered. Unfinished container compatibility varies by browser; interrupted fragments require review and remain downloadable if upload validation fails.
