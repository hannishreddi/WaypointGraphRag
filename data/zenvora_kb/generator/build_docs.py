# -*- coding: utf-8 -*-
"""Render markdown documents and PDFs."""
import os
import subprocess
import html as htmllib
import markdown

from common import *

DISCLAIMER = "Zenvora Technologies Pvt. Ltd. reserves the right to change or revise this policy at any time, in any lawful manner, with notice to employees through ZenPeople and Slack #announcements."
FICTION_NOTE = "*Fictional document created for a GraphRAG demonstration project. All people, companies and figures are invented.*"


def w(path, text):
    full = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(text)
    return full


def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c).replace("|", "/") for c in r) + " |")
    return "\n".join(out)


def render_blocks(blocks):
    out = []
    for b in blocks:
        if isinstance(b, str):
            out.append(b)
        elif b[0] == "ul":
            out.append("\n".join(f"- {x}" for x in b[1]))
        elif b[0] == "ol":
            out.append("\n".join(f"{i}. {x}" for i, x in enumerate(b[1], 1)))
        elif b[0] == "table":
            out.append(md_table(b[1], b[2]))
    return "\n\n".join(out)


def person_label(slug):
    p = BY_SLUG[slug]
    return f"{p['name']} ({p['title']})"


# --------------------------------------------------------------------------- PDF
CSS = """
body{font-family:'DejaVu Sans',Arial,sans-serif;font-size:10.5pt;line-height:1.45;color:#1b1f23;margin:0}
h1{font-size:19pt;margin:0 0 6px 0;color:#14304f}
h2{font-size:12.5pt;margin:18px 0 6px 0;color:#14304f;border-bottom:1px solid #c9d3de;padding-bottom:3px}
h3{font-size:11pt;margin:12px 0 4px 0}
table{border-collapse:collapse;width:100%;margin:8px 0;font-size:9.5pt}
th,td{border:1px solid #c9d3de;padding:4px 7px;text-align:left;vertical-align:top}
th{background:#eef3f8}
ul,ol{margin:4px 0 8px 18px;padding-left:10px}
li{margin-bottom:3px}
.meta{font-size:9.5pt;color:#44505c}
.small{font-size:9pt;color:#5a6672}
"""


def html_to_pdf(html_text, pdf_path):
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
    tmp = pdf_path + ".html"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html_text)
    subprocess.run(["wkhtmltopdf", "-q", "--encoding", "utf-8", "--page-size", "A4", "--margin-top", "16mm", "--margin-bottom", "16mm",
                    "--margin-left", "16mm", "--margin-right", "16mm", tmp, pdf_path], check=True, stderr=subprocess.DEVNULL)
    os.remove(tmp)


def md_to_pdf(md_text, pdf_path, title):
    body = markdown.markdown(md_text, extensions=["tables"])
    html_text = f"<html><head><meta charset='utf-8'><title>{htmllib.escape(title)}</title><style>{CSS}</style></head><body>{body}</body></html>"
    html_to_pdf(html_text, pdf_path)


# --------------------------------------------------------------------------- POLICIES
def policy_md(pol):
    dept = DEPT_BY_CODE[pol["dept"]]
    lines = [f"# {pol['title']}", ""]
    lines.append(f"**Reference No:** {pol['id']} | **Version:** {pol['version']} | **Revision:** {pol['revision']}  ")
    lines.append(f"**Policy type:** {pol['scope']}  ")
    lines.append(f"**Effective Date:** {fdate(pol['effective'])} | **Next Review:** {fdate(pol['next_review'])}  ")
    lines.append(f"**Owning Department:** {dept['name']}  ")
    lines.append(f"**Prepared By:** {person_label(pol['prepared_by'])}  ")
    lines.append(f"**Reviewed By:** {person_label(pol['reviewed_by'])}  ")
    lines.append(f"**Approved By:** {person_label(pol['approved_by'])}  ")
    lines.append(f"**System of record:** Confluence, Policies space, and ZenPeople (acknowledgement)  ")
    if pol["refs"]:
        lines.append("**Related policies:** " + "; ".join(f"{r} ({POL_BY_ID[r]['title']})" for r in pol["refs"]))
    lines += ["", "## Policy History", ""]
    lines.append(md_table(["Revision", "Amendment description", "Effective date", "Reviewed by", "Approved by"],
                          [[h[0], h[1], fdate(h[2]), h[3], h[4]] for h in pol["history"]]))
    secs = pol["sections"]
    lines += ["", "## Table of Contents", ""]
    toc = ["Objective", "Applies to"] + [s[0] for s in secs] + ["Disclaimer"]
    lines.append(md_table(["S.#", "Topic"], [[i, t] for i, t in enumerate(toc, 1)]))
    lines += ["", "## 1. Objective", "", pol["objective"], "", "## 2. Applies to", "", pol["applies_to"]]
    for i, (heading, blocks) in enumerate(secs, 3):
        lines += ["", f"## {i}. {heading}", "", render_blocks(blocks)]
    lines += ["", f"## {len(secs) + 3}. Disclaimer", "", DISCLAIMER, "", FICTION_NOTE]
    return "\n".join(lines) + "\n"


def build_policies():
    for pol in POLICIES:
        sub = "company_wide" if pol["scope"] == "Company-wide" else "departmental"
        text = policy_md(pol)
        w(f"policies/{sub}/{pol['file_stem']}.md", text)
        md_to_pdf(text, os.path.join(OUT, f"policies/pdf/{pol['file_stem']}.pdf"), pol["title"])


# --------------------------------------------------------------------------- EMPLOYEES
def profile_md(p):
    dept = dept_of(p)
    mode, reason = work_mode(p)
    mgr = BY_SLUG[p["mgr"]] if p["mgr"] else None
    lines = [f"# {p['name']}", "", f"**{p['title']}**, {dept['name']}", ""]
    lines += ["## Employee record", ""]
    rows = [
        ["Employee ID", p["id"]],
        ["Work email", email(p)],
        ["Department", f"{dept['name']} ({dept['id']})"],
        ["Job title", p["title"]],
        ["Band", f"{p['band']} ({[b[1] for b in BANDS if b[0] == p['band']][0]})"],
        ["Reports to", f"{mgr['name']} ({mgr['title']})" if mgr else "Board of Directors"],
        ["Direct reports", ", ".join(pname(s) for s in DIRECT_REPORTS.get(p["slug"], [])) or "None"],
        ["Location", f"{LOC_BY_ID[p['loc']]['name']}, {LOC_BY_ID[p['loc']]['city']}"],
        ["Date of joining", fdate(p["joined"])],
        ["Tenure at Zenvora", f"{tenure_years(p)} years (as of {fdate(AS_OF)})"],
        ["Total experience", f"about {exp_years(p)} years"],
        ["Employment status", p["status"]],
        ["Current work mode", f"{mode}. {reason}"],
        ["Notice period", f"{notice_days(p)} days" + (" (probation)" if on_probation(p) else "")],
    ]
    if p["slug"] == dept["head"]:
        rows.insert(3, ["Role in department", f"Head of {dept['name']}"])
    lines.append(md_table(["Field", "Value"], rows))
    lines += ["", "## About", "", p["summary"]]
    pa = PROJECTS_OF.get(p["slug"], [])
    if pa:
        lines += ["", "## Zenvora projects", ""]
        lines.append(md_table(["Project", "Role", "Period", "Status"], [
            [PROJ_BY_ID[a["project_id"]]["name"], a["role"], f"{fmonth(a['from_date'])} to {fmonth(a['to_date']) if a['to_date'] else 'present'}", PROJ_BY_ID[a["project_id"]]["status"]] for a in pa]))
    owned = [pr for pr in PRODUCTS if pr["owner"] == p["slug"] or pr["eng_lead"] == p["slug"]]
    if owned:
        lines += ["", "## Product responsibilities", ""]
        for pr in owned:
            role = "product owner" if pr["owner"] == p["slug"] else "engineering lead"
            lines.append(f"- {pr['name']}: {role}")
    lines += ["", "## Key achievements at Zenvora", ""] + [f"- {a}" for a in p["ach"]]
    lines += ["", "## Skills", "", ", ".join(p["skills"])]
    if p["certs"]:
        lines += ["", "## Certifications", ""] + [f"- {c}" for c in p["certs"]]
    lines += ["", "## Education", ""] + [f"- {deg}, {inst} ({yr})" for deg, inst, yr in p["edu"]]
    if p["prior"]:
        lines += ["", "## Previous employers", ""] + [f"- {org}: {title} ({fmonth(a)} to {fmonth(b)})" for org, title, a, b, bl in p["prior"]]
    lines += ["", "## Policies that apply to this role", ""]
    lines += [f"- {pol['id']}: {pol['title']}" for pol in policies_for_person(p)]
    lines += ["", f"*Resume: employees/resumes/{resume_stem(p)}.pdf*", "", FICTION_NOTE]
    return "\n".join(lines) + "\n"


def resume_stem(p):
    return f"{p['id']}_{p['name'].replace(' ', '_')}_Resume"


def profile_stem(p):
    return f"{p['id']}_{slugify(p['name'])}"


def resume_summary(p):
    n = exp_years(p)
    top = p["skills"][:3]
    skills = f"{top[0]}, {top[1]} and {top[2]}"
    if n < 1:
        return f"Early-career {p['title'].lower()} with hands-on project experience in {skills}. Looking to build strong engineering fundamentals in a product company."
    return f"{p['title']} with {int(n)} years of professional experience, specialising in {skills}. Known for owning outcomes end to end and for working closely with customers and colleagues from other functions."


def resume_data(p):
    exp = []
    exp.append({
        "org": "Zenvora Technologies Pvt. Ltd.", "title": p["title"], "from": fmonth(p["joined"][:7]), "to": "Present",
        "place": LOC_BY_ID[p["loc"]]["city"], "bullets": list(p["ach"]),
    })
    for org, title, a, b, bl in reversed(p["prior"]):
        exp.append({"org": org, "title": title, "from": fmonth(a), "to": fmonth(b), "place": "", "bullets": bl})
    return exp


def resume_md(p):
    L = [f"# {p['name']}", "", f"{p['title']} | {LOC_BY_ID[p['loc']]['city']}, {LOC_BY_ID[p['loc']]['country']} | {email(p)}", "", "## Professional Summary", "", resume_summary(p), "", "## Experience", ""]
    for e in resume_data(p):
        place = f", {e['place']}" if e["place"] else ""
        L += [f"### {e['title']}, {e['org']}{place}", f"*{e['from']} to {e['to']}*", ""] + [f"- {b}" for b in e["bullets"]] + [""]
    pa = PROJECTS_OF.get(p["slug"], [])
    if pa:
        L += ["## Key Projects at Zenvora", ""]
        for a in pa:
            pj = PROJ_BY_ID[a["project_id"]]
            L.append(f"- **{pj['name']}** ({fmonth(a['from_date'])} to {fmonth(a['to_date']) if a['to_date'] else 'present'}): {a['role']}. {pj['summary']}")
        L.append("")
    L += ["## Education", ""] + [f"- {deg}, {inst}, {yr}" for deg, inst, yr in p["edu"]]
    L += ["", "## Skills", "", ", ".join(p["skills"])]
    if p["certs"]:
        L += ["", "## Certifications", ""] + [f"- {c}" for c in p["certs"]]
    return "\n".join(L) + "\n"


def resume_html(p):
    e = htmllib.escape
    parts = [f"<div class='hdr'><h1>{e(p['name'])}</h1><div class='sub'>{e(p['title'])}</div>"
             f"<div class='contact'>{e(email(p))} &nbsp;|&nbsp; {e(LOC_BY_ID[p['loc']]['city'])}, {e(LOC_BY_ID[p['loc']]['country'])}</div></div>"]
    parts.append(f"<h2>Professional Summary</h2><p>{e(resume_summary(p))}</p>")
    parts.append("<h2>Experience</h2>")
    for x in resume_data(p):
        place = f", {e(x['place'])}" if x["place"] else ""
        parts.append(f"<div class='job'><div class='jt'><b>{e(x['title'])}</b> &mdash; {e(x['org'])}{place}</div><div class='dt'>{e(x['from'])} &ndash; {e(x['to'])}</div><ul>"
                     + "".join(f"<li>{e(b)}</li>" for b in x["bullets"]) + "</ul></div>")
    pa = PROJECTS_OF.get(p["slug"], [])
    if pa:
        parts.append("<h2>Key Projects at Zenvora</h2><ul>")
        for a in pa:
            pj = PROJ_BY_ID[a["project_id"]]
            parts.append(f"<li><b>{e(pj['name'])}</b> ({e(fmonth(a['from_date']))} &ndash; {e(fmonth(a['to_date']) if a['to_date'] else 'present')}): {e(a['role'])}. {e(pj['summary'])}</li>")
        parts.append("</ul>")
    parts.append("<h2>Education</h2><ul>" + "".join(f"<li>{e(deg)}, {e(inst)}, {yr}</li>" for deg, inst, yr in p["edu"]) + "</ul>")
    parts.append(f"<h2>Skills</h2><p>{e(', '.join(p['skills']))}</p>")
    if p["certs"]:
        parts.append("<h2>Certifications</h2><ul>" + "".join(f"<li>{e(c)}</li>" for c in p["certs"]) + "</ul>")
    css = CSS + ".hdr{border-bottom:3px solid #14304f;margin-bottom:8px}.sub{font-size:12pt;color:#14304f}.contact{font-size:9.5pt;color:#44505c;margin:4px 0 8px 0}.jt{margin-top:6px}.dt{font-size:9.5pt;color:#5a6672}"
    return f"<html><head><meta charset='utf-8'><title>{e(p['name'])} - Resume</title><style>{css}</style></head><body>{''.join(parts)}</body></html>"


def build_employees():
    for p in PEOPLE:
        w(f"employees/profiles/{profile_stem(p)}.md", profile_md(p))
        w(f"employees/resumes_md/{resume_stem(p)}.md", resume_md(p))
        html_to_pdf(resume_html(p), os.path.join(OUT, f"employees/resumes/{resume_stem(p)}.pdf"))


# --------------------------------------------------------------------------- DEPARTMENTS
def dept_md(dep):
    head = BY_SLUG[dep["head"]]
    members = [p for p in PEOPLE if p["dept"] == dep["code"]]
    members.sort(key=lambda p: (-int(p["band"][1:]), p["name"]))
    loc = LOC_BY_ID[dep["location"]]
    L = [f"# {dep['name']}", "", f"**Department ID:** {dep['id']} | **Head:** {head['name']} ({head['title']}) | **Headcount:** {HEADCOUNT[dep['code']]} | **Primary location:** {loc['name']}", ""]
    if dep["reports_to"]:
        L.append(f"**Reports to:** {pname(dep['reports_to'])} ({person(dep['reports_to'])['title']})")
        L.append("")
    L += ["## Mission", "", dep["mission"], "", "## What the department does", ""] + [f"- {f}" for f in dep["functions"]]
    L += ["", "## Key performance indicators", ""] + [f"- {k}" for k in dep["kpis"]]
    L += ["", "## Tools and systems", "", ", ".join(dep["tools"]), "", "## People", ""]
    L.append(md_table(["Employee ID", "Name", "Title", "Band", "Reports to", "Location", "Joined"],
                      [[m["id"], m["name"], m["title"], m["band"], pname(m["mgr"]) if m["mgr"] else "Board", LOC_BY_ID[m["loc"]]["city"], fdate(m["joined"])] for m in members]))
    projs = [pj for pj in PROJECTS if dep["code"] in pj["depts"] or any(BY_SLUG[s]["dept"] == dep["code"] for s, _ in pj["team"])]
    if projs:
        L += ["", "## Projects the department has contributed to", ""]
        for pj in projs:
            who = [pname(s) for s, _ in pj["team"] if BY_SLUG[s]["dept"] == dep["code"]]
            L.append(f"- **{pj['name']}** ({pj['status']}): {', '.join(who)}")
    own = [pol for pol in POLICIES if pol["dept"] == dep["code"]]
    L += ["", "## Policies owned by this department", ""] + [f"- {pol['id']}: {pol['title']}" for pol in own]
    applies = [pol for pol in POLICIES if pol["scope"] == "Departmental" and dep["code"] in POLICY_APPLIES[pol["id"]] and pol["dept"] != dep["code"]]
    if applies:
        L += ["", "## Policies from other departments that apply here", ""] + [f"- {pol['id']}: {pol['title']}" for pol in applies]
    L += ["", "All company-wide policies (ZEN-POL-001 to ZEN-POL-008) also apply.", "", FICTION_NOTE]
    return "\n".join(L) + "\n"


def build_departments():
    for dep in DEPARTMENTS:
        w(f"departments/{dep['id']}_{slugify(dep['name'])[:50]}.md", dept_md(dep))


# --------------------------------------------------------------------------- PROJECTS & PRODUCTS
def project_md(pj):
    L = [f"# {pj['name']}", "", f"**Project ID:** {pj['id']} | **Status:** {pj['status']} | **Start:** {fdate(pj['start'])} | **End:** {fdate(pj['end']) if pj['end'] else 'ongoing'}", "",
         f"**Executive sponsor:** {person_label(pj['sponsor'])}  ", f"**Project lead:** {person_label(pj['lead'])}  ",
         "**Departments involved:** " + ", ".join(DEPT_BY_CODE[c]["name"] for c in pj["depts"]), "", "## Summary", "", pj["summary"], "", "## Goals", ""]
    L += [f"- {g}" for g in pj["goals"]]
    L += ["", "## Outcomes" if pj["end"] else "## Progress so far", ""] + [f"- {o}" for o in pj["outcomes"]]
    L += ["", "## Technology", "", ", ".join(pj["tech"]), "", "## Team", ""]
    L.append(md_table(["Employee ID", "Name", "Department", "Role on project"], [[pid(s), pname(s), dept_of(BY_SLUG[s])["name"], r] for s, r in pj["team"]]))
    L += ["", "## Milestones", ""] + [f"- {fdate(a)}: {b}" for a, b in pj["milestones"]]
    L += ["", FICTION_NOTE]
    return "\n".join(L) + "\n"


def product_md(pr):
    L = [f"# {pr['name']}", "", f"**Product ID:** {pr['id']} | **Launched:** {fdate(pr['launched'])}", "", f"**Product owner:** {person_label(pr['owner'])}  ", f"**Engineering / operations lead:** {person_label(pr['eng_lead'])}", "",
         "## What it is", "", pr["summary"], "", "## Technology", "", ", ".join(pr["stack"]), "", "## Scale (FY2025-26)", "", pr["stats"], "", FICTION_NOTE]
    return "\n".join(L) + "\n"


def build_projects():
    for pr in PRODUCTS:
        w(f"projects/products/{pr['id']}_{slugify(pr['name'])}.md", product_md(pr))
    for pj in PROJECTS:
        w(f"projects/{pj['id']}_{slugify(pj['name'])}.md", project_md(pj))


# --------------------------------------------------------------------------- COMPANY
def overview_md():
    c = COMPANY
    L = [f"# {c['name']}: Company Overview", "", f"> {c['tagline']}", "", FICTION_NOTE, "", "## At a glance", ""]
    L.append(md_table(["Item", "Detail"], [
        ["Legal name", c["name"]], ["Founded", fdate(c["founded"])], ["Headquarters", c["hq"]], ["Industry", c["industry"]],
        ["Founder and CEO", "Arvind Kulkarni"], ["Co-founder and CTO", "Meera Subramanian"], ["Employees", f"{c['employees']} (as of {fdate(AS_OF)})"],
        ["Revenue FY2025-26", f"INR {c['revenue_fy26_inr_cr']} crore"], ["Attrition FY2025-26", f"{c['attrition_fy26_pct']} percent"],
        ["Financial year", c["fiscal_year"]], ["Customers", f"{c['pulse_customers']} Pulse customers, {c['ledger_businesses']:,} Ledger businesses, {c['care_client_brands']} Care client brands"]]))
    L += ["", "## Mission and vision", "", f"**Mission:** {c['mission']}", "", f"**Vision:** {c['vision']}", "", "## Values", ""]
    L += [f"- **{a}:** {b}" for a, b in c["values"]]
    L += ["", "## Products and services", ""]
    for pr in PRODUCTS:
        L.append(f"- **{pr['name']}** (launched {fdate(pr['launched'])}): {pr['summary']}")
    L += ["", "## Locations", ""]
    L.append(md_table(["ID", "Location", "Type", "Opened", "Notes"], [[l["id"], l["name"], l["type"], fdate(l["opened"]), l["notes"]] for l in LOCATIONS]))
    L += ["", "## Departments", ""]
    L.append(md_table(["ID", "Department", "Head", "Headcount", "Location"], [[x["id"], x["name"], pname(x["head"]), HEADCOUNT[x["code"]], LOC_BY_ID[x["location"]]["city"]] for x in DEPARTMENTS]))
    L += ["", "## Board of Directors", ""] + [md_table(["Name", "Role", "Background"], [list(b) for b in BOARD])]
    L += ["", "## Investors", ""] + [md_table(["Investor", "Type", "Round", "Date", "Amount"], [list(i) for i in INVESTORS])]
    L += ["", "## Selected customers", ""] + [md_table(["Customer", "Products", "Account owner"], [[a, b, pname(s)] for a, b, s in CUSTOMERS])]
    L += ["", "## Bands (grades)", "", md_table(["Band", "Level", "Meaning"], [list(b) for b in BANDS]), "", "## Partner", "", "Overflow support for Zenvora Care is handled by partner BPO **Sutradhar Business Services** (masked data access only)."]
    return "\n".join(L) + "\n"


def history_md():
    L = ["# Company Timeline", "", FICTION_NOTE, ""]
    L.append(md_table(["Date", "Type", "Event", "Details"], [[fdate(a), b, c, e] for a, b, c, e in TIMELINE]))
    return "\n".join(L) + "\n"


def org_md():
    L = ["# Organisation Structure and Reporting Lines", "", f"As of {fdate(AS_OF)}. Indentation shows who reports to whom.", "", FICTION_NOTE, "", "## Reporting tree", ""]
    L += tree_lines("arvind")
    L += ["", "## Department heads", ""]
    L.append(md_table(["Department", "Head", "Band", "Reports to"], [[x["name"], pname(x["head"]), person(x["head"])["band"], pname(person(x["head"])["mgr"]) if person(x["head"])["mgr"] else "Board"] for x in DEPARTMENTS]))
    L += ["", "## Leadership team", "", "Arvind Kulkarni (CEO), Meera Subramanian (CTO), Ramesh Iyengar (CFO), Gaurav Malhotra (CRO), Sunita Banerjee (Head of Product), Lakshmi Prasanna Varma (Head of People & Culture), Suresh Babu Kothapalli (Head of Customer Care). The leadership team meets weekly on Monday."]
    return "\n".join(L) + "\n"


def handbook_md():
    L = ["# New Joiner Handbook", "", "Welcome to Zenvora. This handbook points to the policies and systems you will use in your first weeks.", "", FICTION_NOTE, "",
         "## Your first 90 days", "", "During the first 90 days you work from the office on all working days (Hybrid Work Policy, ZEN-POL-002). Your probation lasts 6 months.", "",
         md_table(["#", "Task", "Owner", "Due (days from joining)", "System"],
                  [[i + 1, t, o, f"day {due}", s] for i, (t, o, due, dep, s) in enumerate(ONBOARDING)]),
         "", "## Systems you will use", "", md_table(["System", "What it is for", "Address", "Owner"], [list(s) for s in SYSTEMS]),
         "", "## Key contacts", "", md_table(["Topic", "Contact", "Channel"], [
             ["HR questions", "Tanvi Deshpande (HR Business Partner)", "Slack #ask-hr, ask-hr@zenvora.example"],
             ["Hiring and onboarding paperwork", "Imran Qureshi", "ask-hr@zenvora.example"],
             ["Payroll and expense claims", "Pavan Kumar Goud, Shalini Rao", "payroll@zenvora.example"],
             ["IT help", "Rekha Sharma (helpdesk), Manoj Thomas (CISO)", "Slack #ask-it, it-helpdesk@zenvora.example"],
             ["Security incidents", "Manoj Thomas", "security@zenvora.example, Slack #incidents"],
             ["POSH Internal Committee", "Tanvi Deshpande (Presiding Officer)", "posh@zenvora.example"],
             ["Health and safety", "Tanvi Deshpande", "ehs@zenvora.example"],
             ["Ethics and whistleblowing", "Head of People & Culture or Audit Committee chair", "ethics@zenvora.example"]]),
         "", "## Benefits at a glance", "",
         "- Group health insurance for you and your family (floater of INR 5 lakh), with an annual health check-up.",
         "- Learning budget of INR 30,000 per employee per financial year.", "- 24x7 confidential Employee Assistance Programme.",
         "- Home internet allowance of INR 1,000 per month for hybrid employees.", "- 2 paid volunteer days a year ('Zenvora Gives Back').", "",
         "## Culture and rituals", "",
         "- **Monthly all-hands:** first Friday of each month.", "- **Quarterly town hall** with Q&A from the CEO and leadership team.",
         "- **Hack Week** twice a year (April and October).", "- **Friday Learning Hour:** one short talk or demo every Friday afternoon.",
         "- **Anniversary awards** at 5 and 10 years of service.", "- **Focus Friday:** no internal meetings before 12:00.", "",
         "## Glossary", "", md_table(["Term", "Meaning"], [list(g) for g in GLOSSARY]), "",
         "## Frequently asked questions", ""]
    for q, a, src in FAQS:
        L += [f"**{q}**  ", f"{a} *(Source: {src})*", ""]
    return "\n".join(L) + "\n"


def readme_md():
    return f"""# Zenvora Technologies: GraphRAG Demo Dataset

A fictional company with departments, employees, resumes, policies, projects and history, built for a Graph RAG project where a new joiner asks a chatbot about the company.

> Everything here is invented. Any resemblance to real people or companies is coincidental.

## What is inside

| Folder | Contents | Count |
|---|---|---|
| `company/` | Overview, story, timeline, org structure, new-joiner handbook, all-hands notes, customer case study | 8 files |
| `departments/` | One profile per department with mission, functions, people, projects, policies | {len(DEPARTMENTS)} files |
| `employees/profiles/` | HR-style profile for each employee (Markdown) | {len(PEOPLE)} files |
| `employees/resumes/` | One resume per employee (PDF) | {len(PEOPLE)} files |
| `employees/resumes_md/` | Same resumes as Markdown (for quick inspection) | {len(PEOPLE)} files |
| `policies/company_wide/`, `policies/departmental/` | Policies in Markdown | {len(POLICIES)} files |
| `policies/pdf/` | The same policies as PDF | {len(POLICIES)} files |
| `projects/` | {len(PRODUCTS)} product pages and {len(PROJECTS)} project dossiers | {len(PRODUCTS) + len(PROJECTS)} files |
| `data/csv/` | Structured tables for graph import (nodes and relationships) | see `data/SCHEMA.md` |
| `data/neo4j_import.cypher` | LOAD CSV script that builds the graph | 1 file |
| `eval/` | Question and answer pairs with ground truth for testing retrieval | 2 files |
| `generator/` | Python source that regenerates everything | |

## The company in one paragraph

Zenvora Technologies is a Hyderabad SaaS company founded in 2014 by Arvind Kulkarni and Meera Subramanian. It sells **Pulse** (omnichannel customer inbox), **Ledger** (invoicing and reconciliation) and **Care** (managed customer support run from a Visakhapatnam centre). It has {COMPANY['employees']} employees across {len(DEPARTMENTS) - 1} departments plus the Executive Office, in Hyderabad, Bengaluru, Visakhapatnam and Austin. Data is as of {fdate(AS_OF)}.

## How the pieces connect (what makes this a good graph test)

- People report to people (a real hierarchy, 4 levels deep), belong to departments and locations, and have bands that drive rules (notice period, hotel limit, who must work from office every day).
- Employees are assigned to projects with roles. Projects have sponsors, leads and contributing departments.
- Policies cite each other explicitly (for example Hybrid Work refers to Leave, Discipline and Security policies) and cite approvers who are employees in the graph.
- Some answers need several hops, for example: *'Who is the head of the department of Sneha's manager?'* or *'Does Tarun need to come to the office on Mondays, and why?'*
- Time matters: one employee is serving notice, one is on maternity leave, one is in induction, one is on probation. As-of date is {AS_OF}.
- Resumes add prior employers, universities, certifications and skills, which create shared nodes across people.

## Suggested use

1. Chunk `policies/`, `departments/`, `projects/`, `company/` and `employees/` documents for the vector side.
2. Load `data/csv/` with `data/neo4j_import.cypher` for the graph side (or build the graph by LLM extraction from the documents and compare with the CSVs as ground truth).
3. Test the chatbot with `eval/questions.csv`.
"""


def build_company():
    w("company/01_company_overview.md", overview_md())
    w("company/02_zenvora_story.md", STORY)
    w("company/03_company_timeline.md", history_md())
    w("company/04_org_structure.md", org_md())
    w("company/05_new_joiner_handbook.md", handbook_md())
    w("company/06_all_hands_notes_2026-09-04.md", ALL_HANDS)
    w("company/07_customer_story_medilink.md", CASE_STUDY)
    w("README.md", readme_md())


def build_all():
    build_company()
    build_departments()
    build_projects()
    build_policies()
    build_employees()


if __name__ == "__main__":
    build_all()
    print("docs built")
