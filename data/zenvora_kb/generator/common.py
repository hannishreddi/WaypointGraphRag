# -*- coding: utf-8 -*-
"""Shared helpers and derived facts."""
import datetime as dt
import re
from collections import defaultdict

from data_company import *
from data_people import PEOPLE, BY_SLUG
from data_policies_a import POLICIES_A
from data_policies_b import POLICIES_B
from data_extra import RULES, FAQS, ONBOARDING
from story import STORY, ALL_HANDS, CASE_STUDY

OUT = "/home/claude/zenvora_kb"
TODAY = dt.date.fromisoformat(AS_OF)
POLICIES = POLICIES_A + POLICIES_B
POL_BY_ID = {p["id"]: p for p in POLICIES}
DEPT_BY_CODE = {d["code"]: d for d in DEPARTMENTS}
DEPT_BY_ID = {d["id"]: d for d in DEPARTMENTS}
LOC_BY_ID = {l["id"]: l for l in LOCATIONS}
PROJ_BY_ID = {p["id"]: p for p in PROJECTS}

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def d(s):
    return dt.date.fromisoformat(s)


def fdate(s):
    x = d(s)
    return f"{x.day} {MONTHS[x.month - 1]} {x.year}"


def fmonth(s):
    y, m = s.split("-")[:2]
    return f"{MONTHS[int(m) - 1]} {y}"


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def person(slug):
    return BY_SLUG[slug]


def pname(slug):
    return BY_SLUG[slug]["name"]


def pid(slug):
    return BY_SLUG[slug]["id"]


# ---- policy header normalisation: version/revision/effective derived from history ----
for _p in POLICIES:
    last = _p["history"][-1]
    label = last[0]
    if "." in label:
        _p["version"], _p["revision"] = label.split(".", 1)
    else:
        _p["version"], _p["revision"] = label, "0"
    _p["effective"] = last[2]
    _p["owner_dept_id"] = DEPT_BY_CODE[_p["dept"]]["id"]
    _p["file_stem"] = _p["id"] + "_" + slugify(_p["title"])[:60]

# which departments each departmental policy applies to ("ALL" = everyone)
POLICY_APPLIES = {
    "ZEN-DPL-HR-01": ["ALL"], "ZEN-DPL-FIN-01": ["ALL"], "ZEN-DPL-ITS-01": ["ALL"],
    "ZEN-DPL-BKE-01": ["BKE"], "ZEN-DPL-FME-01": ["FME", "PDS"], "ZEN-DPL-DAI-01": ["DAI", "CSC", "QAT"],
    "ZEN-DPL-QAT-01": ["QAT", "BKE", "FME", "DAI", "DCL"], "ZEN-DPL-DCL-01": ["DCL", "BKE", "FME", "DAI"],
    "ZEN-DPL-PDS-01": ["PDS", "FME", "CSC", "SAM"], "ZEN-DPL-SAM-01": ["SAM"], "ZEN-DPL-CSC-01": ["CSC"],
}


def policies_for_person(p):
    out = []
    for pol in POLICIES:
        if pol["scope"] == "Company-wide":
            out.append(pol)
        else:
            ap = POLICY_APPLIES[pol["id"]]
            if "ALL" in ap or p["dept"] in ap:
                out.append(pol)
    return out


# ---- people-derived facts ----
DIRECT_REPORTS = defaultdict(list)
for _p in PEOPLE:
    if _p["mgr"]:
        DIRECT_REPORTS[_p["mgr"]].append(_p["slug"])

HEADCOUNT = defaultdict(int)
for _p in PEOPLE:
    HEADCOUNT[_p["dept"]] += 1


def dept_of(p):
    return DEPT_BY_CODE[p["dept"]]


def induction_end(p):
    return d(p["joined"]) + dt.timedelta(days=90)


def on_probation(p):
    j = d(p["joined"])
    months = (TODAY.year - j.year) * 12 + (TODAY.month - j.month) - (1 if TODAY.day < j.day else 0)
    return months < 6


def work_mode(p):
    """Return (mode, reason) as of AS_OF according to ZEN-POL-002 and ZEN-DPL-CSC-01."""
    if p["status"].startswith("On maternity"):
        return "On leave", "On maternity leave (ZEN-POL-003)"
    if p["status"].startswith("Serving notice"):
        return "Full WFO (all working days)", "Serving notice period (ZEN-POL-002)"
    if p["dept"] == "CSC":
        return "On-site shift roster", "Customer Support shift staff work on site (ZEN-DPL-CSC-01)"
    if p["loc"] == "L04":
        return "Remote-first (Austin)", "Austin Regional Supplement (ZEN-POL-002)"
    if p["band"] == "Z1":
        return "Full WFO (all working days)", "Band Z1 trainee (ZEN-POL-002)"
    if TODAY <= induction_end(p):
        return "Full WFO (all working days)", f"Induction: first 90 days, until {fdate(induction_end(p).isoformat())} (ZEN-POL-002)"
    return "Hybrid (3 days WFO)", "Standard rule (ZEN-POL-002)"


def notice_days(p):
    if on_probation(p):
        return 30
    return NOTICE_PERIOD_DAYS[p["band"]]


def tenure_years(p):
    return round((TODAY - d(p["joined"])).days / 365.25, 1)


def exp_years(p):
    starts = []
    for org, title, a, b, bl in p["prior"]:
        if "Intern" in title:
            continue
        starts.append(a)
    start = min(starts) if starts else p["joined"][:7]
    y, m = [int(x) for x in start.split("-")[:2]]
    return round((TODAY.year - y) + (TODAY.month - m) / 12, 1)


def email(p):
    first = p["name"].split()[0].lower()
    last = p["name"].split()[-1].lower()
    return f"{first}.{last}@zenvora.example"


def assignments():
    rows = []
    for pj in PROJECTS:
        for slug, role in pj["team"]:
            p = BY_SLUG[slug]
            frm = max(d(pj["start"]), d(p["joined"])).isoformat()
            rows.append(dict(project_id=pj["id"], slug=slug, employee_id=p["id"], role=role, from_date=frm, to_date=pj["end"] or "", current=pj["end"] is None))
    return rows


ASSIGN = assignments()
PROJECTS_OF = defaultdict(list)
for _a in ASSIGN:
    PROJECTS_OF[_a["slug"]].append(_a)


def hotel_limit(band, city_tier):
    tbl = {"Z1": (4500, 3500), "Z2": (4500, 3500), "Z3": (4500, 3500), "Z4": (7000, 5500), "Z5": (7000, 5500), "Z6": (7000, 5500), "Z7": (11000, 8500), "Z8": (11000, 8500)}
    return tbl[band][0 if city_tier == 1 else 1]


def inr(n):
    s = f"{n:,}"
    return "INR " + s


def reports_chain(slug):
    chain = []
    cur = BY_SLUG[slug]["mgr"]
    while cur:
        chain.append(cur)
        cur = BY_SLUG[cur]["mgr"]
    return chain


def tree_lines(slug, depth=0):
    p = BY_SLUG[slug]
    lines = [("  " * depth) + f"- **{p['name']}**, {p['title']} ({dept_of(p)['name']}, {p['band']})"]
    for c in sorted(DIRECT_REPORTS.get(slug, []), key=lambda s: (BY_SLUG[s]["dept"] != BY_SLUG[slug]["dept"], -int(BY_SLUG[s]["band"][1:]), BY_SLUG[s]["name"])):
        lines += tree_lines(c, depth + 1)
    return lines
