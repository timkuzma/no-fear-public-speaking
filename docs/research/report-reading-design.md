# Reading and acting on a speech report

Research date: 13 October 2026. This is a proposed report specification, not an implemented redesign. Sources were opened in the browser research tool. Thirteen usable primary publications/guidance pages are listed below; a redirect-only writing-guidance page and a Microsoft webinar page were excluded from this count.

## Product decision

The report should let a person identify one useful change, understand why it relates to their speech, and record another attempt. Information density means useful, grounded observations per unit of reading effort, not the number of fields. Proposed layout: one main action, a short explanation, a few evidence-backed observations, then optional detail. This is a product inference from U1–U8 and U12–U13, not a layout proven specifically for No Fear Stage.

## Verified source register

| ID | Primary source | Supported principle | Limits and product application |
| --- | --- | --- | --- |
| U1 | [NN/g: Progressive Disclosure](https://www.nngroup.com/articles/progressive-disclosure/) | Expose frequent/important choices first; defer rare details with clear labels. | General interaction guidance, not a prescription to hide all report evidence. Keep the main recommendation and its reason visible. |
| U2 | [NN/g: Layer-Cake Pattern of Scanning](https://www.nngroup.com/articles/layer-cake-pattern-scanning/) | Descriptive, visually distinct headings support scanning. | Eyetracking observations do not set a universal word limit. Use headings that describe the finding, not abstract categories alone. |
| U3 | [NN/g: Recognition and Recall](https://www.nngroup.com/articles/recognition-and-recall/) | Visible context supports recognition rather than remembering. | Does not prove a coaching intervention works. Keep a short speech excerpt beside the interpretation. |
| U4 | [NN/g: How Users Read on the Web](https://www.nngroup.com/articles/how-users-read-on-the-web/) | Concise, scannable and objective writing improved measured usability in the reported experiment. | Historical web study; do not transfer its effect sizes to this SaaS or Russian reports. Remove empty praise and repetition. |
| U5 | [GOV.UK Design System: Details](https://design-system.service.gov.uk/components/details/) | Use disclosure for information only some users need; do not hide information most users need. | Government component guidance, not a requirement to adopt its library. Transcript and metric definitions can be optional; the main advice cannot. |
| U6 | [GOV.UK Design System: Accordion](https://design-system.service.gov.uk/components/accordion/) | Test ordinary structured content first; avoid nested accordions and hiding universally needed content. | Evidence is required before introducing multiple collapsible sections. Default to one reading column and native details for secondary content. |
| U7 | [GOV.UK Design System: Summary List](https://design-system.service.gov.uk/components/summary-list/) | Key facts can use semantic key/value structure. | Not intended to turn narrative analysis into a large table. Use compact date/duration context only. |
| U8 | [GOV.UK: Identify User Needs](https://guidance.publishing.service.gov.uk/writing-to-gov-uk-standards/plan-manage-content/identify-user-needs/) | Content should support evidenced user tasks; acceptance criteria describe when the need is met. | General content planning. The task here is choosing a concrete next practice, not reading a comprehensive grading dashboard. |
| U9 | [W3C: Understanding Reflow, SC 1.4.10](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html) | Ordinary content should reflow at 320 CSS pixels without two-dimensional scrolling. | Understanding is informative; the normative criterion defines conformance. Verify report prose at narrow width and zoom. |
| U10 | [W3C: Understanding Headings and Labels, SC 2.4.6](https://www.w3.org/WAI/WCAG22/Understanding/headings-and-labels.html) | Headings/labels describe topic or purpose. | Semantic markup is also covered by other criteria. Use actual headings and explicit action labels. |
| U11 | [W3C: Understanding Status Messages, SC 4.1.3](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html) | Announce waiting/success/error status without requiring focus changes. | Applies to status messages, not every newly rendered paragraph. Avoid announcing the entire report through a live region. |
| U12 | [GOV.UK: Moderated Usability Testing](https://www.gov.uk/service-manual/user-research/using-moderated-usability-testing) | Observe relevant users doing realistic tasks; avoid tasks that reveal the answer. | A small study diagnoses problems; it does not estimate population conversion precisely. Test finding the advice, explaining its basis and starting a repeat. |
| U13 | [Microsoft HAX: Guidelines for Human-AI Interaction, Design Library](https://www.microsoft.com/en-us/haxtoolkit/library/) | Set expectations about AI capabilities; support appropriate interaction when outputs fail (G1, G2, G9, G10, G11). | General human-AI design guidance, not proof that any specific model is reliable. Show a concise text-analysis scope and a clear recovery action. |

## Current code audit

Inspected `public/app.js`: `reportMarkup`, `reportItem`, `reportPage`, `repeatChoices`, `repeatPanel`, `downloadReport`; inspected `server/ai.py`: `analyze` and `_findings`.

- Already present: one main insight, strength/recommendation excerpts, caller criteria only, locally computed metrics, transcript disclosure, private playback, repeat-focus selection, text export and usefulness feedback.
- Current visual/reading concerns: parallel strength/recommendation columns, three prominent metrics, a large limits notice, playback for all segments, repeat choices and a five-point feedback form compete for attention. This is a source-based concern, not an observed usability failure from participant testing.
- The main insight can invent facts without violating evidence-ID checks: it is validated only as a string. It should select a validated recommendation ID or carry its own reviewed evidence basis.
- Findings retain `segment_index`, but `reportItem` does not show whether an excerpt is from the original speech or an answer. A response can appear to support a claim about the original speech. Display origin text such as `Выступление` or `Ответ на вопрос 2`.
- UI has empty-array fallbacks; backend requires one to five items in each findings list. Proposed sparse-report states therefore require a coordinated API/prompt change.
- The transcript is merged text. Proposed per-segment display must preserve original speech versus question/answer boundaries; audience questions are context, never the user's quote.

## Proposed visible contract

| Layer | Content | Display rule |
| --- | --- | --- |
| First reading | Recording title/date; main action; why it matters; short supporting excerpt with segment label; one primary repeat action | Always visible. Do not add a score, radar chart or agent badges. |
| Main reading | Zero to two useful strengths and up to three distinct actions, as supported by evidence | Empty lists are valid. Do not fill quotas. Use one column. Each finding contains observation, consequence and practical action where relevant. |
| User request | Only criteria explicitly supplied by the person | Preserve labels. Explain `unknown` without implying failure. Show criteria in normal prose/list, with short textual statuses. |
| Optional detail | Transcript by segment, private recordings, duration/recognized word count/average recording rate, scope explanation | Native accessible disclosure, no nested details. Metrics are descriptive, not performance scores. |
| Secondary actions | Download, another topic, optional feedback | Visually secondary. Feedback remains optional; do not introduce a mandatory questionnaire. |

The initial view should be meaningful without opening anything. Supporting quotes must remain readable next to essential claims. Very long original quotes can be placed below a short observation in an explicitly labelled disclosure; do not shorten the stored canonical evidence or substitute an invented quote. A short quote can only be extracted by the server with validated exact offsets. No timeline links until verified timestamps exist. First iteration uses the existing whole-segment playback.

## Copy specification and budgets

Russian UI; connected sentences; no decorative arrows, numbered badges, personality assessments or unsupported promises. A report should explain a limitation at the relevant conclusion rather than accumulating technical warnings.

Proposed editorial budgets, to validate with users: main action 35–70 words including rationale/example; each observation 30–70 words plus an exact excerpt; default main reading approximately 250–450 words when evidence warrants it. These are soft design budgets, not limits proven by literature or minimum quotas. Short speech can justify a much shorter report. Never truncate a meaning-bearing passage to meet a budget.

Every action should answer: what to change, where in this speech, why a listener might benefit, how to try it, and what the user can check in a repeat. Phrase audience effects as an interpretation (`так слушателю может быть проще...`), never as measured audience reactions. A wording example preserves meaning and facts and is labelled `Возможная формулировка`.

## Synthetic example for internal design only

Speech: `Мы предлагаем открыть библиотеку рядом со школой. Там ученики смогут вместе готовиться к урокам.` No budget, deadline or actual outcome is known.

Optional practice, not a diagnosed weakness: `Попробуй более компактный вариант уже ясной мысли. Можно сказать: «Предлагаем открыть библиотеку рядом со школой, чтобы ученики могли вместе готовиться к урокам». В повторной попытке проверь, сохранилась ли эта связь без отдельного объяснения.`

Support: both original sentences, from speech segment 0. If the schema permits only one short sentence ID, choose a finding supported by that one sentence or extend the evidence contract; do not silently concatenate unrelated quotes.

Poor action: `Добавьте бюджет 2 млн рублей и рост успеваемости на 30%`. This invents facts and imposes a pitch template. Even the current fixture's `назовите расходы` must be evaluated contextually; library topic alone does not make budgeting a necessary defect.

This example must stay in internal design/research material. The public application has no example report route.

## States and acceptance

| State | Expected experience |
| --- | --- |
| Good evidence | Readable main action and its basis; selecting a recommendation starts a repeat with the same selected focus. |
| Sparse speech | Explain the one observable point; empty strengths/actions are allowed; offer another attempt without manufacturing criticism. |
| Unsupported criterion | `По этой записи нельзя оценить` plus a short reason; no failing grade or fabricated voice analysis. |
| Ambiguous ASR | Qualify the affected interpretation and allow listening to the relevant saved segment. Transcript correction is a separate versioned workflow if added later. |
| Job failure/budget pause | Saved recording remains accessible; offer existing explicit retry/continuation; no fabricated successful report. |
| Legacy report | Continue rendering/exporting existing data. Do not regenerate it silently when prompts change. |
| Keyboard/screen reader/mobile | Logical reading/focus order; native details work; origin labels are textual; 320px reflow; visible focus; status announcements are concise. |

Proposed formative study: 8 likely Russian-speaking users, including at least two who use primarily mobile and a participant using zoom/assistive technology where feasible. Give realistic reports from different genres; counterbalance baseline/prototype order. Ask each to identify the main action, point to its basis, distinguish an answer from the original speech, explain what they will try, and start a repeat. Do not instruct where to click. Record task completion, misinterpretations and explanation accuracy; general satisfaction is secondary. Initial design gate: at least 7/8 independently identify an actionable focus and its basis, and no observed misbelief that we measured psychology/voice. These are proposed pilot gates, not statistical validation or literature numbers. Re-test corrected issues.

## Materials to author before implementation

1. Internal report wireframe with normal, sparse, user-criteria, answer-evidence, ambiguous-ASR, failure and legacy states.
2. Russian content rules and good/bad examples, including omission versus unobservable criteria.
3. View-model mapping to existing report schema; migration/compatibility note for any new evidence and focus fields.
4. Usability discussion guide, participant profile, neutral tasks, observation sheet and decision log.
5. Browser acceptance checklist covering reflow, keyboard, disclosure, escaping, segment ownership, export parity and selected-focus persistence.

Implementation order: agree information hierarchy; fix grounded content contract; build the report view using existing native JS/CSS; verify accessibility and saved flows; run formative testing; then publish through the existing release controller after quality gates. No additional dashboard library or service is needed.
