"""Chunk graph and indexes (PLAN 1.3). Expected values come from the files via the
chunker, never from the graph. The indexer runs with an offline embedder, so tests
make no Cohere calls; they need the cache that `make index` fills."""
from __future__ import annotations

from collections import Counter

import pytest
from neo4j import Driver

from tests import doc_expect as D
from waypoint.config import get_settings
from waypoint.graph.db import FULLTEXT_INDEX, VECTOR_INDEX, run_read
from waypoint.graph.load import load
from waypoint.retrieval.chunking import Corpus, build_corpus
from waypoint.retrieval.embed import CacheMissError, Embedder
from waypoint.retrieval.index import index
from waypoint.retrieval.search import search_fulltext, search_text

pytestmark = pytest.mark.neo4j


def offline() -> Embedder:
    return Embedder.from_settings(offline=True)


@pytest.fixture(scope="module")
def corpus() -> Corpus:
    return build_corpus()


@pytest.fixture(scope="module")
def graph(driver: Driver) -> Driver:
    load(driver)
    try:
        index(driver, offline())
    except CacheMissError as exc:
        pytest.fail(f"embedding cache incomplete ({exc}); run `make index` first", pytrace=False)
    return driver


def counts(driver: Driver) -> tuple[dict[str, int], dict[str, int]]:
    nodes = run_read(driver, "MATCH (n) UNWIND labels(n) AS l RETURN l, count(*) AS n")
    rels = run_read(driver, "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS n")
    return {r["l"]: r["n"] for r in nodes}, {r["t"]: r["n"] for r in rels}


def test_chunk_counts_by_type_and_sensitivity(graph: Driver, corpus: Corpus) -> None:
    rows = run_read(graph, "MATCH (c:Chunk) RETURN c.doc_type AS t, c.sensitivity AS s, count(*) AS n")
    assert {(r["t"], r["s"]): r["n"] for r in rows} == dict(
        Counter((c.doc_type, c.sensitivity) for c in corpus.chunks))


def test_restricted_chunks_keep_subject_id(graph: Driver, corpus: Corpus) -> None:
    rows = run_read(graph, "MATCH (c:Chunk {sensitivity: 'restricted'}) "
                           "RETURN c.chunk_id AS id, c.subject_id AS subject")
    assert len(rows) == 46
    assert {r["id"]: r["subject"] for r in rows} == {
        c.chunk_id: c.subject_id for c in corpus.chunks if c.sensitivity == "restricted"}
    assert run_read(graph, "MATCH (c:Chunk {sensitivity: 'public'}) WHERE c.subject_id IS NOT NULL "
                           "RETURN count(c) AS n") == [{"n": 0}]


def test_every_chunk_is_part_of_one_described_document(graph: Driver, corpus: Corpus) -> None:
    assert run_read(graph, "MATCH (d:Document) RETURN count(d) AS n") == [{"n": len(corpus.docs)}]
    bad = run_read(graph, "MATCH (c:Chunk) WITH c, count{(c)-[:PART_OF]->(:Document)} AS k "
                          "WHERE k <> 1 RETURN c.chunk_id AS id")
    assert bad == []
    bad = run_read(graph, "MATCH (d:Document) WITH d, count{(d)-[:DESCRIBES]->()} AS k "
                          "WHERE k <> 1 RETURN d.doc_id AS id")
    assert bad == []


def test_policy_sections_hang_off_their_policy(graph: Driver) -> None:
    expected = sum(len(D.numbered_sections(p)) for p in D.policy_files())
    rows = run_read(graph, "MATCH (p:Policy)-[:HAS_SECTION]->(s:PolicySection) "
                           "WHERE s.policy_id = p.policy_id RETURN count(s) AS n")
    assert rows == [{"n": expected}]
    assert run_read(graph, "MATCH (s:PolicySection) RETURN count(s) AS n") == [{"n": expected}]
    rows = run_read(graph, "MATCH (c:Chunk)-[:OF_SECTION]->(s:PolicySection) RETURN count(c) AS n")
    assert rows == [{"n": expected}]


def test_mentions_match_corpus(graph: Driver, corpus: Corpus) -> None:
    rows = run_read(graph, "MATCH (:Chunk)-[m:MENTIONS]->(t) RETURN labels(t)[0] AS l, count(m) AS n")
    expected = Counter(t.label for c in corpus.chunks for t in c.mentions)
    assert {r["l"]: r["n"] for r in rows} == dict(expected)


def test_index_twice_is_idempotent_with_zero_api_calls(graph: Driver) -> None:
    before = counts(graph)
    emb = offline()
    stats = index(graph, emb)
    assert stats.api_calls == 0 and emb.api_calls == 0
    assert counts(graph) == before


def test_vector_and_fulltext_indexes(graph: Driver) -> None:
    rows = run_read(graph, "SHOW INDEXES YIELD name, type, state, options "
                           "WHERE name IN $names RETURN name, type, state, options",
                    {"names": [VECTOR_INDEX, FULLTEXT_INDEX]})
    by_name = {r["name"]: r for r in rows}
    vec = by_name[VECTOR_INDEX]
    assert vec["type"] == "VECTOR" and vec["state"] == "ONLINE"
    assert vec["options"]["indexConfig"]["vector.dimensions"] == get_settings().embed_dim
    assert vec["options"]["indexConfig"]["vector.similarity_function"].lower() == "cosine"
    assert by_name[FULLTEXT_INDEX]["type"] == "FULLTEXT"
    assert by_name[FULLTEXT_INDEX]["state"] == "ONLINE"


def test_fulltext_finds_leave_policy(graph: Driver) -> None:
    hits = search_fulltext("maternity leave entitlement", 5, driver=graph)
    assert "ZEN-POL-003" in {h["doc_id"] for h in hits}
    assert all(h["sensitivity"] == "public" for h in hits)


def test_fulltext_tolerates_lucene_syntax(graph: Driver) -> None:
    assert isinstance(search_fulltext('ZEN-POL-004 AND (notice "period', 3, driver=graph), list)


class VectorOf:
    """Embedder stand-in whose query vector is the cached vector of a given chunk text."""

    def __init__(self, text: str) -> None:
        self.vector = offline().embed([text], "search_document")[0]

    def embed_query(self, _query: str) -> list[float]:
        return self.vector


def test_search_text_hides_restricted_chunks_by_default(graph: Driver, corpus: Corpus) -> None:
    (about,) = [c for c in corpus.chunks if c.chunk_id == "profile:ZV-1031::about::restricted"]
    emb = VectorOf(about.text)
    default = search_text("Is Pooja Agarwal on maternity leave?", 5, driver=graph, embedder=emb)
    assert len(default) == 5
    assert all(h["sensitivity"] == "public" for h in default)
    assert about.chunk_id not in {h["chunk_id"] for h in default}
    allowed = search_text("Is Pooja Agarwal on maternity leave?", 5, include_restricted=True,
                          driver=graph, embedder=emb)
    assert allowed[0]["chunk_id"] == about.chunk_id
    assert allowed[0]["subject_id"] == "ZV-1031"
