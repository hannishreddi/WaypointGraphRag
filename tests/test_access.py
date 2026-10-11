"""Access filter in the retrieval layer (CLAUDE.md rule 6, PLAN 2.5)."""
from __future__ import annotations

from datetime import date

import pytest
from neo4j import Driver

from waypoint.retrieval.access import filter_hits, search_for_asker, visible
from waypoint.retrieval.plan import Step, run_plan
from waypoint.rules.facts import facts_from_csv

POOJA, POOJA_MGR = "ZV-1031", "ZV-1017"  # on maternity leave; her manager heads Data & AI
TARUN, TARUN_MGR, TARUN_DEPT_HEAD = "ZV-1033", "ZV-1029", "ZV-1011"  # serving notice
HR_HEAD, HR_STAFF = "ZV-1006", "ZV-1019"
PEER = "ZV-1042"  # Arjun Menon, an ordinary colleague
POOJA_LEAVE = "profile:ZV-1031::employee-record::restricted"
TARUN_NOTICE = "profile:ZV-1033::about::restricted"


def hit(subject: str | None, sensitivity: str = "restricted") -> dict:
    return {"chunk_id": f"x:{subject}", "sensitivity": sensitivity, "subject_id": subject}


@pytest.mark.parametrize("asker,ok", [(POOJA, True), (POOJA_MGR, True), (HR_HEAD, True), (HR_STAFF, True),
                                      (PEER, False), (TARUN, False), ("ZV-9999", False)])
def test_pooja_leave_chunk(asker: str, ok: bool) -> None:
    assert visible(hit(POOJA), asker, facts_from_csv()) is ok


@pytest.mark.parametrize("asker,ok", [(TARUN, True), (TARUN_MGR, True), (HR_HEAD, True),
                                      (TARUN_DEPT_HEAD, False),  # skip-level: not the direct manager
                                      ("ZV-1001", False), (PEER, False)])
def test_tarun_notice_chunk(asker: str, ok: bool) -> None:
    assert visible(hit(TARUN), asker, facts_from_csv()) is ok


def test_public_always_and_subjectless_restricted_never() -> None:
    hits = [hit(None, "public"), hit(None), hit(POOJA)]
    assert [h["chunk_id"] for h in filter_hits(hits, PEER)] == ["x:None"]
    assert [h["sensitivity"] for h in filter_hits(hits, HR_HEAD)] == ["public", "restricted"]


class FlatEmbedder:
    def embed_query(self, text: str) -> list[float]:
        return [1.0] * 1024


@pytest.mark.neo4j
@pytest.mark.parametrize("subject,chunk,allowed,denied", [
    (POOJA, POOJA_LEAVE, [POOJA, POOJA_MGR, HR_HEAD], [PEER, TARUN]),
    (TARUN, TARUN_NOTICE, [TARUN, TARUN_MGR, HR_STAFF], [PEER, TARUN_DEPT_HEAD]),
])
def test_search_for_asker(driver: Driver, subject: str, chunk: str, allowed: list[str], denied: list[str]) -> None:
    def ids(asker: str) -> list[str]:
        return [h["chunk_id"] for h in search_for_asker("employment status leave notice", asker, k=30,
                                                         entity_id=subject, driver=driver, embedder=FlatEmbedder())]
    for a in allowed:
        assert chunk in ids(a), a
    for a in denied:
        got = ids(a)
        assert got and not any(c.endswith("::restricted") for c in got), a


@pytest.mark.neo4j
def test_text_search_step_filters_for_the_asker(driver: Driver) -> None:
    plan = [Step(op="text_search", args={"query": "maternity leave", "entity_id": POOJA})]
    kw = {"driver": driver, "as_of": date(2026, 10, 10), "embedder": FlatEmbedder(), "k": 30}
    peer = run_plan(plan, asker_id=PEER, **kw)[0].output
    hr = run_plan(plan, asker_id=HR_HEAD, **kw)[0].output
    assert peer and all(h["sensitivity"] == "public" for h in peer)
    assert POOJA_LEAVE in {h["chunk_id"] for h in hr}
