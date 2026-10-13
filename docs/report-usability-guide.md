# Speech report reading and formative acceptance

Date: 2026-10-13. Implementation guide for `public/app.js`; this document is not evidence of participant acceptance or semantic coaching quality.

## Implemented information hierarchy

The report uses one reading column. Its first block shows the server-selected recommendation and concrete action first, followed by its observation, canonical short quote with the speech/answer source, and optional rewrite explicitly labelled `Возможная формулировка`. The publisher currently withholds unreviewed rewrites (`withhold_unreviewed_rewrites-v1`), so fresh candidate reports publish `example: null`. The view and export retain proposed wording support for already stored or explicitly approved reports; canonical quote provenance alone is not factual review of a rewrite. The primary recording action appears here. Other supported observations follow; there is no minimum item quota, global score, radar or agent panel.

`schema_version=2` selects the main item only through `primary_recommendation_index`. An unrelated `insight` string never supplies a v2 focus. Null priorities and empty recommendations have a plain recording action and no automatic focus. A person may choose another stored recommendation in the optional repeat-focus disclosure. The UI sends the source practice ID and recommendation index; the server resolves the owned saved item. Original explicitly supplied criteria are preserved, rather than replaced with generated advice.

Only returned user criteria appear. `unknown` reads `По этой записи нельзя оценить` with the criterion's specific reason and no failing grade. A directly observed mismatch reads `Есть несоответствие критерию` and includes its reason; absence under unknown recognition completeness is not treated as failure. Transcript availability does not imply perfect recognition. The text-only scope is in optional details, without a large warning competing with advice.

Native details provide transcript by segment, persisted question context, owner-bound whole-segment playback/download, neutral local metrics, scope, and optional usefulness feedback. Questions are labelled separately and never shown as the speaker's quote. No timestamps or excerpt playback are fabricated. A text export preserves observations, actions, proposed wording, origin labels, criteria/reasons, metrics, limitations and segmented transcript. Legacy reports remain readable and downloadable without regeneration; their saved insight and merged transcript remain accessible. Exports are local text files and contain the person's report content; private playback URLs are not exported.

## Deterministic states and browser checklist

`tests/frontend_reports.mjs` executes maintained render/export/repeat functions with synthetic data. It checks main-index selection, quote origins, complete exports, criterion reasons, sparse and legacy states, preserved criteria and selected recommendation, and HTML escaping of provider text. These checks establish UI/contract behavior; they cannot establish semantic entailment or user comprehension.

The browser fixture supports `POST /__test__/report-kind/{normal|sparse|unknown|legacy}` for subsequent report jobs. It remains loopback-only and is absent from the maintained application. Use `--port 8095 --origin http://127.0.0.1:8095` to avoid altering the user's localhost:8094 session. Do not confuse fixture reports with real provider results.

Actual browser acceptance should cover:

- Normal speech plus confirmed answers: the main quote's source is correctly labelled; advice is visible without expanding details.
- Sparse report: no fabricated main focus or empty focus-specific selector; another attempt still works.
- Unknown user criterion: no failure interpretation; reason is readable.
- Legacy report: saved insight, findings, merged transcript and private recording still open; no automatic regeneration.
- At 320 CSS px and desktop zoom: headings, long evidence, radio descriptions and player reflow without horizontal page scroll.
- Keyboard: logical reading order, visible focus, details Enter/Space interaction, radio selection and repeat activation.
- Repeat selection: the new practice keeps original criteria and the selected owned saved recommendation separately, including after reload.
- Failed generation and interrupted upload: existing durable retry/draft paths still work and never substitute a synthetic report.

Record actual checks, environment and failures in the central acceptance record. A screenshot or automated pass is not a participant comprehension result.

## Participant study (pending real participants)

Recruit eight likely Russian-speaking users, including at least two primarily mobile users and, where feasible, one who uses zoom or assistive technology. Obtain permission outside Git; never store identifiable recordings or contact details in this repository. Include speech genres and sparse/unknown states. Counterbalance baseline/prototype order and use different but comparable reports to reduce learning effects. Show participants exactly the evidence available to the product.

Use neutral Russian tasks, without naming UI controls or revealing the intended answer:

1. `Ты получил этот разбор после своей записи. Что он предлагает тебе попробовать дальше? Покажи, на чём основан этот совет.`
2. `Откуда взят этот фрагмент: из выступления или из ответа? Как ты это понял?`
3. `Что ты сделаешь в следующей попытке? Начни её так, как тебе удобно.`
4. `Тебе нужно свериться с записью и сохранить разбор. Сделай это.`
5. For unknown: `Что этот разбор говорит о выбранном тобой критерии?`

The moderator asks what the participant thinks, without correcting them mid-task. Observe independently identified action and basis, correct source identification, ability to find playback/export, selected focus persistence, time and assistance required, and misconceptions about analyzed voice, gestures or psychology. Invite criticism and do not ask leading satisfaction questions. Participants can decline or stop any task.

Use an anonymized row per task: case ID; layout order; device/viewport; completion without help; explanation in participant's own words; source identification; modality misconception; friction; severity; proposed change; retest result. Do not use participant names. The proposed formative gate is 7/8 independently identifying an actionable focus and its basis, with no observed modality misconception. It is a pilot product criterion, not a scientific reliability standard. Retest corrected issues; distinguish sparse cases where no focus is justified.

No real participant or live-provider semantic acceptance is asserted by this implementation. Those remain separate gates from deterministic rendering and synthetic browser flow.
