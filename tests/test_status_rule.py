"""3.3c F2/F3: EMPLOYMENT_STATUS, a restricted record rule. Rule 6 is enforced in the
engine (subject, direct manager, HR); values and dates come from the subject's base
`status` fact; citations are the subject's restricted record chunk (where the status line
is written) plus the policy section that governs the status, where one exists.
Offline: CSV facts, no Neo4j, no LLM."""
from __future__ import annotations

import re
from datetime import date

import pytest

from waypoint.contract import ChunkCitation, PolicyCitation
from waypoint.retrieval.chunking import build_corpus
from waypoint.rules import derived as Dv
from waypoint.rules.engine import RESTRICTED_ATTRS, can_see_restricted, evaluate, load_rules, record_chunk_id
from waypoint.rules.facts import facts_from_csv

AS_OF = date(2026, 10, 10)
FACTS = facts_from_csv()
HR = "ZV-1006"
BY_CAT = {c: next(e for e, f in FACTS.items() if Dv.status_category(f.status) == c
          and f.manager_id and FACTS[f.manager_id].manager_id)  # has a manager and a skip-level
          for c in ("on_leave", "serving_notice", "active")}


def _dates(status: str) -> list[date]:
    import datetime as dt

    return [dt.datetime.strptime(d, "%d %b %Y").date() for d in re.findall(r"\d{1,2} \w{3} \d{4}", status)]


def test_rule_is_restricted_and_a_record_rule() -> None:
    r = load_rules()["EMPLOYMENT_STATUS"]
    assert r.restricted and r.record
    assert [c.id for c in r.cases] == ["ON_LEAVE", "SERVING_NOTICE", "ACTIVE"]


def test_status_dates_parse_for_every_employee() -> None:
    for f in FACTS.values():
        d = Dv.status_dates(f.status)
        cat = Dv.status_category(f.status)
        if cat == "on_leave":
            assert [d["leave_start"], d["leave_end"]] == _dates(f.status), f.employee_id
        elif cat == "serving_notice":
            assert [d["resignation_date"], d["last_working_day"]] == _dates(f.status), f.employee_id
        else:
            assert d == {}, f.employee_id
    assert {"leave_start", "leave_end", "resignation_date", "last_working_day"} <= RESTRICTED_ATTRS


@pytest.mark.parametrize("cat,fields", [
    ("on_leave", ("leave_start", "leave_end")),
    ("serving_notice", ("resignation_date", "last_working_day")),
    ("active", ()),
])
def test_self_gets_the_status_with_citations(cat: str, fields: tuple[str, ...]) -> None:
    eid = BY_CAT[cat]
    r = evaluate("EMPLOYMENT_STATUS", eid, eid, AS_OF)
    assert r.status == "ok" and r.value["employment_status"] == FACTS[eid].status
    for f, d in zip(fields, _dates(FACTS[eid].status)):
        assert r.value[f] == Dv.fmt_date(d)
    assert ChunkCitation(id=record_chunk_id(eid)) in r.citations
    if cat != "active":  # the governing policy section; Active has none, only the record
        assert any(isinstance(c, PolicyCitation) and c.id == "ZEN-POL-003" for c in r.citations)


def test_record_chunk_holds_the_status_line() -> None:
    chunks = {c.chunk_id: c for c in build_corpus().chunks}
    for eid, f in FACTS.items():
        c = chunks[record_chunk_id(eid)]
        assert c.sensitivity == "restricted" and c.subject_id == eid
        assert f.status in c.body, eid


def test_rule6_in_the_engine() -> None:
    for eid in BY_CAT.values():
        s = FACTS[eid]
        allowed = [eid, s.manager_id, HR]
        skip = FACTS[s.manager_id].manager_id
        peer = next(e for e, f in FACTS.items() if e not in allowed and e != skip
                    and f.department_code != "HR" and not can_see_restricted(eid, e, FACTS))
        for asker in allowed:
            assert evaluate("EMPLOYMENT_STATUS", eid, asker, AS_OF).status == "ok", (eid, asker)
        for asker in (peer, skip):
            r = evaluate("EMPLOYMENT_STATUS", eid, asker, AS_OF)
            assert r.status == "restricted" and not r.value and not r.citations and not r.inputs, (eid, asker)
            assert not r.subgraph.nodes and not r.subgraph.edges


def test_restricted_result_is_identical_for_every_subject() -> None:
    peer = "ZV-1020"
    dumps = []
    for eid in BY_CAT.values():
        assert not can_see_restricted(eid, peer, FACTS)
        d = evaluate("EMPLOYMENT_STATUS", eid, peer, AS_OF).model_dump()
        d.pop("subject_id")
        dumps.append(d)
    assert dumps[0] == dumps[1] == dumps[2]


def test_subgraph_details_never_show_status_or_dates() -> None:
    for eid in BY_CAT.values():
        r = evaluate("EMPLOYMENT_STATUS", eid, HR, AS_OF)
        text = r.subgraph.model_dump_json().lower()
        assert FACTS[eid].status.lower() not in text
        for d in _dates(FACTS[eid].status):
            assert Dv.fmt_date(d).lower() not in text and d.isoformat() not in text
