"""Expected graph values computed from the CSVs only (never from the graph)."""
from __future__ import annotations

import csv
from collections import Counter
from functools import cache

from waypoint.config import DATA_DIR

CSV_DIR = DATA_DIR / "data" / "csv"


@cache
def rows(name: str) -> tuple[dict[str, str], ...]:
    with open(CSV_DIR / f"{name}.csv", encoding="utf-8", newline="") as f:
        return tuple(csv.DictReader(f))


def n(name: str, *required: str) -> int:
    """Rows in a CSV whose `required` columns are all non-empty."""
    return sum(1 for r in rows(name) if all(r[c] for c in required))


def node_counts() -> dict[str, int]:
    return {
        "Company": n("company"),
        "Location": n("locations"),
        "Band": n("bands"),
        "Department": n("departments"),
        "Employee": n("employees"),
        "Organization": n("organizations"),
        "Skill": n("skills"),
        "Certification": n("certifications"),
        "Product": n("products"),
        "Project": n("projects"),
        "Policy": n("policies"),
        "Rule": n("policy_rules"),
    }


def rel_counts() -> dict[str, int]:
    targets = Counter(r["target_type"] for r in rows("policy_applies_to"))
    return {
        "HAS_LOCATION": n("locations") * n("company"),
        "HAS_DEPARTMENT": n("departments") * n("company"),
        "LOCATED_AT": n("departments", "location_id"),
        "WORKS_IN": n("employees", "department_id"),
        "IN_BAND": n("employees", "band"),
        "BASED_AT": n("employees", "location_id"),
        "REPORTS_TO": n("reporting_lines", "manager_employee_id"),
        "HEADS": n("departments", "head_employee_id"),
        "PREVIOUSLY_AT": n("prior_experience"),
        "HAS_SKILL": n("employee_skills"),
        "HOLDS": n("employee_certifications"),
        "OWNS_PRODUCT": n("products", "owner_employee_id"),
        "LEADS_ENGINEERING_OF": n("products", "lead_employee_id"),
        "SPONSORS": n("projects", "sponsor_employee_id"),
        "LEADS": n("projects", "lead_employee_id"),
        "CONTRIBUTES_TO": n("project_departments"),
        "WORKED_ON": n("project_assignments"),
        "OWNED_BY": n("policies", "owner_department_id"),
        "PREPARED_BY": n("policies", "prepared_by_employee_id"),
        "REVIEWED_BY": n("policies", "reviewed_by_employee_id"),
        "APPROVED_BY": n("policies", "approved_by_employee_id"),
        "APPLIES_TO": targets["Company"] + targets["Department"],
        "REFERENCES": n("policy_references"),
        "DEFINES": n("policy_rules"),
    }


def employee_id(full_name: str) -> str:
    return next(r["employee_id"] for r in rows("employees") if r["full_name"] == full_name)


def manager_of() -> dict[str, str]:
    return {r["employee_id"]: r["manager_employee_id"] for r in rows("reporting_lines")}


def ceo_id() -> str:
    (ceo,) = [r["employee_id"] for r in rows("employees") if not r["manager_employee_id"]]
    return ceo
