# -*- coding: utf-8 -*-
"""CSV tables, Neo4j import script, schema doc and evaluation questions."""
import csv
import json
import os
import re
from collections import defaultdict

from common import *
from build_docs import render_blocks, profile_stem, resume_stem, w

CSV_DIR = os.path.join(OUT, "data", "csv")
os.makedirs(CSV_DIR, exist_ok=True)
SCHEMA = {}  # filename -> header


def csvw(name, header, rows):
    os.makedirs(CSV_DIR, exist_ok=True)
    path = os.path.join(CSV_DIR, name)
    with open(path, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(header)
        wr.writerows(rows)
    SCHEMA[name] = (header, len(rows))


def join(items, sep="; "):
    return sep.join(items)


def build_csvs():
    c = COMPANY
    csvw("company.csv", ["company_id", "name", "founded", "hq", "industry", "tagline", "mission", "vision", "employees", "revenue_fy26_inr_cr", "attrition_fy26_pct"],
         [[c["id"], c["name"], c["founded"], c["hq"], c["industry"], c["tagline"], c["mission"], c["vision"], c["employees"], c["revenue_fy26_inr_cr"], c["attrition_fy26_pct"]]])
    csvw("company_values.csv", ["company_id", "value", "meaning"], [[c["id"], a, b] for a, b in c["values"]])
    csvw("locations.csv", ["location_id", "name", "city", "state", "country", "type", "address", "opened", "notes"],
         [[l["id"], l["name"], l["city"], l["state"], l["country"], l["type"], l["address"], l["opened"], l["notes"]] for l in LOCATIONS])
    csvw("departments.csv", ["department_id", "code", "name", "head_employee_id", "reports_to_employee_id", "location_id", "headcount", "mission"],
         [[x["id"], x["code"], x["name"], pid(x["head"]), pid(x["reports_to"]) if x["reports_to"] else "", x["location"], HEADCOUNT[x["code"]], x["mission"]] for x in DEPARTMENTS])
    csvw("department_functions.csv", ["department_id", "function"], [[x["id"], f] for x in DEPARTMENTS for f in x["functions"]])
    csvw("department_kpis.csv", ["department_id", "kpi"], [[x["id"], k] for x in DEPARTMENTS for k in x["kpis"]])
    csvw("department_tools.csv", ["department_id", "tool"], [[x["id"], t] for x in DEPARTMENTS for t in x["tools"]])
    csvw("bands.csv", ["band", "level", "meaning", "notice_period_days"], [[a, b, m, NOTICE_PERIOD_DAYS[a]] for a, b, m in BANDS])

    emps = sorted(PEOPLE, key=lambda p: p["id"])
    rows = []
    for p in emps:
        mode, reason = work_mode(p)
        rows.append([p["id"], p["slug"], p["name"], email(p), p["title"], dept_of(p)["id"], p["band"], pid(p["mgr"]) if p["mgr"] else "", p["loc"], p["joined"], p["status"], mode, reason,
                     notice_days(p), tenure_years(p), exp_years(p), f"employees/profiles/{profile_stem(p)}.md", f"employees/resumes/{resume_stem(p)}.pdf"])
    csvw("employees.csv", ["employee_id", "slug", "full_name", "email", "title", "department_id", "band", "manager_employee_id", "location_id", "join_date", "status", "work_mode", "work_mode_reason",
                           "notice_period_days", "tenure_years", "total_experience_years", "profile_file", "resume_file"], rows)
    csvw("reporting_lines.csv", ["employee_id", "manager_employee_id"], [[p["id"], pid(p["mgr"])] for p in emps if p["mgr"]])
    csvw("education.csv", ["employee_id", "degree", "institution", "year"], [[p["id"], a, b, y] for p in emps for a, b, y in p["edu"]])

    orgs = sorted({o[0] for p in PEOPLE for o in p["prior"]})
    org_id = {o: f"ORG{i:03d}" for i, o in enumerate(orgs, 1)}
    csvw("organizations.csv", ["org_id", "name"], [[org_id[o], o] for o in orgs])
    csvw("prior_experience.csv", ["employee_id", "org_id", "title", "start", "end"], [[p["id"], org_id[o[0]], o[1], o[2], o[3]] for p in emps for o in p["prior"]])
    csvw("prior_experience_bullets.csv", ["employee_id", "org_id", "bullet"], [[p["id"], org_id[o[0]], b] for p in emps for o in p["prior"] for b in o[4]])

    skills = sorted({s for p in PEOPLE for s in p["skills"]})
    sk_id = {s: f"SK{i:03d}" for i, s in enumerate(skills, 1)}
    csvw("skills.csv", ["skill_id", "skill"], [[sk_id[s], s] for s in skills])
    csvw("employee_skills.csv", ["employee_id", "skill_id"], [[p["id"], sk_id[s]] for p in emps for s in p["skills"]])
    certs = sorted({s for p in PEOPLE for s in p["certs"]})
    ce_id = {s: f"CE{i:03d}" for i, s in enumerate(certs, 1)}
    csvw("certifications.csv", ["cert_id", "name"], [[ce_id[s], s] for s in certs])
    csvw("employee_certifications.csv", ["employee_id", "cert_id"], [[p["id"], ce_id[s]] for p in emps for s in p["certs"]])
    csvw("achievements.csv", ["employee_id", "achievement"], [[p["id"], a] for p in emps for a in p["ach"]])

    csvw("products.csv", ["product_id", "name", "launched", "owner_employee_id", "lead_employee_id", "summary", "stack", "stats"],
         [[x["id"], x["name"], x["launched"], pid(x["owner"]), pid(x["eng_lead"]), x["summary"], join(x["stack"]), x["stats"]] for x in PRODUCTS])
    csvw("projects.csv", ["project_id", "name", "status", "start_date", "end_date", "sponsor_employee_id", "lead_employee_id", "summary", "tech"],
         [[x["id"], x["name"], x["status"], x["start"], x["end"] or "", pid(x["sponsor"]), pid(x["lead"]), x["summary"], join(x["tech"])] for x in PROJECTS])
    csvw("project_departments.csv", ["project_id", "department_id"], [[x["id"], DEPT_BY_CODE[cde]["id"]] for x in PROJECTS for cde in x["depts"]])
    csvw("project_assignments.csv", ["project_id", "employee_id", "role", "from_date", "to_date", "is_current"],
         [[a["project_id"], a["employee_id"], a["role"], a["from_date"], a["to_date"], str(a["current"]).lower()] for a in ASSIGN])
    csvw("project_milestones.csv", ["project_id", "date", "milestone"], [[x["id"], a, b] for x in PROJECTS for a, b in x["milestones"]])
    csvw("project_outcomes.csv", ["project_id", "outcome"], [[x["id"], o] for x in PROJECTS for o in x["outcomes"]])
    csvw("project_goals.csv", ["project_id", "goal"], [[x["id"], g] for x in PROJECTS for g in x["goals"]])

    csvw("policies.csv", ["policy_id", "title", "scope", "owner_department_id", "version", "revision", "effective_date", "next_review_date", "prepared_by_employee_id", "reviewed_by_employee_id", "approved_by_employee_id",
                          "markdown_file", "pdf_file", "objective", "applies_to"],
         [[x["id"], x["title"], x["scope"], x["owner_dept_id"], x["version"], x["revision"], x["effective"], x["next_review"], pid(x["prepared_by"]), pid(x["reviewed_by"]), pid(x["approved_by"]),
           f"policies/{'company_wide' if x['scope'] == 'Company-wide' else 'departmental'}/{x['file_stem']}.md", f"policies/pdf/{x['file_stem']}.pdf", x["objective"], x["applies_to"]] for x in POLICIES])
    csvw("policy_history.csv", ["policy_id", "revision", "description", "effective_date", "reviewed_by_role", "approved_by_role"], [[x["id"], h[0], h[1], h[2], h[3], h[4]] for x in POLICIES for h in x["history"]])
    sec_rows = []
    for x in POLICIES:
        for i, (hd, bl) in enumerate(x["sections"], 3):
            sec_rows.append([x["id"], i, hd, render_blocks(bl).replace("\n", " ")])
    csvw("policy_sections.csv", ["policy_id", "section_no", "heading", "text"], sec_rows)
    ap = []
    for x in POLICIES:
        if x["scope"] == "Company-wide":
            ap.append([x["id"], "Company", c["id"]])
        else:
            tg = POLICY_APPLIES[x["id"]]
            if "ALL" in tg:
                ap.append([x["id"], "Company", c["id"]])
            else:
                for cde in tg:
                    ap.append([x["id"], "Department", DEPT_BY_CODE[cde]["id"]])
    csvw("policy_applies_to.csv", ["policy_id", "target_type", "target_id"], ap)
    csvw("policy_references.csv", ["from_policy_id", "to_policy_id"], [[x["id"], r] for x in POLICIES for r in x["refs"]])
    csvw("policy_rules.csv", ["rule_id", "policy_id", "statement", "applies_to", "condition_or_exception", "section"], [[f"R{i:03d}", *r] for i, r in enumerate(RULES, 1)])

    csvw("glossary.csv", ["term", "meaning"], [list(g) for g in GLOSSARY])
    csvw("systems.csv", ["system", "purpose", "address", "owner"], [list(s) for s in SYSTEMS])
    csvw("timeline_events.csv", ["event_id", "date", "type", "title", "details"], [[f"EV{i:03d}", a, b, t, e] for i, (a, b, t, e) in enumerate(TIMELINE, 1)])
    csvw("board_members.csv", ["name", "role", "background"], [list(b) for b in BOARD])
    csvw("investors.csv", ["investor", "type", "round", "date", "amount"], [list(i) for i in INVESTORS])
    csvw("customers.csv", ["customer", "products", "account_owner_employee_id"], [[a, b, pid(s)] for a, b, s in CUSTOMERS])
    csvw("faqs.csv", ["faq_id", "question", "answer", "source_policy_id"], [[f"FAQ{i:03d}", q, a, s] for i, (q, a, s) in enumerate(FAQS, 1)])
    tid = {t[0]: f"OT{i:02d}" for i, t in enumerate(ONBOARDING, 1)}
    csvw("onboarding_tasks.csv", ["task_id", "task", "owner", "due_day_from_joining", "depends_on_task_id", "system"],
         [[tid[t[0]], t[0], t[1], t[2], tid[ONBOARDING[t[3]][0]] if t[3] is not None else "", t[4]] for t in ONBOARDING])


CYPHER = """\
// Zenvora Technologies knowledge graph: Neo4j import
// 1. Copy everything in data/csv/ to Neo4j's import directory.
// 2. Run this script in Neo4j Browser or cypher-shell.
// Node labels: Company, Location, Department, Band, Employee, Organization, Skill, Certification, Product, Project, Policy, Rule, Glossary, System, Event
// ---------------------------------------------------------------- constraints
CREATE CONSTRAINT company_id IF NOT EXISTS FOR (n:Company) REQUIRE n.company_id IS UNIQUE;
CREATE CONSTRAINT location_id IF NOT EXISTS FOR (n:Location) REQUIRE n.location_id IS UNIQUE;
CREATE CONSTRAINT dept_id IF NOT EXISTS FOR (n:Department) REQUIRE n.department_id IS UNIQUE;
CREATE CONSTRAINT band_id IF NOT EXISTS FOR (n:Band) REQUIRE n.band IS UNIQUE;
CREATE CONSTRAINT emp_id IF NOT EXISTS FOR (n:Employee) REQUIRE n.employee_id IS UNIQUE;
CREATE CONSTRAINT org_id IF NOT EXISTS FOR (n:Organization) REQUIRE n.org_id IS UNIQUE;
CREATE CONSTRAINT skill_id IF NOT EXISTS FOR (n:Skill) REQUIRE n.skill_id IS UNIQUE;
CREATE CONSTRAINT cert_id IF NOT EXISTS FOR (n:Certification) REQUIRE n.cert_id IS UNIQUE;
CREATE CONSTRAINT product_id IF NOT EXISTS FOR (n:Product) REQUIRE n.product_id IS UNIQUE;
CREATE CONSTRAINT project_id IF NOT EXISTS FOR (n:Project) REQUIRE n.project_id IS UNIQUE;
CREATE CONSTRAINT policy_id IF NOT EXISTS FOR (n:Policy) REQUIRE n.policy_id IS UNIQUE;
CREATE CONSTRAINT rule_id IF NOT EXISTS FOR (n:Rule) REQUIRE n.rule_id IS UNIQUE;

// ---------------------------------------------------------------- core nodes
LOAD CSV WITH HEADERS FROM 'file:///company.csv' AS r
MERGE (c:Company {company_id: r.company_id}) SET c.name = r.name, c.founded = date(r.founded), c.hq = r.hq, c.mission = r.mission, c.vision = r.vision;

LOAD CSV WITH HEADERS FROM 'file:///locations.csv' AS r
MERGE (l:Location {location_id: r.location_id}) SET l.name = r.name, l.city = r.city, l.country = r.country, l.type = r.type, l.opened = date(r.opened)
WITH l MATCH (c:Company) MERGE (c)-[:HAS_LOCATION]->(l);

LOAD CSV WITH HEADERS FROM 'file:///bands.csv' AS r
MERGE (b:Band {band: r.band}) SET b.level = r.level, b.notice_period_days = toInteger(r.notice_period_days);

LOAD CSV WITH HEADERS FROM 'file:///departments.csv' AS r
MERGE (d:Department {department_id: r.department_id}) SET d.name = r.name, d.code = r.code, d.mission = r.mission, d.headcount = toInteger(r.headcount)
WITH d, r MATCH (l:Location {location_id: r.location_id}) MERGE (d)-[:LOCATED_AT]->(l)
WITH d MATCH (c:Company) MERGE (c)-[:HAS_DEPARTMENT]->(d);

LOAD CSV WITH HEADERS FROM 'file:///employees.csv' AS r
MERGE (e:Employee {employee_id: r.employee_id})
SET e.name = r.full_name, e.email = r.email, e.title = r.title, e.join_date = date(r.join_date), e.status = r.status, e.work_mode = r.work_mode,
    e.work_mode_reason = r.work_mode_reason, e.notice_period_days = toInteger(r.notice_period_days), e.profile_file = r.profile_file, e.resume_file = r.resume_file
WITH e, r
MATCH (d:Department {department_id: r.department_id}) MERGE (e)-[:WORKS_IN]->(d)
WITH e, r MATCH (b:Band {band: r.band}) MERGE (e)-[:IN_BAND]->(b)
WITH e, r MATCH (l:Location {location_id: r.location_id}) MERGE (e)-[:BASED_AT]->(l);

LOAD CSV WITH HEADERS FROM 'file:///reporting_lines.csv' AS r
MATCH (e:Employee {employee_id: r.employee_id}), (m:Employee {employee_id: r.manager_employee_id}) MERGE (e)-[:REPORTS_TO]->(m);

LOAD CSV WITH HEADERS FROM 'file:///departments.csv' AS r
MATCH (d:Department {department_id: r.department_id}), (h:Employee {employee_id: r.head_employee_id}) MERGE (h)-[:HEADS]->(d);

// ---------------------------------------------------------------- background: employers, skills, certificates
LOAD CSV WITH HEADERS FROM 'file:///organizations.csv' AS r MERGE (o:Organization {org_id: r.org_id}) SET o.name = r.name;
LOAD CSV WITH HEADERS FROM 'file:///prior_experience.csv' AS r
MATCH (e:Employee {employee_id: r.employee_id}), (o:Organization {org_id: r.org_id})
MERGE (e)-[x:PREVIOUSLY_AT {title: r.title, start: r.start}]->(o) SET x.end = r.end;
LOAD CSV WITH HEADERS FROM 'file:///skills.csv' AS r MERGE (s:Skill {skill_id: r.skill_id}) SET s.name = r.skill;
LOAD CSV WITH HEADERS FROM 'file:///employee_skills.csv' AS r
MATCH (e:Employee {employee_id: r.employee_id}), (s:Skill {skill_id: r.skill_id}) MERGE (e)-[:HAS_SKILL]->(s);
LOAD CSV WITH HEADERS FROM 'file:///certifications.csv' AS r MERGE (c:Certification {cert_id: r.cert_id}) SET c.name = r.name;
LOAD CSV WITH HEADERS FROM 'file:///employee_certifications.csv' AS r
MATCH (e:Employee {employee_id: r.employee_id}), (c:Certification {cert_id: r.cert_id}) MERGE (e)-[:HOLDS]->(c);

// ---------------------------------------------------------------- products and projects
LOAD CSV WITH HEADERS FROM 'file:///products.csv' AS r
MERGE (p:Product {product_id: r.product_id}) SET p.name = r.name, p.launched = date(r.launched), p.summary = r.summary
WITH p, r MATCH (o:Employee {employee_id: r.owner_employee_id}) MERGE (o)-[:OWNS_PRODUCT]->(p)
WITH p, r MATCH (l:Employee {employee_id: r.lead_employee_id}) MERGE (l)-[:LEADS_ENGINEERING_OF]->(p);

LOAD CSV WITH HEADERS FROM 'file:///projects.csv' AS r
MERGE (p:Project {project_id: r.project_id}) SET p.name = r.name, p.status = r.status, p.start_date = date(r.start_date), p.summary = r.summary
FOREACH (_ IN CASE WHEN r.end_date <> '' THEN [1] ELSE [] END | SET p.end_date = date(r.end_date))
WITH p, r MATCH (s:Employee {employee_id: r.sponsor_employee_id}) MERGE (s)-[:SPONSORS]->(p)
WITH p, r MATCH (l:Employee {employee_id: r.lead_employee_id}) MERGE (l)-[:LEADS]->(p);

LOAD CSV WITH HEADERS FROM 'file:///project_departments.csv' AS r
MATCH (p:Project {project_id: r.project_id}), (d:Department {department_id: r.department_id}) MERGE (d)-[:CONTRIBUTES_TO]->(p);

LOAD CSV WITH HEADERS FROM 'file:///project_assignments.csv' AS r
MATCH (e:Employee {employee_id: r.employee_id}), (p:Project {project_id: r.project_id})
MERGE (e)-[w:WORKED_ON]->(p) SET w.role = r.role, w.from_date = date(r.from_date), w.is_current = (r.is_current = 'true');

// ---------------------------------------------------------------- policies and rules
LOAD CSV WITH HEADERS FROM 'file:///policies.csv' AS r
MERGE (p:Policy {policy_id: r.policy_id})
SET p.title = r.title, p.scope = r.scope, p.version = r.version, p.revision = r.revision, p.effective_date = date(r.effective_date), p.next_review_date = date(r.next_review_date),
    p.objective = r.objective, p.markdown_file = r.markdown_file, p.pdf_file = r.pdf_file
WITH p, r MATCH (d:Department {department_id: r.owner_department_id}) MERGE (p)-[:OWNED_BY]->(d)
WITH p, r MATCH (a:Employee {employee_id: r.prepared_by_employee_id}) MERGE (p)-[:PREPARED_BY]->(a)
WITH p, r MATCH (b:Employee {employee_id: r.reviewed_by_employee_id}) MERGE (p)-[:REVIEWED_BY]->(b)
WITH p, r MATCH (c:Employee {employee_id: r.approved_by_employee_id}) MERGE (p)-[:APPROVED_BY]->(c);

LOAD CSV WITH HEADERS FROM 'file:///policy_applies_to.csv' AS r
MATCH (p:Policy {policy_id: r.policy_id})
OPTIONAL MATCH (c:Company {company_id: r.target_id}) OPTIONAL MATCH (d:Department {department_id: r.target_id})
FOREACH (_ IN CASE WHEN c IS NOT NULL THEN [1] ELSE [] END | MERGE (p)-[:APPLIES_TO]->(c))
FOREACH (_ IN CASE WHEN d IS NOT NULL THEN [1] ELSE [] END | MERGE (p)-[:APPLIES_TO]->(d));

LOAD CSV WITH HEADERS FROM 'file:///policy_references.csv' AS r
MATCH (a:Policy {policy_id: r.from_policy_id}), (b:Policy {policy_id: r.to_policy_id}) MERGE (a)-[:REFERENCES]->(b);

LOAD CSV WITH HEADERS FROM 'file:///policy_rules.csv' AS r
MERGE (x:Rule {rule_id: r.rule_id}) SET x.statement = r.statement, x.applies_to = r.applies_to, x.condition = r.condition_or_exception, x.section = r.section
WITH x, r MATCH (p:Policy {policy_id: r.policy_id}) MERGE (p)-[:DEFINES]->(x);

// ---------------------------------------------------------------- example queries
// Who is the skip-level manager of Sneha Hegde?
//   MATCH (e:Employee {name:'Sneha Hegde'})-[:REPORTS_TO*2]->(m) RETURN m.name;
// Who must work from office every day today?
//   MATCH (e:Employee) WHERE e.work_mode STARTS WITH 'Full WFO' RETURN e.name, e.work_mode_reason;
// Which policies reference the Progressive Discipline Policy?
//   MATCH (p:Policy)-[:REFERENCES]->(:Policy {policy_id:'ZEN-POL-004'}) RETURN p.policy_id, p.title;
"""


def build_cypher_and_schema():
    w("data/neo4j_import.cypher", CYPHER)
    L = ["# Data schema", "", "CSV files in `data/csv/`. IDs are stable keys: employees `ZV-xxxx`, departments `Dxx`, locations `Lxx`, projects `PJxx`, products `PRxx`, policies `ZEN-...`.", "",
         "## Graph model", "",
         "```", "(Company)-[:HAS_DEPARTMENT]->(Department)-[:LOCATED_AT]->(Location)", "(Employee)-[:WORKS_IN]->(Department)", "(Employee)-[:REPORTS_TO]->(Employee)", "(Employee)-[:HEADS]->(Department)",
         "(Employee)-[:IN_BAND]->(Band)", "(Employee)-[:BASED_AT]->(Location)", "(Employee)-[:PREVIOUSLY_AT {title,start,end}]->(Organization)", "(Employee)-[:HAS_SKILL]->(Skill)", "(Employee)-[:HOLDS]->(Certification)",
         "(Employee)-[:WORKED_ON {role,from_date,is_current}]->(Project)", "(Employee)-[:SPONSORS|LEADS]->(Project)", "(Department)-[:CONTRIBUTES_TO]->(Project)",
         "(Employee)-[:OWNS_PRODUCT|LEADS_ENGINEERING_OF]->(Product)", "(Policy)-[:OWNED_BY]->(Department)", "(Policy)-[:PREPARED_BY|REVIEWED_BY|APPROVED_BY]->(Employee)",
         "(Policy)-[:APPLIES_TO]->(Company|Department)", "(Policy)-[:REFERENCES]->(Policy)", "(Policy)-[:DEFINES]->(Rule)", "```", "", "## CSV files", ""]
    L.append("| File | Rows | Columns |")
    L.append("|---|---|---|")
    for name in sorted(SCHEMA):
        h, n = SCHEMA[name]
        L.append(f"| `{name}` | {n} | {', '.join(h)} |")
    L += ["", "## Notes", "", f"- All derived fields (`work_mode`, `notice_period_days`, `tenure_years`) are computed as of {AS_OF}.",
          "- `work_mode_reason` cites the policy that produced the value.", "- `project_assignments.from_date` is the later of the project start and the employee's joining date.",
          "- `policy_rules.csv` is hand-curated ground truth for rule nodes (about 60 rules). Use it to check LLM extraction."]
    w("data/SCHEMA.md", "\n".join(L) + "\n")


# --------------------------------------------------------------------------- evaluation questions
def names(slugs):
    return "; ".join(pname(s) for s in slugs)


def build_eval():
    Q = []

    def add(cat, hops, q, a, src):
        Q.append(dict(category=cat, hops=hops, question=q, expected_answer=a, sources=src))

    order = sorted(PEOPLE, key=lambda p: p["id"])
    # 1 manager
    for i, p in enumerate([x for x in order if x["mgr"]]):
        if i % 2 == 0:
            add("org_structure", 1, f"Who does {p['name']} report to?", f"{pname(p['mgr'])} ({person(p['mgr'])['title']})", f"{p['id']}")
    # 2 title and band
    for i, p in enumerate(order):
        if i % 3 == 0:
            add("employee_lookup", 1, f"What is {p['name']}'s job title and band?", f"{p['title']}, band {p['band']}", p["id"])
    # 3 dept head / headcount
    for dep in DEPARTMENTS:
        add("org_structure", 1, f"Who heads the {dep['name']} department?", f"{pname(dep['head'])} ({person(dep['head'])['title']})", dep["id"])
        add("org_structure", 1, f"How many employees are in {dep['name']}?", str(HEADCOUNT[dep["code"]]), dep["id"])
    # 4 direct reports
    for slug, rep in DIRECT_REPORTS.items():
        if len(rep) >= 2:
            add("org_structure", 1, f"Who reports directly to {pname(slug)}?", names(rep), pid(slug))
    # 5 skip level
    k = 0
    for p in order:
        ch = reports_chain(p["slug"])
        if len(ch) >= 2:
            if k % 3 == 0:
                add("org_structure", 2, f"Who is {p['name']}'s manager's manager?", f"{pname(ch[1])} ({person(ch[1])['title']})", f"{p['id']}, {pid(ch[0])}")
            k += 1
    # 6 head of dept of manager
    k = 0
    for p in order:
        if p["mgr"]:
            m = person(p["mgr"])
            if k % 4 == 0:
                dh = DEPT_BY_CODE[m["dept"]]["head"]
                add("org_structure", 3, f"Who heads the department that {p['name']}'s manager belongs to?", f"{pname(dh)} ({DEPT_BY_CODE[m['dept']]['name']})", f"{p['id']}, {m['id']}, {DEPT_BY_CODE[m['dept']]['id']}")
            k += 1
    # 7 projects of person
    for p in order:
        pa = PROJECTS_OF.get(p["slug"], [])
        if len(pa) >= 3:
            add("project", 2, f"Which projects has {p['name']} worked on?", "; ".join(PROJ_BY_ID[a["project_id"]]["name"] for a in pa), p["id"])
    # 8 sponsor / lead
    for pj in PROJECTS:
        add("project", 1, f"Who sponsored {pj['name']} and who led it?", f"Sponsor: {pname(pj['sponsor'])}. Lead: {pname(pj['lead'])}.", pj["id"])
        add("project", 2, f"Which departments contributed to {pj['name']}?", "; ".join(DEPT_BY_CODE[c]["name"] for c in pj["depts"]), pj["id"])
    # 9 project team by city
    for pj in PROJECTS:
        by_city = defaultdict(list)
        for s, r in pj["team"]:
            by_city[LOC_BY_ID[person(s)["loc"]]["city"]].append(s)
        if len(by_city) >= 2:
            for city, sl in by_city.items():
                if city in ("Bengaluru", "Visakhapatnam", "Austin"):
                    add("project", 3, f"Who on {pj['name']} works from {city}?", names(sl), f"{pj['id']}")
    # 10 managers' team on project
    add("project", 3, "Which engineers on Project Atlas report to Divya Krishnamurthy?", names([s for s, r in PROJ_BY_ID["PJ01"]["team"] if person(s)["mgr"] == "divya"]), "PJ01, " + pid("divya"))
    add("project", 3, "Who on Project Lighthouse reports to Farhan Siddiqui?", names([s for s, r in PROJ_BY_ID["PJ05"]["team"] if person(s)["mgr"] == "farhan"]), "PJ05, " + pid("farhan"))
    add("project", 3, "Which members of Project Horizon work in the Customer Support department?", names([s for s, r in PROJ_BY_ID["PJ06"]["team"] if person(s)["dept"] == "CSC"]), "PJ06")
    # 11 employers, certs, skills, schools
    by_org = defaultdict(list)
    for p in PEOPLE:
        for o in p["prior"]:
            by_org[o[0]].append(p["slug"])
    for org, sl in by_org.items():
        sl = list(dict.fromkeys(sl))
        if len(sl) >= 3:
            add("skills_experience", 2, f"Which Zenvora employees previously worked at {org}?", names(sorted(sl, key=lambda s: pid(s))), "resumes")
    by_cert = defaultdict(list)
    by_skill = defaultdict(list)
    by_school = defaultdict(list)
    for p in PEOPLE:
        for c in p["certs"]:
            by_cert[c].append(p["slug"])
        for s in p["skills"]:
            by_skill[s].append(p["slug"])
        for deg, inst, yr in p["edu"]:
            by_school[inst].append(p["slug"])
    for c, sl in by_cert.items():
        if len(sl) >= 2:
            add("skills_experience", 2, f"Who holds the certification '{c}'?", names(sorted(sl, key=lambda s: pid(s))), "resumes")
    for s, sl in by_skill.items():
        if 2 <= len(sl) <= 6 and not any(o != s and re.search(r'\b' + re.escape(s) + r'\b', o) for o in by_skill):
            add("skills_experience", 2, f"Which employees list {s} as a skill?", names(sorted(sl, key=lambda x: pid(x))), "resumes")
    for s, sl in by_school.items():
        if len(sl) >= 3:
            add("skills_experience", 2, f"Which employees studied at {s}?", names(sorted(sl, key=lambda x: pid(x))), "resumes")
    early = [p["slug"] for p in order if p["joined"] < "2016-01-01"]
    add("employee_lookup", 2, "Who joined Zenvora before 2016?", names(early), "employees.csv")
    for city, lid in (("Bengaluru", "L02"), ("Visakhapatnam", "L03"), ("Austin", "L04")):
        add("employee_lookup", 2, f"Which employees are based in {city}?", names([p["slug"] for p in order if p["loc"] == lid]), lid)
    # 12 personalised
    for slug in ["arjun", "tarun", "bindu", "ashwin", "pooja", "sneha", "kiran", "gaurav"]:
        p = person(slug)
        mode, reason = work_mode(p)
        add("personalised", 2, f"How many days a week does {p['name']} need to be in the office right now, and why?", f"{mode}. {reason}", f"{p['id']}, ZEN-POL-002")
    for slug in ["sneha", "karthik", "gaurav", "arjun"]:
        p = person(slug)
        add("personalised", 2, f"What is {p['name']}'s notice period?", f"{notice_days(p)} days" + (" (still on probation)" if on_probation(p) else f" (band {p['band']})"), f"{p['id']}, ZEN-POL-003")
    for slug in ["karthik", "sneha", "imran", "harsha", "naveen", "zaid"]:
        p = person(slug)
        j = d(p["joined"])
        elig = TODAY >= j.replace(year=j.year + 5)
        add("personalised", 2, f"Is {p['name']} eligible for a sabbatical as of {fdate(AS_OF)}?", ("Yes" if elig else "No") + f". Joined {fdate(p['joined'])} ({tenure_years(p)} years of service; 5 years required).", f"{p['id']}, ZEN-POL-003")
    for slug, city, tier in [("arjun", "Mumbai", 1), ("karthik", "Visakhapatnam", 2), ("gaurav", "Pune", 1), ("lavanya", "Chennai", 1), ("sai_teja", "Visakhapatnam", 2), ("ramesh", "Bengaluru", 1)]:
        p = person(slug)
        add("personalised", 3, f"What is the maximum hotel cost per night for {p['name']} on a trip to {city}?", f"{inr(hotel_limit(p['band'], tier))} (band {p['band']}, Tier-{tier} city)", f"{p['id']}, ZEN-DPL-FIN-01")
    for slug in ["sneha", "mohan", "priyanka", "keerthi"]:
        p = person(slug)
        dh = DEPT_BY_CODE[p["dept"]]["head"]
        add("personalised", 3, f"Who approves a business trip costing INR 60,000 for {p['name']}?", f"The department head, {pname(dh)}, because the amount is between INR 25,001 and INR 1,00,000.", f"{p['id']}, ZEN-DPL-FIN-01")
    for slug in ["divya", "naveen", "isha"]:
        p = person(slug)
        dh = DEPT_BY_CODE[p["dept"]]["head"]
        if int(p["band"][1:]) >= 5:
            ans = f"{pname(dh)} (department head) recommends; Head of People & Culture ({pname('lakshmi')}) approves; the CEO ({pname('arvind')}) gives final approval because the band is Z5 or above."
        else:
            ans = f"{pname(dh)} (department head) recommends; Head of People & Culture ({pname('lakshmi')}) approves. CEO final approval is only needed for band Z5 and above."
        add("personalised", 3, f"Who must approve a recommendation to terminate {p['name']}'s employment?", ans, f"{p['id']}, ZEN-POL-004")
    add("personalised", 1, "Who is on maternity leave and until when?", "Pooja Agarwal, until 28 February 2027 (started 1 September 2026).", pid("pooja"))
    add("personalised", 1, "Who is serving a notice period and when is the last working day?", "Tarun Mehta; last working day 14 November 2026 (resigned 15 September 2026, 60-day notice).", pid("tarun"))
    add("personalised", 2, "When does Arjun Menon's induction period end?", f"{fdate(induction_end(person('arjun')).isoformat())} (90 calendar days after joining on 20 July 2026).", f"{pid('arjun')}, ZEN-POL-002")
    add("personalised", 1, "What are the dates for H1 FY2026-27 self-reviews and manager reviews?", "Self-reviews 5 to 16 October 2026; manager reviews 19 to 30 October 2026.", "ZEN-DPL-HR-01")
    # 13 policy FAQs
    for q, a, src in FAQS:
        add("policy", 1, q, a, src)
    # 14 policy references
    refd = defaultdict(list)
    for pol in POLICIES:
        for r in pol["refs"]:
            refd[r].append(pol["id"])
    for tgt in ["ZEN-POL-004", "ZEN-POL-006", "ZEN-DPL-DCL-01", "ZEN-DPL-DAI-01"]:
        add("cross_document", 2, f"Which policies refer to the {POL_BY_ID[tgt]['title']} ({tgt})?", "; ".join(f"{i} ({POL_BY_ID[i]['title']})" for i in sorted(refd[tgt])), ", ".join(sorted(refd[tgt])))
    # 15 cross document
    add("cross_document", 3, "Who is the Presiding Officer of the POSH Internal Committee and who does she report to?", f"Tanvi Deshpande (HR Business Partner); she reports to {pname('lakshmi')}, Head of People & Culture.", "ZEN-POL-008, " + pid("tanvi"))
    add("cross_document", 3, "Who prepared and who approved the Hybrid Work Policy, and what are their titles?", f"Prepared by {pname('tanvi')} (HR Business Partner); reviewed by {pname('lakshmi')} (Head of People & Culture); approved by {pname('arvind')} (Founder & CEO).", "ZEN-POL-002")
    add("cross_document", 3, "Which department owns the Cloud Operations, On-call and Incident Management Policy and who wrote it?", f"DevOps & Cloud Infrastructure; prepared by {pname('prakash')}.", "ZEN-DPL-DCL-01")
    add("cross_document", 3, "A Z3 engineer on notice period asks to work from home on Mondays. What is the answer?", "No. Employees serving notice work from office on all working days (ZEN-POL-002).", "ZEN-POL-002, ZEN-POL-003")
    add("cross_document", 3, "A Customer Support specialist wants to work from home on Fridays. Is that allowed?", "No. Support staff on the Care Centre shift roster work on site, except in a declared contingency (ZEN-DPL-CSC-01 and ZEN-POL-002).", "ZEN-DPL-CSC-01, ZEN-POL-002")
    add("cross_document", 3, "If a security incident is a data breach, how quickly must it be reported internally and to CERT-In?", "Internally within 1 hour of discovery; the CISO reports to CERT-In within 6 hours where legally required.", "ZEN-POL-006")
    add("cross_document", 3, "Who certified Zenvora under ISO 27001, when, and who led that project?", f"The ISO/IEC 27001:2022 certificate was issued on 20 February 2025 through Project Sentinel, led by {pname('manoj')} (CISO).", "PJ04, ZEN-POL-006")
    add("cross_document", 3, "Which project reduced cloud costs and by how much, and who sponsored it?", f"Project Ember cut annual AWS spend by 31 percent (about INR 92 lakh a year); sponsored by {pname('ramesh')} (CFO), led by {pname('prakash')}.", "PJ07")
    add("cross_document", 3, "Who runs the Care Centre pilot of Sage and what was the result?", f"{pname('lavanya')} led the pilot; it deflected 38 percent of Tier-1 tickets (Project Sage).", "PJ08")

    for i, q in enumerate(Q, 1):
        q["id"] = f"Q{i:03d}"
    cols = ["id", "category", "hops", "question", "expected_answer", "sources"]
    os.makedirs(os.path.join(OUT, "eval"), exist_ok=True)
    with open(os.path.join(OUT, "eval", "questions.csv"), "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=cols)
        wr.writeheader()
        wr.writerows(Q)
    with open(os.path.join(OUT, "eval", "questions.jsonl"), "w", encoding="utf-8") as f:
        for q in Q:
            f.write(json.dumps({k: q[k] for k in cols}, ensure_ascii=False) + "\n")
    return Q


def build_all():
    build_csvs()
    build_cypher_and_schema()
    q = build_eval()
    return len(q)


if __name__ == "__main__":
    print("questions:", build_all())
