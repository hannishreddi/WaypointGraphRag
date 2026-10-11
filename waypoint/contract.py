"""Response contract (docs/DESIGN.md) and the System interface every answerer implements."""
from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal, Protocol, runtime_checkable

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
    # Rule evidence (3.2): Waypoint's reasoning about this node (decisive facts, fired case).
    # Public facts only: never status, leave or notice.
    detail: str = ""


class SubgraphEdge(BaseModel):
    source: str
    target: str
    type: str
    # Rule evidence (3.2): "decisive" = the fired case depends on it, "checked" = read to rule
    # out an earlier case; "" for template edges.
    role: Literal["", "decisive", "checked"] = ""
    # True for edges Waypoint infers (RULE_CASE subject -> policy section), not stored in the graph.
    derived: bool = False


class Subgraph(BaseModel):
    nodes: list[SubgraphNode] = []
    edges: list[SubgraphEdge] = []

    def merge(self, other: Subgraph) -> Subgraph:
        """Union by node id and (source, type, target); the first copy wins unless a later one
        carries rule evidence (detail, role) the first lacks."""
        nodes: dict[str, SubgraphNode] = {}
        for n in [*self.nodes, *other.nodes]:
            if n.id not in nodes or (n.detail and not nodes[n.id].detail):
                nodes[n.id] = n
        edges: dict[tuple[str, str, str], SubgraphEdge] = {}
        for e in [*self.edges, *other.edges]:
            k = (e.source, e.type, e.target)
            if k not in edges or (e.role and not edges[k].role):
                edges[k] = e
        return Subgraph(nodes=list(nodes.values()), edges=list(edges.values()))


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
    # Diagnostics for the eval (verifier outcome, router cache, ...). Not part of the
    # contract: excluded from model_dump / JSON, so the API returns exactly the fields above.
    trace: dict[str, Any] = Field(default_factory=dict, exclude=True)


@runtime_checkable
class System(Protocol):
    name: str

    def answer(self, question: str, asker_id: str, as_of: date) -> Response: ...
