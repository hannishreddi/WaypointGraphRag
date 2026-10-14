# Eval: s5 on dev

- as of 2026-10-10 | commit aa998d21cb | 60 questions | default asker ZV-1006
- score: mean over scored rows (exact, set-F1, judge 1 / 0.5 / 0); skipped rows are excluded
- judge gemini-3.5-flash-lite: 13 API calls, 4438 tokens (not counted in tokens/q)
- errors: 0
- dev has 60 questions: per-category numbers are noisy; use the test split for claims
- LLM API calls (answer + judge HTTP requests incl. retries, all sessions): 75
- verifier: {'pass': 60} (regenerated/failed = triggered)
- resumed 2 finished rows from the checkpoint

## Overall

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 60 | 60 | 0 | 0.96 | 0.96 | 0.96 | 6276 | 1973 | 11663.9 | 4124.7 |

## By hops

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 27 | 27 | 0 | 1.00 | 1.00 | 0.94 | 6142 | 1932 | 10886.0 | 3490.3 |
| 2 | 22 | 22 | 0 | 0.93 | 0.90 | 1.00 | 6414 | 2006 | 12133.7 | 4500.0 |
| 3 | 11 | 11 | 0 | 0.95 | 1.00 | 0.91 | 6330 | 2006 | 11905.0 | 4440.2 |

## By category

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cross_document | 3 | 3 | 0 | 0.83 | 1.00 | 1.00 | 6890 | 2006 | 8816.5 | 4440.2 |
| employee_lookup | 4 | 4 | 0 | 0.75 | 0.75 | 1.00 | 6548 | 2006 | 13858.7 | 5179.1 |
| org_structure | 20 | 20 | 0 | 1.00 | 1.00 | 1.00 | 5970 | 1906 | 11632.5 | 3764.0 |
| personalised | 8 | 8 | 0 | 1.00 | 0.94 | 1.00 | 6216 | 2006 | 11650.9 | 4159.6 |
| policy | 7 | 7 | 0 | 1.00 | 1.00 | 0.79 | 6511 | 2006 | 6838.5 | 2383.0 |
| project | 9 | 9 | 0 | 1.00 | 1.00 | 0.89 | 6046 | 2006 | 11673.3 | 4354.6 |
| skills_experience | 9 | 9 | 0 | 0.93 | 0.92 | 1.00 | 6732 | 2006 | 12079.4 | 4476.7 |
