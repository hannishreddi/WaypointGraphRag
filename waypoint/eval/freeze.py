"""Freeze (PLAN 3.3d): docs/freeze.md and the guard for runs on the test split.

    python -m waypoint.eval.freeze           # write docs/freeze.md
    python -m waypoint.eval.freeze --check   # fail if docs/freeze.md is not what this code writes

Scheme: commit docs/freeze.md, then put the annotated tag `freeze-1` on that commit, so
the frozen commit does not need to contain its own hash. A run on the test split
(`waypoint.eval.run`, also through `make eval-test`) refuses to start unless:
- the working tree is clean (no modified, staged or untracked files);
- the tag freeze-1 exists;
- HEAD is the tagged commit, or a descendant whose changes since the tag
  (`git diff --name-only freeze-1..HEAD`) touch only docs/*.md, PLAN.md and CLAUDE.md.

run_config.json records the tag, its commit and the actual HEAD. freeze.md holds no time
stamp, so `--check` can regenerate it exactly.
"""
from __future__ import annotations

import argparse
import platform
import re
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from typing import Any

from waypoint.config import DEFAULT_AS_OF, REPO_ROOT

FREEZE_TAG = "freeze-1"
FREEZE_MD = REPO_ROOT / "docs" / "freeze.md"
ALLOWED_AFTER_FREEZE = re.compile(r"^(docs/[^/]+\.md|PLAN\.md|CLAUDE\.md)$")
PACKAGES = ("pydantic", "httpx", "neo4j", "fastapi", "uvicorn", "pytest")


class FreezeError(ValueError):
    """The repository is not at the frozen state; the test split must not run."""


def _git(repo: Path, *args: str) -> tuple[int, str]:
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return p.returncode, p.stdout.strip()


def check_frozen(repo: Path = REPO_ROOT, tag: str = FREEZE_TAG) -> dict[str, str]:
    code, status = _git(repo, "status", "--porcelain")
    if code != 0:
        raise FreezeError(f"git status failed in {repo}")
    if status:
        raise FreezeError("working tree is not clean (commit or remove every change first):\n" + status)
    code, frozen = _git(repo, "rev-parse", "-q", "--verify", f"refs/tags/{tag}^{{commit}}")
    if code != 0 or not frozen:
        raise FreezeError(f"tag {tag} does not exist: commit docs/freeze.md, then tag that commit")
    _, head = _git(repo, "rev-parse", "HEAD")
    if head != frozen:
        code, _ = _git(repo, "merge-base", "--is-ancestor", frozen, head)
        if code != 0:
            raise FreezeError(f"HEAD {head[:10]} is not {tag} or a descendant of it")
        _, changed = _git(repo, "diff", "--name-only", f"{frozen}..{head}")
        bad = [p for p in changed.splitlines() if p and not ALLOWED_AFTER_FREEZE.match(p)]
        if bad:
            raise FreezeError(f"changes since {tag} touch more than docs/*.md, PLAN.md and CLAUDE.md: "
                              + ", ".join(bad))
    return {"freeze_tag": tag, "freeze_commit": frozen, "head": head}


# ---------------------------------------------------------------- docs/freeze.md

def _known_issues(path: Path = REPO_ROOT / "docs" / "safety.md") -> str:
    text = path.read_text(encoding="utf-8")
    start = text.index("## Known issues at freeze")
    end = text.find("\n## ", start + 1)
    return (text[start:] if end < 0 else text[start:end]).rstrip() + "\n"


def collect_info(*, model_answer: str, model_fast: str, embed_model: str, embed_dim: int, llm_provider: str,
                 test_count: int) -> dict[str, Any]:
    from waypoint.answer.system import config_id
    from waypoint.eval import baselines, heldout, judge, safety, twins
    from waypoint.eval import questions as qmod
    from waypoint.eval.safety_check import VERSION as CHECKER
    from waypoint.retrieval.router import LOW_CONFIDENCE

    return {
        "s5_config": config_id(model_answer, model_fast), "s1_config": f"{baselines.PROMPT_VERSION}:{model_answer}",
        "llm_provider": llm_provider, "model_answer": model_answer, "model_fast": model_fast,
        "judge": f"{judge.PROMPT_VERSION} on {model_fast}", "embed_model": embed_model, "embed_dim": embed_dim,
        "low_confidence": LOW_CONFIDENCE, "as_of": DEFAULT_AS_OF.isoformat(), "default_asker": qmod.DEFAULT_ASKER,
        "asker_overrides": dict(sorted(qmod.ASKER_OVERRIDES.items())), "checker": CHECKER,
        "sets": f"{safety.SET_VERSION}, {heldout.SET_VERSION}, {twins.SET_VERSION}",
        "python": platform.python_version(),
        "packages": {p: metadata.version(p) for p in PACKAGES}, "test_count": test_count,
        "known_issues": _known_issues(),
    }


def _pytest_count() -> int:
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q"], cwd=REPO_ROOT,
                         capture_output=True, text=True).stdout
    m = re.search(r"(\d+) tests? collected", out)
    if not m:
        raise RuntimeError("could not count the tests")
    return int(m.group(1))


def info_from_settings() -> dict[str, Any]:
    from waypoint.config import get_settings

    s = get_settings()  # only model names and the embedding dimension are read; no key is printed
    return collect_info(model_answer=s.model_answer, model_fast=s.model_fast, embed_model=s.cohere_embed_model,
                        embed_dim=s.embed_dim, llm_provider=s.llm_provider, test_count=_pytest_count())


def render(info: dict[str, Any]) -> str:
    overrides = ", ".join(f"{q} -> {a}" for q, a in info["asker_overrides"].items())
    pkgs = ", ".join(f"{p} {v}" for p, v in info["packages"].items())
    return f"""# Freeze (PLAN 3.3d)

Generated by `python -m waypoint.eval.freeze`; `--check` verifies it. The frozen commit is the commit tagged
`{FREEZE_TAG}` (annotated tag, created after this file is committed). A test-split run refuses to start
unless the working tree is clean, the tag exists, and HEAD is the tagged commit or a descendant whose
changes touch only docs/*.md, PLAN.md and CLAUDE.md; run_config.json records the tag, its commit and HEAD.

## Configuration

| item | value |
|---|---|
| S5 config id (answer:router:pack:verifier:models) | `{info['s5_config']}` |
| S1 config id | `{info['s1_config']}` |
| S3 | dev only (not run on the test split) |
| LLM provider | {info['llm_provider']} |
| answer model (S1, S5 answers) | {info['model_answer']} |
| router and judge model | {info['model_fast']} |
| judge | {info['judge']} |
| embeddings | {info['embed_model']}, dimension {info['embed_dim']} (Cohere v2 embed; cached in .cache/embeddings/) |
| router low-confidence threshold | {info['low_confidence']} |
| as-of date | {info['as_of']} |
| default asker | {info['default_asker']} |
| asker overrides | {overrides} |
| safety checker | {info['checker']} (sets {info['sets']}) |
| Python | {info['python']} |
| packages | {pkgs} |
| unit tests | {info['test_count']} tests collected (`make test` and `make test-graph` must pass at the freeze) |

## Commands, in order

1. `python -m waypoint.eval.safety --system s5 --set twins` (before the freeze; not the test split)
2. `python -m waypoint.eval.freeze` and commit docs/freeze.md, then `git tag -a {FREEZE_TAG} -m "freeze"` on that
   commit and `python -m waypoint.eval.freeze --check`
3. `mingw32-make eval-test SYSTEM=s5` (after a quota stop, re-run the same command: it resumes from its checkpoint)
4. `mingw32-make eval-test SYSTEM=s1` (same resume rule)
5. `python -m waypoint.eval.bootstrap --a <S5 test run dir> --b <S1 test run dir>` (95% CIs, seed 42,
   10,000 resamples; a difference is claimed only when its interval excludes zero)
6. the author hand-checks the 10% sample of judge_review.csv (docs/test_plan.md)

{info['known_issues']}"""


def check_file(path: Path, info: dict[str, Any]) -> bool:
    return path.is_file() and path.read_text(encoding="utf-8") == render(info)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Write or check docs/freeze.md.")
    p.add_argument("--check", action="store_true", help="fail if docs/freeze.md differs from a fresh render")
    args = p.parse_args(argv)
    info = info_from_settings()
    if args.check:
        if not check_file(FREEZE_MD, info):
            raise SystemExit(f"{FREEZE_MD} is missing or differs from a fresh render")
        print(f"{FREEZE_MD} matches")
        return
    FREEZE_MD.write_text(render(info), encoding="utf-8", newline="\n")
    print(f"wrote {FREEZE_MD}")


if __name__ == "__main__":
    main()
