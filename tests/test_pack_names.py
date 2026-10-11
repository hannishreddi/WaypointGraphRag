"""Pack names ids (PLAN 2.6 fix B): every id argument and rule subject is shown with its
name, and every name comes from the alias table, checked here against the CSVs read directly."""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest
from neo4j import Driver

from tests.test_answer import HR, route_json, s5
from waypoint.answer.pack import _args, named
from waypoint.config import DATA_DIR
from waypoint.retrieval.aliases import entity_name

CSV_DIR = DATA_DIR / "data" / "csv"
AS_OF = date(2026, 10, 10)


def rows(name: str) -> list[dict[str, str]]:
    with open(CSV_DIR / f"{name}.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_all_42_employees_named_as_in_employees_csv() -> None:
    employees = rows("employees")
    assert len(employees) == 42
    for r in employees:
        assert entity_name(r["employee_id"]) == r["full_name"]
        assert named(r["employee_id"]) == f"{r['full_name']} {r['employee_id']}"


@pytest.mark.parametrize("table,id_col,name_col", [
    ("departments", "department_id", "name"), ("projects", "project_id", "name"),
    ("products", "product_id", "name"), ("policies", "policy_id", "title"),
    ("organizations", "org_id", "name"), ("locations", "location_id", "name"), ("skills", "skill_id", "skill"),
])
def test_every_other_entity_named_as_in_its_csv(table: str, id_col: str, name_col: str) -> None:
    for r in rows(table):
        assert entity_name(r[id_col]) == r[name_col], r[id_col]


def test_named_leaves_non_ids_alone() -> None:
    assert named("ZV-1033") == "Tarun Mehta ZV-1033" and named("ZV-1028") == "Sneha Hegde ZV-1028"
    assert named("Pune") == "Pune" and named(3) == "3" and named(True) == "True" and named("ZV-9999") == "ZV-9999"
    assert _args({"employee_id": "ZV-1004", "current": True}) == "employee_id=Divya Krishnamurthy ZV-1004, current=True"


@pytest.mark.neo4j
def test_template_step_header_names_its_argument(driver: Driver, tmp_path: Path) -> None:
    plan = [{"op": "manager", "args": {"employee_id": "ZV-1004"}}]
    sys, llm = s5(driver, tmp_path, route_json(plan=plan, entities=["ZV-1004"]),
                  '{"answer": "Karthik Naidu.", "cited_ids": ["step1"]}')
    sys.answer("Who does Divya Krishnamurthy report to?", HR, AS_OF)
    assert "manager(employee_id=Divya Krishnamurthy ZV-1004) returned 1 row" in llm.calls[1]["prompt"]


@pytest.mark.neo4j
def test_rule_subject_is_named(driver: Driver, tmp_path: Path) -> None:
    plan = [{"op": "NOTICE_PERIOD", "args": {"subject": "ZV-1033"}}]
    sys, llm = s5(driver, tmp_path, route_json("personal_rule", plan, entities=["ZV-1033"]),
                  '{"answer": "60 days.", "cited_ids": ["step1"]}')
    sys.answer("What is Tarun Mehta's notice period?", HR, AS_OF)
    assert "rule NOTICE_PERIOD for subject Tarun Mehta ZV-1033 as of 2026-10-10" in llm.calls[1]["prompt"]
