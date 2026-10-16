"""A fixed mock-LLM run of S5 (3.3e): the same scripted replies, router cache in a temporary
folder, a fixed query embedding. It is used by tests/fixtures/build_s5_golden.py (run once
against the freeze-1 code) and by tests/test_ablations.py (current code, before and after
every ablation). Only APIs that exist at freeze-1 are used.

A record holds the Response JSON (latency_ms set to 0), the trace, and per LLM call the model,
JSON mode and sha256 of the system and user prompts, so equal records mean byte-identical
prompts and answers.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

from neo4j import Driver

from waypoint.answer.system import S5Waypoint
from waypoint.llm.client import Completion
from waypoint.retrieval.router import Router

AS_OF = date(2026, 10, 10)
HR, ARJUN, PEER = "ZV-1006", "ZV-1042", "ZV-1020"
TARUN, POOJA = "ZV-1033", "ZV-1031"
POOJA_LEAVE = "profile:ZV-1031::employee-record::restricted"
DIVYA_Q = "Who does Divya Krishnamurthy report to?"
POOJA_Q = "What does Pooja Agarwal's profile say about leave?"
TARUN_Q = "What is Tarun Mehta's notice period?"


class ScriptedClient:
    """Fake LLMClient: canned replies in order; records every call."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    def complete(self, *, model: str, system: str, prompt: str, max_tokens: int,
                 json_mode: bool = False) -> Completion:
        self.calls.append({"model": model, "system": system, "prompt": prompt, "json_mode": json_mode})
        return Completion(text=self.replies.pop(0), input_tokens=10, output_tokens=5)


class ChunkEmbedder:
    """Query embedding = a stored chunk's embedding, so that chunk ranks first when visible."""

    def __init__(self, vector: list[float]) -> None:
        self.vector = vector

    def embed_query(self, text: str) -> list[float]:
        return self.vector


def chunk_embedder(driver: Driver, chunk_id: str = POOJA_LEAVE) -> ChunkEmbedder:
    with driver.session() as s:
        return ChunkEmbedder(s.run("MATCH (c:Chunk {chunk_id: $id}) RETURN c.embedding AS v", id=chunk_id)
                             .single()["v"])


def route(intent: str, plan: list[dict] | None = None, **kw: Any) -> str:
    return json.dumps({"intent": intent, "entities": [], "needs_identity": False, "confidence": 0.95,
                       "plan": plan or [], **kw})


def gen(answer: str, *cited: str) -> str:
    return json.dumps({"answer": answer, "cited_ids": list(cited)})


MANAGER = [{"op": "manager", "args": {"employee_id": "ZV-1004"}}]
NOTICE = [{"op": "NOTICE_PERIOD", "args": {"subject": TARUN}}]
POOJA_TEXT = [{"op": "text_search", "args": {"query": "leave", "doc_type": "profile", "entity_id": POOJA}}]

# name, question, asker, scripted replies (router first), uses the fixed embedding
CASES: list[tuple[str, str, str, list[str], bool]] = [
    ("template", DIVYA_Q, HR, [route("fact_list_count", MANAGER, entities=["ZV-1004"]), gen("Karthik Naidu.", "step1")],
     False),
    ("regenerated", DIVYA_Q, HR, [route("fact_list_count", MANAGER, entities=["ZV-1004"]),
                                  gen("Ravi Kumar, since 2019.", "step1"), gen("Karthik Naidu.", "step1")], False),
    ("restricted_rule_peer", TARUN_Q, ARJUN,
     [route("personal_rule", NOTICE, entities=[TARUN], restricted_fact=True)], False),
    ("restricted_rule_hr", TARUN_Q, HR,
     [route("personal_rule", NOTICE, entities=[TARUN], restricted_fact=True), gen("Tarun Mehta.", "step1")], False),
    ("text_hr", POOJA_Q, HR, [route("policy_text", POOJA_TEXT, entities=[POOJA]), gen("She is on leave.", "passage1")],
     True),
    ("text_peer", POOJA_Q, PEER, [route("policy_text", POOJA_TEXT, entities=[POOJA]),
                                  gen("I can't find that in Waypoint's sources.")], True),
    ("refuse", "What is Tarun Mehta's salary?", HR, [route("refuse", restricted_fact=True)], False),
]


def make_s5(driver: Driver, tmp: Path, llm: ScriptedClient, embedder: ChunkEmbedder | None) -> S5Waypoint:
    return S5Waypoint(llm, model_answer="answer", model_fast="fast", driver=driver, embedder=embedder,  # type: ignore[arg-type]
                      router=Router(llm, model="fast", cache_dir=tmp))  # type: ignore[arg-type]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def record(resp: Any, llm: ScriptedClient) -> dict[str, Any]:
    response = json.loads(resp.model_dump_json())
    response["latency_ms"] = 0
    return {"response": response, "trace": resp.trace,
            "calls": [{"model": c["model"], "json_mode": c["json_mode"], "system_sha256": _sha(c["system"]),
                       "prompt_sha256": _sha(c["prompt"])} for c in llm.calls]}


def run_all(driver: Driver, tmp_root: Path) -> dict[str, Any]:
    embedder = chunk_embedder(driver)
    out: dict[str, Any] = {}
    for name, question, asker, replies, embeds in CASES:
        llm = ScriptedClient(*replies)
        system = make_s5(driver, tmp_root / name, llm, embedder if embeds else None)
        out[name] = record(system.answer(question, asker, AS_OF), llm)
        assert not llm.replies, f"{name}: {len(llm.replies)} scripted replies unused"
    return out


def dumps(records: dict[str, Any]) -> str:
    return json.dumps(records, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
