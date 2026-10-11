"""`link_entities(text)`: deterministic entity linking over the alias table. PLAN 2.1.

Pure Python, no LLM. Every alias is matched with word boundaries (?<![\\w-])...(?![\\w-]),
so "ZEN-POL-0040" and the "HR" inside "ZEN-DPL-HR-01" do not match. Candidates are
taken longest first (ties: earlier start, then alias kind), and a candidate that
overlaps an accepted span is dropped. Results are in text order.

Restricted aliases (common English words, see `aliases`) link only when
- a context word follows (team, project, department, dept, product, skill), in any case; or
- the text matches the alias case exactly, is capitalised, is not right after
  "the" / "a" / "an", is not glued to another capitalised word (part of a longer
  proper name: "Finwise Analytics", "Atlas Systems"; a sentence's first word does not
  count), and, for "generic" aliases, is not the first word of a sentence.
So "the Atlas of the world", "Data retention ...", "Finwise Analytics" and lowercase
"data" do not link, while "Who worked on Atlas?", "Atlas was ..." and "the data team" do.

`link_mentions(text)` (2.4) adds the unresolved mentions: tokens shaped like an id
(ZEN-POL-099, ZV-9999, D99, PJ99) that are not in the alias table, so downstream can
answer "no such policy/person" instead of guessing. ZEN-/ZV- codes match in any case;
the short codes (D99, PJ99, PR07, L09, ORG099, SK999) only in upper case.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache

from waypoint.retrieval.aliases import KIND_PRIORITY, Alias, alias_table, canonical_skill

CONTEXT_WORDS = frozenset({"team", "teams", "project", "projects", "department", "dept",
                           "product", "skill", "skills"})
ALT_CONTEXT_WORDS = frozenset({"team", "teams", "department", "dept"})
ARTICLES = frozenset({"the", "a", "an"})
_NEXT_WORD = re.compile(r"[ \t]+([A-Za-z]+)")
_PREV_WORD = re.compile(r"([A-Za-z]+)[ \t]+$")
_SENTENCE_END = re.compile(r"(?:^|[.!?:;\n\"(])\s*$")


@dataclass(frozen=True)
class EntityMatch:
    id: str
    label: str
    surface: str
    start: int
    end: int
    canonical_id: str  # merged skill id for skills; equals id otherwise


@dataclass(frozen=True)
class UnresolvedMention:
    surface: str
    label: str  # the entity type the id shape implies
    start: int
    end: int


@dataclass(frozen=True)
class LinkResult:
    matches: tuple[EntityMatch, ...]
    unresolved: tuple[UnresolvedMention, ...]


_B, _E = r"(?<![\w-])", r"(?![\w-])"
ID_SHAPES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Policy", re.compile(rf"{_B}ZEN-(?:POL-\d+|DPL-[A-Z]{{2,4}}-\d+){_E}", re.IGNORECASE)),
    ("Employee", re.compile(rf"{_B}ZV-\d+{_E}", re.IGNORECASE)),
    ("Department", re.compile(rf"{_B}D\d{{2,}}{_E}")),
    ("Project", re.compile(rf"{_B}PJ\d+{_E}")),
    ("Product", re.compile(rf"{_B}PR\d+{_E}")),
    ("Location", re.compile(rf"{_B}L\d{{2,}}{_E}")),
    ("Organization", re.compile(rf"{_B}ORG\d+{_E}")),
    ("Skill", re.compile(rf"{_B}SK\d+{_E}")),
)


@cache
def _compiled() -> list[tuple[Alias, re.Pattern[str]]]:
    out = []
    for a in alias_table().aliases:
        body = r"\s+".join(re.escape(w) for w in a.text.split())
        flags = re.IGNORECASE if a.ignore_case or a.restrict else 0
        out.append((a, re.compile(rf"(?<![\w-]){body}(?![\w-])", flags)))
    return out


def _next_word(text: str, end: int, *, raw: bool = False) -> str:
    m = _NEXT_WORD.match(text, end)
    return (m[1] if raw else m[1].lower()) if m else ""


def _in_proper_name(text: str, start: int, end: int) -> bool:
    """A capitalised word right before (not sentence-initial) or right after the span."""
    if _next_word(text, end, raw=True)[:1].isupper():
        return True
    prev = _PREV_WORD.search(text, 0, start)
    return bool(prev and prev[1][0].isupper() and not _SENTENCE_END.search(text, 0, prev.start()))


def _allowed(alias: Alias, text: str, start: int, end: int) -> bool:
    if not alias.restrict:
        return True
    if _next_word(text, end) in CONTEXT_WORDS:
        return True
    surface = text[start:end]
    if surface != alias.text or not surface[0].isupper():
        return False
    before = text[:start]
    prev = _PREV_WORD.search(before)
    if prev and prev[1].lower() in ARTICLES:
        return False
    if _in_proper_name(text, start, end):
        return False
    if alias.restrict == "generic" and _SENTENCE_END.search(before):
        return False
    return True


def link_entities(text: str) -> list[EntityMatch]:
    """Entities named in `text`, non-overlapping, in text order."""
    candidates: list[tuple[int, int, Alias]] = []
    for alias, pattern in _compiled():
        for m in pattern.finditer(text):
            if _allowed(alias, text, m.start(), m.end()):
                candidates.append((m.start(), m.end(), alias))
    candidates.sort(key=lambda c: (c[0] - c[1], c[0], KIND_PRIORITY[c[2].kind]))
    taken: list[tuple[int, int]] = []
    matches: list[EntityMatch] = []
    for start, end, alias in candidates:
        if any(start < e and s < end for s, e in taken):
            continue
        taken.append((start, end))
        label, eid = alias.label, alias.id
        if alias.alt and _next_word(text, end) in ALT_CONTEXT_WORDS:
            label, eid = alias.alt
        canonical = canonical_skill(eid) if label == "Skill" else eid
        matches.append(EntityMatch(eid, label, text[start:end], start, end, canonical))
    return sorted(matches, key=lambda m: m.start)


def link_mentions(text: str) -> LinkResult:
    """`link_entities` plus id-shaped tokens that match no known entity."""
    matches = tuple(link_entities(text))
    unresolved = []
    for label, pattern in ID_SHAPES:
        for m in pattern.finditer(text):
            if not any(m.start() < x.end and x.start < m.end() for x in matches):
                unresolved.append(UnresolvedMention(m.group(), label, m.start(), m.end()))
    return LinkResult(matches, tuple(sorted(unresolved, key=lambda u: u.start)))
