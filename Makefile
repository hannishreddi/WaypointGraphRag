# Windows: run with mingw32-make (or install GNU make). Targets match CLAUDE.md.
ifeq ($(OS),Windows_NT)
PY ?= .venv\Scripts\python.exe
else
PY ?= .venv/bin/python
endif

.PHONY: install up down load index test test-graph eval-dev eval-test serve

install:  ## install deps into .venv (create it first: py -3.14 -m venv .venv)
	$(PY) -m pip install -e .[dev]

up:  ## start Neo4j
	docker compose up -d --wait

down:
	docker compose down

load:  ## build the graph from CSVs
	$(PY) -m waypoint.graph.load

index:  ## chunk, embed, create vector + full-text indexes
	$(PY) -m waypoint.retrieval.index

test:  ## unit tests (neo4j-marked tests skip if Neo4j is down)
	$(PY) -m pytest -q

test-graph: export REQUIRE_NEO4J = 1
test-graph:  ## neo4j-marked tests only; fail if Neo4j is unreachable
	$(PY) -m pytest -q -m neo4j

# make eval-dev SYSTEM=echo LIMIT=10 NO_JUDGE=1
SYSTEM ?= echo
EVAL_FLAGS = --system $(SYSTEM) $(if $(LIMIT),--limit $(LIMIT)) $(if $(NO_JUDGE),--no-judge)

eval-dev:  ## dev split (60 questions)
	$(PY) -m waypoint.eval.run --split dev $(EVAL_FLAGS)

eval-test: export WAYPOINT_EVAL_TEST = 1
eval-test:  ## final numbers only; the only target that may read test ids (rule 2)
	$(PY) -m waypoint.eval.run --split test $(EVAL_FLAGS)

serve:  ## API + UI on http://localhost:8000
	$(PY) -m uvicorn waypoint.api.app:app --reload --port 8000
