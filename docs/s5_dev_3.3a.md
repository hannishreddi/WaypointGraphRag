# S5 on dev after 3.3a (neutral passage ids, pack-v4)

Run `eval_runs/20261012-003243_s5_dev`, config `answer-v2:router-v2:pack-v4:verify-v2:gemini-3.1-flash-lite:gemini-3.5-flash-lite`, made on top of commit 5cdc302 with the uncommitted 3.3a change (`git_dirty: true`; the change is the 3.3a commit). Reference: the 2.6 run `eval_runs/20261011-204733_s5_dev` (pack-v3, [s5_dev_2.6.md](s5_dev_2.6.md), unchanged).

Models: router `gemini-3.5-flash-lite` (served from `.cache/router/`, 0 router calls), generator `gemini-3.1-flash-lite`, judge `gemini-3.5-flash-lite`. As of 2026-10-10, asker ZV-1006 (HR) except Q209/Q210. 67 Gemini API calls (60 answers, judge calls only for answers whose text changed; the rest came from `.cache/judge/`).

## The change

The 3.2 demo found HR over-refusal. HR asked "What does Pooja Agarwal's profile say about leave?". The access filter correctly put her restricted profile chunks into HR's pack, but the generator answered with the restricted-rule refusal. The likely cue was the chunk ids, which end in `::restricted` and were shown to the model as item ids. pack-v4 gives passages neutral ids (`passage1`, `passage2`, … in pack order). The chunk id stays in `PackItem.source`, in the contract citations and in the eval trace (`passages`). The generator prompt is unchanged (answer-v2). Its "rule item with status: restricted → refuse" line is still needed for the rule engine's refusal to non-authorised askers.

## Dev cannot exercise the fix

**0 of 60 dev packs contained a restricted passage.** Only 10 dev rows retrieve passages at all, and none of them retrieves a `::restricted` chunk. Dev therefore only shows that the change costs nothing. The safety evidence is the regression tests:
- `tests/test_pack_passage_ids.py`:
  - Neutral ids in pack order, with citations still pointing at the real chunk and policy section.
  - The rendered prompt contains neither "restricted" nor `::`.
  - HR on the Pooja text path receives the leave text under `passage1`, passes the verifier and cites the real chunk.
  - A peer on the same path receives no restricted passage and no leave text.
  - A peer on the rule path still gets `status: restricted`.
- `tests/test_demo.py`: the four demo moments through the API.

## Scoreboard (dev, n = 60; 2.6 → 3.3a)

| group | n | 2.6 (pack-v3) | 3.3a (pack-v4) |
|---|---:|---:|---:|
| all | 60 | 0.96 | 0.96 |
| 1-hop | 27 | 1.00 | 1.00 |
| 2-hop | 22 | 0.93 | 0.93 |
| 3-hop | 11 | 0.95 | 0.95 |
| cross_document | 3 | 0.83 | 0.83 |
| employee_lookup | 4 | 0.75 | 0.75 |
| org_structure | 20 | 1.00 | 1.00 |
| personalised | 8 | 1.00 | 1.00 |
| policy | 7 | 1.00 | 1.00 |
| project | 9 | 1.00 | 1.00 |
| skills_experience | 9 | 0.93 | 0.93 |

Source recall 0.96 and citation precision 0.95 overall, 6,262 tokens/question (2.6: 6,276). Verifier: pass 60/60. Dev numbers stay optimistic (router and 2.6 fixes were developed on dev); claims need the test split (3.3c).

## Keep/revert decision

Rule, fixed before the run: keep pack-v4 if dev overall is at most one question (about 0.017) below 0.96, and revert only for a real regression (a row that was correct and is now wrong), not for judge-wording noise. Every changed row was inspected against the 2.6 run.

**Kept.** Overall and every stratum are identical. 6 rows changed wording. All are judge-scored passage answers, verdict correct → correct, so there is no regression:

| id | category | what changed |
|---|---|---|
| Q207 | personalised | same dates, list format instead of a sentence |
| Q214 | policy | same entitlement, reworded support sentence |
| Q218 | policy | same offence list, reworded |
| Q232 | policy | same SEV1–SEV4 times; now also lists the P0–P3 release-defect levels from ZEN-DPL-QAT-01 (correct, but beyond the question) |
| Q235 | policy | same SLA targets; drops "effective 2025-08-01" |
| Q247 | cross_document | same "No" and reason; drops the closing policy names from the text (the citations still carry them) |

Q232 is the only answer that got longer. It is still correct, and it is the kind of verbosity the judge does not penalise. It is not counted as a regression.

## Demo (live, after the change)

`python -m waypoint.api.demo`: 22/22 checks pass (3.2: 21/22).
- HR on the text path now answers: "Pooja Agarwal is on maternity leave from 1 Sep 2026 to 28 Feb 2027. This leave is governed by ZEN-POL-003, and her current work mode is listed as on leave."
- The peer's text-path answer changed too. With pack-v3 it was "I can't find that in Waypoint's sources."; with pack-v4 it is "Pooja Agarwal is subject to the Leave Policy (ZEN-POL-003).", citing only her public "policies that apply to this role" chunk. That is not a leak: no status, no restricted chunk, no leave section. ZEN-POL-003 is listed on every profile. The 3.2 check for this row demanded a refusal, which is stricter than rule 6, so it is now "states no leave status". The rule-path check still requires the refusal.
- So pack-v3 probably also cued the peer's not-found answer through its visible chunk ids.
