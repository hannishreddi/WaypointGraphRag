"""Template and rule coverage map on the 60 dev questions (PLAN 2.2, 2.3). Report only, not routing.

Each dev question gets a hand-written entry: a template with its arguments resolved from
`link_entities` (by label), a two-step composition, a rule evaluation (2.3: rule id,
subject from linking or the asker, hand-picked params such as the city), or a class
(needs-text for 2.5, other). Template rows are rendered into a plain answer and scored with
the existing scorers. Judge-routed gold is not scored (the judge is an API call): those
rows show the rendered answer next to the gold and an entity-match check for a hand look.
Offline: Neo4j only, no API calls. Writes docs/template_coverage_dev.md.

    python -m waypoint.eval.template_coverage
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from neo4j import Driver

from waypoint.config import DEFAULT_AS_OF, REPO_ROOT
from waypoint.eval.entities import load_entities
from waypoint.eval.questions import Question, asker_for, load_questions
from waypoint.eval.scorers import assign_scorer, score_answer
from waypoint.graph import templates as T
from waypoint.graph.db import get_driver
from waypoint.retrieval.linking import link_entities
from waypoint.rules.engine import RuleResult
from waypoint.rules.engine import evaluate as evaluate_rule

OUT = REPO_ROOT / "docs" / "template_coverage_dev.md"


@dataclass(frozen=True)
class Spec:
    kind: str  # template | composed | rule | needs-text | other
    template: str = ""
    args: tuple[tuple[str, Any], ...] = ()  # (param, "@Label" from linking, or a literal)
    note: str = ""


def tpl(name: str, note: str = "", **args: Any) -> Spec:
    return Spec("template", name, tuple(args.items()), note)


def composed(name: str, note: str) -> Spec:
    return Spec("composed", name, note=note)


def cls(kind: str, note: str) -> Spec:
    return Spec(kind, note=note)


def rule(rule_id: str, subject: str | None, note: str = "", **params: Any) -> Spec:
    """subject: "@Employee" (linked), "@asker" (the question's asker) or None (params only)."""
    return Spec("rule", rule_id, (("subject", subject), *params.items()), note)


E, D, P = "@Employee", "@Department", "@Project"
MANAGER_DEPT_HEAD = composed("manager_department_head", "manager -> employee_card -> department_head")

COVERAGE: dict[str, Spec] = {
    **{q: tpl("manager", employee_id=E) for q in ("Q002", "Q003", "Q006", "Q014", "Q015")},
    **{q: tpl("employee_card", employee_id=E) for q in ("Q024", "Q025", "Q035")},
    **{q: tpl("department_head", department_id=D) for q in ("Q042", "Q052", "Q058")},
    **{q: tpl("headcount", department_id=D) for q in ("Q047", "Q049", "Q053")},
    **{q: tpl("direct_reports", employee_id=E) for q in ("Q062", "Q064", "Q068")},
    **{q: tpl("skip_manager", employee_id=E) for q in ("Q075", "Q080", "Q083")},
    **{q: MANAGER_DEPT_HEAD for q in ("Q087", "Q090", "Q091")},
    **{q: tpl("projects_of", employee_id=E) for q in ("Q096", "Q102")},
    **{q: tpl("project_departments", project_id=P) for q in ("Q104", "Q110")},
    **{q: tpl("project_leadership", entity_id=P) for q in ("Q113", "Q119")},
    **{q: tpl("project_team", project_id=P, location_id="@Location") for q in ("Q122", "Q127")},
    "Q129": tpl("project_team", "'engineers' not filtered", project_id=P, reports_to=E),
    **{q: tpl("previous_employer", org_id="@Organization")
       for q in ("Q133", "Q136", "Q137", "Q139", "Q144")},
    **{q: tpl("skill_holders", skill_id="@Skill") for q in ("Q150", "Q153", "Q155")},
    "Q167": cls("needs-text", "education is not in the graph (resumes)"),
    "Q169": cls("other", "no template: join-date filter over employees"),
    "Q173": rule("WORK_MODE", E, "work mode at as-of (induction, ZEN-POL-002)"),
    "Q178": rule("WORK_MODE", E, "work mode at as-of (standard rule, ZEN-POL-002)"),
    "Q181": rule("NOTICE_PERIOD", E, "notice period by band and probation (ZEN-POL-003)"),
    "Q186": rule("SABBATICAL_ELIGIBILITY", E, "service years at as-of (ZEN-POL-003)"),
    "Q193": rule("HOTEL_CAP", E, "city param by hand; Pune is Tier-1 but not a location", city="Pune"),
    "Q195": rule("HOTEL_CAP", E, "city param by hand", city="Visakhapatnam"),
    "Q196": rule("HOTEL_CAP", E, "city param by hand", city="Bengaluru"),
    "Q207": cls("needs-text", "appraisal calendar (ZEN-DPL-HR-01)"),
    "Q210": rule("WORK_MODE", "@asker", "subject = asker ZV-1033 (serving notice); self may see it"),
    "Q211": cls("needs-text", "leave entitlements and certificate rule (ZEN-POL-003)"),
    "Q214": cls("needs-text", "maternity leave (ZEN-POL-003)"),
    "Q218": cls("needs-text", "offences skipping warnings (ZEN-POL-004)"),
    "Q220": cls("needs-text", "AI tools and data classes (ZEN-POL-005)"),
    "Q232": cls("needs-text", "incident severities (ZEN-DPL-DCL-01)"),
    "Q235": cls("needs-text", "support SLA targets (ZEN-DPL-CSC-01)"),
    "Q239": tpl("policy_references", policy_id="@Policy", direction="in"),
    "Q243": cls("needs-text", "Presiding Officer is named in ZEN-POL-008; then the manager template"),
    "Q247": rule("WORK_MODE", None, "no subject: department_code=CSC as a param", department_code="CSC"),
}

# Judge-routed rule rows, checked by hand against the gold (no API calls).
HAND_CHECKS: dict[str, str] = {
    "Q178": "correct (same mode, standard rule, ZEN-POL-002; longer reason)",
    "Q210": "correct in substance (full WFO while serving notice); the yes/no is the generator's (2.5)",
    "Q247": "correct in substance (on site except declared contingency, same two policies); no explicit 'No'",
}

_RELATION = {"SPONSORS": "Sponsor", "LEADS": "Lead", "OWNS_PRODUCT": "Owner",
             "LEADS_ENGINEERING_OF": "Engineering lead"}


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def render(name: str, r: T.TemplateResult) -> str:
    rows = r.rows
    if name in ("manager", "skip_manager", "department_head"):
        return "; ".join(f"{x['name']} ({x['title']})" for x in rows)
    if name == "employee_card":
        return "; ".join(f"{x['title']}, band {x['band']} ({x['department']}, {x['location']})" for x in rows)
    if name == "headcount":
        return str(rows[0]["headcount"]) if rows else ""
    if name in ("direct_reports", "project_team", "previous_employer", "skill_holders", "project_departments"):
        return "; ".join(_unique([x["name"] for x in rows]))
    if name == "projects_of":
        return "; ".join(_unique([x["project"] for x in rows]))
    if name == "project_leadership":
        return " ".join(f"{_RELATION[x['relation']]}: {x['name']}." for x in rows)
    if name == "policy_references":
        return "; ".join(f"{x['policy_id']} ({x['title']})" for x in rows)
    raise KeyError(name)


def render_rule(r: RuleResult) -> str:
    v = r.value
    if r.status != "ok":
        return f"[{r.status}]"
    policies = ", ".join(dict.fromkeys(c.id for c in r.citations if c.type == "policy"))
    lower = lambda t: t[:1].lower() + t[1:]  # noqa: E731
    if r.rule_id == "WORK_MODE":
        return f"{v['work_mode']}. {v['reason']} ({policies})"
    if r.rule_id == "NOTICE_PERIOD":
        return f"{v['notice_period_days']} days ({lower(v['reason'])})"
    if r.rule_id == "SABBATICAL_ELIGIBILITY":
        return f"{'Yes' if v['eligible'] else 'No'}. {v['reason']}."
    if r.rule_id == "HOTEL_CAP":
        return f"INR {v['cap_inr']:,} ({lower(v['reason'])})"
    raise KeyError(r.rule_id)


def _rule_result(spec: Spec, q: Question) -> RuleResult | None:
    args = dict(spec.args)
    subject = args.pop("subject")
    if subject == "@asker":
        subject = asker_for(q.id)
    elif subject is not None:
        ids = [m.id for m in link_entities(q.question) if m.label == subject[1:]]
        if not ids:
            return None
        subject = ids[0]
    return evaluate_rule(spec.template, subject, asker_for(q.id), DEFAULT_AS_OF, args)


def _args(spec: Spec, q: Question) -> dict[str, Any] | None:
    links = link_entities(q.question)
    out: dict[str, Any] = {}
    for param, value in spec.args:
        if isinstance(value, str) and value.startswith("@"):
            ids = [m.id for m in links if m.label == value[1:]]
            if not ids:
                return None
            out[param] = ids[0]
        else:
            out[param] = value
    return out


def _manager_department_head(driver: Driver, q: Question) -> tuple[str, list[str]]:
    eid = next(m.id for m in link_entities(q.question) if m.label == "Employee")
    mgr = T.manager(driver, eid)
    card = T.employee_card(driver, mgr.rows[0]["employee_id"])
    head = T.department_head(driver, card.rows[0]["department_id"])
    answer = "; ".join(f"{x['name']} ({x['department']})" for x in head.rows)
    return answer, mgr.paths + card.paths + head.paths


COMPOSED: dict[str, Callable[[Driver, Question], tuple[str, list[str]]]] = {
    "manager_department_head": _manager_department_head,
}


def evaluate(driver: Driver) -> list[dict[str, Any]]:
    ents = load_entities()
    out = []
    for q in load_questions("dev"):
        spec = COVERAGE[q.id]
        row: dict[str, Any] = {"q": q, "spec": spec, "answer": "", "paths": [], "status": spec.kind,
                               "score": None, "scorer": assign_scorer(q, ents).kind}
        if spec.kind in ("template", "composed", "rule"):
            if spec.kind == "rule":
                rr = _rule_result(spec, q)
                if rr is None:
                    row["status"] = "link-miss"
                    out.append(row)
                    continue
                row["answer"] = render_rule(rr)
                row["paths"] = [c.path for c in rr.citations if c.type == "graph"]
            elif spec.kind == "template":
                args = _args(spec, q)
                if args is None:
                    row["status"] = "link-miss"
                    out.append(row)
                    continue
                result = getattr(T, spec.template)(driver, **args)
                row["answer"], row["paths"] = render(spec.template, result), result.paths
            else:
                row["answer"], row["paths"] = COMPOSED[spec.template](driver, q)
            res = score_answer(assign_scorer(q, ents), q, row["answer"], ents)
            row["scorer"] = res.kind
            if res.kind == "judge":
                if row["answer"].strip() == q.expected_answer.strip():
                    row["status"] = "hand-check: identical to gold"
                elif q.id in HAND_CHECKS:
                    row["status"] = f"hand-check: {HAND_CHECKS[q.id]}"
                else:
                    same = ents.find(row["answer"]) == ents.find(q.expected_answer)
                    row["status"] = "hand-check: entities match" if same else "hand-check: entities differ"
            else:
                row["score"] = res.score
                row["status"] = "correct" if res.score == 1 else ("partial" if res.score else "wrong")
        out.append(row)
    return out


def _answered(r: dict[str, Any]) -> bool:
    return r["spec"].kind in ("template", "composed", "rule")


def _summary(rows: list[dict[str, Any]], key: Callable[[Question], Any], title: str) -> list[str]:
    groups: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[key(r["q"])].append(r)
    lines = [f"## By {title}", "",
             "| group | n | template | composed | rule | correct | hand-check | needs-text | other |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for g in sorted(groups) + ["all"]:
        rs = rows if g == "all" else groups[g]
        c = lambda f: sum(1 for r in rs if f(r))  # noqa: E731
        lines.append(
            f"| {g} | {len(rs)} | {c(lambda r: r['spec'].kind == 'template')} "
            f"| {c(lambda r: r['spec'].kind == 'composed')} | {c(lambda r: r['spec'].kind == 'rule')} "
            f"| {c(lambda r: r['status'] == 'correct')} | {c(lambda r: r['status'].startswith('hand-check'))} "
            f"| {c(lambda r: r['status'] == 'needs-text')} "
            f"| {c(lambda r: r['status'] == 'other')} |")
    return lines + [""]


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def write_report(rows: list[dict[str, Any]]) -> str:
    answered = [r for r in rows if _answered(r)]
    scored = [r for r in answered if r["score"] is not None]
    lines = [
        "# Template and rule coverage on the dev split",
        "",
        "Generated by `python -m waypoint.eval.template_coverage` (Neo4j only, no API calls).",
        "Report only: the template for each question is chosen by hand here; runtime routing is 2.4.",
        "Template arguments come from `link_entities` on the question text. Template rows are",
        "rendered into a plain answer and scored with the existing scorers (exact / set-F1).",
        "Judge-routed gold is not scored offline; those rows are marked hand-check, with an",
        "entity-match check (`waypoint.eval.entities`) and the answer shown next to the gold.",
        "Dev has 60 questions; groups are small.",
        "",
        "Caveats: the template per question is hand-picked, so this is an upper bound on what",
        "routing (2.4) can reach with these templates. Q129 asks for \"engineers\" but the template",
        "has no title filter; it is correct only because everyone on Atlas who reports to",
        "Divya Krishnamurthy is an engineer. Composed rows chain templates in code here; at",
        "runtime that is the router's or answerer's job.",
        "",
        "Rules (2.3): rule rows call `waypoint.rules.engine.evaluate` at as-of 2026-10-10 with the",
        "question's asker (HR by default; Q210 is asked by ZV-1033 about himself). The rule, the",
        "subject and params such as the city are picked by hand (extracting them is 2.4). The",
        "answer is a plain rendering of the rule result; judge-routed rows are hand-checked with",
        "the verdict in the status column.",
        "",
        f"- answered: {len(answered)} / {len(rows)} "
        f"(templates {sum(r['spec'].kind == 'template' for r in answered)}, "
        f"composed {sum(r['spec'].kind == 'composed' for r in answered)}, "
        f"rules {sum(r['spec'].kind == 'rule' for r in answered)})",
        f"- scored offline: {len(scored)}, correct {sum(r['status'] == 'correct' for r in scored)}, "
        f"mean score {sum(r['score'] for r in scored) / max(1, len(scored)):.2f}",
        f"- hand-check (judge-routed gold): {sum(r['status'].startswith('hand-check') for r in answered)}",
        f"- needs-text (2.5): {sum(r['status'] == 'needs-text' for r in rows)}; "
        f"other: {sum(r['status'] == 'other' for r in rows)}; "
        f"link misses: {sum(r['status'] == 'link-miss' for r in rows)}",
        "- headcount: the gold counts every employee who works in the department regardless of",
        "  employment status (Data & AI = 4 includes the colleague on maternity leave; Product &",
        "  Design = 4 includes the one serving notice). The template counts WORKS_IN the same way",
        "  and never returns status.",
        "",
    ]
    lines += _summary(rows, lambda q: q.hops, "hops")
    lines += _summary(rows, lambda q: q.category, "category")
    lines += ["## Per question", "",
              "| id | cat | hops | route | status | template / rule answer | gold | note |",
              "|---|---|---:|---|---|---|---|---|"]
    for r in rows:
        q, spec = r["q"], r["spec"]
        route = spec.template or spec.kind
        lines.append(f"| {q.id} | {q.category} | {q.hops} | {route} | {r['status']} "
                     f"| {_cell(r['answer'])} | {_cell(q.expected_answer)} | {_cell(spec.note)} |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    driver = get_driver()
    try:
        rows = evaluate(driver)
    finally:
        driver.close()
    text = write_report(rows)
    OUT.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
