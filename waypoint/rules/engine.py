"""Rule evaluator over the JSON predicates in predicates.json (DESIGN "Rules as predicates").

evaluate(rule_id, subject_id, asker_id, as_of, params) -> RuleResult

- A rule is an ordered list of cases; the first case whose `when` predicate is true fires.
  Predicates: {"all": [...]}, {"any": [...]}, {"not": p}, {"attr", "op", "value"} with
  op in == != < <= > >= in. Logic is three-valued: an attribute that is not known (no
  subject, a missing param, data the graph lacks) makes a comparison unknown; a case
  that is unknown is skipped and named in `assumptions`.
- Attributes are derived at query time from the subject's base facts and as_of
  (`waypoint.rules.derived`); numeric and categorical inputs (amount, city) are explicit
  params. Extracting them from a question is the router's job (2.4).
- Access (CLAUDE.md rule 6), enforced here: a `restricted` rule (it reads employment
  status or another person's notice period) runs only when the asker is the subject,
  the subject's direct manager (the subject's own REPORTS_TO target) or HR (works in
  the department with code HR, its head included). Otherwise the result is
  status="restricted" with nothing else filled in, identical for every subject.
- People rules (approvers) resolve roles through the 2.2 `approvals_chain` template.
"""
from __future__ import annotations

import json
import re
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any, Literal

from neo4j import Driver
from pydantic import BaseModel, Field

from waypoint.contract import Citation, GraphCitation, PolicyCitation, Subgraph, SubgraphEdge, SubgraphNode
from waypoint.graph import templates as T
from waypoint.retrieval.linking import link_entities
from waypoint.rules import derived as Dv
from waypoint.rules.facts import EmployeeFacts, FactStore, facts_from_csv

RULES_PATH = Path(__file__).with_name("predicates.json")
HR_DEPARTMENT_CODE = T.HR_DEPARTMENT_CODE
Status = Literal["ok", "restricted", "insufficient_input", "not_applicable"]


# ---------------------------------------------------------------- rule file

class Source(BaseModel):
    policy: str
    section: int
    rule_id: str | None = None  # id in policy_rules.csv, where one exists


class Case(BaseModel):
    id: str
    when: dict[str, Any]
    result: dict[str, Any]
    sources: list[Source]


class Rule(BaseModel):
    id: str
    description: str
    restricted: bool = False
    people: bool = False
    params: list[str] = []
    param_defaults: dict[str, Any] = {}
    subject_params: list[str] = []  # attributes a caller may give when there is no subject
    base: dict[str, Any] = {}
    cases: list[Case]


@cache
def _rules() -> tuple[tuple[str, Rule], ...]:
    raw = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    return tuple((rid, Rule(id=rid, **body)) for rid, body in raw.items())


def load_rules() -> dict[str, Rule]:
    return dict(_rules())


# ---------------------------------------------------------------- result

class RuleResult(BaseModel):
    rule_id: str
    subject_id: str | None
    asker_id: str
    as_of: date
    status: Status
    fired_case: str | None = None
    value: dict[str, Any] = {}
    inputs: dict[str, Any] = {}  # attributes the predicates and result read, plus params
    params: dict[str, Any] = {}
    policy_rules: list[str] = []  # R0xx ids from policy_rules.csv
    citations: list[Citation] = []
    subgraph: Subgraph = Field(default_factory=Subgraph)
    assumptions: list[str] = []


# ---------------------------------------------------------------- attributes

_UNKNOWN = object()
_NOT_IN_GRAPH = {"unallocated_working_days": "project allocation history is not in the graph"}


class Attrs:
    """Lazy attribute lookup that records every attribute it is asked for."""

    def __init__(self, subject: EmployeeFacts | None, as_of: date, params: dict[str, Any]):
        self.subject, self.as_of, self.params = subject, as_of, params
        self.used: dict[str, Any] = {}

    def get(self, name: str) -> Any:
        value = self._compute(name)
        if value is not _UNKNOWN:
            self.used[name] = value.isoformat() if isinstance(value, date) else value
        return value

    def _compute(self, name: str) -> Any:  # noqa: PLR0911, C901 - one branch per attribute
        p, s, as_of = self.params, self.subject, self.as_of
        if name == "city":
            return Dv.canonical_city(p["city"]) if "city" in p else _UNKNOWN
        if name == "city_tier":
            return Dv.city_tier(p["city"]) if "city" in p else _UNKNOWN
        if name in ("amount", "international"):
            return p.get(name, _UNKNOWN)
        if s is None:
            return p.get(name, _UNKNOWN)
        join = s.join_date
        match name:
            case "band" | "department_code" | "department_id" | "base_city" | "location_id" \
                 | "status" | "join_date" | "manager_id":
                return getattr(s, name)
            case "band_number":
                return Dv.band_number(s.band)
            case "status_category":
                return Dv.status_category(s.status)
            case "is_top":
                return s.manager_id is None
            case "days_since_join":
                return Dv.days_since_join(join, as_of)
            case "tenure_years":
                return Dv.tenure_years(join, as_of)
            case "completed_service_years":
                return Dv.completed_years(join, as_of)
            case "induction_end":
                return Dv.induction_end(join)
            case "probation_end":
                return Dv.probation_end(join)
            case "in_probation":
                return as_of <= Dv.probation_end(join)
        return _UNKNOWN


_OPS = {
    "==": lambda a, b: a == b, "!=": lambda a, b: a != b, "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b, ">": lambda a, b: a > b, ">=": lambda a, b: a >= b,
    "in": lambda a, b: a in b,
}


def holds(pred: dict[str, Any], attrs: Attrs, missing: set[str]) -> bool | None:
    """Three-valued predicate: True, False or None (unknown). Unknown attributes go to `missing`."""
    if "all" in pred:
        vals = [holds(p, attrs, missing) for p in pred["all"]]
        return False if False in vals else (None if None in vals else True)
    if "any" in pred:
        vals = [holds(p, attrs, missing) for p in pred["any"]]
        return True if True in vals else (None if None in vals else False)
    if "not" in pred:
        v = holds(pred["not"], attrs, missing)
        return None if v is None else not v
    value = attrs.get(pred["attr"])
    if value is _UNKNOWN:
        missing.add(pred["attr"])
        return None
    return bool(_OPS[pred["op"]](value, pred["value"]))


_PLACEHOLDER = re.compile(r"\{(\w+)(\|date)?\}")


def _fill(value: Any, attrs: Attrs) -> Any:
    if isinstance(value, dict):
        return {k: _fill(v, attrs) for k, v in value.items()}
    if not isinstance(value, str):
        return value

    def sub(m: re.Match[str]) -> str:
        v = attrs.get(m.group(1))
        if v is _UNKNOWN:
            raise ValueError(f"result placeholder {m.group(1)} is unknown")
        if m.group(2) and isinstance(v, date):
            return Dv.fmt_date(v)
        return v.isoformat() if isinstance(v, date) else str(v)

    return _PLACEHOLDER.sub(sub, value)


# ---------------------------------------------------------------- access

def can_see_restricted(subject_id: str, asker_id: str, facts: FactStore) -> bool:
    """Rule 6: the person themselves, their direct manager, or anyone in HR."""
    subject, asker = facts.get(subject_id), facts.get(asker_id)
    if subject is None or asker is None:
        return False
    return (asker_id == subject_id or asker_id == subject.manager_id
            or asker.department_code == HR_DEPARTMENT_CODE)


# ---------------------------------------------------------------- evidence

_EDGES = {  # attribute -> (relationship, target id field, target label, target name field)
    "department_code": ("WORKS_IN", "department_id", "Department", "department_code"),
    "department_id": ("WORKS_IN", "department_id", "Department", "department_code"),
    "band": ("IN_BAND", "band", "Band", "band"),
    "band_number": ("IN_BAND", "band", "Band", "band"),
    "base_city": ("BASED_AT", "location_id", "Location", "base_city"),
    "location_id": ("BASED_AT", "location_id", "Location", "base_city"),
    "is_top": ("REPORTS_TO", "manager_id", "Employee", "manager_id"),
    "manager_id": ("REPORTS_TO", "manager_id", "Employee", "manager_id"),
}


# Rule 6 facts: never written into a subgraph detail, for any asker.
RESTRICTED_ATTRS = frozenset({"status", "status_category"})
_DATE_DERIVED = frozenset({"days_since_join", "tenure_years", "completed_service_years", "in_probation",
                           "induction_end", "probation_end"})


def _leaves(pred: dict[str, Any]) -> list[tuple[str, str, Any]]:
    """(attr, op, value) of every comparison in a predicate."""
    for key in ("all", "any"):
        if key in pred:
            return [leaf for p in pred[key] for leaf in _leaves(p)]
    if "not" in pred:
        return [(a, f"not {op}", v) for a, op, v in _leaves(pred["not"])]
    return [(pred["attr"], pred["op"], pred["value"])]


def _decisive(case: Case) -> set[str]:
    return {a for a, _, _ in _leaves(case.when)}


def _fact_evidence(s: EmployeeFacts, used: dict[str, Any], decisive: set[str] = frozenset()
                   ) -> tuple[list[str], Subgraph]:
    nodes = {s.employee_id: SubgraphNode(id=s.employee_id, label="Employee", name=s.name)}
    edges: dict[tuple[str, str, str], SubgraphEdge] = {}
    for attr in used:
        if attr not in _EDGES:
            continue
        rel, id_field, label, name_field = _EDGES[attr]
        target = getattr(s, id_field)
        if target is None:
            continue
        nodes.setdefault(target, SubgraphNode(id=target, label=label, name=str(getattr(s, name_field) or "")))
        key = (s.employee_id, rel, target)
        role = "decisive" if attr in decisive else "checked"
        if key not in edges or role == "decisive":
            edges[key] = SubgraphEdge(source=s.employee_id, type=rel, target=target, role=role)
    sub = Subgraph(nodes=list(nodes.values()), edges=list(edges.values()))
    return [f"{e.source} -{e.type}-> {e.target}" for e in sub.edges], sub


def _fmt(v: Any) -> str:
    return "yes" if v is True else "no" if v is False else str(v)


def _subject_detail(rule: Rule, case: Case, subject: EmployeeFacts, used: dict[str, Any]) -> str:
    """Public facts the fired case depends on, then the other public facts read. Restricted
    attributes (status) are left out even for an authorised asker; the answer carries them."""
    conds = _leaves(case.when)
    dec = [f"{a} = {_fmt(used[a])} (case needs {op} {_fmt(v)})" for a, op, v in conds
           if a in used and a not in RESTRICTED_ATTRS]
    if any(a in RESTRICTED_ATTRS for a, _, _ in conds):
        dec.append("a restricted fact (shown only in the answer, to an authorised asker)")
    if not conds:
        dec.append("no earlier case applies")
    facts = dict(used)
    if _DATE_DERIVED & set(facts):
        facts.setdefault("join_date", subject.join_date.isoformat())
    shown = {a for a, _, _ in conds} | RESTRICTED_ATTRS | set(rule.params)
    checked = [f"{a} = {_fmt(v)}" for a, v in facts.items() if a not in shown]
    # A case named after a restricted fact (ON_LEAVE, SERVING_NOTICE) would reveal it.
    name = "" if _decisive(case) & RESTRICTED_ATTRS else f", case {case.id}"
    out = f"Rule {rule.id}{name}. Decisive: {'; '.join(dec)}."
    return out + (f" Also checked: {'; '.join(checked)}." if checked else "")


def _section_detail(rule: Rule, case: Case, value: dict[str, Any]) -> str:
    if _decisive(case) & RESTRICTED_ATTRS:
        return f"Rule {rule.id}: the applicable case depends on a restricted fact."
    reason = value.get("reason")
    return f"Rule {rule.id}, case {case.id}" + (f": {reason}" if isinstance(reason, str) else "")


def _rule_evidence(rule: Rule, case: Case, subject: EmployeeFacts | None, used: dict[str, Any],
                   value: dict[str, Any]) -> tuple[list[str], Subgraph]:
    """Fact edges (decisive or checked), the cited policy sections, and the derived
    RULE_CASE edge subject -> section. Paths are the fact edges only (citations unchanged)."""
    paths: list[str] = []
    sub = Subgraph()
    if subject is not None:
        paths, sub = _fact_evidence(subject, used, _decisive(case))
        sub.nodes[0] = sub.nodes[0].model_copy(update={"detail": _subject_detail(rule, case, subject, used)})
    nodes, edges = list(sub.nodes), list(sub.edges)
    for s in dict.fromkeys((s.policy, s.section) for s in case.sources):
        sid = f"{s[0]}#{s[1]}"  # PolicySection.section_id in the graph
        nodes += [SubgraphNode(id=s[0], label="Policy", name=s[0]),
                  SubgraphNode(id=sid, label="PolicySection", name=f"{s[0]} §{s[1]}",
                               detail=_section_detail(rule, case, value))]
        edges.append(SubgraphEdge(source=s[0], type="HAS_SECTION", target=sid))
        if subject is not None:
            edges.append(SubgraphEdge(source=subject.employee_id, type="RULE_CASE", target=sid,
                                      role="decisive", derived=True))
    return paths, Subgraph().merge(Subgraph(nodes=nodes, edges=edges))


def _merge(a: Subgraph, b: Subgraph) -> Subgraph:
    return a.merge(b)


def _resolve_people(driver: Driver, subject: EmployeeFacts, roles: dict[str, str]
                    ) -> tuple[dict[str, dict[str, Any] | None], list[str], Subgraph, list[str]]:
    """Map role names (manager, department_head, hr_head, ceo, cfo) to people."""
    chain = T.approvals_chain(driver, subject.employee_id)
    if not chain.rows:
        raise KeyError(f"no reporting chain for {subject.employee_id}")
    row = chain.rows[0]
    holders: dict[str, dict[str, Any] | None] = {
        "manager": row["chain"][1] if len(row["chain"]) > 1 else None,
        "department_head": row["department_head"], "hr_head": row["hr_head"], "ceo": row["ceo"],
    }
    paths, sub = list(chain.paths), chain.subgraph
    if "cfo" in roles.values():
        cfo_ids = [m.id for m in link_entities("CFO") if m.label == "Employee"]
        card = T.employee_card(driver, cfo_ids[0]) if cfo_ids else None
        holders["cfo"] = ({k: card.rows[0][k] for k in ("employee_id", "name", "title", "band")}
                          if card and card.rows else None)
        if card:
            paths += [p for p in card.paths if p not in paths]
            sub = _merge(sub, card.subgraph)
    people: dict[str, dict[str, Any] | None] = {}
    notes = []
    for role, holder in roles.items():
        person = holders[holder]
        people[role] = person
        if person is None:
            notes.append(f"{role}: no {holder} found for {subject.employee_id}")
        elif person["employee_id"] == subject.employee_id:
            notes.append(f"{role}: the {holder} is the subject ({subject.name}); "
                         "the policy does not say who acts instead")
    return people, paths, sub, notes


# ---------------------------------------------------------------- evaluate

def evaluate(rule_id: str, subject_id: str | None, asker_id: str, as_of: date,
             params: dict[str, Any] | None = None, *, facts: FactStore | None = None,
             driver: Driver | None = None) -> RuleResult:
    rule = load_rules()[rule_id]  # KeyError for an unknown rule
    params = dict(params or {})
    allowed = set(rule.params) | (set(rule.subject_params) if subject_id is None else set())
    if extra := set(params) - allowed:
        raise ValueError(f"{rule_id}: unexpected params {sorted(extra)}; allowed {sorted(allowed)}")
    facts = facts if facts is not None else facts_from_csv()
    subject = None
    if subject_id is not None:
        subject = facts.get(subject_id)
        if subject is None:
            raise KeyError(f"unknown employee {subject_id}")
    base = RuleResult(rule_id=rule_id, subject_id=subject_id, asker_id=asker_id, as_of=as_of,
                      status="ok", params=params)
    if rule.restricted and subject_id is not None and not can_see_restricted(subject_id, asker_id, facts):
        return base.model_copy(update={"status": "restricted"})
    if rule.people and (driver is None or subject is None):
        raise ValueError(f"{rule_id} needs a driver and a subject")
    if subject is not None and as_of < subject.join_date:
        return base.model_copy(update={"status": "not_applicable",
                                       "assumptions": [f"{subject_id} joins on {subject.join_date}"]})

    attrs = Attrs(subject, as_of, {**rule.param_defaults, **params})
    assumptions: list[str] = []
    fired: Case | None = None
    for case in rule.cases:
        missing: set[str] = set()
        verdict = holds(case.when, attrs, missing)
        if verdict is None:
            why = "; ".join(f"{m} unknown" + (f" ({_NOT_IN_GRAPH[m]})" if m in _NOT_IN_GRAPH else "")
                            for m in sorted(missing))
            assumptions.append(f"{case.id} not evaluated: {why}")
        elif verdict:
            fired = case
            break
    if fired is None:
        return base.model_copy(update={"status": "insufficient_input", "inputs": attrs.used,
                                       "assumptions": assumptions})

    value = {**rule.base, **_fill(fired.result, attrs)}
    citations: list[Citation] = []
    for s in fired.sources:
        if not any(c.id == s.policy and c.section == s.section for c in citations if isinstance(c, PolicyCitation)):
            citations.append(PolicyCitation(id=s.policy, section=s.section))
    policy_rules = list(dict.fromkeys(s.rule_id for s in fired.sources if s.rule_id))
    paths, subgraph = _rule_evidence(rule, fired, subject, attrs.used, value)
    if rule.people and subject is not None and driver is not None:
        people, ppaths, psub, notes = _resolve_people(driver, subject, value["roles"])
        value["people"] = people
        paths += [p for p in ppaths if p not in paths]
        subgraph = _merge(subgraph, psub)
        assumptions += notes
    citations += [GraphCitation(path=p) for p in paths]
    return base.model_copy(update={
        "fired_case": fired.id, "value": value, "inputs": attrs.used, "policy_rules": policy_rules,
        "citations": citations, "subgraph": subgraph, "assumptions": assumptions})
