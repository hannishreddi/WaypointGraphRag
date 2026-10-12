"""Router plans (PLAN 2.4): the op catalogue, the plan format, validation, execution, merge.

A plan is an ordered list of steps `{"op": ..., "args": {...}}`. An op is one of the 17
Cypher templates, one of the rule ids in predicates.json, or `text_search`. Each op has a
fixed parameter table (`OPS`); an argument value is one of

- a linked entity id: it must be among the `link_mentions` matches of the question and
  have a label the parameter accepts (ids never come from the LLM alone);
- "asker": the person asking, where a person is accepted (employee, subject, entity);
- "$N.field": the `field` of the first row of earlier template step N (1-based), where
  `field` is one of that template's declared outputs and of a compatible kind;
- a literal for text, int, bool and enum parameters (a city is plain text: "Pune").

`RouterOutput` validates all of this in a Pydantic validator that reads the linked
entities from the validation context, so `complete_json` retries once with the errors
(rule 4). Without a context nothing is linked and every entity id is rejected.

Execution dispatches through `OPS` only, never by name lookup on a module, so an op that
is not in the catalogue cannot run even if validation were bypassed.

Merge (low router confidence): the primary and the alternative path both run; evidence is
concatenated with each item tagged by its path, primary first; subgraph nodes are
deduplicated by id, edges by (source, type, target), citations by value. Nothing is
resolved here: the 2.5 generator sees both paths, labelled.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from neo4j import Driver
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, model_validator

from waypoint.contract import Citation, ChunkCitation, Subgraph
from waypoint.graph import templates as T
from waypoint.graph.load import read_csv
from waypoint.retrieval.access import search_for_asker
from waypoint.retrieval.linking import LinkResult
from waypoint.retrieval.search import DOC_TYPES, Hit, QueryEmbedder
from waypoint.rules.engine import RuleResult, load_rules
from waypoint.rules.engine import evaluate as evaluate_rule

Intent = Literal["fact_list_count", "policy_text", "personal_rule", "overview", "who_to_ask", "refuse"]
INTENTS: tuple[str, ...] = Intent.__args__  # type: ignore[attr-defined]
MAX_STEPS = 4
ASKER = "asker"
REF = re.compile(r"^\$(\d+)\.(\w+)$")

# Parameter kinds. Entity kinds accept linked ids of these labels.
ENTITY_KINDS: dict[str, frozenset[str]] = {
    "employee": frozenset({"Employee"}),
    "subject": frozenset({"Employee"}),
    "department": frozenset({"Department"}),
    "project": frozenset({"Project"}),
    "project_or_product": frozenset({"Project", "Product"}),
    "organization": frozenset({"Organization"}),
    "skill": frozenset({"Skill"}),
    "policy": frozenset({"Policy"}),
    "location": frozenset({"Location"}),
    "entity": frozenset({"Employee", "Department", "Project", "Product", "Policy"}),
}
PERSON_KINDS = frozenset({"employee", "subject", "entity"})  # accept "asker"
# Output column kind -> parameter kinds a reference to it may fill.
REF_TARGETS = {
    "employee": {"employee", "subject", "entity"},
    "department": {"department", "entity"},
    "project": {"project", "project_or_product", "entity"},
    "organization": {"organization"},
    "skill": {"skill"},
    "policy": {"policy", "entity"},
    "location": {"location"},
}
BANDS = tuple(f"Z{i}" for i in range(1, 9))


def _enum(kind: str) -> tuple[Any, ...] | None:
    if kind == "direction":
        return ("in", "out")
    if kind == "doc_type":
        return DOC_TYPES
    if kind == "band":
        return BANDS
    if kind == "department_code":
        return tuple(sorted(d["code"] for d in read_csv("departments")))
    return None


@dataclass(frozen=True)
class Param:
    kind: str
    required: bool = True
    doc: str = ""


@dataclass(frozen=True)
class OpSpec:
    name: str
    family: Literal["template", "rule", "search"]
    doc: str
    params: dict[str, Param]
    outputs: dict[str, str] = field(default_factory=dict)  # template row field -> kind


def _t(name: str, doc: str, params: dict[str, Param], **outputs: str) -> OpSpec:
    return OpSpec(name, "template", doc, params, outputs)


_E = {"employee_id": Param("employee")}
TEMPLATE_OPS: tuple[OpSpec, ...] = (
    _t("employee_card", "title, band, department, location and join date of a person", _E,
       employee_id="employee", department_id="department", location_id="location"),
    _t("manager", "the person's direct manager (REPORTS_TO)", _E, employee_id="employee"),
    _t("direct_reports", "people who report directly to the person", _E, employee_id="employee"),
    _t("skip_manager", "the manager's manager", _E, employee_id="employee"),
    _t("department_head", "head of a department", {"department_id": Param("department")},
       employee_id="employee", department_id="department"),
    _t("headcount", "number of people in a department (all statuses)", {"department_id": Param("department")},
       department_id="department"),
    _t("project_team", "people who worked on a project, optionally filtered",
       {"project_id": Param("project"), "role": Param("text", False, "substring of the assignment role"),
        "current": Param("bool", False, "only current members"),
        "location_id": Param("location", False, "only people based there"),
        "reports_to": Param("employee", False, "only direct reports of this person")},
       employee_id="employee"),
    _t("projects_of", "projects a person worked on", _E, project_id="project"),
    _t("project_leadership", "sponsor and lead of a project, or owner and engineering lead of a product",
       {"entity_id": Param("project_or_product")}, employee_id="employee"),
    _t("project_departments", "departments that contributed to a project", {"project_id": Param("project")},
       department_id="department"),
    _t("previous_employer", "Zenvora employees who previously worked at an organisation",
       {"org_id": Param("organization")}, employee_id="employee"),
    _t("employers_of", "a person's previous employers", _E, org_id="organization"),
    _t("skill_holders", "people who list a skill",
       {"skill_id": Param("skill"), "expand_variants": Param("bool", False, "include variant names of the skill")},
       employee_id="employee", skill_id="skill"),
    _t("policy_owner", "department or person that owns, prepared, reviewed or approved a policy",
       {"policy_id": Param("policy")}),
    _t("policy_references", "policies a policy refers to (out) or that refer to it (in)",
       {"policy_id": Param("policy"), "direction": Param("direction")}, policy_id="policy"),
    _t("location_roster", "people based at an office location", {"location_id": Param("location")},
       employee_id="employee"),
    _t("approvals_chain", "reporting chain to the top with bands, department head and HR head", _E),
)
TEXT_SEARCH = OpSpec("text_search", "search", "search policy sections and pages (public text)", {
    "query": Param("text", doc="what to look for"),
    "doc_type": Param("doc_type", False, "only this kind of document"),
    "entity_id": Param("entity", False, "only documents about this entity: one policy's sections, "
                                        "a department or project page, a person's profile"),
})
_RULE_PARAM_KINDS = {"city": "text", "amount": "int", "international": "bool",
                     "department_code": "department_code", "band": "band", "base_city": "text"}


def _rule_ops() -> tuple[OpSpec, ...]:
    out = []
    for rid, r in load_rules().items():
        hint = 'the person; "asker" for I/my' + ("; null with the params below" if r.subject_params else "")
        params = {"subject": Param("subject", False, hint)}
        for p in r.params:
            params[p] = Param(_RULE_PARAM_KINDS[p], False)
        for p in r.subject_params:
            params[p] = Param(_RULE_PARAM_KINDS[p], False, "only with subject null: a hypothetical person")
        out.append(OpSpec(rid, "rule", r.description, params))
    return tuple(out)


OPS: dict[str, OpSpec] = {o.name: o for o in (*TEMPLATE_OPS, *_rule_ops(), TEXT_SEARCH)}


# ---------------------------------------------------------------- plan format

ArgValue = str | int | float | bool | None


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: str
    args: dict[str, ArgValue] = {}


class AltPath(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: Intent
    plan: list[Step] = Field(default_factory=list, max_length=MAX_STEPS)


class RouterOutput(BaseModel):
    """What the router LLM returns. Validated against the linked entities in the context."""

    model_config = ConfigDict(extra="forbid")
    intent: Intent
    entities: list[str] = []  # linked ids the question is about
    needs_identity: bool = False  # the answer depends on who is asking
    confidence: float = Field(ge=0.0, le=1.0)
    plan: list[Step] = Field(default_factory=list, max_length=MAX_STEPS)
    alternative: AltPath | None = None  # second path, used when confidence is low
    # 3.3c: the question asks about anyone's employment status, leave, notice, last day,
    # availability, pay or contact details (the asker's own included), or for records or
    # instructions. Selects the uniform restricted refusal; access is never decided by it.
    restricted_fact: bool = False

    @model_validator(mode="after")
    def _check(self, info: ValidationInfo) -> RouterOutput:
        links = (info.context or {}).get("links")
        errors = route_errors(self, links if links is not None else LinkResult((), ()))
        if errors:
            raise ValueError("; ".join(errors))
        return self


def route_errors(out: RouterOutput, links: LinkResult) -> list[str]:
    linked = {m.id for m in links.matches}
    errors = [f"entities: {e!r} is not a linked entity id" for e in out.entities if e not in linked]
    paths = [("plan", out.intent, out.plan)]
    if out.alternative is not None:
        paths.append(("alternative.plan", out.alternative.intent, out.alternative.plan))
    uses_asker = False
    for name, intent, plan in paths:
        if intent == "refuse" and plan:
            errors.append(f"{name}: intent refuse must have an empty plan")
        errs, asker = plan_errors(plan, links, name)
        errors += errs
        uses_asker |= asker
    if out.intent == "refuse" and out.alternative is not None:
        errors.append("alternative: intent refuse takes no alternative")
    if uses_asker and not out.needs_identity:
        errors.append('needs_identity must be true when a step uses "asker"')
    return errors


def plan_errors(plan: list[Step], links: LinkResult, name: str = "plan") -> tuple[list[str], bool]:
    """Errors in a plan, and whether it uses "asker"."""
    labels = {m.id: m.label for m in links.matches}
    unresolved = {u.surface.upper() for u in links.unresolved}
    errors: list[str] = []
    uses_asker = False
    for i, step in enumerate(plan, 1):
        where = f"{name}[{i}] {step.op}"
        spec = OPS.get(step.op)
        if spec is None:
            errors.append(f"{where}: unknown op; use only ops from the catalogue")
            continue
        for a in sorted(set(step.args) - set(spec.params)):
            errors.append(f"{where}: unknown arg {a!r}; allowed {sorted(spec.params)}")
        args = {k: v for k, v in step.args.items() if v is not None}
        for pname, p in spec.params.items():
            if pname not in args:
                if p.required:
                    errors.append(f"{where}: missing required arg {pname!r}")
                continue
            err, asker = _arg_error(args[pname], p.kind, plan, i, labels, unresolved)
            uses_asker |= asker
            if err:
                errors.append(f"{where}.{pname}: {err}")
        if spec.family == "rule":
            rule = load_rules()[spec.name]
            sub_params = set(rule.subject_params) & set(args)
            if "subject" in args and sub_params:
                errors.append(f"{where}: {sorted(sub_params)} only apply when subject is null")
            if "subject" not in args and not sub_params:
                errors.append(f"{where}: give a subject (an employee id or \"asker\") or subject params")
    return errors, uses_asker


def _arg_error(value: ArgValue, kind: str, plan: list[Step], i: int, labels: dict[str, str],
               unresolved: set[str]) -> tuple[str | None, bool]:
    if kind in ENTITY_KINDS:
        if not isinstance(value, str):
            return f"expected an entity id, got {value!r}", False
        if value == ASKER:
            return (None, True) if kind in PERSON_KINDS else ('"asker" is only allowed for a person', False)
        if m := REF.match(value):
            return _ref_error(int(m[1]), m[2], kind, plan, i), False
        if value.upper() in unresolved:
            return f"{value!r} does not exist (unresolved mention); leave this step out", False
        if value not in labels:
            return f"{value!r} is not a linked entity id", False
        if labels[value] not in ENTITY_KINDS[kind]:
            return f"{value!r} is a {labels[value]}, expected {sorted(ENTITY_KINDS[kind])}", False
        return None, False
    if kind == "text":
        ok = isinstance(value, str) and 0 < len(value.strip()) <= 300
        return (None if ok else f"expected non-empty text, got {value!r}"), False
    if kind == "int":
        ok = isinstance(value, int) and not isinstance(value, bool) and value >= 0
        return (None if ok else f"expected a non-negative integer, got {value!r}"), False
    if kind == "bool":
        return (None if isinstance(value, bool) else f"expected true/false, got {value!r}"), False
    allowed = _enum(kind)
    if allowed is None:
        raise AssertionError(kind)
    return (None if value in allowed else f"expected one of {list(allowed)}, got {value!r}"), False


def _ref_error(n: int, fld: str, kind: str, plan: list[Step], i: int) -> str | None:
    if not 1 <= n < i:
        return f"${n} must refer to an earlier step (1..{i - 1})"
    src = OPS.get(plan[n - 1].op)
    if src is None or src.family != "template":
        return f"${n} is not a template step; only template rows can be referenced"
    if fld not in src.outputs:
        return f"{src.name} has no output {fld!r}; outputs are {sorted(src.outputs)}"
    if kind not in REF_TARGETS[src.outputs[fld]]:
        return f"${n}.{fld} is a {src.outputs[fld]}, not usable as {kind}"
    return None


# ---------------------------------------------------------------- execution

class PlanError(RuntimeError):
    """A plan step that cannot run (unknown op): never executed."""


StepOutput = T.TemplateResult | RuleResult | list[Hit] | None


@dataclass
class StepResult:
    n: int
    op: str
    args: dict[str, Any]  # resolved
    output: StepOutput = None
    error: str | None = None  # why the step did not run (empty reference, ...)


TEMPLATE_FUNCS: dict[str, Callable[..., T.TemplateResult]] = {
    "employee_card": T.employee_card, "manager": T.manager, "direct_reports": T.direct_reports,
    "skip_manager": T.skip_manager, "department_head": T.department_head, "headcount": T.headcount,
    "project_team": T.project_team, "projects_of": T.projects_of, "project_leadership": T.project_leadership,
    "project_departments": T.project_departments, "previous_employer": T.previous_employer,
    "employers_of": T.employers_of, "skill_holders": T.skill_holders, "policy_owner": T.policy_owner,
    "policy_references": T.policy_references, "location_roster": T.location_roster,
    "approvals_chain": T.approvals_chain,
}


def run_plan(plan: list[Step], *, driver: Driver, asker_id: str, as_of: date,
             embedder: QueryEmbedder | None = None, k: int = 5) -> list[StepResult]:
    """Run the steps in order. A reference to an empty or failed step skips the step."""
    for step in plan:  # defence in depth: refuse the whole plan before running anything
        if step.op not in OPS:
            raise PlanError(f"unknown op {step.op!r}")
    results: list[StepResult] = []
    for n, step in enumerate(plan, 1):
        spec = OPS[step.op]
        args, error = _resolve(step.args, results, asker_id)
        res = StepResult(n, step.op, args, error=error)
        if error is None:
            if spec.family == "template":
                res.output = TEMPLATE_FUNCS[spec.name](driver, **args)
            elif spec.family == "rule":
                params = {a: v for a, v in args.items() if a != "subject"}
                res.output = evaluate_rule(spec.name, args.get("subject"), asker_id, as_of, params,
                                           driver=driver if load_rules()[spec.name].people else None)
            else:  # text_search: restricted chunks only for the subject, their manager or HR
                res.output = search_for_asker(args["query"], asker_id, k=k, doc_type=args.get("doc_type"),
                                              entity_id=args.get("entity_id"), driver=driver, embedder=embedder)
        results.append(res)
    return results


def _resolve(raw: dict[str, ArgValue], done: list[StepResult], asker_id: str) -> tuple[dict[str, Any], str | None]:
    out: dict[str, Any] = {}
    for name, value in raw.items():
        if value is None:
            continue
        if value == ASKER:
            value = asker_id
        elif isinstance(value, str) and (m := REF.match(value)):
            src = done[int(m[1]) - 1]
            rows = src.output.rows if isinstance(src.output, T.TemplateResult) else []
            if src.error or not rows or rows[0].get(m[2]) is None:
                return out, f"{value}: step {m[1]} returned no {m[2]}"
            value = rows[0][m[2]]
        out[name] = value
    return out, None


# ---------------------------------------------------------------- evidence and merge

PathName = Literal["primary", "alternative"]


@dataclass
class EvidenceItem:
    path: PathName
    step: StepResult


@dataclass
class Evidence:
    items: list[EvidenceItem] = field(default_factory=list)
    subgraph: Subgraph = field(default_factory=Subgraph)
    citations: list[Citation] = field(default_factory=list)


def _parts(out: StepOutput) -> tuple[Subgraph, list[Citation]]:
    if isinstance(out, T.TemplateResult):
        return out.subgraph, list(out.citations())
    if isinstance(out, RuleResult):
        return out.subgraph, list(out.citations)
    if isinstance(out, list):
        return Subgraph(), [ChunkCitation(id=h["chunk_id"]) for h in out]
    return Subgraph(), []


def collect(steps: list[StepResult], path: PathName = "primary") -> Evidence:
    ev = Evidence()
    for s in steps:
        sub, cites = _parts(s.output)
        ev = merge(ev, Evidence([EvidenceItem(path, s)], sub, cites))
    return ev


def merge(a: Evidence, b: Evidence) -> Evidence:
    """a's items first, then b's; nodes, edges and citations deduplicated, first one kept
    (a node or edge with rule evidence replaces a bare copy, see `Subgraph.merge`)."""
    cites: dict[str, Citation] = {}
    for c in [*a.citations, *b.citations]:
        cites.setdefault(c.model_dump_json(), c)
    return Evidence(items=[*a.items, *b.items],
                    subgraph=a.subgraph.merge(b.subgraph),
                    citations=list(cites.values()))
