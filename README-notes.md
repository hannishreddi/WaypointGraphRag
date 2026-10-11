# README notes (collected for the 3.4 README)

## Demo security (3.1)
- **No authentication.** `asker_id` in `POST /ask` and the identity dropdown are client-supplied: anyone who can reach the server can claim to be anyone, including HR. The access filter (rule 6) is only as good as that claim. This is a local demo, not a deployable service.
- `make serve` binds `127.0.0.1` only. Do not expose it on a network. Without make (plain Windows): `powershell -ExecutionPolicy Bypass -File scripts\serve.ps1` runs the same server (venv python, uvicorn on 127.0.0.1:8000, no `--reload`).
- Answer and citation text is rendered with `textContent`, never as HTML (tested). The page sends a Content-Security-Policy (`default-src 'self'`; scripts from `'self'` and `cdn.jsdelivr.net` only; no inline scripts or styles). Cytoscape.js is pinned to an exact version with an SRI hash.
- Errors return a short message (502 LLM error, 503 quota or Neo4j down, 500 otherwise); stack traces go to the server log only.
- The serve answer cache (`.cache/answers/`) stores answers per question, asker, as-of and S5 config; answers that depend on restricted facts are cached under the asker who was allowed to see them, so another asker never gets them from the cache.

## Demo (3.2)
- Script, observed answers and screenshot placeholders: `docs/demo.md`. Automated: `python -m waypoint.api.demo` against a running server (cached re-runs make no LLM calls).
- Rule answers draw their evidence: the cited policy section and a dashed **derived (rule case)** edge. Derived edges and node details are Waypoint's reasoning, not data stored in the graph, and node details never contain status, leave or notice, whoever asks.
- Known issue: HR asking about restricted profile text can get an unnecessary refusal (generator over-refusal; retrieval is correct). See docs/demo.md.
