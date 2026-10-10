import importlib

import pytest

from waypoint.config import DATA_DIR, DEFAULT_AS_OF


@pytest.mark.parametrize("mod", ["graph", "retrieval", "rules", "llm", "eval", "api"])
def test_subpackages_import(mod: str) -> None:
    importlib.import_module(f"waypoint.{mod}")


def test_dataset_present() -> None:
    assert (DATA_DIR / "data" / "csv" / "employees.csv").is_file()
    assert (DATA_DIR / "eval" / "questions.csv").is_file()


def test_as_of_pinned() -> None:
    assert DEFAULT_AS_OF.isoformat() == "2026-10-10"
