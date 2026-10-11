# S5 Waypoint on dev: first run (slice 2.5, before any fix)

Run `eval_runs/20261011-140305_s5_dev` (commit eca05fd). Its `summary.md` is frozen unchanged in
[s5_dev_2.5.md](s5_dev_2.5.md) as the pre-fix baseline; 2.6 fixes are compared against it.
Models: router `gemini-3.5-flash-lite` (MODEL_FAST), generator `gemini-3.1-flash-lite` (MODEL_ANSWER),
judge `gemini-3.5-flash-lite`. As of 2026-10-10, asker ZV-1006 (HR) except Q209/Q210.

- The router outputs came from a prompt tuned on dev (router-v2, dev few-shots), so the S5 dev numbers are somewhat optimistic.
- Router outputs were served from `.cache/router/` (0 router calls in this run). Their tokens are still
  counted in tokens/q (5,195 per question on average, about 80% of S5's total); their latency is not.
- Dev has 60 questions (1 to 20 per group): every number below is noisy; claims need the test split.

## Scoreboard (dev)

Scores: exact, set-F1 or judge (1 / 0.5 / 0). Latency is the p50 per question. "excl. wait" leaves out client-side
waiting (rate-limiter pacing and per-minute 429 sleeps). S1/S3 rows were recorded before that was measured, so
their excl.-wait figures are n/a. S3's 29.9 s median was mostly deliberate rate-limit spacing, not model time.

| hops | n | S1 | S3 | S5 | S5 − S1 | source recall S1/S3/S5 | tokens/q S1/S3/S5 | p50 latency s S1/S3/S5 | p50 excl. wait s S1/S3/S5 |
|---|---:|---:|---:|---:|---:|---|---|---|---|
| all | 60 | 0.70 | 0.90 | 0.53 | −0.17 | 0.65/0.74/0.59 | 1,242/88,601/6,558 | 11.8/29.9/12.6 | n/a/n/a/2.1 |
| 1 | 27 | 0.91 | 0.96 | 0.59 | −0.31 | 0.93/0.78/0.63 | 1,332/88,591/6,303 | 11.6/30.0/12.1 | n/a/n/a/2.0 |
| 2 | 22 | 0.66 | 0.91 | 0.52 | −0.14 | 0.48/0.74/0.49 | 1,123/88,615/6,718 | 12.0/29.9/17.1 | n/a/n/a/2.6 |
| 3 | 11 | 0.29 | 0.70 | 0.41 | +0.12 | 0.33/0.67/0.70 | 1,259/88,602/6,867 | 11.8/29.8/23.7 | n/a/n/a/2.8 |

| category | n | S1 | S3 | S5 | S5 − S1 | source recall S1/S3/S5 | tokens/q S1/S3/S5 | p50 latency s S1/S3/S5 | p50 excl. wait s S1/S3/S5 |
|---|---:|---:|---:|---:|---:|---|---|---|---|
| cross_document | 3 | 0.50 | 1.00 | 0.83 | +0.33 | 0.50/0.83/1.00 | 1,522/88,667/7,055 | 11.1/29.3/11.4 | n/a/n/a/1.6 |
| employee_lookup | 4 | 1.00 | 1.00 | 0.75 | −0.25 | 0.75/1.00/0.75 | 1,089/88,598/6,419 | 13.2/30.4/12.2 | n/a/n/a/1.3 |
| org_structure | 20 | 0.70 | 0.95 | 0.45 | −0.25 | 0.68/0.74/0.43 | 1,137/88,582/6,172 | 11.8/30.0/12.2 | n/a/n/a/1.4 |
| personalised | 8 | 0.50 | 0.56 | 0.38 | −0.12 | 0.44/0.62/0.69 | 1,144/88,620/6,393 | 12.0/29.8/12.1 | n/a/n/a/1.8 |
| policy | 7 | 0.86 | 0.93 | 0.71 | −0.14 | 1.00/0.29/0.86 | 1,936/88,603/6,588 | 2.0/28.9/11.0 | n/a/n/a/2.1 |
| project | 9 | 0.69 | 0.96 | 0.56 | −0.13 | 0.50/0.94/0.56 | 1,183/88,594/6,808 | 11.8/30.1/23.7 | n/a/n/a/4.7 |
| skills_experience | 9 | 0.71 | 0.90 | 0.49 | −0.22 | 0.67/0.87/0.47 | 1,054/88,615/7,186 | 12.0/29.9/23.7 | n/a/n/a/3.5 |

Citation precision: S5 0.99, S1 0.79, S3 0.55. LLM API calls: 103 (60 generator, 28 regenerations, 15 judge).
The 2.x gate (S5 beats S1 on 1- and 2-hop) is **not met**.

## Verifier

Triggered on 28 of 60 questions (47%): 17 regenerated and passed, 11 failed and answered "I can't confirm that."
**All 28 were false alarms.** Every flagged item was an artefact of the name check, never an unsupported fact:

- The Capitalised-phrase regex allows "." inside a word, so a phrase runs across a sentence end:
  "Arvind Kulkarni. He", "Sneha Hegde. These", "INR. This" (26 rows).
- The connector "and" joins two separate names into one phrase: "Project Nova and Rahul Khanna" (2 rows: Q113, Q119).

First attempts of the 28 triggered rows, scored offline: 21 correct (exact/set-F1 = 1), 3 wrong for an unrelated
reason (hotel cap formatting, cause C), 4 judge-routed, checked by hand (Q091, Q113, Q119 correct; Q218 lists extra
offences, so it is partial at best). The regeneration only "fixed" answers by dropping the trailing sentence; in the
3 hotel rows it also dropped "INR". Cost: 11 correct-or-partial answers turned into 0, and 28 extra generator calls.
How many real hallucinations the verifier would catch is not measured by this run.

## Failures by category, with root causes (no fixes in 2.5)

Rows below 1.0: 30 (A 11, B 11, C 3, D 2, E 3). Root causes, largest first:

**A. Verifier false alarms (11 rows scored 0; 17 more cost a regeneration).** See above.
org_structure Q003, Q052, Q058, Q091; project Q113, Q119, Q122, Q127; skills_experience Q150, Q153; policy Q218.

**B. The pack names the subject only by id (11 rows, all "I can't find that").** Template arguments and rule
subjects are rendered as bare ids (`manager(employee_id=ZV-1004)`, `rule NOTICE_PERIOD for subject ZV-1028`,
`previous_employer(org_id=ORG002)`). The question names a person or organisation ("Divya Krishnamurthy"), the pack never
connects that name to the id, and the generator, told never to guess, answers not-found although the row holds the
answer. The same packs for list questions mostly worked, because the rows themselves carry the names asked for.
org_structure Q002, Q006, Q014, Q015, Q075, Q080, Q083; personalised Q178, Q181; skills_experience Q133, Q139.

**C. Rule values are raw numbers (3 rows).** HOTEL_CAP renders `cap_inr: 11000`; the generator copies "11000" and
the exact scorer wants "INR 11,000". personalised Q193, Q195, Q196 (S1 also 0). Fix options for 2.6: format money in
the rule value (INR, Indian grouping), and/or make exact scoring comparison-normalise numbers (an eval change, same
for every system).

**D. Over-concise policy answers (2 rows at 0.5, same as S1).** "Lead with the value, at most one short sentence"
drops required detail: Q232 lists SEV1 to SEV4 without definitions or times; Q211 omits the medical-certificate
condition that is in the rule's notes.

**E. Known coverage gaps from 2.4 (3 rows).** Q169 join-date filter (no template; the text fallback finds nothing),
Q167 education (not in the graph; text finds 1 of 4 people), Q243 needs text then graph (who chairs the POSH
committee, then her manager): a plan cannot pass an entity found in text to a template.

Not a cause in this run: no errors, no router errors (routes were cached from 2.4), no access-filter effect (the
main eval asks as HR; the 3.3 safety questions with non-authorised askers will exercise it).
