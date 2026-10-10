# Windows: run with mingw32-make (or install GNU make). Targets match CLAUDE.md.
ifeq ($(OS),Windows_NT)
PY ?= .venv\Scripts\python.exe
else
PY ?= .venv/bin/python
endif

.PHONY: install up down load index test eval-dev eval-test serve

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

test:  ## unit tests
	$(PY) -m pytest -q

eval-dev:
	$(PY) -m waypoint.eval.run --split dev

eval-test:  ## final numbers only
	$(PY) -m waypoint.eval.run --split test

serve:  ## API + UI on http://localhost:8000
	$(PY) -m uvicorn waypoint.api.app:app --reload --port 8000
