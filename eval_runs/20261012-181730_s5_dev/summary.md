# Eval: s5 on dev

- as of 2026-10-10 | commit 621213ec3a (dirty) | 60 questions | default asker ZV-1006
- score: mean over scored rows (exact, set-F1, judge 1 / 0.5 / 0); skipped rows are excluded
- judge gemini-3.5-flash-lite: 11 API calls, 3819 tokens (not counted in tokens/q)
- errors: 0
- dev has 60 questions: per-category numbers are noisy; use the test split for claims
- LLM API calls (answer + judge HTTP requests incl. retries, all sessions): 130
- verifier: {'pass': 59, 'skipped': 1} (regenerated/failed = triggered)

## Overall

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 60 | 60 | 0 | 0.96 | 0.95 | 0.94 | 7562 | 3963 | 12124.5 | 2691.9 |

## By hops

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 27 | 27 | 0 | 1.00 | 1.00 | 0.94 | 7542 | 3881 | 12182.5 | 2821.0 |
| 2 | 22 | 22 | 0 | 0.91 | 0.89 | 0.95 | 7515 | 4030 | 12079.2 | 2548.4 |
| 3 | 11 | 11 | 0 | 0.95 | 0.95 | 0.91 | 7706 | 4030 | 12120.4 | 2693.9 |

## By category

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cross_document | 3 | 3 | 0 | 0.83 | 0.83 | 1.00 | 8161 | 4030 | 12046.6 | 2586.8 |
| employee_lookup | 4 | 4 | 0 | 0.75 | 0.75 | 0.75 | 8028 | 4030 | 12023.5 | 2787.9 |
| org_structure | 20 | 20 | 0 | 1.00 | 1.00 | 1.00 | 7389 | 3828 | 11986.8 | 2570.0 |
| personalised | 8 | 8 | 0 | 1.00 | 0.94 | 1.00 | 7628 | 4030 | 12287.6 | 2719.8 |
| policy | 7 | 7 | 0 | 1.00 | 1.00 | 0.77 | 7864 | 4030 | 14030.1 | 3164.1 |
| project | 9 | 9 | 0 | 1.00 | 1.00 | 0.89 | 7461 | 4030 | 12200.3 | 2693.9 |
| skills_experience | 9 | 9 | 0 | 0.89 | 0.89 | 1.00 | 7349 | 4030 | 11841.0 | 2684.0 |
