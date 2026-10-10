"""Deterministic MENTIONS (PLAN 1.3): ids, full names and policy codes, looked up in the CSVs."""
from __future__ import annotations

from tests import csv_expect as X
from waypoint.retrieval.chunking import build_corpus
from waypoint.retrieval.mentions import Target, find_mentions


def ids(text: str) -> list[tuple[str, str]]:
    return [(t.label, t.id) for t in find_mentions(text)]


def test_policy_code_with_word_boundaries() -> None:
    assert ids("Handled under ZEN-POL-004.") == [("Policy", "ZEN-POL-004")]
    assert ids("See ZEN-DPL-HR-01 (appraisals).") == [("Policy", "ZEN-DPL-HR-01")]
    assert ids("ZEN-POL-0040 and XZEN-POL-004 are not codes") == []


def test_full_name_and_id_map_to_one_employee() -> None:
    pooja = X.employee_id("Pooja Agarwal")
    assert ids("Pooja Agarwal's pipelines; ask ZV-1031 or Pooja Agarwal") == [("Employee", pooja)]
    assert ids("Pooja built it") == []  # first names are slice 2.1


def test_longest_match_wins_over_contained_name() -> None:
    d10 = next(r for r in X.rows("departments") if r["department_id"] == "D10")
    product = next(r for r in X.rows("products") if r["name"] in d10["name"])
    assert ids(f"Ask {d10['name']} first.") == [("Department", "D10")]
    assert ids(f"{product['name']} launched.") == [("Product", product["product_id"])]


def test_projects_departments_by_name_and_id() -> None:
    assert ids("Project Atlas and PJ02; D05 and Finance & Accounts") == [
        ("Project", "PJ01"), ("Project", "PJ02"), ("Department", "D05"), ("Department", "D02")]


def test_chunk_mentions_come_from_body_not_prefix() -> None:
    chunks = {c.chunk_id: c for c in build_corpus().chunks}
    assert chunks["ZEN-POL-003::s1::0"].mentions == ()  # prefix names ZEN-POL-003, body does not
    s4 = chunks["ZEN-POL-003::s4::0"]
    assert Target("Policy", "policy_id", "ZEN-POL-004") in s4.mentions
    handbook = [c for c in chunks.values()
                if c.doc_id == "company:05_new_joiner_handbook" and "ZEN-POL-002" in c.body]
    assert handbook
    assert all(Target("Policy", "policy_id", "ZEN-POL-002") in c.mentions for c in handbook)
