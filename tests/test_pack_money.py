"""Money in the pack (PLAN 2.6 fix C): rule values, inputs and params in INR with Indian grouping."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest
from neo4j import Driver

from tests.test_answer import HR, route_json, s5
from waypoint.answer.pack import ContextPack, PackItem, _args, _value, inr
from waypoint.answer.verify import verify


@pytest.mark.parametrize("amount,text", [
    (0, "INR 0"), (500, "INR 500"), (3500, "INR 3,500"), (11000, "INR 11,000"), (25000, "INR 25,000"),
    (100000, "INR 1,00,000"), (2550000, "INR 25,50,000"), (12345678, "INR 1,23,45,678"), (1500.5, "INR 1,500.50"),
])
def test_inr_indian_grouping(amount: float, text: str) -> None:
    assert inr(amount) == text


def test_only_money_keys_are_formatted() -> None:
    assert _value(11000, "cap_inr") == "INR 11,000" and _value(30000, "amount") == "INR 30,000"
    assert _value(60, "notice_period_days") == "60" and _value(True, "amount") == "yes"
    assert _value({"amount": 150000, "city": "Pune"}) == "amount: INR 1,50,000; city: Pune"
    assert _args({"amount": 30000, "international": False}) == "amount=INR 30,000, international=False"


@pytest.mark.neo4j
def test_hotel_cap_rendered_in_inr(driver: Driver, tmp_path: Path) -> None:
    plan = [{"op": "HOTEL_CAP", "args": {"subject": "asker", "city": "Pune"}}]
    sys, llm = s5(driver, tmp_path, route_json("personal_rule", plan, needs_identity=True),
                  '{"answer": "ok", "cited_ids": ["step1"]}', '{"answer": "ok", "cited_ids": ["step1"]}')
    sys.answer("What is my hotel cap in Pune?", HR, date(2026, 10, 10))
    m = re.search(r"cap_inr: (INR [\d,]+)", llm.calls[1]["prompt"])
    assert m and re.fullmatch(r"INR \d{1,2}(,\d{2})*,\d{3}", m[1]), llm.calls[1]["prompt"]


def test_verifier_accepts_inr_and_raw_forms() -> None:
    pack = ContextPack("What is the hotel cap?", HR, date(2026, 10, 10), [
        PackItem("step1", "rule", "rule HOTEL_CAP\nstatus: ok\ncap_inr: INR 11,000", "primary")])
    for answer in ("INR 11,000.", "11000 INR.", "Rs 11,000."):
        assert verify(answer, ["step1"], pack).ok, answer
    assert not verify("INR 12,000.", ["step1"], pack).ok
