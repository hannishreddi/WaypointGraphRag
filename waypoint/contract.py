"""Response contract (docs/DESIGN.md) and the System interface every answerer implements."""
from __future__ import annotations

from datetime import date
from typing import Annotated, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class PolicyCitation(BaseModel):
    type: Literal["policy"] = "policy"
    id: str
    section: int | str | None = None


class GraphCitation(BaseModel):
    type: Literal["graph"] = "graph"
    path: str  # e.g. "ZV-1042 -WORKS_IN-> D03"


class ChunkCitation(BaseModel):
    type: Literal["chunk"] = "chunk"
    id: str  # chunk id "<doc_id>::<section>::<part>"


Citation = Annotated[PolicyCitation | GraphCitation | ChunkCitation, Field(discriminator="type")]


class SubgraphNode(BaseModel):
    id: str
    label: str
    name: str = ""


class SubgraphEdge(BaseModel):
    source: str
    target: str
    type: str


class Subgraph(BaseModel):
    nodes: list[SubgraphNode] = []
    edges: list[SubgraphEdge] = []


class Usage(BaseModel):
    input_tokens: int = 0  # all prompt tokens, cached ones included
    output_tokens: int = 0  # visible output plus thinking tokens
    cached_input_tokens: int = 0  # part of input_tokens served from the provider's cache

    def __add__(self, other: Usage) -> Usage:
        return Usage(input_tokens=self.input_tokens + other.input_tokens,
                     output_tokens=self.output_tokens + other.output_tokens,
                     cached_input_tokens=self.cached_input_tokens + other.cached_input_tokens)


class Response(BaseModel):
    answer: str
    route: str
    as_of: date
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    citations: list[Citation] = []
    subgraph: Subgraph = Subgraph()
    usage: Usage = Usage()  # LLM tokens spent producing this answer
    latency_ms: float = 0.0


@runtime_checkable
class System(Protocol):
    name: str

    def answer(self, question: str, asker_id: str, as_of: date) -> Response: ...
