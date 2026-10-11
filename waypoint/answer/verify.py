"""Verifier (PLAN 2.5, CLAUDE.md rule 5): deterministic, no LLM.

An answer passes when
- it cites at least one id (unless it is the not-found reply) and every cited id is an
  item of the context pack;
- every name in it appears in the evidence (the rendered pack plus the question): the
  entities `link_entities` finds (by id or by the surface text) and every run of two or
  more Capitalised words (a leading sentence word may be dropped);
- every number appears in the evidence by value, after normalisation: Indian and Western
  digit grouping (1,00,000 = 100,000), lakh/crore/k, ordinals (3rd), number words
  (two .. ninety-nine, hundred; "one" and "zero" are skipped, they are mostly not
  numbers), currency and units ignored (INR 25,000 = Rs 25,000 = 25000 days alike);
- every date appears in the evidence: 18 October 2026, 18 Oct, October 18, 2026,
  2026-10-18 and 18/10/2026 are one date; a date without a year or day matches any
  evidence date with the same month and the parts it does give.
Ids (ZV-1001, ZEN-POL-002, chunk ids) are removed before numbers are read; letter-
prefixed codes (D05, Z7, PJ01) never count as numbers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from waypoint.answer.pack import ContextPack
from waypoint.retrieval.linking import link_entities

VERSION = "verify-v1"  # part of S5's config_id: a change re-answers checkpointed questions
Date = tuple[int | None, int, int | None]  # (year, month, day)

_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9,
           "oct": 10, "nov": 11, "dec": 12}
_MON = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?"
        r"|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)")
_ORD = r"(?:st|nd|rd|th)?"
# (regex, group order) ; months are case-sensitive Capitalised so "may" the verb is no date
_DATE_RES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)"), "ymd"),
    (re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)"), "dmy"),
    (re.compile(rf"(?<!\d)(\d{{1,2}}){_ORD}(?:\s+of)?\s+({_MON})\.?(?:,?\s+(\d{{4}}))?(?!\d)"), "dMy"),
    (re.compile(rf"\b({_MON})\.?\s+(\d{{4}})(?!\d)"), "My"),
    (re.compile(rf"\b({_MON})\.?\s+(\d{{1,2}}){_ORD}(?!\d)(?:,?\s+(\d{{4}}))?"), "Mdy"),
]
_ID = re.compile(r"\S+::\S+|\b(?:ZV-\d+|ZEN(?:-[A-Z]+)+-\d+)\b", re.IGNORECASE)
_SCALED = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(lakhs?|lacs?|crores?|k)\b", re.IGNORECASE)
_SCALE = {"l": 1e5, "c": 1e7, "k": 1e3}
_NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{2,3})+|\d+)(\.\d+)?(?:st|nd|rd|th)?(?!\d)")
_UNITS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if i > 1}
_WORD_NUM = re.compile(
    rf"\b({'|'.join(_TENS)})(?:[\s-]({'|'.join(list(_UNITS)[1:10])}))?\b|\b({'|'.join(_UNITS)}|hundred)\b",
    re.IGNORECASE)
_SKIP_WORDS = {"zero", "one"}

_CAP = r"[A-Z][\w'’&.\-]*"
_PHRASE = re.compile(rf"{_CAP}(?:(?:\s+(?:of|and|&|for|the|de|da|van)\s+|\s+){_CAP})+")
_LEADING = {"yes", "no", "the", "a", "an", "i", "in", "on", "at", "as", "for", "from", "your", "you", "my",
            "this", "that", "since", "until", "per", "under", "both", "each", "all", "only", "ask", "contact",
            "and", "or", "but", "so", "also", "if", "when", "after", "before", "with", "to", "by", "it"}


@dataclass
class Verdict:
    ok: bool
    issues: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- normalisation

def norm_text(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'").replace("&", " and ").casefold()
    return re.sub(r"\s+", " ", text).strip()


def _month(s: str) -> int:
    return _MONTHS[s[:3].lower()]


def extract_dates(text: str) -> tuple[list[Date], str]:
    """Dates in the text, and the text with them blanked out."""
    found: list[Date] = []

    def take(order: str) -> object:
        def sub(m: re.Match[str]) -> str:
            g = dict(zip(order, m.groups(), strict=True))
            y = int(g["y"]) if g.get("y") else None
            mon = _month(g["M"]) if "M" in g else int(g["m"])
            d = int(g["d"]) if g.get("d") else None
            if 1 <= mon <= 12 and (d is None or 1 <= d <= 31):
                found.append((y, mon, d))
                return " "
            return m.group(0)
        return sub

    for rx, order in _DATE_RES:
        text = rx.sub(take(order), text)  # type: ignore[arg-type]
    return found, text


def extract_numbers(text: str) -> set[float]:
    """Numeric values in text that has had its dates removed. Ids are dropped first."""
    text = _ID.sub(" ", text)
    out: set[float] = set()

    def scaled(m: re.Match[str]) -> str:
        out.add(round(float(m[1]) * _SCALE[m[2][0].lower()], 4))
        return " "

    text = _SCALED.sub(scaled, text)
    for m in _NUM.finditer(text):
        out.add(round(float(m[1].replace(",", "") + (m[2] or "")), 4))
    for m in _WORD_NUM.finditer(text):
        if m[1]:
            out.add(float(_TENS[m[1].lower()] + (_UNITS[m[2].lower()] if m[2] else 0)))
        elif m[3].lower() == "hundred":
            out.add(100.0)
        elif m[3].lower() not in _SKIP_WORDS:
            out.add(float(_UNITS[m[3].lower()]))
    return out


def date_supported(d: Date, evidence: list[Date]) -> bool:
    y, mon, day = d
    return any(e[1] == mon and (y is None or e[0] is None or e[0] == y) and (day is None or e[2] == day)
               for e in evidence)


def names(text: str) -> list[str]:
    """Runs of two or more Capitalised words (possessive 's removed)."""
    out = []
    for m in _PHRASE.finditer(text):
        words = re.sub(r"['’]s\b", "", m.group(0)).rstrip(".").split()
        while words and words[0].lower().strip(".,") in _LEADING:
            words = words[1:]
        if len(words) >= 2:
            out.append(" ".join(words))
    return out


# ---------------------------------------------------------------- verify

def _name_supported(name: str, ev: str) -> bool:
    if norm_text(name) in ev:
        return True
    rest = name.split()[1:]  # the first word may just start the sentence
    return len(rest) >= 1 and norm_text(" ".join(rest)) in ev and (len(rest) >= 2 or len(rest[0]) > 2)


def verify(answer: str, cited_ids: list[str], pack: ContextPack, *, not_found: str = "") -> Verdict:
    issues: list[str] = []
    ids = set(pack.ids())
    issues += [f"cited id {c!r} is not a context item" for c in cited_ids if c not in ids]
    if not cited_ids and answer.strip() != not_found:
        issues.append("no context item is cited")

    raw = f"{pack.render()}\n{pack.question}\n{pack.as_of.isoformat()}"
    ev = norm_text(raw)
    for m in link_entities(answer):
        if m.id not in raw and norm_text(m.surface) not in ev:
            issues.append(f"entity {m.surface!r} ({m.id}) is not in the context")
    for name in names(answer):
        if not _name_supported(name, ev):
            issues.append(f"name {name!r} is not in the context")

    a_dates, a_rest = extract_dates(answer)
    e_dates, e_rest = extract_dates(raw)
    issues += [f"date {_fmt(d)} is not in the context" for d in a_dates if not date_supported(d, e_dates)]
    e_nums = extract_numbers(e_rest) | {float(x) for d in e_dates for x in d if x is not None}
    for n in sorted(extract_numbers(a_rest) - e_nums):
        issues.append(f"number {n:g} is not in the context")
    return Verdict(not issues, list(dict.fromkeys(issues)))


def _fmt(d: Date) -> str:
    y, m, day = d
    return "-".join(f"{x:02d}" if x is not None else "?" for x in (y, m, day))
