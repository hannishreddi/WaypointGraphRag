"""Base employee facts the rules read: from the CSVs (offline) or from the graph.

Only base columns are read. The derived columns of employees.csv (work_mode,
notice_period_days, tenure_years, ...) are the answer key for 2026-10-10 and are
never read here: the rule engine computes them from join_date, band, status and as_of.
`status` is restricted (rule 6); the engine decides who may see results that use it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import cache
from typing import Any

from neo4j import Driver

from waypoint.graph.db import run_read
from waypoint.graph.load import read_csv

BASE_COLUMNS = ("employee_id", "full_name", "band", "join_date", "status", "department_id",
                "manager_employee_id", "location_id")
DERIVED_COLUMNS = ("work_mode", "work_mode_reason", "notice_period_days", "tenure_years",
                   "total_experience_years")


@dataclass(frozen=True)
class EmployeeFacts:
    employee_id: str
    name: str
    band: str
    join_date: date
    status: str  # raw text, restricted
    department_id: str | None
    department_code: str | None
    manager_id: str | None
    location_id: str | None
    base_city: str | None


FactStore = dict[str, EmployeeFacts]


@cache
def _csv_facts() -> tuple[tuple[str, EmployeeFacts], ...]:
    codes = {d["department_id"]: d["code"] for d in read_csv("departments")}
    cities = {loc["location_id"]: loc["city"] for loc in read_csv("locations")}
    out = []
    for raw in read_csv("employees"):
        r = {k: raw[k] for k in BASE_COLUMNS}
        out.append((r["employee_id"], EmployeeFacts(
            r["employee_id"], r["full_name"], r["band"], date.fromisoformat(r["join_date"]), r["status"],
            r["department_id"] or None, codes.get(r["department_id"]), r["manager_employee_id"] or None,
            r["location_id"] or None, cities.get(r["location_id"]))))
    return tuple(out)


def facts_from_csv() -> FactStore:
    return dict(_csv_facts())


FACTS_QUERY = """
MATCH (e:Employee)
OPTIONAL MATCH (e)-[:WORKS_IN]->(d:Department)
OPTIONAL MATCH (e)-[:REPORTS_TO]->(m:Employee)
OPTIONAL MATCH (e)-[:BASED_AT]->(l:Location)
RETURN e.employee_id AS employee_id, e.name AS name, e.band AS band,
       toString(e.join_date) AS join_date, e.status AS status,
       d.department_id AS department_id, d.code AS department_code,
       m.employee_id AS manager_id, l.location_id AS location_id, l.city AS base_city
ORDER BY employee_id"""


def facts_from_graph(driver: Driver) -> FactStore:
    out: FactStore = {}
    for r in run_read(driver, FACTS_QUERY):
        row: dict[str, Any] = dict(r)
        row["join_date"] = date.fromisoformat(row["join_date"])
        out[row["employee_id"]] = EmployeeFacts(**row)
    return out
