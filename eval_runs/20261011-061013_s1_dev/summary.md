# Eval: s1 on dev

- as of 2026-10-10 | commit 0822a32ab3 (dirty) | 1 questions | default asker ZV-1006
- score: mean over scored rows (exact, set-F1, judge 1 / 0.5 / 0); skipped rows are excluded
- skipped (judge off): 0
- errors: 0
- dev has 60 questions: per-category numbers are noisy; use the test split for claims
- LLM API calls (answer + judge HTTP requests incl. retries, all sessions): 1

## Overall

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 1 | 1 | 0 | 1.00 | 1.00 | 1.00 | 742 | 0 | 9919.0 |

## By hops

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 1 | 0 | 1.00 | 1.00 | 1.00 | 742 | 0 | 9919.0 |

## By category

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| org_structure | 1 | 1 | 0 | 1.00 | 1.00 | 1.00 | 742 | 0 | 9919.0 |
