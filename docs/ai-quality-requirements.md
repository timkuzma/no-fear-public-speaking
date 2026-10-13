# Speech feedback quality requirements

Version: `speech-feedback-requirements-v1`, 13 October 2026. This implements the research specification as contracts and evaluation materials. It does **not** assert achieved live coaching quality. Source rationale and transfer limits remain in `docs/research/ai-quality-methodology.md` and `speech-assessment-framework.md`.

| ID | Product requirement | Mechanical evidence | Required semantic/user evidence |
| --- | --- | --- | --- |
| Q1 | Interpret actual speech, not a universal presentation outline | Source/quote revision checks | Entailment, purpose and genre review |
| Q2 | Preserve facts, agency, negation and uncertainty in examples | Exact source-bound spans | Humans check every substantive rewrite claim |
| Q3 | Link main focus to an existing recommendation; allow no focus | Nullable index and derived insight | Useful priority and feasible next action |
| Q4 | Formal criteria are user-selected only | Exact criterion identity/count | Capability/status judgment, including mixed criteria |
| Q5 | Short/sparse/uncertain text does not force praise or advice | Empty bounded finding lists | Modest, nonjudgmental scope |
| Q6 | Speech, saved question and confirmed answer are separate | Segment/source/hash/question binding | Correct interpretation of response and uncertainty |
| Q7 | Whole-speech absence is separate from a positive quote | Explicit basis/capability policy | Full reliable text scope; unknown under material doubt |
| Q8 | No voice/gesture/emotion/psychological claims from text | Documented capability boundary | Adversarial real-model and human checks |
| Q9 | Every field is untrusted data | Closed output schema and isolated data sections | Live injection-resistance tests; mock transport is insufficient |
| Q10 | A report is readable and supports a practical repeat | Legacy/new rendering, private playback, export and focus tests | Readers find/understand the focus and try it |
| Q11 | Three audience questions are relevant and meaningfully distinct | IDs, count, persisted provenance | Relevance/diversity; paraphrase duplication is semantic |
| Q12 | Generated claims do not become external world-truth | No external-fact workflow in pipeline | Distinguish stated belief from verified fact |

The internal 0–3 rubric measures **feedback quality**, never a public speech score. A valid quote proves existence, not entailment; complete capture proves transport coverage, not recognition of every word. User topic is contextual history metadata. No new mandatory fields, runtime agent service or automatic critic loop is introduced.

Release acceptance requires measured baseline, trained independent human ratings, final metric/gate freeze, then the untouched holdout. The included 120-case text corpus is separately authored synthetic material, not recordings, expert gold or a statistical population sample. ASR and typical-user outcome validation remain unavailable until authorized real recordings/participants are supplied.
