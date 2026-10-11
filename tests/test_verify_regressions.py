"""Verifier regressions (PLAN 2.6 fix A).

Supported: the 28 first answers of the 2.5 dev run that the verifier flagged, each checked
against the context pack it was generated from (tests/fixtures/verifier_false_alarms.json,
built by tests/fixtures/build_verifier_cases.py). All 28 were false alarms of the name check:
a Capitalised phrase ran across a sentence end ("Arvind Kulkarni. He") or joined two names
on "and" ("Project Nova and Rahul Khanna").

Unsupported: the same real packs with invented facts planted in the answer. Rohan Verma,
Meenakshi Sundaram and Project Marigold appear nowhere in the dataset; the numbers and
dates are not in the packs. The verifier must still catch them, also next to a real name,
at a sentence end and after "and".
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from waypoint.answer.pack import ContextPack, PackItem
from waypoint.answer.verify import names, verify

CASES = json.loads((Path(__file__).parent / "fixtures" / "verifier_false_alarms.json").read_text(encoding="utf-8"))
BY_ID = {c["id"]: c for c in CASES}


def real_pack(case: dict) -> ContextPack:
    items = [PackItem(i["id"], i["kind"], i["text"], i["path"]) for i in case["items"]]
    return ContextPack(case["question"], case["asker_id"], date(2026, 10, 10), items)


def cited(pack: ContextPack) -> list[str]:
    return [i for i in pack.ids() if i != "asker"]


def test_fixture_is_the_28_false_alarms() -> None:
    assert len(CASES) == 28
    assert sum(" and " in c["issues_v1"][0] for c in CASES) == 2  # Q113, Q119
    assert all(". " in c["issues_v1"][0] for c in CASES if " and " not in c["issues_v1"][0])


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_false_alarms_now_pass(case: dict) -> None:
    pack = real_pack(case)
    verdict = verify(case["answer"], cited(pack), pack)
    assert verdict.ok, verdict.issues


@pytest.mark.parametrize("text,expected", [
    ("Arvind Kulkarni. He is the CEO.", ["Arvind Kulkarni"]),
    ("Naveen Reddy; Sneha Hegde. These employees report to Divya Krishnamurthy.",
     ["Naveen Reddy", "Sneha Hegde", "Divya Krishnamurthy"]),
    ("Sunita Banerjee sponsored Project Nova and Rahul Khanna led it.",
     ["Sunita Banerjee", "Project Nova", "Rahul Khanna"]),
    ("Ask Divya Krishnamurthy: She approves it!", ["Divya Krishnamurthy"]),
    ("Who? Karthik Naidu\nSneha Hegde", ["Karthik Naidu", "Sneha Hegde"]),
    ("Head of People & Culture", ["Head of People & Culture"]),  # & and of still join
    ("It is on Node.js and React Native.", ["React Native"]),  # a dot inside a word is no sentence end
])
def test_names_split_at_sentence_ends_and_and(text: str, expected: list[str]) -> None:
    assert names(text) == expected


# (case, answer with a planted fabrication, issue that must be reported)
FABRICATIONS = [
    ("Q062", "Naveen Reddy; Rohan Verma. These employees report directly to Divya Krishnamurthy.",
     "name 'Rohan Verma'"),
    ("Q062", "Naveen Reddy; Sneha Hegde and Rohan Verma report directly to Divya Krishnamurthy.",
     "name 'Rohan Verma'"),
    ("Q119", "Sunita Banerjee sponsored Project Nova and Meenakshi Sundaram led it.", "name 'Meenakshi Sundaram'"),
    ("Q003", "Arvind Kulkarni. Meenakshi Sundaram is his deputy.", "name 'Meenakshi Sundaram'"),
    ("Q096", "Project Atlas; Project Marigold; Project Ember.", "name 'Project Marigold'"),
    ("Q193", "12000 INR. This is the cap for band Z7 employees travelling to Tier-1 cities.", "number 12000"),
    ("Q193", "11000 INR, revised on 14 November 2026.", "date 2026-11-14"),
    ("Q153", "Karthik Naidu; Sneha Hegde. Both have listed Kafka since 2019.", "number 2019"),
]


@pytest.mark.parametrize("case_id,answer,issue", FABRICATIONS)
def test_fabrications_still_fail(case_id: str, answer: str, issue: str) -> None:
    pack = real_pack(BY_ID[case_id])
    verdict = verify(answer, cited(pack), pack)
    assert not verdict.ok
    assert any(i.startswith(issue) for i in verdict.issues), verdict.issues
