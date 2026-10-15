# Closed contest analytics and event journal

This document defines the maintained analytics behavior and measurement rules. The application remains one process with its existing two AI workers. Analytics does not trigger ASR or LLM calls.

## Access

UI: `/#/admin/analytics`, also linked from the authenticated header when `analytics_access` is true. The server checks the current session and `admin_memberships` on every admin API, private media, Range request and export. Occupation `users.role` never grants access. No public administration/grant endpoint exists. There is exactly one active owner; assignment atomically revokes previous memberships. Do not store an operator token in frontend code.

After verifying the intended existing account, run inside the active application container:

```sh
# Supply the verified email privately on stdin, never a password.
docker exec -i no-fear-stage python -m server.cli analytics-owner --email-stdin
```

Existing sessions obtain the navigation permission on the next auth envelope / page reload. Revocation takes effect immediately on server requests. Ordinary participant media endpoints retain ownership isolation; administrative media uses a different owner-protected endpoint.

### Password-protected full reader

`/#/analytics` and `/#/analytics/export` are separate read-only links requiring no
user account. At the user's explicit request, the password grants full viewing of
metrics, account identities/registration data, practices, saved reports, transcripts,
recordings, trace details and current exports. It uses the same read handlers and
filters as the owner interface through explicit GET aliases under `/api/analytics-view`.
It never creates a user/owner identity or authorizes business mutations. Classification
controls are hidden in this mode and all server mutation handlers still require owner
account authentication and CSRF. Session login/logout remain its only allowed mutations.

`GET /api/analytics-view/session` returns only enabled/authenticated booleans.
`POST` verifies a bounded password body with Argon2; `DELETE` revokes the current
session. Both require exact same-origin Origin validation. An opaque HttpOnly,
SameSite=Strict cookie, Secure in production and scoped to `/api/analytics-view`,
expires after eight hours. Only its digest is stored. All responses use no-store;
passwords/cookies are absent from request telemetry. Login attempts are limited to
10 per IP and 100 globally per 15 minutes, with two concurrent password verifications.

Reader routes are `/report`, `/accounts`, `/practices`, `/practices/{id}`, `/export`
and `/evidence/{practice_id}/segments/{segment_id}/media`. The standard `/api/admin/*`
and participant routes continue to reject a viewer credential. Media URLs returned
by viewer details use the reader namespace so the scoped cookie covers playback,
Range requests and downloads. Exports retain existing size, CSV safety and privacy
rules; owner snapshots and all modifying routes remain separate. Audit logging on
reads does not change business data.

Viewer access configuration and session digests use namespaced `operational_state`
rows; there is no schema migration or synthetic account. Password rotation and
disable revoke every viewer session. The existing password/session configuration is
preserved when extending read permissions. The CLI reads a password on stdin without
initializing/migrating Store; see `operations.md` for rotation and disable commands.

Password entry loads the analytics CSS before display and uses `.admin-login`:
a 24px title, 38px password field, 36px button and a 380px maximum-width form with
explicit spacing. It does not inherit the landing/narrow page scale. Small viewports
preserve readable fields and avoid horizontal overflow.

## Sources and semantics

- SQLite triggers atomically persist registration, practice creation, segment acceptance/capture-key binding, job transitions/results, feedback and provider attempts. Triggers use native SQLite functions so earlier schema-family-1 application connections remain writable on a code-only rollback. Trigger `release` is honestly `unknown`; correlated HTTP/diagnostic records carry the runtime image release. No UDF is required by a database trigger.
- `analytics_events` is separate from 90-day operational events and 48-hour quota reservations. Events have an ordered ingestion sequence, event ID, origin, occurred/received times, actor/practice/session/request/correlation IDs, safe fields and release. IDs and enum fields are allowlisted. Browser events cannot assert server milestones.
- Existing users, practices, saved segments and successful job results are backfilled once, idempotently, as `reconstructed`. First physical recording time, historical UTM and actual old report views stay unknown. Existing `report_opened` means a data request and is excluded from visible-view metrics.
- Capture events use the original stable `client_key` as capture ID. UI observations never authorize report generation or prove persistence. Report rendering is bound to a successful report job version; ≥10 visible seconds is additional engagement, not proof of reading.
- The bounded client queue uses sessionStorage (safe observations only, 24-hour TTL, 500 events / 256 KiB), asynchronous 5-second delivery, replay-safe UUIDs and keepalive. It never stores credentials, speech or media. Local recording persistence is unaffected.
- Anonymous traffic uses Secure/HttpOnly first-party visitor/visit cookies in production, 180-day visitor lifetime and 30-minute activity-based visits. Logout rotates the context. Sessions and source snapshots do not use IP/fingerprints to merge people; IP is hashed only for ingestion rate limiting.

## Calculations and filtering

Server engine: `analytics_metrics.py`; source fields are preaggregated by practice before joins. One result drives summary, memberships, drill-down and snapshot. API dates are half-open Moscow calendar ranges; UTC epochs are stored. The UI displays inclusive end dates and converts them to the following exclusive day. Metric names state their population, time window and unit. The UI has no calculation explainer block. Marketing filters are limited to period/source/campaign/source model; event and quality views expose only applicable period filters. Periods are bounded to 366 days. Read calculations run outside the async event loop with a 20-second request deadline.

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

## Metric naming review

The UI names saved accounts/recordings/practices explicitly instead of using an undefined “active user”. Practice funnel percentages share the named created-practice denominator; question answers use the questions-enabled speech base. Observed recorder/report steps carry their measurement start date and are not mixed into historical confirmed completion. Seven-day activation and selected-window completion show the eligible population, result and still-young population as separate counts. Rolling 24-hour/7-day/30-day recording activity is distinct from exact-calendar-day return after first speech. Return within 7/30 days after the first report has its own table. Time quantiles are labeled as the maximum time for half / 90% of observed accounts or practices; they are not an average. Advertising columns name clicks as a share of impressions and the price of one click / 1,000 impressions. No hidden calculation text is needed to identify a percentage denominator. API report-version filtering remains available; implementation version codes are omitted from ordinary UI filters.

Primary references reviewed on 13 October 2026:

- [Yandex Metrica: funnel conversion from first vs previous step](https://yandex.ru/support/metrica/ru/reports/funnels). The product uses explicitly named populations, not a changing unnamed conversion base.
- [Mixpanel: metrics for product management](https://mixpanel.com/blog/product-management-metrics-and-analytics/). Activation, recording usage and return are separate product-specific outcomes.
- [Amplitude: interpreting retention](https://amplitude.com/docs/analytics/charts/retention-analysis/retention-analysis-interpret). Exact-day return is separate from return within a time window, and calendar-day choice is explicit.
- [Yandex Metrica: attribution models](https://yandex.ru/support/metrica/ru/reports/attribution-model.html). Source naming follows the first/last-significant distinction. This application retains its own 30-day, single-browser rules and does not claim Yandex integration, its 90-day window or cross-device recognition.

## Compact owner interface (15 October 2026)

The maintained UI now has exactly two routes: `/#/admin/analytics` and
`/#/admin/analytics/export`. Only the inclusive Moscow date range and the
staff/test-account switch are visible. Advanced calculation, journal, marketing
and legacy snapshot APIs remain owner-authorized; they are not navigation tabs.
The records region switches between practices (default) and accounts, lazily loading
one table at a time with 10 rows per page.
A practice opens its real saved recordings, reports and feedback. These are
completion and report-usefulness observations, not evidence of speech improvement.

The compact calculations live in `server/analytics_overview.py`, returned under
`overview` with `definition_version=owner-overview-v1`:

- Total accounts: eligible accounts registered before the selected period end.
- Started practices: selected practices with a speech `capture_started` observation
  or a saved speech. Setup creation alone is excluded. Per-user mean divides these
  starts by all eligible accounts; per-trainee mean divides them by distinct owners
  of those starts. The user's requested second mean is **not a median**.
- DAU: distinct accounts with a saved speech or answer on the last Moscow calendar
  day of the period, clipped at calculation time. Last-hour activity is the same
  action during the 60 minutes before calculation, independently of selected dates.
- Daily chart: distinct accounts with saved recordings and new registrations on
  each Moscow day. A user with multiple segments counts once per day.
- Seven-day retention: accounts active in `[cutoff-14d,cutoff-7d)` that return in
  `[cutoff-7d,cutoff)`, divided by the first set. Churn is the complementary share.
  `cutoff=min(period_end,as_of)`. This is consecutive-week activity retention,
  distinct from exact-day D7 cohort retention in the legacy API. Empty bases are null.
- Acquisition funnel: distinct observed landing visits, then confirmed registration
  or login **bound to the same visit**, then an observed speech start in that visit after
  authentication. New logins bind first-party analytics cookies; old unbound login
  events cannot be allocated retrospectively. Do not infer identity from IP.
- Training funnel: started practice, saved speech, sequential saved answers 1–3,
  generated report, observed view, later new speech after that view. The questions
  branch excludes questions-disabled practices; these rejoin before report generation.
  Rates use the eligible preceding step. Visits and practices have separate bases.
  Report outcomes describe selected practices as of calculation time; an old report
  GET still does not count as a view.

Account rows expose the stored full name, email, registration time, occupation,
onboarding flag and selected-period practice count to the owner. Separate surname,
first name, patronymic and IP were not collected; their fields remain null. Never
split or invent identity fields, and never include password/session/recovery data.

### Provider accounting

Each new HTTP attempt records a finite nonnegative `x-litellm-response-cost` when
supplied, including failed HTTP responses and retries. `provider_cost_recorded`
is written alongside the quota outcome, before provider-body validation. The durable
journal keeps the practice binding for final jobs and incremental ASR chunks; usage
records and start events identify attempts with missing prices. Quota-row pruning
must not erase recorded prices. Cancellation or an unknown outcome remains unpriced.
No extra generation or recognition calls are made to measure or backfill cost.
Successful usage retains a validated provider response ID; the immediate durable
price event also retains the gateway call header ID when supplied.

Explicit operator reconciliation can refresh the configured key's read-only spend
ledger at most once per 30 seconds, with a six-second network deadline and an
8 MiB response cap. Only a unique provider request ID or a unique model/token match
inside the durable attempt interval can bind a price to an existing practice.
Duplicate/ambiguous rows, conflicts with known header prices and calls belonging to
other work are excluded. One gateway call cannot be charged to two local attempts.
Reconciliation only updates price facts and its refresh timestamp; it never changes
accounts, recordings, questions or reports. Failed refreshes retain saved prices.

Totals include all recorded operations of selected practices (questions, assessment,
wording, recognition and their retries/refreshes). Currency is unknown: raw accounting
retains `gateway_unit`; current UI and exports show text tokens instead. A known zero is a provider-meter
observation, not proof of zero upstream cost. The 12 October recognition-accounting
limitation in `observability-cost.md` still applies. Only fully priced practices can
have a total; any missing attempt/legacy price makes aggregate total and means null.
The raw known subtotal and coverage remain available through the legacy report
accounting object. Exact accounting fields stay null when coverage is partial.
Per-user cost divides total by
accounts with provider work; per-practice cost divides by practices with provider work.
Event retention (180 days) and historical missing billing still limit coverage.

### Visible LLM consumption (15 October 2026)

The dashboard expense row and practice table now show `Токены LLM`, with totals and
means per practice and account with text-model work. `llm_tokens` carries these values
in the API and current CSV/JSON/ZIP exports. Legacy `economy`/`cost` accounting fields
remain in the report/practice API for compatibility but are excluded from current
owner exports. Opening analytics no longer makes a billing network request.

Count provider-reported input plus output tokens for questions, report assessment
and both wording operations, including retries and failed attempts with reported
usage. Deduplicate persisted attempts by their durable ID; legacy rows without IDs
remain separate usage facts. Transcription calls/audio seconds are excluded.
Unknown, invalid or absent token counts are never zero; a reported zero is valid.
Durable text-call start events retain coverage gaps after quota expiry or an
interrupted request. Partial totals and their means display `≥`; separate known
input/output subtotals and call coverage are exported. Usage retention is 90 days,
so missing historical counts remain unavailable. No formula explanations are added
to the interface.

The live configured key and selected models were rechecked on 15 October. Although
some unrelated catalog entries declare RUB, `gpt-5.4`, `gpt-5.4-mini` and
`whisper-large-v3` and the key do not declare a currency. Neither a guessed exchange
rate nor another model's tariff can turn these recorded spend values into RUB.

Reference: [LiteLLM response headers](https://docs.litellm.ai/docs/proxy/response_headers).

### Current owner exports

`GET /api/admin/analytics/export?dataset=summary|daily|accounts|practices|funnel&format=csv|json`
exports current filtered data. `dataset=all&format=zip` includes all five CSVs and
metadata with filters, dates, units and definitions. CSV is UTF-8 with BOM and formula
escaping. At most 10,000 selected practices/accounts are exported; over-limit exports
fail explicitly. Every request rechecks owner access, honors `ANALYTICS_EXPORT_ENABLED`
and records a content-free audit event. Unlike legacy pseudonymous snapshots, the
explicitly requested **private owner account export includes name and email**.
Existing snapshot formats remain pseudonymous and must never acquire identity fields.

### Dense presentation (15 October 2026)

The owner view follows the supplied BI references: a single KPI strip with vertical
rules, compact inline date controls, a horizontal expense row, a daily chart beside
the conversion table, and the selected records table below. KPI labels carry their units and period; calculation explainers, formula tooltips
and definition disclosures are intentionally absent at the user request. Colors distinguish chart
series; unknown values remain em dashes and price coverage stays available beside
expenses. There are no individual rounded KPI cards, shadows or decorative gauges.
The export page uses the same compact controls and table scale. Narrow viewports
stack analytical sections and retain local horizontal scrolling for wide tables.
Report prose, quotations and recordings retain the normal readable product scale.
Calculations, filtering, ownership and export contents are unchanged by this pass.
