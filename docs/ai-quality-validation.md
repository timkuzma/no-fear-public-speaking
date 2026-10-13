# Feedback candidate implementation and validation

Date: 13 October 2026. Branch: `frentend`. This is a local engineering candidate, **not** completed semantic acceptance or a production promotion. The user confirmed that independent reviewers and participants are currently unavailable; prepare their materials and leave acceptance incomplete.

## Implemented work

Three implementation agents owned backend/context/prompts, corpus/evaluation and report presentation. The coordinator froze the original source before contract changes, integrated account-owned repeat selection, reviewed diffs, ran combined checks and controlled the limited provider experiment. Cross-review found and corrected blind-packet schema leakage, rating/offset type weaknesses, incomplete-pair denominators, duplicate exported text, missing source labels and the main action appearing below a long quote.

| Roadmap area | Concrete result | Acceptance boundary |
| --- | --- | --- |
| Baseline/methodology | Immutable `65f6904-frozen` source/prompt/contract snapshot, SHA-256 manifest; requirements, rubric and annotation protocol | Model aliases/source defaults are not immutable observed provider revisions |
| Context/provenance | Closed v2 drafts, exact Unicode offsets/source/hash, persisted private question provenance, separated saved answers, nullable selected primary action | Source identity is not semantic entailment |
| Corpus | 120 separately authored synthetic situations: 40 development, 20 calibration, 60 locked acceptance; 20 challenge pairs with reversed/perturbed views | No real recordings, population sampling or human-adjudicated gold; related challenge variants are clustered |
| Prompt package | `speech-context-v2`, `speech-feedback-v2.2`, `questions-v2.1`, `contextual-text-v1`; shared boundaries, full JSON examples and agreed caps | v2.2 and final question quality remain unmeasured on independent humans/holdout |
| Evaluation | Offline baseline replay, private raw/request capture, bounded live text mode, source checks, blinding, blank ratings, agreement/confusion/paired comparison, optional critic protocol | No calibrated judge/critic is enabled; no acceptance cases were used for tuning or replay |
| Report | One primary action with rationale/source quote, one reading column, optional transcripts/private playback/metrics/feedback, legacy export and ordinary sparse continuation | Participant comprehension and speech improvement unmeasured |
| User flow | Synthetic local registration, failed upload/replay, three saved questions/answers, report, selected and ordinary repeat, legacy/unknown/sparse states | No physical microphone, typical mobile-device or participant session in this work |
| Release | Compatibility/restore checks and a release/rollback decision record | Candidate not pushed or externally deployed; quality gates are unmet |

## Automated and browser evidence

Final Python suite: **169 passed** (one existing third-party Starlette deprecation warning). Node syntax checks passed for maintained app/API modules; additional checks covered typography/landing motion and touched frontend test modules. Diff whitespace checks passed.

The suite covers strict extra/duplicate JSON keys, zero findings, nullable/invalid primary indexes, source revisions/adjacent contiguous spans, wrong question/version binding, user-only criteria, conservative absence/modality abstention, usage/retry/error handling, draft/autosave recovery and owner isolation. New repeat requests resolve a recommendation on the server from an owned saved report and preserve original user criteria separately. The frozen old Store opens the additive database; offline backup/restore preserves new metadata, rows and media.

An isolated fixture (`127.0.0.1:8095`) kept the user's localhost:8094 session separate. Synthetic media traversed real upload/storage/job APIs; one injected upload failure was retried with the same client key and did not duplicate the segment. Three questions and three answer recordings were saved; private question provenance stayed outside public practice/job JSON. The actual browser showed source labels, unknown voice criteria, sparse ordinary continuation, legacy content, keyboard disclosure and an actual downloaded export. A browser-selected non-primary recommendation persisted as separate `repeat_focus`, with the source criteria intact. Private audio reached readyState 4 with the expected one-second synthetic duration. At 320 CSS pixels, document scroll width matched viewport width and body prose was 16px; temporary viewport/reduced-motion overrides were reset. Console inspection reported no errors. The final v2.2 fixture showed zero generated-example blocks and one primary action.

These are engineering checks using synthetic fixtures, not recognition accuracy or participant acceptance.

## Real provider experiment

All calls ran inside the existing application container against its existing SQLite work ledger, using `limits.provider_scope` and durable reservations. The harness used a thin ledger adapter: **no Store initialization, migration, application restart or candidate promotion**. Provider credentials stayed in the container environment. Real calls used configured alias `gigachat-3-pro`, JSON-object mode, temperature 0.2, at most 3000 output tokens per attempt, one HTTP attempt per task and a 35-second HTTP bound. No audio/ASR call occurred. Upstream immutable model identity was unavailable.

| Run | Tasks / attempts | Structural outcome | Purpose |
| --- | --- | --- | --- |
| Initial baseline/v2.0 comparison | 6 / 6 | 5 accepted, 1 candidate report rejected | Two development reports per variant and one question set per variant |
| One v2.0 diagnostic repetition | 1 / 1 | Accepted, but unsafe proposed rewrite | Private pre-validation draft capture; same library case, not a new independent sample |
| One v2.1 verification | 1 / 1 | Accepted, but unsafe proposed rewrite remained | One development library report after manual prompt changes |
| v2.2 publisher replay | 1 saved draft / **0** requests | Unreviewed example absent from all public fields; source/remaining report retained | Deterministic containment test using the saved v2.1 draft |

Across the **eight actual attempts**, reported usage was 20,836 input tokens and 1,069 output tokens, with no missing token counts in these responses. Conservative ledger reservations were 43,026 input characters and 24,000 output tokens. These are different measurements. Actual billing and currency remain **unknown**. Across eight heterogeneous, case-correlated tasks, wall latency median was 1,800ms and nearest-rank p95 3,332ms; this small smoke does not establish capacity or typical latency. Three independent run IDs enforced maximum attempts 6, 1 and 1; no automatic semantic repair/retry loop ran.

The first rejected v2.0 response was not captured before validation, so its precise schema defect cannot be reconstructed. The harness was then repaired to save application prompt/context and parsed draft privately **before** validation. One later v2.0 repetition succeeded; that does not establish stochastic reliability or retrospectively explain the original rejection. Final v2.2 provider behavior and questions-v2.1 semantic quality were not separately live-tested.

## Observed risks and containment decision

Preliminary coordinator/AI-assisted review against author expectations found:

- Baseline library main advice requested resources/support, while its recommendation concerned benefits: the top action was independent of the evidence-linked list.
- Baseline toast proposed board-game evenings absent from the source; it also asserted emotional/audience effects.
- v2.0 toast removed forced advice but still described sincerity/atmosphere and cited only the gratitude sentence for a claim also involving the separate wish.
- A v2.0 diagnostic rewrite proposed premises and parent/teacher volunteers absent from the source.
- v2.1 still invented time-saving and book access after lessons. A valid contiguous quote did not prevent invented rewrite content.
- Initial question outputs included possible near-duplication and a question asking for a location already stated. The final question instruction addresses this, but has no independent quality result.

These are **preliminary findings, not two independent human ratings**, and must not be converted into a measured quality improvement percentage.

The coordinator and two independent implementation agents agreed on a conservative publisher policy: `withhold_unreviewed_rewrites-v1`. Fresh drafts still validate the type/length of `example`, then publish `example:null`; compatibility `text` contains observation/action only. Main insight remains the selected action. The generation instruction now requests null. Raw draft examples remain only in explicitly private evaluation artifacts; ordinary reports/jobs/logs do not retain or expose them. Existing stored reports are not rewritten and their renderer/export support remains.

This removes one known publication surface while preserving usable partial feedback. It is **not** a semantic truth detector: observations/actions can still contain incorrect facts, diagnoses or implications. Withholding an example is `not_assessable` for rewrite fidelity, not a successful fidelity score. The tradeoff is less concrete rewritten help until an independently validated publication approach is available. No brittle word/number filter, extra online critic or repeat-until-success procedure was introduced.

## Pending acceptance and next evidence

Two Russian-speaking independent reviewers must assess groundedness, relevance, genre fit, actionability and raw example fidelity; eight prospective readers should complete the formative tasks. Authorized real audio is needed for ASR fidelity, physical-device capture and actual end-to-end usability. There are zero independent human ratings/participant sessions from this work.

The private initial comparison packet contains only one complete report pair (toast), two correlated forward/reverse views and blank ratings. Failed/missing pairs are not silently included in a preference denominator. Additional diagnostic/replay versions must be kept separate rather than pooled as one improved candidate. The prepared critic is an offline proposal only; its calibration/benefit/cost gate is not satisfied.

`proposed-gates.json` remains a proposal, not an achieved standard. The harness refuses locked acceptance until a measured real baseline, two complete independent review sets, declared operating budgets and evidence-hash-backed frozen gates exist. Acceptance bytes/split metadata were audited without loading acceptance scenarios for tuning or evaluation. Do not open or reuse the holdout simply to obtain a favorable result.

Private raw/provider/request/rating artifacts are excluded from Git under `outputs/test-artifacts/ai-quality/`, with provider outputs/directories restricted to 0600/0700. Only safe methodology, authored synthetic corpus, source snapshots and aggregate findings are committed. Release/rollback conditions are in `docs/ai-quality-rollout.md`.

At the end of the experiment, the external container still reported release `e14bfca4d31a9ed8958dee9730214a1d87f3aee02b28d4debb011d3ddef1314d` (the previous own-speech release). Evaluation temporary files/connections were removed after private local archival. This work does not certify current offsite protection or broader operational state. No push or external deployment was performed.

Implementation commits: baseline `d73fa50`; backend/repeat contracts `f4c9617`; conservative publisher/prompt changes `ea10f0a`; report UI `8216162`; corpus/harness `0ea3b28`. Subsequent documentation records this verification without changing production.
