"""Read-only Cypher guard (CLAUDE.md rule 3).

Neo4j Community has no read-only user, so answer queries run with
session.execute_read AND must pass this guard first. Keywords are matched as
whole words, case-insensitively, after string literals, backtick-quoted
identifiers and comments are blanked out. It is deliberately conservative: a
property or parameter named like a keyword (n.set, $call) is also rejected.
"""
from __future__ import annotations

import re

FORBIDDEN = ("CREATE", "MERGE", "DELETE", "DETACH", "SET", "REMOVE", "DROP", "LOAD CSV", "CALL")
_FORBIDDEN_RE = re.compile(
    r"\b(" + "|".join(k.replace(" ", r"\s+") for k in FORBIDDEN) + r")\b", re.IGNORECASE
)


class UnsafeCypherError(ValueError):
    """Raised when a query is not provably read-only."""


def _strip_literals_and_comments(cypher: str) -> str:
    """Replace strings, `quoted` identifiers and comments with spaces."""
    out: list[str] = []
    i, n = 0, len(cypher)
    while i < n:
        c = cypher[i]
        if c in "'\"`":
            j = i + 1
            while j < n and cypher[j] != c:
                j += 2 if cypher[j] == "\\" and c != "`" else 1
            if j >= n:
                raise UnsafeCypherError("unterminated string or quoted identifier")
            i = j + 1
            out.append(" ")
        elif cypher.startswith("//", i):
            j = cypher.find("\n", i)
            i = n if j == -1 else j
            out.append(" ")
        elif cypher.startswith("/*", i):
            j = cypher.find("*/", i + 2)
            if j == -1:
                raise UnsafeCypherError("unterminated block comment")
            i = j + 2
            out.append(" ")
        else:
            out.append(c)
            i += 1
    return "".join(out)


def check_read_only(cypher: str) -> None:
    """Raise UnsafeCypherError if the query contains a forbidden keyword."""
    match = _FORBIDDEN_RE.search(_strip_literals_and_comments(cypher))
    if match:
        keyword = " ".join(match.group(1).upper().split())
        raise UnsafeCypherError(f"forbidden keyword in read query: {keyword}")


def is_read_only(cypher: str) -> bool:
    try:
        check_read_only(cypher)
    except UnsafeCypherError:
        return False
    return True
