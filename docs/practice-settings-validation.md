# Practice setup and product-copy validation

The main setup exposes optional user topic and a numeric speech duration for both first-time and returning users. It accepts any duration from 0.5 to 10 minutes, including fractions. Questions are additional time: the speech timer no longer silently cuts ten minutes to seven. The overall saved-media cap is now 780 seconds, while individual decoded media remains bounded by 600 seconds and existing provider work caps remain unchanged.

Topic already reaches the existing questions/report context. The UI now exposes it directly; it remains weak user intent, never an invented criterion or evidence of what was said. Prompt versions, evidence validation and withheld rewrite policy are unchanged.

The copy audit covers landing, account entry/recovery, setup, history, meeting, waiting/error/retry states, report reading/export and legacy recording recovery. Progress describes questions or reports becoming ready. Known API errors use plain recovery guidance; legacy application-owned report labels are translated for display/export. User speech, quotations and substantive findings are preserved. Validation errors expose only safe labels of failing fields; registration no longer mentions speech duration.

## Checks on 13 October 2026

- Full suite: 180 tests passed; existing Starlette/httpx deprecation warning only.
- Registration checks cover invalid password, email and name independently, with no account creation or unrelated training messages.
- API checks save 0.5, 1, 3, 4.25, 5 and 10 minutes and the exact chosen topic. Measured-duration fixtures allow a ten-minute speech plus three one-minute answers, reject an overlong final answer and preserve earlier recordings. Real decoding has separate existing media tests.
- Mocked provider requests confirm the exact topic reaches both questions and report calls, with no imposed criteria. These are structural checks, not semantic-quality scores.
- An actual browser registered a synthetic account, entered a topic and 4.25 minutes, and saw the exact topic with a 04:15 speech timer. Native MediaRecorder/AudioWorklet recorded generated audio/video and completed all three answers into a report. Device-request counts stayed one microphone and one camera request; two answers completed through the timer without extra clicks.
- At 390px the setup stacked into one column, both fields remained visible and document width matched the viewport. No browser errors were observed. Screenshot evidence is ignored output under `outputs/test-artifacts/practice-settings/`.

No real provider requests or physical-device captures were made for these checks. Useful coaching and physical-device behavior remain the user's production pilot checks.

## Production publication

Source `efc9ce4bf6b77f9d2fae304e32de1bcb564c4243` was published to the existing No Fear Stage HTTPS host as image `sha256:662e3019683bb18797dae991692552d5f889073c94e8ac0aa8637f4cbac40d01`. The controller verified the pre-release backup/restore check and promoted without rollback. The previous image remains available; database structure and stored recordings are unchanged.

External HTTPS checks matched the entry HTML, application, API client, draft module and stylesheet bytes. Readiness confirmed writable storage, both workers alive and maintenance disabled. A deliberately invalid registration returned HTTP 422 with only the password field/message and no mention of practice time; invalid input cannot create an account. No Git push was made.
