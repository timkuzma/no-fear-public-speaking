# Continuous meeting acceptance

The original verification and publication below describe revision `83117ec`. The optimistic answer update supersedes its three-second countdown and blocking upload transitions; current behavior is defined in `docs/api-contract.md`.

The meeting now follows one ready action, speech, sequential questions and the final report. Each completed answer uses the same automatic draft/upload path as speech. Normal answers no longer open a review page or expose playback/download controls in the meeting. The final report retains all recordings and exports.

Automatic answer capture is bound to the current route and explicit in-memory ready session. Each question becomes visible before a three-second countdown starts its answer recorder. Mic/camera tracks survive saving and question generation; navigation, authentication loss, mute and unavailable devices cancel scheduled recording. Reopening a practice requires a new ready action. Manual completion and the existing time limit both save the answer automatically. Interrupted, missing or conflicting drafts retain explicit recovery; this is separate from normal completion.

## Verification on 13 October 2026

- The full Python suite passed: 169 tests. The only warning is the existing Starlette/httpx deprecation.
- JavaScript syntax checks passed for the application, live capture and synthetic-media fixture.
- The recording harness covers all three answers, reuse of identical audio/video tracks, automatic timer completion, duplicate-render protection, upload failure/retry, original draft retention, interrupted recorder recovery and cancellation on leave/mute/auth loss.
- An actual browser completed registration, one speech and three answers, then reached the report on the separate loopback fixture at port 8095. The fixture used generated audio/video with native MediaRecorder and AudioWorklet, and synthetic server analysis; it did not open physical devices or contact an AI provider.
- Browser device-request counters remained one microphone request and one camera request throughout the meeting. During answers there were zero playback controls and zero download links; the report contained four recording players and four media download links. No browser errors/warnings were captured.
- Screenshot evidence is ignored local output under `outputs/test-artifacts/continuous-meeting/`.

Physical microphone/device behavior and the usefulness of real AI feedback remain user pilot checks. This UI acceptance does not measure semantic report quality.


## Production publication

Source revision `83117ec69ca6d88b92cb680ac69b04e21dc2cb51` was published to the existing No Fear Stage HTTPS host. Image `sha256:d7d38054af3e7ff57f6ecbe1b438c213bac425fe2ac7c545b6837b34c9cc16da` inherits the currently published backend and changes only `public/`; no database or provider contract changed.

The production controller returned success with `verified_backup: true` and no rollback. External HTTPS checks confirmed that `app.js` and the entry HTML exactly match this revision. Readiness confirmed writable storage, both live workers, configured provider and maintenance disabled. The previous production image is retained for code-only rollback. No real provider call or physical recording was made during this publication; no Git push was performed.


## Optimistic answer update — 13 October 2026

Completed answers now advance the meeting immediately. Their Blobs are retained in an owner/practice-scoped in-memory queue while IndexedDB persistence and background uploads run alongside capture of the next answer. Requests preserve the original bytes/client key and drain in stage order. Local stage placeholders are not remote media acknowledgements; report admission waits for every answer to be accepted. Background acceptance changes chat metadata without replacing the scene, preview, controls or active timer. Speech upload and question admission also run alongside local draft persistence/cleanup.

The three-second countdown is removed. A new or reopened meeting still requires its explicit ready action, and a muted/unavailable microphone prevents automatic continuation. Network failure leaves the next answer running; completed answers receive one recovery action at the end. Reauthentication preserves queued answers, and a different account cannot upload them. Reload restores all retained drafts in ascending stage order.

Validation: the 180-test Python suite and native JavaScript syntax checks passed. The recording harness additionally covers deferred local writes and uploads, immediate next-question capture, acknowledgement during active capture, report gating, retry/409 reconciliation, three-draft reload and explicit reauthentication with ownership isolation. An actual browser with generated media and native MediaRecorder/AudioWorklet reached all three questions and the final report on the isolated port-8095 fixture. With a ten-second synthetic upload delay, the third question was recording while earlier answers were still awaiting acceptance. Mic/camera request counts remained one each; no playback/download controls appeared during answers, and the final report contained four players/download links. Browser error/warning logs were empty. Screenshot evidence is ignored output under `outputs/test-artifacts/optimistic-meeting/`.

This verifies interaction and persistence behavior with synthetic AI; physical-device recording and semantic feedback quality remain the user's pilot checks.
