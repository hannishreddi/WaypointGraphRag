"""Parameterised Cypher templates for fact questions. PLAN 2.2, DESIGN "Cypher templates".

Each template takes entity ids (from `waypoint.retrieval.linking.link_entities`) and plain
options, runs one constant query through `run_read` (guard + read transaction) with
parameters only, and returns a `TemplateResult`: rows, the evidence subgraph and graph-path
strings ("ZV-1004 -REPORTS_TO-> ZV-1003") in the response-contract shape.

Rules: no Chunk nodes, deterministic ORDER BY in every query, no hard-coded entity ids
(the CEO is the employee with no REPORTS_TO, the HR head heads the department with code
HR), and only public employee fields (name, title, band, department, location, join date):
employment status is restricted (rule 6) and never returned.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from neo4j import Driver

from waypoint.contract import GraphCitation, Subgraph, SubgraphEdge, SubgraphNode
from waypoint.graph.db import run_read
from waypoint.retrieval.aliases import skill_variants

HR_DEPARTMENT_CODE = "HR"

# label -> (id property, display property)
_KEYS = {
    "Employee": ("employee_id", "name"), "Department": ("department_id", "name"),
    "Project": ("project_id", "name"), "Product": ("product_id", "name"),
    "Policy": ("policy_id", "title"), "Organization": ("org_id", "name"),
    "Location": ("location_id", "name"), "Skill": ("skill_id", "name"),
}


def _n(var: str, label: str) -> str:
    """Cypher map for a subgraph node."""
    key, name = _KEYS[label]
    return f"{{id: {var}.{key}, label: '{label}', name: {var}.{name}}}"


def _e(a: str, a_label: str, rel: str, b: str, b_label: str) -> str:
    """Cypher map for a subgraph edge, in the relationship's direction."""
    return f"{{source: {a}.{_KEYS[a_label][0]}, type: '{rel}', target: {b}.{_KEYS[b_label][0]}}}"


_PERSON = "{a}.employee_id AS employee_id, {a}.name AS name, {a}.title AS title"


def _person(var: str) -> str:
    return _PERSON.format(a=var)


QUERIES: dict[str, str] = {
    "employee_card": f"""
MATCH (e:Employee {{employee_id: $employee_id}})
OPTIONAL MATCH (e)-[:WORKS_IN]->(d:Department)
OPTIONAL MATCH (e)-[:BASED_AT]->(l:Location)
RETURN {_person('e')}, e.band AS band, toString(e.join_date) AS join_date,
       d.department_id AS department_id, d.name AS department,
       l.location_id AS location_id, l.name AS location,
       [{_n('e', 'Employee')}, {_n('d', 'Department')}, {_n('l', 'Location')}] AS _nodes,
       [{_e('e', 'Employee', 'WORKS_IN', 'd', 'Department')},
        {_e('e', 'Employee', 'BASED_AT', 'l', 'Location')}] AS _edges
ORDER BY employee_id""",

    "manager": f"""
MATCH (e:Employee {{employee_id: $employee_id}})-[:REPORTS_TO]->(m:Employee)
RETURN {_person('m')},
       [{_n('e', 'Employee')}, {_n('m', 'Employee')}] AS _nodes,
       [{_e('e', 'Employee', 'REPORTS_TO', 'm', 'Employee')}] AS _edges
ORDER BY employee_id""",

    "direct_reports": f"""
MATCH (r:Employee)-[:REPORTS_TO]->(e:Employee {{employee_id: $employee_id}})
RETURN {_person('r')},
       [{_n('r', 'Employee')}, {_n('e', 'Employee')}] AS _nodes,
       [{_e('r', 'Employee', 'REPORTS_TO', 'e', 'Employee')}] AS _edges
ORDER BY name, employee_id""",

    "skip_manager": f"""
MATCH (e:Employee {{employee_id: $employee_id}})-[:REPORTS_TO]->(m:Employee)-[:REPORTS_TO]->(s:Employee)
RETURN {_person('s')}, m.employee_id AS via_employee_id, m.name AS via_name,
       [{_n('e', 'Employee')}, {_n('m', 'Employee')}, {_n('s', 'Employee')}] AS _nodes,
       [{_e('e', 'Employee', 'REPORTS_TO', 'm', 'Employee')},
        {_e('m', 'Employee', 'REPORTS_TO', 's', 'Employee')}] AS _edges
ORDER BY employee_id""",

    "department_head": f"""
MATCH (h:Employee)-[:HEADS]->(d:Department {{department_id: $department_id}})
RETURN {_person('h')}, d.department_id AS department_id, d.name AS department,
       [{_n('h', 'Employee')}, {_n('d', 'Department')}] AS _nodes,
       [{_e('h', 'Employee', 'HEADS', 'd', 'Department')}] AS _edges
ORDER BY employee_id""",

    # Counts every WORKS_IN regardless of employment status (status itself is not returned).
    "headcount": f"""
MATCH (d:Department {{department_id: $department_id}})
OPTIONAL MATCH (e:Employee)-[:WORKS_IN]->(d)
WITH d, e ORDER BY e.name, e.employee_id
WITH d, count(e) AS headcount, collect(e.name) AS members,
     collect({_n('e', 'Employee')}) AS member_nodes,
     collect({_e('e', 'Employee', 'WORKS_IN', 'd', 'Department')}) AS member_edges
RETURN d.department_id AS department_id, d.name AS department, headcount, members,
       [{_n('d', 'Department')}] + member_nodes AS _nodes, member_edges AS _edges
ORDER BY department_id""",

    "project_team": f"""
MATCH (e:Employee)-[w:WORKED_ON]->(p:Project {{project_id: $project_id}})
WHERE ($role IS NULL OR toLower(w.role) CONTAINS toLower($role))
  AND ($current IS NULL OR w.is_current = $current)
OPTIONAL MATCH (e)-[:BASED_AT]->(l:Location)
OPTIONAL MATCH (e)-[:REPORTS_TO]->(m:Employee)
WITH e, w, p, l, m
WHERE ($location_id IS NULL OR l.location_id = $location_id)
  AND ($reports_to IS NULL OR m.employee_id = $reports_to)
RETURN {_person('e')}, w.role AS role, toString(w.from_date) AS from_date,
       toString(w.to_date) AS to_date, w.is_current AS is_current,
       l.location_id AS location_id, l.name AS location, m.employee_id AS manager_id,
       [{_n('e', 'Employee')}, {_n('p', 'Project')}]
         + CASE WHEN $location_id IS NULL THEN [] ELSE [{_n('l', 'Location')}] END
         + CASE WHEN $reports_to IS NULL THEN [] ELSE [{_n('m', 'Employee')}] END AS _nodes,
       [{_e('e', 'Employee', 'WORKED_ON', 'p', 'Project')}]
         + CASE WHEN $location_id IS NULL THEN []
                ELSE [{_e('e', 'Employee', 'BASED_AT', 'l', 'Location')}] END
         + CASE WHEN $reports_to IS NULL THEN []
                ELSE [{_e('e', 'Employee', 'REPORTS_TO', 'm', 'Employee')}] END AS _edges
ORDER BY name, employee_id""",

    "projects_of": f"""
MATCH (e:Employee {{employee_id: $employee_id}})-[w:WORKED_ON]->(p:Project)
RETURN p.project_id AS project_id, p.name AS project, w.role AS role,
       toString(w.from_date) AS from_date, toString(w.to_date) AS to_date, w.is_current AS is_current,
       [{_n('e', 'Employee')}, {_n('p', 'Project')}] AS _nodes,
       [{_e('e', 'Employee', 'WORKED_ON', 'p', 'Project')}] AS _edges
ORDER BY from_date, project_id""",

    # Projects: SPONSORS, LEADS. Products: OWNS_PRODUCT, LEADS_ENGINEERING_OF.
    "project_leadership": f"""
MATCH (e:Employee)-[r:SPONSORS|LEADS|OWNS_PRODUCT|LEADS_ENGINEERING_OF]->(x)
WHERE (x:Project AND x.project_id = $entity_id) OR (x:Product AND x.product_id = $entity_id)
WITH e, r, x, coalesce(x.project_id, x.product_id) AS xid, labels(x)[0] AS xlabel
RETURN type(r) AS relation, {_person('e')}, xid AS target_id, x.name AS target,
       [{_n('e', 'Employee')}, {{id: xid, label: xlabel, name: x.name}}] AS _nodes,
       [{{source: e.employee_id, type: type(r), target: xid}}] AS _edges
ORDER BY relation DESC, employee_id""",

    "project_departments": f"""
MATCH (d:Department)-[:CONTRIBUTES_TO]->(p:Project {{project_id: $project_id}})
RETURN d.department_id AS department_id, d.name AS name,
       [{_n('d', 'Department')}, {_n('p', 'Project')}] AS _nodes,
       [{_e('d', 'Department', 'CONTRIBUTES_TO', 'p', 'Project')}] AS _edges
ORDER BY name, department_id""",

    "previous_employer": f"""
MATCH (e:Employee)-[x:PREVIOUSLY_AT]->(o:Organization {{org_id: $org_id}})
RETURN e.employee_id AS employee_id, e.name AS name, x.title AS role_title,
       x.start AS start, x.end AS end,
       [{_n('e', 'Employee')}, {_n('o', 'Organization')}] AS _nodes,
       [{_e('e', 'Employee', 'PREVIOUSLY_AT', 'o', 'Organization')}] AS _edges
ORDER BY name, employee_id, start""",

    "employers_of": f"""
MATCH (e:Employee {{employee_id: $employee_id}})-[x:PREVIOUSLY_AT]->(o:Organization)
RETURN o.org_id AS org_id, o.name AS organization, x.title AS role_title,
       x.start AS start, x.end AS end,
       [{_n('e', 'Employee')}, {_n('o', 'Organization')}] AS _nodes,
       [{_e('e', 'Employee', 'PREVIOUSLY_AT', 'o', 'Organization')}] AS _edges
ORDER BY start, org_id""",

    "skill_holders": f"""
MATCH (e:Employee)-[:HAS_SKILL]->(s:Skill)
WHERE s.skill_id IN $skill_ids
RETURN {_person('e')}, s.skill_id AS skill_id, s.name AS skill,
       [{_n('e', 'Employee')}, {_n('s', 'Skill')}] AS _nodes,
       [{_e('e', 'Employee', 'HAS_SKILL', 's', 'Skill')}] AS _edges
ORDER BY name, employee_id, skill_id""",

    "policy_owner": f"""
MATCH (p:Policy {{policy_id: $policy_id}})-[r:OWNED_BY|PREPARED_BY|REVIEWED_BY|APPROVED_BY]->(x)
WITH p, r, x, coalesce(x.department_id, x.employee_id) AS xid, labels(x)[0] AS xlabel
RETURN type(r) AS relation, xid AS id, xlabel AS label, x.name AS name,
       [{_n('p', 'Policy')}, {{id: xid, label: xlabel, name: x.name}}] AS _nodes,
       [{{source: p.policy_id, type: type(r), target: xid}}] AS _edges
ORDER BY relation, id""",

    "policy_references_out": f"""
MATCH (p:Policy {{policy_id: $policy_id}})-[:REFERENCES]->(q:Policy)
RETURN q.policy_id AS policy_id, q.title AS title,
       [{_n('p', 'Policy')}, {_n('q', 'Policy')}] AS _nodes,
       [{_e('p', 'Policy', 'REFERENCES', 'q', 'Policy')}] AS _edges
ORDER BY policy_id""",

    "policy_references_in": f"""
MATCH (q:Policy)-[:REFERENCES]->(p:Policy {{policy_id: $policy_id}})
RETURN q.policy_id AS policy_id, q.title AS title,
       [{_n('q', 'Policy')}, {_n('p', 'Policy')}] AS _nodes,
       [{_e('q', 'Policy', 'REFERENCES', 'p', 'Policy')}] AS _edges
ORDER BY policy_id""",

    "location_roster": f"""
MATCH (e:Employee)-[:BASED_AT]->(l:Location {{location_id: $location_id}})
OPTIONAL MATCH (e)-[:WORKS_IN]->(d:Department)
RETURN {_person('e')}, d.name AS department, l.name AS location,
       [{_n('e', 'Employee')}, {_n('l', 'Location')}] AS _nodes,
       [{_e('e', 'Employee', 'BASED_AT', 'l', 'Location')}] AS _edges
ORDER BY name, employee_id""",

    # Everyone a band-dependent approval can involve; the rule engine (2.3) picks who approves.
    "approvals_chain": f"""
MATCH path = (e:Employee {{employee_id: $employee_id}})-[:REPORTS_TO*0..]->(top:Employee)
WHERE NOT (top)-[:REPORTS_TO]->(:Employee)
OPTIONAL MATCH (e)-[:WORKS_IN]->(d:Department)<-[:HEADS]-(dh:Employee)
OPTIONAL MATCH (hr:Department {{code: $hr_code}})<-[:HEADS]-(hh:Employee)
RETURN [n IN nodes(path) | n {{.employee_id, .name, .title, .band}}] AS chain,
       top {{.employee_id, .name, .title, .band}} AS ceo,
       d.department_id AS department_id,
       dh {{.employee_id, .name, .title, .band}} AS department_head,
       hr.department_id AS hr_department_id,
       hh {{.employee_id, .name, .title, .band}} AS hr_head,
       [n IN nodes(path) | {_n('n', 'Employee')}]
         + [{_n('d', 'Department')}, {_n('dh', 'Employee')}, {_n('hr', 'Department')}, {_n('hh', 'Employee')}]
         AS _nodes,
       [r IN relationships(path) | {{source: startNode(r).employee_id, type: 'REPORTS_TO',
                                     target: endNode(r).employee_id}}]
         + [{_e('e', 'Employee', 'WORKS_IN', 'd', 'Department')},
            {_e('dh', 'Employee', 'HEADS', 'd', 'Department')},
            {_e('hh', 'Employee', 'HEADS', 'hr', 'Department')}] AS _edges
ORDER BY length(path)""",
}


@dataclass
class TemplateResult:
    template: str
    params: dict[str, Any]
    rows: list[dict[str, Any]] = field(default_factory=list)
    subgraph: Subgraph = field(default_factory=Subgraph)
    paths: list[str] = field(default_factory=list)

    def citations(self) -> list[GraphCitation]:
        return [GraphCitation(path=p) for p in self.paths]


def edge_paths(edges: list[dict[str, Any]]) -> list[str]:
    """Chain consecutive edges (one's target is the next one's source) into path strings."""
    out: list[str] = []
    chain = ""
    end = None
    for e in edges:
        if chain and e["source"] == end:
            chain += f" -{e['type']}-> {e['target']}"
        else:
            if chain:
                out.append(chain)
            chain = f"{e['source']} -{e['type']}-> {e['target']}"
        end = e["target"]
    if chain:
        out.append(chain)
    return out


def _run(driver: Driver, name: str, params: dict[str, Any], query: str | None = None) -> TemplateResult:
    result = TemplateResult(name, params)
    nodes: dict[str, SubgraphNode] = {}
    edges: dict[tuple[str, str, str], SubgraphEdge] = {}
    for raw in run_read(driver, QUERIES[query or name], params):
        row_edges = [e for e in raw.pop("_edges") if e["source"] and e["target"]]
        for n in raw.pop("_nodes"):
            if n["id"] is not None:
                nodes.setdefault(n["id"], SubgraphNode(id=n["id"], label=n["label"], name=n["name"] or ""))
        for e in row_edges:
            edges.setdefault((e["source"], e["type"], e["target"]), SubgraphEdge(**e))
        for p in edge_paths(row_edges):
            if p not in result.paths:
                result.paths.append(p)
        result.rows.append(raw)
    result.subgraph = Subgraph(nodes=list(nodes.values()), edges=list(edges.values()))
    return result


# ---------------------------------------------------------------- templates

def employee_card(driver: Driver, employee_id: str) -> TemplateResult:
    return _run(driver, "employee_card", {"employee_id": employee_id})


def manager(driver: Driver, employee_id: str) -> TemplateResult:
    return _run(driver, "manager", {"employee_id": employee_id})


def direct_reports(driver: Driver, employee_id: str) -> TemplateResult:
    return _run(driver, "direct_reports", {"employee_id": employee_id})


def skip_manager(driver: Driver, employee_id: str) -> TemplateResult:
    """The manager's manager."""
    return _run(driver, "skip_manager", {"employee_id": employee_id})


def department_head(driver: Driver, department_id: str) -> TemplateResult:
    return _run(driver, "department_head", {"department_id": department_id})


def headcount(driver: Driver, department_id: str) -> TemplateResult:
    """Everyone who WORKS_IN the department, whatever their employment status."""
    return _run(driver, "headcount", {"department_id": department_id})


def project_team(driver: Driver, project_id: str, *, role: str | None = None, current: bool | None = None,
                 location_id: str | None = None, reports_to: str | None = None) -> TemplateResult:
    """WORKED_ON members; `role` is a case-insensitive substring of the assignment role."""
    return _run(driver, "project_team", {"project_id": project_id, "role": role, "current": current,
                                         "location_id": location_id, "reports_to": reports_to})


def projects_of(driver: Driver, employee_id: str) -> TemplateResult:
    return _run(driver, "projects_of", {"employee_id": employee_id})


def project_leadership(driver: Driver, entity_id: str) -> TemplateResult:
    """Sponsor and lead of a project, or owner and engineering lead of a product."""
    return _run(driver, "project_leadership", {"entity_id": entity_id})


def project_departments(driver: Driver, project_id: str) -> TemplateResult:
    return _run(driver, "project_departments", {"project_id": project_id})


def previous_employer(driver: Driver, org_id: str) -> TemplateResult:
    """Employees who previously worked at the organisation (one row per stint)."""
    return _run(driver, "previous_employer", {"org_id": org_id})


def employers_of(driver: Driver, employee_id: str) -> TemplateResult:
    return _run(driver, "employers_of", {"employee_id": employee_id})


def skill_holders(driver: Driver, skill_id: str, *, expand_variants: bool = False) -> TemplateResult:
    """Holders of the literal skill; `expand_variants` adds the merged variants (Python (FastAPI)...)."""
    ids = sorted(skill_variants(skill_id)) if expand_variants else [skill_id]
    return _run(driver, "skill_holders", {"skill_ids": ids})


def policy_owner(driver: Driver, policy_id: str) -> TemplateResult:
    """Owning department and the people who prepared, reviewed and approved the policy."""
    return _run(driver, "policy_owner", {"policy_id": policy_id})


def policy_references(driver: Driver, policy_id: str, *, direction: Literal["in", "out"]) -> TemplateResult:
    """'out': policies this one references; 'in': policies that reference it."""
    if direction not in ("in", "out"):
        raise ValueError(f"direction must be 'in' or 'out', not {direction!r}")
    return _run(driver, "policy_references", {"policy_id": policy_id}, query=f"policy_references_{direction}")


def location_roster(driver: Driver, location_id: str) -> TemplateResult:
    return _run(driver, "location_roster", {"location_id": location_id})


def approvals_chain(driver: Driver, employee_id: str) -> TemplateResult:
    """Reporting chain up to the top (the employee with no manager), with bands, plus the
    department head and the head of the HR department."""
    return _run(driver, "approvals_chain", {"employee_id": employee_id, "hr_code": HR_DEPARTMENT_CODE})
