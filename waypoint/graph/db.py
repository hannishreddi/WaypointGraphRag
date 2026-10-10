"""Neo4j driver and the single read path used by answer queries (CLAUDE.md rule 3)."""
from __future__ import annotations

from typing import Any

from neo4j import Driver, GraphDatabase

from waypoint.config import get_settings
from waypoint.graph.guard import check_read_only


def get_driver() -> Driver:
    s = get_settings()
    return GraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_username, s.neo4j_password.get_secret_value()))


def run_read(driver: Driver, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Guard the query, then run it in a read-access transaction."""
    check_read_only(cypher)
    with driver.session() as session:
        return session.execute_read(lambda tx: tx.run(cypher, params or {}).data())
