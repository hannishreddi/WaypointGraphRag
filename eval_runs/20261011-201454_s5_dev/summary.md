# Eval: s5 on dev

- as of 2026-10-10 | commit 417d675796 (dirty) | 60 questions | default asker ZV-1006
- score: mean over scored rows (exact, set-F1, judge 1 / 0.5 / 0); skipped rows are excluded
- judge gemini-3.5-flash-lite: 0 API calls, 0 tokens (not counted in tokens/q)
- errors: 0
- dev has 60 questions: per-category numbers are noisy; use the test split for claims
- LLM API calls (answer + judge HTTP requests incl. retries, all sessions): 64
- verifier: {'pass': 60} (regenerated/failed = triggered)
- resumed 28 finished rows from the checkpoint

## Overall

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 60 | 60 | 0 | 0.71 | 0.78 | 0.95 | 6136 | 1973 | 11918.0 | 1281.5 |

## By hops

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 27 | 27 | 0 | 0.81 | 0.85 | 0.95 | 6003 | 1932 | 11978.9 | 1250.2 |
| 2 | 22 | 22 | 0 | 0.61 | 0.58 | 1.00 | 6275 | 2006 | 11762.5 | 1321.0 |
| 3 | 11 | 11 | 0 | 0.68 | 1.00 | 0.91 | 6185 | 2006 | 11790.9 | 1077.2 |

## By category

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cross_document | 3 | 3 | 0 | 0.83 | 1.00 | 1.00 | 6716 | 2006 | 12023.3 | 1569.5 |
| employee_lookup | 4 | 4 | 0 | 0.75 | 0.75 | 1.00 | 6419 | 2006 | 11968.2 | 1239.0 |
| org_structure | 20 | 20 | 0 | 0.65 | 0.65 | 1.00 | 5834 | 1906 | 11764.8 | 1241.8 |
| personalised | 8 | 8 | 0 | 0.38 | 0.69 | 1.00 | 6071 | 2006 | 12016.7 | 1034.9 |
| policy | 7 | 7 | 0 | 0.86 | 1.00 | 0.83 | 6356 | 2006 | 12239.0 | 1345.0 |
| project | 9 | 9 | 0 | 1.00 | 1.00 | 0.89 | 5913 | 2006 | 11711.3 | 1342.2 |
| skills_experience | 9 | 9 | 0 | 0.71 | 0.69 | 1.00 | 6597 | 2006 | 12117.7 | 1275.2 |
