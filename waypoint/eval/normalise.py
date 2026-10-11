"""Answer normalisation for exact match and entity spotting.

Lower-case; '&' -> 'and'; '₹' / 'Rs.' -> 'inr'; '%' -> 'percent'; dates to ISO
(18 Oct 2026, October 18, 2026 -> 2026-10-18); thousands separators dropped
(1,00,000 -> 100000); number words 0-20 to digits; every other punctuation mark
splits tokens. The result is space-joined tokens, so a whole-token span check is
`f" {key} " in f" {text} "`.
"""
from __future__ import annotations

import re

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_MONTH = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
_DAY_FIRST = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+{_MONTH},?\s+(\d{{4}})\b", re.I)
_MONTH_FIRST = re.compile(rf"\b{_MONTH}\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I)
_TOKEN = re.compile(r"\d{4}-\d{2}-\d{2}|\d+(?:\.\d+)?|[^\W\d_]+")
_WORDS = ("zero one two three four five six seven eight nine ten eleven twelve thirteen "
          "fourteen fifteen sixteen seventeen eighteen nineteen twenty").split()
_NUMBER_WORDS = {w: str(i) for i, w in enumerate(_WORDS)}


def _iso(day: str, month: str, year: str) -> str:
    return f"{year}-{_MONTHS[month[:3].lower()]:02d}-{int(day):02d}"


def normalise(text: str) -> str:
    s = _DAY_FIRST.sub(lambda m: f" {_iso(m[1], m[2], m[3])} ", text)
    s = _MONTH_FIRST.sub(lambda m: f" {_iso(m[2], m[1], m[3])} ", s)
    s = s.replace("&", " and ").replace("₹", " inr ").replace("%", " percent ")
    s = re.sub(r"\brs\.?\s*(?=\d)", " inr ", s, flags=re.I)
    s = re.sub(r"(?<=\d),(?=\d)", "", s)
    return " ".join(_NUMBER_WORDS.get(t, t) for t in _TOKEN.findall(s.lower()))


def contains(text_norm: str, key_norm: str) -> bool:
    """Whole-token span match on two normalised strings."""
    return bool(key_norm) and f" {key_norm} " in f" {text_norm} "
