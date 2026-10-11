"""Leakage hardening (rule 2): every number in predicates.json must come from the policy text.

Each numeric threshold, amount, day count and month count in a rule case (its `when`
values and every number inside its `result`) must appear in the text of a policy section
the case cites, or in the policy_rules.csv row it cites. Rule-level `description` and
`base` numbers must appear in the union of the rule's cited sections. The derived-date
constants (induction days, probation months) are checked against their cited sections.
None of this may come from eval/questions.csv.
"""
from __future__ import annotations

import re
from decimal import Decimal
from functools import cache
from typing import Any

import pytest

from waypoint.config import DATA_DIR
from waypoint.graph.load import read_csv
from waypoint.rules import derived as Dv
from waypoint.rules.engine import Source, load_rules

# A number not glued to a preceding letter ("Z1", "R044" and "D03" are ids, not numbers).
NUM = re.compile(r"(?<![A-Za-z\d.,])\d[\d,]*(?:\.\d+)?")

# Numbers that are not policy facts: none today. A documented exception would go here as
# (rule_id, case_id or "*", number) with a comment saying where the number comes from.
EXCEPTIONS: set[tuple[str, str, Decimal]] = set()


def numbers_in_text(text: str) -> set[Decimal]:
    return {Decimal(m.group().rstrip(",").replace(",", "")) for m in NUM.finditer(text)}


def numbers_in(value: Any) -> set[Decimal]:
    if isinstance(value, bool) or value is None:
        return set()
    if isinstance(value, (int, float)):
        return {Decimal(str(value))}
    if isinstance(value, str):
        return numbers_in_text(re.sub(r"\{[^}]*\}", "", value))  # placeholders are not numbers
    if isinstance(value, dict):
        return set().union(*(numbers_in(v) for k, v in value.items() if k != "attr"))
    if isinstance(value, list):
        return set().union(*(numbers_in(v) for v in value))
    raise TypeError(type(value))


@cache
def section_text(policy: str, section: int) -> str:
    path = next(DATA_DIR.glob(f"policies/*/{policy}_*.md"))
    m = re.search(rf"^## {section}\. .*?(?=^## |\Z)", path.read_text(encoding="utf-8"), re.M | re.S)
    assert m, (policy, section)
    return m.group()


@cache
def _policy_rules() -> dict[str, str]:
    return {r["rule_id"]: " ".join(r.values()) for r in read_csv("policy_rules")}


def source_numbers(sources: list[Source]) -> set[Decimal]:
    out: set[Decimal] = set()
    for s in sources:
        out |= numbers_in_text(section_text(s.policy, s.section))
        if s.rule_id:
            out |= numbers_in_text(_policy_rules()[s.rule_id])
    return out


def _cases() -> list[tuple[str, str]]:
    return [(rid, c.id) for rid, r in load_rules().items() for c in r.cases]


def test_number_extraction() -> None:
    assert numbers_in_text("INR 25,001 to INR 1,00,000, Band Z1, Tier-1, 1.5 per month, R044") == {
        Decimal("25001"), Decimal("100000"), Decimal("1"), Decimal("1.5")}
    assert numbers_in({"attr": "band", "op": "in", "value": ["Z1", "Z2"]}) == set()
    assert numbers_in({"x": True, "y": "{probation_end|date}", "z": 90}) == {Decimal(90)}


@pytest.mark.parametrize("rule_id,case_id", _cases())
def test_case_numbers_appear_in_cited_text(rule_id: str, case_id: str) -> None:
    case = next(c for c in load_rules()[rule_id].cases if c.id == case_id)
    found = numbers_in(case.when) | numbers_in(case.result)
    missing = {n for n in found - source_numbers(case.sources) if (rule_id, case_id, n) not in EXCEPTIONS}
    assert not missing, f"{rule_id}/{case_id}: {sorted(missing)} not in {[(s.policy, s.section) for s in case.sources]}"


@pytest.mark.parametrize("rule_id", list(load_rules()))
def test_rule_level_numbers_appear_in_cited_text(rule_id: str) -> None:
    rule = load_rules()[rule_id]
    found = numbers_in(rule.description) | numbers_in(rule.base)
    allowed = source_numbers([s for c in rule.cases for s in c.sources])
    missing = {n for n in found - allowed if (rule_id, "*", n) not in EXCEPTIONS}
    assert not missing, f"{rule_id}: {sorted(missing)}"


def test_derived_constants_appear_in_cited_text() -> None:
    assert re.search(rf"\b{Dv.INDUCTION_DAYS} calendar days\b", section_text("ZEN-POL-002", 4))
    assert re.search(rf"\b{Dv.PROBATION_MONTHS} months\b", section_text("ZEN-POL-003", 5))


def test_leave_entitlements_match_their_table_row() -> None:
    """Stricter than the union check: each entitlement equals the Entitlement cell of its own row."""
    rows = {}
    for line in section_text("ZEN-POL-003", 3).splitlines():
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) == 3:
            rows[cells[0]] = cells[1]
    entitlements = load_rules()["LEAVE_ENTITLEMENTS"].base["entitlements"]
    assert entitlements == {k: rows[k] for k in entitlements}
