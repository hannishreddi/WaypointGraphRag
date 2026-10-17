"""S5 Waypoint (PLAN 2.5): router -> plan execution -> context pack -> generator -> verifier.

    route    one MODEL_FAST call (cached in .cache/router/); refuse answers with a fixed
             text, no retrieval and no generator call: RESTRICTED_REFUSAL when the router
             marks the question restricted_fact, else SCOPE_MESSAGE (3.3c F4)
    execute  templates, rules and text_search (the access filter applies, rule 6)
    pack     identity, graph rows, rule results, passages, unresolved mentions
    answer   one MODEL_ANSWER call -> {answer, cited_ids}
    verify   deterministic; on failure one regeneration with the findings, then
             "I can't confirm that."

Restricted facts (3.3c F4, rule 6 itself is enforced by the engine and the access filter):
every primary step a restricted rule result -> RESTRICTED_REFUSAL with no generator call;
a "not found" or "can't confirm" on a restricted_fact question for an asker who may not
see the fact (a subject they are not the person, direct manager or HR for; or, with no
subject, a non-HR asker) -> RESTRICTED_REFUSAL. Refusals carry no citations or subgraph.

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
from waypoint.answer.refusal import RESTRICTED_REFUSAL, SCOPE_MESSAGE
from waypoint.answer.generate import PROMPT_VERSION as ANSWER_PROMPT
from waypoint.answer.pack import VERSION as PACK_VERSION
from waypoint.answer.pack import build_pack
from waypoint.answer.verify import VERSION as VERIFIER_VERSION
from waypoint.answer.verify import verify
from waypoint.config import get_settings
from waypoint.contract import Response, Usage
from waypoint.llm.client import LLMClient, get_llm_client
from waypoint.retrieval.router import PROMPT_VERSION as ROUTER_PROMPT
from waypoint.retrieval.plan import Evidence
from waypoint.retrieval.router import Route, Router, execute
from waypoint.retrieval.search import QueryEmbedder
from waypoint.rules.engine import HR_DEPARTMENT_CODE, RuleResult, can_see_restricted
from waypoint.rules.facts import facts_from_csv

REFUSAL = RESTRICTED_REFUSAL  # kept name: the router-refuse text for restricted questions
CANT_CONFIRM = "I can't confirm that."


def all_restricted(evidence: Evidence) -> bool:
    """Every primary step is a rule result the asker may not see."""
    primary = [i.step.output for i in evidence.items if i.path == "primary"]
    return bool(primary) and all(isinstance(o, RuleResult) and o.status == "restricted" for o in primary)


def restricted_subjects(route: Route, evidence: Evidence) -> set[str]:
    """Employees the question's restricted facts are about: rule subjects, text_search
    entity ids and linked employees."""
    facts = facts_from_csv()
    ids = {m.id for m in route.links.matches if m.label == "Employee"}
    for item in evidence.items:
        args = item.step.args
        ids |= {v for k, v in args.items() if k in ("subject", "entity_id") and isinstance(v, str)}
    return {i for i in ids if i in facts}


def authorised(route: Route, evidence: Evidence) -> bool:
    """Rule 6 for the refusal wording only: may this asker see the facts asked about?"""
    facts = facts_from_csv()
    subjects = restricted_subjects(route, evidence)
    if subjects:
        return all(can_see_restricted(s, route.asker_id, facts) for s in subjects)
    asker = facts.get(route.asker_id)
    return asker is not None and asker.department_code == HR_DEPARTMENT_CODE


def config_id(model_answer: str, model_fast: str) -> str:
    """S5's config id: answer, router, pack and verifier versions, then both models
    (part of every checkpoint key)."""
    return f"{ANSWER_PROMPT}:{ROUTER_PROMPT}:{PACK_VERSION}:{VERIFIER_VERSION}:{model_answer}:{model_fast}"


class S5Waypoint:
    name = "s5"

    def __init__(self, client: LLMClient, *, model_answer: str, model_fast: str, driver: Driver,
                 embedder: QueryEmbedder | None = None, router: Router | None = None) -> None:
        self.client, self.model, self.driver, self.embedder = client, model_answer, driver, embedder
        self.router = router or Router(client, model=model_fast)
        self.config_id = config_id(model_answer, model_fast)

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

        restricted = route.decision.restricted_fact
        trace["restricted_fact"] = restricted
        if route.intent == "refuse":
            trace |= {"verifier": "skipped", "refusal": "router"}
            return done(RESTRICTED_REFUSAL if restricted else SCOPE_MESSAGE)

        evidence = execute(route, driver=self.driver, as_of=as_of, embedder=self.embedder)
        pack = build_pack(route, evidence, driver=self.driver, as_of=as_of)
        trace["pack_items"] = pack.ids()
        trace["passages"] = pack.passage_sources()
        if all_restricted(evidence):
            trace |= {"verifier": "skipped", "refusal": "restricted_rule"}
            return done(RESTRICTED_REFUSAL)

        def refuse_if_restricted(answer: str) -> Response | None:
            if restricted and answer in (NOT_FOUND, CANT_CONFIRM) and not authorised(route, evidence):
                trace["refusal"] = "not_found_restricted"
                return done(RESTRICTED_REFUSAL)
            return None

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
                return refuse_if_restricted(CANT_CONFIRM) or done(CANT_CONFIRM, subgraph=pack.subgraph)
        if (r := refuse_if_restricted(gen.answer.strip())) is not None:
            return r
        return done(gen.answer, citations=pack.citations_for(gen.cited_ids), subgraph=pack.subgraph)

