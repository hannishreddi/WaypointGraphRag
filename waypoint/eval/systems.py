"""Systems the runner can evaluate, by name (`--system`). S1/S3/S5 register here later."""
from __future__ import annotations

import time
from collections.abc import Callable
from datetime import date

from waypoint.contract import Response, System


class EchoSystem:
    """Answers with the question itself. For testing the runner; scores ~0."""

    name = "echo"

    def answer(self, question: str, asker_id: str, as_of: date) -> Response:
        t0 = time.perf_counter()
        return Response(answer=question, route="echo", as_of=as_of,
                        latency_ms=(time.perf_counter() - t0) * 1000)


SYSTEMS: dict[str, Callable[[], System]] = {"echo": EchoSystem}
