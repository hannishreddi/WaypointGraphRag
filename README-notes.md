# README notes (collected for the 3.4 README)

## Demo security (3.1)
- **No authentication.** `asker_id` in `POST /ask` and the identity dropdown are client-supplied: anyone who can reach the server can claim to be anyone, including HR. The access filter (rule 6) is only as good as that claim. This is a local demo, not a deployable service.
- `make serve` binds `127.0.0.1` only. Do not expose it on a network.
- Answer and citation text is rendered with `textContent`, never as HTML (tested). The page sends a Content-Security-Policy (`default-src 'self'`; scripts from `'self'` and `cdn.jsdelivr.net` only; no inline scripts or styles). Cytoscape.js is pinned to an exact version with an SRI hash.
- Errors return a short message (502 LLM error, 503 quota or Neo4j down, 500 otherwise); stack traces go to the server log only.
- The serve answer cache (`.cache/answers/`) stores answers per question, asker, as-of and S5 config; answers that depend on restricted facts are cached under the asker who was allowed to see them, so another asker never gets them from the cache.
