"""Expected chunking values computed from the Markdown files only (never from the chunker or graph)."""
from __future__ import annotations

import re
from pathlib import Path

from waypoint.config import DATA_DIR

NUMBERED = re.compile(r"^## (\d+)\. (.+)$", re.MULTILINE)


def md(pattern: str) -> list[Path]:
    return sorted(DATA_DIR.glob(pattern))


def policy_files() -> list[Path]:
    return md("policies/*/*.md")


def numbered_sections(path: Path) -> list[tuple[int, str]]:
    return [(int(n), h.strip()) for n, h in NUMBERED.findall(path.read_text(encoding="utf-8"))]


def headings(path: Path, level: int = 2) -> list[str]:
    marks = "#" * level
    return [ln[level + 1:].strip() for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.startswith(marks + " ")]


def file_id(path: Path) -> str:
    """ZV-1031_pooja-agarwal.md -> ZV-1031; ZEN-POL-003_leave-policy.md -> ZEN-POL-003."""
    return path.name.split("_")[0]
