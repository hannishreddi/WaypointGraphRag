"""3.3c router-v3 few-shots: disjoint from the safety set (also near-paraphrases), people
and departments real, restricted_fact examples present. Dev texts come through
`load_questions("dev")` (rule 2); the safety set is our own eval/safety.csv."""
from __future__ import annotations

import re

import pytest
from neo4j import Driver

from waypoint.eval.safety import load_safety
from waypoint.graph import templates as T
from waypoint.retrieval import router_examples as X
from waypoint.retrieval.linking import link_mentions
from waypoint.retrieval.plan import RouterOutput
from waypoint.retrieval.router import few_shots
from waypoint.rules.facts import facts_from_csv

FACTS = facts_from_csv()
SAFETY = load_safety()
MAX_JACCARD = 0.5
NGRAM = 4


def _norm(text: str) -> list[str]:
    """Lower-case tokens; every employee full name, unique first name and id -> <person>."""
    t = text.lower()
    for f in sorted(FACTS.values(), key=lambda f: -len(f.name)):
        t = re.sub(rf"\b({re.escape(f.name.lower())}|{re.escape(f.employee_id.lower())})\b", " person ", t)
    for f in FACTS.values():
        t = re.sub(rf"\b{re.escape(f.name.split()[0].lower())}\b", " person ", t)
    return re.findall(r"[a-z0-9]+", t)


def _ngrams(toks: list[str], n: int = NGRAM) -> set[tuple[str, ...]]:
    return {tuple(toks[i:i + n]) for i in range(len(toks) - n + 1)}


def _ids(ex: dict) -> set[str]:
    out = set(ex["entities"])
    for path in (ex["plan"], (ex.get("alternative") or {}).get("plan") or []):
        for step in path:
            out |= {v for v in step["args"].values() if isinstance(v, str)}
    return out


# The 3.3c restricted-fact few-shots (added after the safety set existed).
NEW_3_3C = {q for q, ex in X.SYNTHETIC_EXAMPLES if ex.get("restricted_fact") and ex["intent"] != "refuse"}
# Few-shots from 2.4 that share a generic 4-gram with a public control (not a paraphrase,
# Jaccard <= 0.5): Q087 "Who heads the department that ..." vs S30. Listed in docs/safety.md.
KNOWN_NGRAM = {("Q087", "S30")}


def test_few_shots_are_disjoint_from_the_safety_set() -> None:
    """Every few-shot: normalised token Jaccard <= 0.5 against every safety row. The new
    3.3c examples also share no 4-gram with any safety row."""
    dev_ids = {q: qid for qid, q in ((qid, q) for qid, (q, _, _) in zip(X.DEV_EXAMPLES, few_shots()))}
    worst = (0.0, "", "")
    for question, _, _ in few_shots():
        a = _norm(question)
        for q in SAFETY:
            b = _norm(q.question)
            jac = len(set(a) & set(b)) / len(set(a) | set(b))
            worst = max(worst, (jac, question, q.id))
            assert jac <= MAX_JACCARD, (question, q.id, round(jac, 2))
            shared = _ngrams(a) & _ngrams(b)
            if question in NEW_3_3C:
                assert not shared, (question, q.id, shared)
            elif shared:
                assert (dev_ids.get(question), q.id) in KNOWN_NGRAM, (question, q.id, shared)
    print(f"highest token overlap {worst[0]:.2f}: {worst[1]!r} vs {worst[2]}")
    assert len(NEW_3_3C) == 6


def test_synthetic_people_are_not_in_the_safety_set() -> None:
    used = {q.asker_id for q in SAFETY} | {q.subject_id for q in SAFETY if q.subject_id}
    text = " ".join(q.question for q in SAFETY)
    for question, ex in X.SYNTHETIC_EXAMPLES:
        people = {i for i in _ids(ex) if i in FACTS} | {m.id for m in link_mentions(question).matches
                                                        if m.label == "Employee"}
        for eid in people:
            assert eid not in used and FACTS[eid].name not in text, (question, eid)


def test_restricted_fact_examples() -> None:
    flagged = [q for q, ex in X.SYNTHETIC_EXAMPLES if ex.get("restricted_fact")]
    assert len(flagged) >= 5
    ops = {s["op"] for _, ex in X.SYNTHETIC_EXAMPLES for s in ex["plan"]}
    assert "EMPLOYMENT_STATUS" in ops
    for question, _, ex in few_shots():
        out = RouterOutput.model_validate(ex, context={"links": link_mentions(question)})
        if any(s.op == "EMPLOYMENT_STATUS" for s in out.plan):
            assert out.restricted_fact, question


def _initials(title: str) -> str:
    return "".join(w[0] for w in re.findall(r"[A-Z][a-z]+", title))


@pytest.mark.neo4j
def test_example_people_and_departments_exist_in_the_graph(driver: Driver) -> None:
    """Every person or department a few-shot names or uses is linked in its question and
    exists in the graph under that name (a person may be named by title: "the CFO")."""
    for question, _, ex in few_shots():
        links = link_mentions(question)
        surface = {m.id: m.surface for m in links.matches}
        people = {m.id for m in links.matches if m.label == "Employee"} | {i for i in _ids(ex) if i in FACTS}
        for eid in people:
            assert eid in surface, (question, eid, "not linked in the question")
            rows = T.employee_card(driver, eid).rows
            assert rows, (question, eid)
            name, title = rows[0]["name"], rows[0]["title"] or ""
            s = surface[eid]
            assert name.lower() in question.lower() or s.lower() in title.lower() or s == _initials(title)                 or s in title, (question, eid, name, title, s)
        depts = {m.id for m in links.matches if m.label == "Department"} |             {i for i in _ids(ex) if re.fullmatch(r"D\d{2}", i)}
        for d in depts:
            assert T.headcount(driver, d).rows, (question, d)
    finance = next(q for q, _ in X.SYNTHETIC_EXAMPLES if "Finance" in q)
    assert any(m.label == "Department" for m in link_mentions(finance).matches), finance
