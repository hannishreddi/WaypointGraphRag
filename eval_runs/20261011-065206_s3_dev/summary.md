# Eval: s3 on dev

- as of 2026-10-10 | commit 0822a32ab3 (dirty) | 60 questions | default asker ZV-1006
- score: mean over scored rows (exact, set-F1, judge 1 / 0.5 / 0); skipped rows are excluded
- judge gemini-3.5-flash-lite: 11 API calls, 3637 tokens (not counted in tokens/q)
- errors: 0
- dev has 60 questions: per-category numbers are noisy; use the test split for claims
- LLM API calls (answer + judge HTTP requests incl. retries, all sessions): 71

## Overall

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 60 | 60 | 0 | 0.90 | 0.74 | 0.55 | 88601 | 83054 | 29867.8 |

## By hops

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 27 | 27 | 0 | 0.96 | 0.78 | 0.38 | 88591 | 79553 | 30014.9 |
| 2 | 22 | 22 | 0 | 0.91 | 0.74 | 0.78 | 88615 | 85918 | 29856.6 |
| 3 | 11 | 11 | 0 | 0.70 | 0.67 | 0.53 | 88602 | 85918 | 29822.0 |

## By category

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cross_document | 3 | 3 | 0 | 1.00 | 0.83 | 0.75 | 88667 | 85918 | 29313.0 |
| employee_lookup | 4 | 4 | 0 | 1.00 | 1.00 | 0.78 | 88598 | 85918 | 30380.3 |
| org_structure | 20 | 20 | 0 | 0.95 | 0.74 | 0.39 | 88582 | 77326 | 29950.2 |
| personalised | 8 | 8 | 0 | 0.56 | 0.62 | 0.54 | 88620 | 85918 | 29843.3 |
| policy | 7 | 7 | 0 | 0.93 | 0.29 | 0.14 | 88603 | 85917 | 28874.9 |
| project | 9 | 9 | 0 | 0.96 | 0.94 | 0.68 | 88594 | 85918 | 30148.0 |
| skills_experience | 9 | 9 | 0 | 0.90 | 0.87 | 0.96 | 88615 | 85918 | 29939.8 |
