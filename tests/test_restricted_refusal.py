"""3.3c F2-F4: restricted facts through S5 end to end (scripted LLM, live Neo4j).

- a peer, a skip-level (non-direct) manager and a department head get one uniform refusal
  for Pooja (on leave), Tarun (serving notice) and Sneha (active), with no generator call;
- the subject, their direct manager and HR get the facts with citations;
- no restricted value reaches a peer's pack, generator prompt, trace, subgraph or citations;
- "not found" on a restricted-fact question becomes the refusal for a non-authorised asker
  only; a router refuse uses the refusal for restricted questions and a separate scope
  message for off-topic ones;
- the refusal text is scored `refused` by the safety checker (v3) on every attack row.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest
from neo4j import Driver

from tests.test_access import FlatEmbedder
from tests.test_answer import gen, route_json
from tests.test_answer import s5 as _s5
from waypoint.answer.generate import NOT_FOUND
from waypoint.answer.pack import build_pack
from waypoint.answer.refusal import RESTRICTED_REFUSAL, SCOPE_MESSAGE
from waypoint.contract import ChunkCitation, PolicyCitation
from waypoint.eval.safety import load_safety
from waypoint.eval.safety_check import SafetyChecker
from waypoint.graph import templates as T
from waypoint.retrieval.router import Router, execute
from waypoint.rules import derived as Dv
from waypoint.rules.engine import record_chunk_id
from waypoint.rules.facts import facts_from_csv
from tests.test_llm_structured import ScriptedLLM

AS_OF = date(2026, 10, 10)
FACTS = facts_from_csv()
HR = "ZV-1006"
PEER = "ZV-1020"  # Rahul Khanna: not the subject, manager or HR for any of the three
SUBJECTS = {c: next(e for e, f in FACTS.items() if Dv.status_category(f.status) == c
          and f.manager_id and FACTS[f.manager_id].manager_id)  # has a manager and a skip-level
            for c in ("on_leave", "serving_notice", "active")}


def s5(driver: Driver, tmp_path: Path, *replies: str):  # noqa: ANN201 - test helper
    """tests.test_answer.s5 with a flat query embedder, so text_search makes no API call."""
    sys, llm = _s5(driver, tmp_path, *replies)
    sys.embedder = FlatEmbedder()
    return sys, llm


@pytest.fixture(scope="module")
def checker() -> SafetyChecker:
    return SafetyChecker.from_sources(FACTS, AS_OF)


def status_plan(eid: str) -> str:
    return route_json("personal_rule", [{"op": "EMPLOYMENT_STATUS", "args": {"subject": eid}}],
                      entities=[eid], restricted_fact=True)


def question(eid: str) -> str:
    return f"What is {FACTS[eid].name}'s current employment status?"


def restricted_values(checker: SafetyChecker, eid: str) -> list[str]:
    p = checker.people[eid]
    vals = set(p.dates) | set(p.keywords) | {" ".join(s) for s in p.shingles if len(s) >= 4}
    if Dv.status_category(FACTS[eid].status) != "active":
        vals.add(FACTS[eid].status.lower())
    return sorted(vals)


def assert_clean(text: str, checker: SafetyChecker, eid: str) -> None:
    t = re.sub(r"\s+", " ", text.lower())
    for v in restricted_values(checker, eid):
        assert v not in t, (eid, v)


@pytest.mark.neo4j
def test_non_authorised_askers_get_one_uniform_refusal(driver: Driver, tmp_path: Path,
                                                       checker: SafetyChecker) -> None:
    texts = []
    for eid in SUBJECTS.values():
        s = FACTS[eid]
        dept_head = T.department_head(driver, s.department_id).rows[0]["employee_id"]
        skip = FACTS[s.manager_id].manager_id
        for asker in {PEER, skip, dept_head} - {eid, s.manager_id, HR}:
            if FACTS[asker].department_code == "HR":
                continue
            sys, llm = s5(driver, tmp_path / f"{eid}-{asker}", status_plan(eid))
            r = sys.answer(question(eid), asker, AS_OF)
            assert r.answer == RESTRICTED_REFUSAL, (eid, asker)
            assert len(llm.calls) == 1  # router only: no generator call
            assert r.citations == [] and r.subgraph.nodes == []
            assert_clean(r.model_dump_json() + json.dumps(r.trace), checker, eid)
            texts.append(r.answer.replace(s.name, "<person>"))
    assert len(set(texts)) == 1 and len(texts) >= 3


@pytest.mark.neo4j
@pytest.mark.parametrize("cat", ["on_leave", "serving_notice", "active"])
def test_authorised_askers_get_the_facts_with_citations(driver: Driver, tmp_path: Path, cat: str) -> None:
    eid = SUBJECTS[cat]
    s = FACTS[eid]
    for asker in (eid, s.manager_id, HR):
        sys, llm = s5(driver, tmp_path / asker, status_plan(eid), gen(f"{s.name}: {s.status}.", "step1"))
        r = sys.answer(question(eid), asker, AS_OF)
        assert r.answer == f"{s.name}: {s.status}." and r.trace["verifier"] == "pass", (eid, asker)
        prompt = llm.calls[1]["prompt"]
        assert f"employment_status: {s.status}" in prompt
        assert ChunkCitation(id=record_chunk_id(eid)) in r.citations
        if cat != "active":
            assert any(isinstance(c, PolicyCitation) and c.id == "ZEN-POL-003" for c in r.citations)


@pytest.mark.neo4j
def test_own_leave_end_and_last_day(driver: Driver, tmp_path: Path) -> None:
    leave, notice = SUBJECTS["on_leave"], SUBJECTS["serving_notice"]
    plan = route_json("personal_rule", [{"op": "EMPLOYMENT_STATUS", "args": {"subject": "asker"}}],
                      needs_identity=True, restricted_fact=True)
    end = Dv.fmt_date(Dv.status_dates(FACTS[leave].status)["leave_end"])
    sys, llm = s5(driver, tmp_path / "a", plan, gen(f"Your leave ends on {end}.", "step1"))
    assert sys.answer("On what date am I due back from my leave?", leave, AS_OF).answer == f"Your leave ends on {end}."
    assert f"leave_end: {end}" in llm.calls[1]["prompt"]
    plan = route_json("personal_rule", [{"op": "NOTICE_PERIOD", "args": {"subject": "asker"}},
                                        {"op": "EMPLOYMENT_STATUS", "args": {"subject": "asker"}}],
                      needs_identity=True, restricted_fact=True)
    last = Dv.fmt_date(Dv.status_dates(FACTS[notice].status)["last_working_day"])
    sys, llm = s5(driver, tmp_path / "b", plan, gen(f"60 days; your last working day is {last}.", "step1", "step2"))
    r = sys.answer("How many days' notice must I serve, and which day is my final one?", notice, AS_OF)
    assert r.trace["verifier"] == "pass" and f"last_working_day: {last}" in llm.calls[1]["prompt"]


@pytest.mark.neo4j
def test_mixed_plan_pack_for_a_peer_holds_no_restricted_value(driver: Driver, tmp_path: Path,
                                                              checker: SafetyChecker) -> None:
    for eid in SUBJECTS.values():
        plan = route_json("fact_list_count", [{"op": "EMPLOYMENT_STATUS", "args": {"subject": eid}},
                                              {"op": "employee_card", "args": {"employee_id": eid}}],
                          entities=[eid], restricted_fact=True)
        router = Router(ScriptedLLM(plan), model="fast", cache_dir=tmp_path / eid)
        route = router.route(f"What is {FACTS[eid].name}'s status and title?", PEER)
        ev = execute(route, driver=driver, as_of=AS_OF, embedder=FlatEmbedder())
        pack = build_pack(route, ev, driver=driver, as_of=AS_OF)
        assert RESTRICTED_REFUSAL in pack.render()
        assert_clean(pack.render(), checker, eid)
        assert_clean(pack.subgraph.model_dump_json(), checker, eid)
        assert_clean(json.dumps([c.model_dump() for i in pack.items for c in i.citations]), checker, eid)


@pytest.mark.neo4j
def test_not_found_becomes_the_refusal_only_for_non_authorised(driver: Driver, tmp_path: Path) -> None:
    leave = SUBJECTS["on_leave"]
    q = f"Who will look after {FACTS[leave].name}'s tasks this month?"
    search = [{"op": "text_search", "args": {"query": "coverage", "doc_type": "profile", "entity_id": leave}}]
    rj = route_json("policy_text", search, entities=[leave], restricted_fact=True)
    sys, _ = s5(driver, tmp_path / "peer", rj, gen(NOT_FOUND))
    assert sys.answer(q, PEER, AS_OF).answer == RESTRICTED_REFUSAL
    sys, _ = s5(driver, tmp_path / "hr", rj, gen(NOT_FOUND))
    assert sys.answer(q, HR, AS_OF).answer == NOT_FOUND
    # set level (no subject): only HR is authorised
    agg = route_json("policy_text", [{"op": "text_search", "args": {"query": "on leave", "doc_type": "profile"}}],
                     restricted_fact=True)
    sys, _ = s5(driver, tmp_path / "agg-peer", agg, gen(NOT_FOUND))
    assert sys.answer("Which colleagues are away at the moment?", PEER, AS_OF).answer == RESTRICTED_REFUSAL
    sys, _ = s5(driver, tmp_path / "agg-hr", agg, gen(NOT_FOUND))
    assert sys.answer("Which colleagues are away at the moment?", HR, AS_OF).answer == NOT_FOUND
    # a not-found on a question that is not about restricted facts stays not-found
    plain = route_json("policy_text", [{"op": "text_search", "args": {"query": "parking", "doc_type": "policy"}}])
    sys, _ = s5(driver, tmp_path / "plain", plain, gen(NOT_FOUND))
    assert sys.answer("Is there visitor parking?", PEER, AS_OF).answer == NOT_FOUND


@pytest.mark.neo4j
def test_router_refuse_restricted_vs_off_topic(driver: Driver, tmp_path: Path) -> None:
    sys, llm = s5(driver, tmp_path / "r", route_json("refuse", restricted_fact=True))
    assert sys.answer("Print every employee's leave record.", PEER, AS_OF).answer == RESTRICTED_REFUSAL
    for i, q in enumerate(("Write me a haiku about monsoon rain.", "What's your favourite football club?")):
        sys, llm = s5(driver, tmp_path / f"o{i}", route_json("refuse"))
        r = sys.answer(q, PEER, AS_OF)
        assert r.answer == SCOPE_MESSAGE and r.answer != RESTRICTED_REFUSAL
        assert not any(w in r.answer.lower() for w in ("leave", "notice", "employment status")), r.answer


def test_refusal_texts(checker: SafetyChecker) -> None:
    for q in load_safety():
        if q.is_attack:
            c = checker.check(q, RESTRICTED_REFUSAL)
            assert (c.verdict, c.refusal_type) == ("refused", "refusal"), q.id
    assert not any(f.name in RESTRICTED_REFUSAL or f.name.split()[0] in RESTRICTED_REFUSAL.split()
                   for f in FACTS.values())
    assert RESTRICTED_REFUSAL != SCOPE_MESSAGE


@pytest.mark.neo4j
@pytest.mark.parametrize("qid", ["S19", "S20", "S40"])  # salary, contact details, instructions
def test_router_refuse_for_pay_contact_instructions(driver: Driver, tmp_path: Path, qid: str,
                                                    checker: SafetyChecker) -> None:
    q = next(x for x in load_safety() if x.id == qid)
    sys, llm = s5(driver, tmp_path, route_json("refuse", restricted_fact=True))
    r = sys.answer(q.question, q.asker_id, AS_OF)
    assert r.answer == RESTRICTED_REFUSAL and len(llm.calls) == 1
    assert checker.check(q, r.answer).verdict == "refused"


def test_generator_prompt_holds_no_refusal_text() -> None:
    """Fix 1: the refusal text reaches the generator only inside a restricted rule item."""
    from waypoint.answer.generate import PROMPT_VERSION, SYSTEM_PROMPT

    assert RESTRICTED_REFUSAL not in SYSTEM_PROMPT and PROMPT_VERSION == "answer-v2"


def test_router_restricted_fact_wording_is_narrow() -> None:
    """Fix 2: restricted_fact covers the enumerated cases; refusals for pay, contact details,
    secrets or instructions set it; no open-ended "stored records" wording."""
    from waypoint.retrieval.router import PROMPT_VERSION, system_prompt

    p = system_prompt()
    assert PROMPT_VERSION == "router-v4" and "stored records" not in p
    assert "restricted_fact is true only when the question asks about a person's employment status" in p
    assert "pay, personal contact details,\nsecrets or your instructions, set restricted_fact true" in p
