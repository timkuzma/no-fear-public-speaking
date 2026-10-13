# Research and plan review record

Date: 13 October 2026. Scope: research artifacts and implementation planning only. No application code, provider configuration, live recording, account or production deployment was modified.

## Work allocation and evidence

Three research subagents investigated prompt construction/evaluation, context/orchestration, and speech assessment. The coordinating agent investigated report reading/interaction, inspected current implementation and the referenced chat, consolidated the plan, then assigned cross-reviews. The linked chat is titled “Составить план запуска в production”; its actual recent content was read through `read_thread`. Historical deployment statements were not treated as a fresh quality or host verification.

The thematic registers contain 63 entries corresponding to 55 distinct documents after deduplicating shared URLs and alternate arXiv representations. Each topic has at least ten unique opened sources:

| Topic | Register | Distinct sources inside topic |
| --- | --- | --- |
| Prompt construction | P1–P11 | 11 |
| AI evaluation methodology | E1–E12 | 12 |
| Context and orchestration | A1–A13 | 13 |
| Report reading and interaction | U1–U13 | 13 |
| Speech assessment | S1–S14 | 14 |

Sources include original research papers, official model/vendor guidance, original assessment manuals on institutional mirrors, W3C explanations and practitioner guidance. They are not 55 independent experiments. Abstract-only or overview-level evidence is explicitly limited in the memos. Failed pages, redirect-only content and duplicate page/PDF versions were excluded. No source establishes the current gateway's coaching quality.

The coordinating agent additionally reopened representative pivotal sources: G-Eval, MT-Bench, Anthropic's workflow/agent distinction, Sber structured output, the original AAC&U/NCA instruments and Whisper model card. The AAC&U short-answer exclusion and Sber's native `response_format.schema` were inspected directly. Report sources were opened by the coordinating agent, with specific details/accordion/reflow/label/status guidance inspected.

The uncertainty example is supported by the original [Hanley and Lippman-Hand article on zero numerators](https://jhanley.biostat.mcgill.ca/c607/ch08/zero_numerator.pdf), pp. 2–3 of the author-hosted copy. This supplementary statistical source is outside the 55-document thematic count. Its approximate 3/n upper bound illustrates uncertainty for independent sampled cases; it is not a production error-rate bound for hand-selected synthetic challenges.

## Material corrections from cross-review

1. The library example already connects proposal and benefit. Reframed its rewrite as an optional concision exercise rather than a detected weakness. The same principle applies to the existing contract fixture's generic budget advice: it is not a quality gold example.
2. Unified the proposed 120-case split to 40 development, 20 judge calibration, 60 locked acceptance cases. Coverage proposals are distinguished from partitions. Repeated runs are 12 preselected cases × 3, not new independent speeches.
3. Bound related speaker/source/task families to one split. Freeze metric definitions and gates after baseline, before acceptance; no holdout tuning disguised as validation.
4. Separated deterministic valid-ID/top-action checks from semantic interpretation checks. Code alone cannot reject every invented meaning attached to a real quotation.
5. Allowed empty recommendation lists, nullable priority selection and honest continuation without a fabricated focus. This is a future coordinated contract/public-mapping change.
6. Distinguished audio capture coverage from ASR lexical fidelity. Bounded omissions refer to the available transcript, with unknown when ASR integrity is doubtful.
7. Bound evidence to transcript revision/content identity. A regenerated `s0-q0` cannot safely reuse stale provenance.
8. Chose one server-issued exact contiguous span per finding for the initial contract. Adjacent multi-sentence candidates are a planned extension; disjoint multiple evidence IDs require a separate schema decision.
9. Added per-report/macro grounding, distribution and critical-error checks alongside pooled claim counts, preventing verbose correct reports from hiding a few bad reports.
10. Kept numerical gates, corpus sizes and editorial budgets explicitly provisional; literature findings and product proposals remain separate.

## Practical verification boundary

Passed artifact checks: five source-register counts and within-topic uniqueness; balanced HTML nesting; 19 unique IDs; 88 valid internal/local/external link targets (external availability established through source research, not a second automated crawl); no unresolved source placeholder; both inline scripts pass `node --check`; secret-pattern screening and `git diff --check`. These are artifact checks; no real model benchmark, human annotation, user study, provider spend or deployment is claimed.

The built-in file panel was asked to open the saved HTML plan. A separate browser-render attempt was refused by the browser URL policy because `file:` is blocked. No alternative browser route or protocol workaround was used. Browser rendering, mobile layout and interactive theme/disclosure behavior therefore remain visually unverified; source/static checks do not certify those behaviors. The report UI discussed in the plan is not implemented by this research task.

Future implementation must run its actual acceptance protocol, not reuse this research review as a successful quality result. The canonical roadmap is `docs/ai-quality-implementation-plan.html`; the memos supply evidence and alternatives, not four competing implementation contracts.
