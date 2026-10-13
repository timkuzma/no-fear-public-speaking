# Feedback 2.3 release validation

13 October 2026. This is a bounded development check, not blind human acceptance.

## Problem and resulting behavior

The inspected latest production report contained zero strengths and one recommendation about the selected filler-word focus. Its selected one-word source did not support the alleged word list; some alleged source words were absent. The private speech was not added to fixtures or committed documentation.

The new report prompt (`speech-feedback-v2.3`, rubric `contextual-text-v2`) examines general speech/answer feedback independently of optional criteria. Trusted coaching context is `speech-coaching-v1`. Questions use `questions-v2.2`. Transcript punctuation is not treated as speaker behavior. Evidence appears once as the canonical source; explanations/actions use their own wording. Inline quoted source words still must belong to selected evidence. This is literal containment, not semantic certification.

The waiting view contains one preparation heading plus a useful history continuation. Owners can explicitly update an older report without recording again. Previous report/media remain available until success; old successful job results retain the prior report. Current/active refresh requests do not create duplicate work.

## Real provider checks and model selection

Three authored synthetic cases are in `evals/speech-feedback/regressions/feedback23.json`: a service pitch with a vague filler-word focus, a personal drawing story, and a scheduling proposal with a non-observable confidence criterion. They are development regressions, not frozen acceptance data or human gold. They contain deliberately circular reasoning as one observable editing opportunity.

The final selected alias is `gpt-5.4` through the existing configured provider. The final report system-prompt hash matches all three successful `reports-ready-actual.json` artifacts; the final questions system-prompt hash matches all three successful `questions-release-actual.json` artifacts. Each passed closed schema, exact source IDs/offsets/revisions, and mechanical provenance checks. Agent inspection found distinct questions and general, actionable findings beyond the selected criterion. Reports contained two strengths and one or two recommendations; there is no mandatory count in production.

Earlier exploratory checks are retained rather than counted as final passes: configured `gigachat-3-pro` and listed `gigachat3.5-432b-a28b` produced rejected quotation/scope errors; GPT-4.1 passed initial structural checks but gave weak or repetitive feedback; GPT-5.4 needed prompt refinements and rejected faulty quotations on some runs. GPT-5.1 also produced rejected quoted self-check/source phrases. Claude Sonnet 4.5 did not produce accepted JSON drafts. Listed GPT-5.5 and temporal-provider/gpt-6-sol aliases returned unavailable. A catalog entry alone is not endpoint compatibility, nor proof of an immutable upstream model revision. This was adaptive debugging, not a randomized cross-model benchmark.

Each evaluation run used the existing in-container durable ledger with maximum six attempts, 250,000 input characters and 18,000 reserved output tokens, one HTTP attempt per task, and synthetic text only. Actual final report/question runs used three requests each. No ASR, real-user transcript submission, production critic or extra runtime generation stage was introduced. Two earlier harness failures occurred after a provider response; they remain ledger attempts and are not quality passes. Provider billing/currency is not established by these work counters.

Private raw/compiled artifacts, usage, run IDs, source hashes and `release-evidence.json` are under ignored `outputs/test-artifacts/feedback23/`, outside public content. Failed drafts are not public reports. Baseline hashes were verified during the provider runs; immutable `65f6904-frozen` snapshots and the locked corpus were not edited.

## Application checks

- Python: 191 tests passed, including ownership/CSRF, versioned refresh idempotency, prior report/job/media preservation on success/failure, single-criterion general feedback, and inline quote mismatch.
- Node: app/API syntax and frontend report checks passed. Existing focus, escaping, source/export, empty/legacy report and repeat behavior remain covered.
- Native browser, isolated local fixture: recorded synthetic audio, received a legacy report, clicked update, observed one waiting heading, then opened the updated report's original media without re-recording. Screenshots are in the ignored artifact directory. This is a UI test, not provider-quality evidence or a physical microphone test.

Two independent Russian-speaking reviewers and participant comprehension checks remain unavailable, so formal semantic acceptance remains unfinished. The user authorized deployment and will assess a real practice. Neither these six smoke checks nor agent inspection guarantees every future advice item is useful or semantically entailed. Generated rewrite examples remain withheld.
