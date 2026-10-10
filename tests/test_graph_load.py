"""Graph load tests (PLAN 1.2). Expected values come from the CSVs; every graph
read goes through run_read (guard + execute_read)."""
from __future__ import annotations

from collections import Counter

import pytest
from neo4j import Driver

from tests import csv_expect as X
from waypoint.graph.db import run_read
from waypoint.graph.guard import UnsafeCypherError
from waypoint.graph.load import load

pytestmark = pytest.mark.neo4j

DERIVED = ("work_mode", "work_mode_reason", "notice_period_days", "tenure_years", "total_experience_years")


def graph_node_counts(driver: Driver) -> dict[str, int]:
    rows = run_read(driver, "MATCH (n) UNWIND labels(n) AS label RETURN label, count(*) AS n")
    return {r["label"]: r["n"] for r in rows}


def graph_rel_counts(driver: Driver) -> dict[str, int]:
    rows = run_read(driver, "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS n")
    return {r["t"]: r["n"] for r in rows}


@pytest.fixture(scope="module")
def graph(driver: Driver) -> Driver:
    load(driver)  # idempotent, so the tests never depend on run order
    return driver


# ---------------------------------------------------------------- structure


def test_node_counts_per_label(graph: Driver) -> None:
    expected = X.node_counts()
    assert sum(expected.values()) == 391
    actual = graph_node_counts(graph)
    for label, count in expected.items():
        assert actual.get(label) == count, label


def test_relationship_counts_per_type(graph: Driver) -> None:
    actual = graph_rel_counts(graph)
    for rel, count in X.rel_counts().items():
        assert actual.get(rel) == count, rel


def test_load_twice_leaves_identical_counts(graph: Driver) -> None:
    before = (graph_node_counts(graph), graph_rel_counts(graph))
    load(graph)
    after = (graph_node_counts(graph), graph_rel_counts(graph))
    assert after == before


def test_every_employee_but_ceo_reports_to_exactly_one_manager(graph: Driver) -> None:
    rows = run_read(
        graph,
        "MATCH (e:Employee) OPTIONAL MATCH (e)-[:REPORTS_TO]->(m:Employee) "
        "RETURN e.employee_id AS id, collect(m.employee_id) AS managers",
    )
    managers = {r["id"]: r["managers"] for r in rows}
    ceo = X.ceo_id()
    assert managers.pop(ceo) == []
    assert managers == {e: [m] for e, m in X.manager_of().items()}


def test_every_department_has_its_head(graph: Driver) -> None:
    rows = run_read(
        graph,
        "MATCH (d:Department) OPTIONAL MATCH (h:Employee)-[:HEADS]->(d) "
        "RETURN d.department_id AS d, collect(h.employee_id) AS heads",
    )
    expected = {r["department_id"]: [r["head_employee_id"]] for r in X.rows("departments")}
    assert {r["d"]: r["heads"] for r in rows} == expected


def test_derived_employee_columns_are_not_graph_facts(graph: Driver) -> None:
    rows = run_read(graph, "MATCH (e:Employee) RETURN keys(e) AS k")
    present = {k for r in rows for k in r["k"]}
    assert present.isdisjoint(DERIVED)
    assert {"employee_id", "name", "join_date", "status"} <= present


def test_run_read_rejects_writes(graph: Driver) -> None:
    with pytest.raises(UnsafeCypherError):
        run_read(graph, "MATCH (e:Employee) SET e.x = 1 RETURN e")


# ---------------------------------------------------------------- ten sanity queries


def test_q1_skip_level_manager_of_sneha(graph: Driver) -> None:
    mgr = X.manager_of()
    expected = mgr[mgr[X.employee_id("Sneha Hegde")]]
    rows = run_read(
        graph,
        "MATCH (:Employee {name: $name})-[:REPORTS_TO*2]->(m:Employee) RETURN m.employee_id AS id",
        {"name": "Sneha Hegde"},
    )
    assert [r["id"] for r in rows] == [expected]


def test_q2_direct_reports_of_meera(graph: Driver) -> None:
    meera = X.employee_id("Meera Subramanian")
    expected = {e for e, m in X.manager_of().items() if m == meera}
    rows = run_read(
        graph,
        "MATCH (e:Employee)-[:REPORTS_TO]->(:Employee {employee_id: $id}) RETURN e.employee_id AS id",
        {"id": meera},
    )
    assert expected and {r["id"] for r in rows} == expected


def test_q3_policies_referencing_pol_004(graph: Driver) -> None:
    expected = {r["from_policy_id"] for r in X.rows("policy_references") if r["to_policy_id"] == "ZEN-POL-004"}
    rows = run_read(
        graph,
        "MATCH (p:Policy)-[:REFERENCES]->(:Policy {policy_id: $id}) RETURN p.policy_id AS id",
        {"id": "ZEN-POL-004"},
    )
    assert expected and {r["id"] for r in rows} == expected


def test_q4_headcount_per_department(graph: Driver) -> None:
    expected = Counter(r["department_id"] for r in X.rows("employees"))
    rows = run_read(
        graph,
        "MATCH (e:Employee)-[:WORKS_IN]->(d:Department) RETURN d.department_id AS d, count(e) AS n",
    )
    assert {r["d"]: r["n"] for r in rows} == expected


def test_q5_project_atlas_team_with_roles(graph: Driver) -> None:
    expected = {(r["employee_id"], r["role"], r["is_current"] == "true")
                for r in X.rows("project_assignments") if r["project_id"] == "PJ01"}
    rows = run_read(
        graph,
        "MATCH (e:Employee)-[w:WORKED_ON]->(:Project {name: $name}) "
        "RETURN e.employee_id AS id, w.role AS role, w.is_current AS cur",
        {"name": "Project Atlas"},
    )
    assert expected and {(r["id"], r["role"], r["cur"]) for r in rows} == expected


def test_q6_previously_at_tessera_cloud(graph: Driver) -> None:
    org = next(r["org_id"] for r in X.rows("organizations") if r["name"] == "Tessera Cloud")
    expected = {r["employee_id"] for r in X.rows("prior_experience") if r["org_id"] == org}
    rows = run_read(
        graph,
        "MATCH (e:Employee)-[:PREVIOUSLY_AT]->(:Organization {name: $name}) RETURN DISTINCT e.employee_id AS id",
        {"name": "Tessera Cloud"},
    )
    assert expected and {r["id"] for r in rows} == expected


def test_q7_rules_defined_by_hybrid_work_policy(graph: Driver) -> None:
    expected = {r["rule_id"] for r in X.rows("policy_rules") if r["policy_id"] == "ZEN-POL-002"}
    rows = run_read(
        graph,
        "MATCH (:Policy {policy_id: $id})-[:DEFINES]->(r:Rule) RETURN r.rule_id AS id",
        {"id": "ZEN-POL-002"},
    )
    assert expected and {r["id"] for r in rows} == expected


def test_q8_policy_owner_and_approver(graph: Driver) -> None:
    expected = {(r["policy_id"], r["owner_department_id"], r["approved_by_employee_id"])
                for r in X.rows("policies")}
    rows = run_read(
        graph,
        "MATCH (d:Department)<-[:OWNED_BY]-(p:Policy)-[:APPROVED_BY]->(a:Employee) "
        "RETURN p.policy_id AS p, d.department_id AS d, a.employee_id AS a",
    )
    assert {(r["p"], r["d"], r["a"]) for r in rows} == expected


def test_q9_policy_applies_to_company_or_department(graph: Driver) -> None:
    expected = {(r["policy_id"], r["target_type"], r["target_id"]) for r in X.rows("policy_applies_to")}
    rows = run_read(
        graph,
        "MATCH (p:Policy)-[:APPLIES_TO]->(t) "
        "RETURN p.policy_id AS p, labels(t)[0] AS type, coalesce(t.company_id, t.department_id) AS id",
    )
    assert {(r["p"], r["type"], r["id"]) for r in rows} == expected


def test_q10_kafka_holders_and_project_leadership(graph: Driver) -> None:
    kafka = next(r["skill_id"] for r in X.rows("skills") if r["skill"] == "Kafka")
    expected_kafka = {r["employee_id"] for r in X.rows("employee_skills") if r["skill_id"] == kafka}
    rows = run_read(
        graph,
        "MATCH (e:Employee)-[:HAS_SKILL]->(:Skill {name: $skill}) RETURN e.employee_id AS id",
        {"skill": "Kafka"},
    )
    assert expected_kafka and {r["id"] for r in rows} == expected_kafka

    expected_proj = {(r["project_id"], r["sponsor_employee_id"], r["lead_employee_id"]) for r in X.rows("projects")}
    rows = run_read(
        graph,
        "MATCH (s:Employee)-[:SPONSORS]->(p:Project)<-[:LEADS]-(l:Employee) "
        "RETURN p.project_id AS p, s.employee_id AS s, l.employee_id AS l",
    )
    assert {(r["p"], r["s"], r["l"]) for r in rows} == expected_proj
