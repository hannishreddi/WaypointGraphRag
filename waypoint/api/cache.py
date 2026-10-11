"""Answer cache for `make serve` (PLAN 3.1): one JSON file per answered question.

Key = question, asker_id, as_of, system name and the system's `config_id`. For S5 the
config_id is `answer-vN:router-vN:pack-vN:verify-vN:<model_answer>:<model_fast>`, so a
prompt, pack, verifier or model change misses instead of serving a stale answer. Only
successful answers are stored; errors and quota stops raise before `put`.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from pathlib import Path
from typing import Any

from waypoint.config import REPO_ROOT

DEFAULT_DIR = REPO_ROOT / ".cache" / "answers"


class AnswerCache:
    def __init__(self, directory: Path = DEFAULT_DIR) -> None:
        self.dir = directory

    @staticmethod
    def key(question: str, asker_id: str, as_of: date, system: str, config_id: str) -> str:
        raw = json.dumps([question, asker_id, as_of.isoformat(), system, config_id])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> dict[str, Any] | None:
        try:
            return json.loads((self.dir / f"{key}.json").read_text(encoding="utf-8"))["response"]
        except (OSError, ValueError, KeyError):
            return None

    def put(self, key: str, response: dict[str, Any], **meta: Any) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.dir / f"{key}.tmp"
        tmp.write_text(json.dumps({"meta": meta, "response": response}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        os.replace(tmp, self.dir / f"{key}.json")
