"""Request statistics of an eval run, for quota planning (3.3d).

    python -m waypoint.eval.callstats eval_runs/<run>

The free tier counts HTTP requests per model, so this reports both:
- requests: generateContent HTTP requests, retries included (results.csv `api_calls`, the
  client's request counter around each question: router, generator and judge together);
- logical calls by model role: router (`trace.router_calls`, validation retries included),
  generator (one per answered question, two after a verifier regeneration, none on a
  refusal path that skips it; one per row for baselines without a trace) and judge (the
  summary's judge line; cached verdicts make no call).

retries = requests - logical calls (429 and 5xx retries). The run logs do not say which
model a retry hit, so a quota plan must count them against each model (worst case).

Resumed runs (fix added 2026-10-16, after the test results were seen, because the final S1
test folder printed retries 119 instead of 62): `api_calls` of a resumed row was counted in
the session that produced it, but each summary's judge line covers only its own session. So
the judge count is summed over every session of the run (`sessions`). These are the earlier
run folders with the same checkpoint file, walked back from the last one to a session that
resumed nothing. The chain is complete when every session's `resumed_rows` equals the rows
its predecessors finished. A session stopped by a quota writes no folder, and neither does
an earlier session folder that was not kept; then the chain is incomplete, and retries are
printed as an upper bound. Requests spent on error rows are not checkpointed and not in
`requests`; they are reported separately (`error_requests`, every session).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

_JUDGE = re.compile(r"judge \S+: (\d+) API calls")


def _rows(run_dir: Path) -> list[dict[str, str]]:
    with open(run_dir / "results.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _config(run_dir: Path) -> dict[str, Any] | None:
    path = run_dir / "run_config.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def _checkpoint_name(config: dict[str, Any]) -> str:
    return re.split(r"[\\/]",str(config.get("checkpoint") or ""))[-1]  # Windows or POSIX path


def _judge_calls(run_dir: Path) -> int | None:
    path = run_dir / "summary.md"
    m = _JUDGE.search(path.read_text(encoding="utf-8")) if path.is_file() else None
    return int(m.group(1)) if m else (0 if path.is_file() else None)


def sessions(run_dir: Path) -> tuple[list[Path], bool]:
    """The finished sessions of the run that ends in `run_dir`, oldest first, and whether they
    account for every resumed row (see the module docstring)."""
    config = _config(run_dir)
    if config is None or not config.get("resumed_rows"):
        return [run_dir], True
    name = _checkpoint_name(config)
    earlier = sorted(
        (c["started_at"], d) for d in run_dir.parent.iterdir()
        if d.is_dir() and d != run_dir and (c := _config(d)) is not None and _checkpoint_name(c) == name
        and str(c.get("started_at", "")) < str(config.get("started_at", "")))
    chain: list[tuple[Path, dict[str, Any]]] = [(run_dir, config)]
    while chain[0][1].get("resumed_rows") and earlier:
        d = earlier.pop()[1]
        chain.insert(0, (d, _config(d) or {}))
    final_ids = {r["id"] for r in _rows(run_dir)}
    done: set[str] = set()
    complete = True
    for d, c in chain:
        rows = _rows(d)
        ids = {r["id"] for r in rows}
        if len(done & ids) != int(c.get("resumed_rows") or 0) or not ids <= final_ids:
            complete = False  # rows finished in a session that left no folder, or another question set
        done |= {r["id"] for r in rows if r.get("status") != "error"}
    return [d for d, _ in chain], complete


def stats(run_dir: Path) -> dict[str, Any]:
    rows = [r for r in _rows(run_dir) if r.get("status") != "error"]
    requests = sum(int(r.get("api_calls") or 0) for r in rows)
    router = generator = 0
    for r in rows:
        trace = json.loads(r["trace"]) if r.get("trace") else None
        if trace is None:  # baseline: one answer call per question
            generator += 1
            continue
        router += int(trace.get("router_calls") or 0)
        verifier = r.get("verifier") or trace.get("verifier")
        if verifier == "skipped":
            continue  # refusal path: no generator call
        generator += 2 if verifier in ("regenerated", "failed") else 1
    chain, complete = sessions(run_dir)
    judge_counts = [_judge_calls(d) for d in chain]
    complete = complete and None not in judge_counts
    judge = sum(j or 0 for j in judge_counts)
    error_requests = sum(int(r.get("api_calls") or 0) for d in chain for r in _rows(d) if r.get("status") == "error")
    logical = {"router": router, "generator": generator, "judge": judge}
    n = len(rows)
    return {"run": run_dir.name, "questions": n, "requests": requests, "logical": logical,
            "retries": requests - sum(logical.values()), "judge_scored": sum(r.get("scorer") == "judge" for r in rows),
            "requests_per_question": requests / n if n else 0.0, "sessions": len(chain), "complete": complete,
            "error_requests": error_requests}


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="HTTP requests and logical LLM calls of an eval run.")
    p.add_argument("runs", nargs="+", type=Path)
    for run in p.parse_args(argv).runs:
        s = stats(run)
        lg = s["logical"]
        print(f"{s['run']}: {s['questions']} questions, {s['requests']} HTTP requests "
              f"({s['requests_per_question']:.2f}/question); logical: router {lg['router']}, generator "
              f"{lg['generator']}, judge {lg['judge']}; retries {'' if s['complete'] else '<= '}{s['retries']}; "
              f"judge-scored rows {s['judge_scored']}; sessions {s['sessions']}"
              + (f" (+{s['error_requests']} requests on error rows, not checkpointed)" if s["error_requests"] else "")
              + ("" if s["complete"] else "; INCOMPLETE: earlier sessions not found, so the judge calls of "
                 "resumed rows are unknown and retries is an upper bound"))


if __name__ == "__main__":
    main()
