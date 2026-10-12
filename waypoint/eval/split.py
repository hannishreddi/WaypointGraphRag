"""Create eval/split.json once: 60 dev / 191 test, stratified by category x hops, seed 42.

Per-stratum dev counts use largest-remainder (Hamilton) allocation of 60 * n_k / 251,
ties broken by stratum key; then random.Random(42) samples dev ids inside each stratum,
visiting strata in sorted order over sorted ids, so the result is independent of CSV order.

    python -m waypoint.eval.split [--force]
    python -m waypoint.eval.split --counts   # sizes and stratum counts only, no ids
"""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

from waypoint.config import DEFAULT_AS_OF
from waypoint.eval.questions import SPLIT_PATH, Question, read_all_questions

DEV_SIZE = 60
SEED = 42


def _quotas(sizes: dict[str, int], dev_size: int) -> dict[str, int]:
    total = sum(sizes.values())
    exact = {k: n * dev_size / total for k, n in sizes.items()}
    quota = {k: math.floor(x) for k, x in exact.items()}
    by_remainder = sorted(sizes, key=lambda k: (-(exact[k] - quota[k]), k))
    for k in by_remainder[:dev_size - sum(quota.values())]:
        quota[k] += 1
    return quota


def make_split(questions: list[Question], dev_size: int = DEV_SIZE, seed: int = SEED) -> dict[str, Any]:
    strata: dict[str, list[str]] = defaultdict(list)
    for q in questions:
        strata[q.stratum].append(q.id)
    quota = _quotas({k: len(v) for k, v in strata.items()}, dev_size)
    rng = random.Random(seed)
    dev: list[str] = []
    for key in sorted(strata):
        dev += rng.sample(sorted(strata[key]), quota[key])
    dev_set = set(dev)
    return {
        "seed": seed,
        "as_of": DEFAULT_AS_OF.isoformat(),
        "stratified_by": ["category", "hops"],
        "dev_size": len(dev),
        "test_size": len(questions) - len(dev),
        "strata": {k: {"total": len(strata[k]), "dev": quota[k], "test": len(strata[k]) - quota[k]}
                   for k in sorted(strata)},
        "dev": sorted(dev),
        "test": sorted(q.id for q in questions if q.id not in dev_set),
    }


def write_split(path: Path = SPLIT_PATH, questions: list[Question] | None = None, *, force: bool = False) -> dict[str, Any]:
    if path.exists() and not force:
        raise FileExistsError(f"{path} exists; the split is created once (pass --force to overwrite)")
    split = make_split(questions if questions is not None else read_all_questions())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(split, indent=2) + "\n", encoding="utf-8")
    return split


def counts(path: Path = SPLIT_PATH) -> dict[str, Any]:
    """Split sizes and per-stratum counts only: never an id or a question (3.3d quota plan)."""
    split = json.loads(path.read_text(encoding="utf-8"))
    return {"dev": int(split["dev_size"]), "test": int(split["test_size"]),
            "strata": {k: {f: int(c[f]) for f in ("total", "dev", "test")} for k, c in split["strata"].items()}}


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--force", action="store_true", help="overwrite an existing split.json")
    p.add_argument("--counts", action="store_true", help="print split sizes and stratum counts only (no ids)")
    args = p.parse_args(argv)
    if args.counts:
        c = counts()
        print(f"dev {c['dev']}, test {c['test']}")
        for k, s in c["strata"].items():
            print(f"  {k:<22} total {s['total']:>3}  dev {s['dev']:>2}  test {s['test']:>3}")
        return
    try:
        split = write_split(force=args.force)
    except FileExistsError as exc:
        raise SystemExit(str(exc)) from None
    print(f"wrote {SPLIT_PATH}: dev {split['dev_size']}, test {split['test_size']}")
    for k, c in split["strata"].items():
        print(f"  {k:<22} total {c['total']:>3}  dev {c['dev']:>2}  test {c['test']:>3}")


if __name__ == "__main__":
    main()
