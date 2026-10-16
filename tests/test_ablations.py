"""3.3e ablations (waypoint.eval.ablations): default S5 is untouched, each ablation removes
exactly its one component, and the router-cache probe makes no calls."""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

import pytest
from neo4j import Driver

from tests.fixtures import s5_golden_scenario as sc
from waypoint.answer import system as s5_module
from waypoint.answer.refusal import RESTRICTED_REFUSAL
from waypoint.answer.system import S5Waypoint, config_id
from waypoint.config import REPO_ROOT
from waypoint.eval import safety
from waypoint.eval.ablations import (ABLATIONS, ANONYMOUS, MAX_QUERY, FailingClient, ProbeMiss, S5NoAccessFilter,
                                     S5NoIdentity, S5NoRouter, S5NoVerifier, TextSearchRouter, ablation_config_id)
from waypoint.eval.run import run_eval
from waypoint.eval.systems import SYSTEMS
from waypoint.retrieval import access, plan
from waypoint.retrieval.router import Router

GOLDEN = Path(__file__).parent / "fixtures" / "s5_golden_freeze1.json"
NAMES = ("s5-norouter", "s5-noverifier", "s5-noidentity", "s5-noaccess")
ORIGINALS = {"verify": s5_module.verify, "visible": access.visible, "evaluate_rule": plan.evaluate_rule}


def _restored() -> bool:
    return (s5_module.verify is ORIGINALS["verify"] and access.visible is ORIGINALS["visible"]
            and plan.evaluate_rule is ORIGINALS["evaluate_rule"])


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True)


def test_no_system_code_changed_since_freeze() -> None:
    if _git("rev-parse", "--verify", "-q", "freeze-1^{commit}").returncode != 0:
        pytest.skip("tag freeze-1 not present")
    diff = _git("diff", "--name-only", "freeze-1", "--", "waypoint/", ":!waypoint/eval")
    assert diff.returncode == 0 and diff.stdout.strip() == ""


def test_config_ids() -> None:
    frozen = re.search(r"S5 config id[^|]*\| `([^`]+)`", (REPO_ROOT / "docs" / "freeze.md").read_text(encoding="utf-8"))
    assert frozen and config_id("gemini-3.1-flash-lite", "gemini-3.5-flash-lite") == frozen[1]
    inner = S5Waypoint(object(), model_answer="gemini-3.1-flash-lite", model_fast="gemini-3.5-flash-lite",  # type: ignore[arg-type]
                       driver=None)  # type: ignore[arg-type]
    assert inner.config_id == frozen[1]
    for cls in ABLATIONS.values():
        a = cls(S5Waypoint(object(), model_answer="gemini-3.1-flash-lite", model_fast="gemini-3.5-flash-lite",  # type: ignore[arg-type]
                           driver=None))  # type: ignore[arg-type]
        assert a.config_id == ablation_config_id(cls.ablation, frozen[1]) == f"{cls.ablation}-v1:{frozen[1]}"
        assert a.name == f"s5-{cls.ablation}" and a.dev_only
    assert inner.config_id == frozen[1] and inner.name == "s5"  # wrapping does not change S5


def test_registered_and_kept_off_the_test_split(tmp_path: Path) -> None:
    assert set(NAMES) <= set(SYSTEMS) and set(NAMES) <= set(safety.ACCESS)
    assert S5NoAccessFilter.safety_only and not any(c.safety_only for c in (S5NoRouter, S5NoVerifier, S5NoIdentity))
    dummy = S5Waypoint(object(), model_answer="a", model_fast="f", driver=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="dev split only"):
        run_eval(split="test", system=S5NoVerifier(dummy), judge=None, out_root=tmp_path)
    with pytest.raises(ValueError, match="safety-set baseline"):
        run_eval(split="dev", system=S5NoAccessFilter(dummy), judge=None, out_root=tmp_path)


def test_text_search_router() -> None:
    r = TextSearchRouter().route("  What does the travel policy say about hotels?  ", "ZV-1006")
    assert r.intent == "policy_text" and r.decision.confidence == 1.0 and not r.low_confidence
    assert [(s.op, s.args) for s in r.decision.plan] == [("text_search", {"query": "What does the travel policy say about hotels?"})]
    assert r.decision.alternative is None and not r.decision.restricted_fact and r.llm_calls == 0
    assert len(TextSearchRouter().route("x" * 400, "ZV-1006").decision.plan[0].args["query"]) == MAX_QUERY


def test_probe_detects_misses_and_writes_nothing(tmp_path: Path) -> None:
    q = "Who does Divya Krishnamurthy report to?"
    with pytest.raises(ProbeMiss):
        Router(FailingClient(), model="fast", cache_dir=tmp_path).route(q, "ZV-1006")  # type: ignore[arg-type]
    assert not any(tmp_path.iterdir())
    Router(sc.ScriptedClient(sc.route("fact_list_count", sc.MANAGER, entities=["ZV-1004"])), model="fast",  # type: ignore[arg-type]
           cache_dir=tmp_path).route(q, "ZV-1006")
    hit = Router(FailingClient(), model="fast", cache_dir=tmp_path).route(q, "ZV-1006")  # type: ignore[arg-type]
    assert hit.cached and hit.llm_calls == 0
    with pytest.raises(ProbeMiss):  # another asker is another key
        Router(FailingClient(), model="fast", cache_dir=tmp_path).route(q, ANONYMOUS)  # type: ignore[arg-type]


# ---------------------------------------------------------------- mock-LLM runs (Neo4j)

def _wrap(cls: type, driver: Driver, tmp: Path, *replies: str, embed: bool = False) -> tuple[object, sc.ScriptedClient]:
    llm = sc.ScriptedClient(*replies)
    return cls(sc.make_s5(driver, tmp, llm, sc.chunk_embedder(driver) if embed else None)), llm


def _run_every_ablation(driver: Driver, tmp: Path) -> None:
    a, _ = _wrap(S5NoRouter, driver, tmp / "r", sc.gen("She is on leave.", "passage1"), embed=True)
    a.answer(sc.POOJA_Q, sc.HR, sc.AS_OF)
    a, _ = _wrap(S5NoVerifier, driver, tmp / "v", sc.route("fact_list_count", sc.MANAGER, entities=["ZV-1004"]),
                 sc.gen("Ravi Kumar, since 2019.", "step1"))
    a.answer(sc.DIVYA_Q, sc.HR, sc.AS_OF)
    a, _ = _wrap(S5NoIdentity, driver, tmp / "i", sc.route("personal_rule", sc.NOTICE, entities=[sc.TARUN],
                                                             restricted_fact=True))
    a.answer(sc.TARUN_Q, sc.HR, sc.AS_OF)
    a, _ = _wrap(S5NoAccessFilter, driver, tmp / "a", sc.route("policy_text", sc.POOJA_TEXT, entities=[sc.POOJA]),
                 sc.gen("She is on leave.", "passage1"), embed=True)
    a.answer(sc.POOJA_Q, sc.PEER, sc.AS_OF)
    assert _restored()


@pytest.mark.neo4j
def test_s5_is_byte_identical_to_freeze1_before_and_after_ablations(driver: Driver, tmp_path: Path) -> None:
    golden = GOLDEN.read_text(encoding="utf-8")
    assert sc.dumps(sc.run_all(driver, tmp_path / "before")) == golden
    _run_every_ablation(driver, tmp_path / "ablations")
    assert sc.dumps(sc.run_all(driver, tmp_path / "after")) == golden


@pytest.mark.neo4j
def test_no_router_makes_no_router_call(driver: Driver, tmp_path: Path) -> None:
    a, llm = _wrap(S5NoRouter, driver, tmp_path, sc.gen("She is on leave.", "passage1"), embed=True)
    r = a.answer(sc.POOJA_Q, sc.HR, sc.AS_OF)
    assert [c["model"] for c in llm.calls] == ["answer"] and r.route == "policy_text"
    assert r.trace["router_calls"] == 0 and sc.POOJA_LEAVE in r.trace["passages"].values()  # access as S5 (HR)


@pytest.mark.neo4j
def test_no_verifier_keeps_the_first_answer(driver: Driver, tmp_path: Path) -> None:
    a, llm = _wrap(S5NoVerifier, driver, tmp_path, sc.route("fact_list_count", sc.MANAGER, entities=["ZV-1004"]),
                   sc.gen("Ravi Kumar, since 2019.", "step1"))
    r = a.answer(sc.DIVYA_Q, sc.HR, sc.AS_OF)
    assert r.answer == "Ravi Kumar, since 2019." and r.trace["verifier"] == "pass" and len(llm.calls) == 2
    assert _restored()  # S5 itself regenerates this answer: golden case "regenerated"


@pytest.mark.neo4j
def test_no_identity_fails_closed(driver: Driver, tmp_path: Path) -> None:
    a, llm = _wrap(S5NoIdentity, driver, tmp_path / "hr", sc.route("personal_rule", sc.NOTICE, entities=[sc.TARUN],
                                                                     restricted_fact=True))
    r = a.answer(sc.TARUN_Q, sc.HR, sc.AS_OF)  # S5 answers HR (golden "restricted_rule_hr")
    assert r.answer == RESTRICTED_REFUSAL and r.trace["refusal"] == "restricted_rule" and len(llm.calls) == 1
    assert ANONYMOUS in llm.calls[0]["prompt"] and sc.HR not in llm.calls[0]["prompt"]
    induction = [{"op": "INDUCTION_END", "args": {"subject": "asker"}}]
    a, llm = _wrap(S5NoIdentity, driver, tmp_path / "me",
                   sc.route("personal_rule", induction, needs_identity=True),
                   sc.gen("I can't find that in Waypoint's sources."))
    r = a.answer("When does my induction end?", sc.ARJUN, sc.AS_OF)  # no KeyError for the unknown subject
    prompt = llm.calls[1]["prompt"]
    assert "insufficient_input" in prompt and "not a known employee" in prompt and sc.ARJUN not in prompt
    assert r.answer == "I can't find that in Waypoint's sources." and _restored()


@pytest.mark.neo4j
def test_no_access_filter_exposes_restricted_chunks_only(driver: Driver, tmp_path: Path) -> None:
    a, _ = _wrap(S5NoAccessFilter, driver, tmp_path / "text", sc.route("policy_text", sc.POOJA_TEXT, entities=[sc.POOJA]),
                 sc.gen("She is on leave.", "passage1"), embed=True)
    r = a.answer(sc.POOJA_Q, sc.PEER, sc.AS_OF)  # S5 never shows the peer this chunk (golden "text_peer")
    assert sc.POOJA_LEAVE in r.trace["passages"].values()
    a, llm = _wrap(S5NoAccessFilter, driver, tmp_path / "rule", sc.route("personal_rule", sc.NOTICE, entities=[sc.TARUN],
                                                                           restricted_fact=True))
    r = a.answer(sc.TARUN_Q, sc.ARJUN, sc.AS_OF)  # the rule engine still refuses
    assert r.answer == RESTRICTED_REFUSAL and len(llm.calls) == 1 and _restored()


@pytest.mark.neo4j
def test_patches_are_restored_after_an_error(driver: Driver, tmp_path: Path) -> None:
    for cls in (S5NoVerifier, S5NoIdentity, S5NoAccessFilter):
        a, _ = _wrap(cls, driver, tmp_path / cls.ablation)  # no scripted replies: the router call fails
        with pytest.raises(IndexError):
            a.answer(sc.DIVYA_Q, sc.HR, sc.AS_OF)
        assert _restored()
    with tempfile.TemporaryDirectory() as t:  # and S5 is still the frozen S5
        assert sc.dumps(sc.run_all(driver, Path(t))) == GOLDEN.read_text(encoding="utf-8")
