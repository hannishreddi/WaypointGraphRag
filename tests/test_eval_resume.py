"""Runner checkpoint/resume and clean quota stops, with fake systems (no API calls)."""
from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

import pytest

from tests.test_llm_structured import ScriptedLLM
from waypoint.contract import Response
from waypoint.eval import run as runmod
from waypoint.eval.judge import Judge
from waypoint.llm.client import DailyQuotaExceeded, QuotaTooSmall


class Counter:
    def __init__(self) -> None:
        self.n = 0

    def __call__(self) -> int:
        return self.n


class QuotaSystem:
    """Answers until `fail_at` calls, then raises the given QuotaStop; counts API calls."""

    name = "quota"
    config_id = "v1"

    def __init__(self, calls: Counter, fail_at: int | None = None, exc: type[Exception] = DailyQuotaExceeded,
                 error_ids: frozenset[str] = frozenset()) -> None:
        self.asked: list[str] = []
        self.calls, self.fail_at, self.exc, self.error_ids = calls, fail_at, exc, error_ids

    def answer(self, question: str, asker_id: str, as_of: date) -> Response:
        if self.fail_at is not None and len(self.asked) + 1 >= self.fail_at:
            raise self.exc("quota gone")
        self.asked.append(question)
        self.calls.n += 2  # e.g. one 429 retry
        if question in self.error_ids:
            raise ValueError("transient")
        return Response(answer="Arvind Kulkarni", route="t", as_of=as_of)


def rows(out: Path) -> list[dict[str, str]]:
    with open(out / "results.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def runs(root: Path) -> list[Path]:
    return [p for p in root.iterdir() if not p.name.startswith(".")]


@pytest.mark.parametrize("exc", [DailyQuotaExceeded, QuotaTooSmall])
def test_quota_stop_then_resume(tmp_path: Path, exc: type[Exception]) -> None:
    calls = Counter()
    first = QuotaSystem(calls, fail_at=5, exc=exc)
    with pytest.raises(runmod.RunStopped, match=r"(?s)question 5/10.*re-run the same command"):
        runmod.run_eval(split="dev", system=first, judge=None, out_root=tmp_path, limit=10, api_calls=calls)
    assert len(first.asked) == 4 and runs(tmp_path) == []  # no partial outputs
    (ckpt,) = (tmp_path / ".checkpoints").iterdir()
    assert len(ckpt.read_text(encoding="utf-8").splitlines()) == 4

    second = QuotaSystem(calls)
    out = runmod.run_eval(split="dev", system=second, judge=None, out_root=tmp_path, limit=10, api_calls=calls)
    assert len(second.asked) == 6 and not set(first.asked) & set(second.asked)
    got = rows(out)
    assert len(got) == 10 and all(r["api_calls"] == "2" for r in got)
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert "resumed 4 finished rows" in summary and "LLM API calls" in summary and ": 20" in summary
    config = json.loads((out / "run_config.json").read_text(encoding="utf-8"))
    assert config["resumed_rows"] == 4 and config["checkpoint"].endswith(ckpt.name)


def test_daily_stop_from_judge_also_checkpoints(tmp_path: Path) -> None:
    class QuotaLLM(ScriptedLLM):
        def complete(self, **kw: object) -> object:
            if len(self.calls) >= 1:
                raise DailyQuotaExceeded("judge quota")
            return super().complete(**kw)  # type: ignore[arg-type]

    judge = Judge(QuotaLLM('{"verdict": "correct", "reason": "ok"}'), model="fast", cache_dir=tmp_path / "j")
    with pytest.raises(runmod.RunStopped, match="judge quota"):
        runmod.run_eval(split="dev", system=QuotaSystem(Counter()), judge=judge, out_root=tmp_path)
    (ckpt,) = (tmp_path / ".checkpoints").iterdir()
    done = [json.loads(line) for line in ckpt.read_text(encoding="utf-8").splitlines()]
    assert sum(r["scorer"] == "judge" for r in done) == 1  # the judged row before the stop is kept


def test_error_rows_are_retried_on_resume(tmp_path: Path) -> None:
    probe = runmod.qmod.load_questions("dev")[:6]
    bad = frozenset({probe[2].question})
    first = QuotaSystem(Counter(), error_ids=bad)
    out1 = runmod.run_eval(split="dev", system=first, judge=None, out_root=tmp_path, limit=6)
    assert [r["status"] for r in rows(out1)].count("error") == 1
    second = QuotaSystem(Counter())
    out2 = runmod.run_eval(split="dev", system=second, judge=None, out_root=tmp_path, limit=6)
    assert second.asked == [probe[2].question] and "error" not in [r["status"] for r in rows(out2)]


def test_config_change_does_not_resume(tmp_path: Path) -> None:
    runmod.run_eval(split="dev", system=QuotaSystem(Counter()), judge=None, out_root=tmp_path, limit=3,
                    models={"model_answer": "a"})
    again = QuotaSystem(Counter())
    runmod.run_eval(split="dev", system=again, judge=None, out_root=tmp_path, limit=3,
                    models={"model_answer": "b"})
    assert len(again.asked) == 3


def test_dev_only_system_refuses_test_split(tmp_path: Path) -> None:
    class DevOnly(QuotaSystem):
        dev_only = True

    with pytest.raises(ValueError, match="dev split only"):
        runmod.run_eval(split="test", system=DevOnly(Counter()), judge=None, out_root=tmp_path)
