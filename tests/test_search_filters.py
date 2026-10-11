"""text_search filters (PLAN 2.4): doc_type and entity_id narrow chunk search, public only."""
from __future__ import annotations

import pytest
from neo4j import Driver

from waypoint.retrieval.search import DOC_TYPES, doc_ids_for, search_fulltext, search_text

pytestmark = pytest.mark.neo4j


class FlatEmbedder:
    """Any fixed vector: the filter, not the ranking, is under test. No API call."""

    def embed_query(self, text: str) -> list[float]:
        return [1.0] * 1024


def test_doc_ids_for_entities(driver: Driver) -> None:
    assert doc_ids_for(driver, "D03") == ["dept:D03"]
    assert doc_ids_for(driver, "PJ01") == ["project:PJ01"]
    assert doc_ids_for(driver, "ZEN-POL-004") == ["ZEN-POL-004"]
    assert doc_ids_for(driver, "ZV-1042") == ["profile:ZV-1042", "resume:ZV-1042"]
    assert doc_ids_for(driver, "ZEN-POL-099") == []


@pytest.mark.parametrize("search", ["vector", "fulltext"])
def test_doc_type_filter(driver: Driver, search: str) -> None:
    for doc_type in ("department", "project", "policy"):
        hits = (search_text("team goals", k=5, doc_type=doc_type, driver=driver, embedder=FlatEmbedder())
                if search == "vector" else search_fulltext("team", k=5, doc_type=doc_type, driver=driver))
        assert hits and {h["doc_type"] for h in hits} == {doc_type}


@pytest.mark.parametrize("search", ["vector", "fulltext"])
def test_entity_filter_one_policy_or_page(driver: Driver, search: str) -> None:
    for entity, doc_ids in (("ZEN-POL-004", {"ZEN-POL-004"}), ("D03", {"dept:D03"}), ("PJ01", {"project:PJ01"})):
        hits = (search_text("warning", k=20, entity_id=entity, driver=driver, embedder=FlatEmbedder())
                if search == "vector" else search_fulltext("the", k=20, entity_id=entity, driver=driver))
        assert hits and {h["doc_id"] for h in hits} <= doc_ids, entity
    policy_hits = search_text("x", k=50, entity_id="ZEN-POL-004", driver=driver, embedder=FlatEmbedder())
    assert len({h["section"] for h in policy_hits}) > 3  # one policy's sections, not just one chunk


def test_unknown_entity_gives_no_hits(driver: Driver) -> None:
    assert search_text("x", entity_id="ZEN-POL-099", driver=driver, embedder=FlatEmbedder()) == []
    assert search_fulltext("leave", entity_id="ZV-9999", driver=driver) == []


def test_filters_stay_public_only(driver: Driver) -> None:
    # Pooja's profile carries a restricted (leave) chunk; a filtered search must not return it.
    hits = search_text("employment status leave", k=50, entity_id="ZV-1031", driver=driver, embedder=FlatEmbedder())
    hits += search_fulltext("leave", k=50, entity_id="ZV-1031", driver=driver)
    hits += search_text("status", k=50, doc_type="profile", driver=driver, embedder=FlatEmbedder())
    assert hits and {h["sensitivity"] for h in hits} == {"public"}


def test_bad_doc_type_fails_loudly(driver: Driver) -> None:
    assert "department" in DOC_TYPES
    with pytest.raises(ValueError, match="doc_type"):
        search_text("x", doc_type="salary", driver=driver, embedder=FlatEmbedder())
