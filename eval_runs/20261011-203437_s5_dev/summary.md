# Eval: s5 on dev (subset: Q211 Q232)

- as of 2026-10-10 | commit 75b0a4c63a (dirty) | 2 questions | default asker ZV-1006
- score: mean over scored rows (exact, set-F1, judge 1 / 0.5 / 0); skipped rows are excluded
- judge gemini-3.5-flash-lite: 2 API calls, 711 tokens (not counted in tokens/q)
- errors: 0
- dev has 60 questions: per-category numbers are noisy; use the test split for claims
- LLM API calls (answer + judge HTTP requests incl. retries, all sessions): 4
- verifier: {'pass': 2} (regenerated/failed = triggered)

## Overall

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 2 | 2 | 0 | 0.75 | 1.00 | 1.00 | 6362 | 2006 | 6955.4 | 3575.4 |

## By hops

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 2 | 2 | 0 | 0.75 | 1.00 | 1.00 | 6362 | 2006 | 6955.4 | 3575.4 |

## By category

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| policy | 2 | 2 | 0 | 0.75 | 1.00 | 1.00 | 6362 | 2006 | 6955.4 | 3575.4 |
