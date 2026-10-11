"""Mapping citations and the `sources` column to entity ids (PLAN 1.4)."""
from __future__ import annotations

import pytest

from waypoint.contract import ChunkCitation, GraphCitation, PolicyCitation
from waypoint.eval.questions import read_all_questions
from waypoint.eval.sources import citation_entities, gold_sources, source_metrics

Q = {q.id: q for q in read_all_questions()}


@pytest.mark.parametrize("citation, expected", [
    (PolicyCitation(type="policy", id="ZEN-POL-002", section=4), {"ZEN-POL-002"}),
    (GraphCitation(type="graph", path="ZV-1042 -WORKS_IN-> D03"), {"ZV-1042", "D03"}),
    (GraphCitation(type="graph", path="ZV-1013 <-REPORTS_TO- ZV-1042 -WORKED_ON-> PJ01"),
     {"ZV-1013", "ZV-1042", "PJ01"}),
    (GraphCitation(type="graph", path="ZEN-POL-001 -REFERENCES-> ZEN-DPL-FIN-01"),
     {"ZEN-POL-001", "ZEN-DPL-FIN-01"}),
    (ChunkCitation(type="chunk", id="ZEN-POL-002::4::0"), {"ZEN-POL-002"}),
    (ChunkCitation(type="chunk", id="profile:ZV-1042::about::restricted"), {"ZV-1042"}),
    (ChunkCitation(type="chunk", id="resume:ZV-1001::job-2::0"), {"ZV-1001"}),
    (ChunkCitation(type="chunk", id="dept:D03::page::0"), {"D03"}),
    (ChunkCitation(type="chunk", id="project:PJ04::page::0"), {"PJ04"}),
    (ChunkCitation(type="chunk", id="product:PR01::page::0"), {"PR01"}),
    (ChunkCitation(type="chunk", id="company:06_all_hands_notes_2026-09-04::intro::0"), set()),
])
def test_citation_entities(citation, expected: set[str]) -> None:  # noqa: ANN001
    assert citation_entities(citation) == expected


def test_gold_sources_plain_ids() -> None:
    assert gold_sources(Q["Q084"]) == {"ZV-1002", "ZV-1001", "D00"}
    assert gold_sources(Q["Q173"]) == {"ZV-1042", "ZEN-POL-002"}


def test_gold_sources_resumes_expand_to_named_people() -> None:
    assert gold_sources(Q["Q146"]) == {"ZV-1018", "ZV-1038"}  # Mohan Krishna; Swathi Kamat
    assert gold_sources(Q["Q169"]) == {"ZV-1001", "ZV-1002", "ZV-1003"}  # employees.csv


def test_every_question_has_resolvable_gold_sources() -> None:
    assert all(gold_sources(q) for q in Q.values())


def test_source_metrics() -> None:
    gold = {"ZV-1042", "ZEN-POL-002"}
    cites = [PolicyCitation(type="policy", id="ZEN-POL-002", section=4),
             GraphCitation(type="graph", path="ZV-1042 -WORKS_IN-> D03"),
             ChunkCitation(type="chunk", id="ZEN-POL-003::5::0")]
    recall, precision = source_metrics(gold, cites)
    assert recall == 1.0 and precision == pytest.approx(2 / 3)
    assert source_metrics(gold, []) == (0.0, None)
