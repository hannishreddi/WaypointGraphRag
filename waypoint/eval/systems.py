"""Systems the runner can evaluate, by name (`--system`)."""
from __future__ import annotations

import time
from collections.abc import Callable
from datetime import date

from waypoint.contract import Response, System
from waypoint.eval.baselines import S1PublicOnly, S1VectorRAG, S3FullContext


class EchoSystem:
    """Answers with the question itself. For testing the runner; scores ~0."""

    name = "echo"

    def answer(self, question: str, asker_id: str, as_of: date) -> Response:
        t0 = time.perf_counter()
        return Response(answer=question, route="echo", as_of=as_of,
                        latency_ms=(time.perf_counter() - t0) * 1000)


def _s5() -> System:
    from waypoint.answer.system import S5Waypoint  # needs Neo4j and the router; import lazily

    return S5Waypoint.from_settings()


def _ablation(name: str) -> Callable[[], System]:
    def make() -> System:
        from waypoint.eval.ablations import ABLATIONS  # imports S5: lazily, like _s5

        return ABLATIONS[name].from_settings()
    return make


SYSTEMS: dict[str, Callable[[], System]] = {
    "echo": EchoSystem,
    "s1": S1VectorRAG.from_settings,
    "s1f": S1PublicOnly.from_settings,  # safety set only (safety_only = True)
    "s3": S3FullContext.from_settings,
    "s5": _s5,
    # 3.3e ablations (waypoint.eval.ablations): dev and safety sets only, never the test split
    **{f"s5-{name}": _ablation(name) for name in ("norouter", "noverifier", "noidentity", "noaccess")},
}
