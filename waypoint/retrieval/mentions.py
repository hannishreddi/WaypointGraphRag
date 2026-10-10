"""Deterministic MENTIONS: exact ids, full names and policy codes from the CSVs. PLAN 1.3.

Rule: one regex of every term, longest first, each wrapped in (?<![\\w-])TERM(?![\\w-]),
matched case-sensitively without overlaps. Longest first makes the department
"Customer Support (Zenvora Care)" win over the product "Zenvora Care" it contains.
Misses (slice 2.1 adds aliases): first names, titles, short names ("Pulse", "HR",
"Atlas"), department codes ("CSC"), pronouns, lowercase or misspelled names, and
organisations and skills, which are not targets here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache

from waypoint.graph.load import read_csv


@dataclass(frozen=True)
class Target:
    label: str
    key: str
    id: str


# (csv, label, id column, name column or None)
_SOURCES = (
    ("employees", "Employee", "employee_id", "full_name"),
    ("departments", "Department", "department_id", "name"),
    ("projects", "Project", "project_id", "name"),
    ("products", "Product", "product_id", "name"),
    ("policies", "Policy", "policy_id", None),
)


@cache
def lookup() -> dict[str, Target]:
    """Term -> target. Fails loudly if two entities share a term."""
    terms: dict[str, Target] = {}
    for table, label, id_col, name_col in _SOURCES:
        for r in read_csv(table):
            target = Target(label, id_col, r[id_col])
            for term in (r[id_col], r[name_col] if name_col else None):
                if not term:
                    continue
                if terms.setdefault(term, target) != target:
                    raise ValueError(f"ambiguous mention term {term!r}")
    return terms


@cache
def _pattern() -> re.Pattern[str]:
    alternatives = "|".join(re.escape(t) for t in sorted(lookup(), key=len, reverse=True))
    return re.compile(rf"(?<![\w-])(?:{alternatives})(?![\w-])")


def find_mentions(text: str) -> tuple[Target, ...]:
    """Distinct targets in order of first appearance."""
    terms = lookup()
    return tuple(dict.fromkeys(terms[m.group(0)] for m in _pattern().finditer(text)))


def employee_names() -> dict[str, str]:
    """Full name -> employee_id."""
    return {r["full_name"]: r["employee_id"] for r in read_csv("employees")}
