r"""Builds tests/fixtures/s5_golden_freeze1.json: the fixed mock-LLM run of S5
(s5_golden_scenario.py) on the **freeze-1** code. Run once, by hand, with Neo4j up and no
LLM calls (the client is scripted):

    git worktree add <tmp>\wp-freeze1 freeze-1
    cd <tmp>\wp-freeze1
    set PYTHONPATH=<tmp>\wp-freeze1
    C:\MINI_PROJECT_GRAPH_RAG\.venv\Scripts\python.exe C:\MINI_PROJECT_GRAPH_RAG\tests\fixtures\build_s5_golden.py ^
        --expect-root <tmp>\wp-freeze1 --env-file C:\MINI_PROJECT_GRAPH_RAG\.env
    git worktree remove <tmp>\wp-freeze1

The script is run by path so that this folder (the scenario) comes from the current tree
and `waypoint` from the worktree; `--expect-root` makes it refuse to write if `waypoint`
was imported from anywhere else. The worktree has no .env, so the Neo4j settings are read
from `--env-file` (only to open the driver; nothing is printed). tests/test_ablations.py runs
the same scenario on the current code and compares the JSON byte for byte.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import s5_golden_scenario as scenario  # noqa: E402

import waypoint  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

from waypoint.config import Settings  # noqa: E402

OUT = Path(__file__).with_name("s5_golden_freeze1.json")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--expect-root", type=Path, required=True, help="the freeze-1 worktree")
    p.add_argument("--env-file", type=Path, required=True, help="the main tree's .env (Neo4j settings)")
    p.add_argument("--out", type=Path, default=OUT)
    args = p.parse_args(argv)
    imported = Path(waypoint.__file__).resolve().parent.parent
    if imported != args.expect_root.resolve():
        raise SystemExit(f"waypoint imported from {imported}, not {args.expect_root}: set PYTHONPATH")
    print(f"waypoint from {imported}")
    st = Settings(_env_file=args.env_file)
    driver = GraphDatabase.driver(st.neo4j_uri, auth=(st.neo4j_username, st.neo4j_password.get_secret_value()))
    try:
        with tempfile.TemporaryDirectory() as tmp:
            text = scenario.dumps(scenario.run_all(driver, Path(tmp)))
    finally:
        driver.close()
    args.out.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {args.out} ({len(scenario.CASES)} cases)")


if __name__ == "__main__":
    main()
