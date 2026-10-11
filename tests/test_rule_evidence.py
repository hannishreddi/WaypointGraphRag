"""Rule evidence in the subgraph (PLAN 3.2): cited policy sections, the derived RULE_CASE edge,
decisive vs checked fact edges, and node details built from public facts only."""
from __future__ import annotations

from datetime import date

import pytest
from neo4j import Driver

from waypoint.contract import SubgraphEdge
from waypoint.rules.engine import RESTRICTED_ATTRS, evaluate
from waypoint.rules.facts import facts_from_csv

ARJUN, POOJA, TARUN, DIVYA = "ZV-1042", "ZV-1031", "ZV-1033", "ZV-1004"
HR, PEER = "ZV-1006", "ZV-1042"


def edges(r) -> dict[tuple[str, str, str], SubgraphEdge]:
    return {(e.source, e.type, e.target): e for e in r.subgraph.edges}


def node(r, nid: str):
    return next(n for n in r.subgraph.nodes if n.id == nid)


@pytest.mark.parametrize("as_of,case,section,day", [
    (date(2026, 10, 10), "INDUCTION", "ZEN-POL-002#4", 82),
    (date(2026, 10, 18), "INDUCTION", "ZEN-POL-002#4", 90),
    (date(2026, 10, 19), "STANDARD", "ZEN-POL-002#3", 91),
])
def test_arjun_work_mode_evidence_flips(as_of: date, case: str, section: str, day: int) -> None:
    r = evaluate("WORK_MODE", ARJUN, ARJUN, as_of)
    assert r.fired_case == case
    e = edges(r)
    rule_edge = e[(ARJUN, "RULE_CASE", section)]
    assert rule_edge.derived and rule_edge.role == "decisive"
    assert e[("ZEN-POL-002", "HAS_SECTION", section)].derived is False
    assert node(r, section).label == "PolicySection" and node(r, section).name == section.replace("#", " §")
    detail = node(r, ARJUN).detail
    assert f"days_since_join = {day}" in detail and "join_date = 2026-07-20" in detail
    assert f"case {case}" in node(r, section).detail
    # Only the RULE_CASE edge is derived; citations stay the fact edges and the policy section.
    assert [k for k, v in e.items() if v.derived] == [(ARJUN, "RULE_CASE", section)]
    assert all(c.path.count("RULE_CASE") == 0 for c in r.citations if c.type == "graph")


def test_induction_marks_band_checked_not_decisive() -> None:
    r = evaluate("WORK_MODE", ARJUN, ARJUN, date(2026, 10, 10))
    assert edges(r)[(ARJUN, "IN_BAND", "Z2")].role == "checked"
    assert "Decisive: days_since_join = 82 (case needs <= 90)" in node(r, ARJUN).detail


def test_standard_case_says_no_earlier_case_applies() -> None:
    d = node(evaluate("WORK_MODE", ARJUN, ARJUN, date(2026, 10, 19)), ARJUN).detail
    assert "Decisive: no earlier case applies" in d and "days_since_join = 91" in d


@pytest.mark.parametrize("subject", [POOJA, TARUN])
def test_peer_gets_no_subgraph_for_restricted_rules(subject: str) -> None:
    for rule in ("WORK_MODE", "NOTICE_PERIOD"):
        r = evaluate(rule, subject, PEER, date(2026, 10, 10))
        assert r.status == "restricted" and r.subgraph.nodes == [] and r.citations == []


@pytest.mark.parametrize("subject", [POOJA, TARUN])
def test_details_never_carry_restricted_facts_even_for_hr(subject: str) -> None:
    facts = facts_from_csv()
    status = facts.get(subject).status
    r = evaluate("WORK_MODE", subject, HR, date(2026, 10, 10), facts=facts)
    assert r.status == "ok" and r.fired_case in ("ON_LEAVE", "SERVING_NOTICE")
    details = " ".join(n.detail for n in r.subgraph.nodes)
    assert details and status not in details and r.fired_case not in details
    assert not any(a in details for a in RESTRICTED_ATTRS)
    assert "restricted fact" in details


def test_detail_only_on_subject_and_sections() -> None:
    r = evaluate("WORK_MODE", ARJUN, ARJUN, date(2026, 10, 10))
    assert {n.id for n in r.subgraph.nodes if n.detail} == {ARJUN, "ZEN-POL-002#4"}


def test_hypothetical_subject_has_sections_but_no_rule_edge() -> None:
    r = evaluate("WORK_MODE", None, HR, date(2026, 10, 10), {"department_code": "CSC"})
    assert r.fired_case == "CARE_CENTRE_ROSTER"
    assert {n.label for n in r.subgraph.nodes} == {"Policy", "PolicySection"}
    assert not any(e.derived for e in r.subgraph.edges)


@pytest.mark.neo4j
def test_termination_band_is_decisive_and_chain_kept(driver: Driver) -> None:
    r = evaluate("TERMINATION_APPROVAL", DIVYA, HR, date(2026, 10, 10), driver=driver)
    e = edges(r)
    assert r.fired_case == "Z5_AND_ABOVE" and e[(DIVYA, "IN_BAND", "Z5")].role == "decisive"
    assert e[(DIVYA, "RULE_CASE", "ZEN-POL-004#7")].derived
    assert {(DIVYA, "REPORTS_TO", "ZV-1003"), ("ZV-1003", "HEADS", "D03"), (HR, "HEADS", "D01")} <= set(e)
    assert "band = Z5" in node(r, DIVYA).detail


@pytest.mark.neo4j
def test_section_ids_exist_in_the_graph(driver: Driver) -> None:
    ids = [n.id for n in evaluate("WORK_MODE", ARJUN, ARJUN, date(2026, 10, 10)).subgraph.nodes
           if n.label == "PolicySection"]
    with driver.session() as s:
        found = s.run("MATCH (p:PolicySection) WHERE p.section_id IN $ids RETURN p.section_id AS id", ids=ids).value()
    assert sorted(found) == sorted(ids)
