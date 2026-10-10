"""Chunk search over the vector and full-text indexes. PLAN 1.3.

Both run fixed queries through waypoint.graph.db.run_read_trusted (read transaction,
parameters only). Restricted chunks are excluded unless include_restricted=True;
the caller (2.5 access filter) decides that from the asker. To still return k
public hits, the index is asked for k + the number of restricted chunks.
"""
from __future__ import annotations

import argparse
import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any, Protocol

from neo4j import Driver

from waypoint.graph.db import get_driver, run_read_trusted
from waypoint.retrieval.embed import Embedder

LUCENE_SPECIAL = re.compile(r'([+\-&|!(){}\[\]^"~*?:\\/])')

Hit = dict[str, Any]


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


def _n(driver: Driver, k: int, include_restricted: bool) -> int:
    if include_restricted:
        return k
    return k + run_read_trusted(driver, "restricted_chunk_count", {})[0]["n"]


def search_text(query: str, k: int = 5, include_restricted: bool = False, *,
                driver: Driver | None = None, embedder: QueryEmbedder | None = None) -> list[Hit]:
    """Top-k chunks by cosine similarity to the query (embedded with input_type search_query)."""
    vector = (embedder or Embedder.from_settings()).embed_query(query)
    with _driver(driver) as drv:
        return run_read_trusted(drv, "chunk_vector", {
            "vector": vector, "k": k, "n": _n(drv, k, include_restricted),
            "include_restricted": include_restricted})


def lucene_escape(query: str) -> str:
    """Lowercase (so AND/OR/NOT are plain words) and escape Lucene syntax."""
    return LUCENE_SPECIAL.sub(r"\\\1", query.lower())


def search_fulltext(query: str, k: int = 5, include_restricted: bool = False, *,
                    driver: Driver | None = None) -> list[Hit]:
    """Top-k chunks from the full-text (Lucene) index."""
    escaped = lucene_escape(query).strip()
    if not escaped:
        return []
    with _driver(driver) as drv:
        return run_read_trusted(drv, "chunk_fulltext", {
            "query": escaped, "k": k, "n": _n(drv, k, include_restricted),
            "include_restricted": include_restricted})


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
