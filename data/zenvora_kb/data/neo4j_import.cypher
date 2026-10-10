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
