"""Turn the Markdown corpus into Documents, PolicySections and Chunks. PLAN 1.3.

Pure: reads data/zenvora_kb, touches neither Neo4j nor the network.
  policy      one chunk per "## N. Heading" (also a PolicySection), plus one header
              chunk (metadata block + history); table of contents dropped; every
              chunk prefixed "<id> <title> (version V, effective YYYY-MM-DD)."
  profile     one chunk per "##" heading, prefixed "<name> (<id>), <title>, <dept>."
  resume      one chunk per "###" job, plus one summary chunk for the other sections
  department, project, product   the whole page as one chunk
  company     one chunk per "##" heading, plus the text before the first heading
Tables become one sentence per row. Lines that state a specific person's status,
leave or notice period move to a separate "restricted" chunk (see sensitivity.py).
Chunk id: "<doc_id>::<section>::<part>", part "0" or "restricted".
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from waypoint.config import DATA_DIR
from waypoint.graph.load import read_csv
from waypoint.retrieval.mentions import Target, employee_names, find_mentions
from waypoint.retrieval.sensitivity import restricted_subject

NUMBERED = re.compile(r"^(\d+)\. (.+)$")
SEPARATOR_CELL = re.compile(r"^:?-+:?$")
BOILERPLATE = ("*Fictional document created", "*Resume:")


@dataclass(frozen=True)
class Doc:
    doc_id: str
    doc_type: str
    path: str
    title: str
    describes_label: str
    describes_id: str


@dataclass(frozen=True)
class PolicySection:
    section_id: str
    policy_id: str
    section_no: int
    heading: str


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    doc_type: str
    section: str
    part: str
    position: int
    heading: str
    prefix: str
    body: str
    sensitivity: str
    subject_id: str | None
    section_id: str | None
    mentions: tuple[Target, ...]

    @property
    def text(self) -> str:
        """What is embedded and full-text indexed."""
        return f"{self.prefix}\n{self.body}" if self.prefix else self.body

    @property
    def text_hash(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Corpus:
    docs: tuple[Doc, ...]
    sections: tuple[PolicySection, ...]
    chunks: tuple[Chunk, ...]


# ---------------------------------------------------------------- markdown helpers


def slug(heading: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")


def table_to_sentences(lines: list[str]) -> list[str]:
    """Markdown table -> one sentence per data row ("Header: value; ...")."""
    rows = [[c.strip().replace("**", "") for c in ln.strip().strip("|").split("|")] for ln in lines]
    header, data = rows[0], [r for r in rows[1:] if not all(SEPARATOR_CELL.match(c) for c in r)]
    out = []
    for r in data:
        if header == ["Field", "Value"]:
            pairs = [f"{r[0]}: {r[1]}"] if r[1] else []
        else:
            pairs = [f"{h}: {v}" for h, v in zip(header, r) if v]
        if pairs:
            out.append("; ".join(pairs).rstrip(".") + ".")
    return out


def clean(lines: Iterable[str]) -> list[str]:
    """Strip markup and boilerplate; tables become sentences; drop blank lines."""
    out: list[str] = []
    table: list[str] = []
    for raw in [*lines, ""]:
        line = raw.strip()
        if line.startswith("|"):
            table.append(line)
            continue
        if table:
            out.extend(table_to_sentences(table))
            table = []
        if line.startswith(BOILERPLATE):
            continue
        line = line.replace("**", "").replace(" | ", "; ")
        if len(line) > 1 and line.startswith("*") and line.endswith("*"):
            line = line[1:-1].strip()
        line = line.lstrip("#").strip()
        if line:
            out.append(line)
    return out


def split_by(lines: list[str], marker: str) -> list[tuple[str | None, list[str]]]:
    """Split on headings "<marker> X"; the first entry holds the text before any heading."""
    sections: list[tuple[str | None, list[str]]] = [(None, [])]
    for line in lines:
        if line.startswith(marker + " "):
            sections.append((line[len(marker) + 1:].strip(), []))
        else:
            sections[-1][1].append(line)
    return sections


def _read(path: Path) -> tuple[str, list[str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    title = next(ln[2:].strip() for ln in lines if ln.startswith("# "))
    return title, [ln for ln in lines if not ln.startswith("# ")]


# ---------------------------------------------------------------- chunk assembly


@dataclass
class _Builder:
    doc: Doc
    subject: str | None = None  # the employee a profile or resume is about
    restrict: bool = True
    chunks: list[Chunk] = field(default_factory=list)

    def add(self, section: str, heading: str, prefix: str, lines: list[str], *,
            record: bool = False, section_id: str | None = None) -> None:
        public: list[str] = []
        restricted: list[str] = []
        subjects: set[str] = set()
        for line in lines:
            who = restricted_subject(line, doc_subject=self.subject, in_record=record,
                                     names=employee_names()) if self.restrict else None
            if who:
                restricted.append(line)
                subjects.add(who)
            else:
                public.append(line)
        if len(subjects) > 1:
            raise ValueError(f"{self.doc.doc_id}::{section}: restricted lines about {sorted(subjects)}")
        for part, body, subject in (("0", public, None), ("restricted", restricted, next(iter(subjects), None))):
            if not body:
                continue
            text = "\n".join(body)
            self.chunks.append(Chunk(
                chunk_id=f"{self.doc.doc_id}::{section}::{part}", doc_id=self.doc.doc_id,
                doc_type=self.doc.doc_type, section=section, part=part, position=len(self.chunks),
                heading=heading, prefix=prefix, body=text,
                sensitivity="restricted" if subject else "public", subject_id=subject,
                section_id=section_id, mentions=find_mentions(text)))


def _unique(key: str, seen: set[str]) -> str:
    out, i = key, 2
    while out in seen:
        out, i = f"{key}-{i}", i + 1
    seen.add(out)
    return out


def _rel(path: Path) -> str:
    return path.relative_to(DATA_DIR).as_posix()


def _policies() -> tuple[list[Doc], list[PolicySection], list[Chunk]]:
    meta = {r["policy_id"]: r for r in read_csv("policies")}
    docs, sections, chunks = [], [], []
    for path in sorted(DATA_DIR.glob("policies/*/*.md")):
        pid = path.name.split("_")[0]
        m = meta[pid]
        title, lines = _read(path)
        base = f"{pid} {m['title']} (version {m['version']}, effective {m['effective_date']})."
        doc = Doc(pid, "policy", _rel(path), title, "Policy", pid)
        b = _Builder(doc, restrict=False)
        parts = split_by(lines, "##")
        header = clean(parts[0][1])
        numbered = []
        for heading, body in parts[1:]:
            assert heading is not None
            if heading == "Policy History":
                header += ["Policy History", *clean(body)]
            elif heading == "Table of Contents":
                continue
            elif match := NUMBERED.match(heading):
                numbered.append((int(match.group(1)), match.group(2).strip(), body))
            else:
                raise ValueError(f"{path.name}: unexpected heading {heading!r}")
        b.add("header", "Header and history", f"{base} Header and history.", header)
        for n, heading, body in numbered:
            section = PolicySection(f"{pid}#{n}", pid, n, heading)
            sections.append(section)
            b.add(f"s{n}", heading, f"{base} Section {n}: {heading}.", clean(body),
                  section_id=section.section_id)
        docs.append(doc)
        chunks += b.chunks
    return docs, sections, chunks


def _people() -> tuple[list[Doc], list[Chunk]]:
    emp = {r["employee_id"]: r for r in read_csv("employees")}
    dept = {r["department_id"]: r["name"] for r in read_csv("departments")}
    docs, chunks = [], []
    for path in sorted(DATA_DIR.glob("employees/profiles/*.md")):
        eid = path.name.split("_")[0]
        e = emp[eid]
        title, lines = _read(path)
        base = f"{e['full_name']} ({eid}), {e['title']}, {dept[e['department_id']]}."
        b = _Builder(Doc(f"profile:{eid}", "profile", _rel(path), title, "Employee", eid), subject=eid)
        seen: set[str] = set()
        for heading, body in split_by(lines, "##")[1:]:
            assert heading is not None
            b.add(_unique(slug(heading), seen), heading, f"{base} {heading}.", clean(body),
                  record=heading == "Employee record")
        docs.append(b.doc)
        chunks += b.chunks
    for path in sorted(DATA_DIR.glob("employees/resumes_md/*.md")):
        eid = path.name.split("_")[0]
        title, lines = _read(path)
        base = f"{emp[eid]['full_name']} ({eid}) resume."
        b = _Builder(Doc(f"resume:{eid}", "resume", _rel(path), title, "Employee", eid), subject=eid)
        parts = split_by(lines, "##")
        summary, jobs = clean(parts[0][1]), []
        for heading, body in parts[1:]:
            if heading == "Experience":
                sub = split_by(body, "###")
                summary += clean(sub[0][1])
                jobs = [(h, clean(jb)) for h, jb in sub[1:]]
            else:
                summary += [f"{heading}.", *clean(body)]
        b.add("summary", "Summary", base, summary)
        for i, (heading, body) in enumerate(jobs, 1):
            b.add(f"job-{i}", heading or "", f"{base} Experience: {heading}.", body)
        docs.append(b.doc)
        chunks += b.chunks
    return docs, chunks


def _pages() -> tuple[list[Doc], list[Chunk]]:
    kinds = (("departments/*.md", "department", "dept", "Department"),
             ("projects/PJ*.md", "project", "project", "Project"),
             ("projects/products/*.md", "product", "product", "Product"))
    docs, chunks = [], []
    for pattern, doc_type, prefix, label in kinds:
        for path in sorted(DATA_DIR.glob(pattern)):
            ident = path.name.split("_")[0]
            text = path.read_text(encoding="utf-8").splitlines()
            title = next(ln[2:].strip() for ln in text if ln.startswith("# "))
            b = _Builder(Doc(f"{prefix}:{ident}", doc_type, _rel(path), title, label, ident))
            b.add("page", title, "", clean(text))
            docs.append(b.doc)
            chunks += b.chunks
    return docs, chunks


def _company() -> tuple[list[Doc], list[Chunk]]:
    (company,) = read_csv("company")
    docs, chunks = [], []
    for path in sorted(DATA_DIR.glob("company/*.md")):
        title, lines = _read(path)
        b = _Builder(Doc(f"company:{path.stem}", "company", _rel(path), title,
                         "Company", company["company_id"]))
        parts = split_by(lines, "##")
        intro = clean(parts[0][1])
        if intro:
            b.add("intro", title, f"{title}.", intro)
        seen = {"intro"}
        for heading, body in parts[1:]:
            assert heading is not None
            b.add(_unique(slug(heading), seen), heading, f"{title}. {heading}.", clean(body))
        docs.append(b.doc)
        chunks += b.chunks
    return docs, chunks


@cache
def build_corpus() -> Corpus:
    p_docs, sections, p_chunks = _policies()
    docs, chunks = list(p_docs), list(p_chunks)
    for part_docs, part_chunks in (_people(), _pages(), _company()):
        docs += part_docs
        chunks += part_chunks
    return Corpus(tuple(docs), tuple(sections), tuple(chunks))
