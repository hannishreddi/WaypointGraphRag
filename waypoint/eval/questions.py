"""Eval questions, the dev/test split and who asks each question.

Rule 2: only `make eval-test` (which exports WAYPOINT_EVAL_TEST=1) may load test ids.
`load_split_ids("test")` raises otherwise, so the dev path cannot reach them.
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path

from pydantic import BaseModel

from waypoint.config import DATA_DIR, REPO_ROOT

QUESTIONS_CSV = DATA_DIR / "eval" / "questions.csv"
SPLIT_PATH = REPO_ROOT / "eval" / "split.json"
TEST_ENV = "WAYPOINT_EVAL_TEST"

# The CSV has no asker column. HR can see every restricted fact the gold answers
# reveal (notice, leave), so HR asks by default; the main eval therefore cannot
# show the access filter working (see the safety questions in PLAN 3.3).
DEFAULT_ASKER = "ZV-1006"  # Lakshmi Prasanna Varma, Head of People & Culture
ASKER_OVERRIDES = {
    "Q209": "ZV-1042",  # "I just joined" -> Arjun Menon, in his first 90 days
    "Q210": "ZV-1033",  # "I resigned" -> Tarun Mehta, serving notice
}


class TestSplitLocked(RuntimeError):
    """Test ids requested outside `make eval-test`."""

    __test__ = False  # not a pytest test class


class Question(BaseModel):
    id: str
    category: str
    hops: int
    question: str
    expected_answer: str
    sources: list[str]

    @property
    def stratum(self) -> str:
        return f"{self.category}|{self.hops}"


def read_all_questions(path: Path = QUESTIONS_CSV) -> list[Question]:
    """All 251 questions. For building the split and scorer tests, never for running an eval."""
    with open(path, encoding="utf-8", newline="") as f:
        return [Question(**{**r, "sources": [s.strip() for s in r["sources"].split(",") if s.strip()]})
                for r in csv.DictReader(f)]


def load_split_ids(split: str, path: Path = SPLIT_PATH) -> list[str]:
    if split not in ("dev", "test"):
        raise ValueError(f"unknown split {split!r}")
    if split == "test" and os.environ.get(TEST_ENV) != "1":
        raise TestSplitLocked("test ids are only readable through `make eval-test` (rule 2)")
    if not path.is_file():
        raise FileNotFoundError(f"{path} missing; run `python -m waypoint.eval.split` once")
    return list(json.loads(path.read_text(encoding="utf-8"))[split])


def load_questions(split: str, path: Path = SPLIT_PATH) -> list[Question]:
    ids = load_split_ids(split, path)
    wanted = set(ids)
    by_id = {q.id: q for q in read_all_questions() if q.id in wanted}
    return [by_id[i] for i in ids]


def asker_for(question_id: str) -> str:
    return ASKER_OVERRIDES.get(question_id, DEFAULT_ASKER)
