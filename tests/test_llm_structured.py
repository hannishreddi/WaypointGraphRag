"""JSON output validated with Pydantic, one retry with the error, then fail loudly (rule 4)."""
from __future__ import annotations

import pytest
from pydantic import BaseModel

from waypoint.llm.client import Completion
from waypoint.llm.structured import StructuredOutputError, complete_json


class Out(BaseModel):
    verdict: str
    n: int


class ScriptedLLM:
    """Fake LLMClient: returns canned replies in order and records every prompt."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.calls: list[dict] = []

    def complete(self, *, model: str, system: str, prompt: str, max_tokens: int) -> Completion:
        self.calls.append({"model": model, "system": system, "prompt": prompt})
        return Completion(text=self.replies.pop(0), input_tokens=10, output_tokens=5)


def test_valid_first_time_with_code_fence() -> None:
    llm = ScriptedLLM('```json\n{"verdict": "ok", "n": 3}\n```')
    out, usage = complete_json(llm, model="m", system="s", prompt="p", schema=Out)
    assert out == Out(verdict="ok", n=3) and len(llm.calls) == 1
    assert (usage.input_tokens, usage.output_tokens) == (10, 5)


def test_retries_once_with_validation_error() -> None:
    llm = ScriptedLLM('{"verdict": "ok", "n": "many"}', '{"verdict": "ok", "n": 2}')
    out, usage = complete_json(llm, model="m", system="s", prompt="p", schema=Out)
    assert out.n == 2 and len(llm.calls) == 2
    retry = llm.calls[1]["prompt"]
    assert retry.startswith("p") and "n" in retry and "valid integer" in retry
    assert usage.input_tokens == 20


def test_fails_loudly_after_second_bad_reply() -> None:
    llm = ScriptedLLM("not json", '{"verdict": 1}')
    with pytest.raises(StructuredOutputError, match="after 1 retry"):
        complete_json(llm, model="m", system="s", prompt="p", schema=Out)
    assert len(llm.calls) == 2
