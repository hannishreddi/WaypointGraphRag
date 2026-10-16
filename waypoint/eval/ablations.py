"""S5 ablations (PLAN 3.3e; definitions and predictions pre-registered in docs/ablations_3.3e.md).

Each ablation wraps a normal `S5Waypoint` and removes exactly one component. The rest of
S5's code path is the frozen code. Nothing outside waypoint/eval/ changes: default S5 behaviour
is untouched (tests/test_ablations.py compares S5 with a golden run of the freeze-1 code,
before and after every ablation has run).

    s5-norouter    no router: every question gets the plan [text_search(question)], built
                   without an LLM call (intent policy_text, confidence 1.0 so no alternative path,
                   restricted_fact false). Identity card, access filter, pack, generator and
                   verifier unchanged.
    s5-noverifier  the verifier always passes: no regeneration, no "I can't confirm that.".
    s5-noidentity  S5 is told the asker is ANONYMOUS (not an employee) everywhere: router
                   prompt, "asker" plan arguments, pack identity item, rule engine, access
                   filter. Fails closed. Only shim: the engine raises KeyError for an unknown
                   subject, so a rule about the anonymous asker returns `restricted` (restricted
                   rules, as for any unknown asker) or `insufficient_input` (the others) instead
                   of an error row.
    s5-noaccess    the retrieval access filter (`waypoint.retrieval.access.visible`) lets every
                   chunk through, so all restricted chunks reach every asker on the text path.
                   Rule-engine restrictions, public-only templates, the router and S5's refusal
                   logic stay on: the marginal value of that one layer, not of all of rule 6.

The swaps are `unittest.mock.patch` on a module name for the duration of one `answer` call
(restored on return or on an exception), or the S5 instance's own `router` attribute. The
eval runners are sequential and the API never builds these systems, so a patch cannot reach
another request. All four are `dev_only` (never the test split); s5-noaccess is also
`safety_only` (the main eval asks as HR, for whom the filter already lets everything through).

    python -m waypoint.eval.ablations --probe-router-cache

counts router-cache hits and misses for the planned runs with a client that fails on any
call: 0 LLM calls, nothing written.
"""
from __future__ import annotations

import argparse
import contextlib
from collections.abc import Iterator
from datetime import date
from typing import Any
from unittest import mock

from waypoint.answer import system as s5_module
from waypoint.answer.system import S5Waypoint
from waypoint.answer.verify import Verdict
from waypoint.contract import Response
from waypoint.retrieval import access, plan
from waypoint.retrieval.linking import link_mentions
from waypoint.retrieval.plan import RouterOutput
from waypoint.retrieval.router import Route
from waypoint.rules.engine import RuleResult, load_rules

VERSION = "v1"
ANONYMOUS = "anonymous"
MAX_QUERY = 300  # text_search's query limit (plan.py: 1 to 300 characters)


def ablation_config_id(ablation: str, s5_config_id: str) -> str:
    return f"{ablation}-{VERSION}:{s5_config_id}"


class TextSearchRouter:
    """No router: the plan is always [text_search(question)], with no LLM call."""

    def route(self, question: str, asker_id: str) -> Route:
        links = link_mentions(question)
        out = RouterOutput.model_validate(
            {"intent": "policy_text", "confidence": 1.0,
             "plan": [{"op": "text_search", "args": {"query": question.strip()[:MAX_QUERY]}}]},
            context={"links": links})
        return Route(question, asker_id, out, links, False)


def _always_pass(*args: Any, **kwargs: Any) -> Verdict:
    return Verdict(ok=True)


def _see_everything(*args: Any, **kwargs: Any) -> bool:
    return True


def _evaluate_without_identity(rule_id: str, subject_id: str | None, asker_id: str, as_of: date,
                               params: dict[str, Any] | None = None, **kw: Any) -> RuleResult:
    if subject_id != ANONYMOUS:
        return _ENGINE_EVALUATE(rule_id, subject_id, asker_id, as_of, params, **kw)
    restricted = load_rules()[rule_id].restricted
    return RuleResult(rule_id=rule_id, subject_id=subject_id, asker_id=asker_id, as_of=as_of,
                      status="restricted" if restricted else "insufficient_input", params=dict(params or {}),
                      assumptions=[] if restricted else ["the asker is not identified (no-identity ablation)"])


_ENGINE_EVALUATE = plan.evaluate_rule


class _Ablation:
    ablation = ""
    dev_only = True
    safety_only = False

    def __init__(self, inner: S5Waypoint) -> None:
        self.inner = inner
        self.name = f"s5-{self.ablation}"
        self.config_id = ablation_config_id(self.ablation, inner.config_id)

    @classmethod
    def from_settings(cls) -> _Ablation:
        return cls(S5Waypoint.from_settings())

    @contextlib.contextmanager
    def _patched(self) -> Iterator[None]:
        yield

    def answer(self, question: str, asker_id: str, as_of: date) -> Response:
        with self._patched():
            return self.inner.answer(question, asker_id, as_of)


class S5NoRouter(_Ablation):
    ablation = "norouter"

    def __init__(self, inner: S5Waypoint) -> None:
        super().__init__(inner)
        inner.router = TextSearchRouter()  # this instance only; the class and module are untouched


class S5NoVerifier(_Ablation):
    ablation = "noverifier"

    @contextlib.contextmanager
    def _patched(self) -> Iterator[None]:
        with mock.patch.object(s5_module, "verify", _always_pass):
            yield


class S5NoIdentity(_Ablation):
    ablation = "noidentity"

    @contextlib.contextmanager
    def _patched(self) -> Iterator[None]:
        with mock.patch.object(plan, "evaluate_rule", _evaluate_without_identity):
            yield

    def answer(self, question: str, asker_id: str, as_of: date) -> Response:
        with self._patched():
            return self.inner.answer(question, ANONYMOUS, as_of)


class S5NoAccessFilter(_Ablation):
    ablation = "noaccess"
    safety_only = True

    @contextlib.contextmanager
    def _patched(self) -> Iterator[None]:
        with mock.patch.object(access, "visible", _see_everything):
            yield


ABLATIONS: dict[str, type[_Ablation]] = {
    c.ablation: c for c in (S5NoRouter, S5NoVerifier, S5NoIdentity, S5NoAccessFilter)}


# ---------------------------------------------------------------- router-cache probe (0 calls)

class ProbeMiss(RuntimeError):
    """The probe's client was asked for a completion: the route is not cached."""


class FailingClient:
    def complete(self, **kwargs: Any) -> Any:
        raise ProbeMiss("router cache miss")


def probe_router_cache() -> list[tuple[str, int, int, list[str]]]:
    """(planned run, questions, cached routes, ids that would need a router call) for the
    routed runs of docs/ablations_3.3e.md, with a client that fails on any call."""
    from waypoint.config import get_settings
    from waypoint.eval import heldout
    from waypoint.eval.questions import asker_for, load_questions
    from waypoint.eval.safety import load_safety
    from waypoint.retrieval.router import Router

    router = Router(FailingClient(), model=get_settings().model_fast)  # type: ignore[arg-type]
    dev = [(q.id, q.question, asker_for(q.id)) for q in load_questions("dev")]
    personal = {q.id for q in load_questions("dev") if q.category == "personalised"}
    safety = [(q.id, q.question, q.asker_id) for q in load_safety()]
    held = [(q.id, q.question, q.asker_id) for q in heldout.load_heldout()[0]]
    planned = [
        ("R1 s5 dev, A1 s5-noverifier dev", dev),
        ("A3 s5-noidentity dev personalised", [(i, q, ANONYMOUS) for i, q, _ in dev if i in personal]),
        ("A6 s5-noverifier heldout", held),
        ("R2 s5 safety, A5 s5-noaccess safety", safety),
        ("A4 s5-noidentity safety", [(i, q, ANONYMOUS) for i, q, _ in safety]),
    ]
    out = []
    for name, items in planned:
        misses = []
        for qid, question, asker in items:
            try:
                router.route(question, asker)
            except ProbeMiss:
                misses.append(qid)
        out.append((name, len(items), len(items) - len(misses), misses))
    return out


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="S5 ablations (3.3e).")
    p.add_argument("--probe-router-cache", action="store_true", help="count router-cache hits (0 LLM calls)")
    args = p.parse_args(argv)
    if not args.probe_router_cache:
        p.error("nothing to do: the ablations run through waypoint.eval.run and waypoint.eval.safety")
    for name, n, cached, misses in probe_router_cache():
        print(f"{name}: {n} questions, {cached} cached routes, {len(misses)} router calls needed"
              + (f" ({' '.join(misses)})" if misses else ""))


if __name__ == "__main__":
    main()
