# Speech feedback v2 contract

This documents implemented **candidate** behavior, not a claim of improved live coaching quality. The frozen baseline is `evals/speech-feedback/baseline/`; changing a prompt or schema requires a new artifact version and evaluation. Structural validation establishes provenance, not entailment, factual truth, genre fit or actionability.

## Context and boundaries

`server.ai.build_context(operation, config, segments)` compiles a server-owned `speech-context-v2` envelope. The runtime uses one tool-free questions call and one tool-free report call, existing system/user JSON messages, JSON-object mode and the same durable provider reservation/retry/timeout boundaries. No runtime critic, independent production agent or new service is added.

- `operation`: `questions` or `report`.
- `prompt_version`: `questions-v2.1` or `speech-feedback-v2.2`; `rubric_version`: `contextual-text-v1`.
- `transcript_revision`: SHA-256 of compact UTF-8 JSON of ordered `{index,kind,text}` segments. Individual segment revisions hash their exact UTF-8 text. Whitespace changes change the revision.
- `context`: optional user topic/history metadata, scenario and explicitly supplied criteria. Optional API-validated `repeat_focus` stays separate from formal criteria. It represents a selected next-practice action, not a compulsory scorecard.
- `segments`: one original `speech` and up to three saved, confirmed `answer` segments, measured durations and origin/revision metadata. Text is not silently retyped or normalized. `asr_model` is the actual current transcription call's model alias where available; cached/live sources remain null unless known. Never label a cached transcript with today's configured model. Known server/evaluation capture interruption (`capture_complete:false`) and ASR doubt (`asr_quality:uncertain`) are passed separately; unknown runtime metadata stays unknown. Neither field can upgrade lexical completeness. These are internal inputs, not new public client assertions.
- `saved_questions`: actual persisted question text mapped by answer segment index, with source provenance when available. A legacy question without provenance remains usable and is explicitly null. Questions never become spoken evidence or word-count input.
- `evidence`: canonical contiguous original-text spans with `id`, `segment_index`, `origin`, `text`, `transcript_revision`, `start_char`, `end_char`. Offsets are Python Unicode code points, not bytes, JavaScript UTF-16 offsets, timestamps or word alignment. Source playback is segment-level only.
- `requested_criteria`: user labels split on semicolons/newlines, at most 12, with server-issued unique IDs. Empty user criteria means an empty requested list, never inferred requirements.

Single-span IDs are `sN-qM`. Optional `sN-pM` spans encompass adjacent original statements when their exact contiguous range fits the 900-character quote cap. They preserve punctuation and intervening whitespace; disjoint snippets are never joined into a quotation. A version/hash is necessary because a short ID alone is not globally unique.

Topic/scenario supply weak context only. Feedback reads actual speech and its tentative communicative purpose. A toast does not require a budget, a narrative does not require an opening thesis, and a short answer does not require an introduction. Unknown purpose permits local wording feedback without a forced genre diagnosis. Model output in every field must avoid manufacturing numbers, achievements, events, listener identities or external facts; fresh freeform examples are currently withheld as described below. Attribution in a speech is not independent factual verification.

## Prompt revisions and rewrite containment

Exploratory `v2.0`/`v2.1` outputs exposed quotation-scope errors, unsupported sincerity/listener-atmosphere claims and invented facts inside modal examples. The `v2.1` instructions required every clause about spoken content to be supported by the chosen excerpt, with a contiguous relational span or a narrower observation. They prohibited claiming sincerity, speaker feelings and actual listener reactions. Nevertheless, a later `v2.1` example still invented time savings and access to books after classes. Prompt wording alone did not establish fact preservation.

The current report prompt `speech-feedback-v2.2` requests `example:null`. The compiler retains strict raw type/length validation, then withholds every freeform rewrite in **new** reports under `publisher_policy:withhold_unreviewed_rewrites-v1`. Public `example` is null, compatibility `text` contains observation/action only, and the primary insight remains the chosen action. Raw drafts are not persisted in public reports/jobs; scoped private evaluation capture can preserve them separately. Existing stored reports and their examples remain unchanged, and the UI retains legacy example support.

This contains one risky field. It does not verify factual truth, entailment or utility of observation/action and does not prevent unsupported content in those fields. Raw model failure and compiled-report behavior must be scored separately: hiding an example is not evidence that the model stopped inventing facts. Semantic human acceptance and a subsequent versioned rewrite experiment remain necessary before enabling generated rewrites. No extra critic, regex truth gate, configuration switch or paid automatic repair is added.

Complete application-owned JSON examples remain compiler-checked: a toast with a contiguous two-statement basis, sparse text/non-observable criteria, explicit negation under a selected criterion and an optional combining action with a null rewrite. They are protocol examples, not user requirements or semantic gold labels. Do not copy their facts/IDs into another speech.

The question policy discourages asking for an already explicitly given fact and uses direct listener-to-speaker wording. Question revision `questions-v2.1` still needs its own live semantic check; a prior version's gateway success and mocked tests do not establish its quality.

## Closed provider drafts

The application rejects additional or duplicate JSON keys, invalid types, missing keys, invalid IDs, count/length overflow, duplicate criteria and out-of-range/bool primary indexes. Fresh provider calls accept v2 only; compatibility is for **stored** reports, not silent acceptance of an obsolete draft schema.

Questions: exactly `{questions:[{text,evidence_id}, ...]}`, exactly three distinct normalized texts, each 8–600 characters and one known speech evidence ID. A sparse speech may support distinct clarifications of one point; ID validation does not prove their semantic relevance.

Report:

```json
{
  "strengths": [{"title":"...", "observation":"...", "evidence_id":"s0-q0"}],
  "recommendations": [{"title":"...", "observation":"...", "action":"...", "example":null, "evidence_id":"s0-q0"}],
  "primary_recommendation_index": 0,
  "criteria": [{"criterion_id":"c0", "status":"unknown", "basis":"unknown", "reason":"...", "evidence_id":null}]
}
```

The draft shape still validates `example` as null or a bounded nonempty string so malformed provider responses fail; the publisher always emits null for this field under the containment policy. `strengths` allows 0–2; `recommendations` allows 0–3. `primary_recommendation_index` is zero-based or null. Empty recommendations require null by index validation. A report may have recommendations but no selected main action. There is no model-authored top-level insight or score.

Caps shared by prompts and validators in `server/feedback_prompts.py`: title 180, observation 1200, action 700, example 700, criterion reason 700, question 600, evidence span 900 characters. These are hard maxima, not target lengths. Prompt guidance asks for concise material, usually no more than 250–450 words overall and much less for sparse speech; no minimum word quota or mandatory number of findings is imposed. Provider output-token limits still apply and a truncated completion fails without publishing.

## Criteria and observability

`status`: `met|partial|not_met|unknown`; `basis`: `present|absent|unknown`; exactly one assessment per requested ID and the original user label is retained.

- `present` requires a canonical evidence ID and a non-unknown status. Partial/non-met can describe an explicit statement or contradiction, but a quote ID does not prove that interpretation. Semantic evaluation remains separate.
- `unknown` requires null evidence and unknown status.
- `absent` accepts no fabricated quote and initially permits partial/non-met draft statuses, but the compiler **downgrades them to unknown** with a concise reason. Current ASR cannot certify that every word was recognized. Capture manifests, decoded duration and complete chunk delivery do not establish lexical completeness. All current sources carry `lexical_completeness=unknown`; there is no client-supplied flag to bypass this.
- A conservative lexical heuristic recognizes common acoustic/visual/psychological criterion labels and compiles them to unknown rather than replacing the requested criterion. This is not a complete semantic modality classifier; ambiguous wording can conservatively remain unknown. Prompt instructions must also abstain on non-observable criteria missed by the heuristic.

Neither absence elsewhere nor real-world lack of knowledge can be established from a single excerpt. The validator cannot reliably detect hidden absence reasoning in an otherwise `present` observation, invented example facts or unjustified conclusions. Human semantic review and real-provider comparisons are required before asserting quality gains.

## Public report and private persistence

New reports have `schema_version:2`, `primary_recommendation_index`, structured observation/action fields and a null example, server-substituted quote provenance and `transcript_segments`. Existing `text` is compiled for legacy consumers; `transcript` remains an ordered speech/answer concatenation for export. Public `insight` is derived **only** from the selected validated recommendation's `action`, otherwise null. It is not another independently generated model conclusion.

Duration, recognized word count and descriptive words/minute remain locally calculated. Audience questions do not count as spoken words. WPM includes silence/ASR defects and does not measure articulation, voice, gestures, emotion or psychological confidence. There is no global grade/radar.

An additive nullable `practices.question_provenance` column stores private question evidence, source revision, prompt/context versions and producing chat-model alias. Public practice/job question results remain string arrays; the private column is not serialized. On report continuation the worker rechecks question text, canonical ID, exact source span, speech revision and origin. Changed/fabricated cached provenance fails safely, preserving media/transcripts. A pre-v2 question set with no provenance still continues; no history rewrite or forced regeneration is performed. Transcript successes persist before provider report failure.

Reports persist their version/provenance and segment revisions inside the existing owner-only report JSON. Known actual ASR model aliases are listed; unknown cached/live origins remain unknown. Aliases are not immutable upstream provider revisions. Existing stored reports are untouched; old application code can open the additive database and code-only rollback preserves current records. Restore checks cover this compatibility separately.

## Validation and remaining acceptance

`tests/test_ai.py`, `tests/test_question_context.py`, `tests/test_feedback_contract.py` cover HTTP retries/usage/error redaction, strict closed drafts, count/type/length gates, primary mapping, exact source revisions/offsets, relational spans, sparse output, conservative absence/modality handling, question/answer separation and durable private provenance. Their provider is mocked. Passing them does not establish live model behavior, user comprehension, ASR accuracy, factual entailment or comparative coaching quality.

Use the evaluation materials and locked-set protocol for those distinct claims. A structural pass must not fill in missing human labels, infer provider billing/currency, or silently enable a second AI critic.
