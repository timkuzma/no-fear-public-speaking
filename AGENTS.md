# No Fear Stage pilot

## Working boundaries

- Serve `public/` and the API through `server/app.py`, on the same origin. Root `index.html` and `styles.css` are imported legacy copies, not the maintained application.
- Keep native JavaScript/CSS. Anonymous visitors can record before registration. Full AI reports and server history require an account; import the same recording after authentication instead of restarting practice.
- API and module boundaries are in `docs/api-contract.md`. Private recordings are outside `public/`; every practice, job and media request must enforce ownership on the server.
- SQLite WAL, private media and the durable worker form a single-host pilot. Run exactly one application process/worker; startup queue recovery is not safe across simultaneous application instances sharing a database.
- Do not simulate authentication, store passwords/session tokens in localStorage, or expose provider credentials in frontend source. Never commit `.env`, private data, logs or temporary test artifacts.
- Provider output is untrusted text. Verify transcript quotations; derive numerical metrics locally. Do not claim voice, gesture or psychological analysis from a text pipeline.

## Interface and Russian copy

- Apply these rules across every route and shared component, including generated report titles.
- Use complete, connected headings and prose. Do not force line breaks or split one idea into a sequence of tiny sentences. Let text wrap naturally. Headings never end in a period; preserve question marks and meaningful source text outside headings.
- CTA labels contain no decorative arrows. Do not use decorative online-status dots or padded numbering such as `01`, `02`, `03`. Use ordinary numbering only for a meaningful sequence.
- Native single-select chevrons need an explicit inner right gutter and reserved text space. Keep keyboard interaction and native accessibility; do not replace selects with decorative divs.
- Typography uses shared CSS tokens: distinguish page titles, section headings, field labels, input values and hints by size, weight, spacing and contrast. Keep optional-field labels inline and attach hints to their field group.
- Visuals must suit a contemporary Russian audience and recognizable local settings. Do not infer or claim real people's nationality from appearance. Record generated-asset provenance; never present an illustration as a real user or testimonial.
- Keep imagery bright, naturally colored and welcoming. Do not equate Russian context with gloomy or desaturated photography. Avoid copy overlays across faces; landing cards must convey a specific product benefit or a clearly labeled example.

- Recording is an immersive meeting scene, with one device toolbar and optional self-video. Keep speech advice and audience labels off this screen. Camera captures video plus audio; AI receives the audio track and transcript, not visual analysis. Speech auto-saves on recorder completion (manual or timer). Upload, retry and question generation stay in the same meeting DOM; never replace the audience/self-video for these transitions. Failed upload retains the Blob and offers retry. Guests save locally and see the authentication continuation in this meeting chat. Answers still use their existing review step. Questions map to confirmed saved answers.

## Validation and operations

- Use Python 3.12+ in `.venv`; `pytest -q` covers API isolation, jobs and provider validation. Check both frontend modules with Node syntax checks, and verify the actual UI in a browser.
- `scripts/run-local.sh` starts the maintained app. Environment variables are not automatically read from `.env`; export them privately before starting.
- Offline backup/restore is in `scripts/backup.py`. Stop the application before backup, verify checksums, and restore into a new location.
- Load tests of ordinary authenticated endpoints do not prove LLM generation capacity. Label real provider calls separately; unknown billing/token counts stay unknown.
- Guest audio drafts use IndexedDB on the browser origin, with a 24-hour restore window. Keep credentials out of this store. Failed authentication/import must preserve the draft; clear it only after a confirmed server recording. Import retries use an account-scoped `idempotency_key` to avoid duplicate practices.
- First-user onboarding starts with one speech recording of up to a minute, followed by three audience questions in a meeting chat. Users can disable questions in custom setup. Saving continues to the next question or a durable analysis job; a failed job start must retain the saved recording and offer continuation. Repeat practices use the selected recommendation, and choosing a repeat or another topic completes onboarding.
- README and UI are Russian; technical documentation is English. Update relevant documentation when changing API or operational behavior.
- Review changes and commit only relevant files. Use branch `frentend`; do not modify remote `main`. Report local, pushed and externally deployed status separately.
