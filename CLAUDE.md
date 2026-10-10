# Waypoint: identity-aware Graph RAG onboarding assistant

Solo project, 3-day build. A chat assistant that answers a new joiner's questions about the fictional company Zenvora (org, departments, projects, policies) as the person asking, with citations and an evidence subgraph. It is benchmarked against plain vector RAG on 251 questions.

Read `docs/DESIGN.md` for the design and `PLAN.md` for the build order. Work through PLAN.md one slice at a time and tick it off.

## Data (read-only, never edit)
- Unzipped at `data/zenvora_kb/`. Key paths: `data/csv/*.csv` (ground-truth graph tables), `data/neo4j_import.cypher`, `policies/`, `employees/`, `departments/`, `projects/`, `company/`, `eval/questions.csv`.
- **As-of date for every test and eval run: 2026-10-10.** Derived columns in `employees.csv` (`work_mode`, `tenure_years`, `notice_period_days`) are the answer key for that date. They are NOT graph facts. Compute them at query time from join_date, band, status and the as-of date.
- Everything in the dataset is fictional.

## Stack (decided, do not re-litigate)
- Python 3.11+, FastAPI, Pydantic v2, pytest. Plain Python for the pipeline: no LangChain, LlamaIndex or similar.
- Neo4j 5.26 Community (`neo4j:5.26-community` in docker-compose.yml, container `waypoint-neo4j`) for graph, vector index and full-text index in one database. Env: `NEO4J_URI` (bolt://localhost:7687), `NEO4J_USERNAME` (must be `neo4j`), `NEO4J_PASSWORD`.
- Embeddings: Cohere embed API via the `cohere` SDK (`ClientV2.embed`). Model `COHERE_EMBED_MODEL` (default `embed-v5.0-fast`), dimension `EMBED_DIM` (default 1024; v5 supports 256/512/768/1024/1536/2048). `input_type` is `search_document` for chunks, `search_query` for queries. Key `COHERE_API_KEY` in `.env`.
- No local ML or native numeric libs: Windows Application Control blocks numpy. Never add numpy, pandas, scikit-learn or torch; use `csv`, `random`, `statistics` from the standard library.
- LLM: Anthropic API through the `anthropic` SDK. Model names come from env vars `MODEL_FAST` (router, judge) and `MODEL_ANSWER` (answers). Key `ANTHROPIC_API_KEY` in `.env`, never committed.
- Settings: `waypoint/config.py` (`get_settings()`), field names match the `.env` names; `.env.example` lists them all.
- UI: one static HTML/JS page served by FastAPI, Cytoscape.js from a CDN for the evidence subgraph. No Node toolchain.

## Rules
1. **Eval first.** Every feature lands with a number from `make eval-dev`. Never claim an improvement without one.
2. **No leakage.** `eval/split.json` (60 dev, 191 test, stratified by category and hops, seed 42) is created once. Prompts, few-shot examples and thresholds may only use dev questions. Run test only for final numbers.
3. **Cypher safety.** Parameterised queries only; never build Cypher by string-formatting user text. Deviation: Neo4j Community has no role-based access, so there is no read-only user. Instead answer queries run in read-access mode (`session.execute_read`, which Neo4j enforces: writes fail with `Neo.ClientError.Statement.AccessMode`) and must first pass `waypoint.graph.guard.check_read_only`, which rejects CREATE, MERGE, DELETE, DETACH, SET, REMOVE, DROP, LOAD CSV and CALL as whole words, case-insensitive, outside string literals and comments. Only the loader and indexer (`make load`, `make index`) write.
4. **Structured LLM output.** Ask for JSON, validate with Pydantic, retry once with the validation error, then fail loudly.
5. **Every answer cites ids** (policy section or graph path). A verifier checks that cited ids are in the context pack and that every name, number and date in the answer appears there.
6. **Restricted facts.** Employment status, leave and another person's notice period are returned only to the person themselves, their manager or HR. Enforce in the retrieval layer, not in the prompt.
7. **Small steps.** One slice per commit. Run `make test` before committing. Update the checklist in PLAN.md.
8. Type hints on public functions. Keep modules small: `graph/`, `retrieval/`, `rules/`, `llm/`, `eval/`, `api/`.

## Commands (keep this section current)
Windows: run every target with `mingw32-make`.
- `make install` deps into .venv · `make up` start Neo4j and wait until healthy (http://localhost:7474) · `make down` stop it
- `make load` build the graph from CSVs (1.2) · `make index` chunk, embed, create indexes (1.3)
- `make test` unit tests · `make eval-dev` · `make eval-test` · `make serve` run API and UI on http://localhost:8000
- Reset only this project's Neo4j data: `docker compose down -v` (volumes `mini_project_graph_rag_neo4j_*`). The unrelated `neo4j-local` container and its `neo4j_data`/`neo4j_logs` volumes are not ours; leave them alone.

## When unsure
Ask me one short question with a recommended default. Do not expand scope beyond PLAN.md; list ideas under "Later" in PLAN.md instead.

Status: slice 1.1 done, next 1.2
