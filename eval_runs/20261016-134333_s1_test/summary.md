# Eval: s1 on test

- as of 2026-10-10 | commit 4553c4c53d | 191 questions | default asker ZV-1006
- score: mean over scored rows (exact, set-F1, judge 1 / 0.5 / 0); skipped rows are excluded
- judge gemini-3.5-flash-lite: 2 API calls, 598 tokens (not counted in tokens/q)
- errors: 0
- LLM API calls (answer + judge HTTP requests incl. retries, all sessions): 312
- resumed 189 finished rows from the checkpoint

## Overall

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 191 | 191 | 0 | 0.70 | 0.63 | 0.77 | 1203 | 0 | 11779.7 | 4013.6 |

## By hops

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 87 | 87 | 0 | 0.91 | 0.82 | 0.76 | 1333 | 0 | 11922.4 | 3792.2 |
| 2 | 71 | 71 | 0 | 0.60 | 0.53 | 0.84 | 1024 | 0 | 11677.2 | 4639.0 |
| 3 | 33 | 33 | 0 | 0.35 | 0.38 | 0.66 | 1246 | 0 | 10891.3 | 4953.4 |

## By category

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cross_document | 10 | 10 | 0 | 0.55 | 0.55 | 0.47 | 1385 | 0 | 7824.5 | 3090.9 |
| employee_lookup | 14 | 14 | 0 | 0.95 | 0.64 | 0.64 | 1030 | 0 | 11523.1 | 2979.3 |
| org_structure | 60 | 60 | 0 | 0.73 | 0.71 | 0.81 | 1189 | 0 | 11958.0 | 3384.2 |
| personalised | 27 | 27 | 0 | 0.28 | 0.20 | 0.86 | 932 | 0 | 9415.3 | 7033.4 |
| policy | 24 | 24 | 0 | 0.81 | 0.75 | 0.64 | 1759 | 0 | 16189.4 | 15271.4 |
| project | 28 | 28 | 0 | 0.78 | 0.70 | 0.75 | 1308 | 0 | 10949.6 | 5080.5 |
| skills_experience | 28 | 28 | 0 | 0.79 | 0.75 | 1.00 | 937 | 0 | 13121.5 | 8271.0 |
