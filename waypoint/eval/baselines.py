"""Naive baselines (PLAN 1.5). Deliberately no identity handling and no access control:
the asker id and as-of date are plain text in the prompt, and S1 retrieves restricted
chunks too, so the 3.3 safety questions are expected to show both leaking.

  S1 vector RAG    top 5 chunks from search_text(question, k=5, include_restricted=True)
  S3 full context  every Markdown file under policies/ employees/ departments/
                   projects/ company/ (no eval/, generator/, data/, README); dev split only

Both make one MODEL_ANSWER call with the same template; only the <context> block
differs. Context first, question last, so the provider can reuse the long prefix.
The model replies {"answer", "cited_ids"} (validated, rule 4); cited ids not in the
context are dropped.

    python -m waypoint.eval.baselines s3-info   # files, exact tokens, context window
"""
from __future__ import annotations

import argparse
import os
import time
from collections.abc import Callable, Sequence
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from waypoint.config import DATA_DIR, get_settings
from waypoint.contract import ChunkCitation, Response
from waypoint.eval.questions import TEST_ENV
from waypoint.llm.client import LLMClient, get_llm_client
from waypoint.llm.structured import complete_json

PROMPT_VERSION = "baseline-v1"
MAX_TOKENS = 2048
S3_DIRS = ("company", "departments", "employees", "policies", "projects")
S3_EXCLUDED_DIRS = {"eval", "generator", "data"}

SYSTEM_PROMPT = """You answer questions from employees of Zenvora, a company, using only the context provided.

- Answer concisely: name exactly the entities or values asked for (full names, numbers, dates, yes/no), with no preamble.
- Use only the context. If it does not contain the answer, reply "I cannot find the answer in the provided context." rather than guess.
- Put the ids of the context items you used in cited_ids.

Reply with only a JSON object: {"answer": "<your answer>", "cited_ids": ["<item id>", ...]}"""


class BaselineAnswer(BaseModel):
    answer: str
    cited_ids: list[str] = []


def context_item(item_id: str, text: str) -> str:
    return f'<item id="{item_id}">\n{text.strip()}\n</item>'


def build_prompt(context: str, question: str, asker_id: str, as_of: date) -> str:
    """The shared template. Context first; everything per-question comes after it."""
    return (f"<context>\n{context}\n</context>\n\n"
            f"Asker: employee {asker_id}\nAs of: {as_of.isoformat()}\n\nQuestion: {question}")


class _Baseline:
    name = ""
    route = ""
    dev_only = False

    def __init__(self, client: LLMClient, model: str) -> None:
        self.client, self.model = client, model
        self.config_id = f"{PROMPT_VERSION}:{model}"

    def _context(self, question: str) -> tuple[str, set[str]]:
        raise NotImplementedError

    def answer(self, question: str, asker_id: str, as_of: date) -> Response:
        t0 = time.perf_counter()
        context, known = self._context(question)
        out, usage = complete_json(self.client, model=self.model, system=SYSTEM_PROMPT,
                                   prompt=build_prompt(context, question, asker_id, as_of),
                                   schema=BaselineAnswer, max_tokens=MAX_TOKENS)
        cited = [ChunkCitation(id=i) for i in dict.fromkeys(out.cited_ids) if i in known]
        return Response(answer=out.answer, route=self.route, as_of=as_of, citations=cited, usage=usage,
                        latency_ms=(time.perf_counter() - t0) * 1000)


Search = Callable[..., list[dict[str, Any]]]


class S1VectorRAG(_Baseline):
    name, route = "s1", "vector_rag"
    K = 5
    INCLUDE_RESTRICTED = True  # naive: no access filter

    def __init__(self, client: LLMClient, model: str, search: Search | None = None) -> None:
        super().__init__(client, model)
        if search is None:
            from waypoint.retrieval.search import search_text as search
        self.search = search

    @classmethod
    def from_settings(cls) -> S1VectorRAG:
        return cls(get_llm_client(), get_settings().model_answer)

    def _context(self, question: str) -> tuple[str, set[str]]:
        hits = self.search(question, k=self.K, include_restricted=self.INCLUDE_RESTRICTED)
        return "\n\n".join(context_item(h["chunk_id"], h["text"]) for h in hits), {h["chunk_id"] for h in hits}


def corpus_files(root: Path = DATA_DIR) -> list[Path]:
    """The S3 corpus: Markdown under S3_DIRS, never eval/, generator/, data/ or a README."""
    files = []
    for d in S3_DIRS:
        for p in sorted((root / d).rglob("*.md")):
            rel = p.relative_to(root)
            if S3_EXCLUDED_DIRS & set(rel.parts[:-1]) or p.name.lower().startswith("readme"):
                continue
            files.append(p)
    return files


def _doc_ids() -> dict[str, str]:
    from waypoint.retrieval.chunking import build_corpus

    return {d.path: d.doc_id for d in build_corpus().docs}


def build_corpus_context(root: Path = DATA_DIR, doc_ids: dict[str, str] | None = None) -> tuple[str, list[str]]:
    """(context block, item ids). Items use the chunker's doc ids so sources.py maps them."""
    ids = doc_ids if doc_ids is not None else {}
    items, item_ids = [], []
    for p in corpus_files(root):
        rel = p.relative_to(root).as_posix()
        item_id = ids.get(rel, rel)
        items.append(context_item(item_id, p.read_text(encoding="utf-8")))
        item_ids.append(item_id)
    return "\n\n".join(items), item_ids


@cache
def _real_corpus() -> tuple[str, tuple[str, ...]]:
    context, ids = build_corpus_context(DATA_DIR, _doc_ids())
    return context, tuple(ids)


class S3FullContext(_Baseline):
    name, route = "s3", "full_context"
    dev_only = True  # about a whole corpus per question: dev split only (DESIGN.md)

    def __init__(self, client: LLMClient, model: str, corpus: tuple[str, Sequence[str]] | None = None) -> None:
        super().__init__(client, model)
        context, ids = corpus if corpus is not None else _real_corpus()
        self.corpus, self.ids = context, set(ids)

    @classmethod
    def from_settings(cls) -> S3FullContext:
        return cls(get_llm_client(), get_settings().model_answer)

    def answer(self, question: str, asker_id: str, as_of: date) -> Response:
        if os.environ.get(TEST_ENV) == "1":
            raise RuntimeError("S3 runs on the dev split only")
        return super().answer(question, asker_id, as_of)

    def _context(self, question: str) -> tuple[str, set[str]]:
        return self.corpus, self.ids


def s3_info() -> None:
    files = corpus_files()
    context, _ = _real_corpus()
    print(f"S3 corpus: {len(files)} files, {len(context):,} characters")
    for d in S3_DIRS:
        print(f"  {d:<12} {sum(f.relative_to(DATA_DIR).parts[0] == d for f in files):>3} files")
    s, client = get_settings(), get_llm_client()
    prompt = build_prompt(context, "Who heads Quality Assurance?", "ZV-1006", date(2026, 10, 10))
    tokens = client.count_tokens(model=s.model_answer, system=SYSTEM_PROMPT, prompt=prompt)
    info = client.model_info(s.model_answer)
    print(f"{s.model_answer}: one S3 request = {tokens:,} input tokens (countTokens); "
          f"context window {info.get('inputTokenLimit')}, output limit {info.get('outputTokenLimit')}")


def main(argv: Sequence[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Baseline utilities")
    p.add_argument("command", choices=["s3-info"])
    p.parse_args(argv)
    s3_info()


if __name__ == "__main__":
    main()
