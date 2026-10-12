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
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

_JUDGE = re.compile(r"judge \S+: (\d+) API calls")


def stats(run_dir: Path) -> dict[str, Any]:
    with open(run_dir / "results.csv", encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r.get("status") != "error"]
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
    summary = (run_dir / "summary.md").read_text(encoding="utf-8") if (run_dir / "summary.md").is_file() else ""
    m = _JUDGE.search(summary)
    judge = int(m.group(1)) if m else 0
    logical = {"router": router, "generator": generator, "judge": judge}
    n = len(rows)
    return {"run": run_dir.name, "questions": n, "requests": requests, "logical": logical,
            "retries": requests - sum(logical.values()), "judge_scored": sum(r.get("scorer") == "judge" for r in rows),
            "requests_per_question": requests / n if n else 0.0}


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="HTTP requests and logical LLM calls of an eval run.")
    p.add_argument("runs", nargs="+", type=Path)
    for run in p.parse_args(argv).runs:
        s = stats(run)
        lg = s["logical"]
        print(f"{s['run']}: {s['questions']} questions, {s['requests']} HTTP requests "
              f"({s['requests_per_question']:.2f}/question); logical: router {lg['router']}, generator "
              f"{lg['generator']}, judge {lg['judge']}; retries {s['retries']}; judge-scored rows {s['judge_scored']}")


if __name__ == "__main__":
    main()
