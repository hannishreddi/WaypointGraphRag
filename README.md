# Waypoint: identity-aware Graph RAG onboarding assistant

Waypoint is a chat assistant for new joiners at **Zenvora**, a fictional company. It answers questions about people, departments, projects and policies **as the person asking**. For example, "Do I need to come to the office every day?" gets a different answer for a new joiner than for a senior engineer. Every answer comes with citations and a small evidence graph.

Under the hood:

- a **Neo4j** graph of the company (employees, reporting lines, departments, projects, policies);
- a **vector and full-text index** over the documents (Cohere embeddings, stored in Neo4j);
- a **router** (one LLM call) that picks Cypher templates, policy rules or a text search;
- a **rule engine** for "about me" questions (office days, notice period, expense approver, …);
- an **access filter**: leave, notice and employment status are shown only to the person, their manager or HR;
- a **generator plus verifier**: answers must cite their sources, and every name, number and date is checked.

Everything in the dataset is fictional. The system answers "as of" **2026-10-10** by default.

More detail: [docs/DESIGN.md](docs/DESIGN.md) (design), [PLAN.md](PLAN.md) (build log), [README-notes.md](README-notes.md) (security notes for the demo).

---

## 1. What you need

| Tool | Version | Notes |
|---|---|---|
| Git | any | to clone the repo |
| Python | **3.11 or newer** | `python --version` (Windows: `py --version`) |
| Docker Desktop | recent | runs Neo4j; it must be **running** before step 5 |
| make | optional | every step below also shows the plain command |
| Free RAM | about 2 GB | Neo4j is set to a 1 GB heap |

Two free API keys:

1. **Gemini** (the LLM): https://aistudio.google.com/apikey. The free tier is enough.
2. **Cohere** (embeddings): https://dashboard.cohere.com/api-keys. A trial key is enough.

Both providers only ever see the fictional dataset and your questions. Don't type real personal data into the app: Google may use free-tier content to improve its products.

---

## 2. Clone the repo

```bash
git clone https://github.com/hannishreddi/WaypointGraphRag.git
cd WaypointGraphRag
```

All later commands run from this folder.

---

## 3. Create a virtual environment and install

**Windows (PowerShell):**
```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

**macOS / Linux:**
```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev]"
```

You don't need to "activate" the venv: every command in this README calls the venv's Python directly. In the rest of this file, **`PY`** means `.venv\Scripts\python.exe` on Windows and `.venv/bin/python` on macOS/Linux.

---

## 4. Create your `.env` file

Copy the template:

```powershell
# Windows
Copy-Item .env.example .env
```
```bash
# macOS / Linux
cp .env.example .env
```

Open `.env` in an editor and fill in three values:

```ini
NEO4J_PASSWORD=pick-any-password-8-chars-or-more
GEMINI_API_KEY=<your Gemini key>
COHERE_API_KEY=<your Cohere key>
```

Leave everything else as it is. In particular:

- `NEO4J_USERNAME` must stay `neo4j`;
- keep the model names (`MODEL_FAST`, `MODEL_ANSWER`), so the shipped caches match (step 7).

`.env` is in `.gitignore`. **Never commit it.**

---

## 5. Start Neo4j (Docker)

Make sure Docker Desktop is running, then:

```bash
docker compose up -d --wait        # or: make up
```

This starts the container `waypoint-neo4j` and waits until it is healthy (about 30 to 60 s the first time, because it downloads the image). Docker reads the password from `.env`.

Check it in a browser: http://localhost:7474. Log in with `neo4j` and your `NEO4J_PASSWORD`.

> Ports 7474 and 7687 must be free. If you already run another Neo4j, stop it first.

---

## 6. Load the graph

```bash
PY -m waypoint.graph.load          # or: make load
```

This builds the company graph from `data/zenvora_kb/data/csv/*.csv` (391 nodes). It makes no API calls.

---

## 7. Copy the shipped caches (recommended)

The repo ships precomputed caches in `cache_seed/`:

- document embeddings;
- router decisions;
- eval judge verdicts;
- answers from the demo.

Copy them into `.cache/`, where the code looks for them:

```bash
PY -c "import shutil; shutil.copytree('cache_seed', '.cache', dirs_exist_ok=True)"     # or: make seed-cache
```

With the caches, building the index makes **0 Cohere calls**, and the demo in step 10 makes **0 Gemini calls**. Without them, everything still works, but the first runs use API quota.

---

## 8. Build the search index

```bash
PY -m waypoint.retrieval.index --dry-run    # optional: shows "planned API calls: 0" if step 7 worked
PY -m waypoint.retrieval.index              # or: make index
```

This splits the documents into 815 chunks, embeds them (from the cache) and creates the vector and full-text indexes in Neo4j.

---

## 9. Run the tests

```bash
PY -m pytest -q                    # or: make test
```

Expect something like `769 passed, 121 skipped` if Neo4j is down. With Neo4j up and loaded, most of the skipped tests run too. To run only the graph tests and fail if Neo4j is unreachable: `make test-graph`.

---

## 10. Start the app

```bash
PY -m uvicorn waypoint.api.app:app --host 127.0.0.1 --port 8000     # or: make serve
```

On Windows you can also run `powershell -ExecutionPolicy Bypass -File scripts\serve.ps1`.

Open **http://127.0.0.1:8000**. Then:

1. Pick **who you are** in the identity dropdown (default: Arjun Menon, ZV-1042, a new joiner).
2. Keep the **as-of date** at 2026-10-10, or change it to see date-dependent answers flip.
3. Ask a question. Click an answer to see its evidence graph; red edges are the cited paths.

Questions to try:

| Asking as | Question | What it shows |
|---|---|---|
| Arjun Menon (ZV-1042), as of 2026-10-10 | Do I need to come to the office every day? | personal rule: "yes" during induction |
| Arjun, as of **2026-10-19** | the same question | the answer flips to hybrid (3 days) |
| ZV-1020 (a colleague) | Is Pooja Agarwal on leave? | refused: restricted fact |
| Lakshmi (ZV-1006, HR) | Is Pooja Agarwal on leave? | answered: HR may see it |
| anyone | Who reports to Meera? | graph template plus evidence graph |
| Lakshmi (ZV-1006, HR) | Who approves terminating Divya? | approval rule chain |

**Scripted demo (optional, second terminal, server running):**
```bash
PY -m waypoint.api.demo
```
It runs the four demo moments and prints PASS/FAIL checks. With the seeded answer cache it makes no LLM calls. See [docs/demo.md](docs/demo.md).

> The identity dropdown is **not authentication**: anyone who can reach the server can claim to be anyone. That is why the server listens on 127.0.0.1 only. Don't expose it on a network.

Stop the server with `Ctrl+C`. Stop Neo4j with `docker compose down` (or `make down`). Your graph is kept in a Docker volume. To delete it as well: `docker compose down -v`.

---

## Command cheat sheet

| Step | make target | Plain command (`PY` = venv python) |
|---|---|---|
| install | `make install` | `PY -m pip install -e ".[dev]"` |
| start Neo4j | `make up` | `docker compose up -d --wait` |
| stop Neo4j | `make down` | `docker compose down` |
| load graph | `make load` | `PY -m waypoint.graph.load` |
| seed caches | `make seed-cache` | `PY -c "import shutil; shutil.copytree('cache_seed', '.cache', dirs_exist_ok=True)"` |
| build index | `make index` | `PY -m waypoint.retrieval.index` |
| tests | `make test` | `PY -m pytest -q` |
| run app | `make serve` | `PY -m uvicorn waypoint.api.app:app --host 127.0.0.1 --port 8000` |
| try a search | | `PY -m waypoint.retrieval.search "expense approval limits" -k 3` |

About `make` on Windows:

- run make from **PowerShell or cmd**, not Git Bash, because the Makefile uses Windows paths (`.venv\Scripts\python.exe`);
- with MinGW, the command is `mingw32-make` instead of `make`.

[CLAUDE.md](CLAUDE.md) ("Commands") lists every other command (evaluation, safety set, routing report, bootstrap CIs).

---

## Evaluation (optional, uses API quota)

The benchmark compares Waypoint (S5) with plain vector RAG (S1) and a full-context baseline (S3). It uses 251 questions, split into 60 **dev** and 191 **test** questions.

```bash
make eval-dev SYSTEM=s5            # or: PY -m waypoint.eval.run --split dev --system s5
make eval-dev SYSTEM=s1 LIMIT=10   # a quick 10-question run of the vector-RAG baseline
```

Output goes to `eval_runs/<timestamp>_<system>_dev/` (results.csv, summary.md). Past runs referenced in `docs/` are already committed in `eval_runs/`.

Please follow these rules when running the evaluation:

- **Don't run or open the test split.** It is held back for the final numbers. `make eval-test` refuses to run until the project is frozen (tag `freeze-1`).
- **Don't open the question files directly** (`data/zenvora_kb/eval/`, `eval/split.json`). To see dev questions, use `PY -m waypoint.eval.show_dev`.
- **Mind the free-tier quota.** A full S5 dev run is roughly 2 to 3 Gemini requests per question. The client paces itself at 5 requests/min per model. If the daily quota runs out, the run stops cleanly; re-run the same command the next day to resume from the checkpoint.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `docker compose` cannot connect to the Docker API | Start Docker Desktop and wait until it says "running". |
| Neo4j container never becomes healthy | Check `docker logs waypoint-neo4j`. A password shorter than 8 characters is rejected; fix `.env`, then `docker compose down -v` and `docker compose up -d --wait`. |
| Port 7474 or 7687 already in use | Another Neo4j is running. Stop it, or stop its container. |
| `ValidationError ... neo4j_password` / `model_fast` | `.env` is missing or incomplete. Redo step 4 in the repo root. |
| Many tests "skipped" | Neo4j is not running or not loaded. That is fine for a quick check; for the full suite do steps 5, 6 and 8. |
| Index tests fail with "embedding cache incomplete" | Run step 7, then step 8. |
| `503` in the UI or "quota" errors | The Gemini free-tier quota is used up (per minute or per day). Wait and retry. |
| `make: .venvScriptspython.exe: command not found` | You ran make from Git Bash on Windows. Use PowerShell or cmd, or the plain commands. |
| `pip install -e .[dev]` fails in zsh | Quote it: `".[dev]"`. |

---

## Repository layout

```
waypoint/            the application
  graph/             Neo4j loader, read-only guard, Cypher templates
  retrieval/         chunking, embeddings, index, search, entity linking, router, access filter
  rules/             policy rules as JSON predicates and the rule engine
  answer/            context pack, generator, verifier, the S5 system
  llm/               Gemini (default) and Anthropic clients over plain HTTP
  eval/              eval runner, scorers, judge, safety checker, baselines, bootstrap
  api/               FastAPI app and the static UI (index.html, app.js, Cytoscape.js)
tests/               pytest suite
data/zenvora_kb/     the fictional dataset (read-only)
eval/                eval split and the safety question sets
eval_runs/           committed results of past runs (new runs stay local)
cache_seed/          precomputed caches; copy to .cache/ (step 7)
docs/                design, results and write-ups
docker-compose.yml   Neo4j 5.26 Community
```

Models behind the LLM steps: router and judge `gemini-3.5-flash-lite`, answers `gemini-3.1-flash-lite`, embeddings Cohere `embed-v5.0-fast` (1024 dimensions). Final test-split numbers are not in yet. Dev-split write-ups are in `docs/` (for example [docs/s5_dev_3.3c.md](docs/s5_dev_3.3c.md) and [docs/scoreboard_dev_baselines.md](docs/scoreboard_dev_baselines.md)).
