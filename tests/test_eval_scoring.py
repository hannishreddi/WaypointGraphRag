"""Normaliser, scorer assignment and the exact / set-F1 scorers (PLAN 1.4)."""
from __future__ import annotations

from collections import Counter

import pytest

from waypoint.eval.entities import load_entities
from waypoint.eval.questions import Question, read_all_questions
from waypoint.eval.scorers import assign_scorer, normalise, score_answer

Q = {q.id: q for q in read_all_questions()}


@pytest.mark.parametrize("raw, expected", [
    ("  Arvind   KULKARNI. ", "arvind kulkarni"),
    ("Founder & Chief Executive Officer", "founder and chief executive officer"),
    ("18 Oct 2026", "2026-10-18"),
    ("until October 18, 2026", "until 2026-10-18"),
    ("on 2 May 2023", "on 2023-05-02"),
    ("2026-10-18", "2026-10-18"),
    ("INR 1,00,000", "inr 100000"),
    ("₹4,500", "inr 4500"),
    ("Rs. 4,500", "inr 4500"),
    ("31%", "31 percent"),
    ("two direct reports", "2 direct reports"),
    ("ZEN-POL-004", "zen pol 004"),
    ("11.1 years", "11.1 years"),
])
def test_normalise(raw: str, expected: str) -> None:
    assert normalise(raw) == expected


def test_scorer_assignment_counts() -> None:
    counts = Counter(assign_scorer(q).kind for q in Q.values())
    assert counts == {"exact": 92, "set_f1": 85, "judge": 74}


@pytest.mark.parametrize("qid, kind, keys", [
    ("Q037", "exact", ["2"]),
    ("Q001", "exact", ["Arvind Kulkarni"]),
    ("Q020", "exact", ["Manoj Thomas"]),  # nested parentheses in the gloss
    ("Q022", "exact", ["Founder & Chief Executive Officer", "Z8"]),
    ("Q033", "exact", ["Business Development Manager, US", "Z4"]),
    ("Q191", "exact", ["INR 4,500"]),
    ("Q060", "set_f1", None),
    ("Q106", "set_f1", None),  # department names contain parentheses
    ("Q239", "set_f1", None),  # policy ids with titles in parentheses
    ("Q123", "set_f1", None),  # single-name list answer
    ("Q172", "set_f1", None),
    ("Q201", "judge", None),  # ';' joins clauses, not entities
    ("Q205", "judge", None),
    ("Q103", "judge", None),
    ("Q208", "judge", None),
])
def test_assignment_examples(qid: str, kind: str, keys: list[str] | None) -> None:
    spec = assign_scorer(Q[qid])
    assert spec.kind == kind
    if keys is not None:
        assert spec.keys == keys


def score(qid: str, answer: str):  # noqa: ANN201 - test helper
    return score_answer(assign_scorer(Q[qid]), Q[qid], answer, load_entities())


def test_exact_name_in_sentence() -> None:
    r = score("Q001", "Meera Subramanian reports to Arvind Kulkarni, the Founder and CEO.")
    assert (r.kind, r.score) == ("exact", 1.0)  # Meera is excluded: she is named in the question
    assert score("Q001", "Meera Subramanian reports to Gaurav Malhotra.").score == 0.0


def test_exact_rambling_answer_goes_to_judge() -> None:
    r = score("Q001", "It could be Arvind Kulkarni, Ramesh Iyengar or Gaurav Malhotra.")
    assert r.kind == "judge" and r.score is None and "extra" in r.detail


def test_exact_number_title_band_and_money() -> None:
    assert score("Q037", "There are two employees in the Executive Office.").score == 1.0
    assert score("Q037", "There are 3 employees in the Executive Office.").score == 0.0
    assert score("Q022", "Arvind is Founder and Chief Executive Officer, band Z8.").score == 1.0
    assert score("Q022", "Arvind is Founder and Chief Executive Officer, band Z7.").score == 0.0
    assert score("Q191", "Arjun (Z2) can spend up to ₹4,500 a night in Mumbai.").score == 1.0


def test_set_f1() -> None:
    full = score("Q062", "Naveen Reddy and Sneha Hegde report to Divya Krishnamurthy.")
    assert (full.kind, full.score) == ("set_f1", 1.0)  # Divya is in the question, not a prediction
    half = score("Q062", "Only Naveen Reddy.")
    assert half.score == pytest.approx(2 * 1 * 0.5 / 1.5)
    extra = score("Q062", "Naveen Reddy, Sneha Hegde and Arjun Menon.")
    assert extra.score == pytest.approx(2 * (2 / 3) * 1 / (2 / 3 + 1))
    assert score("Q062", "I don't know.").score == 0.0


def test_set_f1_aliases_and_policy_ids() -> None:
    assert score("Q104", "Backend Engineering, DevOps & Cloud Infrastructure and Quality Assurance.").score == 1.0
    assert score("Q095", "Atlas, Sentinel and Ember.").score == 1.0
    ans = ("ZEN-DPL-FIN-01, ZEN-DPL-HR-01, ZEN-POL-001, ZEN-POL-002, ZEN-POL-003, "
           "ZEN-POL-005, ZEN-POL-006 and ZEN-POL-008 all cite ZEN-POL-004.")
    assert score("Q239", ans).score == 1.0


def test_judge_rows_are_not_scored_locally() -> None:
    r = score("Q208", "Three days a week.")
    assert r.kind == "judge" and r.score is None


def test_question_model_parses_sources() -> None:
    q: Question = Q["Q072"]
    assert q.hops == 2 and q.sources == ["ZV-1003", "ZV-1002"] and q.stratum == "org_structure|2"
