"""Systems the runner can evaluate, by name (`--system`)."""
from __future__ import annotations

import time
from collections.abc import Callable
from datetime import date

from waypoint.contract import Response, System
from waypoint.eval.baselines import S1VectorRAG, S3FullContext


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


SYSTEMS: dict[str, Callable[[], System]] = {
    "echo": EchoSystem,
    "s1": S1VectorRAG.from_settings,
    "s3": S3FullContext.from_settings,
    "s5": _s5,
}
