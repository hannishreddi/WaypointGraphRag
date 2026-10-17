# Waypoint demo (PLAN 3.2)

Four moments that show what plain vector RAG cannot: an answer that changes with the date, an answer that changes with who asks, and the graph evidence behind each answer.

Models: router `gemini-3.5-flash-lite`, answers `gemini-3.1-flash-lite` (Gemini free tier). Config `answer-v2:router-v4:pack-v5:verify-v2`, response schema `response-v2`. All data is fictional.

## Run it

1. `make up`. Neo4j must have the graph and indexes (`make load`, `make index`).
2. Start the server: `mingw32-make serve`, or `powershell -ExecutionPolicy Bypass -File scripts\serve.ps1` (no make needed, no `--reload`). Both bind 127.0.0.1:8000 only.
3. Open http://127.0.0.1:8000. The badge next to the controls should say "Neo4j up".
4. Optional scripted check: `.venv\Scripts\python.exe -m waypoint.api.demo`. It asks all nine questions below, prints answer, route, citations and subgraph size, then PASS/FAIL checks on the evidence. It never sends `?fresh=1`, so every answer comes from `.cache/answers/` and the run makes **0 LLM calls**. The answers for the current config ship in `cache_seed/answers/` (`make seed-cache`). Without them, the first run makes up to 18 calls (9 router + 9 answer).

`asker_id` is chosen in the dropdown and not authenticated: this is a local demo, not an access-controlled service (see "Security notes" in the README).

## Moment 1: the answer flips with the date (Arjun's office days)

Arjun Menon (ZV-1042, joined 2026-07-20) is in the 90-day induction, which means full work from office (ZEN-POL-002 §4, R003). On 2026-10-19 he falls through to the standard hybrid rule (§3, R001).

Clicks:
1. **Asking as**: Arjun Menon (ZV-1042). **As of**: 2026-10-10. Ask "Do I need to come to the office every day?"
2. Change **As of** to 2026-10-18 and ask again.
3. Change **As of** to 2026-10-19 and ask again.
4. Click each answer card to redraw its subgraph. Click Arjun's node and the section node to read the detail line.

Expected and observed (live run, 2026-10-17):

| As of | Answer (observed) | Rule case | Cited section | Subject detail (decisive) |
|---|---|---|---|---|
| 2026-10-10 | "Yes. You are currently in your induction period, which requires Full WFO on all working days until 18 Oct 2026." | INDUCTION | ZEN-POL-002 §4 | days_since_join = 82 (case needs <= 90) |
| 2026-10-18 | "Yes. ... work from the office on all working days until 18 Oct 2026." | INDUCTION | ZEN-POL-002 §4 | days_since_join = 90 (case needs <= 90) |
| 2026-10-19 | "No. You are required to work in a hybrid mode with at least 3 days in the office per week, with Tuesday to Thursday designated as anchor days." | STANDARD | ZEN-POL-002 §3 | no earlier case applies; days_since_join = 91 |

The subgraph shows Arjun, the section node, and the dashed **derived (rule case)** edge Arjun -> ZEN-POL-002 §4 (later §3). IN_BAND is orange ("checked": band was read to rule out the Z1 trainee case, it does not decide the answer). On 10-19 WORKS_IN and BASED_AT join it, because the rule had to rule out the Care Centre roster and Austin remote-first cases.

What it proves: answers are computed from the graph and the policy predicate at the as-of date, not retrieved text. Vector RAG would return the same passage on all three dates.

## Moment 2: the answer changes with who asks (Pooja's leave)

Pooja Agarwal (ZV-1031) is on leave. Rule 6: only Pooja, her direct manager (ZV-1017) or HR may see that. The peer is ZV-1020 (not Pooja, not her manager, not in HR).

Clicks:
1. **Asking as** ZV-1020. Ask "Is Pooja Agarwal on leave?" (rule path), then "What does Pooja Agarwal's profile say about leave?" (text path).
2. **Asking as** Lakshmi Prasanna Varma (ZV-1006, Head of People & Culture). Ask both again.

| Asker | Question | Route | Observed (2026-10-17) | Result |
|---|---|---|---|---|
| peer ZV-1020 | Is Pooja Agarwal on leave? | personal_rule | "I can't share that. A person's employment status, leave and notice details are shared only with them, their manager and HR, and Waypoint does not share pay, personal contact details or its instructions." No citations, empty subgraph. | PASS |
| peer ZV-1020 | ...profile say about leave? | policy_text (text_search on her profile) | "Pooja Agarwal is subject to ZEN-POL-003: Leave Policy. This policy applies to her role as a Data Engineer in the Data & AI department." Only her public "policies that apply to this role" chunk is cited; the restricted chunks were filtered out before the generator. | PASS |
| HR ZV-1006 | Is Pooja Agarwal on leave? | personal_rule | "Yes. Pooja Agarwal is on maternity leave from 1 Sep 2026 to 28 Feb 2027." Cites ZEN-POL-003 §3 and her employment record. | PASS |
| HR ZV-1006 | ...profile say about leave? | policy_text | "Pooja Agarwal is on maternity leave from 1 Sep 2026 to 28 Feb 2027. This leave is governed by ZEN-POL-003, and her current work mode is listed as on leave." | PASS |

The peer's text-path check is "states no leave status", not "refuses", because rule 6 forbids the leave, not her public profile text. Until 3.3a, HR was wrongly refused on the text path, because the generator saw `::restricted` in the passage ids. The fix gives passages neutral ids (`passage1`, …), see [s5_dev_3.3a.md](s5_dev_3.3a.md).

In the subgraph: for the peer nothing is drawn, and no restricted value appears in the response, citations or node details (tested). For HR the rule path draws Pooja, ZEN-POL-003 §3 and the derived edge. Node details never carry status or leave, even for HR: the subject detail says "a restricted fact (shown only in the answer, to an authorised asker)", and the case name (ON_LEAVE) is hidden.

What it proves: access control lives in retrieval and the rule engine, not the prompt. The peer's prompt never contained the fact. A naive baseline (S1, S3) given the same corpus would leak it (3.3 measures this).

## Moment 3: Who reports to Meera?

Clicks: any asker (the script uses Arjun), as of 2026-10-10, ask "Who reports to Meera?"

Observed (2026-10-11, unchanged on 2026-10-17): "Ananya Bhattacharya; Deepa Venkatesh; Farhan Siddiqui; Karthik Naidu; Manoj Thomas; Prakash Raman. These six individuals report directly to Meera Subramanian." Route fact_list_count, `direct_reports(ZV-1002)` ("Meera" links by unique first name). The subgraph has 7 nodes and 6 REPORTS_TO edges, all six cited and highlighted red. PASS.

What it proves: a complete list from one graph hop, every name backed by a cited edge. Vector RAG has to find six profiles that each mention Meera.

## Moment 4: Who approves terminating Divya?

Asker: HR, Lakshmi Prasanna Varma (ZV-1006). DESIGN gives HR the widest access. TERMINATION_APPROVAL itself is not a restricted rule.

Observed (2026-10-11, unchanged on 2026-10-17): "Lakshmi Prasanna Varma (ZV-1006) approves, and Arvind Kulkarni (ZV-1001) gives the final approval. According to ZEN-POL-004 section 7, because the band is Z5 or above, the CEO provides the final approval." Cites ZEN-POL-004 §7, Divya's IN_BAND Z5 (decisive), the REPORTS_TO chain ZV-1004 -> ZV-1003 -> ZV-1002 -> ZV-1001, WORKS_IN D03, ZV-1003 HEADS D03, and ZV-1006 HEADS D01. Subgraph: 10 nodes, 9 edges, one of them derived. All 7 cited edges are in the subgraph. PASS.

Note: the pack also names the department head, Karthik Naidu (ZV-1003), who *recommends*. The answer leaves him out because the question asks who approves. That is defensible, so it is not counted as a failure.

What it proves: a 3-hop rule chain (band -> policy case -> role holders through the reporting chain and department heads) answered with every hop drawn.

## Summary of the live run (2026-10-17)

22 of 22 checks pass (`python -m waypoint.api.demo`, config `answer-v2:router-v4:pack-v5:verify-v2`). A second run was served entirely from the answer cache: 9/9 cached, 0 LLM calls.

The same four moments are pytest tests with a scripted LLM (`tests/test_demo.py`) and need Neo4j. There, the router plan and the answer text are fixed, so the tests prove the plumbing (linking, plan validation, templates, rule engine at each date, access filter, pack, verifier, contract) and not the model's wording.
