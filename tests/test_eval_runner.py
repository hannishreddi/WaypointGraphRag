"""Eval runner: output files, --no-judge, judge review sample, and the test-split guard (rule 2)."""
from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

import pytest

from tests.test_llm_structured import ScriptedLLM
from waypoint.contract import GraphCitation, Response
from waypoint.eval import questions as qmod
from waypoint.eval import run as runmod
from waypoint.eval.judge import Judge
from waypoint.eval.questions import (ASKER_OVERRIDES, DEFAULT_ASKER, TEST_ENV, TestSplitLocked,
                                     load_questions, load_split_ids)
from waypoint.eval.systems import EchoSystem


class RecordingSystem:
    """Answers with the gold-free question text; records every call."""

    name = "recording"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, date]] = []

    def answer(self, question: str, asker_id: str, as_of: date) -> Response:
        self.calls.append((question, asker_id, as_of))
        return Response(answer=f"Arvind Kulkarni. {question}", route="test", as_of=as_of,
                        citations=[GraphCitation(type="graph", path="ZV-1002 -REPORTS_TO-> ZV-1001")])


def read_rows(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_echo_system_contract() -> None:
    r = EchoSystem().answer("Who heads QA?", "ZV-1006", date(2026, 10, 10))
    assert r.answer == "Who heads QA?" and r.as_of == date(2026, 10, 10) and r.citations == []
    assert r.usage.input_tokens == 0 and r.latency_ms >= 0


def test_askers() -> None:
    assert DEFAULT_ASKER == "ZV-1006"
    assert ASKER_OVERRIDES == {"Q209": "ZV-1042", "Q210": "ZV-1033"}
    assert qmod.asker_for("Q209") == "ZV-1042" and qmod.asker_for("Q001") == "ZV-1006"


def test_run_no_judge_writes_outputs(tmp_path: Path) -> None:
    system = RecordingSystem()
    out = runmod.run_eval(split="dev", system=system, judge=None, out_root=tmp_path,
                          models={"model_fast": "f", "model_answer": "a"})
    assert out.parent == tmp_path and out.name.endswith("_recording_dev")
    rows = read_rows(out / "results.csv")
    dev = load_split_ids("dev")
    assert [r["id"] for r in rows] == dev and len(rows) == 60
    assert all(c[2] == date(2026, 10, 10) for c in system.calls)
    assert {r["asker_id"] for r in rows} <= {"ZV-1006", "ZV-1042", "ZV-1033"}

    judged = [r for r in rows if r["scorer"] == "judge"]
    assert judged and all(r["status"] == "skipped" and r["score"] == "" for r in judged)
    scored = [r for r in rows if r["status"] == "scored"]
    assert all(r["score"] != "" for r in scored)

    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert "By hops" in summary and "By category" in summary
    assert f"skipped (judge off): {len(judged)}" in summary
    config = json.loads((out / "run_config.json").read_text(encoding="utf-8"))
    assert config["system"] == "recording" and config["split"] == "dev" and config["as_of"] == "2026-10-10"
    assert config["judge"] is None and config["models"]["model_fast"] == "f"
    assert len(config["git_commit"]) == 40 and config["default_asker"] == "ZV-1006"
    assert read_rows(out / "judge_review.csv") == []


def test_run_with_fake_judge_and_review_sample(tmp_path: Path) -> None:
    llm = ScriptedLLM(*['{"verdict": "incorrect", "reason": "echo"}'] * 60)
    judge = Judge(llm, model="fast", cache_dir=tmp_path / "cache")
    out = runmod.run_eval(split="dev", system=EchoSystem(), judge=judge, out_root=tmp_path, limit=40,
                          models={"model_fast": "fast", "model_answer": "a"})
    rows = read_rows(out / "results.csv")
    assert len(rows) == 40
    judged = [r for r in rows if r["scorer"] == "judge"]
    assert judged and all(r["status"] == "scored" and r["verdict"] == "incorrect" for r in judged)
    assert len(llm.calls) == len(judged)
    review = read_rows(out / "judge_review.csv")
    assert len(review) == max(1, round(len(judged) * 0.1))
    assert set(review[0]) == {"id", "question", "expected_answer", "answer", "verdict", "reason", "human_verdict"}
    assert all(r["human_verdict"] == "" for r in review)

    # Same answers again: every verdict comes from the cache.
    llm2 = ScriptedLLM()
    runmod.run_eval(split="dev", system=EchoSystem(), judge=Judge(llm2, model="fast", cache_dir=tmp_path / "cache"),
                    out_root=tmp_path, limit=40, models={})
    assert llm2.calls == []


def test_test_split_locked_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(TEST_ENV, raising=False)
    with pytest.raises(TestSplitLocked):
        load_split_ids("test")
    with pytest.raises(TestSplitLocked):
        load_questions("test")
    with pytest.raises(SystemExit, match="eval-test"):
        runmod.main(["--split", "test", "--system", "echo", "--no-judge"])


def test_dev_path_never_reads_test_ids(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv(TEST_ENV, raising=False)
    requested: list[str] = []
    real = qmod.load_split_ids

    def spy(split: str, *a: object, **kw: object) -> list[str]:
        requested.append(split)
        return real(split, *a, **kw)

    monkeypatch.setattr(qmod, "load_split_ids", spy)
    system = RecordingSystem()
    monkeypatch.setitem(runmod.SYSTEMS, "recording", lambda: system)
    runmod.main(["--split", "dev", "--system", "recording", "--no-judge", "--out", str(tmp_path)])

    assert requested == ["dev"]
    split = json.loads(qmod.SPLIT_PATH.read_text(encoding="utf-8"))  # the test reads it, the runner did not
    test_ids = set(split["test"])
    test_questions = {q.question for q in qmod.read_all_questions() if q.id in test_ids}
    assert len(system.calls) == 60 and not {c[0] for c in system.calls} & test_questions
    (run_dir,) = tmp_path.iterdir()
    ids = {r["id"] for r in read_rows(run_dir / "results.csv")}
    assert ids == set(split["dev"]) and not ids & test_ids
