"""Map each gold answer to a scorer and score an answer (PLAN 1.4).

Assignment, from the shape of `expected_answer` (first match wins):
1. integer only ("2")                                  -> exact, key = the number
2. every ';' item names a known entity of one type,
   with an optional trailing "(...)" ("Naveen Reddy; Sneha Hegde",
   "ZEN-POL-001 (Code of Conduct ...)"), or a single bare name
   ("Divya Krishnamurthy", no gloss)                    -> set_f1
3. "<title>, band Zn"                                  -> exact, keys = title and band
4. "<head> (<gloss>)", the gloss closing the answer, no sentence in the head
   ("Arvind Kulkarni (Founder & ...)", "60 days (band Z3)") -> exact, key = head
5. anything else (sentences, ';'-joined clauses)        -> judge

Exact match: every normalised key must appear as a whole-token span in the
normalised answer. When the key is an entity, the answer must also name no other
entity of that type (ignoring entities named in the question); if it does, the
row goes to the judge instead. Set-F1: predicted set = entities of the gold's type
named in the answer, minus entities named in the question that are not in gold.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from waypoint.eval.entities import Entities, load_entities
from waypoint.eval.normalise import contains, normalise
from waypoint.eval.questions import Question

__all__ = ["GoldSpec", "ScoreResult", "assign_scorer", "normalise", "score_answer"]

Kind = Literal["exact", "set_f1", "judge"]
_BAND = re.compile(r"^(.+), band (Z\d)$")
_HEAD_GLOSS = re.compile(r"^([^()]+?) \((.*)\)$")


@dataclass(frozen=True)
class GoldSpec:
    kind: Kind
    keys: list[str]
    entity_type: str | None = None
    gold_ids: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ScoreResult:
    kind: Kind  # "judge" means: not scored here, send to the LLM judge
    score: float | None
    detail: str = ""


def _closes_at_end(text: str, open_at: int) -> bool:
    """True when the "(" at `open_at` is closed by the last character."""
    depth = 0
    for i, ch in enumerate(text[open_at:], open_at):
        depth += {"(": 1, ")": -1}.get(ch, 0)
        if depth == 0:
            return i == len(text) - 1
    return False


def assign_scorer(q: Question, ents: Entities | None = None) -> GoldSpec:
    ents = ents or load_entities()
    gold = q.expected_answer.strip()
    if re.fullmatch(r"\d+", gold):
        return GoldSpec("exact", [gold])
    items = gold.split(";")
    resolved = [ents.resolve(item) for item in items] if len(items) > 1 else [ents.by_name.get(gold)]
    if all(resolved) and len({r[0] for r in resolved if r}) == 1:
        return GoldSpec("set_f1", [r[1] for r in resolved if r], resolved[0][0],  # type: ignore[index]
                        frozenset(r[1] for r in resolved if r))
    if m := _BAND.match(gold):
        return GoldSpec("exact", [m[1], m[2]])
    if (m := _HEAD_GLOSS.match(gold)) and "." not in m[1] and _closes_at_end(gold, len(m[1]) + 1):
        head = ents.resolve(m[1])
        if head:
            return GoldSpec("exact", [m[1]], head[0], frozenset({head[1]}))
        return GoldSpec("exact", [m[1]])
    return GoldSpec("judge", [])


def _f1(predicted: set[str], gold: frozenset[str]) -> float:
    hit = len(predicted & gold)
    if not hit:
        return 0.0
    p, r = hit / len(predicted), hit / len(gold)
    return 2 * p * r / (p + r)


def score_answer(spec: GoldSpec, q: Question, answer: str, ents: Entities | None = None) -> ScoreResult:
    ents = ents or load_entities()
    if spec.kind == "judge":
        return ScoreResult("judge", None, "sentence answer")
    in_question = ents.find(q.question) - spec.gold_ids
    if spec.kind == "set_f1":
        predicted = ents.find(answer, spec.entity_type) - in_question
        return ScoreResult("set_f1", _f1(predicted, spec.gold_ids),
                           f"predicted {sorted(predicted)}")
    if spec.entity_type:
        found = ents.find(answer, spec.entity_type) - in_question
        extra = found - spec.gold_ids
        if spec.gold_ids <= found and extra:
            return ScoreResult("judge", None, f"exact key plus extra {spec.entity_type}s {sorted(extra)}")
        return ScoreResult("exact", 1.0 if spec.gold_ids <= found else 0.0, f"found {sorted(found)}")
    text = normalise(answer)
    missing = [k for k in spec.keys if not contains(text, normalise(k))]
    return ScoreResult("exact", 0.0 if missing else 1.0, f"missing {missing}" if missing else "")
