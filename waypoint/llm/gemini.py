"""Gemini API client over plain httpx (no Google SDK). Free tier.

    POST /v1beta/models/{model}:generateContent   (key in the x-goog-api-key header)
    POST /v1beta/models/{model}:countTokens        GET /v1beta/models/{model}

Quota handling (429 RESOURCE_EXHAUSTED):
  - per-day quota (a QuotaFailure quotaId containing "PerDay")  -> DailyQuotaExceeded,
    never retried; the eval runner stops cleanly and resumes from its checkpoint.
  - per-minute quota -> halve this model's rpm, wait max(RetryInfo/Retry-After, 65 s)
    so every minute window has cleared, retry. A per-minute 429 on a request that
    started >= 60 s after the previous one means the request alone exceeds the
    per-minute quota (e.g. tokens/min) -> QuotaTooSmall, no retry loop.
5xx and transport errors are retried with exponential backoff; other 4xx raise.
Safety blocks (promptFeedback.blockReason, or a blocking finishReason) raise LLMError.
"""
from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from waypoint.config import get_settings
from waypoint.llm.client import Completion, DailyQuotaExceeded, LLMError, QuotaTooSmall
from waypoint.llm.ratelimit import RateLimiter

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
BLOCKING_FINISH = {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "LANGUAGE", "OTHER"}
MINUTE_WAIT_S = 65.0
_DELAY = re.compile(r"^(\d+(?:\.\d+)?)s$")


@dataclass(frozen=True)
class QuotaInfo:
    daily: bool
    retry_after_s: float | None
    quota_ids: tuple[str, ...]
    quota_value: str | None
    message: str


def parse_quota_error(resp: httpx.Response) -> QuotaInfo:
    try:
        err = resp.json().get("error", {})
    except ValueError:
        err = {}
    ids: list[str] = []
    value: str | None = None
    delay: float | None = None
    for d in err.get("details") or []:
        kind = str(d.get("@type", ""))
        if kind.endswith("QuotaFailure"):
            for v in d.get("violations") or []:
                ids.append(str(v.get("quotaId") or v.get("quotaMetric") or ""))
                value = value or (str(v["quotaValue"]) if v.get("quotaValue") is not None else None)
        elif kind.endswith("RetryInfo"):
            m = _DELAY.match(str(d.get("retryDelay", "")))
            delay = float(m.group(1)) if m else None
    if delay is None and resp.headers.get("retry-after", "").replace(".", "", 1).isdigit():
        delay = float(resp.headers["retry-after"])
    message = str(err.get("message", resp.text[:300]))
    daily = any("perday" in i.lower() for i in ids) or (
        not ids and re.search(r"per[ _-]?day|daily", message, re.IGNORECASE) is not None)
    return QuotaInfo(daily, delay, tuple(ids), value, message)


class GeminiClient:
    def __init__(self, api_key: str, *, rpm: float = 5.0, timeout_s: float = 300.0,
                 thinking_level: str = "minimal", temperature: float = 0.0, max_retries: int = 4,
                 transport: httpx.BaseTransport | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self._http = httpx.Client(base_url=BASE_URL, timeout=timeout_s, transport=transport,
                                  headers={"x-goog-api-key": api_key})
        self.rpm, self.thinking_level, self.temperature = rpm, thinking_level, temperature
        self.max_retries = max_retries
        self._clock, self._sleep = clock, sleep
        self._limiters: dict[str, RateLimiter] = {}
        self.calls: dict[str, int] = {}  # generateContent HTTP requests per model, retries included
        self.rate_limited: dict[str, int] = {}  # 429s per model
        self.quota_wait_s = 0.0  # seconds slept after per-minute 429s

    @classmethod
    def from_settings(cls) -> GeminiClient:
        s = get_settings()
        if s.gemini_api_key is None:
            raise LLMError("GEMINI_API_KEY is not set (LLM_PROVIDER=gemini)")
        return cls(s.gemini_api_key.get_secret_value(), rpm=s.llm_rpm, timeout_s=s.llm_timeout_s,
                   thinking_level=s.gemini_thinking_level)

    def limiter(self, model: str) -> RateLimiter:
        if model not in self._limiters:
            self._limiters[model] = RateLimiter(self.rpm, clock=self._clock, sleep=self._sleep)
        return self._limiters[model]

    def total_requests(self) -> int:
        return sum(self.calls.values())

    def total_wait_s(self) -> float:
        """Client-side waiting so far: rate-limiter pacing plus sleeps after per-minute 429s
        (not 5xx back-off). The eval reports latency with and without it."""
        return self.quota_wait_s + sum(lim.waited_s for lim in self._limiters.values())

    def _body(self, system: str, prompt: str, max_tokens: int, json_mode: bool) -> dict[str, Any]:
        config: dict[str, Any] = {"temperature": self.temperature, "maxOutputTokens": max_tokens}
        if json_mode:
            config["responseMimeType"] = "application/json"
        if self.thinking_level:
            config["thinkingConfig"] = {"thinkingLevel": self.thinking_level}
        return {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": config}

    def complete(self, *, model: str, system: str, prompt: str, max_tokens: int,
                 json_mode: bool = False) -> Completion:
        body = self._body(system, prompt, max_tokens, json_mode)
        limiter = self.limiter(model)
        failures = 0
        while True:
            idle = limiter.wait()
            self.calls[model] = self.calls.get(model, 0) + 1
            try:
                resp = self._http.post(f"/models/{model}:generateContent", json=body)
            except httpx.TransportError as exc:
                failures = self._backoff(model, failures, f"{type(exc).__name__}: {exc}")
                continue
            if resp.status_code == 200:
                return _completion(model, resp.json())
            if resp.status_code == 429:
                self.rate_limited[model] = self.rate_limited.get(model, 0) + 1
                q = parse_quota_error(resp)
                if q.daily:
                    raise DailyQuotaExceeded(
                        f"{model}: daily free-tier quota exhausted ({', '.join(q.quota_ids) or q.message}"
                        f"{f', limit {q.quota_value}' if q.quota_value else ''}). It resets at midnight "
                        "Pacific time; re-run the same command then to resume.")
                if idle is not None and idle >= 60.0:
                    raise QuotaTooSmall(
                        f"{model}: per-minute 429 on a request sent after {idle:.0f} s idle, so this one "
                        f"request exceeds the per-minute quota ({', '.join(q.quota_ids) or q.message}"
                        f"{f', limit {q.quota_value}' if q.quota_value else ''}). Not retrying.")
                failures += 1
                if failures > self.max_retries:
                    raise LLMError(f"{model}: still rate limited after {self.max_retries} retries: {q.message}")
                limiter.slow_down()
                wait = max(q.retry_after_s or 0.0, MINUTE_WAIT_S)
                self.quota_wait_s += wait
                self._sleep(wait)
                continue
            if resp.status_code >= 500:
                failures = self._backoff(model, failures, f"HTTP {resp.status_code}: {resp.text[:200]}")
                continue
            raise LLMError(f"{model}: HTTP {resp.status_code}: {resp.text[:500]}")

    def _backoff(self, model: str, failures: int, why: str) -> int:
        failures += 1
        if failures > self.max_retries:
            raise LLMError(f"{model}: giving up after {self.max_retries} retries: {why}")
        self._sleep(5.0 * 2 ** (failures - 1))
        return failures

    def count_tokens(self, *, model: str, system: str, prompt: str) -> int:
        """Exact prompt size via countTokens (does not generate)."""
        body = self._body(system, prompt, 1, False)
        req = {"generateContentRequest": {"model": f"models/{model}", **{
            k: body[k] for k in ("systemInstruction", "contents")}}}
        resp = self._http.post(f"/models/{model}:countTokens", json=req)
        if resp.status_code != 200:
            raise LLMError(f"countTokens {model}: HTTP {resp.status_code}: {resp.text[:300]}")
        return int(resp.json()["totalTokens"])

    def model_info(self, model: str) -> dict[str, Any]:
        """Model metadata, including inputTokenLimit (context window) and outputTokenLimit."""
        resp = self._http.get(f"/models/{model}")
        if resp.status_code != 200:
            raise LLMError(f"models.get {model}: HTTP {resp.status_code}: {resp.text[:300]}")
        data: dict[str, Any] = resp.json()
        return data


def _completion(model: str, data: dict[str, Any]) -> Completion:
    block = (data.get("promptFeedback") or {}).get("blockReason")
    if block:
        raise LLMError(f"{model} blocked the prompt (blockReason={block})")
    candidates = data.get("candidates") or []
    if not candidates:
        raise LLMError(f"{model} returned no candidates")
    cand = candidates[0]
    finish = cand.get("finishReason")
    if finish in BLOCKING_FINISH:
        raise LLMError(f"{model} stopped with finishReason={finish}")
    parts = (cand.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    if not text.strip():
        raise LLMError(f"{model} returned no text (finishReason={finish})")
    u = data.get("usageMetadata") or {}
    return Completion(text, int(u.get("promptTokenCount", 0)),
                      int(u.get("candidatesTokenCount", 0)) + int(u.get("thoughtsTokenCount", 0)),
                      int(u.get("cachedContentTokenCount", 0)))
