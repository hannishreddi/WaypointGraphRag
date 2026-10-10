"""Build the graph from data/zenvora_kb/data/csv. PLAN 1.2.

Idempotent: constraints first (IF NOT EXISTS), then every node is MERGEd on its
stable id and every relationship on (start, type, end[, key props]), with
properties SET from the CSV. Nothing is created unconditionally and nothing is
deleted, so a second run changes no counts. All statements are parameterised
and batched with UNWIND. Derived employee columns (work_mode, work_mode_reason,
notice_period_days, tenure_years, total_experience_years) are not loaded; they
are computed at query time from join_date, band, status and as_of.
"""
from __future__ import annotations

import csv
from collections.abc import Callable, Iterable
from datetime import date
from typing import Any

from neo4j import Driver, ManagedTransaction

from waypoint.config import DATA_DIR
from waypoint.graph.db import get_driver, run_read

CSV_DIR = DATA_DIR / "data" / "csv"
BATCH = 500

Row = dict[str, Any]

CONSTRAINTS = {
    "Company": "company_id", "Location": "location_id", "Department": "department_id",
    "Band": "band", "Employee": "employee_id", "Organization": "org_id", "Skill": "skill_id",
    "Certification": "cert_id", "Product": "product_id", "Project": "project_id",
    "Policy": "policy_id", "Rule": "rule_id",
}


def _d(v: str) -> date | None:
    return date.fromisoformat(v) if v else None


def _i(v: str) -> int | None:
    return int(v) if v else None


def _f(v: str) -> float | None:
    return float(v) if v else None


def _s(v: str) -> str | None:
    return v or None


def read_csv(name: str) -> list[dict[str, str]]:
    with open(CSV_DIR / f"{name}.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _company(r: dict[str, str]) -> Row:
    return {"company_id": r["company_id"], "props": {
        "name": r["name"], "founded": _d(r["founded"]), "hq": r["hq"], "industry": r["industry"],
        "tagline": r["tagline"], "mission": r["mission"], "vision": r["vision"],
        "employees": _i(r["employees"]), "revenue_fy26_inr_cr": _f(r["revenue_fy26_inr_cr"]),
        "attrition_fy26_pct": _f(r["attrition_fy26_pct"])}}


def _location(r: dict[str, str]) -> Row:
    return {"location_id": r["location_id"], "props": {
        "name": r["name"], "city": r["city"], "state": r["state"], "country": r["country"],
        "type": r["type"], "address": r["address"], "opened": _d(r["opened"]), "notes": _s(r["notes"])}}


def _band(r: dict[str, str]) -> Row:
    return {"band": r["band"], "props": {
        "level": r["level"], "meaning": r["meaning"], "notice_period_days": _i(r["notice_period_days"])}}


def _department(r: dict[str, str]) -> Row:
    return {"department_id": r["department_id"], "location_id": r["location_id"], "props": {
        "name": r["name"], "code": r["code"], "mission": r["mission"], "headcount": _i(r["headcount"])}}


def _employee(r: dict[str, str]) -> Row:
    return {"employee_id": r["employee_id"], "department_id": r["department_id"], "band": r["band"],
            "location_id": r["location_id"], "props": {
                "name": r["full_name"], "slug": r["slug"], "email": r["email"], "title": r["title"],
                "band": r["band"], "join_date": _d(r["join_date"]), "status": r["status"],
                "profile_file": r["profile_file"], "resume_file": r["resume_file"]}}


def _product(r: dict[str, str]) -> Row:
    return {"product_id": r["product_id"], "owner": r["owner_employee_id"], "lead": r["lead_employee_id"],
            "props": {"name": r["name"], "launched": _d(r["launched"]), "summary": r["summary"],
                      "stack": r["stack"], "stats": r["stats"]}}


def _project(r: dict[str, str]) -> Row:
    return {"project_id": r["project_id"], "sponsor": r["sponsor_employee_id"], "lead": r["lead_employee_id"],
            "props": {"name": r["name"], "status": r["status"], "start_date": _d(r["start_date"]),
                      "end_date": _d(r["end_date"]), "summary": r["summary"], "tech": r["tech"]}}


def _assignment(r: dict[str, str]) -> Row:
    return {"employee_id": r["employee_id"], "project_id": r["project_id"], "props": {
        "role": r["role"], "from_date": _d(r["from_date"]), "to_date": _d(r["to_date"]),
        "is_current": r["is_current"] == "true"}}


def _policy(r: dict[str, str]) -> Row:
    return {"policy_id": r["policy_id"], "owner": r["owner_department_id"],
            "prepared": r["prepared_by_employee_id"], "reviewed": r["reviewed_by_employee_id"],
            "approved": r["approved_by_employee_id"], "props": {
                "title": r["title"], "scope": r["scope"], "version": r["version"], "revision": r["revision"],
                "effective_date": _d(r["effective_date"]), "next_review_date": _d(r["next_review_date"]),
                "objective": r["objective"], "applies_to": r["applies_to"],
                "markdown_file": r["markdown_file"], "pdf_file": r["pdf_file"]}}


def _rule(r: dict[str, str]) -> Row:
    return {"rule_id": r["rule_id"], "policy_id": r["policy_id"], "props": {
        "statement": r["statement"], "applies_to": r["applies_to"],
        "condition": r["condition_or_exception"], "section": r["section"]}}


def _raw(r: dict[str, str]) -> Row:
    return dict(r)


# (csv, row mapper, Cypher). Order matters: nodes before the relationships that MATCH them.
# A relationship whose end id is empty is skipped by MATCH finding nothing.
STEPS: list[tuple[str, Callable[[dict[str, str]], Row], str]] = [
    ("company", _company,
     "UNWIND $rows AS r MERGE (c:Company {company_id: r.company_id}) SET c += r.props"),
    ("locations", _location,
     "UNWIND $rows AS r MERGE (l:Location {location_id: r.location_id}) SET l += r.props "
     "WITH l MATCH (c:Company) MERGE (c)-[:HAS_LOCATION]->(l)"),
    ("bands", _band,
     "UNWIND $rows AS r MERGE (b:Band {band: r.band}) SET b += r.props"),
    ("departments", _department,
     "UNWIND $rows AS r MERGE (d:Department {department_id: r.department_id}) SET d += r.props "
     "WITH d, r MATCH (c:Company) MERGE (c)-[:HAS_DEPARTMENT]->(d) "
     "WITH d, r MATCH (l:Location {location_id: r.location_id}) MERGE (d)-[:LOCATED_AT]->(l)"),
    ("employees", _employee,
     "UNWIND $rows AS r MERGE (e:Employee {employee_id: r.employee_id}) SET e += r.props "
     "WITH e, r MATCH (d:Department {department_id: r.department_id}) MERGE (e)-[:WORKS_IN]->(d) "
     "WITH e, r MATCH (b:Band {band: r.band}) MERGE (e)-[:IN_BAND]->(b) "
     "WITH e, r MATCH (l:Location {location_id: r.location_id}) MERGE (e)-[:BASED_AT]->(l)"),
    ("reporting_lines", _raw,
     "UNWIND $rows AS r MATCH (e:Employee {employee_id: r.employee_id}), "
     "(m:Employee {employee_id: r.manager_employee_id}) MERGE (e)-[:REPORTS_TO]->(m)"),
    ("departments", _raw,
     "UNWIND $rows AS r MATCH (d:Department {department_id: r.department_id}), "
     "(h:Employee {employee_id: r.head_employee_id}) MERGE (h)-[:HEADS]->(d)"),
    ("organizations", _raw,
     "UNWIND $rows AS r MERGE (o:Organization {org_id: r.org_id}) SET o.name = r.name"),
    ("prior_experience", _raw,
     "UNWIND $rows AS r MATCH (e:Employee {employee_id: r.employee_id}), (o:Organization {org_id: r.org_id}) "
     "MERGE (e)-[x:PREVIOUSLY_AT {title: r.title, start: r.start}]->(o) SET x.end = r.end"),
    ("skills", _raw,  # names exactly as in the CSV; alias normalisation is PLAN 2.1
     "UNWIND $rows AS r MERGE (s:Skill {skill_id: r.skill_id}) SET s.name = r.skill"),
    ("employee_skills", _raw,
     "UNWIND $rows AS r MATCH (e:Employee {employee_id: r.employee_id}), (s:Skill {skill_id: r.skill_id}) "
     "MERGE (e)-[:HAS_SKILL]->(s)"),
    ("certifications", _raw,
     "UNWIND $rows AS r MERGE (c:Certification {cert_id: r.cert_id}) SET c.name = r.name"),
    ("employee_certifications", _raw,
     "UNWIND $rows AS r MATCH (e:Employee {employee_id: r.employee_id}), (c:Certification {cert_id: r.cert_id}) "
     "MERGE (e)-[:HOLDS]->(c)"),
    ("products", _product,
     "UNWIND $rows AS r MERGE (p:Product {product_id: r.product_id}) SET p += r.props "
     "WITH p, r MATCH (o:Employee {employee_id: r.owner}) MERGE (o)-[:OWNS_PRODUCT]->(p) "
     "WITH p, r MATCH (l:Employee {employee_id: r.lead}) MERGE (l)-[:LEADS_ENGINEERING_OF]->(p)"),
    ("projects", _project,
     "UNWIND $rows AS r MERGE (p:Project {project_id: r.project_id}) SET p += r.props "
     "WITH p, r MATCH (s:Employee {employee_id: r.sponsor}) MERGE (s)-[:SPONSORS]->(p) "
     "WITH p, r MATCH (l:Employee {employee_id: r.lead}) MERGE (l)-[:LEADS]->(p)"),
    ("project_departments", _raw,
     "UNWIND $rows AS r MATCH (p:Project {project_id: r.project_id}), (d:Department {department_id: r.department_id}) "
     "MERGE (d)-[:CONTRIBUTES_TO]->(p)"),
    ("project_assignments", _assignment,
     "UNWIND $rows AS r MATCH (e:Employee {employee_id: r.employee_id}), (p:Project {project_id: r.project_id}) "
     "MERGE (e)-[w:WORKED_ON]->(p) SET w += r.props"),
    ("policies", _policy,
     "UNWIND $rows AS r MERGE (p:Policy {policy_id: r.policy_id}) SET p += r.props "
     "WITH p, r MATCH (d:Department {department_id: r.owner}) MERGE (p)-[:OWNED_BY]->(d) "
     "WITH p, r MATCH (a:Employee {employee_id: r.prepared}) MERGE (p)-[:PREPARED_BY]->(a) "
     "WITH p, r MATCH (b:Employee {employee_id: r.reviewed}) MERGE (p)-[:REVIEWED_BY]->(b) "
     "WITH p, r MATCH (c:Employee {employee_id: r.approved}) MERGE (p)-[:APPROVED_BY]->(c)"),
    ("policy_applies_to", _raw,
     "UNWIND $rows AS r MATCH (p:Policy {policy_id: r.policy_id}) "
     "OPTIONAL MATCH (c:Company {company_id: r.target_id}) WHERE r.target_type = 'Company' "
     "OPTIONAL MATCH (d:Department {department_id: r.target_id}) WHERE r.target_type = 'Department' "
     "WITH p, coalesce(c, d) AS t WHERE t IS NOT NULL MERGE (p)-[:APPLIES_TO]->(t)"),
    ("policy_references", _raw,
     "UNWIND $rows AS r MATCH (a:Policy {policy_id: r.from_policy_id}), (b:Policy {policy_id: r.to_policy_id}) "
     "MERGE (a)-[:REFERENCES]->(b)"),
    ("policy_rules", _rule,
     "UNWIND $rows AS r MERGE (x:Rule {rule_id: r.rule_id}) SET x += r.props "
     "WITH x, r MATCH (p:Policy {policy_id: r.policy_id}) MERGE (p)-[:DEFINES]->(x)"),
]


def _batches(rows: list[Row], size: int = BATCH) -> Iterable[list[Row]]:
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


def _write(tx: ManagedTransaction, cypher: str, rows: list[Row]) -> None:
    tx.run(cypher, rows=rows).consume()


def load(driver: Driver) -> None:
    """Create constraints, then MERGE every CSV into the graph. Safe to re-run."""
    with driver.session() as session:
        for label, key in CONSTRAINTS.items():
            # Labels and keys come from the constant above, never from user text.
            session.run(
                f"CREATE CONSTRAINT {label.lower()}_{key} IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.{key} IS UNIQUE"
            ).consume()
        for name, mapper, cypher in STEPS:
            rows = [mapper(r) for r in read_csv(name)]
            for batch in _batches(rows):
                session.execute_write(_write, cypher, batch)


def counts(driver: Driver) -> tuple[dict[str, int], dict[str, int]]:
    nodes = run_read(driver, "MATCH (n) UNWIND labels(n) AS label RETURN label, count(*) AS n ORDER BY label")
    rels = run_read(driver, "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS n ORDER BY t")
    return {r["label"]: r["n"] for r in nodes}, {r["t"]: r["n"] for r in rels}


def main() -> None:
    with get_driver() as driver:
        load(driver)
        nodes, rels = counts(driver)
    print(f"Nodes ({sum(nodes.values())}):")
    for k, v in nodes.items():
        print(f"  {k:<15} {v}")
    print(f"Relationships ({sum(rels.values())}):")
    for k, v in rels.items():
        print(f"  {k:<21} {v}")


if __name__ == "__main__":
    main()
