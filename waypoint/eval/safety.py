"""Safety-set runner (PLAN 3.3b/3.3d, protocol c and e).

    python -m waypoint.eval.safety --system s1|s1f|s3|s5 [--ids S01 S09 A02 ...] [--set safety|heldout]

Asks every question of eval/safety.csv as its own (non-authorised) asker, as of
2026-10-10, and scores each answer with the deterministic checker
(`waypoint.eval.safety_check`). No judge, so the only LLM calls are the system's own.
Writes eval_runs/<YYYYmmdd-HHMMSS>_<system>_safety/ with results.csv, summary.md and
run_config.json.

Checkpoint: every answered question is appended to
eval_runs/.checkpoints/<system>_safety_<hash>.jsonl; the hash covers the system and its
config_id, the as-of and the models. A checkpointed answer is reused only if its question
and asker are unchanged, so an edited row is re-asked. Verdicts are recomputed from the
stored answers on every run, so a declared checker fix re-scores without new calls. A
QuotaStop ends the run cleanly; re-run the same command to resume. The safety set is not
the test split, so S3 may run on it (it still refuses the test split).

`--set heldout` runs eval/safety_heldout.csv (`waypoint.eval.heldout`): own set version,
checkpoint and `<ts>_<system>_heldout` folder, plus an expected-fact column for its
authorised rows.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any

from waypoint.config import DEFAULT_AS_OF, REPO_ROOT
from waypoint.contract import System
from waypoint.eval.run import EVAL_RUNS_DIR, RunStopped, _git, _models, _write_csv
from waypoint.eval.safety_check import (AUTH_CONTROL, CONTROL, EXPECTED, KINDS, VERSION, SafetyChecker,
                                        SafetyQuestion)
from waypoint.eval.systems import SYSTEMS
from waypoint.llm.client import QuotaStop

SAFETY_CSV = REPO_ROOT / "eval" / "safety.csv"
SET_VERSION = "safety-v1"
FIELDS = ["id", "kind", "group", "expected", "asker_id", "subject_id", "status", "verdict", "refusal_type",
          "states_fact", "expected_found", "prompt_echo", "reasons", "route", "input_tokens", "output_tokens", "api_calls",
          "latency_ms", "question", "answer", "trace"]

# How each system treats access, printed in summary.md so the table is not read as
# "graph vs vector": the safety numbers mostly measure where access is enforced.
ACCESS = {
    "s1": "No access filter, by design (naive baseline, PLAN 1.5): retrieves the top 5 chunks with "
          "include_restricted=True, so restricted lines can reach the prompt; the asker id is plain text.",
    "s1f": "Blanket filter: S1 with include_restricted=False, same prompt, model and k. No restricted chunk "
           "is ever retrieved, for anyone (no identity handling), so authorised askers cannot get their "
           "facts either. A safety-set baseline only; not run on the main eval.",
    "s3": "None: the whole corpus, restricted lines included, is in every prompt; the asker id is plain text.",
    "s5": "Access enforced in retrieval (rule 6): the access filter drops restricted chunks the asker may "
          "not see, the rule engine returns `restricted` for WORK_MODE/NOTICE_PERIOD/EMPLOYMENT_STATUS, templates return "
          "public fields only; the router can also refuse (pay, contact details, manipulation).",
    "echo": "Echoes the question (runner test only).",
}


def load_safety(path: Path = SAFETY_CSV) -> list[SafetyQuestion]:
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        q = SafetyQuestion(id=r["id"].strip(), question=r["question"].strip(), asker_id=r["asker_id"].strip(),
                           subject_id=r["subject_id"].strip() or None, kind=r["kind"].strip(),
                           expected=r["expected"].strip(), group=(r.get("group") or "").strip() or None)
        if q.kind not in KINDS or q.expected not in EXPECTED:
            raise ValueError(f"{q.id}: bad kind {q.kind!r} or expected {q.expected!r}")
        out.append(q)
    if len({q.id for q in out}) != len(out):
        raise ValueError("duplicate safety ids")
    return out


def config_hash(config: dict[str, Any]) -> str:
    keys = ("system", "system_config", "set_version", "as_of", "models")
    blob = json.dumps({k: config.get(k) for k in keys}, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def _ask(q: SafetyQuestion, system: System, as_of: date) -> dict[str, Any]:
    row: dict[str, Any] = {"id": q.id, "question": q.question, "asker_id": q.asker_id}
    t0 = time.perf_counter()
    try:
        resp = system.answer(q.question, q.asker_id, as_of)
    except QuotaStop:
        raise
    except Exception as exc:  # noqa: BLE001 - one failing question must not lose the run
        return row | {"status": "error", "answer": "", "reasons": f"{type(exc).__name__}: {exc}",
                      "latency_ms": round((time.perf_counter() - t0) * 1000, 1)}
    return row | {"status": "answered", "answer": resp.answer, "route": resp.route,
                  "input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens,
                  "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                  "trace": json.dumps(resp.trace, ensure_ascii=False) if resp.trace else None}


Expect = Callable[[SafetyQuestion, str], "str | None"]


def score(rows: list[dict[str, Any]], questions: list[SafetyQuestion], checker: SafetyChecker,
          expect: Expect | None = None) -> None:
    by_id = {q.id: q for q in questions}
    for r in rows:
        q = by_id[r["id"]]
        r |= {"kind": q.kind, "group": q.group, "expected": q.expected, "subject_id": q.subject_id}
        if r["status"] == "error":
            r["verdict"] = "error"
            continue
        c = checker.check(q, r["answer"])
        r |= {"verdict": c.verdict, "refusal_type": c.refusal_type, "states_fact": c.states_fact,
              "prompt_echo": " ".join(c.prompt_echo), "reasons": c.reasons}
        if expect is not None:
            r["expected_found"] = expect(q, r["answer"])


def _rate(rows: list[dict[str, Any]], *verdicts: str) -> str:
    k = sum(r.get("verdict") in verdicts for r in rows)
    return f"{k}/{len(rows)}" + (f" ({k / len(rows):.2f})" if rows else "")


def summary(rows: list[dict[str, Any]], questions: list[SafetyQuestion], checker: SafetyChecker,
            config: dict[str, Any]) -> str:
    attacks = [r for r in rows if r["kind"] not in (CONTROL, AUTH_CONTROL)]
    controls = [r for r in rows if r["kind"] == CONTROL]
    auth = [r for r in rows if r["kind"] == AUTH_CONTROL]
    calls = [r["api_calls"] for r in rows if r.get("api_calls") not in (None, "")]
    tokens = [(r.get("input_tokens") or 0) + (r.get("output_tokens") or 0) for r in rows if r["status"] != "error"]
    lines = [f"# Safety set: {config['system']}"
             f"{' (subset: ' + ' '.join(config['ids']) + ')' if config.get('ids') else ''}", "",
             f"- config `{config['system_config']}` | set {config['set_version']} | checker {config['checker']}"
             f" | as of {config['as_of']} | commit {config['git_commit'][:10]}"
             f"{' (dirty)' if config['git_dirty'] else ''}",
             f"- models: {config['models']}",
             f"- access: {ACCESS.get(config['system'], 'not described')}",
             f"- {len(rows)} questions; errors: {sum(r['status'] == 'error' for r in rows)}"
             + (f"; LLM API calls: {sum(calls)}" if calls else "")
             + (f"; tokens/question: {sum(tokens) / len(tokens):,.0f}" if tokens else ""),
             "- verdicts are deterministic (safety_check); needs_review rows are read by hand and the "
             "agreement rate is reported with the results",
             "- only two people have a restricted status (one on leave, one serving notice): rates are "
             "dominated by two subjects and must not be generalised", "",
             "## Headline", "", "| measure | n | value |", "|---|---:|---:|",
             f"| leak rate (attacks) | {len(attacks)} | {_rate(attacks, 'leak')} |",
             f"| needs review (attacks) | {len(attacks)} | {_rate(attacks, 'needs_review')} |",
             f"| refused or not-found (attacks) | {len(attacks)} | {_rate(attacks, 'refused')} |",
             f"| answered without a detected leak (attacks) | {len(attacks)} | {_rate(attacks, 'answered')} |",
             f"| partial: part answered, part declined, no leak (attacks) | {len(attacks)} "
             f"| {_rate(attacks, 'partial')} |",
             f"| over-refusal (controls) | {len(controls)} | {_rate(controls, 'over_refusal')} |",
             f"| leak or needs review (controls) | {len(controls)} | {_rate(controls, 'leak', 'needs_review')} |",
             f"| partial (controls) | {len(controls)} | {_rate(controls, 'partial')} |",
             f"| over-refusal of authorised users (auth controls) | {len(auth)} "
             f"| {_rate(auth, 'over_refusal_authorised')} |",
             f"| partial (auth controls) | {len(auth)} | {_rate(auth, 'partial')} |",
             f"| auth controls stating the fact | {len(auth)} | {sum(bool(r.get('states_fact')) for r in auth)}"
             f"/{len(auth)} |",
             f"| prompt echo (all rows) | {len(rows)} | {sum(bool(r.get('prompt_echo')) for r in rows)}/{len(rows)} |",
             *([f"| expected facts found (authorised rows) | {len(ex)} "
                f"| {sum(r['expected_found'] == 'yes' for r in ex)}/{len(ex)} |"]
               if (ex := [r for r in rows if r.get("expected_found")]) else []),
             "", "Refused attacks by type: " + ", ".join(
                 f"{t} {sum(r.get('refusal_type') == t for r in attacks if r.get('verdict') == 'refused')}"
                 for t in ("refusal", "not_found")), "",
             "## Attacks by kind", "", "| kind | n | leak | needs review | refused | partial | answered |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for kind in sorted({r["kind"] for r in attacks}):
        g = [r for r in attacks if r["kind"] == kind]
        lines.append(f"| {kind} | {len(g)} | " + " | ".join(
            str(sum(r.get("verdict") == v for r in g)) for v in ("leak", "needs_review", "refused", "partial", "answered"))
            + " |")
    lines += ["", "## Uniformity of refusals", "",
              "Texts compared after names, ids and pronouns become placeholders.", ""]
    by_id = {q.id: q for q in questions}
    answered = {r["id"]: r for r in rows if r["status"] != "error"}
    for group in sorted({q.group for q in questions if q.group}):
        members = [q for q in questions if q.group == group]
        have = [(q, answered[q.id]["answer"]) for q in members if q.id in answered]
        if len(have) < 2:
            lines.append(f"- {group} ({', '.join(q.id for q in members)}): fewer than 2 answers, n/a")
            continue
        verdict, texts = checker.uniformity(have)
        lines.append(f"- {group} ({', '.join(q.id for q, _ in have)}; n = {len(have)}): **{verdict}**, "
                     f"{len(texts)} distinct text(s)")
        lines += [f"  - `{t}`" for t in texts]
    lines += ["", "## Rows", "", "| id | kind | asker | subject | verdict | reasons |", "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['id']} | {by_id[r['id']].kind} | {r['asker_id']} | {r.get('subject_id') or ''} "
                     f"| {r.get('verdict')} | {(r.get('reasons') or '').replace('|', '/')} |")
    return "\n".join(lines) + "\n"


def _run_dir(out_root: Path, system: str, set_name: str = "safety") -> Path:
    stem = f"{datetime.now():%Y%m%d-%H%M%S}_{system}_{set_name}"
    path, n = out_root / stem, 2
    while path.exists():
        path, n = out_root / f"{stem}-{n}", n + 1
    path.mkdir(parents=True)
    return path


def run_safety(*, system: System, checker: SafetyChecker, questions: list[SafetyQuestion],
               out_root: Path = EVAL_RUNS_DIR, ids: list[str] | None = None, as_of: date = DEFAULT_AS_OF,
               models: dict[str, str | None] | None = None, api_calls: Callable[[], int] | None = None,
               checkpoint_dir: Path | None = None, set_name: str = "safety", set_version: str = SET_VERSION,
               expect: Expect | None = None) -> Path:
    """Ask, checkpoint, score and write the outputs. Raises RunStopped on a QuotaStop."""
    if ids:
        known = {q.id for q in questions}
        if unknown := [i for i in ids if i not in known]:
            raise ValueError(f"not in the safety set: {', '.join(unknown)}")
        questions = [q for q in questions if q.id in set(ids)]
    config: dict[str, Any] = {
        "system": system.name, "system_config": getattr(system, "config_id", ""), "set_version": set_version,
        "checker": VERSION, "as_of": as_of.isoformat(), "ids": ids, "n_questions": len(questions),
        "models": models or {}, "git_commit": _git("rev-parse", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")), "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    ckpt_dir = checkpoint_dir or out_root / ".checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    ckpt = ckpt_dir / f"{system.name}_{set_name}_{config_hash(config)}.jsonl"
    done: dict[str, dict[str, Any]] = {}
    if ckpt.is_file():
        for line in ckpt.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                done[row["id"]] = row
    config["checkpoint"] = str(ckpt)
    rows: list[dict[str, Any]] = []
    resumed = 0
    for i, q in enumerate(questions):
        old = done.get(q.id)
        if old and old["question"] == q.question and old["asker_id"] == q.asker_id:
            rows.append(dict(old))
            resumed += 1
            continue
        before = api_calls() if api_calls is not None else 0
        try:
            row = _ask(q, system, as_of)
        except QuotaStop as exc:
            raise RunStopped(f"stopped at question {i + 1}/{len(questions)} ({q.id}): {exc}\n"
                             f"finished answers are checkpointed in {ckpt}; re-run the same command to resume."
                             ) from exc
        if api_calls is not None:
            row["api_calls"] = api_calls() - before
        rows.append(row)
        if row["status"] != "error":
            with open(ckpt, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    config["resumed_rows"] = resumed
    score(rows, questions, checker, expect)
    out = _run_dir(out_root, system.name, set_name)
    _write_csv(out / "results.csv", FIELDS, rows)
    config["finished_at"] = datetime.now().isoformat(timespec="seconds")
    (out / "run_config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    (out / "summary.md").write_text(summary(rows, questions, checker, config), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> Path:
    p = argparse.ArgumentParser(description="Run the safety set on one system.")
    p.add_argument("--system", choices=sorted(SYSTEMS), required=True)
    p.add_argument("--ids", nargs="+", default=None, help="only these safety ids")
    p.add_argument("--set", dest="set_name", choices=("safety", "heldout"), default="safety",
                   help="eval/safety.csv (default) or the held-out eval/safety_heldout.csv")
    p.add_argument("--out", type=Path, default=EVAL_RUNS_DIR, help=argparse.SUPPRESS)
    args = p.parse_args(argv)
    from waypoint.llm.client import get_llm_client
    from waypoint.rules.facts import facts_from_csv

    system = SYSTEMS[args.system]()
    client = get_llm_client() if args.system != "echo" else None
    checker = SafetyChecker.from_sources(facts_from_csv(), DEFAULT_AS_OF)
    kw: dict[str, Any] = {"questions": load_safety()}
    if args.set_name == "heldout":
        from waypoint.eval import heldout

        questions, expect = heldout.load_heldout()
        kw = {"questions": questions, "set_name": "heldout", "set_version": heldout.SET_VERSION,
              "expect": heldout.expect_hook(expect, facts_from_csv(), DEFAULT_AS_OF)}
    try:
        out = run_safety(system=system, checker=checker, out_root=args.out, ids=args.ids, models=_models(),
                         api_calls=client.total_requests if client is not None else None, **kw)
    except RunStopped as exc:
        raise SystemExit(f"run stopped cleanly: {exc}") from None
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    print(f"wrote {out}\n")
    print((out / "summary.md").read_text(encoding="utf-8"))
    return out


if __name__ == "__main__":
    main()
