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
Planned systems: S1 vector RAG, S2 hybrid (vector+BM25), S3 full context, S4 GraphRAG on an LLM-extracted graph (stretch), S5 Waypoint. Metrics: exact match / set-F1 / LLM judge with a hand-checked sample; source recall using the `sources` column; citation precision; tokens and latency. A 10-question safety sanity check asks restricted questions as non-authorised askers (`docs/safety.md`). Report by hop count and category. Pin as_of 2026-10-10. Built: S1, S3 (dev only) and S5; S2 and S4 were cut. Results: `docs/results.md`.
Hypotheses: (1) vector RAG drops from 1-hop to 3-hop and on list/count; (2) Waypoint's lead concentrates in 2-3 hop, personalised and cross-document questions; (3) full context matches on simple lookups but costs far more tokens and cannot show evidence.
Full-context costs about 70,000 input tokens per question: run it on the dev split only (about 4.2 million tokens).
