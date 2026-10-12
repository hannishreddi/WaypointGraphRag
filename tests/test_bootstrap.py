"""Bootstrap CIs (PLAN 3.3 protocol d): percentile intervals, fixed seed, pure Python.

Hand-computed cases use the exact resampling distribution of the mean:
- [0, 1] (n=2): mean 0, 1/2, 1 with p 1/4, 1/2, 1/4, so the 2.5% and 97.5% points
  are 0 and 1;
- [0, 0, 1] (n=3): mean k/3 with k ~ Binomial(3, 1/3): P(0) = 8/27 > 2.5%, and
  P(mean <= 2/3) = 26/27 = 0.963 < 97.5%, so the interval is (0, 1).
"""
from __future__ import annotations

import pytest

from waypoint.eval.bootstrap import CI, RESAMPLES, SEED, by_stratum, excludes_zero, mean_ci, paired_diff_ci


def test_defaults() -> None:
    assert RESAMPLES == 10_000 and isinstance(SEED, int)


def test_constant_values() -> None:
    ci = mean_ci([0.5, 0.5, 0.5])
    assert (ci.mean, ci.low, ci.high, ci.n) == (0.5, 0.5, 0.5, 3)


@pytest.mark.parametrize("values,low,high", [([0, 1], 0.0, 1.0), ([0, 0, 1], 0.0, 1.0)])
def test_hand_computed(values: list[float], low: float, high: float) -> None:
    ci = mean_ci(values)
    assert (ci.low, ci.high) == (low, high) and ci.mean == sum(values) / len(values)


def test_interval_contains_the_mean_and_narrows_with_n() -> None:
    small = mean_ci([0, 1] * 5)
    large = mean_ci([0, 1] * 200)
    assert small.low <= 0.5 <= small.high and large.low <= 0.5 <= large.high
    assert (large.high - large.low) < (small.high - small.low)


def test_deterministic() -> None:
    values = [0, 1, 1, 0.5, 1, 0, 1, 1, 0.5, 1]
    assert mean_ci(values) == mean_ci(values)
    assert mean_ci(values, seed=1) == mean_ci(values, seed=1)


def test_paired_difference() -> None:
    a = {"q1": 1.0, "q2": 1.0, "q3": 1.0}
    b = {"q1": 0.0, "q2": 0.5, "q3": 0.0}
    ci = paired_diff_ci(a, b)  # differences 1, 0.5, 1: every resample mean > 0
    assert ci.mean == pytest.approx(2.5 / 3) and ci.low >= 0.5 and excludes_zero(ci)
    sym = paired_diff_ci({"q1": 1.0, "q2": 0.0}, {"q1": 0.0, "q2": 1.0})  # differences 1, -1
    assert (sym.low, sym.high) == (-1.0, 1.0) and not excludes_zero(sym)
    with pytest.raises(ValueError, match="same questions"):
        paired_diff_ci({"q1": 1.0}, {"q2": 1.0})


def test_excludes_zero() -> None:
    assert excludes_zero(CI(mean=0.2, low=0.1, high=0.3, n=5))
    assert excludes_zero(CI(mean=-0.2, low=-0.3, high=-0.1, n=5))
    assert not excludes_zero(CI(mean=0.1, low=0.0, high=0.2, n=5))  # touching zero is not excluding it
    assert not excludes_zero(CI(mean=0.0, low=-0.1, high=0.1, n=5))


def test_by_stratum() -> None:
    rows = [{"hops": "1", "score": 1.0}, {"hops": "1", "score": 0.0}, {"hops": "2", "score": 1.0}]
    out = by_stratum(rows, "hops")
    assert list(out) == ["1", "2"] and out["1"].n == 2 and out["2"] == CI(mean=1.0, low=1.0, high=1.0, n=1)
    rows.append({"hops": "2", "score": None})  # unscored rows are skipped
    assert by_stratum(rows, "hops")["2"].n == 1


def test_empty_is_an_error() -> None:
    with pytest.raises(ValueError):
        mean_ci([])


def test_report(tmp_path) -> None:  # noqa: ANN001
    from waypoint.eval.bootstrap import report

    def run(name: str, scores: list[str]) -> object:
        d = tmp_path / name
        d.mkdir()
        rows = ["id,status,hops,category,score"]
        rows += [f"Q{i},ok,{1 + i % 2},c,{s}" for i, s in enumerate(scores)]
        (d / "results.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
        return d

    text = report(run("a", ["1", "1", "1", "1"]), run("b", ["0", "0", "0", ""]))
    assert "paired difference a - b (3 questions scored by both)" in text
    assert "- all: 1.000 [1.000, 1.000] (n=3); difference claimed: yes" in text
    assert "hops 1" in text and "category c" in text
