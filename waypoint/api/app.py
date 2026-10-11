"""FastAPI app (PLAN 3.1): POST /ask, GET /employees, GET /health and the static page.

S5 is built once at startup (lifespan), or injected by tests through `create_app`.
Endpoints are plain `def` (FastAPI's thread pool); one lock serialises the LLM work of
/ask, so concurrent requests cannot interleave on the client-side rate limiter. A cache
hit is answered without taking the lock.

asker_id is client-supplied and not authenticated: anyone can pick any identity. This is
a local demo (bound to 127.0.0.1 by `make serve`); access control is only as good as the
identity claim.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from neo4j.exceptions import Neo4jError, ServiceUnavailable
from pydantic import BaseModel, ConfigDict, Field

from waypoint.api.cache import AnswerCache
from waypoint.config import DEFAULT_AS_OF
from waypoint.contract import Response, System
from waypoint.graph.db import run_read
from waypoint.llm.client import LLMError, QuotaStop

log = logging.getLogger("waypoint.api")
STATIC_DIR = Path(__file__).resolve().parent / "static"
CDN_HOST = "cdn.jsdelivr.net"  # Cytoscape.js, pinned with SRI in static/index.html
CSP = ("default-src 'self'; "
       f"script-src 'self' https://{CDN_HOST}; "
       "style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")

EMPLOYEES_QUERY = """
MATCH (e:Employee)
OPTIONAL MATCH (e)-[:WORKS_IN]->(d:Department)
RETURN e.employee_id AS id, e.name AS name, e.title AS title, d.name AS department
ORDER BY name, id"""


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=1000)
    asker_id: str = Field(min_length=1, max_length=20)
    as_of: date = DEFAULT_AS_OF


class AskResponse(Response):
    cached: bool = False  # extra, like usage and latency_ms: served from the answer cache


class Employee(BaseModel):
    id: str
    name: str
    title: str
    department: str | None = None


class Services:
    """Everything /ask needs, built once."""

    def __init__(self, system: System, driver: Any, cache: AnswerCache,
                 employees: list[dict[str, Any]] | None = None, *, owns_driver: bool = False) -> None:
        self.system, self.driver, self.cache = system, driver, cache
        self._employees = employees
        self.owns_driver = owns_driver
        self.lock = threading.Lock()  # one /ask at a time through the LLM client

    def employees(self) -> list[dict[str, Any]]:
        """Public fields only (never status). Loaded from the graph on first use."""
        if self._employees is None:
            self._employees = run_read(self.driver, EMPLOYEES_QUERY)
        return self._employees


def _error(status: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": detail})


def create_app(*, system: System | None = None, driver: Any = None, cache: AnswerCache | None = None,
               employees: list[dict[str, Any]] | None = None) -> FastAPI:
    """With `system=None` the lifespan builds S5 from settings (the served app)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if getattr(app.state, "services", None) is None:
            from waypoint.answer.system import S5Waypoint

            s5 = S5Waypoint.from_settings()
            app.state.services = Services(s5, s5.driver, cache or AnswerCache(), owns_driver=True)
        try:
            app.state.services.employees()
        except Exception as exc:  # noqa: BLE001 - Neo4j may come up later; /employees retries
            log.warning("employees not loaded at startup: %s", type(exc).__name__)
        yield
        if app.state.services.owns_driver:
            app.state.services.driver.close()

    app = FastAPI(title="Waypoint", lifespan=lifespan)
    app.state.services = None
    if system is not None:
        app.state.services = Services(system, driver if driver is not None else getattr(system, "driver", None),
                                      cache or AnswerCache(), employees)

    def services() -> Services:
        return app.state.services

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Any:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error on %s", request.url.path)
        return _error(500, "Internal error; see the server log.")

    @app.post("/ask", response_model=AskResponse)
    def ask(req: AskRequest, fresh: bool = False) -> Any:
        svc = services()
        try:
            known = {e["id"] for e in svc.employees()}
        except (ServiceUnavailable, Neo4jError, OSError):
            return _error(503, "The graph database is unreachable; run `make up`.")
        if req.asker_id not in known:
            return JSONResponse(status_code=422, content={"detail": [
                {"type": "value_error", "loc": ["body", "asker_id"], "msg": "unknown asker_id",
                 "input": req.asker_id}]})
        system = svc.system
        key = svc.cache.key(req.question, req.asker_id, req.as_of, system.name,
                            getattr(system, "config_id", system.name))
        if not fresh and (hit := svc.cache.get(key)) is not None:
            return AskResponse.model_validate({**hit, "cached": True})
        try:
            with svc.lock:
                resp = system.answer(req.question, req.asker_id, req.as_of)
        except QuotaStop:
            log.warning("LLM quota stop on /ask", exc_info=True)
            return _error(503, "The LLM quota is used up for now (free tier). Try again later.")
        except LLMError:
            log.warning("LLM error on /ask", exc_info=True)
            return _error(502, "The language model failed to answer. Try again.")
        except (ServiceUnavailable, Neo4jError):
            log.warning("Neo4j error on /ask", exc_info=True)
            return _error(503, "The graph database is unreachable; run `make up`.")
        out = resp.model_dump(mode="json")
        svc.cache.put(key, out, question=req.question, asker_id=req.asker_id, as_of=req.as_of.isoformat(),
                      system=system.name, config_id=getattr(system, "config_id", system.name))
        return AskResponse.model_validate({**out, "cached": False})

    @app.get("/employees", response_model=list[Employee])
    def employees() -> Any:
        try:
            return services().employees()
        except (ServiceUnavailable, Neo4jError, OSError):
            return _error(503, "The graph database is unreachable; run `make up`.")

    @app.get("/health")
    def health() -> JSONResponse:
        drv = services().driver
        try:
            if drv is None:
                raise OSError("no driver")
            drv.verify_connectivity()
            return JSONResponse({"neo4j": True})
        except Exception:  # noqa: BLE001 - any connection/auth failure means "down"
            return JSONResponse({"neo4j": False}, status_code=503)

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()
