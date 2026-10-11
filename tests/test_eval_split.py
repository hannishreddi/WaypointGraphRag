"""eval/split.json (PLAN 1.4, rule 2): 60 dev / 191 test, stratified by category x hops, seed 42."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from waypoint.eval import questions as qmod
from waypoint.eval.questions import SPLIT_PATH, read_all_questions
from waypoint.eval.split import DEV_SIZE, SEED, make_split, write_split


@pytest.fixture(scope="module")
def all_questions() -> list[qmod.Question]:
    return read_all_questions()


def test_dataset_shape(all_questions: list[qmod.Question]) -> None:
    assert len(all_questions) == 251
    assert len({q.stratum for q in all_questions}) == 15


def test_split_is_deterministic(all_questions: list[qmod.Question]) -> None:
    assert make_split(all_questions) == make_split(list(reversed(all_questions)))


def test_split_sizes_overlap_and_coverage(all_questions: list[qmod.Question]) -> None:
    s = make_split(all_questions)
    dev, test = set(s["dev"]), set(s["test"])
    assert len(dev) == DEV_SIZE == 60 and len(test) == 191
    assert not dev & test
    assert dev | test == {q.id for q in all_questions}
    assert s["seed"] == SEED == 42


def test_each_stratum_in_proportion(all_questions: list[qmod.Question]) -> None:
    s = make_split(all_questions)
    by_id = {q.id: q.stratum for q in all_questions}
    for key, c in s["strata"].items():
        assert c["dev"] + c["test"] == c["total"]
        assert sum(by_id[i] == key for i in s["dev"]) == c["dev"]
        assert abs(c["dev"] - c["total"] * DEV_SIZE / 251) <= 1, key
        assert c["dev"] >= 1 and c["test"] >= 1, key  # every stratum is visible in both splits


def test_write_refuses_overwrite_without_force(tmp_path: Path, all_questions: list[qmod.Question]) -> None:
    path = tmp_path / "split.json"
    write_split(path, all_questions)
    path.write_text('{"sentinel": true}', encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_split(path, all_questions)
    assert json.loads(path.read_text(encoding="utf-8")) == {"sentinel": True}
    write_split(path, all_questions, force=True)
    assert json.loads(path.read_text(encoding="utf-8")) == make_split(all_questions)


def test_committed_split_matches_generator(all_questions: list[qmod.Question]) -> None:
    assert SPLIT_PATH.is_file(), "run `python -m waypoint.eval.split` once"
    assert json.loads(SPLIT_PATH.read_text(encoding="utf-8")) == make_split(all_questions)
