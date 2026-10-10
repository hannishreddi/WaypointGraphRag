"""Cohere embeddings over httpx (POST /v2/embed), batched and cached on disk. PLAN 1.3.

Cohere allows at most 96 texts per call. Vectors are cached in
.cache/embeddings/<model>_<dim>.jsonl, keyed by sha256(model, dim, input_type, text),
and appended after every batch, so a re-run embeds only new or changed text.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Sequence
from pathlib import Path

import httpx

from waypoint.config import REPO_ROOT, get_settings

COHERE_EMBED_URL = "https://api.cohere.com/v2/embed"
BATCH_SIZE = 96
INPUT_TYPES = ("search_document", "search_query")
CACHE_DIR = REPO_ROOT / ".cache" / "embeddings"
RETRY_STATUS = {429, 500, 502, 503, 504}


class EmbedError(RuntimeError):
    """Cohere returned an error or a malformed response."""


class CacheMissError(RuntimeError):
    """Offline embedder asked for a text that is not cached."""


class Embedder:
    def __init__(self, *, model: str, dim: int, api_key: str | None = None,
                 cache_dir: Path = CACHE_DIR, client: httpx.Client | None = None,
                 offline: bool = False) -> None:
        self.model, self.dim, self.offline = model, dim, offline
        self._api_key = api_key
        self._client = client
        self.path = cache_dir / f"{re.sub(r'[^A-Za-z0-9.-]+', '-', model)}_{dim}.jsonl"
        self._cache = self._load()
        self.api_calls = 0

    @classmethod
    def from_settings(cls, *, offline: bool = False, **kw: object) -> Embedder:
        s = get_settings()
        key = s.cohere_api_key.get_secret_value() if s.cohere_api_key else None
        return cls(model=s.cohere_embed_model, dim=s.embed_dim, api_key=key, offline=offline, **kw)  # type: ignore[arg-type]

    def _key(self, text: str, input_type: str) -> str:
        raw = "\0".join((self.model, str(self.dim), input_type, text))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _load(self) -> dict[str, list[float]]:
        cache: dict[str, list[float]] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:  # a run killed mid-write leaves a partial line
                    continue
                cache[row["k"]] = row["v"]
        return cache

    def missing(self, texts: Sequence[str], input_type: str) -> list[str]:
        """Distinct texts that would need an API call, in input order."""
        return [t for t in dict.fromkeys(texts) if self._key(t, input_type) not in self._cache]

    def embed(self, texts: Sequence[str], input_type: str) -> list[list[float]]:
        if input_type not in INPUT_TYPES:
            raise ValueError(f"input_type must be one of {INPUT_TYPES}, got {input_type!r}")
        todo = self.missing(texts, input_type)
        if todo and self.offline:
            raise CacheMissError(f"{len(todo)} texts not cached for {self.model}/{self.dim}")
        for i in range(0, len(todo), BATCH_SIZE):
            self._embed_batch(todo[i:i + BATCH_SIZE], input_type)
        return [self._cache[self._key(t, input_type)] for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text], "search_query")[0]

    def _post(self, payload: dict[str, object]) -> httpx.Response:
        if not self._api_key:
            raise EmbedError("COHERE_API_KEY is not set")
        if self._client is None:
            self._client = httpx.Client(timeout=60)
        for attempt in range(3):
            self.api_calls += 1
            resp = self._client.post(COHERE_EMBED_URL, json=payload,
                                     headers={"Authorization": f"Bearer {self._api_key}"})
            if resp.status_code not in RETRY_STATUS or attempt == 2:
                return resp
            time.sleep(2 ** attempt * 5)
        raise AssertionError("unreachable")

    def _embed_batch(self, batch: list[str], input_type: str) -> None:
        resp = self._post({"model": self.model, "texts": batch, "input_type": input_type,
                           "embedding_types": ["float"], "output_dimension": self.dim,
                           "truncate": "NONE"})
        if resp.status_code != 200:
            raise EmbedError(f"Cohere embed failed: HTTP {resp.status_code}: {resp.text[:300]}")
        vectors = resp.json().get("embeddings", {}).get("float")
        if not isinstance(vectors, list) or len(vectors) != len(batch):
            raise EmbedError(f"expected {len(batch)} vectors, got {len(vectors or [])}")
        if any(len(v) != self.dim for v in vectors):
            raise EmbedError(f"expected dimension {self.dim}, got {sorted({len(v) for v in vectors})}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            for text, vector in zip(batch, vectors):
                key = self._key(text, input_type)
                self._cache[key] = vector
                f.write(json.dumps({"k": key, "v": vector}) + "\n")
