# -*- coding: utf-8 -*-
"""Consistency checks across the generated dataset. Prints problems; exit code 1 if any."""
import csv
import glob
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict

from common import *

problems = []


def bad(msg):
    problems.append(msg)


# --- people / hierarchy
slugs = {p["slug"] for p in PEOPLE}
if len(PEOPLE) != COMPANY["employees"]:
    bad(f"headcount {len(PEOPLE)} != company employees {COMPANY['employees']}")
if len({p["id"] for p in PEOPLE}) != len(PEOPLE):
    bad("duplicate employee IDs")
if len({email(p) for p in PEOPLE}) != len(PEOPLE):
    bad("duplicate emails")
tops = [p["slug"] for p in PEOPLE if not p["mgr"]]
if tops != ["arvind"]:
    bad(f"people without manager: {tops}")
for p in PEOPLE:
    if p["mgr"] and p["mgr"] not in slugs:
        bad(f"{p['slug']}: unknown manager {p['mgr']}")
    seen, cur = set(), p["slug"]
    while cur:
        if cur in seen:
            bad(f"cycle at {cur}")
            break
        seen.add(cur)
        cur = BY_SLUG[cur]["mgr"]
    if p["mgr"]:
        m = BY_SLUG[p["mgr"]]
        if int(m["band"][1:]) < int(p["band"][1:]) or (int(m["band"][1:]) == int(p["band"][1:]) and p["band"] != "Z8"):
            bad(f"{p['slug']} ({p['band']}) reports to {m['slug']} ({m['band']}): manager not senior")
        if d(m["joined"]) > d(p["joined"]):
            print(f"note: {p['slug']} joined before manager {m['slug']}")
    if p["loc"] not in LOC_BY_ID:
        bad(f"{p['slug']}: bad location")
    if p["dept"] not in DEPT_BY_CODE:
        bad(f"{p['slug']}: bad dept")
    if d(p["joined"]) > TODAY:
        bad(f"{p['slug']}: joins in the future")
    if d(p["joined"]) < d(COMPANY["founded"]):
        bad(f"{p['slug']}: joined before company founded")

# departments
if sum(HEADCOUNT.values()) != len(PEOPLE):
    bad("department headcount mismatch")
for dep in DEPARTMENTS:
    h = BY_SLUG[dep["head"]]
    if h["dept"] != dep["code"]:
        bad(f"{dep['id']} head {dep['head']} not in department")
    rt = dep["reports_to"]
    if (h["mgr"] or None) != rt:
        bad(f"{dep['id']} reports_to {rt} != head's manager {h['mgr']}")
    if h["loc"] != dep["location"] and dep["code"] not in ("BKE", "FME", "DAI"):
        print(f"note: {dep['id']} head location {h['loc']} differs from department location {dep['location']}")
    for p in PEOPLE:
        if p["dept"] == dep["code"] and p["slug"] != dep["head"]:
            # must reach head via chain
            if dep["head"] not in reports_chain(p["slug"]):
                bad(f"{p['slug']} does not roll up to its department head {dep['head']}")

# experience timeline
for p in PEOPLE:
    jm = p["joined"][:7]
    last_end = None
    edu_year = min(y for deg, _, y in p["edu"] if "Chartered" not in deg and "CMA" not in deg and "Cost & Management" not in deg)
    for org, title, a, b, bl in p["prior"]:
        if a > b:
            bad(f"{p['slug']}: {org} start after end")
        if b > jm:
            bad(f"{p['slug']}: {org} ends after joining Zenvora")
        if "Intern" not in title and int(a[:4]) < edu_year:
            bad(f"{p['slug']}: job at {org} starts {a} before final degree {edu_year}")
        if last_end and a < last_end:
            bad(f"{p['slug']}: overlapping jobs at {org}")
        last_end = b
    if p["prior"] and last_end:
        # gap to Zenvora more than 4 months?
        y1, m1 = map(int, last_end.split("-"))
        y2, m2 = map(int, jm.split("-"))
        gap = (y2 - y1) * 12 + (m2 - m1)
        if gap > 4 and "Intern" not in p["prior"][-1][1]:
            bad(f"{p['slug']}: {gap}-month gap before joining Zenvora")

# projects
for pj in PROJECTS:
    ts = [s for s, _ in pj["team"]]
    if pj["lead"] not in ts:
        bad(f"{pj['id']} lead not in team")
    if len(ts) != len(set(ts)):
        bad(f"{pj['id']} duplicate team member")
    end = d(pj["end"]) if pj["end"] else TODAY
    for s in ts + [pj["sponsor"]]:
        if d(BY_SLUG[s]["joined"]) > end:
            bad(f"{pj['id']}: {s} joined after project ended")
    teamdepts = {BY_SLUG[s]["dept"] for s in ts}
    for c in pj["depts"]:
        if c not in teamdepts and c != BY_SLUG[pj["sponsor"]]["dept"]:
            bad(f"{pj['id']}: department {c} listed but no team member from it")
    for c in teamdepts:
        if c not in pj["depts"]:
            print(f"note: {pj['id']} has members from {c} not in depts list")
    ms = [a for a, _ in pj["milestones"]]
    if ms != sorted(ms):
        bad(f"{pj['id']} milestones not ordered")
    if ms[0] < pj["start"]:
        bad(f"{pj['id']} milestone before start")
    if pj["end"] and ms[-1] > pj["end"]:
        bad(f"{pj['id']} milestone after end")

# achievements mentioning projects must match membership
names = {pj["name"]: pj for pj in PROJECTS}
for p in PEOPLE:
    for a in p["ach"]:
        for n, pj in names.items():
            if n in a:
                members = {s for s, _ in pj["team"]} | {pj["sponsor"], pj["lead"]}
                if p["slug"] not in members:
                    bad(f"{p['slug']} achievement mentions {n} but is not on it: {a}")

# policies
for pol in POLICIES:
    for r in pol["refs"]:
        if r not in POL_BY_ID:
            bad(f"{pol['id']} references unknown {r}")
        if r == pol["id"]:
            bad(f"{pol['id']} references itself")
    for k in ("prepared_by", "reviewed_by", "approved_by"):
        if pol[k] not in slugs:
            bad(f"{pol['id']} {k} unknown")
    if BY_SLUG[pol["prepared_by"]]["dept"] != pol["dept"]:
        bad(f"{pol['id']} prepared_by not from owning department")
    hist_dates = [h[2] for h in pol["history"]]
    if hist_dates != sorted(hist_dates):
        bad(f"{pol['id']} history not ordered")
    if d(hist_dates[-1]) < d(BY_SLUG[pol["prepared_by"]]["joined"]):
        bad(f"{pol['id']} latest revision predates preparer joining")
    if d(hist_dates[0]) < d(COMPANY["founded"]):
        bad(f"{pol['id']} history before founding")
    if d(pol["next_review"]) <= TODAY:
        bad(f"{pol['id']} next review not in the future")
    if d(pol["effective"]) > TODAY:
        bad(f"{pol['id']} effective in the future")
    # reciprocal reference sanity: cited ids in text must be in refs
    text = repr(pol["sections"])
    for cited in set(re.findall(r"ZEN-(?:POL-\d{3}|DPL-[A-Z]{2,3}-\d{2})", text)):
        if cited != pol["id"] and cited not in pol["refs"]:
            bad(f"{pol['id']} text cites {cited} but it is not in refs")
        if cited not in POL_BY_ID:
            bad(f"{pol['id']} text cites nonexistent {cited}")
for rid in {r[0] for r in RULES}:
    if rid not in POL_BY_ID:
        bad(f"rule for unknown policy {rid}")
for q, a, s in FAQS:
    if s not in POL_BY_ID:
        bad(f"FAQ source unknown {s}")
polids = {p["id"] for p in POLICIES}
for pid_ in polids:
    if not any(r[0] == pid_ for r in RULES):
        bad(f"no curated rules for {pid_}")

# POSH committee members exist
for nm in ["Tanvi Deshpande", "Deepa Venkatesh", "Lavanya Murthy"]:
    if nm not in {p["name"] for p in PEOPLE}:
        bad(f"POSH member {nm} not an employee")

# timeline
tl = [t[0] for t in TIMELINE]
if tl != sorted(tl):
    bad("timeline not ordered")
for t in TIMELINE:
    if d(t[0]) > TODAY:
        bad(f"timeline event in the future: {t}")

# narrative names must be real employees (first+last name tokens)
fulls = {p["name"] for p in PEOPLE}
narr = STORY + ALL_HANDS + CASE_STUDY
for m in re.findall(r"\*\*([A-Z][a-z]+(?: [A-Z][a-z]+)+)\*\*", narr):
    if m not in fulls and m not in {b[0] for b in BOARD} and m not in {"Zenvora Care", "Pulse Mobile", "Zenvora Sage", "Project Nova", "Project Atlas", "Project Compass", "Project Beacon", "Project Sentinel", "Project Horizon", "Project Ember", "Project Lighthouse", "Zenvora Ledger", "Pulse Mobile"}:
        print(f"note: bold name in narrative not an employee: {m}")

# Fact checks derived from data
bgl = [p for p in PEOPLE if p["loc"] == "L02"]
eng = [p for p in PEOPLE if p["dept"] in ("BKE", "FME", "DAI", "QAT", "DCL")]
print(f"info: Bengaluru has {len(bgl)} people; engineering-type departments have {len(eng)}; Bengaluru engineers = {sum(1 for p in bgl if p['dept'] in ('BKE','FME','DAI','QAT','DCL'))}")
print("info: work modes:", Counter(work_mode(p)[0] for p in PEOPLE))
print("info: bands:", sorted(Counter(p["band"] for p in PEOPLE).items()))
print("info: depts:", {k: v for k, v in HEADCOUNT.items()})

# --- generated files
csvdir = os.path.join(OUT, "data", "csv")
emp = list(csv.DictReader(open(os.path.join(csvdir, "employees.csv"), encoding="utf-8")))
if len(emp) != 42:
    bad("employees.csv rows != 42")
for r in emp:
    for col in ("profile_file", "resume_file"):
        if not os.path.exists(os.path.join(OUT, r[col])):
            bad(f"missing {r[col]}")
# FK checks
ids = {r["employee_id"] for r in emp}
for fn, col in [("reporting_lines.csv", "manager_employee_id"), ("project_assignments.csv", "employee_id"), ("employee_skills.csv", "employee_id"), ("education.csv", "employee_id")]:
    for r in csv.DictReader(open(os.path.join(csvdir, fn), encoding="utf-8")):
        if r[col] not in ids:
            bad(f"{fn}: bad FK {r[col]}")
for r in csv.DictReader(open(os.path.join(csvdir, "policy_references.csv"), encoding="utf-8")):
    if r["to_policy_id"] not in polids or r["from_policy_id"] not in polids:
        bad("policy_references FK")

# resume PDFs contain name and employer
for p in PEOPLE:
    f = glob.glob(os.path.join(OUT, "employees", "resumes", f"{p['id']}_*.pdf"))
    if len(f) != 1:
        bad(f"{p['slug']}: resume pdf count {len(f)}")
        continue
    txt = subprocess.run(["pdftotext", f[0], "-"], capture_output=True, text=True).stdout
    if p["name"] not in txt or "Zenvora" not in txt:
        bad(f"{p['slug']}: resume PDF missing name/employer")
    if "Serving notice" in txt or "maternity" in txt.lower():
        bad(f"{p['slug']}: resume contains HR status text")

# stray placeholders in markdown
for f in glob.glob(os.path.join(OUT, "**", "*.md"), recursive=True):
    t = open(f, encoding="utf-8").read()
    for pat in (r"\bNone\b(?! \|)", r"\bnan\b", r"\{[a-z_]+\}", r"\bTODO\b"):
        for m in re.finditer(pat, t):
            ctx = t[max(0, m.start() - 30): m.end() + 30].replace("\n", " ")
            if pat.startswith(r"\bNone"):
                # allowed: 'Direct reports | None'
                if "Direct reports" in ctx or "None" in ctx and "Direct" in t[max(0, m.start() - 40): m.start()]:
                    continue
            bad(f"{os.path.relpath(f, OUT)}: placeholder-like text '{m.group(0)}' near: {ctx}")

print()
if problems:
    print(f"{len(problems)} problem(s):")
    for x in problems:
        print(" -", x)
    sys.exit(1)
print("All checks passed")
