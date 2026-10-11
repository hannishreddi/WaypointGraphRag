"""Cypher templates (PLAN 2.2). Graph tests use dev questions only (rule 2); templates with no
dev question are checked against the CSVs and say so."""
from __future__ import annotations

import json
import re
from functools import cache

import pytest

from waypoint.graph import templates as T
from waypoint.graph.guard import check_read_only
from waypoint.graph.load import read_csv
from waypoint.eval.questions import Question, load_questions
from waypoint.retrieval.aliases import skill_variants
from waypoint.retrieval.linking import link_entities


# ---------------------------------------------------------------- static, no Neo4j

@pytest.mark.parametrize("name", sorted(T.QUERIES))
def test_query_is_read_only_ordered_and_never_touches_chunks(name: str) -> None:
    cypher = T.QUERIES[name]
    check_read_only(cypher)
    assert "Chunk" not in cypher
    assert "ORDER BY" in cypher
    assert "$" in cypher  # parameterised


def test_no_hard_coded_entity_ids_in_queries() -> None:
    ids = re.compile(r"\b(?:ZV-\d{4}|D\d{2}|PJ\d{2}|PR\d{2}|L\d{2}|ORG\d{3}|SK\d{3}|ZEN-[A-Z]+-[\w-]+)\b")
    for name, cypher in T.QUERIES.items():
        assert not ids.search(cypher), name


def test_paths_follow_relationship_direction() -> None:
    edges = [{"source": "ZV-1", "type": "REPORTS_TO", "target": "ZV-2"},
             {"source": "ZV-2", "type": "REPORTS_TO", "target": "ZV-3"},
             {"source": "ZV-1", "type": "WORKS_IN", "target": "D01"}]
    assert T.edge_paths(edges) == ["ZV-1 -REPORTS_TO-> ZV-2 -REPORTS_TO-> ZV-3", "ZV-1 -WORKS_IN-> D01"]


# ---------------------------------------------------------------- helpers for graph tests

@cache
def dev() -> dict[str, Question]:
    return {q.id: q for q in load_questions("dev")}


def linked(qid: str, label: str, n: int = 0) -> str:
    return [m.id for m in link_entities(dev()[qid].question) if m.label == label][n]


def gold_names(qid: str) -> set[str]:
    return {re.sub(r"\s*\(.*\)$", "", s).strip() for s in dev()[qid].expected_answer.split(";")}


def names(result: T.TemplateResult, key: str = "name") -> set[str]:
    return {r[key] for r in result.rows}


def no_status(result: T.TemplateResult) -> None:
    """Employment status is restricted (rule 6): templates never return it."""
    dumped = json.dumps(result.rows, default=str)
    assert '"status"' not in dumped and "Serving notice" not in dumped and "maternity" not in dumped


def evidence_ok(result: T.TemplateResult) -> None:
    node_ids = {n.id for n in result.subgraph.nodes}
    for e in result.subgraph.edges:
        assert e.source in node_ids and e.target in node_ids
    for p in result.paths:
        for token in re.findall(r"[^\s]+", p):
            if not token.startswith("-"):
                assert token in node_ids, (p, token)
    assert result.paths, "every non-empty result cites at least one graph path"
    no_status(result)


# ---------------------------------------------------------------- one test per template

@pytest.mark.neo4j
def test_manager_q002(driver) -> None:
    r = T.manager(driver, linked("Q002", "Employee"))
    assert names(r) == gold_names("Q002")
    assert r.paths == ["ZV-1004 -REPORTS_TO-> ZV-1003"]
    evidence_ok(r)


@pytest.mark.neo4j
def test_direct_reports_q062(driver) -> None:
    r = T.direct_reports(driver, linked("Q062", "Employee"))
    assert names(r) == gold_names("Q062")
    evidence_ok(r)


@pytest.mark.neo4j
def test_skip_manager_q083(driver) -> None:
    r = T.skip_manager(driver, linked("Q083", "Employee"))
    assert names(r) == gold_names("Q083")
    assert len(r.paths) == 1 and r.paths[0].count("-REPORTS_TO->") == 2
    evidence_ok(r)


@pytest.mark.neo4j
def test_department_head_q042(driver) -> None:
    r = T.department_head(driver, linked("Q042", "Department"))
    assert names(r) == gold_names("Q042")
    evidence_ok(r)


@pytest.mark.neo4j
@pytest.mark.parametrize("qid", ["Q047", "Q049", "Q053"])
def test_headcount_counts_every_status(driver, qid: str) -> None:
    r = T.headcount(driver, linked(qid, "Department"))
    [row] = r.rows
    assert row["headcount"] == int(dev()[qid].expected_answer)
    assert len(row["members"]) == row["headcount"]
    evidence_ok(r)


@pytest.mark.neo4j
def test_headcount_gold_includes_non_active_employees(driver) -> None:
    """Gold counts every WORKS_IN regardless of status: D05 = 4 includes the colleague on leave,
    D08 = 4 includes the one serving notice (checked against employees.csv, status not exposed)."""
    emps = read_csv("employees")
    for qid in ("Q047", "Q053"):
        did = linked(qid, "Department")
        members = [e for e in emps if e["department_id"] == did]
        assert len(members) == int(dev()[qid].expected_answer)
        assert any(e["status"] != "Active" for e in members)
        assert T.headcount(driver, did).rows[0]["headcount"] == len(members)


@pytest.mark.neo4j
def test_employee_card_q024(driver) -> None:
    r = T.employee_card(driver, linked("Q024", "Employee"))
    [row] = r.rows
    assert f"{row['title']}, band {row['band']}" == dev()["Q024"].expected_answer
    assert row["department_id"] and row["location_id"] and row["join_date"]
    evidence_ok(r)


@pytest.mark.neo4j
def test_project_team_location_filter_q122(driver) -> None:
    r = T.project_team(driver, linked("Q122", "Project"), location_id=linked("Q122", "Location"))
    assert names(r) == gold_names("Q122")
    assert any("-BASED_AT->" in p for p in r.paths)
    evidence_ok(r)


@pytest.mark.neo4j
def test_project_team_reports_to_filter_q129(driver) -> None:
    r = T.project_team(driver, linked("Q129", "Project"), reports_to=linked("Q129", "Employee"))
    assert names(r) == gold_names("Q129")
    evidence_ok(r)


@pytest.mark.neo4j
def test_project_team_role_and_current_filters_csv(driver) -> None:
    """No dev question filters by role or currency: expectation from project_assignments.csv."""
    rows = read_csv("project_assignments")
    emp = {e["employee_id"]: e["full_name"] for e in read_csv("employees")}
    for proj in read_csv("projects"):
        for flag in (True, False):
            want = {emp[a["employee_id"]] for a in rows
                    if a["project_id"] == proj["project_id"] and (a["is_current"] == "true") == flag}
            assert names(T.project_team(driver, proj["project_id"], current=flag)) == want
    pid = "PJ09"
    role = next(a["role"] for a in rows if a["project_id"] == pid)
    word = role.split()[0]
    want = {emp[a["employee_id"]] for a in rows if a["project_id"] == pid and word.lower() in a["role"].lower()}
    assert names(T.project_team(driver, pid, role=word)) == want
    everyone = {emp[a["employee_id"]] for a in rows if a["project_id"] == pid}
    assert names(T.project_team(driver, pid)) == everyone


@pytest.mark.neo4j
def test_projects_of_q096(driver) -> None:
    r = T.projects_of(driver, linked("Q096", "Employee"))
    assert names(r, "project") == gold_names("Q096")
    evidence_ok(r)


@pytest.mark.neo4j
def test_project_leadership_q119(driver) -> None:
    r = T.project_leadership(driver, linked("Q119", "Project"))
    got = {(row["relation"], row["name"]) for row in r.rows}
    gold = dict(part.split(": ") for part in dev()["Q119"].expected_answer.rstrip(".").split(". "))
    assert got == {("SPONSORS", gold["Sponsor"]), ("LEADS", gold["Lead"])}
    evidence_ok(r)


@pytest.mark.neo4j
def test_product_leadership_csv(driver) -> None:
    """No dev question about product owners: expectation from products.csv."""
    emp = {e["employee_id"]: e["full_name"] for e in read_csv("employees")}
    for p in read_csv("products"):
        r = T.project_leadership(driver, p["product_id"])
        got = {(row["relation"], row["name"]) for row in r.rows}
        assert got == {("OWNS_PRODUCT", emp[p["owner_employee_id"]]),
                       ("LEADS_ENGINEERING_OF", emp[p["lead_employee_id"]])}
        evidence_ok(r)


@pytest.mark.neo4j
def test_project_departments_q104(driver) -> None:
    r = T.project_departments(driver, linked("Q104", "Project"))
    assert names(r) == gold_names("Q104")
    evidence_ok(r)


@pytest.mark.neo4j
def test_previous_employer_q133(driver) -> None:
    r = T.previous_employer(driver, linked("Q133", "Organization"))
    assert names(r) == gold_names("Q133")
    evidence_ok(r)


@pytest.mark.neo4j
def test_employers_of_csv(driver) -> None:
    """No dev question lists one person's employers: expectation from prior_experience.csv."""
    orgs = {o["org_id"]: o["name"] for o in read_csv("organizations")}
    eid = "ZV-1001"
    want = {orgs[p["org_id"]] for p in read_csv("prior_experience") if p["employee_id"] == eid}
    r = T.employers_of(driver, eid)
    assert names(r, "organization") == want
    evidence_ok(r)


@pytest.mark.neo4j
def test_skill_holders_literal_q153(driver) -> None:
    r = T.skill_holders(driver, linked("Q153", "Skill"))
    assert names(r) == gold_names("Q153")
    evidence_ok(r)


@pytest.mark.neo4j
def test_skill_holders_expanded_variants_csv(driver) -> None:
    """Expansion has no dev question: expectation from employee_skills.csv."""
    py = next(s["skill_id"] for s in read_csv("skills") if s["skill"] == "Python")
    group = skill_variants(py)
    emp = {e["employee_id"]: e["full_name"] for e in read_csv("employees")}
    holders = read_csv("employee_skills")
    literal = {emp[h["employee_id"]] for h in holders if h["skill_id"] == py}
    expanded = {emp[h["employee_id"]] for h in holders if h["skill_id"] in group}
    assert names(T.skill_holders(driver, py)) == literal
    r = T.skill_holders(driver, py, expand_variants=True)
    assert names(r) == expanded and expanded > literal
    evidence_ok(r)


@pytest.mark.neo4j
def test_policy_owner_csv(driver) -> None:
    """No dev question about policy owners: expectation from policies.csv."""
    p = next(r for r in read_csv("policies") if r["policy_id"] == "ZEN-POL-002")
    r = T.policy_owner(driver, p["policy_id"])
    got = {(row["relation"], row["id"]) for row in r.rows}
    assert got == {("OWNED_BY", p["owner_department_id"]), ("PREPARED_BY", p["prepared_by_employee_id"]),
                   ("REVIEWED_BY", p["reviewed_by_employee_id"]), ("APPROVED_BY", p["approved_by_employee_id"])}
    evidence_ok(r)


@pytest.mark.neo4j
def test_policy_references_in_q239(driver) -> None:
    pol = linked("Q239", "Policy")
    r = T.policy_references(driver, pol, direction="in")
    assert {row["policy_id"] for row in r.rows} == set(dev()["Q239"].sources)
    assert all(p.endswith(f"-REFERENCES-> {pol}") for p in r.paths)
    evidence_ok(r)


@pytest.mark.neo4j
def test_policy_references_out_csv(driver) -> None:
    """Outbound has no dev question: expectation from policy_references.csv."""
    refs = read_csv("policy_references")
    pol = refs[0]["from_policy_id"]
    want = {x["to_policy_id"] for x in refs if x["from_policy_id"] == pol}
    r = T.policy_references(driver, pol, direction="out")
    assert {row["policy_id"] for row in r.rows} == want
    evidence_ok(r)
    with pytest.raises(ValueError):
        T.policy_references(driver, pol, direction="sideways")


@pytest.mark.neo4j
def test_location_roster_csv(driver) -> None:
    """No dev question lists a whole location: expectation from employees.csv."""
    for loc in read_csv("locations"):
        want = {e["full_name"] for e in read_csv("employees") if e["location_id"] == loc["location_id"]}
        r = T.location_roster(driver, loc["location_id"])
        assert names(r) == want
        if want:
            evidence_ok(r)


@pytest.mark.neo4j
def test_approvals_chain_csv(driver) -> None:
    """No dev question asks for an approval chain: CEO = the employee with no manager, HR head =
    head of the department with code HR, both from the CSVs (nothing hard-coded in the template)."""
    emps = {e["employee_id"]: e for e in read_csv("employees")}
    depts = read_csv("departments")
    ceo = next(e for e in emps.values() if not e["manager_employee_id"])["employee_id"]
    hr_head = next(d["head_employee_id"] for d in depts if d["code"] == "HR")
    for eid in ("ZV-1004", "ZV-1042", ceo):
        chain = [eid]
        while emps[chain[-1]]["manager_employee_id"]:
            chain.append(emps[chain[-1]]["manager_employee_id"])
        dept_head = next(d["head_employee_id"] for d in depts if d["department_id"] == emps[eid]["department_id"])
        r = T.approvals_chain(driver, eid)
        [row] = r.rows
        assert [c["employee_id"] for c in row["chain"]] == chain
        assert [c["band"] for c in row["chain"]] == [emps[c]["band"] for c in chain]
        assert row["ceo"]["employee_id"] == ceo
        assert row["hr_head"]["employee_id"] == hr_head
        assert row["department_head"]["employee_id"] == dept_head
        evidence_ok(r)


@pytest.mark.neo4j
def test_unknown_id_returns_empty(driver) -> None:
    r = T.manager(driver, "ZV-0000")
    assert r.rows == [] and r.paths == [] and r.subgraph.nodes == []
