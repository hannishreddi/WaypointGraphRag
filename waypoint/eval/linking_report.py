"""Entity-linking report on the dev questions (PLAN 2.1). Offline: no API calls.

For each dev question: linked entities, and capitalised words outside every linked
span. Recall is measured against `waypoint.eval.entities.find`, which is a weak
reference: it knows employees, departments, projects, products and policies by full
names, ids and bare project names (normalised, so case-insensitive), but no first
names, titles or skills. Links it does not have are listed as "extra" for hand
classification (real link vs false link).

    python -m waypoint.eval.linking_report
"""
from __future__ import annotations

import re

from waypoint.eval.entities import load_entities
from waypoint.eval.questions import load_questions
from waypoint.retrieval.linking import link_entities

QUESTION_WORDS = frozenset("Who What Which How Is Can Do Does A An The I If When Where Why".split())
_CAP_WORD = re.compile(r"\b[A-Z][\w&-]*")


def main() -> None:
    ents = load_entities()
    questions = load_questions("dev")
    ref_total = hit_total = 0
    misses: list[str] = []
    extras: list[str] = []
    for q in questions:
        links = link_entities(q.question)
        linked = {m.id for m in links}
        ref = ents.find(q.question)
        hit_total += len(ref & linked)
        ref_total += len(ref)
        spans = [(m.start, m.end) for m in links]
        unlinked = [w.group(0) for w in _CAP_WORD.finditer(q.question)
                    if not any(s <= w.start() < e for s, e in spans) and w.group(0) not in QUESTION_WORDS]
        shown = "; ".join(f"{m.surface!r}->{m.label}:{m.id}" for m in links) or "-"
        print(f"{q.id} {q.question}\n    linked: {shown}\n    unlinked caps: {', '.join(unlinked) or '-'}")
        misses += [f"{q.id}: {eid} ({ents.names.get(eid, '?')})" for eid in sorted(ref - linked)]
        extras += [f"{q.id}: {m.surface!r} -> {m.label}:{m.id}" for m in links if m.id not in ref]
    print(f"\nrecall vs waypoint.eval.entities (weak reference): {hit_total}/{ref_total}"
          f" = {hit_total / ref_total:.3f} over {len(questions)} dev questions")
    print(f"misses ({len(misses)}):", *misses or ["none"], sep="\n  ")
    print(f"links not in the reference ({len(extras)}), classify by hand:", *extras or ["none"], sep="\n  ")


if __name__ == "__main__":
    main()
