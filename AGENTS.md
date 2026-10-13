# No Fear Stage pilot

## Working boundaries

- Serve `public/` and the API through `server/app.py`, on the same origin. Root `index.html` and `styles.css` are imported legacy copies, not the maintained application.
- Keep native JavaScript/CSS. Anonymous visitors can record before registration. Full AI reports and server history require an account; import the same recording after authentication instead of restarting practice.
- API and module boundaries are in `docs/api-contract.md`. Private recordings are outside `public/`; every practice, job and media request must enforce ownership on the server.
- SQLite WAL, private media and durable queues form a single-host pilot. Run exactly one application process, with one final-job worker and one incremental-ASR worker; startup queue recovery is not safe across simultaneous application instances sharing a database.
- Do not simulate authentication, store passwords/session tokens in localStorage, or expose provider credentials in frontend source. Never commit `.env`, private data, logs or temporary test artifacts.
- Provider output is untrusted text. Verify transcript quotations; derive numerical metrics locally. Do not claim voice, gesture or psychological analysis from a text pipeline.

## Interface and Russian copy

- Apply these rules across every route and shared component, including generated report titles.
- Use complete, connected headings and prose. Do not force line breaks or split one idea into a sequence of tiny sentences. Let text wrap naturally. Headings never end in a period; preserve question marks and meaningful source text outside headings.
- CTA labels contain no decorative arrows. Do not use decorative online-status dots or padded numbering such as `01`, `02`, `03`. Use ordinary numbering only for a meaningful sequence.
- Native single-select chevrons need an explicit inner right gutter and reserved text space. Keep keyboard interaction and native accessibility; do not replace selects with decorative divs.
- Typography uses shared CSS tokens: distinguish page titles, section headings, field labels, input values and hints by size, weight, spacing and contrast. Keep optional-field labels inline and attach hints to their field group.
- Main prose, questions and report content use `--text-body` (16px minimum); compact metadata uses `--text-small`. Keep the green accent for the main action and use neutral surfaces plus explicit checked/focus indicators for static content and choices. Hero result cards join document flow below 900px so longer copy cannot cover faces. Short, narrow meeting viewports use the stacked chat layout for zoom reflow.
- Visuals must suit a contemporary Russian audience and recognizable local settings. Do not infer or claim real people's nationality from appearance. Record generated-asset provenance; never present an illustration as a real user or testimonial.
- Keep imagery bright, naturally colored and welcoming. Do not equate Russian context with gloomy or desaturated photography. Avoid copy overlays across faces; landing cards must convey a specific product benefit or a clearly labeled example.

- Recording is an immersive meeting scene, with one device toolbar and optional self-video. Keep speech advice and audience labels off this screen. Camera captures video plus audio; AI receives the audio track and transcript, not visual analysis. Speech auto-saves on recorder completion (manual or timer). Upload, retry and question generation stay in the same meeting DOM; never replace the audience/self-video for these transitions. Failed upload retains the Blob and offers retry. Guests save locally and see the authentication continuation in this meeting chat. Answers still use their existing review step. Questions map to confirmed saved answers.
- Logged-in speech also captures independent 15-second mono 16 kHz PCM WAV chunks through an AudioWorklet. Never upload MediaRecorder timeslice blobs as standalone audio, transcribe the microphone check, or send guest audio before authentication. Keep full recording as the fallback; reuse live transcripts only for the bound capture session with complete indices, offsets, final manifest and matching duration. Provider question objects must select server-issued speech evidence IDs; public questions remain strings.

## Validation and operations

- Use Python 3.12+ in `.venv`; `pytest -q` covers API isolation, jobs and provider validation. Check both frontend modules with Node syntax checks, and verify the actual UI in a browser.
- The deterministic browser acceptance fixture is `tests/browser_flow_server.py`: loopback port 8094, temporary data, synthetic provider functions and test-only fault endpoints. Never include its fault routes in the maintained app or production container.
- `scripts/run-local.sh` starts the maintained app. Environment variables are not automatically read from `.env`; export them privately before starting.
- Offline backup/restore is in `scripts/backup.py`. Stop the application before backup, verify checksums, and restore into a new location.
- Load tests of ordinary authenticated endpoints do not prove LLM generation capacity. Label real provider calls separately; unknown billing/token counts stay unknown.
- The 12 October 2026 gateway audit found no declared `spend` currency and zero Whisper expense despite nonzero audio seconds. Reconcile request logs with the asynchronously updated key counter; do not equate its audio meter with free upstream service or RUB settlement. Evidence and limitations are in `docs/observability-cost.md`.
- Guest and account recording drafts use the existing IndexedDB store on the browser origin, with a 24-hour restore window. Account drafts are scoped to owner/practice/stage; a bound guest import must not resume in a different account. Keep credentials out of this store. Preserve original Blobs and stable capture keys across login/reload; retire a draft only after matching server acknowledgement or explicit discard. Completed media is saved before upload/review; interrupted aggregate MediaRecorder checkpoints require review and must never be treated as standalone timeslice audio. Import retries use an account-scoped `idempotency_key`; segment retries use `client_key` plus the original-byte hash. Keep unconfirmed answers on their review step and failed jobs on explicit retry.
- First-user onboarding starts with one speech recording of up to a minute, followed by three audience questions in a meeting chat. Users can disable questions in custom setup. Saving continues to the next question or a durable analysis job; a failed job start must retain the saved recording and offer continuation. Repeat practices use the selected recommendation, and choosing a repeat or another topic completes onboarding.
- README and UI are Russian; technical documentation is English. Update relevant documentation when changing API or operational behavior.
- Review changes and commit only relevant files. Use branch `frentend`; do not modify remote `main`. Report local, pushed and externally deployed status separately.
