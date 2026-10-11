r"""Builds tests/fixtures/verifier_false_alarms.json (PLAN 2.6 fix A). Run once, by hand:

    .venv\Scripts\python.exe -m tests.fixtures.build_verifier_cases eval_runs/20261011-140305_s5_dev

For every dev row of the 2.5 S5 run where the verifier triggered (all 28 were false alarms,
docs/s5_dev_2.5_report.md), it rebuilds the context pack the answer was checked against
(cached route, templates, rules, cached query embeddings: no LLM or embedding calls) and
stores the pack items with the generator's first answer. Answers are model output, not gold.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from waypoint.answer.pack import build_pack
from waypoint.config import DEFAULT_AS_OF, get_settings
from waypoint.graph.db import get_driver
from waypoint.llm.client import get_llm_client
from waypoint.retrieval.embed import Embedder
from waypoint.retrieval.router import Router, execute

OUT = Path(__file__).with_name("verifier_false_alarms.json")


def main(run_dir: str) -> None:
    rows = list(csv.DictReader(open(Path(run_dir) / "results.csv", encoding="utf-8", newline="")))
    s = get_settings()
    router, driver, embedder = Router(get_llm_client(), model=s.model_fast), get_driver(), Embedder.from_settings()
    cases = []
    for r in rows:
        if r["verifier"] not in ("regenerated", "failed"):
            continue
        trace = json.loads(r["trace"])
        route = router.route(r["question"], r["asker_id"])
        assert route.cached, f"{r['id']}: route not cached"
        pack = build_pack(route, execute(route, driver=driver, as_of=DEFAULT_AS_OF, embedder=embedder),
                          driver=driver, as_of=DEFAULT_AS_OF)
        assert pack.ids() == trace["pack_items"], f"{r['id']}: pack differs from the run"
        cases.append({"id": r["id"], "question": r["question"], "asker_id": r["asker_id"],
                      "answer": trace["first_answer"], "issues_v1": trace["issues"],
                      "items": [{"id": i.id, "kind": i.kind, "text": i.text, "path": i.path} for i in pack.items]})
    OUT.write_text(json.dumps(cases, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(cases)} cases to {OUT}")


if __name__ == "__main__":
    main(sys.argv[1])
