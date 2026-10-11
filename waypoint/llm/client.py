"""Minimal LLM client interface and the Anthropic implementation. Tests use a fake."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import anthropic

from waypoint.config import get_settings


class LLMError(RuntimeError):
    """The model refused or returned no text."""


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int
    output_tokens: int


class LLMClient(Protocol):
    def complete(self, *, model: str, system: str, prompt: str, max_tokens: int) -> Completion: ...


class AnthropicClient:
    def __init__(self, api_key: str | None = None) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)

    @classmethod
    def from_settings(cls) -> AnthropicClient:
        key = get_settings().anthropic_api_key
        return cls(key.get_secret_value() if key else None)

    def complete(self, *, model: str, system: str, prompt: str, max_tokens: int) -> Completion:
        msg = self._client.messages.create(
            model=model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        if msg.stop_reason == "refusal":
            raise LLMError(f"{model} refused (request id {msg._request_id})")
        text = "".join(b.text for b in msg.content if b.type == "text")
        if not text.strip():
            raise LLMError(f"{model} returned no text (stop_reason={msg.stop_reason})")
        return Completion(text, msg.usage.input_tokens, msg.usage.output_tokens)
