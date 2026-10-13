# Reviewer packet preparation

No reviewer decisions are included. The synthetic author expectations are not human gold.

Generate development baseline/candidate reports first, then prepare blinded materials:

```sh
.venv/bin/python scripts/evaluate_ai.py blind --artifacts /private/eval/provider.json --destination /private/eval/review
.venv/bin/python scripts/evaluate_ai.py challenge-packets --destination /private/eval/challenge-review
```

Give each reviewer `review-packets.json`, a separate copy of `ratings-blank.json`, the rubric and annotation guide. Do **not** give the coordinator key, raw artifact identities or expected challenge labels. Reviewers fill dimensions, claim assessments, rewrite checks, criterion checks, critical flags and reasons independently. Null fields remain unrated; use `not_assessable` to abstain. Assign pseudonymous IDs and retain originals before adjudication.

`ratings` reports agreement and missing dimensions; `compare` clusters preference views within each case. `challenge-score` compares independent decisions to seeded expected labels and measures order reversal consistency. Empty input yields null rates and denominator zero, never a passing quality score. Reverse views are the same family, not extra speeches. A grader doing well on twenty obvious seeded pairs is still not certified for subtle coaching quality.

Human review, real recordings, ASR labels and report comprehension participants are currently unavailable. No acceptance report or release approval is implied by these templates.
