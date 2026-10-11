"""Eval runner (PLAN 1.4). Only `make eval-test` may pass --split test (rule 2).

    python -m waypoint.eval.run --split dev --system echo [--limit N] [--ids Q003 Q052 ...] [--no-judge]

Writes eval_runs/<YYYYmmdd-HHMMSS>_<system>_<split>/ with results.csv, summary.md
(by hops and by category), run_config.json and judge_review.csv (a seeded 10% sample
of judged rows with an empty human_verdict column for hand checking).
Latency is recorded in total and without client-side waiting (rate-limiter pacing and
per-minute 429 sleeps, `waits`), and a system's `Response.trace` goes into results.csv.

Checkpoint and resume: every finished question (answer + verdict) is appended to
<out>/.checkpoints/<system>_<split>_<config hash>.jsonl. The hash covers the system and
its config_id, split, as-of, models, judge and askers (not the git commit), so the same
command resumes where it stopped and redoes nothing. Error rows are not checkpointed,
so they are retried. A QuotaStop (daily quota, or one request larger than the
per-minute quota) ends the run cleanly with the checkpoint kept; the output files are
written once every question is done.

--ids runs only the chosen questions of the split (unknown ids are an error, so a test
id cannot be named on the dev split). The subset shares the checkpoint of the full run:
the ids are not part of the config hash, so a later full run reuses the finished rows.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import statistics
import subprocess
import time
from collections.abc import Callable, Iterable
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
from waypoint.llm.client import QuotaStop

EVAL_RUNS_DIR = REPO_ROOT / "eval_runs"
REVIEW_FRACTION = 0.1
REVIEW_SEED = 42
FIELDS = ["id", "category", "hops", "asker_id", "scorer", "status", "score", "verdict", "reason",
          "source_recall", "citation_precision", "n_citations", "input_tokens", "output_tokens",
          "cached_input_tokens", "api_calls", "latency_ms", "latency_excl_wait_ms", "route", "verifier",
          "trace", "detail", "question", "expected_answer", "answer"]
REVIEW_FIELDS = ["id", "question", "expected_answer", "answer", "verdict", "reason", "human_verdict"]


class RunStopped(RuntimeError):
    """The run stopped early on a QuotaStop; finished questions are in the checkpoint."""


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


def _evaluate(q: qmod.Question, system: System, judge: Judge | None, as_of: date,
              waits: Callable[[], float] | None = None) -> dict[str, Any]:
    asker = qmod.asker_for(q.id)
    row: dict[str, Any] = {"id": q.id, "category": q.category, "hops": q.hops, "asker_id": asker,
                           "question": q.question, "expected_answer": q.expected_answer}
    t0 = time.perf_counter()
    waited0 = waits() if waits is not None else None
    try:
        resp = system.answer(q.question, asker, as_of)
    except QuotaStop:
        raise
    except Exception as exc:  # noqa: BLE001 - one failing question must not lose the run
        return row | {"scorer": assign_scorer(q).kind, "status": "error", "score": 0.0,
                      "detail": f"{type(exc).__name__}: {exc}", "answer": "", "source_recall": 0.0,
                      "latency_ms": round((time.perf_counter() - t0) * 1000, 1)}
    latency = (time.perf_counter() - t0) * 1000
    waited_ms = (waits() - waited0) * 1000 if waits is not None and waited0 is not None else None
    recall, precision = source_metrics(gold_sources(q), resp.citations)
    result = score_answer(assign_scorer(q), q, resp.answer, load_entities())
    row |= {"scorer": result.kind, "score": result.score, "detail": result.detail, "answer": resp.answer,
            "route": resp.route, "source_recall": recall, "citation_precision": precision,
            "n_citations": len(resp.citations), "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
            "cached_input_tokens": resp.usage.cached_input_tokens, "latency_ms": round(latency, 1),
            "latency_excl_wait_ms": None if waited_ms is None else round(latency - waited_ms, 1),
            "verifier": resp.trace.get("verifier"),
            "trace": json.dumps(resp.trace, ensure_ascii=False) if resp.trace else None,
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
             "| group | n | scored | skipped | score | source recall | citation precision | tokens/q "
             "| cached in/q | p50 latency ms | p50 latency excl. wait ms |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name, rows in groups.items():
        counted = [r for r in rows if r["status"] in ("scored", "error")]
        tokens = _mean((r.get("input_tokens") or 0) + (r.get("output_tokens") or 0) for r in rows)
        latency = statistics.median(r["latency_ms"] for r in rows) if rows else None
        net = [r["latency_excl_wait_ms"] for r in rows if r.get("latency_excl_wait_ms") not in (None, "")]
        latency_net = statistics.median(net) if net else None
        lines.append(
            f"| {name} | {len(rows)} | {len(counted)} | {sum(r['status'] == 'skipped' for r in rows)} "
            f"| {_fmt(_mean(r['score'] for r in counted))} | {_fmt(_mean(r['source_recall'] for r in rows))} "
            f"| {_fmt(_mean(r.get('citation_precision') for r in rows))} | {_fmt(tokens, 0)} "
            f"| {_fmt(_mean(r.get('cached_input_tokens') or 0 for r in rows), 0)} | {_fmt(latency, 1)} "
            f"| {_fmt(latency_net, 1)} |")
    return lines + [""]


def _summary(rows: list[dict[str, Any]], config: dict[str, Any], judge: Judge | None) -> str:
    def group(key: str) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {}
        for r in sorted(rows, key=lambda r: str(r[key])):
            out.setdefault(str(r[key]), []).append(r)
        return out

    skipped = sum(r["status"] == "skipped" for r in rows)
    lines = [f"# Eval: {config['system']} on {config['split']}"
             f"{' (subset: ' + ' '.join(config['ids']) + ')' if config.get('ids') else ''}", "",
             f"- as of {config['as_of']} | commit {config['git_commit'][:10]}{' (dirty)' if config['git_dirty'] else ''}"
             f" | {len(rows)} questions | default asker {config['default_asker']}",
             "- score: mean over scored rows (exact, set-F1, judge 1 / 0.5 / 0); skipped rows are excluded",
             f"- skipped (judge off): {skipped}" if judge is None else
             f"- judge {judge.model}: {judge.api_calls} API calls, "
             f"{judge.usage.input_tokens + judge.usage.output_tokens} tokens (not counted in tokens/q)",
             f"- errors: {sum(r['status'] == 'error' for r in rows)}"]
    if config["split"] == "dev":
        lines.append("- dev has 60 questions: per-category numbers are noisy; use the test split for claims")
    calls = [r["api_calls"] for r in rows if r.get("api_calls") not in (None, "")]
    if calls:
        lines.append(f"- LLM API calls (answer + judge HTTP requests incl. retries, all sessions): {sum(calls)}")
    verdicts = [r.get("verifier") for r in rows if r.get("verifier")]
    if verdicts:
        counts = {v: verdicts.count(v) for v in sorted(set(verdicts))}
        lines.append(f"- verifier: {counts} (regenerated/failed = triggered)")
    if config.get("resumed_rows"):
        lines.append(f"- resumed {config['resumed_rows']} finished rows from the checkpoint")
    lines += ["", *_table("Overall", {"all": rows}), *_table("By hops", group("hops")),
              *_table("By category", group("category"))]
    return "\n".join(lines)


def _write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: "" if r.get(k) is None else r.get(k) for k in fields})


def config_hash(config: dict[str, Any]) -> str:
    keys = ("system", "system_config", "split", "as_of", "models", "judge", "default_asker", "asker_overrides")
    blob = json.dumps({k: config.get(k) for k in keys}, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def _load_checkpoint(path: Path) -> dict[str, dict[str, Any]]:
    done: dict[str, dict[str, Any]] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                done[row["id"]] = row
    return done


def select_questions(questions: list[qmod.Question], ids: list[str] | None) -> list[qmod.Question]:
    """The questions with the given ids, in split order; every id must be in the split."""
    if not ids:
        return questions
    known = {q.id for q in questions}
    unknown = [i for i in ids if i not in known]
    if unknown:
        raise ValueError(f"not in this split: {', '.join(unknown)}")
    wanted = set(ids)
    return [q for q in questions if q.id in wanted]


def run_eval(*, split: str, system: System, judge: Judge | None, out_root: Path = EVAL_RUNS_DIR,
             limit: int | None = None, ids: list[str] | None = None, as_of: date = DEFAULT_AS_OF,
             models: dict[str, str | None] | None = None,
             api_calls: Callable[[], int] | None = None, checkpoint_dir: Path | None = None,
             waits: Callable[[], float] | None = None) -> Path:
    """Evaluate `system` on `split`, resuming from its checkpoint. Raises RunStopped on a QuotaStop."""
    if getattr(system, "dev_only", False) and split != "dev":
        raise ValueError(f"{system.name} runs on the dev split only")
    if getattr(system, "safety_only", False):
        raise ValueError(f"{system.name} is a safety-set baseline; run it with python -m waypoint.eval.safety")
    questions = select_questions(qmod.load_questions(split), ids)[:limit]
    config: dict[str, Any] = {
        "system": system.name, "system_config": getattr(system, "config_id", ""), "split": split,
        "as_of": as_of.isoformat(), "limit": limit, "ids": ids, "n_questions": len(questions),
        "models": models or {},
        "judge": None if judge is None else {"model": judge.model, "prompt_version": PROMPT_VERSION},
        "default_asker": qmod.DEFAULT_ASKER, "asker_overrides": qmod.ASKER_OVERRIDES,
        "git_commit": _git("rev-parse", "HEAD"), "git_dirty": bool(_git("status", "--porcelain")),
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    ckpt_dir = checkpoint_dir or out_root / ".checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    ckpt = ckpt_dir / f"{system.name}_{split}_{config_hash(config)}.jsonl"
    done = _load_checkpoint(ckpt)
    config["checkpoint"] = str(ckpt)
    config["resumed_rows"] = sum(q.id in done for q in questions)
    rows: list[dict[str, Any]] = []
    for i, q in enumerate(questions):
        if q.id in done:
            rows.append(done[q.id])
            continue
        before = api_calls() if api_calls is not None else 0
        try:
            row = _evaluate(q, system, judge, as_of, waits)
        except QuotaStop as exc:
            raise RunStopped(f"stopped at question {i + 1}/{len(questions)} ({q.id}): {exc}\n"
                             f"{len(rows)} finished questions are checkpointed in {ckpt}; "
                             "re-run the same command to resume.") from exc
        if api_calls is not None:
            row["api_calls"] = api_calls() - before
        rows.append(row)
        if row["status"] != "error":
            with open(ckpt, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    out = _run_dir(out_root, system.name, split)

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
        return {"llm_provider": None, "model_fast": None, "model_answer": None, "embed_model": None}
    return {"llm_provider": s.llm_provider, "model_fast": s.model_fast, "model_answer": s.model_answer,
            "embed_model": s.cohere_embed_model}


def main(argv: list[str] | None = None) -> Path:
    p = argparse.ArgumentParser(description="Run the eval on one split.")
    p.add_argument("--split", choices=["dev", "test"], required=True)
    p.add_argument("--system", choices=sorted(SYSTEMS), default="echo")
    p.add_argument("--limit", type=int, default=None, help="first N questions of the split")
    p.add_argument("--ids", nargs="+", default=None, help="run only these question ids of the split")
    p.add_argument("--no-judge", action="store_true", help="skip judge-routed rows (no API calls)")
    p.add_argument("--out", type=Path, default=EVAL_RUNS_DIR, help=argparse.SUPPRESS)
    args = p.parse_args(argv)
    if args.split == "test":
        try:
            qmod.load_split_ids("test")
        except qmod.TestSplitLocked:
            raise SystemExit("the test split runs only through `make eval-test` (rule 2)") from None

    models = _models()
    system = SYSTEMS[args.system]()
    if getattr(system, "dev_only", False) and args.split != "dev":
        raise SystemExit(f"{args.system} runs on the dev split only")
    if getattr(system, "safety_only", False):
        raise SystemExit(f"{args.system} runs on the safety set only (python -m waypoint.eval.safety)")
    client = None
    if not args.no_judge or args.system != "echo":
        from waypoint.llm.client import get_llm_client
        client = get_llm_client()
    judge = None
    if not args.no_judge:
        if models["model_fast"] == models["model_answer"]:
            print(f"warning: the judge uses the answer model ({models['model_fast']})")
        judge = Judge(client, model=str(models["model_fast"]))
    try:
        out = run_eval(split=args.split, system=system, judge=judge, out_root=args.out, limit=args.limit,
                       ids=args.ids,
                       models=models, api_calls=client.total_requests if client is not None else None,
                       waits=getattr(client, "total_wait_s", None))
    except RunStopped as exc:
        raise SystemExit(f"run stopped cleanly: {exc}") from None
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    print(f"wrote {out}\n")
    print((out / "summary.md").read_text(encoding="utf-8"))
    return out


if __name__ == "__main__":
    main()
