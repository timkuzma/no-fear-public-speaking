# Feedback candidate rollout and rollback

This document governs the feedback-v2 candidate, not an external release approval or evidence of model quality. Source, prompts and public view must be released together. Preserve the single final worker, incremental worker, ownership checks, original media, durable jobs and existing provider reservations.

## Before release

1. Record the candidate Git revision, prompt artifact hashes, schema/rubric/dataset versions, actual provider routing/model/settings and the frozen baseline manifest. An alias/default is not an observed immutable model version.
2. Complete development comparisons, independent Russian-language human calibration and the frozen quality-gate decision. Freeze numerical targets before the first locked acceptance run. Record assessable denominators and critical failures separately; do not tune against acceptance failures while calling the set untouched.
3. Verify semantic support of each observation, rewritten facts/uncertainty, genre fit, helpful actions, question relevance/diversity and speech-versus-answer scope. Canonical spans and contract tests verify provenance, not entailment. Test ASR fidelity against authorized audio separately.
4. Complete reader tasks with the proposed participants, including mobile/zoom and distinguishing speech from answer evidence. Synthetic browser tests are engineering acceptance only.
5. Run Python/Node regressions and isolated browser flows, including sparse reports, unknown criteria, legacy reports, export, private playback, selected repeat, failure/retry and retained transcription. Run current backup/restore tests and old-code database compatibility checks.
6. Verify the real gateway supports the existing JSON-object response contract on a bounded synthetic input. No new provider schema mode, role, tool API or runtime critic is assumed. Every HTTP attempt uses `limits.provider_scope` and a durable reservation; do not bypass rolling caps for evaluation. Set explicit small run caps and retain unknown usage/currency as unknown.
7. Check the correct production hostname, active immutable image, private operator configuration, readiness, latest verified backup/restore and previous compatible image. Never replace a similarly named project on the shared host. Use the existing `scripts/production.py` release controller; no ad hoc copying into a running container.

Absent real model outputs, reviewers or participants, maintain a local candidate with explicit uncompleted quality gates. Successful synthetic/structural tests do not justify a claim of improved live-model quality or a production promotion.

## Additive storage and code rollback

Private question provenance is additive metadata; public questions remain strings and old stored reports remain readable. The exact migration and compatibility checks are described in `docs/ai-quality-contract.md`. Keep family `1` only after verifying old code opens the migrated database and preserves rows; an incompatible change needs a new family and its own recovery procedure.

Before promotion the controller stops the application, verifies an offline backup and rehearses restoring it into a separate location. After promotion, a manual rollback changes code/prompts while keeping current participant data. Do not restore an old database merely to revert a prompt. Do not regenerate old reports silently, fabricate consent, erase question/answer bindings, or discard successful ASR on report retry. Check legacy presentation after rollback, especially nullable focus and empty findings. If previous UI cannot explain a sparse new report, use the previous compatible backend with an appropriate compatible renderer.

## Pause and investigation

Pause new AI work through the existing operator control when a verified critical semantic issue appears: invented material fact, unsupported modality/personality assessment, wrong recording/question/answer scope, execution of injected instructions, or an imposed unselected requirement. Retain affected recordings/reports for owned review and keep playback/retry available. A deterministic validation failure should fail safely rather than fabricate success or start an automatic paid repair loop.

General events/alerts contain only safe codes, versions and counts. Existing usage records retain nullable tokens/attempt latency and prompt version; detailed evaluation traces belong in private files with restricted permissions. Never add transcripts, quotes, provider bodies, credentials or sensitive annotations to operational alerts. Track validation/job failures, unknown usage, feedback and investigation outcomes without interpreting usage caps as money or satisfaction as skill improvement.

Compare an optional offline critic with human labels before enabling it. Record precision/recall, unresolved disagreements, latency, attempts, usage and retention behavior. No additional production call is enabled solely because research used subagents.
