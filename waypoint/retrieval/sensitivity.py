"""Sensitivity rule for chunk lines (PLAN 1.3, CLAUDE.md rule 6).

A line is restricted, with a subject employee, when either
  (a) it is an Employee-record row Employment status / Current work mode / Notice
      period of a profile (subject: the profile's employee), or
  (b) it matches STATUS_RE (a person on leave, serving notice, resigning) and a
      subject resolves: the last employee full name before the match, else the
      document's own employee (profile, resume).
Lines with no resolvable subject stay public, so general text ("Employees serving
notice work from office") is public. Policy documents are never passed in here.
"""
from __future__ import annotations

import re

RECORD_FIELDS = ("Employment status", "Current work mode", "Notice period")

STATUS_RE = re.compile(
    r"\b(on (maternity |paternity |sabbatical )?leave"
    r"|started (maternity|paternity) leave"
    r"|serving (a |his |her |their )?(\d+-day )?notice"
    r"|serves a \d+-day notice"
    r"|resign(s|ed)"
    r"|last working day)\b",
    re.IGNORECASE,
)


def restricted_subject(line: str, *, doc_subject: str | None, in_record: bool,
                       names: dict[str, str]) -> str | None:
    """Employee id the line is restricted for, or None if the line is public."""
    if in_record:
        return doc_subject if line.startswith(tuple(f"{f}:" for f in RECORD_FIELDS)) else None
    match = STATUS_RE.search(line)
    if not match:
        return None
    before = [(line.rfind(name, 0, match.start()), eid) for name, eid in names.items()]
    named = [(pos, eid) for pos, eid in before if pos >= 0]
    return max(named)[1] if named else doc_subject
