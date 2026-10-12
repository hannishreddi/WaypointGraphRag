"""3.3a: passages carry neutral ids (pack-v4), so the generator never sees a chunk's
sensitivity label. Access is enforced in retrieval (rule 6), not by the model reading
"::restricted" in an id.

Unit tests build packs from hand-made evidence; the Neo4j tests run the Pooja text path
(3.2 demo moment 2) through S5 with a scripted LLM and the real access filter.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from neo4j import Driver

import waypoint.answer.pack as P
from tests.test_llm_structured import ScriptedLLM
from waypoint.answer.generate import build_prompt
from waypoint.answer.system import S5Waypoint
from waypoint.contract import ChunkCitation, PolicyCitation, Subgraph
from waypoint.retrieval.plan import Evidence, EvidenceItem, StepResult
from waypoint.retrieval.router import Router
from waypoint.answer.refusal import RESTRICTED_REFUSAL

AS_OF = date(2026, 10, 10)
POOJA, HR, PEER = "ZV-1031", "ZV-1006", "ZV-1020"
POOJA_LEAVE = "profile:ZV-1031::employee-record::restricted"
POOJA_ABOUT = "profile:ZV-1031::about::restricted"
Q = "What does Pooja Agarwal's profile say about leave?"
ITEM_TAG = re.compile(r"<item ([^>]*)>")


def hit(chunk_id: str, text: str, **kw: object) -> dict:
    return {"chunk_id": chunk_id, "text": text, "doc_type": "profile", "doc_id": "profile:x", "section": "",
            **kw}


def pack_from(hits_by_step: list[list[dict]], monkeypatch: pytest.MonkeyPatch) -> P.ContextPack:
    monkeypatch.setattr(P, "identity_item", lambda driver, asker: (P.PackItem("asker", "identity", "me"), Subgraph()))
    route = SimpleNamespace(question="q", asker_id=HR, decision=SimpleNamespace(needs_identity=False), unresolved=[])
    ev = Evidence(items=[EvidenceItem("primary", StepResult(i + 1, "text_search", {"query": "q"}, hits))
                         for i, hits in enumerate(hits_by_step)])
    return P.build_pack(route, ev, driver=None, as_of=AS_OF)  # type: ignore[arg-type]


def test_passages_get_neutral_ids_in_pack_order(monkeypatch: pytest.MonkeyPatch) -> None:
    pol = hit("ZEN-POL-003::s3::0", "Leave policy text", doc_type="policy", doc_id="ZEN-POL-003", section="s3")
    pack = pack_from([[hit(POOJA_LEAVE, "leave text"), pol], [hit(POOJA_LEAVE, "dup"), hit(POOJA_ABOUT, "about")]],
                     monkeypatch)
    assert pack.ids() == ["asker", "passage1", "passage2", "passage3"]  # duplicate chunk dropped
    assert pack.passage_sources() == {"passage1": POOJA_LEAVE, "passage2": "ZEN-POL-003::s3::0",
                                      "passage3": POOJA_ABOUT}
    # Citations still point at the real chunk (and the policy section).
    assert pack.citations_for(["passage1"]) == [ChunkCitation(id=POOJA_LEAVE)]
    assert pack.citations_for(["passage2"]) == [ChunkCitation(id="ZEN-POL-003::s3::0"),
                                                PolicyCitation(id="ZEN-POL-003", section=3)]


def test_rendered_pack_never_shows_chunk_ids_or_sensitivity(monkeypatch: pytest.MonkeyPatch) -> None:
    pack = pack_from([[hit(POOJA_LEAVE, "Employment status: On leave."), hit(POOJA_ABOUT, "About.")]], monkeypatch)
    rendered = build_prompt(pack)
    assert "restricted" not in rendered and "::" not in rendered
    for attrs in ITEM_TAG.findall(rendered):
        assert "restricted" not in attrs and "::" not in attrs


# ---------------------------------------------------------------- the 3.2 failure, end to end

class ChunkEmbedder:
    def __init__(self, vector: list[float]) -> None:
        self.vector = vector

    def embed_query(self, text: str) -> list[float]:
        return self.vector


@pytest.fixture(scope="module")
def leave_embedder(driver: Driver) -> ChunkEmbedder:
    with driver.session() as s:
        return ChunkEmbedder(s.run("MATCH (c:Chunk {chunk_id: $id}) RETURN c.embedding AS v", id=POOJA_LEAVE)
                             .single()["v"])


def s5(driver: Driver, tmp_path: Path, embedder: ChunkEmbedder, plan: list, answer: str, *cited: str
       ) -> tuple[S5Waypoint, ScriptedLLM]:
    route = {"intent": "policy_text", "entities": [POOJA], "needs_identity": False, "confidence": 0.9, "plan": plan}
    llm = ScriptedLLM(json.dumps(route), json.dumps({"answer": answer, "cited_ids": list(cited)}))
    return S5Waypoint(llm, model_answer="answer", model_fast="fast", driver=driver, embedder=embedder,
                      router=Router(llm, model="fast", cache_dir=tmp_path)), llm


TEXT_PLAN = [{"op": "text_search", "args": {"query": "leave", "doc_type": "profile", "entity_id": POOJA}}]


@pytest.mark.neo4j
def test_hr_gets_the_leave_text_under_a_neutral_id(driver: Driver, tmp_path: Path,
                                                   leave_embedder: ChunkEmbedder) -> None:
    sys, llm = s5(driver, tmp_path, leave_embedder, TEXT_PLAN,
                  "Pooja Agarwal is on maternity leave from 1 Sep 2026 to 28 Feb 2027.", "passage1")
    r = sys.answer(Q, HR, AS_OF)
    prompt = llm.calls[1]["prompt"]
    assert "On maternity leave (1 Sep 2026 to 28 Feb 2027)" in prompt  # the access filter let it through
    assert "restricted" not in prompt and "::" not in prompt  # but the model cannot see the label
    assert r.trace["verifier"] == "pass" and r.trace["passages"]["passage1"] == POOJA_LEAVE
    assert ChunkCitation(id=POOJA_LEAVE) in r.citations
    assert all("restricted" not in i for i in r.trace["pack_items"])


@pytest.mark.neo4j
def test_peer_never_receives_a_restricted_passage(driver: Driver, tmp_path: Path,
                                                  leave_embedder: ChunkEmbedder) -> None:
    sys, llm = s5(driver, tmp_path, leave_embedder, TEXT_PLAN, "I can't find that in Waypoint's sources.")
    r = sys.answer(Q, PEER, AS_OF)
    prompt = llm.calls[1]["prompt"]
    assert "maternity" not in prompt.lower() and "Employment status" not in prompt
    assert not any(c.endswith("::restricted") for c in r.trace["passages"].values())
    assert r.citations == []


@pytest.mark.neo4j
def test_peer_rule_path_still_gets_the_restricted_refusal(driver: Driver, tmp_path: Path,
                                                          leave_embedder: ChunkEmbedder) -> None:
    plan = [{"op": "WORK_MODE", "args": {"subject": POOJA}}]
    sys, llm = s5(driver, tmp_path, leave_embedder, plan, "I can't share Pooja Agarwal's leave details.", "step1")
    r = sys.answer("Is Pooja Agarwal on leave?", PEER, AS_OF)
    # 3.3c F4: an all-restricted plan is refused with the fixed text, before the generator
    assert len(llm.calls) == 1 and r.answer == RESTRICTED_REFUSAL and r.citations == []
