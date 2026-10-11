# No Fear Stage pilot

## Working boundaries

- Serve `public/` and the API through `server/app.py`, on the same origin. Root `index.html` and `styles.css` are imported legacy copies, not the maintained application.
- Keep native JavaScript/CSS. Preserve explicitly local anonymous practice; real reports and durable history require an account.
- API and module boundaries are in `docs/api-contract.md`. Private recordings are outside `public/`; every practice, job and media request must enforce ownership on the server.
- SQLite WAL, private media and the durable worker form a single-host pilot. Run exactly one application process/worker; startup queue recovery is not safe across simultaneous application instances sharing a database.
- Do not simulate authentication, store passwords/session tokens in localStorage, or expose provider credentials in frontend source. Never commit `.env`, private data, logs or temporary test artifacts.
- Provider output is untrusted text. Verify transcript quotations; derive numerical metrics locally. Do not claim voice, gesture or psychological analysis from a text pipeline.

## Validation and operations

- Use Python 3.12+ in `.venv`; `pytest -q` covers API isolation, jobs and provider validation. Check both frontend modules with Node syntax checks, and verify the actual UI in a browser.
- `scripts/run-local.sh` starts the maintained app. Environment variables are not automatically read from `.env`; export them privately before starting.
- Offline backup/restore is in `scripts/backup.py`. Stop the application before backup, verify checksums, and restore into a new location.
- Load tests of ordinary authenticated endpoints do not prove LLM generation capacity. Label real provider calls separately; unknown billing/token counts stay unknown.
- README and UI are Russian; technical documentation is English. Update relevant documentation when changing API or operational behavior.
- Review changes and commit only relevant files. Use branch `frentend`; do not modify remote `main`. Report local, pushed and externally deployed status separately.
