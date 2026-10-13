# Annotation guide

Version `speech-feedback-annotations-v1`.

1. Read the actual transcript, segment identity/version, optional context, saved questions and bound answers. User topic is not speech evidence; a question is not a confirmed spoken answer. Capture coverage does not prove each recognized word is correct.
2. Separate known source words from inferred purpose, external facts and unavailable modality. Where negation, names, numbers or scope are materially uncertain, label `unknown`/`not_assessable`; do not fill gaps confidently.
3. For each substantive feedback claim, record its source span and one of `supported`, `unsupported`, `unknown`. Existence of a span is checked mechanically; its meaning is checked independently by you. A quote “стоимость не рассчитана” cannot support “вы назвали цену.” Multiple plausible useful interpretations may be allowed.
4. For each example rewrite, check every added fact, actor, amount, date, result, cause, negation and uncertainty. Rearrangement is allowed; invented achievements are a critical failure. An explicit `[реальная причина]` placeholder is a request, not a factual assertion.
5. Judge genre/context fit without a universal content checklist. A toast, a personal story and a proposal have different useful next actions. Unknown purpose permits narrower local wording feedback. Do not demand a business model simply because scenario/topic says defense.
6. Read each answer with its **persisted matching question**. Do not swap answers, treat generated questions as audience reaction or penalize honest uncertainty/clarification automatically. If question is absent, response relevance is not assessable.
7. Rate the seven feedback dimensions independently using rubric anchors. Identify a concrete next action; allow empty advice where justified. Label critical failures separately. Quote fluent-but-false reports are not “mostly correct” merely because well written.
8. For each generated audience question, check the actual point it refers to, whether it introduces an unsupported premise, whether the answer is already explicit in the speech, and whether the three questions add distinct useful facets. Rate sparse-input clarification separately from factual recall; a canonical ID does not prove relevance.
9. Keep reviewer ID pseudonymous, preserve original ratings and brief auditable reasons (no hidden chain-of-thought), then adjudicate disagreements. Do not overwrite disagreement with a model's self-confidence.

Blank `null` means unrated. `not_assessable` is an explicit abstention. Numeric ratings must be integers 0–3; critical flags boolean or abstention, never probability. Preference: `A`, `B`, `tie`, `not_assessable` or null. Forward/reverse views belong to the same pair/family. Do not count them as independent cases.

Author expectations in the synthetic corpus and deliberately bad challenge labels are provisional test annotations, not human consensus. Reviewers should record where those expectations are too narrow or wrong. Keep related corrections/variants in the same split, freeze hashes after approved changes and before opening acceptance. Real recordings require actual authorization/de-identification and source/audio provenance; no such samples are included here.

The candidate publisher withholds unreviewed rewrite examples. Evaluate raw model drafts and public compiled reports as separate artifacts; do not treat a null published example as a successful fact-preservation rating. Mark that dimension not_assessable when no example exists. Observations/actions still need grounding and actionability assessment.
