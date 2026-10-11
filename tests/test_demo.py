"""The four 3.2 demo moments through the API, with a scripted LLM and live Neo4j.

The router reply and the answer text are scripted; what is real is everything in between:
linking, plan validation, templates, the rule engine at each as-of, the access filter,
the pack, the verifier and the response contract the page draws.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from neo4j import Driver

from tests.test_llm_structured import ScriptedLLM
from waypoint.answer.system import S5Waypoint
from waypoint.api.app import create_app
from waypoint.api.cache import AnswerCache
from waypoint.retrieval.router import Router
from waypoint.rules.facts import facts_from_csv

pytestmark = pytest.mark.neo4j

ARJUN, POOJA, POOJA_MGR, HR, MEERA, DIVYA = "ZV-1042", "ZV-1031", "ZV-1017", "ZV-1006", "ZV-1002", "ZV-1004"
PEER = "ZV-1020"
POOJA_LEAVE = "profile:ZV-1031::employee-record::restricted"
MEERA_REPORTS = {"ZV-1017", "ZV-1007", "ZV-1010", "ZV-1003", "ZV-1012", "ZV-1005"}


class ChunkEmbedder:
    """Query embedding = a stored chunk's embedding, so that chunk ranks first if visible."""

    def __init__(self, vector: list[float]) -> None:
        self.vector = vector

    def embed_query(self, text: str) -> list[float]:
        return self.vector


def run(driver: Driver, tmp_path: Path, body: dict, route: dict, answer: str, *cited: str,
        embedder: object = None) -> tuple[dict, ScriptedLLM]:
    route = {"entities": [], "needs_identity": False, "confidence": 0.95, **route}
    llm = ScriptedLLM(json.dumps(route), json.dumps({"answer": answer, "cited_ids": list(cited)}))
    system = S5Waypoint(llm, model_answer="answer", model_fast="fast", driver=driver, embedder=embedder,
                        router=Router(llm, model="fast", cache_dir=tmp_path / "router"))
    client = TestClient(create_app(system=system, cache=AnswerCache(tmp_path / "answers")),
                        raise_server_exceptions=False)
    r = client.post("/ask?fresh=1", json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["answer"] == answer, "verifier rejected the scripted answer"
    return out, llm


def edge_set(resp: dict) -> set[tuple[str, str, str]]:
    return {(e["source"], e["type"], e["target"]) for e in resp["subgraph"]["edges"]}


def assert_cited_paths_drawable(resp: dict) -> int:
    """Every edge of every cited graph path is in the subgraph: what the page highlights."""
    edges, n = edge_set(resp), 0
    for c in resp["citations"]:
        if c["type"] != "graph":
            continue
        parts = c["path"].split(" ")
        for i in range(0, len(parts) - 2, 2):
            assert (parts[i], parts[i + 1][1:-2], parts[i + 2]) in edges, c["path"]
            n += 1
    return n


def restricted_values(subject: str) -> list[str]:
    return [facts_from_csv().get(subject).status]


# ---------------------------------------------------------------- 1. Arjun's office days flip

ARJUN_ROUTE = {"intent": "personal_rule", "needs_identity": True,
               "plan": [{"op": "WORK_MODE", "args": {"subject": "asker"}}]}


@pytest.mark.parametrize("as_of,case,section,answer", [
    ("2026-10-10", "INDUCTION", 4, "Yes. You are in induction, so you work from the office on all working days."),
    ("2026-10-18", "INDUCTION", 4, "Yes. You are in induction, so you work from the office on all working days."),
    ("2026-10-19", "STANDARD", 3, "No. Your induction is over; you are hybrid with 3 days a week in the office."),
])
def test_moment1_arjun_office_days_flip(driver: Driver, tmp_path: Path, as_of: str, case: str, section: int,
                                        answer: str) -> None:
    body = {"question": "Do I need to come to the office every day?", "asker_id": ARJUN, "as_of": as_of}
    resp, llm = run(driver, tmp_path, body, ARJUN_ROUTE, answer, "step1")
    prompt = llm.calls[1]["prompt"]
    assert f"case: {case}" in prompt or case in prompt
    assert resp["as_of"] == as_of and resp["route"] == "personal_rule"
    assert {"type": "policy", "id": "ZEN-POL-002", "section": section} in resp["citations"]
    sid = f"ZEN-POL-002#{section}"
    assert (ARJUN, "RULE_CASE", sid) in edge_set(resp)
    rule_edge = next(e for e in resp["subgraph"]["edges"] if e["type"] == "RULE_CASE")
    assert rule_edge["derived"] is True and rule_edge["role"] == "decisive"
    arjun = next(n for n in resp["subgraph"]["nodes"] if n["id"] == ARJUN)
    assert "join_date = 2026-07-20" in arjun["detail"]
    assert "Decisive:" not in prompt  # the detail is for the page, not the generator
    assert_cited_paths_drawable(resp)


# ---------------------------------------------------------------- 2. Pooja's leave: peer refused, HR answered

POOJA_Q = "Is Pooja Agarwal on leave?"
POOJA_RULE = {"intent": "personal_rule", "entities": [POOJA],
              "plan": [{"op": "WORK_MODE", "args": {"subject": POOJA}}]}
POOJA_TEXT = {"intent": "policy_text", "entities": [POOJA],
              "plan": [{"op": "text_search", "args": {"query": "Pooja Agarwal leave", "entity_id": POOJA}}]}


@pytest.fixture(scope="module")
def leave_embedder(driver: Driver) -> ChunkEmbedder:
    with driver.session() as s:
        vec = s.run("MATCH (c:Chunk {chunk_id: $id}) RETURN c.embedding AS v", id=POOJA_LEAVE).single()["v"]
    return ChunkEmbedder(vec)


def test_peer_is_not_authorised() -> None:
    p, peer = facts_from_csv().get(POOJA), facts_from_csv().get(PEER)
    assert PEER not in (POOJA, POOJA_MGR, p.manager_id) and peer.department_code != "HR"


def test_moment2_rule_path_peer_refused(driver: Driver, tmp_path: Path) -> None:
    resp, llm = run(driver, tmp_path, {"question": POOJA_Q, "asker_id": PEER}, POOJA_RULE,
                    "I can't share Pooja Agarwal's leave or employment status.", "step1")
    prompt = llm.calls[1]["prompt"]
    assert "status: restricted" in prompt
    assert resp["citations"] == [] and resp["subgraph"] == {"nodes": [], "edges": []}
    blob = json.dumps(resp) + prompt
    for v in restricted_values(POOJA) + ["ON_LEAVE", "ZEN-POL-003#3"]:
        assert v not in blob, v


def test_moment2_rule_path_hr_answered(driver: Driver, tmp_path: Path) -> None:
    resp, llm = run(driver, tmp_path, {"question": POOJA_Q, "asker_id": HR}, POOJA_RULE,
                    "Yes, Pooja Agarwal is on leave.", "step1")
    assert "ON_LEAVE" in llm.calls[1]["prompt"]
    assert any(c["type"] == "policy" for c in resp["citations"])
    details = " ".join(n["detail"] for n in resp["subgraph"]["nodes"])
    assert all(v not in details for v in restricted_values(POOJA))  # details stay public even for HR


def test_moment2_text_path_peer_refused(driver: Driver, tmp_path: Path, leave_embedder: ChunkEmbedder) -> None:
    resp, llm = run(driver, tmp_path, {"question": POOJA_Q, "asker_id": PEER}, POOJA_TEXT,
                    "I can't find that in Waypoint's sources.", embedder=leave_embedder)
    prompt = llm.calls[1]["prompt"]
    blob = json.dumps(resp) + prompt
    assert POOJA_LEAVE not in blob
    for v in restricted_values(POOJA):
        assert v not in blob, v


def test_moment2_text_path_hr_sees_the_chunk(driver: Driver, tmp_path: Path, leave_embedder: ChunkEmbedder) -> None:
    resp, llm = run(driver, tmp_path, {"question": POOJA_Q, "asker_id": HR}, POOJA_TEXT,
                    "Yes, Pooja Agarwal is on leave.", "passage1", embedder=leave_embedder)
    prompt = llm.calls[1]["prompt"]
    assert "Employment status: On maternity leave" in prompt  # the chunk's text reached HR's pack
    assert "restricted" not in prompt  # under a neutral id (pack-v4, 3.3a)
    assert {"type": "chunk", "id": POOJA_LEAVE} in resp["citations"]


# ---------------------------------------------------------------- 3. Who reports to Meera?

def test_moment3_meera_reports(driver: Driver, tmp_path: Path) -> None:
    route = {"intent": "fact_list_count", "entities": [MEERA],
             "plan": [{"op": "direct_reports", "args": {"employee_id": MEERA}}]}
    answer = ("Ananya Bhattacharya, Deepa Venkatesh, Farhan Siddiqui, Karthik Naidu, Manoj Thomas "
              "and Prakash Raman.")
    resp, _ = run(driver, tmp_path, {"question": "Who reports to Meera?", "asker_id": ARJUN}, route, answer, "step1")
    nodes = {n["id"] for n in resp["subgraph"]["nodes"]}
    assert nodes >= MEERA_REPORTS | {MEERA}
    assert {(r, "REPORTS_TO", MEERA) for r in MEERA_REPORTS} <= edge_set(resp)
    assert assert_cited_paths_drawable(resp) == 6
    assert not any(e["derived"] for e in resp["subgraph"]["edges"])


# ---------------------------------------------------------------- 4. Who approves terminating Divya?

def test_moment4_divya_termination(driver: Driver, tmp_path: Path) -> None:
    route = {"intent": "personal_rule", "entities": [DIVYA],
             "plan": [{"op": "TERMINATION_APPROVAL", "args": {"subject": DIVYA}}]}
    answer = "Karthik Naidu recommends it, Lakshmi approves it and the CEO gives the final approval."
    resp, llm = run(driver, tmp_path, {"question": "Who approves terminating Divya?", "asker_id": HR},
                    route, answer, "step1")
    nodes = {n["id"] for n in resp["subgraph"]["nodes"]}
    assert nodes >= {DIVYA, "ZV-1003", HR, "ZV-1001", "ZEN-POL-004#7"}
    e = edge_set(resp)
    assert {(DIVYA, "IN_BAND", "Z5"), (DIVYA, "RULE_CASE", "ZEN-POL-004#7"), ("ZV-1003", "HEADS", "D03"),
            (HR, "HEADS", "D01")} <= e
    assert {"type": "policy", "id": "ZEN-POL-004", "section": 7} in resp["citations"]
    assert assert_cited_paths_drawable(resp) >= 3
