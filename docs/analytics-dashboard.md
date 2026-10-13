# Closed contest analytics and event journal

Implemented against the approved `contest-analytics-dashboard-plan.html`. The application remains one process with its existing two AI workers. Analytics does not trigger ASR or LLM calls.

## Access

UI: `/#/admin/analytics`, also linked from the authenticated header when `analytics_access` is true. The server checks the current session and `admin_memberships` on every admin API, private media, Range request and export. Occupation `users.role` never grants access. No public administration/grant endpoint exists. There is exactly one active owner; assignment atomically revokes previous memberships. Do not store an operator token in frontend code.

After verifying the intended existing account, run inside the active application container:

```sh
# Supply the verified email privately on stdin, never a password.
docker exec -i no-fear-stage python -m server.cli analytics-owner --email-stdin
```

Existing sessions obtain the navigation permission on the next auth envelope / page reload. Revocation takes effect immediately on server requests. Ordinary participant media endpoints retain ownership isolation; administrative media uses a different owner-protected endpoint.

## Sources and semantics

- SQLite triggers atomically persist registration, practice creation, segment acceptance/capture-key binding, job transitions/results, feedback and provider attempts. Triggers use native SQLite functions so earlier schema-family-1 application connections remain writable on a code-only rollback. Trigger `release` is honestly `unknown`; correlated HTTP/diagnostic records carry the runtime image release. No UDF is required by a database trigger.
- `analytics_events` is separate from 90-day operational events and 48-hour quota reservations. Events have an ordered ingestion sequence, event ID, origin, occurred/received times, actor/practice/session/request/correlation IDs, safe fields and release. IDs and enum fields are allowlisted. Browser events cannot assert server milestones.
- Existing users, practices, saved segments and successful job results are backfilled once, idempotently, as `reconstructed`. First physical recording time, historical UTM and actual old report views stay unknown. Existing `report_opened` means a data request and is excluded from visible-view metrics.
- Capture events use the original stable `client_key` as capture ID. UI observations never authorize report generation or prove persistence. Report rendering is bound to a successful report job version; ≥10 visible seconds is additional engagement, not proof of reading.
- The bounded client queue uses sessionStorage (safe observations only, 24-hour TTL, 500 events / 256 KiB), asynchronous 5-second delivery, replay-safe UUIDs and keepalive. It never stores credentials, speech or media. Local recording persistence is unaffected.
- Anonymous traffic uses Secure/HttpOnly first-party visitor/visit cookies in production, 180-day visitor lifetime and 30-minute activity-based visits. Logout rotates the context. Sessions and source snapshots do not use IP/fingerprints to merge people; IP is hashed only for ingestion rate limiting.

## Calculations and filtering

Server engine: `analytics_metrics.py`; source fields are preaggregated by practice before joins. One result drives summary, memberships, drill-down and snapshot. API dates are half-open Moscow calendar ranges; UTC epochs are stored. The UI displays inclusive end dates and converts them to the following exclusive day. Dashboard prose is minimized; calculation definitions are collapsed under “Как считаем”. Periods are bounded to 366 days. Read calculations run outside the async event loop with a 20-second request deadline.

The default mode selects practices created during the period. The alternative selects practices with measured activity during the period (including existing practices). Practice milestone/record totals describe selected practices as of calculation time, not a raw count of all HTTP events. The daily chart separately uses the actual milestone dates. Filters include source, registration campaign, scenario, questions, duration, account, occupation, report version and staff inclusion. The source model can select the frozen last non-direct touch or first observed touch; these are distinct definitions. Question milestones count the actual saved answer index, including incomplete/out-of-order legacy data. Observed-step drill-down uses the same cohort window as the summary. DAU/WAU/MAU are global rolling 1/7/30-day confirmed recording activity, explicitly distinct from selected-cohort totals.

A report refresh never adds a practice or first completion. Retained first successful reports remain results when a refresh fails. Questions-on completion requires three saved answers; questions-off does not. Completion rate uses mature practices and a selected 24/72/168-hour window. First value is a first report within 7 days of registration, using mature account cohorts. Registration conversion uses observed form-session cohorts and a 7-day maturity window. Report views are client observations, with unknown historical coverage.

D1/D7/D30 are confirmed new speech recordings on the exact Moscow calendar day relative to the first speech, not rolling return. A separate repeat rate measures a new speech within 7/30 days after the first report. Empty denominators return null. Rating uses the last feedback per practice; historical feedback/report-version association may be unknown. The dashboard does not claim causal speech improvement, biometric uniqueness, or revenue/CAC/ROAS without payment data.

The detailed funnel separates each question being displayed, answer start, local recording and durable saving. Exact memberships drive all practice-step drill-downs. Acquisition includes observed landing/CTA/form/submission visits and registration failure codes, with direct-form visits separated. Behavior/account filters exclude anonymous observations that cannot be allocated reliably. P50/P90 use interpolated quantiles; negative intervals are excluded and counted separately. Unfinished states describe retained artifacts, not a guessed psychological reason for leaving.

## Marketing

UTM allowlist: source/medium/campaign/id/content/term; referrer hostname only. Registration source is the last non-direct observed touch within 30 days, frozen at account creation; first observed touch is also retained. A direct revisit does not overwrite a qualifying non-direct source. Practice-session attribution is stored separately. Shared-browser identity links exclude other authenticated owners.

First release accepts UTF-8 CSV, at most 10 MiB / 50,000 rows. Required columns:

`date,platform,account_id,campaign_id,campaign_name,creative_id,impressions,clicks,spend,currency,source_timezone,tax_mode`

Days must be `Europe/Moscow`; do not silently split or redistribute another timezone. Currency is a three-letter uppercase code, amounts finite/nonnegative decimal, tax_mode `included|excluded|unknown`. A batch is a full day/campaign revision, not additive partial creative data. No campaign-total and creative-level rows for the same day/campaign. Preview/confirmation are separate. Identical source bytes are idempotent; confirmation is atomic; revision disables previous active rows and audited rollback restores the previous confirmed revision. An owner must review completeness of the supplied file.

CTR/CPC/CPM derive from uploaded matching counts. Campaign and creative breakdowns reconcile to the same active batches. Acquisition cost counts only touches on uploaded expense days; omitted days are not assumed covered. Creative cost-per-result is not invented without a reliable allocation. Frozen snapshots retain active marketing batch IDs. Different currencies/tax modes are separated. Cost per registration/first value uses attributed acquisition touches in the selected expense period; full maturity can take 37 days. Ambiguous platform/account/currency matches stay unallocated rather than being guessed. Current expenses cover uploaded days only; missing budgets are unavailable, not free. Automatic ad API connections are deferred until channels are selected.

## Evidence, snapshots and logs

Practice cards expose participant details only after owner authorization, private speech/answers, bound questions, available transcripts, up to 100 saved successful report versions, feedback and up to 500 trace rows. Playback/download is audited and does not loosen participant routes. Missing/deleted files have explicit unavailable state. A private card computes the stored-file SHA-256 on demand off the event loop and labels the original-upload SHA-256 separately; normalization can legitimately produce different bytes.

Snapshots persist a closed, consistent read of calculations and marketing rows, metric/attribution versions, timezone, filters, as_of and source watermark, exact pseudonymous memberships and method. JSON/CSV/ZIP exports require owner access; ZIP contains hashes/manifest and an HTML summary. They contain no names, email, speech or media. Stable account IDs remain pseudonymous personal associations: these bundles are private, not automatically publishable jury materials. Public evidence or a jury account requires separately authorized recipients and records.

Journal filters: period, practice, actor, event kind, correlation/request/event/job ID, origin, errors and technical entries. Technical request/provider noise is hidden by default, not discarded. Trace links server/client observations and retries, retaining parallel optimistic transitions. Sequence orders ingestion; late/skewed browser times remain observations. Exports use the same filters, up to 10,000 rows per API request (UI labels its 500-row export); use returned cursor for subsequent pages. This bound is not a complete-history claim. Reconstructed events and missing browser observations are explicit.

Technical runtime diagnostics are structured JSONL with severity/component/release, safe request fields and exception type. Never include exception messages, request bodies, auth secrets, topics, transcripts or provider response bodies. Detailed events expire after 180 days; anonymous daily aggregate archives remain 24 months. Quota/operational retention is unchanged. Archives are private on the same host and are included in existing verified database backups; offsite protection remains unconfirmed until configured and tested.

Deleting a practice removes its identifying trace and bindings, records only an anonymous outcome count, and revokes/clears affected stored snapshots. Media/content is not retained in logs. Already downloaded private bundles cannot be recalled remotely; the owner must handle copies accordingly. Removed evidence is never reconstructed from a log. Daily aggregate archives do not provide unique-account retention after source deletion; current-detail counts and archive coverage must be distinguished.

## Operations and validation

Additive schema-family-1 migration, single process, no new dependencies/services. First migration backfills once; later starts do not repeat it. Existing code-only rollback remains writable because trigger statements are native SQLite. Never initialize the live Store from another process/kernel to grant access: the owner CLI uses the existing schema, not migrations.

Feature flags (`0` disables): `ANALYTICS_CLIENT_ENABLED`, `ANALYTICS_ADMIN_ENABLED`, `ANALYTICS_EXPORT_ENABLED`. Disabling optional collection/UI/export does not remove canonical business events or block recording. Deployment controller supports these config keys. Preserve the independent exact public research-page Nginx location; do not open `/api/operator/` publicly.

Meaningful acceptance: `tests/test_analytics.py` covers exact counts/branches/refresh, access exclusivity, ownership/media, atomic rollback/backfill, forged/sensitive events, attribution/replay, CSV revisions/rollback, bad money, snapshot manifests, classifications/CSRF, deletion, retention and 10 parallel saves/replays on a single ASGI event loop. `tests/analytics_browser_server.py` is private loopback-only synthetic UI acceptance; no test routes are shipped. `tests/analytics_load_acceptance.py` measures 10,000 accounts, 100,000 practices and 1,000,000 diagnostic events with no real provider calls. Synthetic capacity does not prove LLM generation throughput.
