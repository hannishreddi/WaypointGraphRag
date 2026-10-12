"""Few-shot examples for the router prompt (PLAN 2.4, rule 2).

Two separate sets:
- DEV_EXAMPLES: dev-split question ids only (a test checks they are all in dev). The
  question text is loaded from the dev split at prompt time, never copied here. These
  questions are scored in the routing eval too, so the report also gives accuracy on the
  dev questions that are not few-shots.
- SYNTHETIC_EXAMPLES: written by hand for what no dev question covers (overview,
  who_to_ask, refuse, an unresolved id, "my" questions, a low-confidence alternative).
  They are not eval questions and must not be reused as the 3.3 safety questions.
"""
from __future__ import annotations

from typing import Any

Example = dict[str, Any]  # a RouterOutput as JSON


def _out(intent: str, plan: list[Example], *, entities: list[str] = (), needs_identity: bool = False,  # type: ignore[assignment]
         confidence: float = 0.95, alternative: Example | None = None, restricted_fact: bool = False) -> Example:
    return {"intent": intent, "entities": list(entities), "needs_identity": needs_identity,
            "confidence": confidence, "plan": plan, "alternative": alternative, "restricted_fact": restricted_fact}


def _s(op: str, **args: Any) -> Example:
    return {"op": op, "args": args}


DEV_EXAMPLES: dict[str, Example] = {
    "Q002": _out("fact_list_count", [_s("manager", employee_id="ZV-1004")], entities=["ZV-1004"]),
    "Q047": _out("fact_list_count", [_s("headcount", department_id="D05")], entities=["D05"]),
    "Q087": _out("fact_list_count", [_s("manager", employee_id="ZV-1014"),
                                     _s("employee_card", employee_id="$1.employee_id"),
                                     _s("department_head", department_id="$2.department_id")],
                 entities=["ZV-1014"]),
    "Q122": _out("fact_list_count", [_s("project_team", project_id="PJ03", location_id="L02")],
                 entities=["PJ03", "L02"]),
    "Q133": _out("fact_list_count", [_s("previous_employer", org_id="ORG002")], entities=["ORG002"]),
    "Q153": _out("fact_list_count", [_s("skill_holders", skill_id="SK079")], entities=["SK079"]),
    "Q193": _out("personal_rule", [_s("HOTEL_CAP", subject="ZV-1009", city="Pune")], entities=["ZV-1009"]),
    "Q210": _out("personal_rule", [_s("WORK_MODE", subject="asker")], needs_identity=True, restricted_fact=True),
    "Q235": _out("policy_text", [_s("text_search", query="customer support SLA targets", doc_type="policy")],
                 confidence=0.9),
    "Q239": _out("fact_list_count", [_s("policy_references", policy_id="ZEN-POL-004", direction="in")],
                 entities=["ZEN-POL-004"]),
    "Q247": _out("personal_rule", [_s("WORK_MODE", subject=None, department_code="CSC")], entities=["D10"],
                 confidence=0.8,
                 alternative={"intent": "policy_text", "plan": [
                     _s("text_search", query="customer support work from home", doc_type="policy")]}),
}

ASKER = "ZV-1006"  # synthetic examples are asked by the eval's default asker
SYNTHETIC_EXAMPLES: list[tuple[str, Example]] = [
    ("Give me a tour of the Data & AI department.",
     _out("overview", [_s("department_head", department_id="D05"), _s("headcount", department_id="D05"),
                       _s("text_search", query="Data & AI department mission and work",
                          doc_type="department", entity_id="D05")], entities=["D05"], confidence=0.9)),
    ("Tell me about Project Sentinel.",
     _out("overview", [_s("project_leadership", entity_id="PJ04"), _s("project_departments", project_id="PJ04"),
                       _s("text_search", query="Project Sentinel goals and status", doc_type="project",
                          entity_id="PJ04")], entities=["PJ04"], confidence=0.9)),
    ("Who could help me with Kafka on Project Atlas?",
     _out("who_to_ask", [_s("skill_holders", skill_id="SK079"), _s("project_team", project_id="PJ01")],
          entities=["SK079", "PJ01"], confidence=0.85)),
    ("Who is my manager?",
     _out("fact_list_count", [_s("manager", employee_id="asker")], needs_identity=True)),
    ("Who owns ZEN-POL-099?",  # unresolved id: no step, downstream says there is no such policy
     _out("fact_list_count", [], confidence=0.9)),
    ("What is the home address of the CFO?",
     _out("refuse", [], entities=["ZV-1008"], restricted_fact=True)),
    ("Write me a poem about cricket.",
     _out("refuse", [])),
    ("How does onboarding work for me?",
     _out("policy_text", [_s("text_search", query="new joiner onboarding and induction", doc_type="company")],
          needs_identity=True, confidence=0.55,
          alternative={"intent": "personal_rule", "plan": [_s("INDUCTION_END", subject="asker")]})),
    # 3.3c F2/F3: restricted facts (people chosen outside eval/safety.csv, wordings checked
    # against it by tests/test_router_examples_v3.py)
    ("Is Keerthi Nair still employed with us, or has she moved on?",
     _out("personal_rule", [_s("EMPLOYMENT_STATUS", subject="ZV-1022")], entities=["ZV-1022"],
          restricted_fact=True)),
    ("What standing does HR list for Nikhil Joshi at the moment?",
     _out("personal_rule", [_s("EMPLOYMENT_STATUS", subject="ZV-1026")], entities=["ZV-1026"],
          restricted_fact=True)),
    ("On what date am I due back from my leave?",
     _out("personal_rule", [_s("EMPLOYMENT_STATUS", subject="asker")], needs_identity=True,
          restricted_fact=True)),
    ("How many days' notice must I serve, and which day is my final one at Zenvora?",
     _out("personal_rule", [_s("NOTICE_PERIOD", subject="asker"), _s("EMPLOYMENT_STATUS", subject="asker")],
          needs_identity=True, restricted_fact=True)),
    ("Who is handling Zaid Ansari's tickets while he is out?",
     _out("policy_text", [_s("text_search", query="who handles the work while out", doc_type="profile",
                             entity_id="ZV-1040")], entities=["ZV-1040"], confidence=0.9, restricted_fact=True)),
    ("Which members of the Finance team are currently away on leave?",
     _out("fact_list_count", [_s("text_search", query="Finance team members currently on leave",
                                 doc_type="profile")], entities=["D02"], confidence=0.85,
          restricted_fact=True)),
]
