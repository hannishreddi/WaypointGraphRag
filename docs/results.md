# Results

Waypoint (S5) against plain vector RAG (S1) on the Zenvora question set: 251 questions, split once (seed 42) into 60 dev and 191 test questions, stratified by category and hop count. Every run is as of 2026-10-10 and asked as HR (ZV-1006), except two questions that need a specific asker.

Models: answers `gemini-3.1-flash-lite`; S5 router and the judge `gemini-3.5-flash-lite` (a different model, so the judge never grades its own answers); embeddings Cohere `embed-v5.0-fast` (1024 dimensions). Gemini free tier, temperature 0.

Scoring:
- exact match for a single value;
- set-F1 for lists;
- the LLM judge for sentence answers (correct 1, partial 0.5, incorrect 0).

The judge agreed with a hand check on 12 of 12 sampled rows ([judge_check.md](judge_check.md)).

## Test split (191 questions)

S5 config `answer-v2:router-v4:pack-v5:verify-v2`, run 2026-10-16 (`eval_runs/20261016-032128_s5_test`). S1 run the same day (`eval_runs/20261016-134333_s1_test`). Each system ran once on the test split; nothing was changed after the results were seen.

| group | n | S5 | S1 |
|---|---:|---:|---:|
| **all** | 191 | **0.95** | **0.70** |
| 1-hop | 87 | 0.93 | 0.91 |
| 2-hop | 71 | 0.97 | 0.60 |
| 3-hop | 33 | 0.95 | 0.35 |
| cross_document | 10 | 0.95 | 0.55 |
| employee_lookup | 14 | 1.00 | 0.95 |
| org_structure | 60 | 0.98 | 0.73 |
| personalised | 27 | 1.00 | 0.28 |
| policy | 24 | 0.75 | 0.81 |
| project | 28 | 0.96 | 0.78 |
| skills_experience | 28 | 0.96 | 0.79 |

| | S5 | S1 |
|---|---:|---:|
| source recall | 0.95 | 0.63 |
| citation precision | 0.93 | 0.77 |
| tokens per question | 7,654 | 1,203 |
| LLM requests per question (router + answer) | 2.0 | 1.0 |
| verifier triggered | 2/191 | n/a |

How to read it:
- On 1-hop lookups the two systems are level. The gap opens on 2-hop and 3-hop questions, where an answer needs a graph traversal or a rule, not one matching passage.
- Personalised questions depend on who is asking. S1 receives the asker only as plain text, so this category measures a capability S1 lacks, not retrieval quality.
- Policy questions are the one category where S1 scores higher, and S5's weakest. The cause was not analysed (per-question analysis of the test split was out of scope).

## Dev split (60 questions)

The router prompt and the 2.6/3.3 fixes were developed on dev, so S5's dev numbers are optimistic. S3 (the whole 134-file corpus in every prompt, about 88.6k tokens per question) ran on dev only.

| group | n | S5 | S1 | S3 |
|---|---:|---:|---:|---:|
| all | 60 | 0.99 | 0.70 | 0.90 |
| 1-hop | 27 | 1.00 | 0.91 | 0.96 |
| 2-hop | 22 | 0.99 | 0.66 | 0.91 |
| 3-hop | 11 | 0.95 | 0.29 | 0.70 |

The history behind these numbers is in [s5_dev_2.5_report.md](s5_dev_2.5_report.md), [s5_dev_2.6.md](s5_dev_2.6.md), [s5_dev_3.3a.md](s5_dev_3.3a.md), [s5_dev_3.3c.md](s5_dev_3.3c.md) and [scoreboard_dev_baselines.md](scoreboard_dev_baselines.md).

## Limits

- The corpus is small, synthetic and clean: 42 employees, 391 graph nodes.
- Only two people have a restricted status (one on leave, one serving notice), so the access-control results rest on two subjects. See [safety.md](safety.md).
- No confidence intervals are reported. On the per-category rows with n = 10 to 28, differences of a few points are noise.
