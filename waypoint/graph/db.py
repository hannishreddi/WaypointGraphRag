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


# ---------------------------------------------------------------- trusted fixed queries
# Index procedures need CALL, which check_read_only rejects. These constant queries are
# the only exception: callers pick one by name and pass parameters, never Cypher text.
# They still run in a read transaction. Only waypoint.retrieval.search uses them.

VECTOR_INDEX = "chunk_embedding"
FULLTEXT_INDEX = "chunk_text"

_CHUNK_FIELDS = (
    "RETURN node.chunk_id AS chunk_id, node.doc_id AS doc_id, node.doc_type AS doc_type, "
    "node.section AS section, node.text AS text, node.sensitivity AS sensitivity, "
    "node.subject_id AS subject_id, score ORDER BY score DESC LIMIT $k"
)
# Optional filters (PLAN 2.4): null means no filter.
_CHUNK_FILTER = (
    "WHERE ($include_restricted OR node.sensitivity = 'public') "
    "AND ($doc_type IS NULL OR node.doc_type = $doc_type) "
    "AND ($doc_ids IS NULL OR node.doc_id IN $doc_ids)"
)
_TRUSTED: dict[str, str] = {
    "chunk_vector": (
        f"CALL db.index.vector.queryNodes('{VECTOR_INDEX}', $n, $vector) YIELD node, score "
        f"{_CHUNK_FILTER} {_CHUNK_FIELDS}"
    ),
    "chunk_fulltext": (
        f"CALL db.index.fulltext.queryNodes('{FULLTEXT_INDEX}', $query, {{limit: $n}}) YIELD node, score "
        f"{_CHUNK_FILTER} {_CHUNK_FIELDS}"
    ),
    "restricted_chunk_count": "MATCH (c:Chunk {sensitivity: 'restricted'}) RETURN count(c) AS n",
    "chunk_count": "MATCH (c:Chunk) RETURN count(c) AS n",
}


def run_read_trusted(driver: Driver, name: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Run one of the fixed queries in _TRUSTED in a read transaction. Internal: search only."""
    cypher = _TRUSTED[name]
    with driver.session() as session:
        return session.execute_read(lambda tx: tx.run(cypher, params).data())
