# Production mechanism acceptance, 13 October 2026

## Implemented boundary

The maintained single-host pilot now has durable rolling AI work caps and operator pause, bounded queues/timeouts, writable-storage/worker readiness, private operational status, local and independent external alert probes, verified encrypted backups/retention, and an immutable-image release controller with pre-activation recovery and data-preserving code rollback. The production runbook is `docs/operations.md`; proxy and timer assets are in `deploy/`.

## Checks

- Python 3.12 `.venv`: **121 tests passed**, including existing authentication, recording recovery, ownership, jobs, live ASR and provider validation. New tests exercise concurrent budget reservation, unknown/retried call accounting, rolling account/minute limits, failed queue admission and replay quotas, whole-job timeout preserving media, single-instance/offline leases, real worker cancellation/readiness, maintenance refusing new work, backup tampering/symlinks, scoped local retention, preflight failure and service resumption after copy failure.
- Five maintained frontend modules pass `node --check`: `app.js`, `api.js`, `guest-draft.js`, `live-audio.js`, `audio-capture-worklet.js`. No frontend behavior was changed in this increment.
- Real Docker acceptance built separate immutable previous/current fixtures and a candidate that raises at startup. Disposable synthetic accounts, PCM audio and a reserved provider-attempt row were used; no external AI requests were sent. The rehearsal verified nonroot/read-only/capability/resource/loopback settings, maintenance gating before activation, deployment and manual rollback preserving recording hashes/session/history/attempt ledger, durable operator pause, automatic recovery from the faulty candidate, encrypted full repository check/exact snapshot restore, local-repository offsite honesty, rejection of a second application instance, interrupted-operation resume and disaster restore into a new root.
- Alert tests cover three-check incident confirmation, deduplication, recovery notification, bounded webhook delivery retry, no operator credential on the external probe and no private details in output. No real recipient was contacted.
- Nginx `nginx -t` and `systemd-analyze verify` passed in a disposable Linux container. Validation supplied a synthetic certificate, executable-path fixtures and a Docker service stub. These checks validate configuration syntax/unit dependencies, not real DNS/certificates, installed timers or external notification delivery.
- `git diff --check` passed. Private fixtures and command logs remain ignored; no private production data or secrets are included in the source changes.

The test suite emits one existing Starlette/httpx deprecation warning; this is not a test failure. Changing the HTTP testing dependency was outside this increment.

## Reproduce the Docker rehearsal

Build two fixtures with distinct image identities and a deliberately failing candidate:

```sh
docker build --build-arg REVISION=acceptance-previous -t nfs-ops-acceptance:previous .
docker build --build-arg REVISION=acceptance-current -t nfs-ops-acceptance:current .
```

Create a temporary Dockerfile outside tracked source:

```dockerfile
FROM nfs-ops-acceptance:current
CMD ["python", "-c", "raise RuntimeError('synthetic startup failure')"]
```

Build it as `nfs-ops-acceptance:faulty`, then run:

```sh
.venv/bin/python tests/production_docker_acceptance.py \
  --previous-image nfs-ops-acceptance:previous \
  --current-image nfs-ops-acceptance:current \
  --faulty-image nfs-ops-acceptance:faulty
```

The test only manages uniquely named/root-labelled disposable containers, networks and volumes and removes them afterwards. It does not contact the configured provider. Fixture revision differences test the controller's image identity/promotion behavior; they do not establish compatibility with arbitrary historical application versions. Image authors must preserve the documented schema-family and maintenance contract.

On this macOS Docker Desktop, Restic's Go reader returned EIO for source bind mounts while ordinary reads worked. The test stages ONLY its disposable offline source snapshot into a temporary Linux volume before the actual Restic command. Full encrypted restore/check remains real. The production controller has no platform workaround and targets a Linux host with local persistent storage; do not use Docker Desktop as the production host. This rehearsal does not certify a remote object-store provider, Linux-host disk throughput, production TLS or real-provider generation capacity.

## External activation still requires host configuration

No push or external deployment was performed. Supply the actual Linux host/domain/TLS, private provider configuration and its financial limits, offsite repository and separately protected recovery password, HTTPS notification receiver and independent external monitor. Install and inspect the supplied timers/proxy, receive an incident/recovery pair, run and restore an offsite backup, then verify login/private playback/resume/microphone at the real origin before participant access. These are deployment-specific inputs and checks, not simulated successes.

The repository contains working and locally verified mechanisms; monetary cost and upstream transcription billing remain unconfirmed. AI reservations bound work without claiming a currency budget. Recording retention and participant consent/support decisions remain with the operator; telemetry/backup retention does not automatically delete participant recordings.
