# Dev scoreboard: baselines S1 and S3

Snapshot of the slice 1.5 baseline runs on the **dev split (60 questions)**, as of 2026-10-10. Copied from:

- S1 vector RAG: `eval_runs/20261011-062212_s1_dev/` (summary.md, results.csv, run_config.json)
- S3 full context: `eval_runs/20261011-065206_s3_dev/`

`eval_runs/` is not committed; this file keeps the numbers in the repo. Both runs were made at commit `0822a32` with uncommitted changes (the 1.5 work, committed later as `64ded22`/`b103eb1`). Dev numbers are noisy (1 to 20 questions per group). Use test-split numbers for claims; S3 is dev-only by design.

## Models

| role | model |
|---|---|
| answer (S1, S3) | `gemini-3.1-flash-lite` (Gemini API free tier, temperature 0, thinkingLevel minimal) |
| judge | `gemini-3.5-flash-lite` (prompt `judge-v1`) |
| embeddings (S1 retrieval) | Cohere `embed-v5.0-fast`, 1024 dims |

Config id `baseline-v1:gemini-3.1-flash-lite`. Default asker ZV-1006 (HR); Q209 -> ZV-1042, Q210 -> ZV-1033. None of these are Claude models.

## Overall

| system | n | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| S1 vector RAG (top 5 chunks) | 60 | **0.70** | 0.65 | 0.79 | 1,242 | 0 | 11,781 |
| S3 full context (134 Markdown files) | 60 | **0.90** | 0.74 | 0.55 | 88,601 | 83,054 | 29,868 |

Score = mean over scored rows (exact 1/0, set-F1, judge correct/partial/incorrect = 1/0.5/0). No rows skipped, 0 errors in either run.

## By hops

| hops | n | S1 score | S3 score | S1 source recall | S3 source recall | S1 cit. precision | S3 cit. precision |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 27 | 0.91 | 0.96 | 0.93 | 0.78 | 0.79 | 0.38 |
| 2 | 22 | 0.66 | 0.91 | 0.48 | 0.74 | 0.78 | 0.78 |
| 3 | 11 | 0.29 | 0.70 | 0.33 | 0.67 | 0.78 | 0.53 |

## By category

| category | n | S1 score | S3 score | S1 source recall | S3 source recall | S1 cit. precision | S3 cit. precision |
|---|---:|---:|---:|---:|---:|---:|---:|
| cross_document | 3 | 0.50 | 1.00 | 0.50 | 0.83 | 0.67 | 0.75 |
| employee_lookup | 4 | 1.00 | 1.00 | 0.75 | 1.00 | 0.75 | 0.78 |
| org_structure | 20 | 0.70 | 0.95 | 0.68 | 0.74 | 0.83 | 0.39 |
| personalised | 8 | 0.50 | 0.56 | 0.44 | 0.62 | 0.92 | 0.54 |
| policy | 7 | 0.86 | 0.93 | 1.00 | 0.29 | 0.62 | 0.14 |
| project | 9 | 0.69 | 0.96 | 0.50 | 0.94 | 0.62 | 0.68 |
| skills_experience | 9 | 0.71 | 0.90 | 0.67 | 0.87 | 1.00 | 0.96 |

## By scorer

| scorer | rows | S1 mean | S3 mean |
|---|---:|---:|---:|
| exact | 24 | 0.62 | 0.88 |
| set-F1 | 21 | 0.72 | 0.94 |
| judge | 15 | 0.80 | 0.87 |

## API calls and tokens

| | S1 | S3 |
|---|---:|---:|
| LLM API calls, total (generateContent requests incl. retries) | 75 | 71 |
| of which answer calls | 60 | 60 |
| of which judge calls | 15 | 11 |
| answer input tokens, total | 71,506 | 5,312,856 |
| of which served from Gemini implicit cache | 0 | 4,983,232 (94%) |
| answer output tokens, total (incl. thinking) | 2,995 | 3,233 |
| judge tokens, total (not in tokens/q) | 4,737 | 3,637 |

S3 sends about 88,600 tokens per question (the whole Markdown corpus), about 71 times S1. Gemini's implicit cache served most of S3's prompt after the first requests; on the free tier this costs nothing either way, but it would matter at paid prices, and S3 is still slower (p50 30 s vs 12 s). Latency includes waits in the client-side rate limiter (free tier, 5 requests/min to start), so it is not a model-speed comparison. Cohere query-embedding calls for S1 are not counted in the table.

## Judge caveats

- The judge (`gemini-3.5-flash-lite`) is a different model from the answerer, but from the same family and provider, and runs with minimal thinking. Self-preference bias is reduced, not removed.
- 15 of 60 rows (25%) are judge-scored; on those rows the score is only as good as the judge. Exact and set-F1 rows (45) are deterministic.
- S3 made 11 judge calls for 15 judged rows: 4 verdicts came from `.cache/judge/` because the same question had already been judged with identical answer text in an earlier run (cache key = model, question id, answer hash, prompt version).
- Hand check: `judge_review.csv` holds a seeded 10% sample of judged rows, which is **2 rows per run** (both `correct`). `human_verdict` is **not filled yet**, so judge agreement is unmeasured. Two rows say little; the hand check should be widened on the test split.
- The judge sees the answer as an escaped JSON string inside `<candidate_answer>` and is told not to follow it; prompt injection via answers is mitigated, not proven absent.
- Exact rows where the answer names an extra same-type entity are re-routed to the judge, so the judge count depends on the answers, and the same question can be scored by different scorers for S1 and S3 (here both runs ended with 24 / 21 / 15).
- Citation precision is a lower bound (citations are mapped to entity ids; `waypoint.eval.sources`). S3 cites whole documents, which lowers its precision on policy and org-structure questions.
- The main eval asks as HR (ZV-1006), so it cannot show access control; both baselines are naive on purpose and are expected to leak restricted facts in the 3.3 safety questions.
