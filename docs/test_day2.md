# Test split, day 2 (2026-10-16): S1 test and S5 − S1 bootstrap

Numbers only, no interpretation. Models: answers gemini-3.1-flash-lite (`MODEL_ANSWER`), judge gemini-3.5-flash-lite (`MODEL_FAST`, judge-v1), embeddings embed-v5.0-fast; S5's router is also gemini-3.5-flash-lite. As-of 2026-10-10, default asker ZV-1006.

Runs:
- S5 test: `eval_runs/20261016-032128_s5_test` (day 1, see docs/test_day1.md)
- S1 test: `eval_runs/20261016-134333_s1_test` (final; resumed 189 rows from the checkpoint of the first session)

Run after the 12:30 pm IST quota reset (started 12:35 IST). Expected before the run (docs/test_plan.md): gemini-3.1-flash-lite 191 answers (worst case ≤ 201), gemini-3.5-flash-lite judge ~60 (worst case ≤ ~70).

## S1 sessions

| session | folder | time (IST) | rows finished | errors | HTTP requests |
|---|---|---|---:|---:|---:|
| 1 | `eval_runs/20261016-134237_s1_test` (superseded, not archived) | 12:35:10–13:42:37 | 189 | 2 | 308 for the 189 rows + 10 for the 2 error rows = 318 (summary header) |
| 2 (resume, same command) | `eval_runs/20261016-134333_s1_test` | 13:43:06–13:43:33 | 2 | 0 | 4 (2 answers, 2 judge) |

- Session 1 errors: two judge-routed rows; `LLMError: gemini-3.1-flash-lite: giving up after 4 retries: HTTP 503 ... "This model is currently experiencing high demand" (UNAVAILABLE)`, 5 requests each. Error rows are not checkpointed, so the unchanged command retried them in session 2. No code was changed.
- HTTP requests sent for S1 on day 2: 318 + 4 = 322. The final summary header says 312 (= 308 + 4), because the 10 requests of the error rows were never checkpointed.

## S1 summary as printed by the runner (`eval_runs/20261016-134333_s1_test/summary.md`)

# Eval: s1 on test

- as of 2026-10-10 | commit 4553c4c53d | 191 questions | default asker ZV-1006
- score: mean over scored rows (exact, set-F1, judge 1 / 0.5 / 0); skipped rows are excluded
- judge gemini-3.5-flash-lite: 2 API calls, 598 tokens (not counted in tokens/q)
- errors: 0
- LLM API calls (answer + judge HTTP requests incl. retries, all sessions): 312
- resumed 189 finished rows from the checkpoint

## Overall

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 191 | 191 | 0 | 0.70 | 0.63 | 0.77 | 1203 | 0 | 11779.7 | 4013.6 |

## By hops

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 87 | 87 | 0 | 0.91 | 0.82 | 0.76 | 1333 | 0 | 11922.4 | 3792.2 |
| 2 | 71 | 71 | 0 | 0.60 | 0.53 | 0.84 | 1024 | 0 | 11677.2 | 4639.0 |
| 3 | 33 | 33 | 0 | 0.35 | 0.38 | 0.66 | 1246 | 0 | 10891.3 | 4953.4 |

## By category

| group | n | scored | skipped | score | source recall | citation precision | tokens/q | cached in/q | p50 latency ms | p50 latency excl. wait ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cross_document | 10 | 10 | 0 | 0.55 | 0.55 | 0.47 | 1385 | 0 | 7824.5 | 3090.9 |
| employee_lookup | 14 | 14 | 0 | 0.95 | 0.64 | 0.64 | 1030 | 0 | 11523.1 | 2979.3 |
| org_structure | 60 | 60 | 0 | 0.73 | 0.71 | 0.81 | 1189 | 0 | 11958.0 | 3384.2 |
| personalised | 27 | 27 | 0 | 0.28 | 0.20 | 0.86 | 932 | 0 | 9415.3 | 7033.4 |
| policy | 24 | 24 | 0 | 0.81 | 0.75 | 0.64 | 1759 | 0 | 16189.4 | 15271.4 |
| project | 28 | 28 | 0 | 0.78 | 0.70 | 0.75 | 1308 | 0 | 10949.6 | 5080.5 |
| skills_experience | 28 | 28 | 0 | 0.79 | 0.75 | 1.00 | 937 | 0 | 13121.5 | 8271.0 |

## S1 requests, retries, errors, verifier

- Requests (`waypoint.eval.callstats`, final folder): `20261016-134333_s1_test: 191 questions, 312 HTTP requests (1.63/question); logical: router 0, generator 191, judge 2; retries 119; judge-scored rows 59`.
- callstats on session 1 (`20261016-134237_s1_test`): `189 questions, 308 HTTP requests (1.63/question); logical: router 0, generator 189, judge 57; retries 62; judge-scored rows 57`.
- callstats computes retries as requests − logical calls. It takes the judge count from the summary's judge line, which covers the last session only (2), while requests sum over all sessions. So "retries 119" also counts session 1's 57 judge calls: retries are 62 (session 1) + 0 (session 2) = **62**.
- Errors: 0 in the final run (2 in session 1, retried, see above).
- Verifier: n/a for all 191 rows (S1 has no verifier; the `verifier` column is empty).
- Judge-scored rows: 59, all `sentence answer` (none fell back from exact). S5 had 60 (docs/test_plan.md, note after day 1).
- For comparison, S5 test (callstats): `191 questions, 446 HTTP requests (2.34/question); logical: router 193, generator 193, judge 60; retries 0; judge-scored rows 60`.

## Bootstrap, verbatim

`python -m waypoint.eval.bootstrap --a eval_runs/20261016-032128_s5_test --b eval_runs/20261016-134333_s1_test` (a = S5, b = S1):

```
# Bootstrap 95% CIs (seed 42, 10,000 resamples, percentile)

- a: 20261016-032128_s5_test
- b: 20261016-134333_s1_test

## a: overall 0.950 [0.921, 0.976] (n=191)
- hops 1: 0.931 [0.879, 0.977] (n=87)
- hops 2: 0.971 [0.927, 1.000] (n=71)
- hops 3: 0.955 [0.879, 1.000] (n=33)
- category cross_document: 0.950 [0.850, 1.000] (n=10)
- category employee_lookup: 1.000 [1.000, 1.000] (n=14)
- category org_structure: 0.983 [0.950, 1.000] (n=60)
- category personalised: 1.000 [1.000, 1.000] (n=27)
- category policy: 0.750 [0.583, 0.896] (n=24)
- category project: 0.964 [0.893, 1.000] (n=28)
- category skills_experience: 0.962 [0.887, 1.000] (n=28)

## b: overall 0.701 [0.640, 0.761] (n=191)
- hops 1: 0.914 [0.856, 0.960] (n=87)
- hops 2: 0.605 [0.497, 0.709] (n=71)
- hops 3: 0.347 [0.197, 0.503] (n=33)
- category cross_document: 0.550 [0.250, 0.850] (n=10)
- category employee_lookup: 0.952 [0.878, 1.000] (n=14)
- category org_structure: 0.733 [0.617, 0.833] (n=60)
- category personalised: 0.278 [0.111, 0.444] (n=27)
- category policy: 0.812 [0.667, 0.938] (n=24)
- category project: 0.781 [0.631, 0.914] (n=28)
- category skills_experience: 0.793 [0.657, 0.910] (n=28)

## paired difference a - b (191 questions scored by both)
- all: 0.249 [0.182, 0.317] (n=191); difference claimed: yes
- hops 1: 0.017 [-0.034, 0.075] (n=87); difference claimed: no
- hops 2: 0.366 [0.250, 0.484] (n=71); difference claimed: yes
- hops 3: 0.607 [0.420, 0.783] (n=33); difference claimed: yes

```

The tool prints the paired difference overall and by hops only, **not by category**. Per-category values above are per-system means with their own intervals; no paired per-category difference was computed (no code change, no ad-hoc analysis).

### Does each paired difference's interval exclude zero

| group | n | S5 − S1 | 95% CI | excludes zero |
|---|---:|---:|---|---|
| all | 191 | 0.249 | [0.182, 0.317] | yes |
| hops 1 | 87 | 0.017 | [-0.034, 0.075] | no |
| hops 2 | 71 | 0.366 | [0.250, 0.484] | yes |
| hops 3 | 33 | 0.607 | [0.420, 0.783] | yes |

## Freeze fields from run_config.json

| field | S5 (`20261016-032128_s5_test`) | S1 (`20261016-134333_s1_test`) |
|---|---|---|
| system_config | `answer-v2:router-v4:pack-v5:verify-v2:gemini-3.1-flash-lite:gemini-3.5-flash-lite` | `baseline-v1:gemini-3.1-flash-lite` |
| git_commit | `975e58c117699b8007e02fc3986aa0ce749d3291` | `4553c4c53d6288d442dc88b5d9ce9886e22dc3e3` |
| git_dirty | `False` | `False` |
| freeze_tag | `freeze-1` | `freeze-1` |
| freeze_commit | `975e58c117699b8007e02fc3986aa0ce749d3291` | `975e58c117699b8007e02fc3986aa0ce749d3291` |
| head | `975e58c117699b8007e02fc3986aa0ce749d3291` | `4553c4c53d6288d442dc88b5d9ce9886e22dc3e3` |
| started_at | `2026-10-16T02:30:06` | `2026-10-16T13:43:06` |
| finished_at | `2026-10-16T03:21:28` | `2026-10-16T13:43:33` |
| resumed_rows | `0` | `189` |

S1's HEAD `4553c4c` is the docs-only commit "3.3d day 2: judge count note after day 1"; `git diff --name-only freeze-1..4553c4c` = docs/test_day1.md, docs/test_plan.md.
