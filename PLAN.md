# Waypoint: 3-day solo plan

Realistic only with this scope. Cut line if you fall behind: drop S2 (hybrid) and the extraction stretch first, keep the evaluation always.

## Before you start (about 30 minutes, one time)
- [x] Create the repo folder, `git init`, unzip the dataset so it lands at `data/zenvora_kb/`, copy `CLAUDE.md`, `PLAN.md` and `docs/DESIGN.md` into the repo.
- [x] Neo4j: Docker if you have it, otherwise a free Neo4j Aura instance. Note the URI, user and password. (Docker, `neo4j:5.26-community` via `make up`.)
- [x] Put `ANTHROPIC_API_KEY`, `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `MODEL_FAST`, `MODEL_ANSWER`, `COHERE_API_KEY` in `.env` (not committed). Optional, with defaults: `COHERE_EMBED_MODEL`, `EMBED_DIM`.
- [x] Open Claude Code in the repo folder and send **Prompt 0**.

**How to work with Claude Code (every slice)**
1. Ask for a short plan first. Approve or trim it.
2. Let it write the test or eval check first, then the code, then run it.
3. Read the diff and the numbers yourself. Ask it to explain anything you could not defend in a viva.
4. Commit. Tick the box here. Start the next slice in a fresh session so context stays small; CLAUDE.md and this file carry the state.
5. When an eval run shows failures, paste the worst category into the session and ask for a root-cause grouping before any fix.

## Day 1: foundations and the baseline scoreboard
Gate: a scoreboard with S1 and S3 numbers on the dev split.

- [x] **1.1 Skeleton.** **Prompt 0:** "Read CLAUDE.md, docs/DESIGN.md and PLAN.md. Set up the repo skeleton: pyproject, Makefile with the targets in CLAUDE.md, .env.example, docker-compose for Neo4j, package `waypoint` with `graph/ retrieval/ rules/ llm/ eval/ api/`, and `tests/`. Do not implement features. Show me the tree and what you would do first."
- [x] **1.2 Graph load.** "Load the CSVs in data/zenvora_kb/data/csv into Neo4j using the model in DESIGN.md (use neo4j_import.cypher as a reference, but write a Python loader so it is idempotent). Add tests: node counts per label (about 391 nodes in total), every employee except the CEO has one REPORTS_TO, every department has a head, ten sanity Cypher queries with expected rows."
- [x] **1.3 Chunks and indexes.** "Chunk policies by numbered section (policy id, title, version, effective date prepended), profiles by heading, resumes by job, department and project pages whole. Convert policy tables to one sentence per row. Embed with the Cohere API (batched, `search_document`), store Chunk nodes linked with PART_OF and MENTIONS, create a vector index and a full-text index. Expose `search_text(query, k)`. Add sensitivity labels: any chunk containing employment status or leave text is `restricted`."
- [ ] **1.4 Eval harness.** "Create eval/split.json once (60 dev, 191 test, stratified by category and hops, seed 42). Write scorers: exact match, set-F1 for semicolon-separated lists, LLM judge for sentences. Define a `System` interface `answer(question, asker_id, as_of) -> Response`. Runner writes per-question results to CSV and a markdown summary by hop count and category. Never read the test split except in `make eval-test`."
- [ ] **1.5 Baselines.** "Implement S1 vector RAG (top 5 chunks, one LLM call) and S3 full context (all Markdown files in the prompt, dev split only). Run `make eval-dev` and show me the scoreboard."

## Day 2: the core (router, templates, rules, verifier)
Gate: S5 beats S1 on 1-hop and 2-hop dev questions, and the rule tests pass.

- [ ] **2.1 Entity linking.** "Build an alias table from employees, departments, projects, policies (full names, first names when unique, titles, IDs, short codes like ZEN-POL-004). Add `link_entities(text)` and tests."
  - Note: Skill nodes are loaded exactly as in skills.csv (1.2). Skill alias normalisation (Python / Python (FastAPI) / Python scripting) is handled here.
- [ ] **2.2 Cypher templates.** "Implement the templates listed in DESIGN.md as parameterised functions returning rows plus the nodes and edges used (for the subgraph). One test per template against known answers from eval/questions.csv dev questions only."
- [ ] **2.3 Rule engine.** "Implement predicates and the evaluator from DESIGN.md with derived attributes computed from `as_of`. Write predicates for the MVP rules. Tests: for every employee, computed work mode, notice period and tenure must match employees.csv at 2026-10-10; Arjun Menon must change at 2026-10-19; Pooja Agarwal must show on leave; Tarun Mehta full office."
- [ ] **2.4 Router.** "Implement the router as one LLM call returning a Pydantic-validated JSON (intent, entities, needs_identity, confidence). On low confidence run two paths and merge. Evaluate routing accuracy on dev questions first."
- [ ] **2.5 Answering.** "Context pack, generator with id citations, verifier, response contract exactly as in DESIGN.md, access-control filter in the retrieval layer. Implement S5 as a `System`. Run `make eval-dev`, then group failures by category and show me root causes before fixing."
- [ ] **2.6 Fix loop.** Repeat 2.5 failure analysis until 1- and 2-hop beat S1. Text2Cypher fallback only if templates leave a clear gap.

## Day 3: product, proof, write-up
Gate: demo runs end to end; final test-split numbers and ablations are in the README.

- [ ] **3.1 API and UI.** "FastAPI `POST /ask` {question, asker_id, as_of} returning the response contract; `GET /employees` for the picker. One static page: chat, identity dropdown, as-of date picker, answer with citations, and the evidence subgraph in Cytoscape.js (CDN)."
- [ ] **3.2 Demo moments.** Set as-of to 2026-10-19 and ask Arjun's office question again (answer must flip). A peer asks about someone's leave (must refuse). "Who reports to Meera?", "Who approves terminating Divya?" show the subgraph.
- [ ] **3.3 Final numbers.** `make eval-test` for S1, S3 (dev only is fine, say so), S5. Ablations on S5: no router, no identity, no verifier, no access filter. 20 safety questions you write yourself.
- [ ] **3.4 README.** Problem, design, architecture diagram, scoreboard by hop count, ablation table, limitations (small synthetic corpus, full-context baseline), how to run.
- [ ] **3.5 Stretch if time remains (pick one):** (a) extraction slice: LLM extracts REFERENCES edges and rule predicates from the policy Markdown, scored against `policy_references.csv` and `policy_rules.csv`; (b) who-should-I-ask finder; (c) onboarding checklist from `onboarding_tasks.csv`.

## Later (do not touch before the gate)
Event nodes from timeline_events.csv, hybrid reranker, community summaries, full document-to-graph extraction for all entities, Slack bot, multilingual answers, policy contradiction auditor.
