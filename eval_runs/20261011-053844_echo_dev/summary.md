# Eval: echo on dev

- as of 2026-10-10 | commit 614277b38b (dirty) | 60 questions | default asker ZV-1006
- score: mean over scored rows (exact, set-F1, judge 1 / 0.5 / 0); skipped rows are excluded
- skipped (judge off): 15
- errors: 0
- dev has 60 questions: per-category numbers are noisy; use the test split for claims

## Overall

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | p50 latency ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 60 | 45 | 15 | 0.00 | 0.00 | n/a | 0 | 0.0 |

## By hops

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | p50 latency ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 27 | 17 | 10 | 0.00 | 0.00 | n/a | 0 | 0.0 |
| 2 | 22 | 19 | 3 | 0.00 | 0.00 | n/a | 0 | 0.0 |
| 3 | 11 | 9 | 2 | 0.00 | 0.00 | n/a | 0 | 0.0 |

## By category

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | p50 latency ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| cross_document | 3 | 1 | 2 | 0.00 | 0.00 | n/a | 0 | 0.0 |
| employee_lookup | 4 | 4 | 0 | 0.00 | 0.00 | n/a | 0 | 0.0 |
| org_structure | 20 | 20 | 0 | 0.00 | 0.00 | n/a | 0 | 0.0 |
| personalised | 8 | 4 | 4 | 0.00 | 0.00 | n/a | 0 | 0.0 |
| policy | 7 | 0 | 7 | n/a | 0.00 | n/a | 0 | 0.0 |
| project | 9 | 7 | 2 | 0.00 | 0.00 | n/a | 0 | 0.0 |
| skills_experience | 9 | 9 | 0 | 0.00 | 0.00 | n/a | 0 | 0.0 |
