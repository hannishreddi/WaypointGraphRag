"""95% bootstrap confidence intervals (PLAN 3.3 protocol d). Pure Python, fixed seed.

- `mean_ci(values)`: percentile interval of the mean over RESAMPLES resamples with
  replacement; the interval is the 2.5% and 97.5% order statistics of the resampled means.
- `paired_diff_ci(a, b)`: the same for the per-question difference a - b (for example S5
  minus S1 on the same test questions); both must score exactly the same question ids.
- `by_stratum(rows, key)`: n, mean and interval per stratum (hops, category); unscored
  rows (score None or "") are skipped.
- `excludes_zero(ci)`: the only case in which a difference may be claimed. An interval
  that touches zero does not exclude it.

    python -m waypoint.eval.bootstrap --a <run dir> --b <run dir>

prints both runs' intervals overall, by hops and by category, and the paired a - b
difference on the questions both scored, overall and by hops.

Every call seeds its own `random.Random`, so results do not depend on call order.
"""
from __future__ import annotations

import argparse
import csv
import math
import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RESAMPLES = 10_000
SEED = 42  # the split's seed (CLAUDE.md 1.4); fixed for every reported interval
LEVEL = 0.95


@dataclass(frozen=True)
class CI:
    mean: float
    low: float
    high: float
    n: int


def mean_ci(values: Sequence[float], *, resamples: int = RESAMPLES, seed: int = SEED, level: float = LEVEL) -> CI:
    vals = [float(v) for v in values]
    n = len(vals)
    if n == 0:
        raise ValueError("no values")
    rng = random.Random(seed)
    means = sorted(sum(rng.choices(vals, k=n)) / n for _ in range(resamples))
    tail = (1 - level) / 2
    lo = means[math.floor(tail * resamples)]
    hi = means[math.ceil((1 - tail) * resamples) - 1]
    return CI(mean=sum(vals) / n, low=lo, high=hi, n=n)


def paired_diff_ci(a: Mapping[str, float], b: Mapping[str, float], **kw: Any) -> CI:
    if set(a) != set(b):
        raise ValueError(f"paired difference needs the same questions: {len(set(a) ^ set(b))} ids differ")
    ids = sorted(a)
    return mean_ci([float(a[i]) - float(b[i]) for i in ids], **kw)


def by_stratum(rows: Iterable[Mapping[str, Any]], key: str, value: str = "score", **kw: Any) -> dict[str, CI]:
    groups: dict[str, list[float]] = {}
    for r in rows:
        v = r.get(value)
        if v is None or v == "":
            continue
        groups.setdefault(str(r[key]), []).append(float(v))
    return {k: mean_ci(vs, **kw) for k, vs in sorted(groups.items())}


def excludes_zero(ci: CI) -> bool:
    return ci.low > 0 or ci.high < 0


# ---------------------------------------------------------------- CLI (3.3d)

def _load(run_dir: Path) -> list[dict[str, str]]:
    with open(run_dir / "results.csv", encoding="utf-8", newline="") as f:
        return [r for r in csv.DictReader(f) if r.get("status") != "error"]


def _fmt(ci: CI) -> str:
    return f"{ci.mean:.3f} [{ci.low:.3f}, {ci.high:.3f}] (n={ci.n})"


def report(a_dir: Path, b_dir: Path) -> str:
    """Per-run CIs overall, by hops and by category, and the paired difference a - b on the
    questions both runs scored (overall and by hops)."""
    a, b = _load(a_dir), _load(b_dir)
    lines = [f"# Bootstrap 95% CIs (seed {SEED}, {RESAMPLES:,} resamples, percentile)", "",
             f"- a: {a_dir.name}", f"- b: {b_dir.name}", ""]
    for name, rows in (("a", a), ("b", b)):
        lines.append(f"## {name}: overall {_fmt(mean_ci([float(r['score']) for r in rows if r['score'] != '']))}")
        for key in ("hops", "category"):
            lines += [f"- {key} {k}: {_fmt(ci)}" for k, ci in by_stratum(rows, key).items()]
        lines.append("")
    sa = {r["id"]: r for r in a if r["score"] != ""}
    sb = {r["id"]: r for r in b if r["score"] != ""}
    common = sorted(set(sa) & set(sb))
    lines.append(f"## paired difference a - b ({len(common)} questions scored by both)")
    groups: dict[str, list[str]] = {"all": common}
    for i in common:
        groups.setdefault(f"hops {sa[i]['hops']}", []).append(i)
    for g, ids in groups.items():
        ci = paired_diff_ci({i: float(sa[i]["score"]) for i in ids}, {i: float(sb[i]["score"]) for i in ids})
        lines.append(f"- {g}: {_fmt(ci)}; difference claimed: {'yes' if excludes_zero(ci) else 'no'}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Bootstrap CIs for two eval runs on the same split.")
    p.add_argument("--a", type=Path, required=True, help="run folder (e.g. S5 on test)")
    p.add_argument("--b", type=Path, required=True, help="run folder (e.g. S1 on test)")
    args = p.parse_args(argv)
    print(report(args.a, args.b))


if __name__ == "__main__":
    main()
