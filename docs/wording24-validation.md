# DeepSeek wording stage validation

13 October 2026. The user requested a DeepSeek pass for GPT-authored formulations. Source/hash snapshots remain frozen; the baseline verifier passed.

## Actual provider observations

Through the existing provider, DeepSeek V4 Pro first exhausted the 3,000-token ceiling. Official DeepSeek documentation describes non-thinking controls, but this gateway returned HTTP 400 for both the nested thinking control and standard reasoning-effort control; V4 Flash also rejected the tested control. These failures are not quality passes, and a catalog entry does not prove endpoint compatibility.

DeepSeek V3.2 returned a complete edited copy of the user's saved report and a separate synthetic three-question set. The report kept two strengths, three recommendations, the selected main focus, criteria assessments, metrics, exact quotes, transcript and source offsets. Agent reading found the observations/actions shorter and the final prompt aligned the address to informal Russian. This is agent review, not independent blind acceptance.

The question draft echoed the input max_chars metadata. The compiler was refined to accept only an exact integer echo of the original cap and discard it; altered caps and other extra keys remain rejected. Captured real report/question drafts were recompiled offline with the current validator and both passed. This is reuse of actual output, not an extra provider call or a claim that the first question compilation succeeded. Synthetic saved questions were not inserted into the user's practice, and already answered real questions are not rewritten.

The controlled probes used one HTTP attempt per task, two planned calls per run, the existing in-container durable ledger, and the planned 600,000-token daily reserved-output capacity. One initial second request was blocked by the former 300,000 cap after prior development evaluations. The capacity doubles for the requested two-stage pipeline while job, per-call, per-user, attempt and audio caps remain bounded. A failed source upload preceded one exploratory run; its results were not treated as current-source evidence. Unknown provider prices/currency stay unknown.

Private raw/compiled results and source material are in ignored outputs/test-artifacts/wording24 (mode 0600 files, private directory), never public assets or source control. Operations use the application container's database namespace without creating a Store or starting a second worker. Production publication uses the same durable queue as normal refresh.

## Automated and application checks

211 Python tests, both frontend syntax checks and the frontend report suite passed. The new tests cover immutable report fields and derived text, invalid/missing/duplicate IDs, altered read-only caps, changed signed numbers, invalid source quotations, formatting leakage, duplicated/compound questions, exact question/source binding, source revision checks, assessment reuse, and accounting for both stages on success/failure. Failed editing retains the previous report and recordings. Existing frontend report rendering, explicit refresh and source/export/repeat tests remain applicable; no new user step or page is introduced.

Literal numbers and immutable metadata can be checked mechanically. Semantic equivalence of free prose cannot; preserving IDs/statuses alone is not proof of preserved meaning. Independent reviewers remain unavailable, and the user will assess the revised wording. The DeepSeek editor receives text/selected excerpts, not audio or video, through the existing configured provider.
