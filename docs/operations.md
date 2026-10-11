# Pilot operations

## Local and production modes

Run with Python 3.12+ and the locked dependencies. `scripts/run-local.sh` binds loopback by default. Export configuration into the process environment; no `.env` auto-loading. `LLM_API_KEY` is backend-only. Never paste it into UI configuration, command output, Git, screenshots or operational reports.

Production requires `APP_ENV=production`, exact HTTPS `APP_ORIGIN`, private `LLM_API_KEY`, provider model settings and an independently generated `OPERATOR_TOKEN`. `REQUIRE_INVITE=0` does not disable production invitations. Keep `DATA_DIR` on persistent writable storage; never use an ephemeral filesystem. Run exactly one Uvicorn worker and one container instance. Trust proxy forwarding only from your actual reverse proxy.

The Dockerfile is a deployment artifact; a local successful test is not evidence that this container has been built or deployed. Put the container behind an HTTPS reverse proxy, forward one origin, cap upload bodies/timeouts and provide restart policy and disk monitoring. Do not expose the application port directly on the public Internet. The default media limit is 32 MiB and total practice audio limit is ten minutes.

Issue one-use invitations:

```sh
.venv/bin/python -m server.cli invite --uses 1 --hours 72
```

After checking identity with the participant, issue a short-lived recovery code:

```sh
.venv/bin/python -m server.cli reset participant@example.com --minutes 30
```

Share codes privately. The CLI intentionally prints the new code for the operator; do not redirect it into application logs or commit it. Supply the same `DATA_DIR` to the server and CLI. The UI reset form accepts the code and a new password.

## Backups and rollback

Stop the application first so private media cannot be deleted or changed during the snapshot. Use a new destination each time:

```sh
.venv/bin/python scripts/backup.py backup data backups/2026-10-11 --offline
.venv/bin/python scripts/backup.py restore backups/2026-10-11 data-restored --offline
```

The backup uses SQLite's backup API, copies referenced private files, checks database integrity and saves SHA-256 checksums. Restore refuses an existing destination and checks the manifest. A backup contains account hashes and private speech: restrict permissions, encrypt remote storage, and keep it outside Git. Restored sessions and queued jobs remain in the database; use the restored data directory only after stopping the original server.

Rollback: stop the application, switch back to the previous code/dependency lock and a compatible verified backup if necessary, then start one instance and check login/history/private playback. This release uses additive schema initialization; it has no automatic destructive migration rollback.

## External release gate

Before inviting external participants, set up a reachable HTTPS hostname, persistent volume, provider credentials and quotas, operator access, support contact, consent/retention wording, and the participant eligibility decision. Validate the entire user flow at the actual external origin, including microphone permission on desktop and mobile. Automated email verification/recovery is intentionally deferred while invitations and operator-assisted recovery are in use.

The supplied aggregator's actual billing tariffs and any zero-retention guarantees remain unverified. Configure those with the provider before making cost or privacy promises. Manual deletion is supported; do not advertise automatic time-based retention unless it is implemented and tested.
