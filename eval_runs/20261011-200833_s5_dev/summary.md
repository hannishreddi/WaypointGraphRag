# Eval: s5 on dev (subset: Q003 Q052 Q058 Q062 Q064 Q068 Q087 Q091 Q096 Q102 Q104 Q110 Q113 Q119 Q122 Q127 Q129 Q136 Q137 Q144 Q150 Q153 Q155 Q193 Q195 Q196 Q218 Q239)

- as of 2026-10-10 | commit 417d675796 (dirty) | 28 questions | default asker ZV-1006
- score: mean over scored rows (exact, set-F1, judge 1 / 0.5 / 0); skipped rows are excluded
- judge gemini-3.5-flash-lite: 4 API calls, 1244 tokens (not counted in tokens/q)
- errors: 0
- dev has 60 questions: per-category numbers are noisy; use the test split for claims
- LLM API calls (answer + judge HTTP requests incl. retries, all sessions): 32
- verifier: {'pass': 28} (regenerated/failed = triggered)

## Overall

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 28 | 28 | 0 | 0.89 | 1.00 | 0.94 | 5919 | 1934 | 11738.7 | 1295.1 |

## By hops

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 9 | 9 | 0 | 1.00 | 1.00 | 0.93 | 5893 | 2006 | 11945.4 | 1345.0 |
| 2 | 11 | 11 | 0 | 1.00 | 1.00 | 1.00 | 5893 | 1824 | 11711.3 | 1342.2 |
| 3 | 8 | 8 | 0 | 0.62 | 1.00 | 0.88 | 5984 | 2006 | 11721.6 | 1054.6 |

## By category

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cross_document | 1 | 1 | 0 | 1.00 | 1.00 | 1.00 | 6020 | 2006 | 11282.4 | 1569.5 |
| org_structure | 8 | 8 | 0 | 1.00 | 1.00 | 1.00 | 5872 | 2006 | 10916.5 | 1253.5 |
| personalised | 3 | 3 | 0 | 0.00 | 1.00 | 1.00 | 5897 | 2006 | 11953.6 | 986.0 |
| policy | 1 | 1 | 0 | 1.00 | 1.00 | 0.33 | 6500 | 2006 | 12343.5 | 1345.0 |
| project | 9 | 9 | 0 | 1.00 | 1.00 | 0.89 | 5913 | 2006 | 11711.3 | 1342.2 |
| skills_experience | 6 | 6 | 0 | 1.00 | 1.00 | 1.00 | 5888 | 1672 | 11652.9 | 2009.2 |
