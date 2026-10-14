# Eval: s5 on dev

- as of 2026-10-10 | commit 32c57487d2 (dirty) | 60 questions | default asker ZV-1006
- score: mean over scored rows (exact, set-F1, judge 1 / 0.5 / 0); skipped rows are excluded
- judge gemini-3.5-flash-lite: 3 API calls, 953 tokens (not counted in tokens/q)
- errors: 0
- dev has 60 questions: per-category numbers are noisy; use the test split for claims
- LLM API calls (answer + judge HTTP requests incl. retries, all sessions): 64
- verifier: {'pass': 60} (regenerated/failed = triggered)
- resumed 11 finished rows from the checkpoint

## Overall

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 60 | 60 | 0 | 0.90 | 0.96 | 0.96 | 6143 | 1973 | 12084.5 | 3620.4 |

## By hops

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 27 | 27 | 0 | 0.96 | 1.00 | 0.96 | 6007 | 1932 | 12200.1 | 3891.6 |
| 2 | 22 | 22 | 0 | 0.93 | 0.90 | 1.00 | 6285 | 2006 | 12084.5 | 3193.3 |
| 3 | 11 | 11 | 0 | 0.68 | 1.00 | 0.91 | 6191 | 2006 | 12071.2 | 4136.6 |

## By category

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cross_document | 3 | 3 | 0 | 0.83 | 1.00 | 1.00 | 6735 | 2006 | 13232.2 | 5643.4 |
| employee_lookup | 4 | 4 | 0 | 0.75 | 0.75 | 1.00 | 6422 | 2006 | 12656.1 | 3826.9 |
| org_structure | 20 | 20 | 0 | 1.00 | 1.00 | 1.00 | 5843 | 1906 | 12002.7 | 3594.6 |
| personalised | 8 | 8 | 0 | 0.62 | 0.94 | 1.00 | 6080 | 2006 | 12213.8 | 2760.2 |
| policy | 7 | 7 | 0 | 0.86 | 1.00 | 0.83 | 6358 | 2006 | 12357.7 | 3119.1 |
| project | 9 | 9 | 0 | 1.00 | 1.00 | 0.89 | 5915 | 2006 | 12210.1 | 4208.2 |
| skills_experience | 9 | 9 | 0 | 0.93 | 0.92 | 1.00 | 6605 | 2006 | 11986.8 | 2494.6 |
