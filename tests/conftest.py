from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from neo4j import Driver

from waypoint.graph.db import get_driver


@pytest.fixture(scope="session")
def driver() -> Iterator[Driver]:
    """Live Neo4j driver. Skips when unreachable, unless REQUIRE_NEO4J=1 (make test-graph)."""
    drv = get_driver()
    try:
        drv.verify_connectivity()
    except Exception as exc:  # noqa: BLE001 - any connection/auth failure
        drv.close()
        msg = f"Neo4j unreachable ({type(exc).__name__}: {exc}); run `make up`"
        if os.environ.get("REQUIRE_NEO4J") == "1":
            pytest.fail(msg, pytrace=False)
        pytest.skip(msg)
    yield drv
    drv.close()
