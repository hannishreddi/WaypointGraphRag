# Eval: s1 on dev

- as of 2026-10-10 | commit 0822a32ab3 (dirty) | 60 questions | default asker ZV-1006
- score: mean over scored rows (exact, set-F1, judge 1 / 0.5 / 0); skipped rows are excluded
- judge gemini-3.5-flash-lite: 15 API calls, 4737 tokens (not counted in tokens/q)
- errors: 0
- dev has 60 questions: per-category numbers are noisy; use the test split for claims
- LLM API calls (answer + judge HTTP requests incl. retries, all sessions): 75

## Overall

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 60 | 60 | 0 | 0.70 | 0.65 | 0.79 | 1242 | 0 | 11781.0 |

## By hops

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 27 | 27 | 0 | 0.91 | 0.93 | 0.79 | 1332 | 0 | 11553.2 |
| 2 | 22 | 22 | 0 | 0.66 | 0.48 | 0.78 | 1123 | 0 | 12001.3 |
| 3 | 11 | 11 | 0 | 0.29 | 0.33 | 0.78 | 1259 | 0 | 11750.4 |

## By category

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cross_document | 3 | 3 | 0 | 0.50 | 0.50 | 0.67 | 1522 | 0 | 11122.7 |
| employee_lookup | 4 | 4 | 0 | 1.00 | 0.75 | 0.75 | 1089 | 0 | 13234.8 |
| org_structure | 20 | 20 | 0 | 0.70 | 0.68 | 0.83 | 1137 | 0 | 11827.5 |
| personalised | 8 | 8 | 0 | 0.50 | 0.44 | 0.92 | 1144 | 0 | 11979.0 |
| policy | 7 | 7 | 0 | 0.86 | 1.00 | 0.62 | 1936 | 0 | 2040.8 |
| project | 9 | 9 | 0 | 0.69 | 0.50 | 0.62 | 1183 | 0 | 11819.5 |
| skills_experience | 9 | 9 | 0 | 0.71 | 0.67 | 1.00 | 1054 | 0 | 12045.9 |
