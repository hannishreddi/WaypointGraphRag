# Eval: s5 on dev (subset: Q193 Q195 Q196)

- as of 2026-10-10 | commit a192449099 (dirty) | 3 questions | default asker ZV-1006
- score: mean over scored rows (exact, set-F1, judge 1 / 0.5 / 0); skipped rows are excluded
- judge gemini-3.5-flash-lite: 0 API calls, 0 tokens (not counted in tokens/q)
- errors: 0
- dev has 60 questions: per-category numbers are noisy; use the test split for claims
- LLM API calls (answer + judge HTTP requests incl. retries, all sessions): 3
- verifier: {'pass': 3} (regenerated/failed = triggered)

## Overall

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 3 | 3 | 0 | 1.00 | 1.00 | 1.00 | 5906 | 2006 | 7595.4 | 6154.0 |

## By hops

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3 | 3 | 3 | 0 | 1.00 | 1.00 | 1.00 | 5906 | 2006 | 7595.4 | 6154.0 |

## By category

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| personalised | 3 | 3 | 0 | 1.00 | 1.00 | 1.00 | 5906 | 2006 | 7595.4 | 6154.0 |
