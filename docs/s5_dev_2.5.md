# Eval: s5 on dev

- as of 2026-10-10 | commit eca05fdd91 | 60 questions | default asker ZV-1006
- score: mean over scored rows (exact, set-F1, judge 1 / 0.5 / 0); skipped rows are excluded
- judge gemini-3.5-flash-lite: 15 API calls, 4777 tokens (not counted in tokens/q)
- errors: 0
- dev has 60 questions: per-category numbers are noisy; use the test split for claims
- LLM API calls (answer + judge HTTP requests incl. retries, all sessions): 103
- verifier: {'failed': 11, 'pass': 32, 'regenerated': 17} (regenerated/failed = triggered)

## Overall

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 60 | 60 | 0 | 0.53 | 0.59 | 0.99 | 6558 | 1973 | 12600.1 | 2075.2 |

## By hops

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 27 | 27 | 0 | 0.59 | 0.63 | 0.97 | 6303 | 1932 | 12080.2 | 1960.2 |
| 2 | 22 | 22 | 0 | 0.52 | 0.49 | 1.00 | 6718 | 2006 | 17120.4 | 2602.4 |
| 3 | 11 | 11 | 0 | 0.41 | 0.70 | 1.00 | 6867 | 2006 | 23693.8 | 2825.3 |

## By category

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cross_document | 3 | 3 | 0 | 0.83 | 1.00 | 1.00 | 7055 | 2006 | 11409.3 | 1618.1 |
| employee_lookup | 4 | 4 | 0 | 0.75 | 0.75 | 1.00 | 6419 | 2006 | 12219.4 | 1284.7 |
| org_structure | 20 | 20 | 0 | 0.45 | 0.43 | 1.00 | 6172 | 1906 | 12224.8 | 1406.3 |
| personalised | 8 | 8 | 0 | 0.38 | 0.69 | 1.00 | 6393 | 2006 | 12123.0 | 1846.7 |
| policy | 7 | 7 | 0 | 0.71 | 0.86 | 0.92 | 6588 | 2006 | 10976.7 | 2148.9 |
| project | 9 | 9 | 0 | 0.56 | 0.56 | 1.00 | 6808 | 2006 | 23693.8 | 4706.6 |
| skills_experience | 9 | 9 | 0 | 0.49 | 0.47 | 1.00 | 7186 | 2006 | 23665.1 | 3487.7 |
