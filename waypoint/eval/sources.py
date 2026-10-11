"""Source recall and citation precision (PLAN 1.4).

The `sources` column holds entity ids (ZV-xxxx, ZEN-POL-xxx, ZEN-DPL-XXX-nn, Dnn,
PJnn, Lnn), plus "resumes" (37 rows) and "employees.csv" (1 row), which stand for
the people named in the gold answer. Every citation is mapped to the entity ids
it touches:
  policy {id, section}               -> {id}
  graph {path}                       -> every entity id in the path
  chunk "<doc_id>::<sec>::<part>"    -> the entity the document describes:
      ZEN-...            -> policy id      profile:/resume:ZV-x -> ZV-x
      dept:Dnn -> Dnn    project:PJnn -> PJnn    product:PRnn -> PRnn
      company:*          -> nothing
Source recall = |gold & cited| / |gold|. Citation precision = share of citations
touching at least one gold id; a lower bound, since a legitimate supporting
citation (e.g. a BASED_AT edge on a project question) can count against it.
"""
from __future__ import annotations

import re
from collections.abc import Sequence

from waypoint.contract import ChunkCitation, Citation, GraphCitation, PolicyCitation
from waypoint.eval.entities import load_entities
from waypoint.eval.questions import Question

ID_RE = re.compile(r"\b(?:ZV-\d{4}|ZEN-POL-\d{3}|ZEN-DPL-[A-Z]+-\d{2}|PJ\d{2}|PR\d{2}|D\d{2}|L\d{2})\b")
_DOC_PREFIXES = {"profile", "resume", "dept", "project", "product"}
_PEOPLE_SOURCES = {"resumes", "employees.csv"}


def citation_entities(c: Citation) -> set[str]:
    if isinstance(c, PolicyCitation):
        return {c.id}
    if isinstance(c, GraphCitation):
        return set(ID_RE.findall(c.path))
    if isinstance(c, ChunkCitation):
        doc_id = c.id.split("::", 1)[0]
        if ":" in doc_id:
            prefix, ident = doc_id.split(":", 1)
            return {ident} if prefix in _DOC_PREFIXES else set()
        return {doc_id} if ID_RE.fullmatch(doc_id) else set()
    raise TypeError(f"unknown citation {c!r}")


def gold_sources(q: Question) -> set[str]:
    gold: set[str] = set()
    for s in q.sources:
        if s in _PEOPLE_SOURCES:
            gold |= load_entities().find(q.expected_answer, "employee")
        else:
            gold.add(s)
    return gold


def source_metrics(gold: set[str], citations: Sequence[Citation]) -> tuple[float, float | None]:
    """(source recall, citation precision); precision is None without citations."""
    per_citation = [citation_entities(c) for c in citations]
    cited = set().union(*per_citation)
    recall = len(gold & cited) / len(gold) if gold else 0.0
    precision = sum(bool(e & gold) for e in per_citation) / len(per_citation) if per_citation else None
    return recall, precision
