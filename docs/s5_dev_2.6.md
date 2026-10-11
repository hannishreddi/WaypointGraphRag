# S5 Waypoint on dev after the 2.6 fix loop

Final run `eval_runs/20261011-204733_s5_dev` (commit aa998d2, config `answer-v2:router-v2:pack-v3:verify-v2`).
The pre-fix baseline stays frozen in [s5_dev_2.5.md](s5_dev_2.5.md) and its analysis in
[s5_dev_2.5_report.md](s5_dev_2.5_report.md). S1 `eval_runs/20261011-062212_s1_dev`, S3 `eval_runs/20261011-065206_s3_dev`
(unchanged since 1.5).

Models: router `gemini-3.5-flash-lite` (MODEL_FAST), S5 generator and S1/S3 answers `gemini-3.1-flash-lite`
(MODEL_ANSWER), judge `gemini-3.5-flash-lite`. As of 2026-10-10, asker ZV-1006 (HR) except Q209/Q210.

Read with care:
- Dev has 60 questions (1 to 20 per group). Every number here is noisy, and the router prompt and the 2.6
  fixes were developed on dev, so S5's dev numbers are optimistic. Claims need the test split (3.3).
- Router outputs came from `.cache/router/` (0 router calls); their recorded tokens are still counted in S5's
  tokens/q (about 5,200 per question, most of the total).
- "Uncached" = input tokens the provider did not serve from its implicit cache, plus output tokens. S3's
  uncached figure swings between groups (2,676 to 11,256) depending on Gemini's implicit cache hits.

## Scoreboard (dev)

| split | n | S1 | S3 | S5 | S5 − S1 | source recall S1/S3/S5 | tokens/q S1/S3/S5 | uncached tokens/q S1/S3/S5 |
|---|---:|---:|---:|---:|---:|---|---|---|
| all | 60 | 0.70 | 0.90 | 0.96 | +0.26 | 0.65/0.74/0.96 | 1,242/88,601/6,276 | 1,242/5,548/4,304 |

| hops | n | S1 | S3 | S5 | S5 − S1 | source recall S1/S3/S5 | tokens/q S1/S3/S5 | uncached tokens/q S1/S3/S5 |
|---|---:|---:|---:|---:|---:|---|---|---|
| 1 | 27 | 0.91 | 0.96 | 1.00 | +0.09 | 0.93/0.78/1.00 | 1,332/88,591/6,142 | 1,332/9,037/4,210 |
| 2 | 22 | 0.66 | 0.91 | 0.93 | +0.27 | 0.48/0.74/0.90 | 1,123/88,615/6,414 | 1,123/2,697/4,408 |
| 3 | 11 | 0.29 | 0.70 | 0.95 | +0.67 | 0.33/0.67/1.00 | 1,259/88,602/6,330 | 1,259/2,684/4,324 |

| category | n | S1 | S3 | S5 | S5 − S1 | source recall S1/S3/S5 | tokens/q S1/S3/S5 | uncached tokens/q S1/S3/S5 |
|---|---:|---:|---:|---:|---:|---|---|---|
| cross_document | 3 | 0.50 | 1.00 | 0.83 | +0.33 | 0.50/0.83/1.00 | 1,522/88,667/6,890 | 1,522/2,749/4,884 |
| employee_lookup | 4 | 1.00 | 1.00 | 0.75 | −0.25 | 0.75/1.00/0.75 | 1,089/88,598/6,548 | 1,089/2,680/4,542 |
| org_structure | 20 | 0.70 | 0.95 | 1.00 | +0.30 | 0.68/0.74/1.00 | 1,137/88,582/5,970 | 1,137/11,256/4,064 |
| personalised | 8 | 0.50 | 0.56 | 1.00 | +0.50 | 0.44/0.62/0.94 | 1,144/88,620/6,216 | 1,144/2,702/4,210 |
| policy | 7 | 0.86 | 0.93 | 1.00 | +0.14 | 1.00/0.29/1.00 | 1,936/88,603/6,511 | 1,936/2,686/4,505 |
| project | 9 | 0.69 | 0.96 | 1.00 | +0.31 | 0.50/0.94/1.00 | 1,183/88,594/6,046 | 1,183/2,676/4,040 |
| skills_experience | 9 | 0.71 | 0.90 | 0.93 | +0.22 | 0.67/0.87/0.92 | 1,054/88,615/6,732 | 1,054/2,697/4,726 |

Citation precision: S5 0.96, S1 0.79, S3 0.55. S5 p50 latency 11.7 s, 4.1 s excluding client-side waits.
The 2.x gate (S5 beats S1 on 1- and 2-hop dev) is **met**.

## Verifier

Triggered on 0 of 60 questions (2.5: 28 of 60, all false alarms of the name check). It is not switched off:
`tests/test_verify_regressions.py` keeps the 28 old false alarms passing on their real packs and checks that
planted fabrications (invented people and project, a number, a year, a date; next to real names, at sentence
ends, after "and") still fail. How many real hallucinations it catches on live answers is not measured here.

## The fix loop, one root cause per commit

| step | commit | all | 1-hop | 2-hop | 3-hop | verifier triggered | tokens/q (uncached) |
|---|---|---:|---:|---:|---:|---:|---|
| 2.5 baseline | eca05fd | 0.53 | 0.59 | 0.52 | 0.41 | 28 | 6,558 (4,585) |
| A verifier: names stop at sentence ends, not joined on "and" | 32c5748 | 0.71 | 0.81 | 0.61 | 0.68 | 0 | 6,136 (4,163) |
| B pack names step arguments and rule subjects | a192449 | 0.90 | 0.96 | 0.93 | 0.68 | 0 | 6,143 (4,170) |
| C money as INR with Indian grouping; D generator keeps conditions and per-item figures | 75b0a4c, aa998d2 | 0.96 | 1.00 | 0.93 | 0.95 | 0 | 6,276 (4,304) |

C and D were verified on their affected rows with `--ids` (Q193, Q195, Q196; Q211, Q232) and measured in one
full run together. Against the after-B run, per question: Q193, Q195, Q196 0 -> 1, Q211 and Q232 0.5 -> 1; no
question that scored 1.0 after B scored lower. D's longer policy/rule answers cost about 130 tokens per question.

Caveat on Q211 ("How many casual and sick leave days do I get?"): the judge now scores it 1, but the answer still
omits the medical-certificate condition that is in the rule's notes. Count it as judge leniency, not a fix.

## Remaining failures (3 rows, all known coverage gaps E, listed under "Later" in PLAN.md)

- **Q169** (employee_lookup, 2-hop, 0): join-date filter. No template filters by join_date; the text fallback
  finds nothing.
- **Q167** (skills_experience, 2-hop, 0.4): education is not in the graph; text search finds 1 of the people.
- **Q243** (cross_document, 3-hop, 0.5): who chairs the POSH committee is found in text, but a plan cannot pass
  an entity found in a passage to a template, so her manager is not looked up.

These need three different mechanisms (a join-date template, education data, passage-to-plan references), not
one template gap, so Text2Cypher was not built and `s5-direct` was not needed (gate met).
