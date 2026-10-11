"""Structured LLM output (CLAUDE.md rule 4): ask for JSON, validate with Pydantic,
retry once with the validation error, then fail loudly.

The retry is a fresh single-turn prompt (original prompt + previous reply + error),
so no assistant turn is ever replayed. `context` is passed to Pydantic validators
(`model_validate_json(..., context=...)`), so checks that need run-time data, such as
the router's plan against the linked entities, get the same single retry.
"""
from __future__ import annotations

import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from waypoint.contract import Usage
from waypoint.llm.client import LLMClient

T = TypeVar("T", bound=BaseModel)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


class StructuredOutputError(RuntimeError):
    """The model's reply did not validate, even after one retry."""


def _json_text(text: str) -> str:
    text = _FENCE.sub("", text.strip())
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if 0 <= start < end else text


def complete_json(client: LLMClient, *, model: str, system: str, prompt: str, schema: type[T],
                  max_tokens: int = 2048, context: dict[str, Any] | None = None) -> tuple[T, Usage]:
    usage = Usage()
    attempt_prompt = prompt
    for attempt in range(2):
        c = client.complete(model=model, system=system, prompt=attempt_prompt, max_tokens=max_tokens,
                            json_mode=True)
        usage += Usage(input_tokens=c.input_tokens, output_tokens=c.output_tokens,
                       cached_input_tokens=c.cached_input_tokens)
        try:
            return schema.model_validate_json(_json_text(c.text), context=context), usage
        except ValidationError as exc:
            if attempt:
                raise StructuredOutputError(
                    f"{schema.__name__} invalid after 1 retry: {exc}\nlast reply: {c.text[:500]!r}") from exc
            attempt_prompt = (
                f"{prompt}\n\nYour previous reply was:\n<previous_reply>\n{c.text}\n</previous_reply>\n"
                f"It failed validation against the {schema.__name__} schema:\n{exc}\n"
                "Reply with only the corrected JSON object."
            )
    raise AssertionError("unreachable")
