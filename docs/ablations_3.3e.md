# 3.3e Ablations: pre-registration

Written 2026-10-16, **before any ablation run**. It is committed together with the ablation code, and no ablation has been run at that commit. Definitions, predictions, request estimates and run order are fixed here. Any later change is declared in a dated section at the end of this file, and the numbers it affects are labelled.

The S5 and S1 test numbers are final and are not affected. They stay tied to 975e58c (freeze-1) and 4553c4c (docs/test_day2.md). Every ablation runs on the dev split, the safety set or the held-out set, **never the test split**: all ablations are `dev_only`, and `make eval-test` refuses them.

## Frozen system untouched

- Code: `waypoint/eval/ablations.py` (wrappers), registered in `waypoint/eval/systems.py`, with an access note per ablation in `waypoint/eval/safety.py`. `git diff freeze-1 -- waypoint/ ':!waypoint/eval'` is empty, and a test checks it.
- `tests/test_ablations.py` runs a fixed mock-LLM scenario of S5: scripted replies, temporary router cache, fixed query embedding, Neo4j. It has 7 cases: template, regeneration, restricted rule as a peer and as HR, text path as HR and as a peer, refusal. The output must be **byte-identical** to `tests/fixtures/s5_golden_freeze1.json`:
  - the golden comes from the **freeze-1 code** (`tests/fixtures/build_s5_golden.py`, run in a `git worktree` at freeze-1; the builder refuses to write unless `waypoint` was imported from that worktree);
  - the comparison covers the Response JSON, the trace, and sha256 of every system and user prompt; `latency_ms` is set to 0;
  - it is checked before and after every ablation has run in the same process, and after an ablation call that raised. So the patches are restored and S5 stays the frozen S5.
- The default S5 config id equals docs/freeze.md: `answer-v2:router-v4:pack-v5:verify-v2:gemini-3.1-flash-lite:gemini-3.5-flash-lite`. Each ablation has its own config id `<ablation>-v1:<that id>`, so it gets its own checkpoint.

## Reference runs: fresh

The full-S5 dev run `eval_runs/20261012-193747_s5_dev` and the safety run `eval_runs/20261012-195500_s5_safety` both have the frozen config id. But both ran on a **dirty tree** (`git_dirty: true`, commit 621213e, before F2–F4 were committed in 9638263), so their code cannot be proven equal to freeze-1. So the references are re-run at HEAD:
- **R1:** S5 on dev.
- **R2:** S5 on the safety set.

Their checkpoints have the same key as the old runs, so a plain re-run would resume every row and make 0 calls. Before R1 and R2, the two old checkpoint files are **moved, not deleted**, to `eval_runs/.checkpoints/archive/`:
- `s5_dev_b43c99b46257.jsonl`
- `s5_safety_8d71bd94ea50.jsonl`

R1 against the 3.3c dev run (0.99) and R2 against safety v2 are also a reproducibility check of the frozen code. Answers can differ because the generator is not deterministic. The router is not a source of difference: the probe below shows every route of R1 and R2 is cached.

## Definitions

| id | ablation (system name) | set | what is removed | what stays |
|---|---|---|---|---|
| A1 | no-verifier (`s5-noverifier`) | dev, 60 | `verify` always passes: no regeneration, no "I can't confirm that." | everything else |
| A2 | no-router (`s5-norouter`) | dev, 60 | the router LLM call. Every question gets the plan `[text_search(query = question, first 300 characters)]`, built in code: intent `policy_text`, confidence 1.0 (no alternative path), `restricted_fact` false. k = 5, the plan executor's default and the same as S1. | asker identity card, access filter, pack, generator, verifier |
| A3 | no-identity (`s5-noidentity`) | dev personalised, 8 | S5 is told the asker is `anonymous` (not an employee) everywhere: router prompt, `"asker"` plan arguments, pack identity item ("not a known employee"), rule engine, access filter. It fails closed. Only shim: the engine raises KeyError for an unknown subject, so a rule about the anonymous asker returns `restricted` (restricted rules, as for any unknown asker) or `insufficient_input` (the others) instead of an error row. | everything else; the scorer still uses the gold for the row's real asker |
| A4 | no-identity (`s5-noidentity`) | safety, 44 | as A3 | the checker scores against the row's real asker |
| A5 | no-access-filter (`s5-noaccess`) | safety, 44 | the retrieval access filter (`waypoint.retrieval.access.visible` lets every chunk through), so all 46 restricted chunks reach every asker on the text path | rule-engine restrictions (EMPLOYMENT_STATUS, WORK_MODE, NOTICE_PERIOD return `restricted`), public-only templates, the router (`restricted_fact`, pay/contact/manipulation refusals), S5's refusal logic |
| A6 | no-verifier (`s5-noverifier`) | held-out, 8 (H01–H08) | as A1 | everything else |

A5 shows the **marginal value of one layer, the retrieval access filter, not of all of rule 6**. The rule engine's restrictions and S5's refusal logic stay on, so A5 is not "S5 without access control".

A6 is an **ablation, not tuning**. Nothing is changed in response to it. H01–H08 were burned for tuning in 3.3c and stay burned.

## Predictions, written before any run

| id | counts as support | counts as a surprise |
|---|---|---|
| A1 | Within noise of R1 (the paired interval includes zero). The verifier triggered 0/60 in the 3.3c dev run, so A1 is close to a no-op on dev; the verifier's value is shown by the fabrication tests and held-out H02, not by dev. | A paired difference whose interval excludes zero, in either direction. |
| A2 | Overall below R1, with the paired interval excluding zero. The drop on 2- and 3-hop is larger than on 1-hop. Overall lands between S1 dev (0.70, `eval_runs/20261011-062212_s1_dev`) and R1. | A2 within 0.05 of R1 overall, or A2 1-hop more than 0.10 below S1 dev. |
| A3 | A large drop on the 8 personalised dev questions compared with R1's same 8 rows: most need the asker's identity ("my manager", "my notice period", a rule about the asker). | No drop: the personalised dev questions would not depend on the asker. |
| A4 | 0/30 attack leaks; A01–A04 (authorised askers) 0/4 given the fact (S5 safety v2: 3/4); controls answered about as often as by R2. | Any leak; any authorised row given its fact. |
| A5 | Leaks above 0, only on rows routed to text_search (availability, inference, aggregates, text path); rule-routed rows stay refused. | 0 leaks (other layers also withhold restricted text), or a leak on a rule-routed row (a channel other than the filter). |
| A6 | Weak evidence only, n = 8. In the S5 held-out run the verifier caught H02's computed return date ("1 Mar 2027", not in the sources) and regenerated. Without the verifier that date may reach the answer, which would be support. It may also **not reproduce**, because the generator is not deterministic and may not invent the date this time. That is a valid outcome, not a failure, and it is reported as such. | A wrong or unsupported fact on another held-out row that the verifier would have caught, or any leak on H06–H08: report either. |

How the comparisons are made:
- **Dev (A1, A2, A3):** `python -m waypoint.eval.bootstrap --a <R1> --b <ablation>`, with the paired difference on the questions both runs scored. A difference is claimed only when its interval excludes zero. Dev is small (60; by hops 27/22/11; personalised 8), so the intervals are wide. Dev is also optimistic for S5: 11 router few-shots are dev questions, and the router was tuned on dev.
- **Safety and held-out (A4, A5, A6):** verdict counts from the checker (`safety-check-v3`) for attacks (30), controls (10) and authorised askers (4); uniformity of refusals; expected facts found on the held-out authorised rows. No rates are generalised: only two people have a restricted status.

## Router-cache probe (0 LLM calls)

`.venv\Scripts\python.exe -m waypoint.eval.ablations --probe-router-cache` routes each planned set through a client that fails on any call. It writes nothing; `.cache/router` had 561 files before and after. Output on 2026-10-16:

```
R1 s5 dev, A1 s5-noverifier dev: 60 questions, 60 cached routes, 0 router calls needed
A3 s5-noidentity dev personalised: 8 questions, 0 cached routes, 8 router calls needed (Q173 Q178 Q181 Q186 Q193 Q195 Q196 Q207)
A6 s5-noverifier heldout: 8 questions, 8 cached routes, 0 router calls needed
R2 s5 safety, A5 s5-noaccess safety: 44 questions, 44 cached routes, 0 router calls needed
A4 s5-noidentity safety: 44 questions, 0 cached routes, 44 router calls needed (S01 S02 S03 S04 S05 S06 S07 S08 S09 S10 S11 S12 S13 S14 S15 S16 S17 S18 S19 S20 S21 S22 S23 S24 S25 S26 S27 S28 S29 S30 A01 A02 A03 A04 S31 S32 S33 S34 S35 S36 S37 S38 S39 S40)
```

A2 makes no router call by construction. A3 and A4 miss because the asker is part of the router cache key.

## Request estimates (worst case)

The rates come from `waypoint.eval.callstats`:
- S5 dev uncached `20261012-193747_s5_dev`: 0.28 retries per question.
- S5 safety v2 `20261012-195500_s5_safety`: router 45, generator 24, retries 7.
- S5 held-out `20261012-204928_s5_heldout`: router 9, generator 9, retries 1.

The logs do not say which model a retry hit, so retries are counted **against each model**. Judge calls apply to dev runs only, at most one per judge-scored row (15 on dev). An unchanged answer reuses its cached verdict.

| order | run | gemini-3.1-flash-lite (answers) | gemini-3.5-flash-lite (router + judge) |
|---:|---|---:|---:|
| 1 | probe | 0 | 0 |
| 2 | R1 S5 dev | 60 + 17 = ≤ 77 | judge 15 + 17 = ≤ 32 |
| 3 | R2 S5 safety | 44 + 7 = ≤ 51 | 7 = ≤ 7 |
| 4 | A1 no-verifier dev | ≤ 77 | ≤ 32 |
| 5 | A2 no-router dev | 60 + 6 regenerations + 17 = ≤ 83 | ≤ 32 |
| 6 | A3 no-identity dev personalised | 8 + 1 + 3 = ≤ 12 | router 8 + 1 + judge ≤ 8 + 3 = ≤ 20 |
| 7 | A6 no-verifier held-out | 8 + 4 = ≤ 12 | retries only, ≤ 3 |
| 8 | A5 no-access-filter safety | ≤ 51 | ≤ 7 |
| 9 | A4 no-identity safety | ≤ 51 | router 44 + 1 + 7 = ≤ 52 |
| | **total** | **≤ 414** | **≤ 185** |

All runs are planned for **one day, 2026-10-17, after the 12:30 pm IST quota reset**. The answers model has a 500/day limit. The router/judge model's daily limit has never been observed; its highest use in one quota day so far was about 255 (S5 test: router 193 + judge 60, plus the twins, 2026-10-16). If any run stops on a daily quota, re-run the same command the next day: finished rows resume from the checkpoint.

## Run order and commands (2026-10-17, after 12:30 pm IST)

1. Probe: `.venv\Scripts\python.exe -m waypoint.eval.ablations --probe-router-cache` (expect the output above).
2. R1: move `eval_runs/.checkpoints/s5_dev_b43c99b46257.jsonl` to `eval_runs/.checkpoints/archive/`, then `mingw32-make eval-dev SYSTEM=s5`.
3. R2: move `eval_runs/.checkpoints/s5_safety_8d71bd94ea50.jsonl` to `eval_runs/.checkpoints/archive/`, then `.venv\Scripts\python.exe -m waypoint.eval.safety --system s5`.
4. A1: `mingw32-make eval-dev SYSTEM=s5-noverifier`.
5. A2: `mingw32-make eval-dev SYSTEM=s5-norouter`.
6. A3: `mingw32-make eval-dev SYSTEM=s5-noidentity IDS="Q173 Q178 Q181 Q186 Q193 Q195 Q196 Q207"` (the 8 dev personalised questions, from the probe).
7. A6: `.venv\Scripts\python.exe -m waypoint.eval.safety --system s5-noverifier --set heldout`.
8. A5: `.venv\Scripts\python.exe -m waypoint.eval.safety --system s5-noaccess`.
9. A4: `.venv\Scripts\python.exe -m waypoint.eval.safety --system s5-noidentity`.

After each run, `waypoint.eval.callstats` gives the requests actually made. The calls and quota are stated again before the runs start.

## Reporting (docs/results.md, after the runs)

Every number cites its run folder; no number is invented. The ablation table gives the split or set per row, the reference row, the config ids, the run folders, and whether each prediction above held.

The judge hand-check section is titled **"Judge hand check (reviewer: Claude, not the author)"**. It is an empty table (system, question id, judge verdict, reviewer verdict, agree) for the author to paste in. Claude never reads `eval_runs/*_test*/`.
