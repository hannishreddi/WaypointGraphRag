"""Known entities from the CSVs, for scoring lists and spotting extra names in answers.

Aliases (normalised): employee full names; department names and, when unique, the
name without its parenthetical ("Customer Support"); project names and the bare
name ("Atlas"); policy ids and titles; product names. First names wait for PLAN 2.1.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from waypoint.eval.normalise import normalise
from waypoint.graph.load import read_csv


@dataclass
class Entities:
    by_name: dict[str, tuple[str, str]] = field(default_factory=dict)  # exact CSV name -> (type, id)
    by_alias: dict[str, tuple[str, str]] = field(default_factory=dict)  # normalised alias -> (type, id)
    names: dict[str, str] = field(default_factory=dict)  # id -> display name

    def add(self, etype: str, eid: str, name: str, *aliases: str) -> None:
        self.by_name[name] = (etype, eid)
        self.names[eid] = name
        for alias in (name, *aliases):
            key = normalise(alias)
            if key and self.by_alias.setdefault(key, (etype, eid)) != (etype, eid):
                raise ValueError(f"alias {alias!r} is ambiguous")

    def resolve(self, text: str) -> tuple[str, str] | None:
        """(type, id) for an exact CSV name or id, also with a trailing '(...)' gloss removed."""
        text = text.strip()
        stripped = re.sub(r"\s*\(.*\)$", "", text)
        return self.by_name.get(text) or self.by_name.get(stripped)

    def find(self, text: str, etype: str | None = None) -> set[str]:
        """Ids of entities named in `text`; longest aliases claim tokens first."""
        tokens = normalise(text).split()
        used = [False] * len(tokens)
        found: set[str] = set()
        for alias in sorted(self.by_alias, key=lambda a: (-len(a.split()), a)):
            atoks = alias.split()
            n = len(atoks)
            for i in range(len(tokens) - n + 1):
                if tokens[i:i + n] == atoks and not any(used[i:i + n]):
                    used[i:i + n] = [True] * n
                    t, eid = self.by_alias[alias]
                    if etype is None or t == etype:
                        found.add(eid)
        return found


@lru_cache
def load_entities() -> Entities:
    ents = Entities()
    for r in read_csv("employees"):
        ents.add("employee", r["employee_id"], r["full_name"], r["employee_id"])
    depts = read_csv("departments")
    short = [re.sub(r"\s*\(.*\)$", "", r["name"]) for r in depts]
    for r, s in zip(depts, short):
        extra = (s,) if s != r["name"] and short.count(s) == 1 else ()
        ents.add("department", r["department_id"], r["name"], *extra)
    for r in read_csv("projects"):
        ents.add("project", r["project_id"], r["name"], r["name"].removeprefix("Project "))
    for r in read_csv("policies"):
        ents.add("policy", r["policy_id"], r["policy_id"], r["title"])
    for r in read_csv("products"):
        ents.add("product", r["product_id"], r["name"])
    return ents
