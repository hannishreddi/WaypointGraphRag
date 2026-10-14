# Eval: s5 on dev (subset: Q002 Q006 Q014 Q015 Q075 Q080 Q083 Q133 Q139 Q178 Q181)

- as of 2026-10-10 | commit 32c57487d2 (dirty) | 11 questions | default asker ZV-1006
- score: mean over scored rows (exact, set-F1, judge 1 / 0.5 / 0); skipped rows are excluded
- judge gemini-3.5-flash-lite: 1 API calls, 323 tokens (not counted in tokens/q)
- errors: 0
- dev has 60 questions: per-category numbers are noisy; use the test split for claims
- LLM API calls (answer + judge HTTP requests incl. retries, all sessions): 12
- verifier: {'pass': 11} (regenerated/failed = triggered)

## Overall

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 11 | 11 | 0 | 1.00 | 1.00 | 1.00 | 5857 | 1824 | 11423.8 | 2931.1 |

## By hops

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 4 | 4 | 0 | 1.00 | 1.00 | 1.00 | 5787 | 1504 | 11070.5 | 1980.7 |
| 2 | 7 | 7 | 0 | 1.00 | 1.00 | 1.00 | 5897 | 2006 | 11902.4 | 3865.7 |

## By category

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| org_structure | 7 | 7 | 0 | 1.00 | 1.00 | 1.00 | 5801 | 1719 | 11902.4 | 2522.6 |
| personalised | 2 | 2 | 0 | 1.00 | 1.00 | 1.00 | 5904 | 2006 | 12194.4 | 3241.2 |
| skills_experience | 2 | 2 | 0 | 1.00 | 1.00 | 1.00 | 6006 | 2006 | 10740.3 | 3398.4 |
