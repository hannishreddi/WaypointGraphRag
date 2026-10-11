"""Context pack (PLAN 2.5, DESIGN "Answer assembly"): what the generator may use.

Built from the router's `Evidence`. Every item has an id the generator cites and the
contract citations behind it:

  asker        identity: the asker's public employee card (graph paths of the card)
  step<N>      primary-path step N: template rows (with an explicit row count, and an
               item count for every list field) or a rule result (status, case, value,
               inputs, assumptions, policy sections)
  alt<N>       the same for the alternative path (low router confidence)
  <chunk id>   a passage from text_search (chunk citation, plus the policy section)
  unresolved   id-shaped mentions in the question that match nothing

Passages arrive already filtered by `waypoint.retrieval.access` (rule 6); a restricted
rule result is rendered as a refusal and carries nothing about the person.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from neo4j import Driver

from waypoint.contract import ChunkCitation, Citation, PolicyCitation, Subgraph
from waypoint.graph import templates as T
from waypoint.retrieval.plan import Evidence, StepResult, merge
from waypoint.retrieval.router import Route
from waypoint.rules.engine import RuleResult

VERSION = "pack-v1"  # part of S5's config_id: a change re-answers checkpointed questions
Kind = Literal["identity", "graph", "rule", "passage", "unresolved", "note"]
_SECTION = re.compile(r"^s(\d+)$")


@dataclass
class PackItem:
    id: str
    kind: Kind
    text: str
    path: str = ""  # primary | alternative | "" (identity, unresolved)
    citations: list[Citation] = field(default_factory=list)

    def render(self) -> str:
        path = f' path="{self.path}"' if self.path else ""
        return f'<item id="{self.id}" kind="{self.kind}"{path}>\n{self.text}\n</item>'


@dataclass
class ContextPack:
    question: str
    asker_id: str
    as_of: date
    items: list[PackItem] = field(default_factory=list)
    subgraph: Subgraph = field(default_factory=Subgraph)

    def ids(self) -> list[str]:
        return [i.id for i in self.items]

    def get(self, item_id: str) -> PackItem | None:
        return next((i for i in self.items if i.id == item_id), None)

    def render(self) -> str:
        return "\n\n".join(i.render() for i in self.items)

    def citations_for(self, item_ids: list[str]) -> list[Citation]:
        out: dict[str, Citation] = {}
        for item_id in item_ids:
            item = self.get(item_id)
            for c in item.citations if item else []:
                out.setdefault(c.model_dump_json(), c)
        return list(out.values())


# ---------------------------------------------------------------- rendering values

def _person(d: dict[str, Any]) -> str:
    extra = ", ".join(str(d[k]) for k in ("title", "band") if d.get(k))
    return f"{d.get('name')} ({d['employee_id']}{', ' + extra if extra else ''})"


def _value(v: Any) -> str:
    if isinstance(v, dict):
        if "employee_id" in v and "name" in v:
            return _person(v)
        return "; ".join(f"{k}: {_value(x)}" for k, x in v.items())
    if isinstance(v, list):
        return f"[{len(v)} items] " + " | ".join(_value(x) for x in v) if v else "[0 items]"
    if v is None:
        return "none"
    if isinstance(v, bool):
        return "yes" if v else "no"
    return str(v)


def _row(row: dict[str, Any]) -> str:
    return "- " + "; ".join(f"{k}: {_value(v)}" for k, v in row.items()
                            if not k.startswith("_") and v is not None)


def _args(args: dict[str, Any]) -> str:
    return ", ".join(f"{k}={v}" for k, v in args.items())


def _template_text(s: StepResult, out: T.TemplateResult) -> str:
    n = len(out.rows)
    lines = [f"{s.op}({_args(s.args)}) returned {n} row{'s' if n != 1 else ''}"]
    lines += [_row(r) for r in out.rows]
    return "\n".join(lines)


RESTRICTED_TEXT = ("status: restricted. The asker is not permitted to see this person's employment status, "
                   "leave or notice period. Do not reveal, hint at or guess it.")


def _rule_text(s: StepResult, r: RuleResult) -> str:
    who = f"subject {r.subject_id}" if r.subject_id else f"a hypothetical person ({_args(r.params)})"
    head = f"rule {r.rule_id} for {who} as of {r.as_of.isoformat()}"
    if r.status == "restricted":
        return f"{head}\n{RESTRICTED_TEXT}"
    lines = [head, f"status: {r.status}"]
    if r.fired_case:
        lines.append(f"case: {r.fired_case}")
    if r.value:
        lines += [f"{k}: {_value(v)}" for k, v in r.value.items() if k != "roles"]
    if r.inputs:
        lines.append(f"inputs: {_value(r.inputs)}")
    if r.assumptions:
        lines.append("assumptions: " + " | ".join(r.assumptions))
    sources = [f"{c.id} section {c.section}" for c in r.citations if isinstance(c, PolicyCitation)]
    if sources:
        lines.append("policy: " + "; ".join(sources))
    return "\n".join(lines)


def _passage_citations(hit: dict[str, Any]) -> list[Citation]:
    cites: list[Citation] = [ChunkCitation(id=hit["chunk_id"])]
    m = _SECTION.match(str(hit.get("section") or ""))
    if hit.get("doc_type") == "policy" and m:
        cites.append(PolicyCitation(id=hit["doc_id"], section=int(m[1])))
    return cites


# ---------------------------------------------------------------- building

def identity_item(driver: Driver, asker_id: str) -> tuple[PackItem, Subgraph]:
    card = T.employee_card(driver, asker_id)
    if not card.rows:
        return PackItem("asker", "identity", f"The asker {asker_id} is not a known employee."), Subgraph()
    r = card.rows[0]
    text = (f"The asker (I, me, my) is {r['name']} ({r['employee_id']}), {r['title']}, band {r['band']}, "
            f"{r['department']} ({r['department_id']}), based at {r['location']} ({r['location_id']}), "
            f"joined {r['join_date']}.")
    return PackItem("asker", "identity", text, citations=list(card.citations())), card.subgraph


def build_pack(route: Route, evidence: Evidence, *, driver: Driver, as_of: date) -> ContextPack:
    pack = ContextPack(route.question, route.asker_id, as_of)
    ident, ident_sub = identity_item(driver, route.asker_id)
    pack.items.append(ident)
    seen_chunks: set[str] = set()
    counters = {"primary": 0, "alternative": 0}
    for ev_item in evidence.items:
        s, path = ev_item.step, ev_item.path
        counters[path] += 1
        sid = f"{'step' if path == 'primary' else 'alt'}{counters[path]}"
        out = s.output
        if s.error is not None:
            pack.items.append(PackItem(sid, "note", f"{s.op}({_args(s.args)}) did not run: {s.error}", path))
        elif isinstance(out, T.TemplateResult):
            pack.items.append(PackItem(sid, "graph", _template_text(s, out), path, list(out.citations())))
        elif isinstance(out, RuleResult):
            cites = [] if out.status == "restricted" else list(out.citations)
            pack.items.append(PackItem(sid, "rule", _rule_text(s, out), path, cites))
        elif isinstance(out, list):
            fresh = [h for h in out if h["chunk_id"] not in seen_chunks]
            if not out:
                pack.items.append(PackItem(sid, "note", f"text_search({_args(s.args)}) found no passages", path))
            for h in fresh:
                seen_chunks.add(h["chunk_id"])
                pack.items.append(PackItem(h["chunk_id"], "passage", h["text"].strip(), path, _passage_citations(h)))
    if route.unresolved:
        pack.items.append(PackItem(
            "unresolved", "unresolved",
            "These ids in the question match no policy, person or other entity at Zenvora: "
            + ", ".join(route.unresolved) + ". Say that no such policy or person exists."))
    sub = evidence.subgraph
    if route.decision.needs_identity:
        sub = merge(Evidence(subgraph=sub), Evidence(subgraph=ident_sub)).subgraph
    pack.subgraph = sub
    return pack
