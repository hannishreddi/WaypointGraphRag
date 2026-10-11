"""API and UI (PLAN 3.1): contract, validation, errors, cache, serialisation, CSP, static page."""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from neo4j import Driver

from tests.test_llm_structured import ScriptedLLM
from waypoint.answer.system import REFUSAL, S5Waypoint
from waypoint.api.app import CDN_HOST, create_app
from waypoint.api.cache import AnswerCache
from waypoint.contract import GraphCitation, Response
from waypoint.llm.client import DailyQuotaExceeded, LLMError
from waypoint.retrieval.router import Router

STATIC = Path(__file__).resolve().parent.parent / "waypoint" / "api" / "static"
EMPLOYEES = [{"id": "ZV-1042", "name": "Arjun Menon", "title": "Software Engineer", "department": "Engineering"},
             {"id": "ZV-1006", "name": "Lakshmi", "title": "Head of People & Culture", "department": "HR"}]
CONTRACT = set(Response.model_fields) - {"trace"} | {"cached"}
ASK = {"question": "Who does Divya Krishnamurthy report to?", "asker_id": "ZV-1042"}


class FakeSystem:
    """Stands in for S5: counts calls, can be slow, can raise."""

    name = "fake"

    def __init__(self, answer: str = "Karthik Naidu.", *, exc: Exception | None = None, delay: float = 0.0,
                 config_id: str = "v1") -> None:
        self.text, self.exc, self.delay, self.config_id = answer, exc, delay, config_id
        self.calls, self.active, self.max_active = 0, 0, 0
        self._mu = threading.Lock()

    def answer(self, question: str, asker_id: str, as_of: date) -> Response:
        with self._mu:
            self.calls += 1
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(self.delay)
            if self.exc:
                raise self.exc
            return Response(answer=self.text, route="fact_list_count", as_of=as_of, confidence=0.9,
                            citations=[GraphCitation(path="ZV-1004 -REPORTS_TO-> ZV-1003")],
                            trace={"secret": "diagnostics"})
        finally:
            with self._mu:
                self.active -= 1


def client(tmp_path: Path, system: object, **kw: object) -> TestClient:
    app = create_app(system=system, employees=EMPLOYEES, cache=AnswerCache(tmp_path / "answers"), **kw)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------- contract and validation

def test_contract_shape_and_default_as_of(tmp_path: Path) -> None:
    r = client(tmp_path, FakeSystem()).post("/ask", json=ASK)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == CONTRACT and "trace" not in body
    assert body["as_of"] == "2026-10-10" and body["cached"] is False
    assert body["citations"] == [{"type": "graph", "path": "ZV-1004 -REPORTS_TO-> ZV-1003"}]


@pytest.mark.parametrize("payload", [
    {**ASK, "asker_id": "ZV-9999"},
    {**ASK, "asker_id": "zv-1042 OR 1=1"},
    {**ASK, "question": "   "},
    {**ASK, "as_of": "10/10/2026"},
    {**ASK, "extra": 1},
    {"question": "hi"},
])
def test_invalid_input_is_422_without_calling_the_system(tmp_path: Path, payload: dict) -> None:
    fake = FakeSystem()
    r = client(tmp_path, fake).post("/ask", json=payload)
    assert r.status_code == 422 and fake.calls == 0


def test_unknown_asker_names_the_field(tmp_path: Path) -> None:
    r = client(tmp_path, FakeSystem()).post("/ask", json={**ASK, "asker_id": "ZV-9999"})
    assert r.status_code == 422 and r.json()["detail"][0]["loc"] == ["body", "asker_id"]


def test_html_in_the_answer_is_returned_as_plain_data(tmp_path: Path) -> None:
    evil = '<script>alert("x")</script><img src=x onerror=alert(1)>'
    r = client(tmp_path, FakeSystem(evil)).post("/ask", json=ASK)
    assert r.headers["content-type"].startswith("application/json")
    assert r.json()["answer"] == evil  # JSON string, untouched; the page renders it with textContent


# ---------------------------------------------------------------- errors

@pytest.mark.parametrize("exc,status,needle", [
    (DailyQuotaExceeded("quota PerDay for gemini-x at /secret/path"), 503, "quota"),
    (LLMError("blocked: finishReason SAFETY, request id abc"), 502, "language model"),
    (RuntimeError("Traceback (most recent call last): boom"), 500, "internal error"),
])
def test_errors_are_mapped_and_never_leak(tmp_path: Path, exc: Exception, status: int, needle: str) -> None:
    c = client(tmp_path, FakeSystem(exc=exc))
    r = c.post("/ask", json=ASK)
    assert r.status_code == status and needle in r.json()["detail"].lower()
    text = r.text
    assert "Traceback" not in text and "secret" not in text and "request id" not in text and "boom" not in text
    assert not list((tmp_path / "answers").glob("*.json"))  # errors are never cached


# ---------------------------------------------------------------- answer cache

def test_cache_hit_miss_and_fresh(tmp_path: Path) -> None:
    fake = FakeSystem()
    c = client(tmp_path, fake)
    first = c.post("/ask", json=ASK).json()
    second = c.post("/ask", json=ASK).json()
    assert (first["cached"], second["cached"], fake.calls) == (False, True, 1)
    assert {k: v for k, v in second.items() if k != "cached"} == {k: v for k, v in first.items() if k != "cached"}
    assert c.post("/ask", json={**ASK, "asker_id": "ZV-1006"}).json()["cached"] is False  # other asker
    assert c.post("/ask", json={**ASK, "as_of": "2026-10-19"}).json()["cached"] is False  # other date
    assert fake.calls == 3
    fresh = c.post("/ask?fresh=1", json=ASK).json()
    assert fresh["cached"] is False and fake.calls == 4
    assert c.post("/ask", json=ASK).json()["cached"] is True and fake.calls == 4


def test_cache_invalidated_by_a_version_change(tmp_path: Path) -> None:
    old = FakeSystem(config_id="answer-v2:router-v2:pack-v3:verify-v2:m1:m2")
    client(tmp_path, old).post("/ask", json=ASK)
    new = FakeSystem(config_id="answer-v2:router-v2:pack-v4:verify-v2:m1:m2")
    r = client(tmp_path, new).post("/ask", json=ASK).json()
    assert r["cached"] is False and new.calls == 1
    same = FakeSystem(config_id=old.config_id)
    assert client(tmp_path, same).post("/ask", json=ASK).json()["cached"] is True and same.calls == 0


def test_cache_key_covers_question_asker_date_and_config() -> None:
    k = AnswerCache.key
    base = k("q", "ZV-1042", date(2026, 10, 10), "s5", "cfg")
    assert len({base, k("q2", "ZV-1042", date(2026, 10, 10), "s5", "cfg"),
                k("q", "ZV-1006", date(2026, 10, 10), "s5", "cfg"),
                k("q", "ZV-1042", date(2026, 10, 19), "s5", "cfg"),
                k("q", "ZV-1042", date(2026, 10, 10), "s5", "cfg2")}) == 5


def test_s5_config_id_carries_every_version() -> None:
    from waypoint.answer.generate import PROMPT_VERSION as A
    from waypoint.answer.pack import VERSION as P
    from waypoint.answer.verify import VERSION as V
    from waypoint.retrieval.router import PROMPT_VERSION as R
    cfg = S5Waypoint(ScriptedLLM(), model_answer="ma", model_fast="mf", driver=None).config_id  # type: ignore[arg-type]
    assert all(part in cfg.split(":") for part in (A, R, P, V, "ma", "mf"))


# ---------------------------------------------------------------- serialisation

def test_concurrent_requests_are_serialised(tmp_path: Path) -> None:
    fake = FakeSystem(delay=0.3)
    c = client(tmp_path, fake)
    codes: list[int] = []
    threads = [threading.Thread(target=lambda i=i: codes.append(
        c.post("/ask?fresh=1", json={**ASK, "question": f"Question {i}?"}).status_code)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert codes == [200, 200, 200] and fake.calls == 3 and fake.max_active == 1


# ---------------------------------------------------------------- employees, health, headers

def test_employees_injected(tmp_path: Path) -> None:
    assert client(tmp_path, FakeSystem()).get("/employees").json() == EMPLOYEES


class DeadDriver:
    def verify_connectivity(self) -> None:
        raise OSError("connection refused")


def test_health_reports_neo4j_down(tmp_path: Path) -> None:
    r = client(tmp_path, FakeSystem(), driver=DeadDriver()).get("/health")
    assert r.status_code == 503 and r.json() == {"neo4j": False}


def test_page_has_csp_and_no_inline_script(tmp_path: Path) -> None:
    r = client(tmp_path, FakeSystem()).get("/")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    csp = dict(d.strip().split(" ", 1) for d in r.headers["content-security-policy"].split(";") if d.strip())
    assert csp["default-src"] == "'self'"
    assert csp["script-src"].split() == ["'self'", f"https://{CDN_HOST}"]
    assert "unsafe-inline" not in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"


# ---------------------------------------------------------------- static page

def test_static_page_never_uses_html_sinks() -> None:
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
        assert sink not in js and sink not in html, sink
    assert "textContent" in js
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), "inline <script> block"
    assert not re.search(r"\son[a-z]+\s*=", html), "inline event handler"


def test_cdn_script_is_pinned_with_sri() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    tags = re.findall(r"<script[^>]*src=\"https://[^>]*>", html)
    assert len(tags) == 1
    tag = tags[0]
    assert re.search(rf'src="https://{re.escape(CDN_HOST)}/npm/cytoscape@\d+\.\d+\.\d+/dist/cytoscape\.min\.js"', tag)
    assert re.search(r'integrity="sha384-[A-Za-z0-9+/]{64}"', tag) and 'crossorigin="anonymous"' in tag
    # Cytoscape injects a <style> unless this id exists; CSP style-src 'self' would block it.
    assert 'id="__________cytoscape_stylesheet"' in html


# ---------------------------------------------------------------- with Neo4j and the real S5

def s5_client(driver: Driver, tmp_path: Path, *replies: str) -> tuple[TestClient, ScriptedLLM]:
    llm = ScriptedLLM(*replies)
    system = S5Waypoint(llm, model_answer="answer", model_fast="fast", driver=driver,
                        router=Router(llm, model="fast", cache_dir=tmp_path / "router"))
    app = create_app(system=system, cache=AnswerCache(tmp_path / "answers"))
    return TestClient(app, raise_server_exceptions=False), llm


def route_json(intent: str, plan: list | None = None, **kw: object) -> str:
    return json.dumps({"intent": intent, "entities": [], "needs_identity": False, "confidence": 0.95,
                       "plan": plan or [], **kw})


@pytest.mark.neo4j
def test_employees_from_graph_public_fields_only(driver: Driver, tmp_path: Path) -> None:
    c, _ = s5_client(driver, tmp_path)
    rows = c.get("/employees").json()
    assert len(rows) == 42 and all(set(r) == {"id", "name", "title", "department"} for r in rows)
    assert {"id": "ZV-1006"}.items() <= next(r for r in rows if r["id"] == "ZV-1006").items()
    assert not any(v in json.dumps(rows).lower() for v in ("on_leave", "serving_notice", "status"))
    assert c.post("/ask", json={**ASK, "asker_id": "ZV-9999"}).status_code == 422


@pytest.mark.neo4j
def test_health_up(driver: Driver, tmp_path: Path) -> None:
    c, _ = s5_client(driver, tmp_path)
    assert c.get("/health").json() == {"neo4j": True}


@pytest.mark.neo4j
def test_contract_with_s5(driver: Driver, tmp_path: Path) -> None:
    plan = [{"op": "manager", "args": {"employee_id": "ZV-1004"}}]
    c, llm = s5_client(driver, tmp_path, route_json("fact_list_count", plan, entities=["ZV-1004"]),
                       json.dumps({"answer": "Karthik Naidu.", "cited_ids": ["step1"]}))
    body = c.post("/ask", json={**ASK, "asker_id": "ZV-1006"}).json()
    assert set(body) == CONTRACT and body["answer"] == "Karthik Naidu." and body["route"] == "fact_list_count"
    assert {"type": "graph", "path": "ZV-1004 -REPORTS_TO-> ZV-1003"} in body["citations"]
    assert {n["id"] for n in body["subgraph"]["nodes"]} >= {"ZV-1004", "ZV-1003"}
    assert body["usage"]["input_tokens"] == 20 and len(llm.calls) == 2


@pytest.mark.neo4j
def test_peer_asking_about_poojas_leave_is_refused(driver: Driver, tmp_path: Path) -> None:
    plan = [{"op": "WORK_MODE", "args": {"subject": "ZV-1031"}}]
    c, llm = s5_client(driver, tmp_path, route_json("personal_rule", plan, entities=["ZV-1031"]),
                       json.dumps({"answer": "I can't share Pooja Agarwal's leave details.", "cited_ids": ["step1"]}))
    body = c.post("/ask", json={"question": "Is Pooja Agarwal on leave?", "asker_id": "ZV-1042"}).json()
    prompt = llm.calls[1]["prompt"]
    assert "status: restricted" in prompt
    assert not any(s in prompt.lower() for s in ("maternity", "on_leave", "on leave until"))
    assert body["citations"] == [] and "can't share" in body["answer"]


@pytest.mark.neo4j
def test_refuse_route_makes_no_generator_call(driver: Driver, tmp_path: Path) -> None:
    c, llm = s5_client(driver, tmp_path, route_json("refuse"))
    body = c.post("/ask", json={"question": "What is Tarun Mehta's salary?", "asker_id": "ZV-1042"}).json()
    assert body["answer"] == REFUSAL and body["route"] == "refuse" and body["subgraph"]["nodes"] == []
    assert len(llm.calls) == 1 and llm.calls[0]["model"] == "fast"
