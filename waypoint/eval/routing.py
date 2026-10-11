"""Routing accuracy on the 60 dev questions (PLAN 2.4), before anything else is wired.

Gold routes come from the hand-labelled `template_coverage.COVERAGE`:
template/composed -> fact_list_count with that plan (ids from link_entities), rule ->
personal_rule with rule id, subject ("asker" for @asker) and params, needs-text ->
policy_text (plan scored only as "has a text_search step"), other -> fact_list_count
(no plan to score). Reported: intent confusion, exact plan match, parameter-extraction
errors, needs_identity agreement, confidence by correctness and the low-confidence
threshold sweep, LLM calls and tokens. Accuracy is also given on the dev questions that
are not few-shot examples, because few-shots are scored too.

Router outputs are cached in .cache/router/, which is the checkpoint: after a quota stop
re-run the same command (the next day for a daily quota); cached rows make 0 calls.

    python -m waypoint.eval.routing [--limit N]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from waypoint.config import REPO_ROOT, get_settings
from waypoint.eval.questions import Question, asker_for, load_questions
from waypoint.eval.template_coverage import COVERAGE
from waypoint.llm.client import QuotaStop, get_llm_client
from waypoint.llm.structured import StructuredOutputError
from waypoint.retrieval import router_examples as X
from waypoint.retrieval.linking import link_entities
from waypoint.retrieval.plan import INTENTS, OPS
from waypoint.retrieval.router import CACHE_DIR, LOW_CONFIDENCE, PROMPT_VERSION, Route, Router

OUT = REPO_ROOT / "docs" / "routing_dev.md"
EXTRA_PATH_COST = 0.2  # threshold objective: missed wrong routes + 0.2 x correct routes sent down two paths

StepT = tuple[str, dict[str, Any]]


@dataclass
class Gold:
    intent: str
    steps: list[StepT] | None  # None: plan not scored
    needs_text: bool = False
    needs_identity: bool | None = None  # None: not labelled


def gold_route(q: Question) -> Gold:
    spec = COVERAGE[q.id]
    links = link_entities(q.question)

    def res(v: Any) -> Any:
        if isinstance(v, str) and v.startswith("@"):
            return next(m.id for m in links if m.label == v[1:])
        return v

    if spec.kind == "template":
        return Gold("fact_list_count", [(spec.template, {k: res(v) for k, v in spec.args})], needs_identity=False)
    if spec.kind == "composed":
        assert spec.template == "manager_department_head", spec.template
        return Gold("fact_list_count", [("manager", {"employee_id": res("@Employee")}),
                                        ("employee_card", {"employee_id": "$1.employee_id"}),
                                        ("department_head", {"department_id": "$2.department_id"})],
                    needs_identity=False)
    if spec.kind == "rule":
        args = dict(spec.args)
        subject = args.pop("subject")
        if subject == "@asker":
            args = {"subject": "asker", **args}
        elif subject is not None:
            args = {"subject": res(subject), **args}
        return Gold("personal_rule", [(spec.template, args)], needs_identity=subject == "@asker")
    if spec.kind == "needs-text":
        return Gold("policy_text", None, needs_text=True)
    return Gold("fact_list_count", None)


def _steps(route: Route) -> list[StepT]:
    return [(s.op, {k: v for k, v in s.args.items() if v is not None}) for s in route.decision.plan]


def plan_diff(gold: list[StepT], pred: list[StepT]) -> tuple[bool, list[str]]:
    """(core match, errors). Core match: same ops, every gold arg equal; extras only optional args."""
    g_ops, p_ops = [o for o, _ in gold], [o for o, _ in pred]
    if g_ops != p_ops:
        return False, [f"ops {g_ops} -> {p_ops}"]
    errs, core = [], True
    for i, ((op, ga), (_, pa)) in enumerate(zip(gold, pred, strict=True), 1):
        for k in sorted(set(ga) | set(pa)):
            if k not in pa:
                errs.append(f"[{i}] {op}.{k}: missing (gold {ga[k]!r})")
                core = False
            elif k not in ga:
                errs.append(f"[{i}] {op}.{k}: extra {pa[k]!r}")
                core &= not OPS[op].params[k].required
            elif str(ga[k]).lower() != str(pa[k]).lower():
                errs.append(f"[{i}] {op}.{k}: {ga[k]!r} -> {pa[k]!r}")
                core = False
    return core, errs


@dataclass
class Row:
    q: Question
    gold: Gold
    route: Route | None = None
    error: str = ""
    few_shot: bool = False

    @property
    def intent_ok(self) -> bool:
        return self.route is not None and self.route.intent == self.gold.intent

    def plan(self) -> tuple[str, list[str]]:
        """(status, errors): status exact | core | wrong | has-text | no-text | n/a | error."""
        if self.route is None:
            return "error", [self.error]
        pred = _steps(self.route)
        if self.gold.needs_text:
            return ("has-text" if any(o == "text_search" for o, _ in pred) else "no-text"), []
        if self.gold.steps is None:
            return "n/a", []
        core, errs = plan_diff(self.gold.steps, pred)
        return ("exact" if not errs else "core" if core else "wrong"), errs

    @property
    def correct(self) -> bool:
        return self.intent_ok and self.plan()[0] in ("exact", "core", "has-text", "n/a")


def run(limit: int | None = None) -> tuple[list[Row], dict[str, Any], str | None]:
    s = get_settings()
    client = get_llm_client()
    router = Router(client, model=s.model_fast)
    rows, stop = [], None
    calls_now = 0
    for q in load_questions("dev")[:limit]:
        row = Row(q, gold_route(q), few_shot=q.id in X.DEV_EXAMPLES)
        try:
            row.route = router.route(q.question, asker_for(q.id))
            calls_now += row.route.llm_calls
        except StructuredOutputError as exc:
            row.error = f"invalid after retry: {str(exc)[:200]}"
            calls_now += getattr(router, "last_calls", 2)
        except QuotaStop as exc:
            stop = f"{type(exc).__name__}: {exc}"
            break
        rows.append(row)
        print(f"{q.id} {'cached' if row.route and row.route.cached else 'called'} "
              f"{row.route.intent if row.route else 'ERROR'}", flush=True)
    stats = {"model": s.model_fast, "llm_calls_now": calls_now,
             "http_requests_now": dict(getattr(client, "calls", {}) or {}), "rpm": s.llm_rpm,
             "records": _cache_records([(r.q.question, asker_for(r.q.id)) for r in rows], s.model_fast)}
    return rows, stats, stop


def _cache_records(keys: list[tuple[str, str]], model: str) -> list[dict[str, Any]]:
    wanted = set(keys)
    out = []
    for p in CACHE_DIR.glob("*.json"):
        rec = json.loads(p.read_text(encoding="utf-8"))
        if (rec["question"], rec["asker_id"]) in wanted and rec["model"] == model \
                and rec["prompt_version"] == PROMPT_VERSION:
            out.append(rec)
    return out


def sweep(rows: list[Row]) -> tuple[float, list[tuple[float, int, int, float]]]:
    scored = [(r.route.decision.confidence, r.correct) for r in rows if r.route is not None]
    table = []
    for t in [0.0, 0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.01]:
        missed = sum(1 for c, ok in scored if not ok and c >= t)
        extra = sum(1 for c, ok in scored if ok and c < t)
        table.append((t, missed, extra, missed + EXTRA_PATH_COST * extra))
    best = min(table, key=lambda r: (r[3], -r[0]))[0]
    return best, table


def _pct(n: int, d: int) -> str:
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "0/0"


def report(rows: list[Row], stats: dict[str, Any], stop: str | None) -> str:
    held = [r for r in rows if not r.few_shot]
    L = ["# Router accuracy on the dev split (PLAN 2.4)", "",
         f"Generated by `python -m waypoint.eval.routing`. Router `{PROMPT_VERSION}`, model `{stats['model']}` "
         f"(MODEL_FAST, Gemini free tier). Gold: hand-labelled `template_coverage.COVERAGE`. "
         f"{len(X.DEV_EXAMPLES)} of the dev questions are few-shot examples in the prompt, so they are also "
         "reported apart (held-out = the other dev questions).", ""]
    if stop:
        L += [f"**Stopped early on a quota stop** ({stop}); re-run to resume from the cache.", ""]
    plan_rows = [r for r in rows if r.gold.steps is not None]
    text_rows = [r for r in rows if r.gold.needs_text]
    for name, rs in (("all dev", rows), ("held-out", held)):
        pr = [r for r in rs if r.gold.steps is not None]
        tr = [r for r in rs if r.gold.needs_text]
        L += [f"- **{name}** ({len(rs)}): intent {_pct(sum(r.intent_ok for r in rs), len(rs))}; "
              f"plan exact {_pct(sum(r.plan()[0] == 'exact' for r in pr), len(pr))}, "
              f"exact or core (extra optional filter only) "
              f"{_pct(sum(r.plan()[0] in ('exact', 'core') for r in pr), len(pr))}; "
              f"text questions with a text_search step {_pct(sum(r.plan()[0] == 'has-text' for r in tr), len(tr))}; "
              f"route correct {_pct(sum(r.correct for r in rs), len(rs))}"]
    ident = [r for r in rows if r.gold.needs_identity is not None and r.route]
    L += [f"- needs_identity agrees with gold on {_pct(sum(r.route.decision.needs_identity == r.gold.needs_identity for r in ident), len(ident))} "
          "labelled rows (only Q210 is an asker question; text questions with I/my are unlabelled)",
          f"- failed loudly (invalid after retry): {sum(1 for r in rows if r.route is None)}; "
          f"unresolved mentions on dev: {sum(len(r.route.unresolved) for r in rows if r.route)}; "
          f"alternatives given: {sum(1 for r in rows if r.route and r.route.decision.alternative)}", ""]
    # confusion
    L += ["## Intent confusion (rows gold, columns predicted)", "",
          "| gold \\ predicted | " + " | ".join(INTENTS) + " | error |", "|---|" + "---:|" * (len(INTENTS) + 1)]
    conf: dict[str, Counter[str]] = defaultdict(Counter)
    for r in rows:
        conf[r.gold.intent][r.route.intent if r.route else "error"] += 1
    for g in INTENTS:
        if conf[g]:
            L.append(f"| {g} | " + " | ".join(str(conf[g][p] or "") for p in (*INTENTS, "error")) + " |")
    # errors
    L += ["", "## Routing and parameter-extraction errors", "",
          "| q | few-shot | gold | predicted intent | plan | errors | conf |", "|---|---|---|---|---|---|---:|"]
    for r in rows:
        status, errs = r.plan()
        if r.correct and not errs:
            continue
        gold = r.gold.intent + (": " + " > ".join(o for o, _ in r.gold.steps) if r.gold.steps else "")
        pred = r.route.intent if r.route else "error"
        plan = " > ".join(o for o, _ in _steps(r.route)) if r.route else ""
        conf_v = f"{r.route.decision.confidence:.2f}" if r.route else ""
        L.append(f"| {r.q.id} | {'yes' if r.few_shot else ''} | {gold} | {pred} | {plan} ({status}) | "
                 f"{'; '.join(errs).replace('|', '/')} | {conf_v} |")
    # confidence
    best, table = sweep(rows)
    ok_c = sorted(r.route.decision.confidence for r in rows if r.route and r.correct)
    bad_c = sorted(r.route.decision.confidence for r in rows if r.route and not r.correct)
    L += ["", "## Confidence and the low-confidence threshold (dev only)", "",
          f"Correct routes: {len(ok_c)}, confidence {', '.join(f'{c:.2f}' for c in ok_c)}.  ",
          f"Wrong routes: {len(bad_c)}, confidence {', '.join(f'{c:.2f}' for c in bad_c) or '-'}.", "",
          f"Objective: wrong routes at or above the threshold (one path only) + {EXTRA_PATH_COST} x correct routes "
          "below it (an extra path). Ties go to the higher threshold.", "",
          "| threshold | wrong, one path | correct, two paths | cost |", "|---:|---:|---:|---:|"]
    L += [f"| {t:.2f} | {m} | {e} | {c:.1f} |" for t, m, e, c in table]
    L += ["", f"Best on dev: {best:.2f}. In use: `router.LOW_CONFIDENCE = {LOW_CONFIDENCE}`.", ""]
    # calls and quota
    recs = stats["records"]
    by_date = Counter(r["date"] for r in recs)
    tok = Counter()
    for r in recs:
        tok.update(r["usage"])
    L += ["## LLM calls and Gemini free-tier quota", "",
          f"- This run: {stats['llm_calls_now']} router LLM calls (validation retries included); "
          f"HTTP generateContent requests by model (429/5xx retries included): {stats['http_requests_now'] or '{}'}.",
          f"- All cached routes for these {len(rows)} questions: {sum(r['llm_calls'] for r in recs)} LLM calls "
          f"({sum(r['llm_calls'] - 1 for r in recs)} validation retries), by day {dict(sorted(by_date.items()))}; "
          f"tokens in {tok['input_tokens']:,} (cached {tok['cached_input_tokens']:,}), out {tok['output_tokens']:,} "
          f"(thinking included).",
          f"- Quota: model `{stats['model']}` on the free tier, client limiter {stats['rpm']:g} requests/min "
          "(halved on a per-minute 429). The daily request quota is not readable through the API; a daily 429 "
          "stops the run and the cache resumes it. A re-run of this report makes 0 calls.", ""]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Router accuracy on dev (cached)")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args(argv)
    rows, stats, stop = run(args.limit)
    OUT.write_text(report(rows, stats, stop) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    if stop:
        print(f"stopped: {stop}; re-run to resume", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
