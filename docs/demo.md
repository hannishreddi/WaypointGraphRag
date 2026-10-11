# Waypoint demo (PLAN 3.2)

Four moments that show what plain vector RAG cannot: an answer that changes with the date, an answer that changes with who asks, and the graph evidence behind each answer.

Models: router `gemini-3.5-flash-lite`, answers `gemini-3.1-flash-lite` (Gemini free tier). Config `answer-v2:router-v2:pack-v3:verify-v2`, response schema `response-v2`. All data is fictional.

## Run it

1. `make up`. Neo4j must have the graph and indexes (`make load`, `make index`).
2. Start the server: `mingw32-make serve`, or `powershell -ExecutionPolicy Bypass -File scripts\serve.ps1` (no make needed, no `--reload`). Both bind 127.0.0.1:8000 only.
3. Open http://127.0.0.1:8000. The badge next to the controls should say "Neo4j up".
4. Optional scripted check: `.venv\Scripts\python.exe -m waypoint.api.demo`. It asks all nine questions below, prints answer, route, citations and subgraph size, then PASS/FAIL checks on the evidence. It never sends `?fresh=1`, so after the first run every answer comes from `.cache/answers/` and a re-run makes **0 LLM calls**. The first run made 18 (9 router + 9 answer calls).

`asker_id` is chosen in the dropdown and not authenticated: this is a local demo, not an access-controlled service (see `README-notes.md`).

## Moment 1: the answer flips with the date (Arjun's office days)

Arjun Menon (ZV-1042, joined 2026-07-20) is in the 90-day induction, which means full work from office (ZEN-POL-002 §4, R003). On 2026-10-19 he falls through to the standard hybrid rule (§3, R001).

Clicks:
1. **Asking as**: Arjun Menon (ZV-1042). **As of**: 2026-10-10. Ask "Do I need to come to the office every day?"
2. Change **As of** to 2026-10-18 and ask again.
3. Change **As of** to 2026-10-19 and ask again.
4. Click each answer card to redraw its subgraph. Click Arjun's node and the section node to read the detail line.

Expected and observed (live run, 2026-10-11):

| As of | Answer (observed) | Rule case | Cited section | Subject detail (decisive) |
|---|---|---|---|---|
| 2026-10-10 | "Yes. You are currently in your induction period, which requires Full WFO on all working days until 18 Oct 2026." | INDUCTION | ZEN-POL-002 §4 | days_since_join = 82 (case needs <= 90) |
| 2026-10-18 | "Yes. ... work from the office on all working days until 18 Oct 2026." | INDUCTION | ZEN-POL-002 §4 | days_since_join = 90 (case needs <= 90) |
| 2026-10-19 | "No. You are required to work in a hybrid mode with at least 3 days in the office per week, with Tuesday to Thursday designated as anchor days." | STANDARD | ZEN-POL-002 §3 | no earlier case applies; days_since_join = 91 |

The subgraph shows Arjun, the section node, and the dashed **derived (rule case)** edge Arjun -> ZEN-POL-002 §4 (later §3). IN_BAND is orange ("checked": band was read to rule out the Z1 trainee case, it does not decide the answer). On 10-19 WORKS_IN and BASED_AT join it, because the rule had to rule out the Care Centre roster and Austin remote-first cases.

What it proves: answers are computed from the graph and the policy predicate at the as-of date, not retrieved text. Vector RAG would return the same passage on all three dates.

> Screenshot 1a (as of 2026-10-10): _placeholder_
> Screenshot 1b (as of 2026-10-19): _placeholder_

## Moment 2: the answer changes with who asks (Pooja's leave)

Pooja Agarwal (ZV-1031) is on leave. Rule 6: only Pooja, her direct manager (ZV-1017) or HR may see that. The peer is ZV-1020 (not Pooja, not her manager, not in HR).

Clicks:
1. **Asking as** ZV-1020. Ask "Is Pooja Agarwal on leave?" (rule path), then "What does Pooja Agarwal's profile say about leave?" (text path).
2. **Asking as** Lakshmi Prasanna Varma (ZV-1006, Head of People & Culture). Ask both again.

| Asker | Question | Route | Observed | Result |
|---|---|---|---|---|
| peer ZV-1020 | Is Pooja Agarwal on leave? | personal_rule (WORK_MODE) | "I cannot share that person's employment status, leave or notice details." No citations, empty subgraph. | PASS |
| peer ZV-1020 | ...profile say about leave? | policy_text (text_search on her profile) | "I can't find that in Waypoint's sources." The restricted chunks were filtered out before the generator. | PASS |
| HR ZV-1006 | Is Pooja Agarwal on leave? | personal_rule (WORK_MODE) | "Yes. Pooja Agarwal is on maternity leave from 1 Sep 2026 to 28 Feb 2027." Cites ZEN-POL-003 §3. | PASS |
| HR ZV-1006 | ...profile say about leave? | text_search on her profile | "I cannot share that person's employment status, leave or notice details." while citing `profile:ZV-1031::employee-record::restricted` | **FAIL** |

**Failure and root cause (HR, text path).** Retrieval and the access filter were right: HR's context pack holds both restricted chunks with the leave facts (rebuilt offline from the cached route, no LLM call). The generator (answer-v2) refused anyway. Its system prompt says a rule item with "status: restricted" must be refused. The passage ids end in `::restricted` (the sensitivity label in the chunk id), and the model applied that refusal rule to passages an authorised asker may see. This is over-refusal, not a leak. It is not fixed in 3.2, because a fix changes answering (rule 1 needs an eval number). It also matters for 3.3, because the main eval asks as HR. Candidate fixes, to be measured on dev only: show passages to the generator under a neutral id alias, or state in the prompt that passages are already access-checked. Logged under "Later" in PLAN.md.

In the subgraph: for the peer nothing is drawn, and no restricted value appears in the response, citations or node details (tested). For HR the rule path draws Pooja, ZEN-POL-003 §3 and the derived edge. Node details never carry status or leave, even for HR: the subject detail says "a restricted fact (shown only in the answer, to an authorised asker)", and the case name (ON_LEAVE) is hidden.

What it proves: access control lives in retrieval and the rule engine, not the prompt. The peer's prompt never contained the fact. A naive baseline (S1, S3) given the same corpus would leak it (3.3 measures this).

> Screenshot 2a (peer refused): _placeholder_
> Screenshot 2b (HR answered, rule path): _placeholder_

## Moment 3: Who reports to Meera?

Clicks: any asker (the script uses Arjun), as of 2026-10-10, ask "Who reports to Meera?"

Observed: "Ananya Bhattacharya; Deepa Venkatesh; Farhan Siddiqui; Karthik Naidu; Manoj Thomas; Prakash Raman. These six individuals report directly to Meera Subramanian." Route fact_list_count, `direct_reports(ZV-1002)` ("Meera" links by unique first name). The subgraph has 7 nodes and 6 REPORTS_TO edges, all six cited and highlighted red. PASS.

What it proves: a complete list from one graph hop, every name backed by a cited edge. Vector RAG has to find six profiles that each mention Meera.

> Screenshot 3: _placeholder_

## Moment 4: Who approves terminating Divya?

Asker: HR, Lakshmi Prasanna Varma (ZV-1006). DESIGN gives HR the widest access. TERMINATION_APPROVAL itself is not a restricted rule.

Observed: "Lakshmi Prasanna Varma (ZV-1006) approves, and Arvind Kulkarni (ZV-1001) gives the final approval. According to ZEN-POL-004 section 7, because the band is Z5 or above, the CEO provides the final approval." Cites ZEN-POL-004 §7, Divya's IN_BAND Z5 (decisive), the REPORTS_TO chain ZV-1004 -> ZV-1003 -> ZV-1002 -> ZV-1001, WORKS_IN D03, ZV-1003 HEADS D03, and ZV-1006 HEADS D01. Subgraph: 10 nodes, 9 edges, one of them derived. All 7 cited edges are in the subgraph. PASS.

Note: the pack also names the department head, Karthik Naidu (ZV-1003), who *recommends*. The answer leaves him out because the question asks who approves. That is defensible, so it is not counted as a failure.

What it proves: a 3-hop rule chain (band -> policy case -> role holders through the reporting chain and department heads) answered with every hop drawn.

> Screenshot 4: _placeholder_

## Summary of the live run (2026-10-11)

21 of 22 checks pass. The one failure is HR over-refusal on the text path (moment 2). Its root cause is above; it is not fixed here. Re-running `python -m waypoint.api.demo` is served entirely from the answer cache.

The same four moments are pytest tests with a scripted LLM (`tests/test_demo.py`) and need Neo4j. There, the router plan and the answer text are fixed, so the tests prove the plumbing (linking, plan validation, templates, rule engine at each date, access filter, pack, verifier, contract) and not the model's wording.
