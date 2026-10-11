"""Chunk search over the vector and full-text indexes. PLAN 1.3.

Both run fixed queries through waypoint.graph.db.run_read_trusted (read transaction,
parameters only). Restricted chunks are excluded unless include_restricted=True;
the caller (2.5 access filter) decides that from the asker. To still return k
public hits, the index is asked for k + the number of restricted chunks.

Optional filters (PLAN 2.4): `doc_type` (one of DOC_TYPES) and `entity_id` (only chunks
of the Documents that DESCRIBE that entity: a policy's sections, a department or project
page, a person's profile and resume). With a filter the index is asked for every chunk,
so the k best matching ones survive the filter (the corpus is small).
"""
from __future__ import annotations

import argparse
import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any, Protocol

from neo4j import Driver

from waypoint.graph.db import get_driver, run_read, run_read_trusted
from waypoint.retrieval.embed import Embedder

LUCENE_SPECIAL = re.compile(r'([+\-&|!(){}\[\]^"~*?:\\/])')

Hit = dict[str, Any]
DOC_TYPES = ("policy", "profile", "resume", "department", "project", "product", "company")

DOC_IDS_FOR = """
MATCH (d:Document)-[:DESCRIBES]->(e)
WHERE $id IN [e.employee_id, e.department_id, e.project_id, e.product_id, e.policy_id, e.company_id]
RETURN d.doc_id AS doc_id ORDER BY doc_id"""


class QueryEmbedder(Protocol):
    def embed_query(self, text: str) -> list[float]: ...


@contextmanager
def _driver(driver: Driver | None) -> Iterator[Driver]:
    if driver is not None:
        yield driver
        return
    own = get_driver()
    try:
        yield own
    finally:
        own.close()


def doc_ids_for(driver: Driver, entity_id: str) -> list[str]:
    """Documents describing the entity (empty for an unknown id)."""
    return [r["doc_id"] for r in run_read(driver, DOC_IDS_FOR, {"id": entity_id})]


def _n(driver: Driver, k: int, include_restricted: bool, filtered: bool) -> int:
    if filtered:
        return run_read_trusted(driver, "chunk_count", {})[0]["n"]
    if include_restricted:
        return k
    return k + run_read_trusted(driver, "restricted_chunk_count", {})[0]["n"]


def _filters(driver: Driver, doc_type: str | None, entity_id: str | None) -> dict[str, Any]:
    if doc_type is not None and doc_type not in DOC_TYPES:
        raise ValueError(f"unknown doc_type {doc_type!r}; expected one of {DOC_TYPES}")
    return {"doc_type": doc_type,
            "doc_ids": None if entity_id is None else doc_ids_for(driver, entity_id)}


def search_text(query: str, k: int = 5, include_restricted: bool = False, *,
                doc_type: str | None = None, entity_id: str | None = None,
                driver: Driver | None = None, embedder: QueryEmbedder | None = None) -> list[Hit]:
    """Top-k chunks by cosine similarity to the query (embedded with input_type search_query)."""
    with _driver(driver) as drv:
        filters = _filters(drv, doc_type, entity_id)
        if filters["doc_ids"] == []:
            return []
        vector = (embedder or Embedder.from_settings()).embed_query(query)
        return run_read_trusted(drv, "chunk_vector", {
            "vector": vector, "k": k, "n": _n(drv, k, include_restricted, bool(doc_type or entity_id)),
            "include_restricted": include_restricted, **filters})


def lucene_escape(query: str) -> str:
    """Lowercase (so AND/OR/NOT are plain words) and escape Lucene syntax."""
    return LUCENE_SPECIAL.sub(r"\\\1", query.lower())


def search_fulltext(query: str, k: int = 5, include_restricted: bool = False, *,
                    doc_type: str | None = None, entity_id: str | None = None,
                    driver: Driver | None = None) -> list[Hit]:
    """Top-k chunks from the full-text (Lucene) index."""
    escaped = lucene_escape(query).strip()
    if not escaped:
        return []
    with _driver(driver) as drv:
        filters = _filters(drv, doc_type, entity_id)
        if filters["doc_ids"] == []:
            return []
        return run_read_trusted(drv, "chunk_fulltext", {
            "query": escaped, "k": k, "n": _n(drv, k, include_restricted, bool(doc_type or entity_id)),
            "include_restricted": include_restricted, **filters})


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Search chunks (public only by default)")
    parser.add_argument("query", nargs="+")
    parser.add_argument("-k", type=int, default=3)
    parser.add_argument("--fulltext", action="store_true")
    args = parser.parse_args(argv)
    for q in args.query:
        hits = search_fulltext(q, args.k) if args.fulltext else search_text(q, args.k)
        print(f"\n{q}")
        for i, h in enumerate(hits, 1):
            first = h["text"].splitlines()[0][:90]
            print(f"  {i}. {h['score']:.3f}  {h['chunk_id']}  | {first}")


if __name__ == "__main__":
    main()
