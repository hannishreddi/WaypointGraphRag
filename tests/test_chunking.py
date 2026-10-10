"""Chunking rules (PLAN 1.3). Expected counts come from the Markdown and CSV files."""
from __future__ import annotations

from collections import Counter

import pytest

from tests import csv_expect as X
from tests import doc_expect as D
from waypoint.retrieval.chunking import Corpus, build_corpus, slug, table_to_sentences


@pytest.fixture(scope="module")
def corpus() -> Corpus:
    return build_corpus()


def by_doc(corpus: Corpus, doc_id: str) -> list:
    return [c for c in corpus.chunks if c.doc_id == doc_id]


def test_chunk_ids_are_stable_and_unique(corpus: Corpus) -> None:
    ids = [c.chunk_id for c in corpus.chunks]
    assert len(ids) == len(set(ids))
    build_corpus.cache_clear()
    assert [c.chunk_id for c in build_corpus().chunks] == ids


def test_document_count_per_type() -> None:
    corpus = build_corpus()
    expected = {
        "policy": len(D.policy_files()),
        "profile": len(D.md("employees/profiles/*.md")),
        "resume": len(D.md("employees/resumes_md/*.md")),
        "department": len(D.md("departments/*.md")),
        "project": len(D.md("projects/PJ*.md")),
        "product": len(D.md("projects/products/*.md")),
        "company": len(D.md("company/*.md")),
    }
    assert Counter(d.doc_type for d in corpus.docs) == expected
    assert {c.doc_id for c in corpus.chunks} == {d.doc_id for d in corpus.docs}


# ---------------------------------------------------------------- policies


def test_one_chunk_per_numbered_policy_section_plus_header(corpus: Corpus) -> None:
    for path in D.policy_files():
        pid = D.file_id(path)
        chunks = by_doc(corpus, pid)
        sections = sorted(c.section for c in chunks if c.section != "header")
        assert sections == sorted(f"s{n}" for n, _ in D.numbered_sections(path)), pid
        assert [c.section for c in chunks].count("header") == 1, pid


def test_policy_chunks_carry_id_title_version_effective_date(corpus: Corpus) -> None:
    meta = {r["policy_id"]: r for r in X.rows("policies")}
    policy_chunks = [c for c in corpus.chunks if c.doc_type == "policy"]
    assert policy_chunks
    for c in policy_chunks:
        m = meta[c.doc_id]
        assert c.text.startswith(
            f"{m['policy_id']} {m['title']} (version {m['version']}, effective {m['effective_date']})."
        ), c.chunk_id


def test_policy_sections_agree_with_markdown_and_csv(corpus: Corpus) -> None:
    from_md = {(D.file_id(p), n, h) for p in D.policy_files() for n, h in D.numbered_sections(p)}
    got = {(s.policy_id, s.section_no, s.heading) for s in corpus.sections}
    assert got == from_md
    assert len(corpus.sections) == sum(len(D.numbered_sections(p)) for p in D.policy_files())
    from_csv = {(r["policy_id"], int(r["section_no"]), r["heading"]) for r in X.rows("policy_sections")}
    assert from_csv <= got
    assert {s.section_id for s in corpus.sections} == {
        c.section_id for c in corpus.chunks if c.section_id}


def test_policy_table_rows_become_sentences(corpus: Corpus) -> None:
    (s3,) = [c for c in corpus.chunks if c.chunk_id == "ZEN-POL-003::s3::0"]
    rows = [ln for ln in s3.body.splitlines() if ln.startswith("Leave type: ")]
    assert len(rows) == 10
    assert "Leave type: Maternity leave; Entitlement: 26 weeks" in s3.body
    assert all("|" not in c.text for c in corpus.chunks)


def test_table_to_sentences() -> None:
    table = ["| A | B |", "|---|---|", "| x | y. |", "| z |  |"]
    assert table_to_sentences(table) == ["A: x; B: y.", "A: z."]
    assert table_to_sentences(["| Field | Value |", "|---|---|", "| Band | Z3 |"]) == ["Band: Z3."]


def test_table_of_contents_is_dropped(corpus: Corpus) -> None:
    assert not any("S.#:" in c.text or "Table of Contents" in c.text for c in corpus.chunks)


# ---------------------------------------------------------------- people


def test_profiles_chunked_by_heading(corpus: Corpus) -> None:
    paths = D.md("employees/profiles/*.md")
    assert len(paths) == X.n("employees")
    for path in paths:
        eid = D.file_id(path)
        got = {c.section for c in by_doc(corpus, f"profile:{eid}")}
        assert got == {slug(h) for h in D.headings(path)}, eid


def test_resumes_chunked_by_job(corpus: Corpus) -> None:
    for path in D.md("employees/resumes_md/*.md"):
        eid = D.file_id(path)
        sections = sorted(c.section for c in by_doc(corpus, f"resume:{eid}"))
        jobs = len(D.headings(path, level=3))
        assert sections == sorted(["summary"] + [f"job-{i}" for i in range(1, jobs + 1)]), eid


def test_people_chunks_prefixed_with_name_and_id(corpus: Corpus) -> None:
    name = {r["employee_id"]: r["full_name"] for r in X.rows("employees")}
    for c in corpus.chunks:
        if c.doc_type in ("profile", "resume"):
            eid = c.doc_id.split(":")[1]
            assert c.text.startswith(f"{name[eid]} ({eid})"), c.chunk_id


# ---------------------------------------------------------------- whole pages and company docs


@pytest.mark.parametrize(("doc_type", "pattern", "prefix"), [
    ("department", "departments/*.md", "dept"),
    ("project", "projects/PJ*.md", "project"),
    ("product", "projects/products/*.md", "product"),
])
def test_whole_page_docs_are_one_chunk(corpus: Corpus, doc_type: str, pattern: str, prefix: str) -> None:
    for path in D.md(pattern):
        chunks = by_doc(corpus, f"{prefix}:{D.file_id(path)}")
        assert [c.section for c in chunks] == ["page"], path.name


def test_company_docs_chunked_by_heading(corpus: Corpus) -> None:
    for path in D.md("company/*.md"):
        got = {c.section for c in by_doc(corpus, f"company:{path.stem}")}
        assert {slug(h) for h in D.headings(path)} <= got, path.name
        assert got <= {slug(h) for h in D.headings(path)} | {"intro"}, path.name


def test_boilerplate_and_markup_stripped(corpus: Corpus) -> None:
    for c in corpus.chunks:
        assert "Fictional document created" not in c.text, c.chunk_id
        assert "**" not in c.text and "*Resume:" not in c.text, c.chunk_id
        assert c.body.strip(), c.chunk_id
