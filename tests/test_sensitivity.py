"""Sensitivity labels (PLAN 1.3, CLAUDE.md rule 6): restricted = a specific person's
employment status, leave or notice period. General policy text stays public."""
from __future__ import annotations

import pytest

from tests import csv_expect as X
from waypoint.retrieval.chunking import Corpus, build_corpus
from waypoint.retrieval.sensitivity import restricted_subject

POOJA, TARUN = "ZV-1031", "ZV-1033"

NON_RECORD_RESTRICTED = {
    "profile:ZV-1031::about::restricted": POOJA,
    "profile:ZV-1033::about::restricted": TARUN,
    "company:03_company_timeline::intro::restricted": TARUN,
    "company:06_all_hands_notes_2026-09-04::people::restricted": POOJA,
}


@pytest.fixture(scope="module")
def corpus() -> Corpus:
    return build_corpus()


def restricted(corpus: Corpus) -> dict[str, str | None]:
    return {c.chunk_id: c.subject_id for c in corpus.chunks if c.sensitivity == "restricted"}


def test_exactly_46_restricted_chunks(corpus: Corpus) -> None:
    got = restricted(corpus)
    records = {f"profile:{r['employee_id']}::employee-record::restricted": r["employee_id"]
               for r in X.rows("employees")}
    assert got == records | NON_RECORD_RESTRICTED
    assert len(got) == 46


def test_every_restricted_chunk_has_subject_and_public_ones_none(corpus: Corpus) -> None:
    ids = {r["employee_id"] for r in X.rows("employees")}
    for c in corpus.chunks:
        assert c.sensitivity in ("public", "restricted")
        if c.sensitivity == "restricted":
            assert c.subject_id in ids and c.part == "restricted", c.chunk_id
        else:
            assert c.subject_id is None, c.chunk_id


def test_pooja_on_leave_text_is_restricted_with_her_subject_id(corpus: Corpus) -> None:
    hers = {c.chunk_id: c for c in corpus.chunks if c.subject_id == POOJA}
    assert set(hers) == {
        "profile:ZV-1031::employee-record::restricted",
        "profile:ZV-1031::about::restricted",
        "company:06_all_hands_notes_2026-09-04::people::restricted",
    }
    assert all("maternity leave" in c.body for c in hers.values())
    for c in corpus.chunks:
        if c.sensitivity == "public":
            assert "Currently on maternity leave" not in c.text
            assert "started maternity leave" not in c.text
            assert "On maternity leave (1 Sep 2026" not in c.text


def test_tarun_serving_notice_is_restricted(corpus: Corpus) -> None:
    for c in corpus.chunks:
        if c.sensitivity == "public":
            assert "Tarun Mehta resigns" not in c.text and "Resigned on 15 September" not in c.text


def test_leave_policy_chunks_are_public(corpus: Corpus) -> None:
    leave = [c for c in corpus.chunks if c.doc_id == "ZEN-POL-003"]
    assert leave and all(c.sensitivity == "public" and c.subject_id is None for c in leave)
    assert any("Maternity leave" in c.body for c in leave)
    assert any("Notice period after probation" in c.body for c in leave)


def test_all_policy_chunks_are_public(corpus: Corpus) -> None:
    assert all(c.sensitivity == "public" for c in corpus.chunks if c.doc_type == "policy")


def test_general_text_about_notice_and_leave_stays_public(corpus: Corpus) -> None:
    for needle in ("I resigned. Do I still get remote days?", "How long is maternity leave?",
                   "still in his 90-day induction"):  # Arjun's induction stays public
        hits = [c for c in corpus.chunks if needle in c.body]
        assert hits and all(c.sensitivity == "public" for c in hits), needle


def test_public_remainder_of_split_section_survives(corpus: Corpus) -> None:
    (people,) = [c for c in corpus.chunks
                 if c.chunk_id == "company:06_all_hands_notes_2026-09-04::people::0"]
    assert "Arjun Menon" in people.body and "Pooja" not in people.body
    (record,) = [c for c in corpus.chunks if c.chunk_id == "profile:ZV-1031::employee-record::0"]
    assert "Employee ID: ZV-1031." in record.body
    assert "Employment status" not in record.body and "Notice period" not in record.body


NAMES = {"Pooja Agarwal": POOJA, "Harsha Vardhan": "ZV-1041", "Tarun Mehta": TARUN}


@pytest.mark.parametrize(("line", "doc_subject", "record", "expected"), [
    ("Pooja Agarwal (Data Engineer) started maternity leave on 1 September. Harsha Vardhan reports",
     None, False, POOJA),
    ("Event: Tarun Mehta resigns; Details: serves a 60-day notice period.", None, False, TARUN),
    ("Resigned on 15 September 2026.", TARUN, False, TARUN),
    ("No. Employees serving notice work from office on all working days.", None, False, None),
    ("Notice period: 60 days.", POOJA, True, POOJA),
    ("Notice period: 60 days.", POOJA, False, None),
    ("Band: Z3 (Engineer / Specialist / Executive).", POOJA, True, None),
    ("Harsha Vardhan approved the Leave Policy.", None, False, None),
])
def test_restricted_subject_rule(line: str, doc_subject: str | None, record: bool,
                                 expected: str | None) -> None:
    assert restricted_subject(line, doc_subject=doc_subject, in_record=record, names=NAMES) == expected
