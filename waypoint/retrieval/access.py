"""Access filter for text retrieval (CLAUDE.md rule 6, PLAN 2.5).

A restricted chunk states one person's employment status, leave or notice and carries
that person's id as `subject_id`. It is returned only when `can_see_restricted` allows
the asker: the subject themselves, the subject's direct manager, or HR. The decision is
made here, per hit, in the retrieval layer; prompts never see a chunk the asker may not
see. Template rows are public-only by construction (waypoint.graph.templates).

`search_for_asker` over-fetches by the number of restricted chunks, so k visible hits
survive the filter.
"""
from __future__ import annotations

from neo4j import Driver

from waypoint.retrieval.search import Hit, QueryEmbedder, _driver, restricted_count, search_text
from waypoint.rules.engine import can_see_restricted
from waypoint.rules.facts import FactStore, facts_from_csv


def visible(hit: Hit, asker_id: str, facts: FactStore) -> bool:
    if hit.get("sensitivity") == "public":
        return True
    subject = hit.get("subject_id")
    return bool(subject) and can_see_restricted(subject, asker_id, facts)


def filter_hits(hits: list[Hit], asker_id: str, facts: FactStore | None = None) -> list[Hit]:
    facts = facts if facts is not None else facts_from_csv()
    return [h for h in hits if visible(h, asker_id, facts)]


def search_for_asker(query: str, asker_id: str, k: int = 5, *, doc_type: str | None = None,
                     entity_id: str | None = None, driver: Driver | None = None,
                     embedder: QueryEmbedder | None = None, facts: FactStore | None = None) -> list[Hit]:
    """Top-k chunks the asker may see: public ones, plus restricted ones about a person
    the asker is, manages directly, or (as HR) may see."""
    with _driver(driver) as drv:
        hits = search_text(query, k=k + restricted_count(drv), include_restricted=True, doc_type=doc_type,
                           entity_id=entity_id, driver=drv, embedder=embedder)
    return filter_hits(hits, asker_id, facts)[:k]
