# Eval: s5 on dev

- as of 2026-10-10 | commit 621213ec3a (dirty) | 60 questions | default asker ZV-1006
- score: mean over scored rows (exact, set-F1, judge 1 / 0.5 / 0); skipped rows are excluded
- judge gemini-3.5-flash-lite: 3 API calls, 1058 tokens (not counted in tokens/q)
- errors: 0
- dev has 60 questions: per-category numbers are noisy; use the test split for claims
- LLM API calls (answer + judge HTTP requests incl. retries, all sessions): 140
- verifier: {'pass': 60} (regenerated/failed = triggered)

## Overall

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 60 | 60 | 0 | 0.99 | 0.97 | 0.93 | 7588 | 3358 | 30463.9 | 26604.4 |

## By hops

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 27 | 27 | 0 | 1.00 | 1.00 | 0.91 | 7535 | 2836 | 31301.5 | 29738.5 |
| 2 | 22 | 22 | 0 | 0.99 | 0.93 | 0.95 | 7590 | 3847 | 28409.3 | 24338.6 |
| 3 | 11 | 11 | 0 | 0.95 | 1.00 | 0.91 | 7716 | 3664 | 23996.3 | 23020.6 |

## By category

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cross_document | 3 | 3 | 0 | 0.83 | 1.00 | 1.00 | 8215 | 4030 | 50824.6 | 34686.0 |
| employee_lookup | 4 | 4 | 0 | 0.95 | 0.75 | 0.75 | 7922 | 3022 | 39078.6 | 39078.6 |
| org_structure | 20 | 20 | 0 | 1.00 | 1.00 | 1.00 | 7378 | 2620 | 30479.5 | 29698.0 |
| personalised | 8 | 8 | 0 | 1.00 | 0.94 | 1.00 | 7619 | 4030 | 33610.9 | 25840.6 |
| policy | 7 | 7 | 0 | 1.00 | 1.00 | 0.67 | 7868 | 3454 | 26714.3 | 21085.1 |
| project | 9 | 9 | 0 | 1.00 | 1.00 | 0.89 | 7454 | 4030 | 23020.6 | 22510.4 |
| skills_experience | 9 | 9 | 0 | 1.00 | 1.00 | 1.00 | 7587 | 3582 | 25548.5 | 23586.5 |
