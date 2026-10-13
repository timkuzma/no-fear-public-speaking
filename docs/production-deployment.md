# Deployment acceptance, 13 October 2026

## Current deployment

- Public origin: `https://no-fear-stage.157.22.172.204.nip.io`.
- Host: Ubuntu 24.04 at `157.22.172.204`; source `/opt/no-fear-stage`, private configuration/data/backups `/srv/no-fear-stage`.
- Deployed application source revision: `6ed59a4`; immutable image ID `sha256:512b5572b2fb0cf7602836a8cf54e13d9f753f20ed4f05a3a6ddc7041b329588`.
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

The application release remains `6ed59a4`; the subsequent source commit documents this deployment and adds operator/acceptance assets. Those assets are installed on the host separately from the container. No Git push was performed. Secrets, fixture state, server logs and backup repositories are excluded from the commit.

## Remaining external protections

The user has not supplied offsite repository or notification-receiver settings. Backups currently use a LOCAL encrypted repository on this host; operator status explicitly reports `offsite_configured: false`. Monitoring writes incident codes to its journal; it does not deliver external notifications. An independent external monitor is not installed. These protections still require a separate repository/password-recovery location and receiver/monitor host. Existing application-host loss cannot be claimed recoverable from host-local copies alone.

The public HTTPS application and real AI generation are verified. Continue to use invitations for the pilot and configure those external protections before relying on unattended production operation. Host throughput, remote repository recovery, real user microphone/browser combinations and upstream monetary limits remain separate deployment-specific checks.
