# Speech-feedback evaluation protocol

Version `speech-feedback-eval-v1`, 13 October 2026.

## Immutable baseline and scope

`evals/speech-feedback/baseline/manifest.json` freezes source/prompt/contracts at source revision `65f6904`; baseline snapshot was committed before candidate editing. SHA-256 files are verified before every baseline import. The snapshot has **no live outputs or measured human quality**. `scripts/evaluate_ai.py baseline-mechanical` injects fixed provider JSON into that original validator, never calls a model, and records acceptance/rejection, not semantic scores.

Observed original-validator probes: existing quote with a fabricated standalone main insight is accepted; empty findings are rejected; nonexistent quote ID is rejected; unsolicited criteria are discarded when none were selected. These are architectural observations in synthetic mechanical replay. They do not measure incident frequency or live semantic quality.

## Corpus, partitions and locks

The initial version has **120 separately authored synthetic task situations**: 40 development, 20 calibration, 60 locked acceptance. Each has a distinct source/task family, optional context, transcript/answer/question binding, explicit author expectations, exact source spans/hashes and limits of observation. Related challenge/polish/context/order variants stay with that case's family. The corpus has zero audio, zero real speakers and zero adjudicated human labels. Unique scenario families are a leakage control, not proof of statistical independence. A synthetic 590-second duration boundary fixture contains short text; it does not validate long speech/context or audio.

Twenty development challenge pairs contrast grounded feedback with fluent but wrong feedback, each shown in forward and reversed A/B order. Variants include wording polish, misleading topic, artificial early/middle/late placement, fact/negation changes, selected-but-unobservable criteria and genuine ambiguity. Author-constructed expected errors are seeded tests for evaluator behavior, not expert gold. No LLM judge results currently exist.

`audit` checks all file hashes and split metadata but reads case contents only in development/calibration. `freeze-gates` produces an evidence-backed gate artifact after operator-reviewed budgets, real baseline output and complete ratings from two independent reviewers. It stores SHA-256 links to private provider, rating and blinding-key artifacts; acceptance access rechecks their hashes. Acceptance access requires a gate artifact with `status=frozen_after_measured_baseline`, at least one baseline provider report, one human-reviewed report and two independent reviewers. Merely renaming proposed gates is not evidence: matching source artifacts are mandatory, and the coordinator attests actual human reviewer independence (software cannot prove identity). Do not use holdout cases for prompt exemplars or tune after reading them. Corpus authors necessarily saw the material; authors must not tune against acceptance. If leakage occurs, retire/rebuild affected families before claiming a holdout.

## Runs and artifacts

```sh
.venv/bin/python scripts/evaluate_ai.py audit
.venv/bin/python scripts/evaluate_ai.py baseline-mechanical --output /private/eval/baseline.json
.venv/bin/python scripts/evaluate_ai.py replay --artifacts /private/eval/reports.json --split development
```

Outputs containing transcripts/provider text require a private 0700 directory and 0600 files. The script refuses to chmod shared directories such as `/tmp`. Do not commit real responses, credentials, personal recordings or reviewer data. Keep dataset/prompt/context/rubric/model-alias/source hashes with each run; provider aliases do not establish an immutable backend version.

Real provider mode is opt-in, development-only, at most **6 HTTP attempts total**, no ASR, retry policy explicitly `LLM_MAX_ATTEMPTS=1`. It uses the existing durable `ai_attempts` ledger, `limits.provider_scope` and maintained reservation for every transmission. A thin existing-ledger adapter opens SQLite without creating tables or migrating production. Run only inside the existing container/kernel when using the live ledger. Additional per-run reserved-input/output work caps include failed/unknown attempts. They are conservative work counts, not money. The six-task example compares two report cases baseline/candidate plus questions for one case:

```sh
LLM_MAX_ATTEMPTS=1 .venv/bin/python scripts/evaluate_ai.py provider --live \
  --data-dir /data --case-ids dev-002-library,dev-004-quiet-evenings --include-questions \
  --max-attempts 6 --max-input-chars 120000 --max-output-tokens 18000 \
  --output /private/eval/provider.json
```

For an explicitly authorized diagnostic run, `--variants candidate --max-attempts 1` executes one chosen development report rather than repeating the whole comparison. It remains bounded; no generator–critic retry loop exists. Each call records prompt versions, source/system hashes and its request context privately. The parsed provider draft and usage are saved before report validation, so invalid-schema/ID failures can be diagnosed without another call. Draft capture does not bypass runtime validation and is never copied into public reports or general stdout.

Credentials come only from the existing private environment. No provider call occurs in ordinary audit/replay/tests. Only an authorized operator initiates `--live`; running the command successfully is not release acceptance.

## Human and judge procedure

Two independent Russian-speaking reviewers, ideally one speech/coaching practitioner, train on development examples, then independently rate anonymized baseline/candidate packets. `blind` produces identical report presentation shapes, randomized A/B, reverse views, blank ratings and a coordinator-only identity key. Source/prompt/model/schema labels are removed. Null focus and stylistic differences remain observable; blinding cannot erase genuine behavior. Never display the identity key to reviewers.

Reviewers inspect full supplied context and individual claims, with the separate rubric/annotation guide. They may abstain; empty ratings remain missing. Do not silently use audio or external facts unseen by the model. ASR review is a separate task with authorized audio/reference transcripts. Collect each criterion judgment, rewrite fact check and critical error independently. Adjudicate serious disagreements and retain reasons, original ratings and versioned changes.

`replay` supports both reports and questions, verifies new question evidence/text/source binding, and explicitly does not reconstruct missing provenance for legacy questions. These are contract checks, not semantic question-diversity measures.

The `ratings` command computes per-dimension linear-weighted agreement/kappa and per-critical-flag confusion, precision, recall and exact agreement. Reviewer 1 is a comparison reference, not automatic truth; comparing two humans is not a judge-accuracy estimate. Unknown/unfilled fields are excluded and counted separately. Reverse views/repeated trials are correlated diagnostics; aggregate preference at case/family level before uncertainty calculations. Report macro per-report grounding, claim-level support denominators and per-genre/slice counts. Do not claim superiority from a small mixed/uncertain comparison or use pooled claim counts as independent speeches.

`usage` reports task failure count, nearest-rank p95/median wall latency, token totals only when all usage is known, and unknown usage count. Monetary expense/currency remain null. Six calls cannot establish p95 reliability, typical-user capacity or billing. Three trials on 12 preselected calibration families is a later bounded reliability experiment, not 36 independent speeches.

## Gates and unfinished acceptance

`proposed-gates.json` records operational proposals (100% deterministic contract checks; zero observed critical failures; proposed 90% human grounding/actionability ≥2; proposed 95% seeded-failure judge recall). They are **pending** measured baseline/calibration, not scientific standards or achieved quality. Latency/work thresholds are not yet set. Freeze final gate definitions with baseline artifact hashes before first acceptance access; do not adjust thresholds to improve a seen holdout.

As of preparation, human reviewers and participants are unavailable. Prepare packets and continue deterministic implementation; human semantic acceptance, real audio fidelity and user-outcome trials remain incomplete. Do not run locked acceptance or production-enable a critic to bypass this gap. `critic-experiment.json` is an offline proposal; runtime does not consume it. Activate only after human-calibrated paired benefit, measured incremental work/latency, bounded failures and recording retention checks.
