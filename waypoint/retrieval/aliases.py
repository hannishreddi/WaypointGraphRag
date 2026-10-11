"""Alias table for entity linking, built from the CSVs only. PLAN 2.1.

Sources: employees, departments, projects, products, policies, skills.

- Case-insensitive ("full names and ids"): employee full names, every id, policy codes,
  department / project / product full names, policy titles.
- Case-sensitive: first names (only when unique among employees), unique titles and
  the acronyms derived from them (CEO from "Chief Executive Officer", CISO from
  "(CISO)"), department codes and short names, project and product short names
  ("Atlas", "Pulse"), skill names.
- Restricted (common English words; see `linking`): single-word project / product
  short names ("codename": no link after an article unless a context word follows),
  single-word department short names and common-word skills ("generic": also no
  link at the start of a sentence). A context word after the alias ("data team",
  "Horizon project") always links, in any case.
- Collisions: an alias that names two entities is dropped and reported, except a
  product vs a department ("Zenvora Care"): the product keeps it and the department
  wins when followed by team / department / dept (`Alias.alt`).
- Skills: "X (Y)" merges into "X" when X is a skill; word-suffix variants
  ("Python scripting") merge only through the explicit SKILL_MERGES map. Links keep
  the literal skill id (the dev gold lists skill holders literally);
  `canonical_skill` / `skill_variants` give the merged group.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import cache
from typing import Literal

from waypoint.graph.load import read_csv

Restrict = Literal["codename", "generic"] | None

# Short department names seen in the corpus ("Support Team", "Care team", "backend
# team") or natural in questions, beyond what the name itself splits into.
DEPT_SHORT = {
    "D01": ("People",),
    "D03": ("Backend",),
    "D04": ("Mobile",),
    "D06": ("QA",),
    "D10": ("Support", "Customer Care", "Care"),
    "D11": ("Security",),
}

# Word-suffix skill variants that really are the same skill (checked by hand).
SKILL_MERGES = {
    "Python scripting": "Python",
    "PostgreSQL tuning": "PostgreSQL",
    "Pulse inbox administration": "Pulse inbox",
}
# Word-suffix candidates that are different skills, with the reason.
REJECTED_SKILL_MERGES = {
    "Fundraising and investor relations": "Fundraising",  # adds investor relations (CFO), broader
    "GST e-invoicing": "GST",  # product engineering skill vs tax compliance
    "Pricing and contracts": "Pricing",  # sales contracting, not product pricing
    "Pricing experiments": "Pricing",  # product experimentation method
    "Reconciliation engines": "Reconciliation",  # backend engineering vs finance operations
}

# Single-word skills that are ordinary English words.
COMMON_SKILL_WORDS = frozenset({
    "Accessibility", "Analytics", "Audit", "Budgeting", "Calibration", "Coaching", "Dart",
    "Events", "Excel", "Fintech", "Fundraising", "Go", "Helpdesk", "Iconography",
    "Illustration", "Mentoring", "Negotiation", "Networking", "Observability", "Onboarding",
    "Postman", "Pricing", "React", "Reconciliation", "Roadmapping", "Rostering", "Statistics",
    "Testing", "Troubleshooting",
})
# All-caps department aliases that are still generic words.
GENERIC_ACRONYMS = frozenset({"AI"})

# Priority on identical spans (lower wins); identical spans only arise for one entity.
KIND_PRIORITY = {"id": 0, "full": 1, "title": 2, "first_name": 3, "short": 4, "skill": 4}


@dataclass(frozen=True)
class Alias:
    text: str
    label: str
    id: str
    kind: str
    ignore_case: bool = False
    restrict: Restrict = None
    alt: tuple[str, str] | None = None  # (label, id) when followed by team/department/dept


@dataclass
class AliasTable:
    aliases: list[Alias] = field(default_factory=list)
    excluded_first_names: dict[str, list[str]] = field(default_factory=dict)
    excluded_titles: dict[str, list[str]] = field(default_factory=dict)
    dropped: dict[str, list[tuple[str, str]]] = field(default_factory=dict)  # collisions
    skill_canonical: dict[str, str] = field(default_factory=dict)  # skill id -> canonical id

    @property
    def restricted(self) -> list[Alias]:
        return [a for a in self.aliases if a.restrict]


def _single_word(text: str) -> bool:
    return " " not in text


def _dept_restrict(text: str) -> Restrict:
    if not _single_word(text):
        return None
    if text.isupper() and text not in GENERIC_ACRONYMS:
        return None
    return "generic"


def _chief_acronym(part: str) -> str | None:
    """'Chief Executive Officer' -> 'CEO'."""
    words = part.split()
    if len(words) >= 3 and words[0] == "Chief" and words[-1] == "Officer":
        return "".join(w[0] for w in words)
    return None


def _title_aliases(title: str) -> list[str]:
    """Full title, 'Chief ... Officer' parts and acronyms, '(ACRONYM)' and the title without it."""
    out = [title]
    m = re.fullmatch(r"(.*?)\s*\(([A-Z]{2,})\)", title)
    if m:
        out += [m[1], m[2]]
    for part in re.split(r"\s*&\s*", title):
        acronym = _chief_acronym(part)
        if acronym:
            out += [part, acronym]
    return list(dict.fromkeys(out))


def skill_merge_candidates() -> list[tuple[str, str]]:
    """Word-suffix variants (variant, base): a skill name that is another skill + ' ' + words."""
    names = {r["skill"] for r in read_csv("skills")}
    return sorted((s, b) for s in names for b in names
                  if s != b and s.startswith(b + " ") and not s.startswith(b + " ("))


def _skill_groups(skills: list[dict[str, str]]) -> dict[str, str]:
    by_name = {r["skill"]: r["skill_id"] for r in skills}
    canonical = {r["skill_id"]: r["skill_id"] for r in skills}
    for name, sid in by_name.items():
        m = re.fullmatch(r"(.*?)\s*\((.*)\)", name)
        base = m[1] if m and m[1] in by_name else SKILL_MERGES.get(name)
        if base:
            canonical[sid] = by_name[base]
    return canonical


def _collect() -> tuple[list[Alias], AliasTable]:
    table = AliasTable()
    raw: list[Alias] = []

    employees = read_csv("employees")
    firsts = Counter(r["full_name"].split()[0] for r in employees)
    titles: dict[str, set[str]] = defaultdict(set)
    for r in employees:
        eid, name = r["employee_id"], r["full_name"]
        raw += [Alias(name, "Employee", eid, "full", True), Alias(eid, "Employee", eid, "id", True)]
        first = name.split()[0]
        if firsts[first] == 1:
            raw.append(Alias(first, "Employee", eid, "first_name"))
        for t in _title_aliases(" ".join(r["title"].split())):
            titles[t].add(eid)
    for r in employees:
        first = r["full_name"].split()[0]
        if firsts[first] > 1:
            table.excluded_first_names.setdefault(first, []).append(r["employee_id"])
    for t, eids in sorted(titles.items()):
        if len(eids) == 1:
            raw.append(Alias(t, "Employee", next(iter(eids)), "title"))
        else:
            table.excluded_titles[t] = sorted(eids)

    for r in read_csv("departments"):
        did, name = r["department_id"], r["name"]
        raw += [Alias(did, "Department", did, "id", True), Alias(name, "Department", did, "full", True),
                Alias(r["code"], "Department", did, "short")]
        m = re.fullmatch(r"(.*?)\s*\((.*)\)", name)
        bare, paren = (m[1], m[2]) if m else (name, None)
        shorts = [bare, *re.split(r"\s*&\s*", bare), *DEPT_SHORT.get(did, ())]
        if paren:
            shorts.append(paren)
        for s in dict.fromkeys(shorts):
            if s != name:
                raw.append(Alias(s, "Department", did, "short", restrict=_dept_restrict(s)))

    for r in read_csv("projects"):
        pid, name = r["project_id"], r["name"]
        short = name.removeprefix("Project ")
        raw += [Alias(pid, "Project", pid, "id", True), Alias(name, "Project", pid, "full", True),
                Alias(short, "Project", pid, "short", restrict="codename" if _single_word(short) else None)]

    for r in read_csv("products"):
        pid, name = r["product_id"], r["name"]
        short = name.removeprefix("Zenvora ")
        raw += [Alias(pid, "Product", pid, "id", True), Alias(name, "Product", pid, "full", True),
                Alias(short, "Product", pid, "short", restrict="codename" if _single_word(short) else None)]

    for r in read_csv("policies"):
        raw += [Alias(r["policy_id"], "Policy", r["policy_id"], "id", True),
                Alias(r["title"], "Policy", r["policy_id"], "full", True)]

    skills = read_csv("skills")
    names = {r["skill"] for r in skills}
    for r in skills:
        sid, name = r["skill_id"], r["skill"]
        raw += [Alias(sid, "Skill", sid, "id", True),
                Alias(name, "Skill", sid, "skill",
                      restrict="generic" if name in COMMON_SKILL_WORDS else None)]
        m = re.fullmatch(r"(.*?)\s*\((.*)\)", name)
        if m:
            raw.append(Alias(m[2], "Skill", sid, "skill"))  # "FastAPI", "pandas", "WCAG 2.1"
            if m[1] not in names:  # "Accessibility" -> Accessibility (WCAG 2.1)
                raw.append(Alias(m[1], "Skill", sid, "skill",
                                 restrict="generic" if m[1] in COMMON_SKILL_WORDS else None))
    table.skill_canonical = _skill_groups(skills)
    return raw, table


def _resolve(raw: list[Alias], table: AliasTable) -> list[Alias]:
    """One alias per lower-cased text: same entity merges, product beats department, else drop."""
    groups: dict[str, list[Alias]] = defaultdict(list)
    for a in raw:
        groups[a.text.lower()].append(a)
    out: list[Alias] = []
    for key, group in groups.items():
        targets = list(dict.fromkeys((a.label, a.id) for a in group))
        if len(targets) == 1:
            best = min(group, key=lambda a: (not a.ignore_case, a.restrict is not None, KIND_PRIORITY[a.kind]))
            out.append(best)
            continue
        labels = {t[0] for t in targets}
        if len(targets) == 2 and labels == {"Product", "Department"}:
            product = min((a for a in group if a.label == "Product"), key=lambda a: not a.ignore_case)
            dept = next(t for t in targets if t[0] == "Department")
            out.append(Alias(product.text, product.label, product.id, product.kind,
                             product.ignore_case, product.restrict, alt=dept))
            continue
        table.dropped[group[0].text] = targets
    return out


@cache
def alias_table() -> AliasTable:
    raw, table = _collect()
    table.aliases = _resolve(raw, table)
    return table


def canonical_skill(skill_id: str) -> str:
    return alias_table().skill_canonical[skill_id]


def skill_variants(skill_id: str) -> set[str]:
    """Every skill id in the merged group of `skill_id` (including itself)."""
    canon = alias_table().skill_canonical
    root = canon[skill_id]
    return {s for s, c in canon.items() if c == root}


def skill_groups() -> dict[str, list[str]]:
    """Canonical skill name -> merged variant names (groups of 2 or more)."""
    names = {r["skill_id"]: r["skill"] for r in read_csv("skills")}
    groups: dict[str, list[str]] = defaultdict(list)
    for sid, root in alias_table().skill_canonical.items():
        if sid != root:
            groups[names[root]].append(names[sid])
    return {k: sorted(v) for k, v in sorted(groups.items())}


def main() -> None:
    t = alias_table()
    print(f"{len(t.aliases)} aliases")
    print("excluded first names (shared):", {k: v for k, v in sorted(t.excluded_first_names.items())})
    print("excluded titles (shared):")
    for k, v in t.excluded_titles.items():
        print(f"  {k}: {', '.join(v)}")
    print("dropped colliding aliases:", t.dropped or "none")
    print("product/department aliases:", [(a.text, a.id, a.alt) for a in t.aliases if a.alt])
    print("skill groups merged:")
    for k, v in skill_groups().items():
        print(f"  {k} <- {', '.join(v)}")
    print("word-suffix candidates:", skill_merge_candidates())
    print("rejected skill merges:", REJECTED_SKILL_MERGES)
    print("restricted aliases:")
    for kind in ("codename", "generic"):
        print(f"  {kind}:", sorted(f"{a.text} ({a.id})" for a in t.restricted if a.restrict == kind))


if __name__ == "__main__":
    main()
