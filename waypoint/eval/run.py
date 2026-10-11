"""Eval runner (PLAN 1.4). Only `make eval-test` may pass --split test (rule 2).

    python -m waypoint.eval.run --split dev --system echo [--limit N] [--no-judge]

Writes eval_runs/<YYYYmmdd-HHMMSS>_<system>_<split>/ with results.csv, summary.md
(by hops and by category), run_config.json and judge_review.csv (a seeded 10% sample
of judged rows with an empty human_verdict column for hand checking).
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import subprocess
import time
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path
from typing import Any

from waypoint.config import DEFAULT_AS_OF, REPO_ROOT, get_settings
from waypoint.contract import System
from waypoint.eval import questions as qmod
from waypoint.eval.entities import load_entities
from waypoint.eval.judge import PROMPT_VERSION, Judge
from waypoint.eval.scorers import assign_scorer, score_answer
from waypoint.eval.sources import gold_sources, source_metrics
from waypoint.eval.systems import SYSTEMS

EVAL_RUNS_DIR = REPO_ROOT / "eval_runs"
REVIEW_FRACTION = 0.1
REVIEW_SEED = 42
FIELDS = ["id", "category", "hops", "asker_id", "scorer", "status", "score", "verdict", "reason",
          "source_recall", "citation_precision", "n_citations", "input_tokens", "output_tokens",
          "latency_ms", "route", "detail", "question", "expected_answer", "answer"]
REVIEW_FIELDS = ["id", "question", "expected_answer", "answer", "verdict", "reason", "human_verdict"]


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def _run_dir(out_root: Path, system: str, split: str) -> Path:
    stem = f"{datetime.now():%Y%m%d-%H%M%S}_{system}_{split}"
    path, n = out_root / stem, 2
    while path.exists():
        path, n = out_root / f"{stem.split('_', 1)[0]}-{n}_{system}_{split}", n + 1
    path.mkdir(parents=True)
    return path


def _evaluate(q: qmod.Question, system: System, judge: Judge | None, as_of: date) -> dict[str, Any]:
    asker = qmod.asker_for(q.id)
    row: dict[str, Any] = {"id": q.id, "category": q.category, "hops": q.hops, "asker_id": asker,
                           "question": q.question, "expected_answer": q.expected_answer}
    t0 = time.perf_counter()
    try:
        resp = system.answer(q.question, asker, as_of)
    except Exception as exc:  # noqa: BLE001 - one failing question must not lose the run
        return row | {"scorer": assign_scorer(q).kind, "status": "error", "score": 0.0,
                      "detail": f"{type(exc).__name__}: {exc}", "answer": "", "source_recall": 0.0,
                      "latency_ms": round((time.perf_counter() - t0) * 1000, 1)}
    latency = (time.perf_counter() - t0) * 1000
    recall, precision = source_metrics(gold_sources(q), resp.citations)
    result = score_answer(assign_scorer(q), q, resp.answer, load_entities())
    row |= {"scorer": result.kind, "score": result.score, "detail": result.detail, "answer": resp.answer,
            "route": resp.route, "source_recall": recall, "citation_precision": precision,
            "n_citations": len(resp.citations), "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens, "latency_ms": round(latency, 1),
            "status": "scored"}
    if result.kind == "judge":
        if judge is None:
            row["status"] = "skipped"
        else:
            v = judge.judge(q, resp.answer)
            row |= {"score": v.score, "verdict": v.verdict, "reason": v.reason}
    return row


def _mean(values: Iterable[float | None]) -> float | None:
    vals = [v for v in values if v is not None and v != ""]
    return statistics.fmean(vals) if vals else None


def _fmt(v: float | None, digits: int = 2) -> str:
    return "n/a" if v is None else f"{v:.{digits}f}"


def _table(title: str, groups: dict[str, list[dict[str, Any]]]) -> list[str]:
    lines = [f"## {title}", "",
             "| group | n | scored | skipped | score | source recall | citation precision | tokens/q | p50 latency ms |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name, rows in groups.items():
        counted = [r for r in rows if r["status"] in ("scored", "error")]
        tokens = _mean((r.get("input_tokens") or 0) + (r.get("output_tokens") or 0) for r in rows)
        latency = statistics.median(r["latency_ms"] for r in rows) if rows else None
        lines.append(
            f"| {name} | {len(rows)} | {len(counted)} | {sum(r['status'] == 'skipped' for r in rows)} "
            f"| {_fmt(_mean(r['score'] for r in counted))} | {_fmt(_mean(r['source_recall'] for r in rows))} "
            f"| {_fmt(_mean(r.get('citation_precision') for r in rows))} | {_fmt(tokens, 0)} | {_fmt(latency, 1)} |")
    return lines + [""]


def _summary(rows: list[dict[str, Any]], config: dict[str, Any], judge: Judge | None) -> str:
    def group(key: str) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {}
        for r in sorted(rows, key=lambda r: str(r[key])):
            out.setdefault(str(r[key]), []).append(r)
        return out

    skipped = sum(r["status"] == "skipped" for r in rows)
    lines = [f"# Eval: {config['system']} on {config['split']}", "",
             f"- as of {config['as_of']} | commit {config['git_commit'][:10]}{' (dirty)' if config['git_dirty'] else ''}"
             f" | {len(rows)} questions | default asker {config['default_asker']}",
             "- score: mean over scored rows (exact, set-F1, judge 1 / 0.5 / 0); skipped rows are excluded",
             f"- skipped (judge off): {skipped}" if judge is None else
             f"- judge {judge.model}: {judge.api_calls} API calls, "
             f"{judge.usage.input_tokens + judge.usage.output_tokens} tokens (not counted in tokens/q)",
             f"- errors: {sum(r['status'] == 'error' for r in rows)}"]
    if config["split"] == "dev":
        lines.append("- dev has 60 questions: per-category numbers are noisy; use the test split for claims")
    lines += ["", *_table("Overall", {"all": rows}), *_table("By hops", group("hops")),
              *_table("By category", group("category"))]
    return "\n".join(lines)


def _write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: "" if r.get(k) is None else r.get(k) for k in fields})


def run_eval(*, split: str, system: System, judge: Judge | None, out_root: Path = EVAL_RUNS_DIR,
             limit: int | None = None, as_of: date = DEFAULT_AS_OF,
             models: dict[str, str | None] | None = None) -> Path:
    questions = qmod.load_questions(split)[:limit]
    config = {
        "system": system.name, "split": split, "as_of": as_of.isoformat(), "limit": limit,
        "n_questions": len(questions), "models": models or {},
        "judge": None if judge is None else {"model": judge.model, "prompt_version": PROMPT_VERSION},
        "default_asker": qmod.DEFAULT_ASKER, "asker_overrides": qmod.ASKER_OVERRIDES,
        "git_commit": _git("rev-parse", "HEAD"), "git_dirty": bool(_git("status", "--porcelain")),
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    out = _run_dir(out_root, system.name, split)
    rows = [_evaluate(q, system, judge, as_of) for q in questions]

    _write_csv(out / "results.csv", FIELDS, rows)
    judged = sorted((r for r in rows if r.get("verdict")), key=lambda r: r["id"])
    n_review = max(1, round(len(judged) * REVIEW_FRACTION)) if judged else 0
    review = sorted(random.Random(REVIEW_SEED).sample(judged, n_review), key=lambda r: r["id"])
    _write_csv(out / "judge_review.csv", REVIEW_FIELDS, review)
    config["finished_at"] = datetime.now().isoformat(timespec="seconds")
    (out / "run_config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    (out / "summary.md").write_text(_summary(rows, config, judge), encoding="utf-8")
    return out


def _models() -> dict[str, str | None]:
    try:
        s = get_settings()
    except Exception:  # noqa: BLE001 - settings are only recorded here; --no-judge needs none
        return {"model_fast": None, "model_answer": None, "embed_model": None}
    return {"model_fast": s.model_fast, "model_answer": s.model_answer, "embed_model": s.cohere_embed_model}


def main(argv: list[str] | None = None) -> Path:
    p = argparse.ArgumentParser(description="Run the eval on one split.")
    p.add_argument("--split", choices=["dev", "test"], required=True)
    p.add_argument("--system", choices=sorted(SYSTEMS), default="echo")
    p.add_argument("--limit", type=int, default=None, help="first N questions of the split")
    p.add_argument("--no-judge", action="store_true", help="skip judge-routed rows (no API calls)")
    p.add_argument("--out", type=Path, default=EVAL_RUNS_DIR, help=argparse.SUPPRESS)
    args = p.parse_args(argv)
    if args.split == "test":
        try:
            qmod.load_split_ids("test")
        except qmod.TestSplitLocked:
            raise SystemExit("the test split runs only through `make eval-test` (rule 2)") from None

    models = _models()
    judge = None
    if not args.no_judge:
        from waypoint.llm.client import AnthropicClient
        judge = Judge(AnthropicClient.from_settings(), model=str(models["model_fast"]))
    out = run_eval(split=args.split, system=SYSTEMS[args.system](), judge=judge, out_root=args.out,
                   limit=args.limit, models=models)
    print(f"wrote {out}\n")
    print((out / "summary.md").read_text(encoding="utf-8"))
    return out


if __name__ == "__main__":
    main()
