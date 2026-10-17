"""LLM client interface and the factory. The only provider is Gemini (waypoint.llm.gemini).
Tests use fakes that implement `complete`.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol



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


@lru_cache
def get_llm_client() -> Any:
    """One shared client per process, so per-model rate limits cover answerer and judge."""
    from waypoint.llm.gemini import GeminiClient

    return GeminiClient.from_settings()
