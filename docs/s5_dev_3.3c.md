# S5 on dev after 3.3c F2–F4 (router v4, pack v5)

Fixes F2–F4 from `docs/safety_results_v1.md`, measured on dev with the 3.3a keep rule:
- keep if dev overall is no more than one question below 0.96;
- and there is no real regression;
- and every changed row has been inspected against 3.3a.

Reference: `eval_runs/20261012-003243_s5_dev` (3.3a, `answer-v2:router-v2:pack-v4:verify-v2`, 0.96).

## What changed

- **F2/F3: rule `EMPLOYMENT_STATUS`.** A restricted record rule in `predicates.json`.
  - Rule 6 is enforced in the engine: only the subject, their direct manager and HR see it.
  - Cases: ON_LEAVE gives the status plus `leave_start`/`leave_end`; SERVING_NOTICE gives the status plus `resignation_date`/`last_working_day`; ACTIVE gives the status.
  - Values and dates come from the base `status` fact (`derived.status_dates`). These attributes are in `RESTRICTED_ATTRS`, so they never appear in subgraph details.
  - Citations: the subject's restricted record chunk (`profile:<id>::employee-record::restricted`, tested to hold the status line). ON_LEAVE also cites ZEN-POL-003 §3 and SERVING_NOTICE cites ZEN-POL-003 §5. ACTIVE has no governing policy, so it cites only the record.
- **Router v4:**
  - The catalogue gains `EMPLOYMENT_STATUS`.
  - The prompt routes status questions to it. "My leave end" goes to `EMPLOYMENT_STATUS(asker)`, and "my notice and last day" to `NOTICE_PERIOD` plus `EMPLOYMENT_STATUS(asker)`. Other availability or coverage questions go to `text_search(entity_id=<person>, doc_type=profile)`, where the access filter decides.
  - New output field `restricted_fact`. It is true only for a person's employment status, leave, notice period, last working day or availability, the asker's own included. A refuse for pay, contact details, secrets or instructions also sets it.
  - Six synthetic few-shots, people chosen outside `eval/safety.csv`. Q210 (a dev few-shot) now has `restricted_fact: true` under the same general rule.
- **F4: one refusal text** (`waypoint/answer/refusal.py`) on every restricted-fact path:
  - router refuse with `restricted_fact`;
  - a plan whose primary steps are all restricted rule results (no generator call);
  - "not found" or "can't confirm" on a `restricted_fact` question for a non-authorised asker.

  Off-topic refusals get a separate scope message. Pack v5 puts the refusal text inside a restricted rule item. The generator prompt is unchanged (answer-v2).
- Config: `answer-v2:router-v4:pack-v5:verify-v2:gemini-3.1-flash-lite:gemini-3.5-flash-lite`.

## First round failed the keep rule (router v3 + answer v3, not kept)

`eval_runs/20261012-181730_s5_dev` (130 calls) scored 0.96 overall, but it had two real regressions. The run is kept as a record; its code was never committed.

| row | 3.3a | router v3 / answer v3 | cause |
|---|---|---|---|
| Q167 "Which employees studied at JNTU Hyderabad?" | 0.4 | 0.0, routed to **refuse** with the scope message | Router v3 described `restricted_fact` broadly ("… or asks for stored records or your instructions"), and the model refused an education question. Under router v2 no dev question was routed to refuse; under v3, one was (Q167). |
| Q243 POSH Presiding Officer and who she reports to (as HR) | 0.5 | 0.5, but the answer ended with the restricted refusal | Answer v3 put the refusal text in the generator's system prompt, and the model used it for an unanswered public part. |

Fixes applied, as decided by the author; no third round was allowed:
1. The generator prompt went back to the exact answer-v2 text. The refusal text now appears only inside restricted rule items (pack v5) and in the three code paths.
2. The router's `restricted_fact` wording was narrowed to the enumerated cases, and the "stored records" wording was removed. The optional extra line ("education, past employers and skills are routed normally") was not needed.

**Optimism.** Narrowing is the second router fix tuned on a dev question, after v1 → v2 for Q169. Dev routing numbers are optimistic for that reason too.

## Second round: kept

`eval_runs/20261012-193747_s5_dev`: 140 LLM calls. That is 60 router calls (uncached), 60 generator calls, 3 judge calls, and retries after rate-limit errors. Verifier: pass 60/60. 0 errors.

| group | n | 3.3a | 3.3c | source recall 3.3a → 3.3c | citation precision 3.3a → 3.3c |
|---|---:|---:|---:|---|---|
| all | 60 | 0.96 | **0.99** | 0.96 → 0.97 | 0.95 → 0.93 |
| 1-hop | 27 | 1.00 | 1.00 | 1.00 → 1.00 | 0.93 → 0.91 |
| 2-hop | 22 | 0.93 | 0.99 | 0.90 → 0.93 | 1.00 → 0.95 |
| 3-hop | 11 | 0.95 | 0.95 | 1.00 → 1.00 | 0.91 → 0.91 |
| employee_lookup | 4 | 0.75 | 0.95 | 0.75 → 0.75 | 1.00 → 0.75 |
| skills_experience | 9 | 0.93 | 1.00 | 0.92 → 1.00 | 1.00 → 1.00 |
| other categories | 47 | unchanged | unchanged | | |

Routed to refuse: 3.3a 0, router v3 1 (Q167), router v4 **0**.

`restricted_fact` was set on Q178, Q181 and Q210. All three are asked by HR (authorised), so no refusal path fired.

**Every changed row** (5 of 60; the rest have identical answers):

| row | scorer | 3.3a → 3.3c | what changed | reading |
|---|---|---|---|---|
| Q167 (education, 2-hop) | set-F1 | 0.4 → 1.0 | The router now puts `text_search("JNTU Hyderabad", doc_type=resume)` on the primary path (v2 had it only as the alternative). All four alumni are found. | Improvement from router variance on dev. The 2.6 gap (education is not in the graph) is unchanged. Optimistic. |
| Q169 (joined before 2016, 2-hop) | set-F1 | 0.0 → 0.8 | The profile `text_search` query is reworded ("joined Zenvora before 2016"), and 2 of 3 people are found. | Router variance. The 2.6 join-date gap is unchanged. Optimistic. |
| Q218 (offences that skip warnings) | judge | 1.0 → 1.0 | A different query no longer retrieves ZEN-POL-005 §10, so the answer drops two items from that policy. | Closer to the gold answer, which is ZEN-POL-004's list. Not a regression. |
| Q220 (AI tools and confidential data) | judge | 1.0 → 1.0 | Adds the passage's "no screenshots or personal notes about customers". | Rewording, still correct. |
| Q243 (POSH officer and her manager, 3-hop) | judge | 0.5 → 0.5 | "I can't find that in Waypoint's sources regarding who she reports to" instead of "The provided sources do not state …". | Same content. No refusal text. |

**Keep rule: met.** Overall is 0.99, which is at least 0.943; no row lost score; all changed rows were inspected.

**Tokens and latency**
- Tokens per question rose from 6,262 to 7,588 (+21%). The router prompt is longer: the `EMPLOYMENT_STATUS` op and six few-shots.
- Latency is not comparable with 3.3a. The 3.3a run used cached routes, whose latency is not counted, while this run routed every question fresh.

## Few-shot overlap with the safety set

`tests/test_router_examples_v3.py` normalises questions first: lower case, tokens, and every employee name and id replaced by `<person>`. Then:
- every few-shot must have token Jaccard ≤ 0.5 against every safety row;
- the six new 3.3c few-shots must also share no 4-gram with any safety row;
- the people in the new few-shots must not appear in the safety set;
- every person or department a few-shot names must exist in the graph.

The check caught one draft example ("… Nikhil Joshi's employment record …", which shared a 4-gram with S12), and that example was reworded.

Two few-shots from 2.4 overlap with public **controls** (not attacks). Both pass Jaccard ≤ 0.5, and both were left unchanged, because editing them would change dev routing:
- "Who is my manager?" (synthetic) has Jaccard exactly 0.50 with S21 and S24 ("Who is X's manager?");
- dev few-shot Q087 ("Who heads the department that … manager belongs to?") shares the 4-gram "who heads the department" with S30. Its Jaccard is 0.42.
