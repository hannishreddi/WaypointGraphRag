"""3.3d freeze machinery: docs/freeze.md and the test-split guard. No LLM, no test split.

The guard runs on temporary git repos (never this one): a run on the test split needs a
clean tree, the tag freeze-1, and HEAD at the tag or at a descendant whose changes since
the tag touch only docs/*.md, PLAN.md and CLAUDE.md.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from waypoint.answer.system import S5Waypoint, config_id
from waypoint.eval import run as runmod
from waypoint.eval.freeze import FREEZE_TAG, FreezeError, check_frozen, collect_info, render


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    git(tmp_path, "config", "commit.gpgsign", "false")
    (tmp_path / "docs").mkdir()
    (tmp_path / "waypoint").mkdir()
    (tmp_path / "docs" / "freeze.md").write_text("frozen\n")
    (tmp_path / "waypoint" / "a.py").write_text("x = 1\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def tag(repo: Path) -> str:
    git(repo, "tag", "-a", FREEZE_TAG, "-m", "freeze")
    return git(repo, "rev-parse", "HEAD")


def commit(repo: Path, path: str, text: str) -> str:
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_text(text)
    git(repo, "add", path)
    git(repo, "commit", "-q", "-m", f"edit {path}")
    return git(repo, "rev-parse", "HEAD")


def test_at_the_tag_passes(repo: Path) -> None:
    sha = tag(repo)
    assert check_frozen(repo) == {"freeze_tag": FREEZE_TAG, "freeze_commit": sha, "head": sha}


def test_missing_tag_refuses(repo: Path) -> None:
    with pytest.raises(FreezeError, match="tag freeze-1"):
        check_frozen(repo)


def test_dirty_tree_refuses(repo: Path) -> None:
    tag(repo)
    (repo / "waypoint" / "a.py").write_text("x = 2\n")
    with pytest.raises(FreezeError, match="not clean"):
        check_frozen(repo)


def test_untracked_file_refuses(repo: Path) -> None:
    tag(repo)
    (repo / "notes.txt").write_text("scratch\n")
    with pytest.raises(FreezeError, match="not clean"):
        check_frozen(repo)


@pytest.mark.parametrize("path", ["docs/results.md", "PLAN.md", "CLAUDE.md"])
def test_docs_only_descendant_passes(repo: Path, path: str) -> None:
    sha = tag(repo)
    head = commit(repo, path, "after the freeze\n")
    assert check_frozen(repo) == {"freeze_tag": FREEZE_TAG, "freeze_commit": sha, "head": head}


@pytest.mark.parametrize("path", ["waypoint/a.py", "docs/sub/notes.md", "docs/data.csv", "eval/safety.csv",
                                  "README.md"])
def test_other_descendant_changes_refuse(repo: Path, path: str) -> None:
    tag(repo)
    commit(repo, "docs/results.md", "ok\n")
    commit(repo, path, "changed\n")
    with pytest.raises(FreezeError, match=path.replace(".", r"\.")):
        check_frozen(repo)


def test_head_not_descended_from_the_tag_refuses(repo: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, "docs/freeze.md", "second\n")
    tag(repo)
    git(repo, "checkout", "-q", base)  # before the tag
    with pytest.raises(FreezeError, match="not freeze-1 or a descendant"):
        check_frozen(repo)


def test_run_eval_checks_the_freeze_before_loading_test_questions(monkeypatch: pytest.MonkeyPatch,
                                                                  tmp_path: Path) -> None:
    from tests.test_eval_resume import Counter, QuotaSystem

    def refuse() -> dict[str, str]:
        raise FreezeError("working tree is not clean")

    def never(*a: object, **kw: object) -> None:
        raise AssertionError("test questions loaded before the freeze check")

    monkeypatch.setattr(runmod, "check_frozen", refuse)
    monkeypatch.setattr(runmod.qmod, "load_questions", never)
    with pytest.raises(FreezeError):
        runmod.run_eval(split="test", system=QuotaSystem(Counter()), judge=None, out_root=tmp_path)


def test_main_refuses_test_split_when_not_frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAYPOINT_EVAL_TEST", "1")
    monkeypatch.setattr(runmod, "check_frozen", lambda: (_ for _ in ()).throw(FreezeError("no tag freeze-1")))
    with pytest.raises(SystemExit, match="freeze"):
        runmod.main(["--split", "test", "--system", "echo", "--no-judge"])


# ---------------------------------------------------------------- docs/freeze.md


def info() -> dict:
    return collect_info(model_answer="gemini-3.1-flash-lite", model_fast="gemini-3.5-flash-lite",
                        embed_model="embed-v5.0-fast", embed_dim=1024, llm_provider="gemini", test_count=123)


def test_config_id_matches_the_system() -> None:
    """freeze.md's S5 config id is the one the running system records (no LLM call made)."""
    s5 = S5Waypoint(object(), model_answer="m-answer", model_fast="m-fast", driver=None)  # type: ignore[arg-type]
    assert s5.config_id == config_id("m-answer", "m-fast") == "answer-v2:router-v4:pack-v5:verify-v2:m-answer:m-fast"


def test_render_is_deterministic_and_complete() -> None:
    text = render(info())
    assert text == render(info())
    for needle in ("answer-v2:router-v4:pack-v5:verify-v2:gemini-3.1-flash-lite:gemini-3.5-flash-lite",
                   "baseline-v1:gemini-3.1-flash-lite", "embed-v5.0-fast", "1024", "2026-10-10", "ZV-1006",
                   "safety-check-v3", "judge-v1", "123 tests", "freeze-1", "make eval-test SYSTEM=s5",
                   "make eval-test SYSTEM=s1", "Known issues at freeze", "A01", "S11", "F5"):
        assert needle in text, needle
    assert "api_key" not in text.lower() and "secret" not in text.lower()


def test_check_mode(tmp_path: Path) -> None:
    from waypoint.eval.freeze import check_file

    path = tmp_path / "freeze.md"
    path.write_text(render(info()), encoding="utf-8")
    assert check_file(path, info())
    path.write_text("edited\n", encoding="utf-8")
    assert not check_file(path, info())
