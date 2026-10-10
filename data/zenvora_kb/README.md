# Zenvora Technologies: GraphRAG Demo Dataset

A fictional company with departments, employees, resumes, policies, projects and history, built for a Graph RAG project where a new joiner asks a chatbot about the company.

> Everything here is invented. Any resemblance to real people or companies is coincidental.

## What is inside

| Folder | Contents | Count |
|---|---|---|
| `company/` | Overview, story, timeline, org structure, new-joiner handbook, all-hands notes, customer case study | 8 files |
| `departments/` | One profile per department with mission, functions, people, projects, policies | 12 files |
| `employees/profiles/` | HR-style profile for each employee (Markdown) | 42 files |
| `employees/resumes/` | One resume per employee (PDF) | 42 files |
| `employees/resumes_md/` | Same resumes as Markdown (for quick inspection) | 42 files |
| `policies/company_wide/`, `policies/departmental/` | Policies in Markdown | 19 files |
| `policies/pdf/` | The same policies as PDF | 19 files |
| `projects/` | 3 product pages and 9 project dossiers | 12 files |
| `data/csv/` | Structured tables for graph import (nodes and relationships) | see `data/SCHEMA.md` |
| `data/neo4j_import.cypher` | LOAD CSV script that builds the graph | 1 file |
| `eval/` | Question and answer pairs with ground truth for testing retrieval | 2 files |
| `generator/` | Python source that regenerates everything | |

## The company in one paragraph

Zenvora Technologies is a Hyderabad SaaS company founded in 2014 by Arvind Kulkarni and Meera Subramanian. It sells **Pulse** (omnichannel customer inbox), **Ledger** (invoicing and reconciliation) and **Care** (managed customer support run from a Visakhapatnam centre). It has 42 employees across 11 departments plus the Executive Office, in Hyderabad, Bengaluru, Visakhapatnam and Austin. Data is as of 10 Oct 2026.

## How the pieces connect (what makes this a good graph test)

- People report to people (a real hierarchy, 4 levels deep), belong to departments and locations, and have bands that drive rules (notice period, hotel limit, who must work from office every day).
- Employees are assigned to projects with roles. Projects have sponsors, leads and contributing departments.
- Policies cite each other explicitly (for example Hybrid Work refers to Leave, Discipline and Security policies) and cite approvers who are employees in the graph.
- Some answers need several hops, for example: *'Who is the head of the department of Sneha's manager?'* or *'Does Tarun need to come to the office on Mondays, and why?'*
- Time matters: one employee is serving notice, one is on maternity leave, one is in induction, one is on probation. As-of date is 2026-10-10.
- Resumes add prior employers, universities, certifications and skills, which create shared nodes across people.

## Suggested use

1. Chunk `policies/`, `departments/`, `projects/`, `company/` and `employees/` documents for the vector side.
2. Load `data/csv/` with `data/neo4j_import.cypher` for the graph side (or build the graph by LLM extraction from the documents and compare with the CSVs as ground truth).
3. Test the chatbot with `eval/questions.csv`.
