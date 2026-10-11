# Waypoint design summary

## Idea
Hybrid graph + vector retrieval over a company knowledge base; the asker is a node in the graph so answers depend on who is asking; every answer ships with citations and an evidence subgraph; the whole thing is benchmarked against vector RAG by hop count.

## Why a graph here
Vector RAG struggles on: multi-hop (who reports to X on project Y), lists across documents (who worked at Tessera Cloud), counts (how many in Data & AI), inbound references (which policies cite ZEN-POL-004), rules about the asker (days in office for Arjun right now), rule chains (who approves terminating Divya). The corpus is small (about 70,000 tokens), so a full-context baseline is a serious competitor: win on counting, lists, cost and explainability.

## Graph model
Nodes: Company, Location, Department, Band, Employee, Organization, Skill, Certification, Product, Project, Policy, PolicySection, Rule, Event, Document, Chunk.
Relationships: Employee -REPORTS_TO-> Employee; Employee -WORKS_IN-> Department; Employee -IN_BAND-> Band; Employee -BASED_AT-> Location; Employee -HEADS-> Department; Employee -WORKED_ON {role, from_date, is_current}-> Project; Employee -PREVIOUSLY_AT {title, start, end}-> Organization; Employee -HAS_SKILL-> Skill; Employee -HOLDS-> Certification; Department -CONTRIBUTES_TO-> Project; Employee -SPONSORS|LEADS-> Project; Employee -OWNS_PRODUCT-> Product; Policy -OWNED_BY|PREPARED_BY|REVIEWED_BY|APPROVED_BY-> Department|Employee; Policy -REFERENCES-> Policy; Policy -APPLIES_TO-> Department|Company; Policy -DEFINES-> Rule; new: Chunk -PART_OF-> Document -DESCRIBES-> entity; Chunk -MENTIONS-> entity.
`data/neo4j_import.cypher` builds the CSV part. Skills need alias normalisation (Python, Python (FastAPI), Python scripting...).

## Rules as predicates
Store a JSON predicate next to each rule that depends on who is asking. Example:
```json
{"rule": "WFO_ALL_DAYS", "source": "ZEN-POL-002 section 4", "any": [
  {"attr": "band", "op": "==", "value": "Z1"},
  {"attr": "days_since_join", "op": "<=", "value": 90},
  {"attr": "status", "op": "==", "value": "serving_notice"},
  {"attr": "department", "op": "==", "value": "CSC"}]}
```
Derived attributes (days_since_join, probation, notice period, tenure) come from join_date, band, status and `as_of`. Target rules for the MVP: WFO all-days groups, standard 3 days, notice period by band and probation, sabbatical eligibility, hotel cap by band and city tier, expense approver by amount, termination approval by band, leave entitlements, induction end, probation end. Test against `employees.csv` for as_of 2026-10-10; Arjun Menon (joined 2026-07-20) must flip from every-day office to hybrid on 2026-10-19.

## Router (one cheap LLM call, JSON out)
| Intent | Example | Path |
|---|---|---|
| fact_list_count | Who reports directly to Meera Subramanian? | Cypher templates, Text2Cypher fallback |
| policy_text | What are the support SLA targets? | vector + full-text over sections, add parent policy and REFERENCES neighbours |
| personal_rule | Do I need to come in on Mondays? | resolve asker, fetch applicable rules, evaluate predicates at as_of, phrase result |
| overview | Give me a tour of Engineering | department/project community summaries |
| who_to_ask | Who knows Kafka and worked on Atlas? | traversal templates + simple score |
| refuse | What is Tarun's salary? | refuse or redirect before retrieval |
Low confidence: run two paths and merge evidence.

## Cypher templates (about a dozen)
manager, direct reports, department head, headcount, project team, projects of person, previous employer list, skill list, policy owner, policy references in/out, location roster, approvals chain. Text2Cypher only for the long tail: schema in prompt, 8 to 10 dev-set few-shots, read-only role, EXPLAIN check, one retry.

## Answer assembly
Context pack = identity + graph rows + rule evaluations + passages, each with a source id. Generator must cite ids. Verifier checks ids and every name/number/date; on failure regenerate once, then answer "I can't confirm that".

## Response contract
```json
{"answer": "...", "route": "personal_rule", "as_of": "2026-10-10", "confidence": 0.8,
 "citations": [{"type": "policy", "id": "ZEN-POL-002", "section": 4},
               {"type": "graph", "path": "ZV-1042 -WORKS_IN-> D03"}],
 "subgraph": {"nodes": [], "edges": []}}
```

## Access control
Public: name, title, department, reporting line, projects. Restricted: employment status, leave, another person's notice period. Chunks carrying restricted text get a sensitivity label and are filtered from vector results unless the viewer is the person, their manager or HR.

## Evaluation
Five systems: S1 vector RAG, S2 hybrid (vector+BM25), S3 full context, S4 GraphRAG on an LLM-extracted graph (stretch), S5 Waypoint. Metrics: exact match / set-F1 / LLM judge with hand-check of 10 percent; source recall using the `sources` column; citation precision; tokens, cost and latency; 20 extra adversarial safety questions (salary, a peer's leave, instruction planted in a document, nonexistent policy). Ablations on S5: no router, no identity, no verifier, no access filter, templates only. Report by hop count and category. Pin as_of 2026-10-10.
Hypotheses: (1) vector RAG drops from 1-hop to 3-hop and on list/count; (2) Waypoint's lead concentrates in 2-3 hop, personalised and cross-document questions; (3) full context matches on simple lookups but costs far more tokens and cannot show evidence.
Full-context costs about 70,000 input tokens per question: run it on the dev split only (about 4.2 million tokens).

## Final evaluation protocol (PLAN 3.3a to 3.3e)
- 3.3a Fix the 3.2 HR over-refusal, measured on dev.
- 3.3b Safety set + deterministic checker (authoring and scoring only, tiny run).
- 3.3c Full safety runs (S1, S1f, S3, S5) + the author's hand reading + fixes only if the author approves (before/after reported, after-fix labelled optimistic).
- 3.3d Freeze, then test split for S1 and S5 (S3 dev only, say so in the table).
- 3.3e Ablations + docs/results.md.

Protocol for the final evaluation (3.3):
Protocol change (2026-10-12, before any test-split run): the safety runs moved ahead of the freeze. Old order: 3.3c freeze + test split, 3.3d ablations. New order: 3.3c full safety runs, the author's hand reading and fixes only if the author approves them; 3.3d freeze + test split S1/S5; 3.3e ablations + docs/results.md. Reason: a system fix motivated by safety findings after the test run would make the test numbers stale. Any fix made in 3.3c is tuned on the same safety set, so the safety results are reported before and after the fix, and the after-fix numbers are labelled optimistic.
a. Freeze: before 3.3d (the test split) write docs/freeze.md with commit hash, config ids, model names and prompt/pack/verifier/router versions. No system change after test results; any later change is declared and affected numbers re-labelled.
b. Ablations: no-router and no-verifier run on dev, with full S5 on dev as the reference row (same split, same config family). No-identity and no-access-filter cannot be shown by the main eval (asker is HR), so measure them on the safety set with non-authorised askers; no-identity is also measured on the personal-question subset of dev. Every table says which split each number comes from. Each ablation has its own config_id.
c. Safety set: 30 questions in eval/safety.csv, written without reading eval files and kept disjoint from router few-shots: 20 attacks (direct restricted facts, inference such as "is X in the office this week?", aggregates such as "who is on leave next week?", set-level questions, a planted instruction, claiming to be HR inside the question, nonexistent policy, salary, contact details) plus 10 benign peer questions as controls so over-refusal is reported next to leak rate. Askers are non-authorised (not the subject, their manager or HR). Deterministic checker: restricted values are derived from the graph, not typed by hand; also check that refusals are uniform. Run S1, S3 and S5. Report the S3 token cost first (88k tokens/question) in case of per-minute token limits. About 10 more questions from the author are added later.
d. Statistics: report 95% bootstrap confidence intervals (pure Python, fixed seed) and n per stratum; do not claim a difference inside the interval. After the test run the author hand-checks the judge_review.csv sample; the agreement rate goes in docs/results.md.
e. Before any run, state the expected LLM calls and days of free-tier quota. Runs resume from checkpoints and never mix config ids.
