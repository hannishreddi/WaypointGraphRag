"""Chunk, embed and index the corpus into Neo4j (`make index`). PLAN 1.3.

Idempotent: unique constraints, then everything is MERGEd on stable ids
(Document.doc_id, PolicySection.section_id, Chunk.chunk_id). Nodes whose id the
chunker no longer produces are deleted, and chunk MENTIONS are rebuilt, so a re-run
leaves identical counts. All embeddings are fetched (or read from the cache)
before the first write, so a failed API call leaves the graph untouched.
Labels in formatted Cypher come from the constant TARGET_KEYS, never from text.
"""
from __future__ import annotations

import argparse
import math
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any

from neo4j import Driver, ManagedTransaction, Session

from waypoint.graph.db import FULLTEXT_INDEX, VECTOR_INDEX, get_driver, run_read
from waypoint.retrieval.chunking import Corpus, build_corpus
from waypoint.retrieval.embed import BATCH_SIZE, Embedder

BATCH = 100

TARGET_KEYS = {
    "Policy": "policy_id", "Employee": "employee_id", "Department": "department_id",
    "Project": "project_id", "Product": "product_id", "Company": "company_id",
}

CONSTRAINTS = (
    "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.chunk_id IS UNIQUE",
    "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:Document) REQUIRE d.doc_id IS UNIQUE",
    "CREATE CONSTRAINT policy_section_id IF NOT EXISTS FOR (s:PolicySection) REQUIRE s.section_id IS UNIQUE",
)


@dataclass
class IndexStats:
    chunks: Counter[tuple[str, str]]
    documents: int
    sections: int
    mentions: int
    planned_calls: int
    api_calls: int


def _batches(rows: Sequence[dict[str, Any]], size: int = BATCH) -> Iterator[Sequence[dict[str, Any]]]:
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


def planned_calls(corpus: Corpus, embedder: Embedder) -> int:
    return math.ceil(len(embedder.missing([c.text for c in corpus.chunks], "search_document")) / BATCH_SIZE)


def _merge_counted(tx: ManagedTransaction, cypher: str, rows: Sequence[dict[str, Any]], what: str) -> None:
    """Run a MATCH ... MERGE ... RETURN count(*) per batch; every row must find its nodes."""
    for batch in _batches(rows):
        n = tx.run(cypher, rows=list(batch)).single(strict=True)["n"]
        if n != len(batch):
            raise RuntimeError(f"{what}: {len(batch) - n} of {len(batch)} targets missing; run `make load`")


def _write(tx: ManagedTransaction, corpus: Corpus, vectors: list[list[float]]) -> None:
    docs = [{"doc_id": d.doc_id, "doc_type": d.doc_type, "path": d.path, "title": d.title,
             "label": d.describes_label, "target": d.describes_id} for d in corpus.docs]
    sections = [{"section_id": s.section_id, "policy_id": s.policy_id, "section_no": s.section_no,
                 "heading": s.heading} for s in corpus.sections]
    chunks = [{"chunk_id": c.chunk_id, "doc_id": c.doc_id, "section_id": c.section_id, "embedding": v,
               "props": {"doc_id": c.doc_id, "doc_type": c.doc_type, "section": c.section,
                         "part": c.part, "position": c.position, "heading": c.heading,
                         "text": c.text, "text_hash": c.text_hash, "sensitivity": c.sensitivity,
                         "subject_id": c.subject_id}}
              for c, v in zip(corpus.chunks, vectors, strict=True)]

    for label, ids in (("Chunk", [c["chunk_id"] for c in chunks]),
                       ("Document", [d["doc_id"] for d in docs]),
                       ("PolicySection", [s["section_id"] for s in sections])):
        key = {"Chunk": "chunk_id", "Document": "doc_id", "PolicySection": "section_id"}[label]
        tx.run(f"MATCH (n:{label}) WHERE NOT n.{key} IN $ids DETACH DELETE n", ids=ids)
    tx.run("MATCH (:Chunk)-[m:MENTIONS]->() DELETE m")

    for batch in _batches(docs):
        tx.run("UNWIND $rows AS r MERGE (d:Document {doc_id: r.doc_id}) "
               "SET d.doc_type = r.doc_type, d.path = r.path, d.title = r.title", rows=list(batch))
    for label, key in TARGET_KEYS.items():
        _merge_counted(tx, f"UNWIND $rows AS r MATCH (d:Document {{doc_id: r.doc_id}}) "
                           f"MATCH (t:{label} {{{key}: r.target}}) MERGE (d)-[:DESCRIBES]->(t) "
                           f"RETURN count(*) AS n", [d for d in docs if d["label"] == label],
                       f"DESCRIBES {label}")
    _merge_counted(tx, "UNWIND $rows AS r MATCH (p:Policy {policy_id: r.policy_id}) "
                       "MERGE (s:PolicySection {section_id: r.section_id}) "
                       "SET s.policy_id = r.policy_id, s.section_no = r.section_no, s.heading = r.heading "
                       "MERGE (p)-[:HAS_SECTION]->(s) RETURN count(*) AS n", sections, "HAS_SECTION")
    _merge_counted(tx, "UNWIND $rows AS r MATCH (d:Document {doc_id: r.doc_id}) "
                       "MERGE (c:Chunk {chunk_id: r.chunk_id}) SET c += r.props, c.embedding = r.embedding "
                       "MERGE (c)-[:PART_OF]->(d) RETURN count(*) AS n", chunks, "PART_OF")
    _merge_counted(tx, "UNWIND $rows AS r MATCH (c:Chunk {chunk_id: r.chunk_id}) "
                       "MATCH (s:PolicySection {section_id: r.section_id}) "
                       "MERGE (c)-[:OF_SECTION]->(s) RETURN count(*) AS n",
                   [c for c in chunks if c["section_id"]], "OF_SECTION")
    for label, key in TARGET_KEYS.items():
        rows = [{"chunk_id": c.chunk_id, "target": t.id}
                for c in corpus.chunks for t in c.mentions if t.label == label]
        _merge_counted(tx, f"UNWIND $rows AS r MATCH (c:Chunk {{chunk_id: r.chunk_id}}) "
                           f"MATCH (t:{label} {{{key}: r.target}}) MERGE (c)-[:MENTIONS]->(t) "
                           f"RETURN count(*) AS n", rows, f"MENTIONS {label}")


def _vector_dimension(session: Session) -> int | None:
    rows = session.run("SHOW INDEXES YIELD name, options WHERE name = $name RETURN options",
                       name=VECTOR_INDEX).data()
    return rows[0]["options"]["indexConfig"]["vector.dimensions"] if rows else None


def index(driver: Driver, embedder: Embedder, corpus: Corpus | None = None) -> IndexStats:
    corpus = corpus or build_corpus()
    planned = planned_calls(corpus, embedder)
    vectors = embedder.embed([c.text for c in corpus.chunks], "search_document")
    dim = int(embedder.dim)
    with driver.session() as session:
        for cypher in CONSTRAINTS:
            session.run(cypher).consume()
        if _vector_dimension(session) not in (None, dim):
            session.run(f"DROP INDEX {VECTOR_INDEX}").consume()
        session.execute_write(_write, corpus, vectors)
        session.run(
            f"CREATE VECTOR INDEX {VECTOR_INDEX} IF NOT EXISTS FOR (c:Chunk) ON c.embedding "
            f"OPTIONS {{indexConfig: {{`vector.dimensions`: {dim}, "
            f"`vector.similarity_function`: 'cosine'}}}}").consume()
        session.run(f"CREATE FULLTEXT INDEX {FULLTEXT_INDEX} IF NOT EXISTS "
                    f"FOR (c:Chunk) ON EACH [c.text]").consume()
        session.run("CALL db.awaitIndexes(300)").consume()
    return IndexStats(
        chunks=Counter((c.doc_type, c.sensitivity) for c in corpus.chunks),
        documents=len(corpus.docs), sections=len(corpus.sections),
        mentions=sum(len(c.mentions) for c in corpus.chunks),
        planned_calls=planned, api_calls=embedder.api_calls)


def print_chunk_table(counts: Counter[tuple[str, str]]) -> None:
    types = sorted({t for t, _ in counts})
    print(f"  {'doc_type':<11}{'public':>8}{'restricted':>12}{'total':>8}")
    for t in types:
        pub, res = counts[(t, "public")], counts[(t, "restricted")]
        print(f"  {t:<11}{pub:>8}{res:>12}{pub + res:>8}")
    pub = sum(n for (_, s), n in counts.items() if s == "public")
    res = sum(n for (_, s), n in counts.items() if s == "restricted")
    print(f"  {'TOTAL':<11}{pub:>8}{res:>12}{pub + res:>8}")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="chunk and plan only: no API calls, no writes")
    args = parser.parse_args(argv)
    corpus = build_corpus()
    embedder = Embedder.from_settings()
    print(f"Embedding model {embedder.model}, dimension {embedder.dim}, cache {embedder.path}")
    print(f"Documents {len(corpus.docs)}, PolicySections {len(corpus.sections)}, "
          f"MENTIONS {sum(len(c.mentions) for c in corpus.chunks)}")
    print("Chunks by type and sensitivity (from files):")
    print_chunk_table(Counter((c.doc_type, c.sensitivity) for c in corpus.chunks))
    missing = len(embedder.missing([c.text for c in corpus.chunks], "search_document"))
    print(f"Texts not cached: {missing}; planned API calls: {planned_calls(corpus, embedder)} "
          f"(batch size {BATCH_SIZE})")
    if args.dry_run:
        return
    driver = get_driver()
    try:
        stats = index(driver, embedder, corpus)
        print(f"Cohere API calls made: {stats.api_calls}")
        rows = run_read(driver, "MATCH (c:Chunk) RETURN c.doc_type AS t, c.sensitivity AS s, count(*) AS n")
        print("Chunks in graph:")
        print_chunk_table(Counter({(r["t"], r["s"]): r["n"] for r in rows}))
        nodes = run_read(driver, "MATCH (n) WHERE n:Document OR n:PolicySection OR n:Chunk "
                                 "RETURN labels(n)[0] AS l, count(*) AS n ORDER BY l")
        rels = run_read(driver, "MATCH ()-[r:PART_OF|DESCRIBES|HAS_SECTION|OF_SECTION|MENTIONS]->() "
                                "RETURN type(r) AS t, count(*) AS n ORDER BY t")
        print("Nodes: " + ", ".join(f"{r['l']} {r['n']}" for r in nodes))
        print("Relationships: " + ", ".join(f"{r['t']} {r['n']}" for r in rels))
    finally:
        driver.close()


if __name__ == "__main__":
    main()
