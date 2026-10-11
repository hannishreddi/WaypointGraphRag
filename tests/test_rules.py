"""Rule engine (PLAN 2.3). employees.csv derived columns (work_mode, notice_period_days,
tenure_years) are used here only as the answer key; runtime code never reads them."""
from __future__ import annotations

import inspect
import re
from datetime import date

import pytest

from waypoint.contract import GraphCitation, PolicyCitation
from waypoint.graph.load import read_csv
from waypoint.rules import derived as Dv
from waypoint.rules import engine, facts as F
from waypoint.rules.engine import evaluate, load_rules
from waypoint.config import DATA_DIR

AS_OF = date(2026, 10, 10)
HR_HEAD, HR_BP, HR_EXEC = "ZV-1006", "ZV-1019", "ZV-1036"
ARJUN, NAVEEN, DIVYA, KARTHIK, SNEHA = "ZV-1042", "ZV-1013", "ZV-1004", "ZV-1003", "ZV-1028"
POOJA, TARUN, CEO = "ZV-1031", "ZV-1033", "ZV-1001"
EMPLOYEES = read_csv("employees")


def _policy_cites(r) -> set[tuple[str, int | str | None]]:
    return {(c.id, c.section) for c in r.citations if isinstance(c, PolicyCitation)}


# ---------------------------------------------------------------- facts: no answer-key columns

def test_csv_facts_never_read_derived_columns() -> None:
    assert not set(F.BASE_COLUMNS) & set(F.DERIVED_COLUMNS)
    src = inspect.getsource(F) + inspect.getsource(Dv) + inspect.getsource(engine)
    for col in F.DERIVED_COLUMNS:  # never accessed as a CSV field
        assert f'["{col}"]' not in src and f"['{col}']" not in src and f'get("{col}"' not in src


def test_csv_facts_cover_every_employee() -> None:
    facts = F.facts_from_csv()
    assert len(facts) == len(EMPLOYEES) == 42
    a = facts[ARJUN]
    assert (a.band, a.join_date, a.department_code, a.manager_id, a.base_city) == \
        ("Z2", date(2026, 7, 20), "BKE", NAVEEN, "Hyderabad")


# ---------------------------------------------------------------- derived attributes and dates

@pytest.mark.parametrize("join,n,expected", [
    (date(2026, 7, 20), 6, date(2027, 1, 20)),
    (date(2026, 8, 31), 6, date(2027, 2, 28)),  # month end clamps
    (date(2023, 8, 31), 6, date(2024, 2, 29)),  # into a leap February
    (date(2024, 2, 29), 6, date(2024, 8, 29)),
    (date(2024, 2, 29), 60, date(2029, 2, 28)),  # leap day anniversary clamps
    (date(2024, 2, 29), 48, date(2028, 2, 29)),
])
def test_add_months(join: date, n: int, expected: date) -> None:
    assert Dv.add_months(join, n) == expected


def test_tenure_matches_csv_for_every_employee() -> None:
    facts = F.facts_from_csv()
    for e in EMPLOYEES:
        assert Dv.tenure_years(facts[e["employee_id"]].join_date, AS_OF) == float(e["tenure_years"]), e["employee_id"]


def test_tenure_rounding_rule() -> None:
    # round(days / 365.25, 1): 1734 days -> 4.7 (a /365 divisor would give 4.8)
    assert Dv.tenure_years(date(2022, 1, 10), AS_OF) == 4.7
    assert Dv.tenure_years(AS_OF, AS_OF) == 0.0


def test_completed_service_years_on_anniversaries() -> None:
    assert Dv.completed_years(date(2021, 6, 14), date(2026, 6, 13)) == 4
    assert Dv.completed_years(date(2021, 6, 14), date(2026, 6, 14)) == 5
    assert Dv.completed_years(date(2024, 2, 29), date(2029, 2, 27)) == 4
    assert Dv.completed_years(date(2024, 2, 29), date(2029, 2, 28)) == 5
    assert Dv.completed_years(date(2024, 2, 29), date(2028, 2, 28)) == 3
    assert Dv.completed_years(date(2024, 2, 29), date(2028, 2, 29)) == 4


@pytest.mark.parametrize("status,cat", [
    ("Active", "active"),
    ("On maternity leave (1 Sep 2026 to 28 Feb 2027)", "on_leave"),
    ("Serving notice (resigned 15 Sep 2026, last working day 14 Nov 2026)", "serving_notice"),
])
def test_status_category(status: str, cat: str) -> None:
    assert Dv.status_category(status) == cat


def test_status_category_unknown_fails_loudly() -> None:
    with pytest.raises(ValueError):
        Dv.status_category("Seconded")


@pytest.mark.parametrize("city,tier", [
    ("Hyderabad", 1), ("Bengaluru", 1), ("Bangalore", 1), ("Mumbai", 1), ("pune", 1), ("New Delhi", 1),
    ("Gurugram", 1), ("Chennai", 1), ("Kolkata", 1), ("Visakhapatnam", 2), ("Austin", 2), ("Mysuru", 2),
])
def test_city_tier(city: str, tier: int) -> None:
    assert Dv.city_tier(city) == tier


def test_tier1_list_matches_policy_text() -> None:
    text = (DATA_DIR / "policies/departmental").glob("ZEN-DPL-FIN-01_*.md").__next__().read_text(encoding="utf-8")
    line = re.search(r"Tier-1 cities: (.+?)\.", text).group(1)
    named = [c.strip() for c in re.split(r",| and ", line) if c.strip()]
    assert set(named) == set(Dv.TIER1_CITIES)


# ---------------------------------------------------------------- rule file integrity

def _policy_sections(policy_id: str) -> set[int]:
    path = next(DATA_DIR.glob(f"policies/*/{policy_id}_*.md"))
    return {int(m) for m in re.findall(r"^## (\d+)\. ", path.read_text(encoding="utf-8"), re.M)}


def test_every_case_cites_an_existing_section_and_policy_rule() -> None:
    known = {r["rule_id"]: r["policy_id"] for r in read_csv("policy_rules")}
    for rule_id, rule in load_rules().items():
        assert rule.cases, rule_id
        for case in rule.cases:
            assert case.sources, (rule_id, case.id)
            for s in case.sources:
                assert s.section in _policy_sections(s.policy), (rule_id, case.id, s)
                if s.rule_id:
                    assert known[s.rule_id] == s.policy, (rule_id, case.id, s)


def test_notice_thresholds_agree_with_bands_csv() -> None:
    for b in read_csv("bands"):
        f = F.EmployeeFacts("X", "X", b["band"], date(2020, 1, 1), "Active", "D03", "BKE", None, "L01", "Hyderabad")
        r = evaluate("NOTICE_PERIOD", "X", "X", AS_OF, facts={"X": f})
        assert r.value["notice_period_days"] == int(b["notice_period_days"]), b["band"]


def test_induction_threshold_matches_derived_constant() -> None:
    case = next(c for c in load_rules()["WORK_MODE"].cases if c.id == "INDUCTION")
    assert case.when == {"attr": "days_since_join", "op": "<=", "value": Dv.INDUCTION_DAYS}


def test_unknown_rule_and_params_fail_loudly() -> None:
    with pytest.raises(KeyError):
        evaluate("NOPE", ARJUN, ARJUN, AS_OF)
    with pytest.raises(ValueError):
        evaluate("HOTEL_CAP", ARJUN, ARJUN, AS_OF, {"town": "Pune"})


# ---------------------------------------------------------------- answer key: every employee

def test_work_mode_notice_match_csv_for_every_employee() -> None:
    for e in EMPLOYEES:
        eid = e["employee_id"]
        wm = evaluate("WORK_MODE", eid, HR_HEAD, AS_OF)
        assert wm.status == "ok" and wm.value["work_mode"] == e["work_mode"], (eid, wm.value)
        n = evaluate("NOTICE_PERIOD", eid, HR_HEAD, AS_OF)
        assert n.value["notice_period_days"] == int(e["notice_period_days"]), eid


def test_pooja_on_leave_and_tarun_full_office() -> None:
    p = evaluate("WORK_MODE", POOJA, HR_HEAD, AS_OF)
    assert (p.fired_case, p.value["work_mode"]) == ("ON_LEAVE", "On leave")
    t = evaluate("WORK_MODE", TARUN, HR_HEAD, AS_OF)
    assert (t.fired_case, t.value["work_mode"]) == ("SERVING_NOTICE", "Full WFO (all working days)")
    assert ("ZEN-POL-002", 4) in _policy_cites(t) and "R004" in t.policy_rules


# ---------------------------------------------------------------- date boundaries

def test_arjun_flips_from_induction_to_hybrid() -> None:
    before = evaluate("WORK_MODE", ARJUN, ARJUN, date(2026, 10, 18))
    after = evaluate("WORK_MODE", ARJUN, ARJUN, date(2026, 10, 19))
    assert (before.fired_case, before.value["work_mode"]) == ("INDUCTION", "Full WFO (all working days)")
    assert before.inputs["days_since_join"] == 90 and "18 Oct 2026" in before.value["reason"]
    assert (after.fired_case, after.value["work_mode"]) == ("STANDARD", "Hybrid (3 days WFO)")
    assert after.inputs["days_since_join"] == 91
    assert "R003" in before.policy_rules and "R001" in after.policy_rules


def test_induction_end_rule() -> None:
    r = evaluate("INDUCTION_END", ARJUN, ARJUN, AS_OF)
    assert r.value == {"induction_end": "2026-10-18", "in_induction": True}
    assert evaluate("INDUCTION_END", ARJUN, ARJUN, date(2026, 10, 19)).value["in_induction"] is False


def test_probation_boundary_drives_notice_period() -> None:
    assert evaluate("PROBATION_END", ARJUN, ARJUN, AS_OF).value == {"probation_end": "2027-01-20", "in_probation": True}
    on = evaluate("NOTICE_PERIOD", ARJUN, ARJUN, date(2027, 1, 20))
    off = evaluate("NOTICE_PERIOD", ARJUN, ARJUN, date(2027, 1, 21))
    assert (on.fired_case, on.value["notice_period_days"]) == ("IN_PROBATION", 30)
    assert off.value["notice_period_days"] == 60 and "R019" in off.policy_rules


def _synthetic(join: date, band: str = "Z3", dept: str = "BKE", city: str = "Hyderabad") -> dict[str, F.EmployeeFacts]:
    return {"X": F.EmployeeFacts("X", "Test Person", band, join, "Active", "D03", dept, "ZV-1013", "L01", city)}


def test_month_end_probation_boundary() -> None:
    facts = _synthetic(date(2026, 8, 31))
    assert evaluate("PROBATION_END", "X", "X", date(2027, 2, 28), facts=facts).value == \
        {"probation_end": "2027-02-28", "in_probation": True}
    assert evaluate("PROBATION_END", "X", "X", date(2027, 3, 1), facts=facts).value["in_probation"] is False
    assert evaluate("NOTICE_PERIOD", "X", "X", date(2027, 3, 1), facts=facts).value["notice_period_days"] == 60


def test_leap_day_joiner() -> None:
    facts = _synthetic(date(2024, 2, 29))
    assert evaluate("INDUCTION_END", "X", "X", date(2024, 5, 29), facts=facts).value == \
        {"induction_end": "2024-05-29", "in_induction": True}
    assert evaluate("PROBATION_END", "X", "X", date(2024, 8, 30), facts=facts).value == \
        {"probation_end": "2024-08-29", "in_probation": False}
    assert evaluate("SABBATICAL_ELIGIBILITY", "X", "X", date(2029, 2, 27), facts=facts).value["eligible"] is False
    assert evaluate("SABBATICAL_ELIGIBILITY", "X", "X", date(2029, 2, 28), facts=facts).value["eligible"] is True


def test_before_joining_is_not_applicable() -> None:
    r = evaluate("WORK_MODE", ARJUN, ARJUN, date(2026, 7, 19))
    assert r.status == "not_applicable" and r.value == {}


# ---------------------------------------------------------------- other rules

def test_sabbatical() -> None:
    yes = evaluate("SABBATICAL_ELIGIBILITY", SNEHA, SNEHA, AS_OF)
    assert yes.value["eligible"] is True and yes.inputs["tenure_years"] == 5.3
    assert ("ZEN-POL-003", 7) in _policy_cites(yes) and "R020" in yes.policy_rules
    assert evaluate("SABBATICAL_ELIGIBILITY", "ZV-1036", "ZV-1036", AS_OF).value["eligible"] is False
    # Sneha's 5th anniversary is 2026-06-14
    assert evaluate("SABBATICAL_ELIGIBILITY", SNEHA, SNEHA, date(2026, 6, 13)).value["eligible"] is False
    assert evaluate("SABBATICAL_ELIGIBILITY", SNEHA, SNEHA, date(2026, 6, 14)).value["eligible"] is True


@pytest.mark.parametrize("band,city,cap,tier", [
    ("Z1", "Mumbai", 4500, 1), ("Z3", "Visakhapatnam", 3500, 2), ("Z4", "Chennai", 7000, 1),
    ("Z6", "Visakhapatnam", 5500, 2), ("Z7", "Pune", 11000, 1), ("Z8", "Austin", 8500, 2),
])
def test_hotel_cap(band: str, city: str, cap: int, tier: int) -> None:
    facts = _synthetic(date(2020, 1, 1), band=band)
    r = evaluate("HOTEL_CAP", "X", "X", AS_OF, {"city": city}, facts=facts)
    assert r.value["cap_inr"] == cap and r.inputs["city_tier"] == tier and r.inputs["band"] == band
    assert ("ZEN-DPL-FIN-01", 4) in _policy_cites(r)


def test_hotel_cap_needs_city() -> None:
    r = evaluate("HOTEL_CAP", ARJUN, ARJUN, AS_OF)
    assert r.status == "insufficient_input" and "city_tier" in " ".join(r.assumptions)


def test_leave_entitlements_and_el_after_probation() -> None:
    a = evaluate("LEAVE_ENTITLEMENTS", ARJUN, ARJUN, AS_OF)
    assert a.value["earned_leave_available"] is False
    assert a.value["entitlements"]["Casual Leave (CL)"] == "8 days"
    s = evaluate("LEAVE_ENTITLEMENTS", SNEHA, SNEHA, AS_OF)
    assert s.value["earned_leave_available"] is True
    assert {"R013", "R014", "R015"} <= set(s.policy_rules)


def test_hypothetical_support_specialist_works_on_site() -> None:
    r = evaluate("WORK_MODE", None, HR_HEAD, AS_OF, {"department_code": "CSC"})
    assert r.status == "ok" and r.fired_case == "CARE_CENTRE_ROSTER"
    assert r.value["work_mode"] == "On-site shift roster"
    assert {("ZEN-POL-002", 4), ("ZEN-DPL-CSC-01", 3)} <= _policy_cites(r)
    assert r.assumptions  # status and join date were unknown, so earlier cases were skipped


def test_graph_citations_name_the_facts_used() -> None:
    r = evaluate("WORK_MODE", "ZV-1021", HR_HEAD, AS_OF)
    paths = {c.path for c in r.citations if isinstance(c, GraphCitation)}
    assert "ZV-1021 -WORKS_IN-> D10" in paths
    assert {n.id for n in r.subgraph.nodes} >= {"ZV-1021", "D10"}


# ---------------------------------------------------------------- access (rule 6)

@pytest.mark.parametrize("asker", [ARJUN, NAVEEN, HR_HEAD, HR_BP, HR_EXEC])
@pytest.mark.parametrize("rule", ["WORK_MODE", "NOTICE_PERIOD"])
def test_restricted_rules_allow_self_direct_manager_and_hr(rule: str, asker: str) -> None:
    assert evaluate(rule, ARJUN, asker, AS_OF).status == "ok"


@pytest.mark.parametrize("asker", [DIVYA, KARTHIK, SNEHA, CEO, "ZV-9999"])
@pytest.mark.parametrize("rule", ["WORK_MODE", "NOTICE_PERIOD"])
def test_restricted_rules_deny_skip_level_head_peer_ceo_unknown(rule: str, asker: str) -> None:
    r = evaluate(rule, ARJUN, asker, AS_OF)
    assert r.status == "restricted"
    assert r.value == {} and r.inputs == {} and r.citations == [] and r.assumptions == []
    assert r.fired_case is None and r.policy_rules == [] and r.subgraph.nodes == []


@pytest.mark.parametrize("rule", ["WORK_MODE", "NOTICE_PERIOD"])
def test_refusal_does_not_reveal_special_status(rule: str) -> None:
    """A peer's refusal looks the same for Tarun (notice), Pooja (leave) and an ordinary colleague."""
    peer = "ZV-1037"  # Sai Teja Chowdary: no reporting or HR link to any of the three
    dumps = []
    for subject in (TARUN, POOJA, SNEHA):
        d = evaluate(rule, subject, peer, AS_OF).model_dump()
        assert d.pop("subject_id") == subject
        dumps.append(d)
    assert dumps[0] == dumps[1] == dumps[2]


def test_public_rules_need_no_access() -> None:
    assert evaluate("SABBATICAL_ELIGIBILITY", SNEHA, "ZV-1037", AS_OF).status == "ok"
    assert evaluate("HOTEL_CAP", SNEHA, "ZV-1037", AS_OF, {"city": "Pune"}).status == "ok"


# ---------------------------------------------------------------- people rules (Neo4j)

def _people(r) -> dict[str, str | None]:
    return {role: (p["employee_id"] if p else None) for role, p in r.value["people"].items()}


@pytest.mark.neo4j
def test_graph_facts_equal_csv_facts(driver) -> None:
    assert F.facts_from_graph(driver) == F.facts_from_csv()


@pytest.mark.neo4j
def test_termination_approval_by_band(driver) -> None:
    d = evaluate("TERMINATION_APPROVAL", DIVYA, HR_HEAD, AS_OF, driver=driver)  # Z5
    assert d.fired_case == "Z5_AND_ABOVE"
    assert _people(d) == {"recommends": KARTHIK, "approves": HR_HEAD, "final_approval": CEO}
    assert "R024" in d.policy_rules and ("ZEN-POL-004", 7) in _policy_cites(d)
    assert any(isinstance(c, GraphCitation) and c.path.startswith(f"{DIVYA} -REPORTS_TO->") for c in d.citations)
    s = evaluate("TERMINATION_APPROVAL", SNEHA, HR_HEAD, AS_OF, driver=driver)  # Z3
    assert s.fired_case == "BELOW_Z5" and _people(s) == {"recommends": KARTHIK, "approves": HR_HEAD}


@pytest.mark.neo4j
def test_termination_notes_when_subject_holds_a_role(driver) -> None:
    r = evaluate("TERMINATION_APPROVAL", KARTHIK, HR_HEAD, AS_OF, driver=driver)
    assert any("recommends" in a for a in r.assumptions)


@pytest.mark.neo4j
@pytest.mark.parametrize("amount,case,role,who", [
    (25_000, "UP_TO_25K", "approver", NAVEEN),
    (25_001, "UP_TO_1L", "approver", KARTHIK),
    (100_000, "UP_TO_1L", "approver", KARTHIK),
    (100_001, "ABOVE_1L", "approver", "ZV-1008"),
])
def test_expense_approver_by_amount(driver, amount: int, case: str, role: str, who: str) -> None:
    r = evaluate("EXPENSE_APPROVER", ARJUN, ARJUN, AS_OF, {"amount": amount}, driver=driver)
    assert r.fired_case == case and _people(r)[role] == who
    assert "R044" in r.policy_rules and ("ZEN-DPL-FIN-01", 3) in _policy_cites(r)


@pytest.mark.neo4j
def test_expense_international_and_ceo_own_travel(driver) -> None:
    r = evaluate("EXPENSE_APPROVER", ARJUN, ARJUN, AS_OF, {"amount": 5000, "international": True}, driver=driver)
    assert r.fired_case == "INTERNATIONAL" and _people(r) == {"approver": CEO, "budget": "ZV-1008"}
    c = evaluate("EXPENSE_APPROVER", CEO, CEO, AS_OF, {"amount": 5000, "international": True}, driver=driver)
    assert c.fired_case == "CEO_OWN_TRAVEL" and _people(c) == {"approver": "ZV-1008"}


def test_people_rules_need_a_driver() -> None:
    with pytest.raises(ValueError):
        evaluate("TERMINATION_APPROVAL", DIVYA, HR_HEAD, AS_OF)
