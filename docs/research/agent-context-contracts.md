# Agent context, orchestration and contracts research

Research date: 13 October 2026. This is an implementation specification and research record, not a statement that the proposed contracts or quality gates already run in production. Thirteen distinct primary web documents were opened and their relevant content checked. Failed Sber REST/gRPC pages and the Model Spec redirect are excluded from the count.

## Decision

Keep a deterministic workflow in the existing Python application. Use specialized model calls for audience questions and feedback, with server-owned context preparation, validation, persistence and rendering. Research can benefit from multiple autonomous agents because discovery is open-ended; assessing a saved speech has predictable inputs and outputs. Adding independent production agents is an experiment requiring measured benefit, not a requirement inferred from doing this research with subagents. [Anthropic: Building effective agents](https://www.anthropic.com/engineering/building-effective-agents), [Anthropic: Multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system).

First improve the report call's evidence, examples and evaluation. Evaluate a separate semantic critic offline if unsupported interpretations remain frequent. Enable it online only if a held-out, human-reviewed comparison demonstrates an improvement that justifies additional latency, failures and provider expenditure. Do not introduce an agent framework, vector database, browsing agent, persistent model memory or a new service for this pilot.

## Current application, verified from owning source

Inspected `server/ai.py`, `server/worker.py`, `server/live.py`, `server/store.py`, `tests/test_ai.py`, `tests/test_question_context.py`, `docs/llm.md` and `docs/api-contract.md`.

| Stage | Actual behavior | Boundary to preserve |
| --- | --- | --- |
| Admission | Authenticated, owned practice; private uploaded media; durable final/live queues | A model never determines ownership, admission, deletion or quota |
| Incremental ASR | Separate serialized worker, independent mono 16 kHz WAV chunks; successful contiguous prefix shown | A prefix is not a complete speech |
| Final ASR | Reuse only bound, complete manifest with matching duration; otherwise whole-recording ASR | Save original media; a failed report must not erase successful transcription |
| Questions | One `/chat/completions` call returns exactly three distinct `text/evidence_id` objects | IDs refer only to server-issued speech spans; public result is strings |
| Answers | Final worker binds answer index to persisted question | Audience question is context, never spoken evidence or word count |
| Report | One `/chat/completions` call sees speech, answers, question context, canonical quotes and explicit criteria | Server validates IDs and calculates metrics locally |
| Publication | Worker persists validated report then marks job successful | Raw provider strings are not executable HTML or trusted control data |

The current chat payload has one application-owned `system` message followed by JSON training data in one `user` message. It uses temperature 0.2 and `response_format: json_object`; it does not send a `developer` message, tool definitions, autonomous delegation or conversational memory. Default model names are `gigachat-3-pro` and `whisper-large-v3`; source defaults are not proof of current operator configuration or provider capabilities. Prompt version is `pilot-evidence-v5`.

Existing protections include bounded inputs/output bodies, exact quote or canonical-ID checks, original criterion labels, unknown status, server-owned duration/word counts, private media and safe error messages. Existing mocked tests verify these mechanical protections; they do not establish semantic quality on real model responses.

### Quality gaps to close

1. A valid evidence ID proves that a span exists. It does not prove that the interpretation follows from the span, that a question is relevant, or that the recommendation is useful. Groundedness needs semantic and human checks alongside code checks. [Anthropic: Demystifying evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents).
2. `insight` is currently a separately generated bounded string without evidence or linkage to a validated recommendation. A useful-looking top action can contradict the grounded items.
3. The report prompt requests 1–3 strengths and recommendations, while `_findings` accepts 1–5; report objects do not consistently reject extra keys. Align writer and validator contracts. Closed object schemas require both required properties and an explicit extra-property policy. [JSON Schema: Object](https://json-schema.org/understanding-json-schema/reference/object).
4. Question evidence IDs are checked and then discarded; persisted/public questions contain strings only. Keep private provenance if question/report debugging or revision auditing is required, without adding fields to the meeting interface.
5. Segment-scoped quote IDs are stable only for a specific transcript. They need a transcript revision binding before correction, regeneration or cached agent handoff is supported.
6. A missing item cannot be proved by citing an arbitrary existing sentence. Absence conclusions need complete-input coverage and an explicit user requirement; the default response to non-observable criteria is `unknown`.
7. Current free strings make it hard to distinguish a speech observation, an inference and a proposed rewritten example. Internal structure can improve validation while preserving a simple report interface.

## What each model receives

All model stages receive a freshly assembled bounded context. A model call knows only the messages sent in that request; it does not automatically know the practice UI, earlier jobs, other agents' work or the account's history. Information shared between calls must be selected and serialized by application code. Maintain a small, relevant context rather than forwarding full agent conversations or unrelated history. [Anthropic: Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents).

| Context layer | Owner | Contents | Allowed authority |
| --- | --- | --- | --- |
| Application instructions | Code/reviewed prompt artifact | Task, language, epistemic limits, evidence rules, output contract, examples | Model behavior; never account authorization |
| Server facts | Backend | Bound speech/answer indexes, measured duration, transcript revision, quote IDs, criterion IDs | Validated factual inputs; no instructions embedded in strings |
| User context | User | Optional topic, selected scenario, explicit criteria | Context and selected requirements, subject to product capability limits |
| Speech/answer transcripts | ASR, optionally corrected through a future owned flow | Actual recognized text | Untrusted source material to analyze |
| Audience questions | Prior model output, persisted by server | Question paired with an answer | Untrusted context; never speech evidence |
| Draft findings | Prior model output | Typed claims, actions, selected evidence | Untrusted candidate output; not new facts |
| Validation results | Deterministic code / calibrated reviewer | Error codes, valid references, semantic review annotations | Gate to publication; no authority to change source speech |

Do not interpolate user text, transcripts, previous model output or fetched content into the application instruction message. JSON serialization separates values syntactically, but does not make semantic injection impossible. Keep every model stage tool-free for this use case; credentials, file paths and other users' data remain unavailable. [OpenAI: Agent safety](https://developers.openai.com/api/docs/guides/agent-builder-safety), [OWASP: LLM01 Prompt injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/).

Message roles are provider contracts. OpenAI documents developer instructions taking precedence over user input; Claude exposes application instructions through a separate `system` parameter; Google uses `systemInstruction`. These are not portable wire formats or universal guarantees. Preserve the existing gateway's supported system/user arrangement until a real capability test verifies any change. [OpenAI: Prompt engineering](https://developers.openai.com/api/docs/guides/prompt-engineering), [Claude: Prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices), [Google: Use system instructions](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/prompts/system-instructions).

## Proposed internal contracts

These are conceptual types to implement with the project's ordinary Python validation. They do not require a schema library, a new frontend form or changes to the existing public Report shape. Length/item caps must be specified once and used by both prompt builders and validators.

```text
ContextEnvelope
  schema_version: fixed application-owned string
  operation: questions | report | semantic_review
  prompt_version: fixed application-owned string
  transcript_revision: server-issued identifier for exact analyzed text
  context: {scenario, topic, purpose?}
  segments: [SpokenSegment]                         # one speech, 0–3 saved answers
  evidence: [EvidenceSpan]                          # server-owned exact text
  requested_criteria: [Criterion]                   # empty unless user selected

SpokenSegment
  segment_index: 0 | 1 | 2 | 3
  kind: speech | answer
  text: nonempty bounded string
  duration_seconds: finite positive measured number
  question_context: optional bounded string         # answer only, never evidence

EvidenceSpan
  id: server-issued string
  segment_index: existing segment index
  text: exact contiguous source span
  revision: matches ContextEnvelope transcript_revision

Criterion
  id: server-issued string
  label: original user-selected text

QuestionDraft
  text: bounded nonempty Russian question
  evidence_id: one existing speech evidence ID

FindingDraft
  title: short connected Russian heading
  observation: specific interpretation of supplied speech
  action: optional specific next-practice action
  example: optional proposed wording, preserving known facts
  evidence_id: one existing speech or answer evidence ID

ReportDraft
  strengths: 0–2 FindingDraft items
  recommendations: 0–3 FindingDraft items
  priority_recommendation_index: valid recommendation index | null
  criteria: exactly one CriterionAssessment per requested criterion

CriterionAssessment
  criterion_id: one requested criterion ID, unique
  status: met | partial | not_met | unknown
  reason: brief explanation, no invented measurements
  basis: transcript_presence | bounded_absence | not_observable
  evidence_id: existing evidence ID or null under documented basis rules
```

Both empty strengths and empty recommendations are proposed contract changes. If recommendations are empty, priority_recommendation_index is null; the server renders an honest limitation/ordinary continuation rather than a fabricated coaching focus, and suppresses focus-specific repeat controls. This requires an explicit legacy/public mapping decision. The 0-strength allowance means: do not force a model to invent praise for unintelligible, hostile or insufficient material. If there is too little usable recognized speech for a report, retain the recording and return an honest processing outcome. Do not turn `NO_SPEECH` into an artificial report.

`purpose` is optional context available only if explicitly supplied or cautiously inferred from the speech. It must not create a pre-recording checklist or require onboarding users to fill out additional fields. Broad editorial lenses may guide reading, but become reported criteria only when selected by the user. Topic is history metadata and context; it is not proof that specific content occurred.

For `bounded_absence`, require an explicit observable user criterion, a complete transcript revision and a reason limited to that transcript. Never use it to claim absence of real-world knowledge, lack of preparation or psychological traits. If the implementation cannot distinguish omission from ASR loss or unsupported interpretation, return `unknown`. This entails a versioned internal/public mapping change; do not silently weaken current evidence validation.

Server compilation should derive public `insight` from the selected validated recommendation's action/example; it should not ask for a separate unsupported top-level conclusion. Compile observation/action/example into the existing `text` field and substitute quote/index from server data. Do not add provider-created metrics or a numerical overall score. Private provenance may retain transcript revision, selected IDs and prompt versions; its persistence and retention require an additive, reviewed migration if the present schema cannot store them.

Strict output schemas constrain shape, not truth. OpenAI's JSON mode does not ensure schema adherence. Official GigaChat schema output uses its own `response_format.schema` shape and distinguishes v1/v2 request/response structures; the current OpenAI-compatible gateway is not verified to implement those native features. Test compatibility on synthetic inputs before selecting schema mode; retain deterministic server validation in either mode. [OpenAI: Structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [Sber: Structured data generation](https://developers.sber.ru/docs/ru/gigachat/guides/structured-output).

## Minimal workflow and optional critic experiment

```text
Owned saved recording
  -> complete live ASR or whole-recording ASR
  -> persist transcript
  -> application context builder + canonical evidence
  -> questions call (when enabled) -> validate -> persist -> meeting chat
  -> save reviewed answers -> bind persisted questions
  -> report call -> deterministic validation -> compile public Report
  -> persist -> publish in existing report route
```

A research-only critic sees the complete bounded transcript, requested criteria, original canonical spans and the draft. It returns a closed list of finding indexes and issues (`unsupported_claim`, `wrong_scope`, `invented_fact`, `non_observable`, `generic_action`, `contradiction`), with relevant valid evidence IDs or a bounded-absence reason. It cannot approve its own new facts or replace speech. Evaluate critic precision and recall against human labels; a second LLM is not an independent ground-truth oracle. [Anthropic: Demystifying evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents), [NIST: Generative AI Profile](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf).

If the critic later passes the experiment gate, code—not a model manager—controls a fixed maximum of one review and one repair. Repair receives the same original evidence/context plus typed issue codes, then passes every validation again. A second invalid result fails safely with saved media and an explicit retry. A failed mandatory critic means no publication; do not silently bypass the gate. Define the added budget, whole-job deadline, persisted stage and restart behavior before enabling. Do not launch an unbounded evaluator/optimizer loop. Multi-agent research token ratios published by Anthropic describe their own system and are not a cost estimate for this product. [Anthropic: Building effective agents](https://www.anthropic.com/engineering/building-effective-agents), [Anthropic: Multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system).

## Failure, versioning and cost requirements

- Preserve exactly one final-job worker and one incremental-ASR worker in one application process. No extra worker processes sharing SQLite.
- Reserve provider work before every HTTP attempt under `limits.provider_scope`; count retries, invalid results and unknown outcomes. Use present bounded transient retries; semantic/schema failures do not trigger automatic paid repairs until the repair experiment is explicitly enabled and budgeted.
- Do not retranscribe successful segments on report retry. Persist final-stage artifacts before advancing; ownership and input revision are rechecked when using cached artifacts.
- Keep unknown usage/currency unknown. Maintain nullable token counts, attempt status/latency, operation and prompt version. Never call rolling work caps a monetary spend cap.
- Add independent `questions_prompt_version`, `report_prompt_version`, `context_schema_version`, `report_schema_version`, `rubric_version`, `asr_model` and `chat_model` to private provenance when implemented; report version should identify the actual producing job, not a frontend build.
- Model alias upgrades, ASR changes, schema changes, example changes and prompt edits all require regression evaluation. Store synthetic/redacted fixtures in source; do not commit real private recordings, credentials, transcripts or raw traces.
- Instrument content-free reason codes and rates. Private eval artifacts must be owned, access-controlled and retained deliberately; public/general logs contain no raw transcripts or provider output.
- Roll back prompt/code behavior without erasing current media/data; old reports remain readable. Any new internal contracts require explicit legacy serialization rules.

## Required materials and implementation order

| Stage | Materials to prepare in this chat | Practical completion gate |
| --- | --- | --- |
| 1. Freeze baseline | Current prompt snapshots, provider capability matrix, actual payload capture using synthetic inputs, current tests/results | Every input source and current limitation is documented; no private source material exported |
| 2. Context and schemas | Reviewed contracts, cap table, transcript revision/evidence binding rules, legacy mapping, proposed migration | Questions/answers/reports cannot exchange or promote untrusted text into instructions; schema/prompt caps agree |
| 3. Prompt artifacts | Russian common policy plus independent questions/report prompts; 3–5 diverse synthetic examples per task as an experiment | Examples include sparse speech, non-pitch genre, explicit criteria, unsupported acoustic criterion and Q&A context; no forced content template |
| 4. Deterministic gates | Closed-key validation, reference checks, criterion completeness, main-action linkage, public compilation and escaping | Malformed and fabricated outputs are rejected; no-provider fixtures remain fast and deterministic |
| 5. Quality evaluation | Human-labeled held-out corpus, semantic rubric, repeated trials, blind baseline/candidate comparison, cost/latency report | Critical unsupported claims reviewed individually; semantic quality exceeds agreed baseline without regression in privacy/recovery |
| 6. Optional critic trial | Offline critic contract, human calibration labels, false-positive/negative analysis and bounded repair experiment | Enable online only after measurable incremental benefit; failure and budget paths tested first |
| 7. Pilot release | Separate browser fixture origin, synthetic provider smoke test, prompt/schema versions, rollback and content-free monitoring instructions | Practical UI reading/repeat task works; checks pass; local/pushed/external release status reported separately |

Example counts and experimental thresholds are local proposals, not published universal quality standards. Claude's guidance supports relevant, varied examples; actual example quantity and wording must be tested on this product's gateway/model. [Claude: Prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices).

## Acceptance cases

| Case | Expected result | Check type |
| --- | --- | --- |
| Topic mentions AI; speech discusses a library without AI | Questions/recommendations never attribute AI to the speaker | Human semantic + regression fixture |
| Narrative, toast, technical explanation, short argument | Feedback responds to actual purpose; no universal pitch checklist | Blind human review across genres |
| Speech contains instruction to ignore rules or return fake high marks | Analyze spoken content as data; preserve contract and evidence rules | Adversarial fixtures + real model evaluation |
| Correct quote ID attached to an unrelated conclusion | Mechanical validation alone does not count as semantic success | Human-labeled counterexample; critic calibration |
| Question mentions a number absent from answer | Number is not counted as spoken or cited as answer evidence | Unit/integration |
| Empty criteria | No generated rubric rows or score appear | Unit + browser |
| Criterion asks for gestures, voice or confidence | `unknown` with honest reason; no inferred psychology | Unit + live-model fixture |
| Explicit content criterion is omitted | No arbitrary quote used as proof; bounded omission only with complete transcript contract | Semantic review + contract |
| Top action contradicts a recommendation | Compiler linkage prevents independent top action | Unit + semantic review |
| Four or five findings emitted under 1–3 contract | Reject under new contract; legacy report rendering remains supported | Unit |
| Missing tail/stale session/failed live chunk | Full saved recording ASR fallback; never publish prefix as full speech | Existing live integration + regression |
| Report call fails after successful ASR | Saved transcript/media reused; explicit retry resumes report | Integration |
| Unknown timeout outcome/429/repair failure | Every attempt accounted/reserved; no invented billing; media retained | Mocked HTTP + integration |
| Critic absent or disabled | Baseline path remains finite and tested | Configuration/integration |
| Cached draft revision differs | Reject reuse and rebuild bound context | Unit/integration |
| Provider strings include HTML/script | UI displays escaped text; no execution | Browser fixture |

Before runtime implementation, run relevant existing Python checks, Node syntax checks for touched modules, and actual browser flows. For research-only documentation, link/source review and comparison against source code are the meaningful checks. Load testing ordinary endpoints cannot establish real model quality or generation capacity.

## Source registry

Every item below was opened, not merely discovered in a search snippet. Access date: 13 October 2026. They are distinct documents, not thirteen independent empirical validations of this product. Provider engineering guidance is useful but often reflects the provider's own models and examples; transfer to Russian speech/gateway behavior is a hypothesis to test.

| ID | Primary source | Supports | Limitations |
| --- | --- | --- | --- |
| A1 | [Anthropic — Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) | Workflow/agent distinction, simple baseline, gated chaining, finite loops | 2024 architectural guidance; page itself notes tooling has changed; no public-speaking trial |
| A2 | [Anthropic — Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) | Relevant bounded context, instructions/examples/tool separation | Engineering guidance, not an exact recipe for the configured model |
| A3 | [Anthropic — How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) | Delegation contracts, coordination/reliability costs, research suitability | Its reported improvements/token ratios belong to its research workload |
| A4 | [OpenAI — Prompt engineering](https://developers.openai.com/api/docs/guides/prompt-engineering) | Instruction/input role distinction, context structure, prompt versioning and evals | OpenAI role/API behavior cannot be assumed for GigaChat gateway |
| A5 | [OpenAI — Structured model outputs](https://developers.openai.com/api/docs/guides/structured-outputs) | JSON mode vs schema compliance; refusal/incomplete-response handling | Compatible model subset and API-specific schema support; shape is not semantic truth |
| A6 | [OpenAI — Safety in building agents](https://developers.openai.com/api/docs/guides/agent-builder-safety) | Untrusted data outside developer messages, typed inter-node outputs, residual injection risk | Agent Builder-specific tool/approval recommendations do not imply adding approvals to a tool-free speech report |
| A7 | [OWASP — LLM01:2025 Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/) | Direct/indirect injection, least privilege, deterministic output checks and adversarial testing | General threat guidance; does not certify a prompt safe |
| A8 | [NIST — AI RMF Generative AI Profile, AI 600-1](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf) | Confabulation, human calibration, provenance, scoped validation and monitoring | Voluntary cross-domain risk guidance; no prescribed SaaS architecture or speech score |
| A9 | [Anthropic — Claude prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices) | Clear task/role, diverse examples, separation of context | Original system-prompts URL redirected here; model-specific advice must be evaluated |
| A10 | [Google Cloud — Use system instructions](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/prompts/system-instructions) | Instruction/context API separation; explicit residual jailbreak/leak limits | Google-specific parameter/role behavior; not a security boundary |
| A11 | [Anthropic — Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) | Code/model/human graders, trial variation, outcomes and traces, calibrated semantic judgment | Agent examples differ from speech assessment; graders still need local validation |
| A12 | [JSON Schema — Object reference](https://json-schema.org/understanding-json-schema/reference/object) | Required keys, additionalProperties and closed object contracts | Syntactic standard; no inference/groundedness guarantee |
| A13 | [Sber — Генерация структурированных данных](https://developers.sber.ru/docs/ru/gigachat/guides/structured-output) | Native GigaChat schema output, `response_format.schema`, v1/v2 differences | Official page updated 20 July 2026; does not prove current shared gateway accepts native schema or roles |

Unverified sources excluded from count: the Sber REST chat and gRPC methods URLs returned internal browsing errors; the root OpenAI Model Spec URL returned only a redirect. No claims about those pages' details rely on search snippets.
