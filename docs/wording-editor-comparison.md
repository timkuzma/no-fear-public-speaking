# Wording editor comparison, 15 October 2026

Selected candidate: `gpt-5.4-mini` with `speech-wording-v2`. Assessment remains a separate `gpt-5.4` call. The editor still receives only display strings and source excerpts; publication continues through the existing validator. There is no extra assessor, automatic repair or history regeneration.

## Evidence and decision

The latest user practice took 59.532 seconds of server processing: 1.680 seconds of answer transcription HTTP, 9.326 seconds of assessment HTTP and 48.166 seconds of DeepSeek editing HTTP. Queue wait was 0.072 seconds. Questions took 12.616 seconds, including 8.876 seconds of editing. These measurements describe this particular run, not a service average or browser delivery time.

The comparison used the actual gateway, application container, request format, output ceiling and wording validator. Three fixed synthetic cases contain three questions, a six-field short report and a sixteen-field report testing signed numbers, conditional advice, scope, uncertainty, genre and an instruction embedded in an untrusted excerpt. Every model received identical fields and the existing v1 prompt initially. Values below are wall seconds, including rejected responses; failures are not successful latency measurements.

| Model, v1 prompt | Questions | Short report | Extended report | Observed issues |
| --- | ---: | ---: | ---: | --- |
| DeepSeek v3.2 | 21.993, rejected | 15.276 | 10.867, failed | Returned forbidden source keys; another request failed |
| GPT-4.1 mini | 2.846 | 3.400 | 7.387 | Removed local scope from one observation |
| GPT-5.4 mini, two runs | 1.755–2.142 | 2.509–2.619 | 3.601–4.457 | One repeat changed the listener to the author; an observable check was weakened |
| Gemini 2.5 Flash | 2.388 | 2.679 | 4.442 | Converted a qualified listener inference into certainty; removed local scope |
| GPT-5.4, two runs | 2.146–2.497 | 2.921–8.393 | 19.011–112.763 | One heading changed a requested correction into an achieved result; variable latency |
| Claude Haiku 4.5 | 2.239, rejected | 3.155, rejected | 7.479, rejected | Current JSON adapter responses failed the existing parser |

These are configured gateway aliases, not immutable upstream model identities. Gateway inventory alone was not treated as proof of compatibility. Official [GPT-5.4 mini documentation](https://developers.openai.com/api/docs/models/gpt-5.4-mini), [Gemini documentation](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash) and [Haiku documentation](https://www.anthropic.com/news/claude-haiku-4-5) informed the shortlist; the measurements and editorial observations above are from this application's calls, not vendor benchmark claims.

Changing the alias alone was insufficient. Wording v2 explicitly preserves author/listener roles, local scope, uncertainty, heading intent and observable checks; it asks for minimal changes and avoids guessing grammatical gender. Two intermediate prompt drafts were explored privately. Final candidate results before deployment were 1.681 seconds for questions, 2.047 for the short report and 3.804 for the extended report. All three passed the unchanged validator. Editorial inspection of those outputs found no change to the advice, source scope, uncertainty, actors or observable checks; formal independent human acceptance remains unmeasured. This combines a model change with a prompt revision, rather than claiming a model-only quality improvement.

The saved source/assessment and public report schema do not change. New provenance and usage identify `speech-wording-v2` and the actual editor alias. Old reports retain their original model/version. Prompt changes do not imply a semantic guarantee: this small synthetic development comparison has no independent human raters, locked acceptance result, sustained-capacity measurement or production end-to-end latency distribution.

## Reproduction and limits

`scripts/benchmark_wording.py` uses `ExistingLedger` and `RunBudget` from `scripts/evaluate_ai.py`; it never constructs a Store or migrates the live database. Run it inside the application container with its existing private ledger and provider environment. Copy the script, evaluation helper and immutable baseline into a temporary writable tree if they are not in the image; keep the running server package on `PYTHONPATH`. The baseline manifest/hashes must verify before any request.

Example, from that temporary tree, after creating a private output directory (0700):

```sh
LLM_MAX_ATTEMPTS=1 PYTHONPATH=/tmp/wording-benchmark:/app python scripts/benchmark_wording.py \
  --live --models gpt-5.4-mini --data-dir /data \
  --output /tmp/wording-benchmark/new-run.json \
  --max-attempts 3 --max-input-chars 20000 --max-output-tokens 9000
```

At most six HTTP attempts are allowed per run, with one attempt per task. Each transmission requires both a per-run reservation and the maintained rolling/pause/rate checks. Audio is forbidden by the run budget. Responses and usage are written incrementally to a new private artifact; an existing output is never overwritten. `--prompt-file` can load a local candidate wording module for an isolated evaluation process; it does not change the running application's prompt. Artifact hashes distinguish intermediate prompt drafts. No practice, report, segment or job is updated. The synthetic cases are development probes, not additions to the locked acceptance set.

Raw artifacts remain in ignored `outputs/wording-20261015/`, including failed calls. Reservations are work ceilings, not measured billing; currency and actual billing remain unknown. The immutable speech-feedback baseline remains unchanged.
