# Test-split plan (3.3d): quota, days, order

Written before the freeze and before any test-split run. S1 and S5 only; S3 is dev-only (88.6k tokens per question, and its system refuses the test split).

## Size

`python -m waypoint.eval.split --counts` prints counts only, no ids: **dev 60, test 191**. Test strata (category | hops: n):

| stratum | n | stratum | n | stratum | n |
|---|---:|---|---:|---|---:|
| cross_document 2 | 3 | org_structure 2 | 9 | policy 1 | 24 |
| cross_document 3 | 7 | org_structure 3 | 8 | project 1 | 7 |
| employee_lookup 1 | 11 | personalised 1 | 2 | project 2 | 13 |
| employee_lookup 2 | 3 | personalised 2 | 15 | project 3 | 8 |
| org_structure 1 | 43 | personalised 3 | 10 | skills_experience 2 | 28 |

By hops: 1-hop 87, 2-hop 71, 3-hop 33. Several strata are under 10, so per-stratum intervals will be wide; claims use the overall and per-hop intervals (`waypoint.eval.bootstrap`).

**Judge-scored test rows: 59.** The scorers are assigned by gold shape (CLAUDE.md 1.4): 74 of all 251 are judge rows, and 15 of them are dev rows (every dev run reports 15), so 74 − 15 = 59. This comes from counts, not from question text.

## Requests per question, measured from run logs

From `python -m waypoint.eval.callstats <run>`. The quota counts **HTTP requests**, so retries are included. Logical calls are listed alongside.

| run | questions | HTTP requests | per question | router | generator | judge | retries |
|---|---:|---:|---:|---:|---:|---:|---:|
| S5 dev 3.3c (`20261012-193747_s5_dev`, routes not cached, as on test) | 60 | 140 | 2.33 | 60 | 60 | 3 (cache) | 17 |
| S5 dev 3.3a (`20261012-003243_s5_dev`, routes cached) | 60 | 67 | 1.12 | 0 | 60 | 6 | 1 |
| S1 dev (`20261011-062212_s1_dev`) | 60 | 75 | 1.25 | – | 60 | 15 | 0 |
| S5 held-out (`20261012-204928_s5_heldout`) | 8 | 19 | 2.38 | 9 | 9 | 0 | 1 |
| S5 safety v2 (`20261012-195500_s5_safety`) | 44 | 76 | 1.73 | 45 | 24 | 0 | 7 |

Notes on the counts:
- Router calls include validation retries: 9 for 8 held-out questions, 45 for 44 safety questions, so about 2% extra.
- Verifier regenerations: 0/60 on dev, 1/8 on held-out.
- Retries (429 and 5xx re-sends) were 17 for 60 questions on the uncached S5 dev run, 0.28 per question. The logs do not say which model a retry hit, so the plan counts them **against each model** (worst case).
- Judge calls on test are not cached, so expect one per judge-scored row.

## Which quota each call uses

| model | used by | daily limit |
|---|---|---|
| gemini-3.1-flash-lite (`MODEL_ANSWER`) | S5 generator and regenerations, S1 answers | 500 requests/day (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`), 5 requests/min |
| gemini-3.5-flash-lite (`MODEL_FAST`) | S5 router **and** the judge (both systems): they share this quota | not observed (never hit; the most used in one day so far was about 230); 5 requests/min |

The daily quota resets around **12:30 pm IST** (midnight Pacific). After a quota stop (`DailyQuotaExceeded`), the run stops cleanly. Re-running the same command resumes from its checkpoint, and finished questions are never re-asked.

## Expected requests on the test split (191 questions)

| run | gemini-3.1-flash-lite | gemini-3.5-flash-lite | worst case with retries (each model) |
|---|---:|---:|---|
| twins (S5, 2 rows) | ≤ 2 | ≤ 2 | ≤ 6 |
| S5 test | 191 + regenerations (allow 10) = ~201 | router 191 + 2% (~4) + judge 59 = ~254 | +54 retries: 3.1 ≤ 255, 3.5 ≤ 308 |
| S1 test | 191 | judge 59 | +10 retries (S1 dev had 0): 3.1 ≤ 201, 3.5 ≤ 69 |

Time, from the dev pace at 5 requests/min:
- S5: 60 uncached questions took 36 min (`run_config.json` start/finish), so 191 is about 2 h.
- S1: 60 questions plus 15 judge calls took 12 min, so 191 is about 40 min.

## Two days

| day | runs | gemini-3.1-flash-lite | gemini-3.5-flash-lite |
|---|---|---:|---:|
| 1 (after the 12:30 pm IST reset) | twins, freeze commit + tag, **S5 test** | ≤ ~260 | ≤ ~315 |
| 2 (after the next reset) | **S1 test**, scoring, bootstrap CIs, judge sample | ≤ ~205 | ≤ ~70 |

- Each day stays under 500 per model, even in the worst case.
- If S5 stops on a daily quota on day 1, it resumes on day 2 before S1, and S1 moves to day 3 if needed.
- Calls and quota are stated again before each run.

## Order

1. **Twins**: `python -m waypoint.eval.safety --system s5 --set twins` (2 questions, before the freeze, not the test split). Report the `twin_check` result as is: a difference is a differential-channel finding, not a fix.
2. **Freeze**:
   - `python -m waypoint.eval.freeze`;
   - commit docs/freeze.md;
   - `git tag -a freeze-1 -m "freeze"` on that commit;
   - `python -m waypoint.eval.freeze --check`;
   - `make test` and `make test-graph` pass at the tagged commit.
3. **S5 test**: `mingw32-make eval-test SYSTEM=s5`. It refuses unless the tree is clean and HEAD is freeze-1, or a docs-only descendant of it.
4. **S1 test**: `mingw32-make eval-test SYSTEM=s1`.
5. **Scoring**: done by the runner (exact, set-F1, judge). `results.csv`, `summary.md` and `judge_review.csv` go to each run folder, and `run_config.json` records freeze-1, its commit and HEAD.
6. **Bootstrap CIs**: `python -m waypoint.eval.bootstrap --a <S5 test run> --b <S1 test run>`.
   - Seed 42, 10,000 resamples, percentile 95%.
   - Overall, by hops and by category, plus the paired S5 − S1 difference.
   - A difference is claimed only when its interval excludes zero.
7. **Judge hand check**:
   - For each system, the author fills `human_verdict` in `judge_review.csv` for a 10% sample of its judge-scored rows: ceil(0.1 × 59) = 6 rows.
   - The rows are chosen by `random.Random(42).sample(sorted(judge-scored ids), 6)`.
   - The agreement rate goes into docs/results.md (3.3e).

## Note after day 1 (2026-10-16): judge count

S5 test (`eval_runs/20261016-032128_s5_test`): **60 judge-scored rows**, not 59. `callstats` shows **60 judge calls** (60 HTTP requests, 0 retries). The `detail` column in results.csv explains the gap. 59 rows went to the judge because of their gold shape (`sentence answer`), which matches the plan. One more row has an exact-shaped gold, but the scorer passed it to the judge because S5's answer named another employee besides the gold one (`exact key plus extra employees`). CLAUDE.md 1.4 states this rule: an exact entity key also requires no other same-type entity in the answer. So the judge count depends on the answer, not only on the gold. 59 is the minimum, and S1's count can differ for the same reason. The judge hand check (step 7) uses each system's actual judge-scored rows.
