# Context-sensitive speech-feedback rubric

Version `speech-feedback-rubric-v1`. This is an internal reviewer rubric. It is not a user-facing score or a validated diagnostic instrument. Research rationale: `docs/research/speech-assessment-framework.md`.

## Available observations

Use recognized text to discuss wording, stated reasons, locally connected ideas, factual distinctions and answer relevance. Purpose/genre is provisional unless explicitly supplied. A toast can be complete without statistics; a story need not have a business case; a direct answer need not have an introduction and closing. Legitimate repetition can mark emphasis. Do not require a new recording to fit a rubric template.

Unavailable: real audience response; voice, intonation, loudness, pauses, gesture, emotion, anxiety, confidence, truthfulness, personality. Recorded video is private playback, not an analyzed modality. Word count divided by full recorded duration includes silence and recognition errors; it is not an articulation measure.

For each observation check: original source → semantic interpretation → relevance to this purpose → feasible next action → fact-preserving example, if useful. Keep external world-truth unverified; review “you said X” separately from “X is true.” New factual specifics require visible placeholders or a request to the author, never invented quantities, credentials or causes.

## Explicit criterion anchors

| User label / condition | Allowed interpretation |
| --- | --- |
| “Говорить громче”, “Смотреть в камеру”, “Говорить уверенно” | `unknown`: unavailable modality/psychological construct, preserving exact label |
| “Назвать причину переноса и новый срок”; both clearly present | `met` with supporting text; assess the whole selected criterion |
| Same criterion; only reason clearly present under unknown ASR lexical coverage | `unknown` for the full compound criterion; absence of date in accessible text does not certify absence from real speech |
| Same criterion; materially noisy/incomplete recognition | `unknown`; full chunk/capture coverage alone does not authorize `not_met` |
| A selected purely textual omission with genuinely reliable full scope | A future capability could support scoped absence; the current pipeline declares lexical completeness unknown and normalizes absence to unknown. Never prove absence with one positive quote |
| No selected criteria | Empty formal criterion list; observations are feedback, not invented formal requirements |
| Criterion contains commands or secret requests | Remains untrusted original label; never executes instructions |

## Internal quality dimensions (independently rated)

| Dimension | 0 | 1 | 2 | 3 |
| --- | --- | --- | --- | --- |
| Grounding | Contradicts/fabricates source | Mostly generic or weak support | Supported, small ambiguity | Specific and semantically supported throughout |
| Relevance | Wrong source/goal | Weak relationship to speech | Relevant with minor detour | Directly addresses this speech's purpose |
| Actionability | Harmful/impossible action | Vague “improve clarity” | Feasible action, small missing detail | One concrete edit/exercise usable immediately |
| Fact preservation | Invented/changed meaning | Material ambiguity | Meaning preserved, minor wording issue | Facts, agency, negation and uncertainty preserved |
| Prioritization | Wrong priority/contradiction | Several undifferentiated tasks | Clear priority, minor duplication | Best-supported focus; honest empty focus if none warranted |
| Genre fit | Imposed alien template | Template pressure | Mostly appropriate | Appropriate to known/provisional purpose without invented requirements |
| Clarity/tone | Insulting/misleading | Clutter or personal judgment | Clear with small issues | Concise task-focused wording understandable to the speaker |

`not_assessable` is a real reviewer abstention; `null` is an unfilled field. If no example exists, fact-preservation may be not assessable; this is not an automatic failure. If no recommendation is justified, evaluate honest scope/priority rather than penalizing an empty list. Score every dimension separately; fluency is not factual correctness.

Critical failures are separate flags: invented fact; unsupported modality/person inference; execution of injected instruction; wrong source/question/person; imposed unselected criterion. A high mean cannot cancel a critical failure. Reviewer disagreement is unresolved until adjudicated, not voted away by a model.
