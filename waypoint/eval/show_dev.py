"""Print the 60 dev questions with category, hops and gold answers (rule 2).

The only sanctioned way to look at eval questions while developing: never read
data/zenvora_kb/eval/ or eval/split.json directly, because those hold the test split.

    python -m waypoint.eval.show_dev [--id Q012 ...] [--category org_structure] [--hops 2]
"""
from __future__ import annotations

import argparse
import sys

from waypoint.eval.questions import Question, asker_for, load_questions


def dev_questions(ids: list[str] | None = None, category: str | None = None,
                  hops: int | None = None) -> list[Question]:
    qs = load_questions("dev")
    return [q for q in qs
            if (not ids or q.id in ids) and (not category or q.category == category)
            and (hops is None or q.hops == hops)]


def render(q: Question) -> str:
    return (f"{q.id} [{q.category}, {q.hops}-hop, asker {asker_for(q.id)}]\n"
            f"  Q: {q.question}\n  A: {q.expected_answer}\n  sources: {', '.join(q.sources)}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--id", nargs="*", dest="ids")
    ap.add_argument("--category")
    ap.add_argument("--hops", type=int)
    args = ap.parse_args(argv)
    qs = dev_questions(args.ids, args.category, args.hops)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    print("\n\n".join(render(q) for q in qs))
    print(f"\n{len(qs)} dev question(s)")


if __name__ == "__main__":
    main()
