"""S5 Waypoint (PLAN 2.5): router -> plan execution -> context pack -> generator -> verifier.

    route    one MODEL_FAST call (cached in .cache/router/); refuse answers with a fixed
             refusal, no retrieval and no generator call
    execute  templates, rules and text_search (the access filter applies, rule 6)
    pack     identity, graph rows, rule results, passages, unresolved mentions
    answer   one MODEL_ANSWER call -> {answer, cited_ids}
    verify   deterministic; on failure one regeneration with the findings, then
             "I can't confirm that."

`usage` is the sum over every LLM call for the question: router, generator and
regeneration (validation retries included). A router answer served from the cache counts
with the tokens it cost when it was made, so tokens per question reflect a live run; the
router's latency cannot be recovered from the cache and is not in latency_ms.
Citations are those of the context items the final answer cites.
"""
from __future__ import annotations

import time
from datetime import date
from typing import Any

from neo4j import Driver

from waypoint.answer.generate import NOT_FOUND, generate
from waypoint.answer.generate import PROMPT_VERSION as ANSWER_PROMPT
from waypoint.answer.pack import VERSION as PACK_VERSION
from waypoint.answer.pack import build_pack
from waypoint.answer.verify import VERSION as VERIFIER_VERSION
from waypoint.answer.verify import verify
from waypoint.config import get_settings
from waypoint.contract import Response, Usage
from waypoint.llm.client import LLMClient, get_llm_client
from waypoint.retrieval.router import PROMPT_VERSION as ROUTER_PROMPT
from waypoint.retrieval.router import Router, execute
from waypoint.retrieval.search import QueryEmbedder

REFUSAL = ("I can't help with that. Waypoint answers questions about Zenvora's people, teams, projects "
           "and policies, and does not share pay, personal contact details or secrets.")
CANT_CONFIRM = "I can't confirm that."


class S5Waypoint:
    name = "s5"

    def __init__(self, client: LLMClient, *, model_answer: str, model_fast: str, driver: Driver,
                 embedder: QueryEmbedder | None = None, router: Router | None = None) -> None:
        self.client, self.model, self.driver, self.embedder = client, model_answer, driver, embedder
        self.router = router or Router(client, model=model_fast)
        self.config_id = (f"{ANSWER_PROMPT}:{ROUTER_PROMPT}:{PACK_VERSION}:{VERIFIER_VERSION}:"
                          f"{model_answer}:{model_fast}")

    @classmethod
    def from_settings(cls) -> S5Waypoint:
        from waypoint.graph.db import get_driver
        from waypoint.retrieval.embed import Embedder

        s = get_settings()
        return cls(get_llm_client(), model_answer=s.model_answer, model_fast=s.model_fast,
                   driver=get_driver(), embedder=Embedder.from_settings())

    def answer(self, question: str, asker_id: str, as_of: date) -> Response:
        t0 = time.perf_counter()
        route = self.router.route(question, asker_id)
        usage = route.recorded_usage
        trace: dict[str, Any] = {"intent": route.intent, "router_cached": route.cached,
                                 "router_calls": route.llm_calls, "low_confidence": route.low_confidence,
                                 "unresolved": route.unresolved}

        def done(answer: str, **kw: Any) -> Response:
            return Response(answer=answer, route=route.intent, as_of=as_of,
                            confidence=route.decision.confidence, usage=usage,
                            latency_ms=(time.perf_counter() - t0) * 1000, trace=trace, **kw)

        if route.intent == "refuse":
            trace["verifier"] = "skipped"
            return done(REFUSAL)

        evidence = execute(route, driver=self.driver, as_of=as_of, embedder=self.embedder)
        pack = build_pack(route, evidence, driver=self.driver, as_of=as_of)
        trace["pack_items"] = pack.ids()
        gen, u = generate(self.client, self.model, pack)
        usage += u
        verdict = verify(gen.answer, gen.cited_ids, pack, not_found=NOT_FOUND)
        trace |= {"verifier": "pass", "issues": verdict.issues}
        if not verdict.ok:
            trace["first_answer"] = gen.answer
            gen, u = generate(self.client, self.model, pack, previous=gen, issues=verdict.issues)
            usage += u
            verdict = verify(gen.answer, gen.cited_ids, pack, not_found=NOT_FOUND)
            trace |= {"verifier": "regenerated" if verdict.ok else "failed", "issues_retry": verdict.issues}
            if not verdict.ok:
                trace["second_answer"] = gen.answer
                return done(CANT_CONFIRM, subgraph=pack.subgraph)
        return done(gen.answer, citations=pack.citations_for(gen.cited_ids), subgraph=pack.subgraph)

