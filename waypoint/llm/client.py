"""LLM client interface, the provider factory and the optional Anthropic implementation.

The provider comes from LLM_PROVIDER (gemini | anthropic); Gemini lives in
waypoint.llm.gemini. Tests use fakes that implement `complete`.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

from waypoint.config import get_settings


class LLMError(RuntimeError):
    """The model refused, was blocked, or returned no usable text."""


class QuotaStop(LLMError):
    """Retrying cannot help in this run; the eval runner stops cleanly and can resume later."""


class DailyQuotaExceeded(QuotaStop):
    """The provider's per-day quota is used up."""


class QuotaTooSmall(QuotaStop):
    """A single request is larger than the per-minute quota allows."""


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int  # all prompt tokens, cached ones included
    output_tokens: int  # visible output plus thinking
    cached_input_tokens: int = 0


class LLMClient(Protocol):
    def complete(self, *, model: str, system: str, prompt: str, max_tokens: int,
                 json_mode: bool = False) -> Completion: ...


class AnthropicClient:
    """Kept for LLM_PROVIDER=anthropic; needs the optional `anthropic` package."""

    def __init__(self, api_key: str | None = None) -> None:
        import anthropic  # optional dependency: pip install -e .[anthropic]

        self._client = anthropic.Anthropic(api_key=api_key)
        self.calls: dict[str, int] = {}

    @classmethod
    def from_settings(cls) -> AnthropicClient:
        key = get_settings().anthropic_api_key
        return cls(key.get_secret_value() if key else None)

    def total_requests(self) -> int:
        return sum(self.calls.values())

    def complete(self, *, model: str, system: str, prompt: str, max_tokens: int,
                 json_mode: bool = False) -> Completion:
        self.calls[model] = self.calls.get(model, 0) + 1
        msg: Any = self._client.messages.create(
            model=model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        if msg.stop_reason == "refusal":
            raise LLMError(f"{model} refused (request id {msg._request_id})")
        text = "".join(b.text for b in msg.content if b.type == "text")
        if not text.strip():
            raise LLMError(f"{model} returned no text (stop_reason={msg.stop_reason})")
        u = msg.usage
        read, write = u.cache_read_input_tokens or 0, u.cache_creation_input_tokens or 0
        return Completion(text, u.input_tokens + read + write, u.output_tokens, read)


@lru_cache
def get_llm_client() -> Any:
    """One shared client per process, so per-model rate limits cover answerer and judge."""
    if get_settings().llm_provider == "anthropic":
        return AnthropicClient.from_settings()
    from waypoint.llm.gemini import GeminiClient

    return GeminiClient.from_settings()
