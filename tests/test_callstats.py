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


# Added 2026-10-16, after the test results were seen: resumed runs. The final S1 test folder
# printed retries 119 because only the last session's judge line was counted (true figure 62).

def _session(root: Path, name: str, rows: list[dict], judge_calls: int, started: str, resumed: int,
             checkpoint: str = r"C:\repo\eval_runs\.checkpoints\s1_test_abc.jsonl") -> Path:
    import csv

    d = root / name
    d.mkdir()
    cols = ["id", "scorer", "status", "api_calls", "verifier", "trace"]
    with open(d / "results.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    (d / "summary.md").write_text(f"- judge gemini-x: {judge_calls} API calls, 10 tokens\n", encoding="utf-8")
    (d / "run_config.json").write_text(json.dumps({"checkpoint": checkpoint, "started_at": started,
                                                   "resumed_rows": resumed}), encoding="utf-8")
    return d


def _row(qid: str, scorer: str, status: str, calls: int) -> dict:
    return {"id": qid, "scorer": scorer, "status": status, "api_calls": calls, "verifier": "", "trace": ""}


def _two_sessions(root: Path) -> tuple[Path, Path]:
    """Session 1: Q1 judged (answer + judge, 2 requests), Q2 exact with one retry (2), Q3 errors
    after 5 requests. Session 2 resumes Q1 and Q2 and answers and judges Q3 (2)."""
    s1 = _session(root, "20261016-120000_s1_test",
                  [_row("Q1", "judge", "scored", 2), _row("Q2", "exact", "scored", 2), _row("Q3", "judge", "error", 5)],
                  judge_calls=1, started="2026-10-16T12:00:00", resumed=0)
    s2 = _session(root, "20261016-130000_s1_test",
                  [_row("Q1", "judge", "scored", 2), _row("Q2", "exact", "scored", 2), _row("Q3", "judge", "scored", 2)],
                  judge_calls=1, started="2026-10-16T13:00:00", resumed=2)
    return s1, s2


def test_stats_sums_judge_calls_over_all_sessions(tmp_path: Path) -> None:
    from waypoint.eval.callstats import sessions

    s1, s2 = _two_sessions(tmp_path)
    # unrelated folders: another checkpoint, and a later session of the same checkpoint
    _session(tmp_path, "20261016-110000_s5_test", [_row("Q1", "exact", "scored", 9)], 9,
             "2026-10-16T11:00:00", 0, checkpoint="/repo/eval_runs/.checkpoints/s5_test_def.jsonl")
    _session(tmp_path, "20261016-140000_s1_test", [_row("Q1", "judge", "scored", 2)], 7, "2026-10-16T14:00:00", 1)
    assert sessions(s2) == ([s1, s2], True)
    s = stats(s2)
    assert s["requests"] == 6 and s["logical"] == {"router": 0, "generator": 3, "judge": 2}
    assert s["retries"] == 1  # Q2's retry; the old code counted judge 1 and printed 2
    assert s["sessions"] == 2 and s["complete"] and s["error_requests"] == 5
    assert stats(s1)["sessions"] == 1 and stats(s1)["complete"]  # a first session stands alone


def test_stats_flags_an_incomplete_chain(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    import shutil

    from waypoint.eval.callstats import main

    s1, s2 = _two_sessions(tmp_path)
    shutil.rmtree(s1)  # earlier session not kept
    s = stats(s2)
    assert not s["complete"] and s["logical"]["judge"] == 1 and s["retries"] == 2
    main([str(s2)])
    out = capsys.readouterr().out
    assert "retries <= 2" in out and "INCOMPLETE" in out


def test_stats_flags_a_session_that_left_no_folder(tmp_path: Path) -> None:
    s1, s2 = _two_sessions(tmp_path)
    cfg = json.loads((s2 / "run_config.json").read_text(encoding="utf-8"))
    (s2 / "run_config.json").write_text(json.dumps(cfg | {"resumed_rows": 3}), encoding="utf-8")
    assert not stats(s2)["complete"]  # 3 resumed, but the folders show only 2 finished rows


def test_stats_single_session_unchanged(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    from waypoint.eval.callstats import main

    d = _session(tmp_path, "run", [_row("Q1", "judge", "scored", 3)], 1, "2026-10-16T12:00:00", 0)
    s = stats(d)
    assert s["retries"] == 1 and s["complete"] and s["sessions"] == 1 and s["error_requests"] == 0
    main([str(d)])
    assert capsys.readouterr().out.strip().endswith("retries 1; judge-scored rows 1; sessions 1")
