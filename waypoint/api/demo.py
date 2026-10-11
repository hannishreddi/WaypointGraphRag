"""The four 3.2 demo moments against a running server (`make serve` or scripts/serve.ps1).

    python -m waypoint.api.demo [--base-url http://127.0.0.1:8000]

Prints answer, route, citations, subgraph size and whether the server's answer cache served
it, then PASS/FAIL checks on the evidence (not on wording). Never sends ?fresh=1, so a
re-run is served from `.cache/answers/` and makes no LLM calls. Exit code 1 if a check fails.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from waypoint.rules.facts import facts_from_csv

ARJUN, POOJA, HR, MEERA, DIVYA = "ZV-1042", "ZV-1031", "ZV-1006", "ZV-1002", "ZV-1004"
PEER = "ZV-1020"  # not Pooja, not her manager, not HR (checked in tests/test_demo.py)
MEERA_REPORTS = {"ZV-1017", "ZV-1007", "ZV-1010", "ZV-1003", "ZV-1012", "ZV-1005"}

Resp = dict[str, Any]
Check = Callable[[Resp], tuple[bool, str]]


@dataclass
class Ask:
    moment: str
    question: str
    asker_id: str
    as_of: str = "2026-10-10"
    checks: list[Check] = field(default_factory=list)


def edges(r: Resp) -> set[tuple[str, str, str]]:
    return {(e["source"], e["type"], e["target"]) for e in r["subgraph"]["edges"]}


def cites_section(policy: str, section: int) -> Check:
    def check(r: Resp) -> tuple[bool, str]:
        ok = any(c["type"] == "policy" and c["id"] == policy and c["section"] == section for c in r["citations"])
        return ok, f"cites {policy} §{section}"
    return check


def rule_edge(subject: str, section_id: str) -> Check:
    def check(r: Resp) -> tuple[bool, str]:
        e = next((e for e in r["subgraph"]["edges"]
                  if (e["source"], e["type"], e["target"]) == (subject, "RULE_CASE", section_id)), None)
        return bool(e and e["derived"]), f"derived RULE_CASE {subject} -> {section_id}"
    return check


def no_restricted(subject: str) -> Check:
    status = facts_from_csv().get(subject).status

    def check(r: Resp) -> tuple[bool, str]:
        blob = json.dumps(r)
        ok = status not in blob and "::restricted" not in blob and "ZEN-POL-003#3" not in blob
        return ok, f"no restricted fact about {subject} (status, restricted chunk, leave section)"
    return check


def answers_leave(r: Resp) -> tuple[bool, str]:
    a = r["answer"].lower()
    refused = any(s in a for s in ("cannot share", "can't share", "can't find", "can't confirm", "can't help"))
    return "leave" in a and not refused, "answer states the leave (no refusal)"


def refused(r: Resp) -> tuple[bool, str]:
    a = r["answer"].lower()
    return any(s in a for s in ("cannot share", "can't share", "can't find")), "answer refuses or finds nothing"


def states_no_leave(r: Resp) -> tuple[bool, str]:
    a = r["answer"].lower()
    said = [w for w in ("on leave", "maternity", "on_leave", "returns on", "is away") if w in a]
    return not said, "answer states no leave status" + (f" (found {said})" if said else "")


def starts_with(word: str) -> Check:
    def check(r: Resp) -> tuple[bool, str]:
        return r["answer"].startswith(word), f"answer starts with {word!r}"
    return check


def names(*people: str) -> Check:
    def check(r: Resp) -> tuple[bool, str]:
        missing = [p for p in people if p not in r["answer"]]
        return not missing, f"answer names {', '.join(people)}" + (f" (missing {missing})" if missing else "")
    return check


def cited_paths_drawable(r: Resp) -> tuple[bool, str]:
    es, n = edges(r), 0
    for c in r["citations"]:
        if c["type"] == "graph":
            parts = c["path"].split(" ")
            for i in range(0, len(parts) - 2, 2):
                if (parts[i], parts[i + 1][1:-2], parts[i + 2]) not in es:
                    return False, f"cited path edge missing from subgraph: {c['path']}"
                n += 1
    return n > 0, f"{n} cited graph edge(s), all in the subgraph (highlighted)"


def has_edges(want: set[tuple[str, str, str]], what: str) -> Check:
    def check(r: Resp) -> tuple[bool, str]:
        missing = want - edges(r)
        return not missing, what + (f" (missing {sorted(missing)})" if missing else "")
    return check


def moments() -> list[Ask]:
    q1 = "Do I need to come to the office every day?"
    q2, q2t = "Is Pooja Agarwal on leave?", "What does Pooja Agarwal's profile say about leave?"
    return [
        Ask("1 Arjun, induction", q1, ARJUN, "2026-10-10",
            [starts_with("Yes"), cites_section("ZEN-POL-002", 4), rule_edge(ARJUN, "ZEN-POL-002#4")]),
        Ask("1 Arjun, last induction day", q1, ARJUN, "2026-10-18",
            [starts_with("Yes"), cites_section("ZEN-POL-002", 4), rule_edge(ARJUN, "ZEN-POL-002#4")]),
        Ask("1 Arjun, hybrid", q1, ARJUN, "2026-10-19",
            [starts_with("No"), cites_section("ZEN-POL-002", 3), rule_edge(ARJUN, "ZEN-POL-002#3")]),
        Ask("2 peer asks about Pooja (rule)", q2, PEER, checks=[no_restricted(POOJA), refused]),
        # Text path: public profile text may answer (e.g. "the Leave Policy applies"); rule 6 only
        # forbids the leave itself, so the check is "states no leave status", not "refuses" (3.3a).
        Ask("2 peer asks about Pooja (text)", q2t, PEER, checks=[no_restricted(POOJA), states_no_leave]),
        Ask("2 HR asks about Pooja (rule)", q2, HR, checks=[answers_leave]),
        Ask("2 HR asks about Pooja (text)", q2t, HR, checks=[answers_leave]),
        Ask("3 Meera's reports", "Who reports to Meera?", ARJUN,
            checks=[has_edges({(r, "REPORTS_TO", MEERA) for r in MEERA_REPORTS}, "6 REPORTS_TO edges to Meera"),
                    cited_paths_drawable]),
        Ask("4 terminating Divya", "Who approves terminating Divya?", HR,
            # approves: HR head; final approval (Z5+): CEO. The department head (Karthik Naidu)
            # recommends, which the question does not ask; see docs/demo.md.
            checks=[names("Lakshmi Prasanna Varma", "Arvind Kulkarni"),
                    cites_section("ZEN-POL-004", 7), rule_edge(DIVYA, "ZEN-POL-004#7"),
                    has_edges({(DIVYA, "IN_BAND", "Z5"), ("ZV-1003", "HEADS", "D03"), (HR, "HEADS", "D01")},
                              "band, department head and HR head edges"),
                    cited_paths_drawable]),
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = ap.parse_args(argv)
    failed = 0
    with httpx.Client(base_url=args.base_url, timeout=600) as http:
        for a in moments():
            r = http.post("/ask", json={"question": a.question, "asker_id": a.asker_id, "as_of": a.as_of})
            print(f"\n== {a.moment}: {a.question!r} as {a.asker_id}, as of {a.as_of}")
            if r.status_code != 200:
                print(f"   HTTP {r.status_code}: {r.text[:300]}")
                failed += 1
                continue
            body = r.json()
            sg = body["subgraph"]
            print(f"   answer: {body['answer']}")
            print(f"   route: {body['route']}  confidence: {body['confidence']}  cached: {body['cached']}  "
                  f"tokens: {body['usage']['input_tokens']}/{body['usage']['output_tokens']}")
            cites = [c.get("path") or f"{c['id']}" + (f" §{c['section']}" if c.get("section") else "")
                     for c in body["citations"]]
            print(f"   citations: {cites}")
            print(f"   subgraph: {len(sg['nodes'])} nodes, {len(sg['edges'])} edges "
                  f"({sum(e['derived'] for e in sg['edges'])} derived)")
            for check in a.checks:
                ok, what = check(body)
                failed += not ok
                print(f"   {'PASS' if ok else 'FAIL'} {what}")
    print(f"\n{'all checks passed' if not failed else f'{failed} check(s) failed'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    raise SystemExit(main())
