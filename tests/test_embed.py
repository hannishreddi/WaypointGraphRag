"""Cohere embedder over httpx (PLAN 1.3): batching, input_type, disk cache. No real API calls."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from waypoint.retrieval.embed import BATCH_SIZE, CacheMissError, Embedder, EmbedError

DIM = 8


class FakeCohere:
    """Records every request and answers like POST /v2/embed with float vectors."""

    def __init__(self, dim: int = DIM, count_delta: int = 0) -> None:
        self.requests: list[dict] = []
        self.headers: list[httpx.Headers] = []
        self.dim, self.count_delta = dim, count_delta

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        self.headers.append(request.headers)
        n = len(body["texts"]) + self.count_delta
        vectors = [[float(i)] * self.dim for i in range(n)]
        return httpx.Response(200, json={"id": "x", "embeddings": {"float": vectors}, "meta": {}})


def make(tmp_path: Path, fake: FakeCohere, **kw) -> Embedder:
    kw = {"model": "embed-test", "dim": DIM, "api_key": "k", "cache_dir": tmp_path} | kw
    return Embedder(client=httpx.Client(transport=httpx.MockTransport(fake)), **kw)


def texts(n: int) -> list[str]:
    return [f"text {i}" for i in range(n)]


def test_batches_stay_under_cohere_limit(tmp_path: Path) -> None:
    assert BATCH_SIZE == 96  # Cohere /v2/embed: at most 96 texts per call
    fake = FakeCohere()
    emb = make(tmp_path, fake)
    vectors = emb.embed(texts(200), "search_document")
    assert len(vectors) == 200 and all(len(v) == DIM for v in vectors)
    assert [len(r["texts"]) for r in fake.requests] == [96, 96, 8]
    assert emb.api_calls == 3
    r = fake.requests[0]
    assert r["model"] == "embed-test" and r["output_dimension"] == DIM
    assert r["input_type"] == "search_document" and r["embedding_types"] == ["float"]
    assert fake.headers[0]["authorization"] == "Bearer k"


def test_second_run_hits_disk_cache_with_zero_calls(tmp_path: Path) -> None:
    first = make(tmp_path, FakeCohere()).embed(texts(150), "search_document")
    fake = FakeCohere()
    again = make(tmp_path, fake)
    assert again.embed(texts(150), "search_document") == first
    assert again.api_calls == 0 and fake.requests == []


def test_only_missing_texts_are_sent_and_duplicates_once(tmp_path: Path) -> None:
    make(tmp_path, FakeCohere()).embed(texts(10), "search_document")
    fake = FakeCohere()
    make(tmp_path, fake).embed(texts(12) + ["text 11"], "search_document")
    assert [r["texts"] for r in fake.requests] == [["text 10", "text 11"]]


def test_cache_key_includes_model_dimension_and_input_type(tmp_path: Path) -> None:
    make(tmp_path, FakeCohere()).embed(["a"], "search_document")
    for kw, input_type in [({"model": "other"}, "search_document"),
                           ({"dim": 4}, "search_document"),
                           ({}, "search_query")]:
        fake = FakeCohere(dim=kw.get("dim", DIM))
        make(tmp_path, fake, **kw).embed(["a"], input_type)
        assert len(fake.requests) == 1, (kw, input_type)


def test_query_uses_search_query(tmp_path: Path) -> None:
    fake = FakeCohere()
    assert len(make(tmp_path, fake).embed_query("who is on leave?")) == DIM
    assert fake.requests[0]["input_type"] == "search_query"


@pytest.mark.parametrize("fake", [FakeCohere(count_delta=-1), FakeCohere(dim=DIM + 1)])
def test_wrong_vector_count_or_dimension_fails_loudly(tmp_path: Path, fake: FakeCohere) -> None:
    with pytest.raises(EmbedError):
        make(tmp_path, fake).embed(texts(3), "search_document")


def test_http_error_fails_loudly(tmp_path: Path) -> None:
    emb = Embedder(model="m", dim=DIM, api_key="k", cache_dir=tmp_path, client=httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(401, json={"message": "bad key"}))))
    with pytest.raises(EmbedError, match="401"):
        emb.embed(["a"], "search_document")


def test_offline_mode_never_calls_api(tmp_path: Path) -> None:
    fake = FakeCohere()
    emb = make(tmp_path, fake, offline=True)
    with pytest.raises(CacheMissError):
        emb.embed(["never embedded"], "search_document")
    assert fake.requests == []


def test_rejects_unknown_input_type(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        make(tmp_path, FakeCohere()).embed(["a"], "document")
