# Eval: s5 on test

- as of 2026-10-10 | commit 975e58c117 | 191 questions | default asker ZV-1006
- score: mean over scored rows (exact, set-F1, judge 1 / 0.5 / 0); skipped rows are excluded
- judge gemini-3.5-flash-lite: 60 API calls, 20057 tokens (not counted in tokens/q)
- errors: 0
- LLM API calls (answer + judge HTTP requests incl. retries, all sessions): 446
- verifier: {'pass': 189, 'regenerated': 2} (regenerated/failed = triggered)

## Overall

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 191 | 191 | 0 | 0.95 | 0.95 | 0.93 | 7654 | 4009 | 12247.1 | 3062.1 |

## By hops

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 87 | 87 | 0 | 0.93 | 0.97 | 0.95 | 7676 | 3937 | 12288.4 | 3308.2 |
| 2 | 71 | 71 | 0 | 0.97 | 0.91 | 0.97 | 7450 | 4030 | 12124.3 | 2783.9 |
| 3 | 33 | 33 | 0 | 0.95 | 0.97 | 0.81 | 8032 | 4153 | 13289.8 | 3326.6 |

## By category

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cross_document | 10 | 10 | 0 | 0.95 | 0.90 | 0.90 | 9135 | 4434 | 14555.7 | 3747.2 |
| employee_lookup | 14 | 14 | 0 | 1.00 | 1.00 | 1.00 | 7400 | 4030 | 12242.3 | 3185.1 |
| org_structure | 60 | 60 | 0 | 0.98 | 1.00 | 1.00 | 7380 | 3963 | 12052.0 | 2977.8 |
| personalised | 27 | 27 | 0 | 1.00 | 0.81 | 0.84 | 7781 | 4030 | 13501.9 | 3132.5 |
| policy | 24 | 24 | 0 | 0.75 | 0.88 | 0.81 | 8150 | 3862 | 14455.2 | 3707.4 |
| project | 28 | 28 | 0 | 0.96 | 1.00 | 0.89 | 7463 | 4030 | 12117.4 | 2911.2 |
| skills_experience | 28 | 28 | 0 | 0.96 | 0.96 | 1.00 | 7482 | 4030 | 12004.4 | 2885.0 |
