"""S1 / S3 naive baselines with a fake LLM and fake search; no real calls (PLAN 1.5)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from tests.test_llm_structured import ScriptedLLM
from waypoint.config import DATA_DIR
from waypoint.eval.baselines import (SYSTEM_PROMPT, S1VectorRAG, S3FullContext, build_prompt,
                                     corpus_files)
from waypoint.eval.questions import TEST_ENV

AS_OF = date(2026, 10, 10)
HITS = [{"chunk_id": "profile:ZV-1002::role::0", "text": "Meera Subramanian is CTO.", "score": 0.9},
        {"chunk_id": "dept:D03::page::0", "text": "Backend Engineering is headed by Karthik.", "score": 0.8}]


class FakeSearch:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, query: str, **kw: Any) -> list[dict[str, Any]]:
        self.calls.append((query, kw))
        return HITS


def reply(answer: str, *ids: str) -> str:
    return json.dumps({"answer": answer, "cited_ids": list(ids)})


def test_s1_naive_retrieval_and_citations() -> None:
    llm, search = ScriptedLLM(reply("Meera Subramanian", "profile:ZV-1002::role::0", "made-up::x::0",
                                    "profile:ZV-1002::role::0")), FakeSearch()
    r = S1VectorRAG(llm, "answer-model", search=search).answer("Who is the CTO?", "ZV-1042", AS_OF)
    assert search.calls == [("Who is the CTO?", {"k": 5, "include_restricted": True})]
    assert r.answer == "Meera Subramanian" and r.route == "vector_rag" and r.as_of == AS_OF
    assert [c.id for c in r.citations] == ["profile:ZV-1002::role::0"]  # unknown dropped, deduped
    assert (r.usage.input_tokens, r.usage.output_tokens) == (10, 5) and r.latency_ms >= 0
    call = llm.calls[0]
    assert call["model"] == "answer-model" and call["system"] == SYSTEM_PROMPT and call["json_mode"]
    prompt = call["prompt"]
    assert prompt.startswith("<context>") and prompt.endswith("Question: Who is the CTO?")
    assert "Asker: employee ZV-1042" in prompt and "As of: 2026-10-10" in prompt
    assert '<item id="dept:D03::page::0">' in prompt


def test_template_rules() -> None:
    low = SYSTEM_PROMPT.lower()
    assert "concise" in low and "exactly the entities or values" in low
    assert "cannot find the answer" in low and "rather than guess" in low


def test_s1_and_s3_share_the_template() -> None:
    a, b = ScriptedLLM(reply("x")), ScriptedLLM(reply("x"))
    S1VectorRAG(a, "m", search=FakeSearch()).answer("Q?", "ZV-1006", AS_OF)
    S3FullContext(b, "m", corpus=("<item id=\"d\">\nall docs\n</item>", ["d"])).answer("Q?", "ZV-1006", AS_OF)
    pa, pb = a.calls[0]["prompt"], b.calls[0]["prompt"]
    assert a.calls[0]["system"] == b.calls[0]["system"]
    tail = pa[pa.index("</context>"):]
    assert tail == pb[pb.index("</context>"):]
    assert build_prompt("CTX", "Q?", "ZV-1006", AS_OF).replace("CTX", "") == pa.replace(
        pa[len("<context>\n"):pa.index("\n</context>")], "")


def test_s3_cites_document_ids_and_is_dev_only(monkeypatch: pytest.MonkeyPatch) -> None:
    llm = ScriptedLLM(reply("Prakash Raman", "dept:D06", "nope"))
    s3 = S3FullContext(llm, "m", corpus=("ctx", ["dept:D06", "ZEN-POL-002"]))
    assert s3.dev_only and s3.name == "s3"
    r = s3.answer("Who heads QA?", "ZV-1006", AS_OF)
    assert [c.id for c in r.citations] == ["dept:D06"] and r.route == "full_context"
    monkeypatch.setenv(TEST_ENV, "1")
    with pytest.raises(RuntimeError, match="dev split only"):
        s3.answer("Who heads QA?", "ZV-1006", AS_OF)


def test_corpus_never_includes_eval_generator_data_or_readme(tmp_path: Path) -> None:
    keep = ["policies/company_wide/ZEN-POL-001_x.md", "employees/profiles/ZV-1001_a.md",
            "employees/resumes_md/ZV-1001_a.md", "departments/D00_x.md", "projects/products/PR01_x.md",
            "company/01_overview.md"]
    drop = ["eval/questions.md", "generator/notes.md", "data/schema.md", "README.md", "policies/README.md",
            "employees/eval/leak.md", "projects/generator/leak.md", "company/data/leak.md",
            "policies/pdf/ZEN-POL-001.pdf", "company/notes.txt"]
    for rel in keep + drop:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("x", encoding="utf-8")
    got = sorted(p.relative_to(tmp_path).as_posix() for p in corpus_files(tmp_path))
    assert got == sorted(keep)


def test_real_corpus_files() -> None:
    files = corpus_files(DATA_DIR)
    rels = [p.relative_to(DATA_DIR).as_posix() for p in files]
    assert len(files) == 134 and all(r.endswith(".md") for r in rels)
    assert not [r for r in rels if r.split("/")[0] in {"eval", "generator", "data"} or "readme" in r.lower()]
    assert {r.split("/")[0] for r in rels} == {"company", "departments", "employees", "policies", "projects"}
