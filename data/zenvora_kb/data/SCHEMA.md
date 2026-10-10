# Data schema

CSV files in `data/csv/`. IDs are stable keys: employees `ZV-xxxx`, departments `Dxx`, locations `Lxx`, projects `PJxx`, products `PRxx`, policies `ZEN-...`.

## Graph model

```
(Company)-[:HAS_DEPARTMENT]->(Department)-[:LOCATED_AT]->(Location)
(Employee)-[:WORKS_IN]->(Department)
(Employee)-[:REPORTS_TO]->(Employee)
(Employee)-[:HEADS]->(Department)
(Employee)-[:IN_BAND]->(Band)
(Employee)-[:BASED_AT]->(Location)
(Employee)-[:PREVIOUSLY_AT {title,start,end}]->(Organization)
(Employee)-[:HAS_SKILL]->(Skill)
(Employee)-[:HOLDS]->(Certification)
(Employee)-[:WORKED_ON {role,from_date,is_current}]->(Project)
(Employee)-[:SPONSORS|LEADS]->(Project)
(Department)-[:CONTRIBUTES_TO]->(Project)
(Employee)-[:OWNS_PRODUCT|LEADS_ENGINEERING_OF]->(Product)
(Policy)-[:OWNED_BY]->(Department)
(Policy)-[:PREPARED_BY|REVIEWED_BY|APPROVED_BY]->(Employee)
(Policy)-[:APPLIES_TO]->(Company|Department)
(Policy)-[:REFERENCES]->(Policy)
(Policy)-[:DEFINES]->(Rule)
```

## CSV files

| File | Rows | Columns |
|---|---|---|
| `achievements.csv` | 120 | employee_id, achievement |
| `bands.csv` | 8 | band, level, meaning, notice_period_days |
| `board_members.csv` | 4 | name, role, background |
| `certifications.csv` | 34 | cert_id, name |
| `company.csv` | 1 | company_id, name, founded, hq, industry, tagline, mission, vision, employees, revenue_fy26_inr_cr, attrition_fy26_pct |
| `company_values.csv` | 5 | company_id, value, meaning |
| `customers.csv` | 8 | customer, products, account_owner_employee_id |
| `department_functions.csv` | 53 | department_id, function |
| `department_kpis.csv` | 36 | department_id, kpi |
| `department_tools.csv` | 60 | department_id, tool |
| `departments.csv` | 12 | department_id, code, name, head_employee_id, reports_to_employee_id, location_id, headcount, mission |
| `education.csv` | 56 | employee_id, degree, institution, year |
| `employee_certifications.csv` | 36 | employee_id, cert_id |
| `employee_skills.csv` | 210 | employee_id, skill_id |
| `employees.csv` | 42 | employee_id, slug, full_name, email, title, department_id, band, manager_employee_id, location_id, join_date, status, work_mode, work_mode_reason, notice_period_days, tenure_years, total_experience_years, profile_file, resume_file |
| `faqs.csv` | 31 | faq_id, question, answer, source_policy_id |
| `glossary.csv` | 18 | term, meaning |
| `investors.csv` | 2 | investor, type, round, date, amount |
| `locations.csv` | 4 | location_id, name, city, state, country, type, address, opened, notes |
| `onboarding_tasks.csv` | 14 | task_id, task, owner, due_day_from_joining, depends_on_task_id, system |
| `organizations.csv` | 18 | org_id, name |
| `policies.csv` | 19 | policy_id, title, scope, owner_department_id, version, revision, effective_date, next_review_date, prepared_by_employee_id, reviewed_by_employee_id, approved_by_employee_id, markdown_file, pdf_file, objective, applies_to |
| `policy_applies_to.csv` | 32 | policy_id, target_type, target_id |
| `policy_history.csv` | 63 | policy_id, revision, description, effective_date, reviewed_by_role, approved_by_role |
| `policy_references.csv` | 71 | from_policy_id, to_policy_id |
| `policy_rules.csv` | 62 | rule_id, policy_id, statement, applies_to, condition_or_exception, section |
| `policy_sections.csv` | 119 | policy_id, section_no, heading, text |
| `prior_experience.csv` | 61 | employee_id, org_id, title, start, end |
| `prior_experience_bullets.csv` | 71 | employee_id, org_id, bullet |
| `products.csv` | 3 | product_id, name, launched, owner_employee_id, lead_employee_id, summary, stack, stats |
| `project_assignments.csv` | 65 | project_id, employee_id, role, from_date, to_date, is_current |
| `project_departments.csv` | 33 | project_id, department_id |
| `project_goals.csv` | 27 | project_id, goal |
| `project_milestones.csv` | 34 | project_id, date, milestone |
| `project_outcomes.csv` | 27 | project_id, outcome |
| `projects.csv` | 9 | project_id, name, status, start_date, end_date, sponsor_employee_id, lead_employee_id, summary, tech |
| `reporting_lines.csv` | 41 | employee_id, manager_employee_id |
| `skills.csv` | 179 | skill_id, skill |
| `systems.csv` | 11 | system, purpose, address, owner |
| `timeline_events.csv` | 28 | event_id, date, type, title, details |

## Notes

- All derived fields (`work_mode`, `notice_period_days`, `tenure_years`) are computed as of 2026-10-10.
- `work_mode_reason` cites the policy that produced the value.
- `project_assignments.from_date` is the later of the project start and the employee's joining date.
- `policy_rules.csv` is hand-curated ground truth for rule nodes (about 60 rules). Use it to check LLM extraction.
