# Production operations on one Linux host

## Deployment boundary

Use a Linux host with Docker Engine, Python 3.12+, the locked dependencies and persistent local storage. This release is one application process with two serialized workers, SQLite WAL and private media. It is not a multi-host or multi-replica deployment. The application holds an exclusive instance lease plus a shared data lease; offline backup takes the exclusive data lease. Never access live SQLite from a different kernel (for example macOS while Docker Desktop runs Linux); issue operator commands with `docker exec` instead.

Install the checkout at `/opt/no-fear-stage`; keep `/srv/no-fear-stage` outside Git and restrict it to mode 0700. The controller only manages containers/networks with matching application/root labels. It serializes operations, requires compatible schema labels and resolves application images to immutable SHA-256 IDs. Images carry schema family `1`; compatibility is an explicit release-author assertion, not a migration detector. Change this family and write a migration/restore procedure before any incompatible schema change. Keep current and previous images available; do not prune them.

## Private configuration and first release

```sh
cd /opt/no-fear-stage
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
.venv/bin/python scripts/production.py init --root /srv/no-fear-stage
```

Privately edit `/srv/no-fear-stage/runtime.json` and `secrets.json`, both mode 0600. Runtime settings include exact HTTPS `APP_ORIGIN`, HTTPS `LLM_BASE_URL` without credentials/query/fragment, `LLM_MODEL`, `TRANSCRIPTION_MODEL`, and the limits below. Secrets contain `LLM_API_KEY`, independently generated `OPERATOR_TOKEN`, `RESTIC_PASSWORD`, `RESTIC_REPOSITORY` and optional `ALERT_WEBHOOK_URL`. Supported object-storage credential names are listed in `BACKUP_ENV` in the controller. Do not paste any of these files or command environments into reports. `.env` is not loaded automatically.

The bootstrap repository value `local` is only for rehearsal. Production requires a separately hosted encrypted repository (for example an S3 endpoint supported by Restic), a private HTTPS notification receiver and an independent external monitor. Keep the Restic password, repository access and nonsecret release/image/configuration information in separate protected recovery storage; losing the only repository password makes recovery impossible. Use a dedicated repository/prefix and credentials for this deployment. Restic verifies TLS normally; insecure TLS options are not enabled. Do not put credentials in provider URLs.

```sh
docker build --build-arg REVISION="$(git rev-parse HEAD)" -t no-fear-stage:candidate .
.venv/bin/python scripts/production.py deploy --root /srv/no-fear-stage --image no-fear-stage:candidate
.venv/bin/python scripts/production.py init-backup --root /srv/no-fear-stage
.venv/bin/python scripts/production.py backup --root /srv/no-fear-stage
```

Never re-run `init-backup` against an existing repository. Before first exposure, confirm operator status reports a fresh encrypted restore check and `offsite_configured: true`, and actually receive a test incident/recovery notification. A remote repository URI only indicates configuration; each successful backup/check/restore supplies the connectivity/integrity evidence. No secret is written into the image or command arguments; Docker administrators can still inspect container environment variables and must be trusted.

The container runs as a nonroot user, with read-only root, all capabilities dropped, `no-new-privileges`, bounded tmpfs, 1 GiB memory, two CPUs, 128 PIDs and 128 concurrent HTTP connections. Logs rotate at 10 MiB × 3. Only `127.0.0.1:9080` is published; proxy trust is restricted to the actual private network gateway and loopback. `deploy/nginx.conf` supplies HTTPS/body/timeout settings and blocks public operator routes. Replace its example hostname and certificate paths, run `nginx -t`, and verify it at the real domain before participants use it. The script does not issue certificates or configure DNS/firewalls.

## Releases, rollback and interruption

A release first completes image/configuration/network preflight. It sets maintenance, rejects business API calls with 503/Retry-After, stops workers and waits for the process to exit. It then copies SQLite and referenced media, verifies integrity/checksums and rehearses a restore. The candidate starts with business traffic and provider workers still paused. Readiness must confirm writable storage, live workers, provider configuration and the exact candidate identity. Only then are current/previous image and nonsecret configuration atomically promoted and maintenance cleared; activation is checked again. This single-host rollout has brief downtime.

If the candidate fails before promotion, the controller stops it, restores the verified pre-release snapshot into a new directory, quarantines failed data, and starts the previous release. A backup failure restarts the previous release with its original data. Failed first installation preserves data in maintenance because no previous image exists. Readiness checks configuration, not upstream provider availability.

```sh
.venv/bin/python scripts/production.py status --root /srv/no-fear-stage
.venv/bin/python scripts/production.py rollback --root /srv/no-fear-stage
.venv/bin/python scripts/production.py resume --root /srv/no-fear-stage
```

Manual rollback switches code and nonsecret settings while retaining CURRENT data, including writes made after deployment. It never silently restores an older database. No automatic restore is allowed after promotion/activation. If the controller or host crashes, `resume` snapshots current data and starts the last committed release; it does not discard later writes. The boot unit performs this operation. Incompatible images are rejected. Failed operation markers remain visible to monitoring until a successful release/backup/resume. If recovery fails, leave maintenance in place, preserve all data/images and investigate privately. Quarantined `failed-data-*` directories require reviewed manual cleanup and count towards disk usage.

## AI and capacity limits

Every actual HTTP provider attempt, including each retry and both workers, reserves resources atomically in SQLite BEFORE transmission. Reservations survive restart, user/practice deletion and deployment. Failed/unknown calls retain reservations; recovery can repeat an upstream call and reserve again. This is a conservative work ceiling, not exactly-once billing or a monetary budget. Input characters bound prompt size; output reserves requested `max_tokens`, not measured completion usage. Configure the provider's own financial/quota limits using verified tariffs separately.

| Setting | Default | Scope |
|---|---:|---|
| `AI_DAILY_ATTEMPTS` | 500 | All calls in rolling 24 hours |
| `AI_USER_DAILY_ATTEMPTS` | 100 | Account calls in rolling 24 hours |
| `AI_REQUESTS_PER_MINUTE` | 30 | All calls in rolling 60 seconds |
| `AI_DAILY_AUDIO_SECONDS` | 18000 | All reserved ASR audio in rolling 24 hours |
| `AI_DAILY_INPUT_CHARS` | 5000000 | All reserved chat input characters in rolling 24 hours |
| `AI_DAILY_OUTPUT_TOKENS` | 300000 | All requested chat output ceilings in rolling 24 hours |
| `AI_MAX_OUTPUT_TOKENS` | 3000 | Per chat call, maximum 3000 |
| `MAX_PENDING_JOBS` / `MAX_PENDING_LIVE_CHUNKS` | 20 / 120 | Global pending + running queue rows |
| `DAILY_JOB_LIMIT` / `DAILY_LIVE_CHUNK_LIMIT` | 20 / 120 | Per-account rolling 24-hour admission |
| `LLM_MAX_ATTEMPTS` / `LLM_TIMEOUT_SECONDS` | 2 / 120 | Per provider operation |
| `JOB_TIMEOUT_SECONDS` / `LIVE_JOB_TIMEOUT_SECONDS` | 900 / 180 | Whole final/live job |
| `MIN_FREE_DISK_BYTES` | 268435456 | Storage readiness and new upload admission |
| `MAX_UPLOAD_BYTES` | 33554432 | Saved recording size |

Invalid/out-of-range limits prevent startup. The exact accepted ranges are in `server/limits.py`. Configure lower provider limits before first use and adjust only from measured workload. `AI_ENABLED=0` disables AI independently of the persistent operator switch.

```sh
.venv/bin/python scripts/production.py pause-ai --root /srv/no-fear-stage
.venv/bin/python scripts/production.py resume-ai --root /srv/no-fear-stage
```

Pause blocks new provider attempts and claims; an already transmitted call can finish. Saved audio, history and private playback remain available. Queue/admission/budget failures retain recordings and offer explicit continuation. Active/completed job replays do not consume another quota. Failed live transcription falls back to the full recording; if the global budget is exhausted, final transcription also waits for budget availability. Whole-job timeouts produce a retryable failed state and preserve audio.

## Monitoring and notification

`GET /api/health` checks the process. Public `GET /api/readiness` checks database/media writes, free space, supervised worker liveness, provider configuration and release identity; it includes maintenance state but may remain ready during candidate validation. It does not send an AI request. Operator-only `GET /api/operator/status` adds queue ages, recent errors/provider failures, rolling budgets, backup and last operation state. `POST /api/operator/ai` uses bearer authorization and origin validation; operator routes are blocked at the public proxy.

```sh
.venv/bin/python scripts/monitor.py --root /srv/no-fear-stage --url http://127.0.0.1:9080
```

Alerts cover unreachable/readiness failure, unavailable disk/workers, queue age >300 seconds, maintenance >600 seconds, at least three errors in 15 minutes, paused AI, budgets >=90%, missing offsite configuration, backups/restore checks older than 26 hours and failed operations. Three consecutive minute checks open an incident; recovery resolves it on the next successful check. Incidents are deduplicated and failed webhook deliveries are persisted/retried (last 20 changes). Only generic incident codes go to the HTTPS receiver; redirects are refused. Without a receiver, JSON logs are the sink and do not notify a person. Exit 0 means no confirmed alert/delivery failure, 1 means alert/failure, 2 means monitor configuration/state failure. Monitor its timer/journal and hook delivery externally as well.

Set up `deploy/systemd/no-fear-stage-monitor.*`, `no-fear-stage-backup.*` and `no-fear-stage-resume.service` on the application host. They assume the paths above and root access to the Docker daemon; they are templates and are not installed by the controller. Review them, install under `/etc/systemd/system`, run `systemctl daemon-reload`, enable the two timers and resume service, and run the backup service once. Check actual timer status/journals and delivery. Backup runs at 02:00 Europe/Moscow with up to five minutes of jitter and missed-run recovery.

Install `no-fear-stage-external-monitor.*` on a SEPARATE host and replace the HTTPS origin. Create `/srv/no-fear-stage-external-monitor` mode 0700; its optional mode-0600 `secrets.json` contains only `ALERT_WEBHOOK_URL`, no application operator/provider credentials. The public-only probe checks readiness and maintenance. This independent watcher is necessary to detect complete application-host failure. Host/disk/repository monitoring outside the application remains the hosting operator's responsibility.

Telemetry is content-free: no request bodies, cookies, speech or provider response text in status/alerts. Provider attempt reservations expire after 48 hours; operational events and usage rows after 90 days; expired sessions/invites/resets are removed hourly. This is telemetry retention only, not automatic recording deletion. Export usage into protected accounting storage before retention if needed.

## Backups, retention and disaster recovery

A scheduled backup briefly enters maintenance, stops the app, captures SQLite plus referenced private media, checks hashes/integrity and rehearses offline restore. The app resumes BEFORE remote encryption/upload/check/restore. Restic is pinned by digest; partial-source or repository errors fail the command and never advance encrypted-success timestamps. Every encrypted backup runs `check --read-data`, restores the exact snapshot, rechecks its manifest and rehearses database/media restore. Retention is scoped by a deployment-specific tag: seven daily, four weekly and six monthly snapshots, followed by prune and another full check. The newest seven local verified copies are kept only after encryption/restore/retention succeeds; failures do not prune local copies. This policy removes older copies, not production recordings. Full repository checks may be expensive as the data grows; monitor timer duration/storage and schedule capacity before growing the pilot.

The maximum intended data-loss window is 24 hours under a successful daily schedule; actual recovery time and host throughput must be measured on the chosen host. A local encrypted repository is not offsite protection and is reported as such. Low disk blocks uploads/readiness; no automatic deletion of participant recordings occurs.

```sh
# Offline local verification/restore, application must be stopped.
.venv/bin/python scripts/backup.py verify /srv/no-fear-stage/backups/SNAPSHOT
.venv/bin/python scripts/backup.py restore /srv/no-fear-stage/backups/SNAPSHOT /srv/recovered-data --offline
# Encrypted recovery: initialize private configuration in a NEW root first.
.venv/bin/python scripts/production.py init --root /srv/no-fear-stage-restored
# Privately supply the original repository/password and compatible runtime settings.
.venv/bin/python scripts/production.py restore-backup --root /srv/no-fear-stage-restored --name no-fear-stage-restored --snapshot-id SNAPSHOT_ID
.venv/bin/python scripts/production.py deploy --root /srv/no-fear-stage-restored --name no-fear-stage-restored --image VERIFIED_COMPATIBLE_IMAGE
```

Restore refuses existing data or a managed container, validates the exact requested snapshot, and never starts the application implicitly. Stop the original deployment before exposing the restored one; do not run two copies of its queue. Keep the original volume/quarantines until private playback, login, history and queue recovery are verified. Do not restore stale data during ordinary code rollback.

## Participant and external release gate

Issue invite/recovery codes inside the running container; the CLI shares the app's kernel and lease:

```sh
docker exec no-fear-stage python -m server.cli invite --uses 1 --hours 72
docker exec no-fear-stage python -m server.cli reset participant@example.com --minutes 30
```

Share codes privately after checking identity; do not put them in service logs. Production always requires invitations. Automated email verification/recovery remains deferred. Before inviting participants, configure the actual host/domain/TLS, provider limits and billing, offsite repository/password recovery, alert receiver and independent monitor, support/consent/recording-retention policy. Verify the complete flow and microphone access at the actual external origin on desktop and mobile. Local Docker acceptance is not an external deployment or real-provider capacity claim.
