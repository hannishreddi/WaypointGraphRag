"""3.3d quota planning tools: request statistics from run logs, split sizes (counts only)."""
from __future__ import annotations

import json
from pathlib import Path

from waypoint.eval.callstats import stats
from waypoint.eval.split import counts


def _run(tmp: Path, rows: list[dict], judge_calls: int) -> Path:
    import csv

    d = tmp / "run"
    d.mkdir()
    cols = ["id", "scorer", "status", "api_calls", "verifier", "trace"]
    with open(d / "results.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    (d / "summary.md").write_text(f"- judge gemini-x: {judge_calls} API calls, 10 tokens\n", encoding="utf-8")
    return d


def test_stats_counts_requests_and_logical_calls(tmp_path: Path) -> None:
    rows = [
        {"id": "Q1", "scorer": "exact", "status": "ok", "api_calls": 2, "verifier": "pass",
         "trace": json.dumps({"router_calls": 1})},
        {"id": "Q2", "scorer": "judge", "status": "ok", "api_calls": 5, "verifier": "regenerated",
         "trace": json.dumps({"router_calls": 2})},  # validation retry on the router + regeneration + judge
        {"id": "Q3", "scorer": "exact", "status": "ok", "api_calls": 1, "verifier": "skipped",
         "trace": json.dumps({"router_calls": 1, "refusal": "router"})},  # refuse: no generator call
    ]
    s = stats(_run(tmp_path, rows, judge_calls=1))
    assert s["questions"] == 3 and s["requests"] == 8
    assert s["logical"] == {"router": 4, "generator": 3, "judge": 1}  # Q1 1, Q2 2 (regenerated), Q3 0
    assert s["retries"] == 0 and s["judge_scored"] == 1
    assert round(s["requests_per_question"], 3) == round(8 / 3, 3)


def test_stats_for_a_baseline_without_trace(tmp_path: Path) -> None:
    rows = [{"id": f"Q{i}", "scorer": "exact", "status": "ok", "api_calls": 1, "verifier": "", "trace": ""}
            for i in range(4)]
    rows[0]["api_calls"] = 3  # two HTTP retries
    s = stats(_run(tmp_path, rows, judge_calls=0))
    assert s["logical"] == {"router": 0, "generator": 4, "judge": 0} and s["retries"] == 2


def test_split_counts_only(tmp_path: Path) -> None:
    p = tmp_path / "split.json"
    p.write_text(json.dumps({"dev": ["Q1"], "test": ["Q2", "Q3"], "dev_size": 1, "test_size": 2,
                             "strata": {"policy|1": {"total": 3, "dev": 1, "test": 2}}}), encoding="utf-8")
    c = counts(p)
    assert c == {"dev": 1, "test": 2, "strata": {"policy|1": {"total": 3, "dev": 1, "test": 2}}}
    assert "Q2" not in json.dumps(c)  # no ids
