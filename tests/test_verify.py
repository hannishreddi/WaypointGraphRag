"""Deterministic verifier (PLAN 2.5): normalisation and pass/fail decisions."""
from __future__ import annotations

from datetime import date

import pytest

from waypoint.answer.generate import NOT_FOUND
from waypoint.answer.pack import ContextPack, PackItem
from waypoint.answer.verify import date_supported, extract_dates, extract_numbers, names, verify


@pytest.mark.parametrize("text,expected", [
    ("INR 1,00,000", {100000}), ("Rs. 100,000", {100000}), ("₹1 lakh", {100000}), ("1.5 lakh", {150000}),
    ("25k", {25000}), ("twenty-six weeks", {26}), ("twenty six", {26}), ("ninety days", {90}),
    ("the 3rd step", {3}), ("1.5 per month", {1.5}), ("a 60-day notice", {60}), ("Tier-1 city", {1}),
    ("ZV-1001 in D05, band Z7, ZEN-POL-002 and ZEN-DPL-FIN-01", set()), ("one of them", set()),
    ("chunk ZEN-POL-003::s7::0", set()), ("4 rows, four people", {4}),
])
def test_numbers(text: str, expected: set) -> None:
    assert extract_numbers(text) == {float(x) for x in expected}


@pytest.mark.parametrize("text,expected", [
    ("18 October 2026", (2026, 10, 18)), ("2026-10-18", (2026, 10, 18)), ("October 18, 2026", (2026, 10, 18)),
    ("18/10/2026", (2026, 10, 18)), ("18th of Oct 2026", (2026, 10, 18)), ("18 Oct", (None, 10, 18)),
    ("Sept 1", (None, 9, 1)), ("March 2027", (2027, 3, None)),
])
def test_dates(text: str, expected: tuple) -> None:
    found, rest = extract_dates(f"until {text}.")
    assert found == [expected] and not extract_numbers(rest)


def test_lowercase_may_is_not_a_date() -> None:
    assert extract_dates("you may 5 times")[0] == []


def test_date_matching() -> None:
    ev = [(2026, 10, 18), (None, 11, 14)]
    assert date_supported((None, 10, 18), ev) and date_supported((2026, 10, None), ev)
    assert date_supported((2026, 11, 14), ev)  # evidence without a year
    assert not date_supported((2026, 10, 19), ev) and not date_supported((2025, 10, 18), ev)


def test_names() -> None:
    assert names("Yes. Karthik Naidu approves it, per the Head of People & Culture's rule.") == [
        "Karthik Naidu", "Head of People & Culture"]
    assert names("No, Arjun works in Backend.") == []


def pack(text: str, question: str = "When does Arjun Menon's induction end?") -> ContextPack:
    return ContextPack(question, "ZV-1006", date(2026, 10, 10), [
        PackItem("asker", "identity", "The asker is Lakshmi Prasanna Varma (ZV-1006)."),
        PackItem("step1", "rule", text, "primary")])


RULE = ("rule INDUCTION_END for subject ZV-1042 as of 2026-10-10\nstatus: ok\n"
        "induction_end: 18 Oct 2026; budget: INR 1,00,000; members: [4 items] Arjun Menon | Divya Krishnamurthy")


@pytest.mark.parametrize("answer", [
    "Arjun Menon's induction ends on 18 October 2026.",
    "2026-10-18, for Arjun Menon.",
    "October 18 (Arjun Menon).",
    "Budget: ₹100,000, that is 1 lakh.",
    "Four people: Arjun Menon; Divya Krishnamurthy.",
])
def test_supported_answers_pass(answer: str) -> None:
    v = verify(answer, ["step1"], pack(RULE))
    assert v.ok, v.issues


@pytest.mark.parametrize("answer,cited,issue", [
    ("It ends on 19 October 2026.", ["step1"], "date 2026-10-19"),
    ("It takes 120 days.", ["step1"], "number 120"),
    ("Ask Ravi Kumar.", ["step1"], "name 'Ravi Kumar'"),
    ("Ask Karthik Naidu.", ["step1"], "entity 'Karthik Naidu' (ZV-1003)"),
    ("18 October 2026.", ["step9"], "cited id 'step9'"),
    ("18 October 2026.", [], "no context item is cited"),
])
def test_unsupported_answers_fail(answer: str, cited: list, issue: str) -> None:
    v = verify(answer, cited, pack(RULE))
    assert not v.ok and any(i.startswith(issue) for i in v.issues), v.issues


def test_question_terms_and_not_found() -> None:
    assert verify("Arjun Menon: 18 Oct.", ["step1"], pack(RULE)).ok  # name from the question
    assert verify(NOT_FOUND, [], pack(RULE), not_found=NOT_FOUND).ok
