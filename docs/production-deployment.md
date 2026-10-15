# Production deployment and migration

## Current deployment, 15 October 2026

- Canonical origin: **https://no-fear-stage.72-56-96-17.nip.io** on `72.56.96.17` (`agency-planner-01`, Ubuntu 26.04 LTS). SSH uses the existing `deploy` account and its server-specific key; root password authentication is disabled.
- Source/controller: `/opt/no-fear-stage`; private configuration, data, verified snapshots and encrypted repository: `/srv/no-fear-stage`. The host controller uses a Python 3.14 venv; at migration the application retained the exact original Python 3.12 image `sha256:20e3b88e4a14b7fe1493df43499669b78212316a7db3dbae648494647bdc8bed` (application revision `7b6c496`). The migration required no application image rebuild, schema change, report regeneration or paid provider call. The subsequent registration release is recorded below.
- The existing Agency Planner Nginx container owns ports 80/443. Its original image, environment, ports, mounts and networks were retained; only the edge was recreated. Every other existing application container retained its identity. Append `/etc/no-fear-stage/agency-planner-edge-no-fear-stage.override.yml` to **all five** pre-existing Compose files on future edge deployments; the running edge labels record the complete list.
- The edge has reserved address `172.24.0.254` on `no-fear-stage-private` (`172.24.0.0/16`). Runtime `TRUSTED_PROXY_IPS` adds only that address; the controller still includes loopback and gateway `172.24.0.1`. The app publishes only `127.0.0.1:9080` and runs exactly one process with its two workers.
- Exact site configuration: `/etc/no-fear-stage/nginx/no-fear-stage.conf.template`. The public research reader remains a separate read-only mount from `/var/www/no-fear-stage-pages`.
- TLS is isolated under `/etc/no-fear-stage/letsencrypt`. The lineage directory remains `live/no-fear-stage.72.56.96.17.nip.io`; its certificate covers both that dotted-IP alias and the canonical hyphenated hostname, and expires on 12 January 2027. HTTP and the dotted HTTPS alias redirect to the canonical origin. Certificate renewal uses `no-fear-stage-certificate.timer`, separate work/log directories and `--no-directory-hooks`; the shared host's global hooks stop its edge for standalone validation and must not run for this site's webroot renewal. The scoped deploy hook restores the existing TLS reader group (981), validates Nginx, then reloads it.

### Open registration release, 15 October 2026

At the user's request, registration no longer requires an invitation in any environment. Auth responses retain `registration_requires_invite: false` for cached clients; legacy environment settings and submitted invite codes have no effect. Password recovery keeps its operator-issued one-use code. Existing invitations remain in the database for rollback compatibility; this release does not migrate or delete data.

Application revision `962bfb6` is deployed as immutable image `sha256:b0d730b8ea4bb0463fc0311e0aea4eddf4314bcfe554f6fb9cd2f21b065217d5`. The image extends the previously active image and replaces only `server/app.py`, `public/app.js` and `public/index.html`; their previous hashes matched the local parent revision before release. The normal controller completed a verified pre-release backup/restore rehearsal, activation and readiness. The previous image remains available for rollback.

Validation passed 259 Python tests, JavaScript syntax checks and the frontend auth regression script. A disposable local browser account registered without a code and reached the first-practice setup. The public production registration form has no code field, `/api/auth/me` reports open registration, public frontend and container backend hashes match the committed source, both workers are alive and maintenance is disabled. Unauthenticated private APIs still return 401 and public operator status returns 404. No production account or provider call was created for this verification. Source commits remain local; no Git push was requested or performed.

### Faster wording editor, 15 October 2026

Application change `38b9eca` is deployed as immutable image `sha256:d675dbf1b938fcf103bab80f16f2832e15ca23333ba5c3ace6d12661c973e4b6`. It extends the open-registration image above and replaces only `server/wording_prompts.py`; the old prompt hash matched its committed source before replacement. Runtime `FEEDBACK_EDITOR_MODEL` now selects `gpt-5.4-mini`; assessment still uses `gpt-5.4` separately. Wording prompt version is `speech-wording-v2`; report/question schemas and prompt versions are unchanged. See the [bounded comparison](wording-editor-comparison.md) for measurements and semantic-review limits.

The normal controller completed the verified offline backup/restore rehearsal, activation and readiness. Before activation there were no active final or incremental jobs. Canonical hashes of every users/practices/segments/jobs row matched across release, preserving all existing reports, transcripts and job results. Previous image/configuration remain available for rollback; the old private runtime configuration is retained on the host. The application's durable ledger includes all evaluation attempts.

Post-deployment HTTPS readiness reports writable storage, both live workers and maintenance disabled. The actual browser rendered the landing; the deployed wording file hash matches source. Three synthetic editor probes through the deployed prompt/validator succeeded at 1.838, 2.022 and 3.665 seconds (questions, short report, extended report), matching the earlier final-prompt checks. No production practice, user report or ASR task was created for this validation. Local checks passed 267 Python tests including frontend regressions/syntax, plus final focused wording/evaluation checks. Source commits remain local; no Git push was requested or performed.

### Compact owner dashboard, 15 October 2026

Application revision `f5f0c0c72e32b8f6d5d813c076530ab04ae4c065` is deployed as immutable image `sha256:2ea3d24797b4b438af31d816b091684c4fbb3a58a2e438df3aa6254304e4bf88`. It extends the faster-editor image above, replacing four public assets and seven server modules, including the new compact analytics calculator. All pre-existing application source hashes matched the expected source baseline; unchanged scripts, dependencies, configuration and the shared edge were retained. The local build tag was verified against the immutable base and the candidate's layer prefix matched it.

The owner interface has only analytics and export pages. It uses a dense KPI strip, daily user chart, compact conversion table and paginated practice/account table. Calculation explainers, definition disclosures and formula tooltips are removed; metric labels and units carry the meaning. Owner exports include CSV, JSON and a combined ZIP. New provider prices are recorded per attempt in unspecified gateway units; missing historical prices stay unknown. Access continues to depend exclusively on the existing analytics owner membership.

The normal controller completed a verified pre-release backup and full offline restore rehearsal (snapshot `1792077869638449834-af5511`), then readiness and activation. Before release there were no pending/running final or incremental jobs. Canonical row hashes of eleven business tables and all 20 referenced media files matched the pre-release snapshot after activation: 7 users, 10 practices, 20 saved segments and 18 jobs were preserved, including existing results and transcripts. All unrelated container identities remained unchanged. The previous immutable image remains the rollback target; schema family is unchanged.

Validation passed 273 Python tests, JavaScript syntax checks and local browser checks of the authenticated dashboard without explanations. After publication, all four public asset hashes and all eleven deployed module hashes matched source. Public HTTPS health/readiness returned 200, writable storage and both workers were healthy, and maintenance was disabled. Unauthenticated analytics/account/export APIs returned 401, public operator status returned 404, and the independent research page remained available. A read-only calculation inside the running container returned the compact metrics from real retained data. The actual production browser correctly required owner sign-in; no session was fabricated and no account/password or provider call was created for verification. Source commits remain local; no Git push was requested or performed.

### Question editor compatibility fix, 15 October 2026

Application revision `54f6b3a` is deployed as immutable image `sha256:a0cd4e405dcf5e003bbb82611532d2f728e43dbf4e4b08c1cb1f94ee803e82d7`, extending the compact-analytics image above. Only `server/ai.py`, `public/app.js`, `public/index.html` and the new audience JPEG differ; previous replaced-file hashes matched source before the build. The editor may echo exact read-only source/cap inputs without failing publication; altered values still fail. Question errors now name questions. See [incident evidence and limits](question-wording-incident.md).

The normal controller completed verified backup/restore rehearsal (snapshot `1792078209070945881-88acff`), activation and readiness. Both queues were idle beforehand. Hashes of every users/practices/segments/jobs row and all 20 media files match the pre-release snapshot: 7 users, 10 practices, 20 segments and 18 jobs are preserved. The four deployed source hashes match the commit. Settings, prompt versions, schemas and existing reports remain unchanged; failed user jobs were not automatically restarted.

Validation passed 279 Python tests, frontend syntax checks, offline replay of both captured editor responses and a local synthetic browser recording-to-question flow. Public HTTPS readiness confirms both workers, writable storage and maintenance disabled. The smaller JPEG returned 200 with its complete 320,773 bytes in 7.171 seconds; the production landing rendered in the browser. Private practices still return 401 and public operator status 404. The investigation used four durably accounted text requests and zero ASR; deployment validation made no further provider calls. Source commits remain local; no Git push was requested or performed.

### Visible LLM expenses and ledger reconciliation, 15 October 2026

Application revisions `83dda0a` and `b84195d` are deployed as immutable image
`sha256:46f51b7764b429f75615e8dc0ee0915bd623dff5c43e8c185c2bba30796a36b9`.
The first image extended the question-editor release above and replaced eight
server/public files; the final image adjusts only the ledger network deadline.
Both verified base-layer prefixes and source baselines before building. All 46
tracked server/public file hashes now match source, including the question-editor
fix and audience asset. No dependencies, schema, runtime settings or shared edge
were changed.

The expense row now shows known sums and per-practice/per-user means with `≥`
when some prices are missing. Practice rows use the same convention. Production
owner reads reconcile the configured key's GET-only billing ledger through unique
request IDs or conservative attempt intervals/model/tokens. The measured ledger
response was 4.275 seconds / 4.07 MB, so the final bounded network deadline is six
seconds; failed refreshes retain known prices. Accounting makes no generation or
recognition requests. Currency remains unspecified gateway units.

The first successful refresh increased the known subtotal from 12.694541335 to
38.189629513 gateway units and priced coverage from 4/118 to 76/118 attempts;
five of nine practices with provider work were fully priced. The remaining prices
stay unknown. These are point-in-time observations during continued participant
activity, not a frozen financial settlement.

Both controller releases completed verified offline backup/restore rehearsals,
readiness and activation with idle queues beforehand. Snapshots are
`1792084944809484099-923d74` and `1792085074068736927-78d91d`. Every pre-release row
in eleven business tables remained present with identical content; all 94 media
files in the first snapshot retained their hashes. Participants subsequently added
accounts, practices and usage normally. All 15 unrelated running containers retained
their identities. Current data must be preserved on any code rollback.

Validation passed 287 Python tests, frontend syntax checks and a synthetic owner
browser check of complete/partial costs. Focused reconciliation tests passed again
after the measured timeout adjustment. External HTTPS health/readiness returned 200,
with writable storage, both workers alive and maintenance disabled; three public
asset hashes match source. Unauthenticated report/account/export requests return
401, public operator status returns 404, and the independent research page returns
200. No production authentication was fabricated or account credential changed.
Source commits remain local; no Git push was requested or performed.

### Local recording-copy recovery, 15 October 2026

Application revision `fb62dfe` is deployed as immutable image `sha256:654317a9994a7c26962114146b5b3623b2a401581eccbe81a5678ab8937c3515`, extending the expense-reconciliation image above. Only `public/app.js`, `public/guest-draft.js` and `public/index.html` changed; all previous file hashes matched committed source before the build. Runtime settings, providers, schemas and media validation remain unchanged.

The authenticated `/#/recording-copies` view reads owner-scoped local drafts without retrying uploads or deleting entries. It can be opened separately while an original meeting remains open. Failed answer queues identify the failed stage and offer original Blob downloads. See [incident evidence and recovery limits](recording-save-incident.md): this release supplies diagnosis/recovery access, not a confirmed Safari codec fix or proof that rejected recordings can be repaired.

Both queues were idle before the normal controller completed its verified offline backup/restore rehearsal, readiness and activation. Canonical users/practices/segments/jobs row hashes and all 47 referenced media-file hashes match across deployment. Public source hashes match all three local assets. HTTPS readiness confirms writable storage, both workers and maintenance disabled; private practices return 401 and public operator status returns 404. A production browser required sign-in for the copy route. Local checks passed 287 Python tests and final focused frontend auth/recording/syntax checks; the separate browser fixture on port 8095 rendered the authenticated copy view. No user credentials, real recording copies or new provider calls were used for validation. Source commits remain local; no Git push was requested or performed.

### Provider-reported LLM tokens, 15 October 2026

Application revision `ab16699` is deployed as immutable image
`sha256:b572bf72006dde48f1494a9a195ad709d489472bf43ace7f06fb13db1e7aad71`,
extending the recording-copy recovery release. Only `public/admin-analytics.js`,
`public/app.js`, `public/index.html`, `server/analytics_api.py` and
`server/analytics_overview.py` changed. All 46 tracked server/public source hashes
match the running image; its verified base layers, dependencies, runtime settings,
schema and shared edge remain intact.

The dashboard and current owner exports now show text LLM tokens instead of
unspecified accounting units. They include input/output consumption, retries and
wording calls, deduplicate durable attempt IDs and exclude audio transcription.
Missing counts retain partial `≥` values. Historical monetary journal facts and
legacy report accounting fields remain available; opening analytics no longer
depends on a billing GET. Live key/model metadata still does not declare a billing
currency for any selected model, so no unverified conversion to RUB was applied.

The controller completed verified backup/restore rehearsal (snapshot
`1792088382035995354-54b061`), readiness and activation with idle queues beforehand.
Participant activity continued afterward: an existing practice received a report
and a new practice/job appeared; earlier job rows retained their content. No
generation, recognition, practice refresh or production authentication was invoked
for verification. Calculating the current metrics read the database in read-only
mode and returned 281,120 known tokens (262,406 input / 18,714 output), reported for
59 of 61 text calls at that instant. These counts can increase with real activity.

Validation passed 291 Python tests, frontend syntax checks and the synthetic owner
browser check of complete/partial token values. Export tests cover filtered totals,
CSV/JSON units, privacy and absence of gateway units. External HTTPS health/readiness
returned 200 with both workers, writable storage and maintenance disabled; all three
public asset hashes match source. Private analytics/practice/export requests return
401, public operator status returns 404, and the research reader returns 200.
GitHub publication uses the `github` remote and explicit `HEAD:main` refspec.

### Password-protected aggregate link, 15 October 2026

Application revision `3ed08bb` is deployed as immutable image
`sha256:2186181bd5dc867a10cc8bd8f565719ba53e3ec5a9d3fa1906e9c5f97846a3c6`,
extending the token-dashboard release. Eight public/server files changed, including
the dedicated viewer API/UI and stdin-only operator configuration command. All 48
tracked server/public source hashes and all four published asset hashes match.
Dependencies, schema family, provider settings and shared edge were unchanged.

The user-authorized link is `/#/analytics`. A generated password was configured
through the running container's CLI using stdin; plaintext was neither committed
nor placed in frontend code, command arguments, URLs or logs. Only its Argon2 hash
is stored. The viewer exposes allowlisted aggregate metrics with date filters;
it does not authorize owner APIs, account/practice tables, exports, media or report
content. Independent opaque sessions expire after eight hours and are revoked by
logout, password rotation or disabling access. Existing owner access is unchanged.

The controller completed verified offline backup/restore rehearsal (snapshot
`1792096262303706818-e029bf`), readiness and activation with idle queues beforehand.
Every prior row in eight immutable business tables, including owner membership,
was preserved; all 355 snapshotted media files retained their hashes. All 15
unrelated running containers retained their identities. Password setup changed
only namespaced viewer configuration/session rows in existing operational state.

Validation passed 297 Python tests, final focused analytics/access checks and
frontend syntax checks. The synthetic browser verified invalid/valid password,
date filtering, reload, logout and the separate owner table/export interface.
The actual production browser rendered the password form. External HTTPS checks
verified password login, Secure/HttpOnly/SameSite cookie attributes, aggregate
response privacy/no-store, logout and rejection of a copied revoked cookie.
Viewer credentials still receive 401 from owner report/account/practice/export
and participant APIs; invalid extra filters receive 422. Health/readiness returned
200 with both workers, writable storage and maintenance disabled; operator status
remains 404 and the independent research reader remains 200. No account login,
provider generation, ASR or report refresh was invoked for release verification.

### Migration evidence and recovery boundary

The original application had no queued/running final or incremental jobs when it entered maintenance and stopped. A verified offline snapshot and complete restore rehearsal preceded transport. The destination verified every media checksum, restored into a new directory and matched the canonical content hashes of **every database table before activation**. At cutover it contained **3 users, 7 practices, 14 saved media segments, 13 jobs, 3 reports and one analytics owner**. Existing report versions, questions, transcripts, sessions, accounting and analytics data were retained. Private invitation files were transferred separately without exposing their codes.

The destination passed public HTTPS health/readiness with writable storage, both workers alive and maintenance disabled. The landing rendered in the actual browser; the research reader returned 200. Private practice APIs returned 401 and operator routes 404. Local regression validation passed 256 tests plus JavaScript syntax checks. No authenticated user password was requested or changed. Users must sign in at the new browser origin; origin-local IndexedDB drafts do not move with the server database.

The daily backup and minute monitor timers are active; committed-release recovery is enabled at boot. A manual run of `no-fear-stage-backup.service` completed successfully, including Restic content verification and an encrypted restore rehearsal (snapshot `7ffcb14c6d96298db11563ef78c43375e81bf58098a2b06257152d2f74ad4c0c`). Local encrypted protection remains `offsite_configured:false`; external receiver/monitor configuration was not added by this migration.

The original host `157.22.172.204` remains a **frozen migration source**, not a second active application. Its container is stopped with restart disabled; its boot recovery and application backup/monitor timers are disabled. Its exact Nginx virtual host redirects to the new canonical origin, including requests arriving through the existing port-10443 fallback. Original data, images, backup history and proxy configuration backups remain preserved there. Source manifest: `/srv/no-fear-stage/migration-to-72-56-96-17.json`; destination import verification: `/srv/no-fear-stage/migration-source-verification.json`.

Do not resume the frozen source after the destination has accepted writes. A return migration must first stop destination writes and transfer a newly verified snapshot back; restarting the old database would discard newer activity. The observations below describe the historical original deployment and ingress fallback, not the current application host.

## Original deployment, 13 October 2026

- Public origin: `https://no-fear-stage.157.22.172.204.nip.io`.
- Host: Ubuntu 24.04 at `157.22.172.204`; source `/opt/no-fear-stage`, private configuration/data/backups `/srv/no-fear-stage`.
- Initial accepted application source revision: `6ed59a4`; immutable image ID `sha256:512b5572b2fb0cf7602836a8cf54e13d9f753f20ed4f05a3a6ddc7041b329588`.
- One hardened application container publishes only `127.0.0.1:9080`. Dedicated Nginx backend listens on `127.0.0.1:9081`. The host's existing HAProxy TLS listener routes the exact new hostname to that backend. Existing project routes were retained. The separately owned `scena` site was not replaced; its Nginx configuration checksum remained unchanged.
- Private provider/operator/Restic credentials are mode 0600 on the host, never in source, image or command arguments. Production registration requires invitations. A one-use owner invitation valid for 72 hours was saved privately at `/srv/no-fear-stage/owner-invite.txt`; retrieve it through the authorized SSH connection, not public HTTP or application logs.

## Actual checks

External HTTPS readiness returned 200 with writable storage, both live workers, provider configuration, exact image identity and maintenance disabled. The landing UI opened in the browser at the new HTTPS origin. HTTP redirects to HTTPS. Public operator status returns 404. Both configured provider models were confirmed by an authenticated model-list request.

A disposable synthetic account completed registration over HTTPS with Secure/HttpOnly/SameSite Strict cookies. Synthetic Russian speech generated with macOS Milena TTS was uploaded; unauthenticated media access was refused. Actual upstream processing produced three grounded audience questions, accepted three separate synthetic answers and saved a report. Logout/login preserved the same practice. This used **six actual provider HTTP attempts**, **85.946 seconds of ASR audio**, **10639 reserved input characters** and **6000 reserved output-token ceilings** with no provider/job failures. Output ceilings are not measured token use or monetary cost; no currency assertion is made. This checks real generation on one synthetic practice, not sustained capacity or live microphone behavior.

The host backed up that practice's database/media, checked encrypted repository contents, restored the exact encrypted snapshot and verified its manifest/database. The committed app was resumed through the release controller. The existing authenticated session, report, four segments and speech hash survived the process replacement. The external acceptance waits for public readiness after restart because HAProxy health-check hysteresis can briefly outlast direct application readiness; it does not mistake a temporary proxy 503 for data loss.

The test practice and its media were deleted through the owner API. The synthetic account/sessions were removed by the operator, and its temporary local credential state was deleted. Durable provider reservations remain counted. Another verified backup completed after cleanup. No participant data was used in acceptance.

Local monitor and daily backup timers are enabled/active. The backup is scheduled at 02:00 Europe/Moscow plus up to five minutes of jitter. The committed-release resume service is enabled at boot. The Certbot renewal timer is active; a hostname-specific deploy hook atomically publishes the renewed certificate to HAProxy, validates its configuration and reloads it. The hook was exercised against the current valid certificate. Other lineages are ignored; failed publication restores the previous PEM. Proxy configuration backups are private under `/srv/no-fear-stage/proxy-before`.

## Source checks and operator assets

`deploy/nginx-behind-haproxy.conf` is the alternate proxy template for a host with an existing TLS terminator. `deploy/renew-haproxy-certificate.py` is the isolated certificate publication hook; set its lineage during installation. Nginx and HAProxy configuration validation passed before activation. Two existing HAProxy rule-order warnings remain outside this project's changes.

The local regression suite passed **123 tests**, including the two added certificate-isolation/rollback tests. Python syntax checks cover the hook and `tests/deployed_flow_acceptance.py`. The latter is an explicit real-provider acceptance runner; it receives invitation/fixture settings on stdin and stores temporary fixture credentials mode 0600 outside Git. Ordinary pytest does not invoke this script or spend upstream quota.

The initial accepted backend baseline is `6ed59a4`; frontend-only releases can reuse its immutable image and replace only `public/`. The current immutable release is recorded in `/srv/no-fear-stage/release.json`. The subsequent source commit documents this deployment and adds operator/acceptance assets. Those assets are installed on the host separately from the container. No Git push was performed. Secrets, fixture state, server logs and backup repositories are excluded from the commit.

## Remaining external protections

The user has not supplied offsite repository or notification-receiver settings. Backups currently use a LOCAL encrypted repository on this host; operator status explicitly reports `offsite_configured: false`. Monitoring writes incident codes to its journal; it does not deliver external notifications. An independent external monitor is not installed. These protections still require a separate repository/password-recovery location and receiver/monitor host. Existing application-host loss cannot be claimed recoverable from host-local copies alone.

The public HTTPS application and real AI generation are verified. Continue to use invitations for the pilot and configure those external protections before relying on unattended production operation. Host throughput, remote repository recovery, real user microphone/browser combinations and upstream monetary limits remain separate deployment-specific checks.

## Public example removal, 13 October 2026

The public example report was removed from navigation, hero overlay/actions and the landing preview section. Its static payload and unused CSS were removed; old `#/example` URLs return to the landing page. Actual account reports and recording recovery are unchanged. Module/stylesheet versions were updated to invalidate browser caches. The frontend-only image is released through the existing backup/readiness/rollback controller; the initial accepted backend image remains its immutable base.

## HTTPS ingress incident and fallback, 14 October 2026

The user reported connection timeouts on two networks. The running application, its two workers, loopback Nginx and loopback HAProxy HTTPS were healthy. The certificate was valid through 11 January 2027; HAProxy had spare capacity and had never reached its connection limit. External connections intermittently established TCP but stalled before TLS completed. A source-scoped temporary bypass of existing TCP MSS rules did not resolve this and was removed automatically. Packet-header inspection showed affected external connections with missing TLS data. The responsible upstream network component is not established.

An [independent standard-port check](https://check-host.net/check-report/50f2b26ek5fa) timed out from all five selected nodes. Passing the same TLS service through port 10443 succeeded. An isolated `no_fear_stage_fallback_https` frontend is now installed at **https://no-fear-stage.157.22.172.204.nip.io:10443/** using `deploy/haproxy-fallback-https.cfg`. It reuses the existing certificate and protected backend. The complete HAProxy candidate validated before a graceful reload; the prior shared configuration is saved privately under `/srv/no-fear-stage/proxy-before/`. Existing application, database, container image, canonical `APP_ORIGIN`, port-443 configuration and other project routes were retained.

The fallback landing page rendered in the actual browser. Landing, health, readiness and auth-state reads returned 200. A validly shaped synthetic login for a nonexistent account reached credential validation (401) with the exact fallback Origin. Hostile origins, a deceptive origin suffix and cross-site requests returned 403; an unrelated Host returned 421. Private practices returned 401 and operator status returned 404. No real account was created or altered and no AI calls were made. An [independent fallback check](https://check-host.net/check-report/50f2d7a6k777) returned 200 from Russia, the Netherlands, Turkey and Indonesia; the Iran node timed out before resolving an address. This verifies a working alternate entry, not universal connectivity or recovery of port 443.

Keep this fallback until standard HTTPS is verified externally over time or hosting/network support resolves the ingress fault. Do not silently move browser-local drafts between origins: saved server recordings/reports are shared, but port-443 IndexedDB drafts are not visible on port 10443. Removal and exact-origin security controls are documented in `docs/operations.md`.
