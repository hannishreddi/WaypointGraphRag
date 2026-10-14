# Eval: s5 on dev

- as of 2026-10-10 | commit 5cdc3024f9 (dirty) | 60 questions | default asker ZV-1006
- score: mean over scored rows (exact, set-F1, judge 1 / 0.5 / 0); skipped rows are excluded
- judge gemini-3.5-flash-lite: 6 API calls, 2259 tokens (not counted in tokens/q)
- errors: 0
- dev has 60 questions: per-category numbers are noisy; use the test split for claims
- LLM API calls (answer + judge HTTP requests incl. retries, all sessions): 67
- verifier: {'pass': 60} (regenerated/failed = triggered)

## Overall

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 60 | 60 | 0 | 0.96 | 0.96 | 0.95 | 6262 | 1973 | 11842.5 | 3229.9 |

## By hops

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 27 | 27 | 0 | 1.00 | 1.00 | 0.93 | 6127 | 1932 | 11651.8 | 3538.9 |
| 2 | 22 | 22 | 0 | 0.93 | 0.90 | 1.00 | 6404 | 2006 | 11940.4 | 3229.9 |
| 3 | 11 | 11 | 0 | 0.95 | 1.00 | 0.91 | 6308 | 2006 | 11836.7 | 2840.9 |

## By category

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cross_document | 3 | 3 | 0 | 0.83 | 1.00 | 1.00 | 6807 | 2006 | 11691.3 | 3908.3 |
| employee_lookup | 4 | 4 | 0 | 0.75 | 0.75 | 1.00 | 6508 | 2006 | 11740.4 | 3041.6 |
| org_structure | 20 | 20 | 0 | 1.00 | 1.00 | 1.00 | 5970 | 1906 | 11952.0 | 3222.7 |
| personalised | 8 | 8 | 0 | 1.00 | 0.94 | 1.00 | 6211 | 2006 | 11923.6 | 3279.4 |
| policy | 7 | 7 | 0 | 1.00 | 1.00 | 0.71 | 6460 | 2006 | 11611.4 | 3308.5 |
| project | 9 | 9 | 0 | 1.00 | 1.00 | 0.89 | 6046 | 2006 | 12282.2 | 3121.9 |
| skills_experience | 9 | 9 | 0 | 0.93 | 0.92 | 1.00 | 6725 | 2006 | 12325.6 | 3240.1 |
