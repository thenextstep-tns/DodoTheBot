"""
The same cases, exposed to pytest for anyone who has it.

The suite's own runner (``tests/run_tests.py``) is stdlib-only on purpose, so
this file is a bridge rather than the source of truth: it hands pytest one test
per case file, each run in its own process exactly as the runner does.

    pytest tests/            # if pytest is installed
    py -3 tests/run_tests.py # always works
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CASES = sorted((pathlib.Path(__file__).resolve().parent / "cases").glob("test_*.py"))


@pytest.mark.parametrize("case", CASES, ids=[c.stem for c in CASES])
def test_case(case: pathlib.Path) -> None:
    result = subprocess.run(
        [sys.executable, str(case)],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
    )
    output = (result.stdout or "") + (result.stderr or "")
    # A case that exits clean without announcing itself has usually had its
    # assertions skipped by an early return, which is worth failing on.
    assert result.returncode == 0, output
    assert "PASS" in (result.stdout or ""), output
