"""95% bootstrap confidence intervals (PLAN 3.3 protocol d). Pure Python, fixed seed.

- `mean_ci(values)`: percentile interval of the mean over RESAMPLES resamples with
  replacement; the interval is the 2.5% and 97.5% order statistics of the resampled means.
- `paired_diff_ci(a, b)`: the same for the per-question difference a - b (for example S5
  minus S1 on the same test questions); both must score exactly the same question ids.
- `by_stratum(rows, key)`: n, mean and interval per stratum (hops, category); unscored
  rows (score None or "") are skipped.
- `excludes_zero(ci)`: the only case in which a difference may be claimed. An interval
  that touches zero does not exclude it.

Every call seeds its own `random.Random`, so results do not depend on call order.
"""
from __future__ import annotations

import math
import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
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
