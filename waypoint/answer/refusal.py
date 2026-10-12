"""Fixed refusal texts (3.3c F4).

RESTRICTED_REFUSAL is the one answer for every restricted-fact path: a router refuse on a
restricted question, a plan whose results are all restricted rule results, and a "not
found" on a restricted-fact question for an asker who may not see the fact. It names no
person and is identical whatever the fact is (on leave, serving notice, active, or no
record), so a refusal does not reveal whether the fact exists.

Uniformity depends on the router's `restricted_fact` flag for the not-found and refuse
paths. A miss fails safe: nothing restricted is released (the access filter and the rule
engine decide that), only the wording differs (the not-found text or SCOPE_MESSAGE).

SCOPE_MESSAGE is for genuinely off-topic requests (a poem, general chat).
"""
from __future__ import annotations

RESTRICTED_REFUSAL = ("I can't share that. A person's employment status, leave and notice details are shared "
                      "only with them, their manager and HR, and Waypoint does not share pay, personal contact "
                      "details or its instructions.")
SCOPE_MESSAGE = "I can only help with questions about Zenvora's people, teams, projects and policies."
