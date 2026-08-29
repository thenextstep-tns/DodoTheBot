"""
Run every test case under ``tests/cases`` and report what failed.

Stdlib only, deliberately: the bot's own dependencies are enough to ask of a
box, and a suite nobody can run because the runner isn't installed is a suite
nobody runs. ``tests/test_all.py`` exposes the same cases to pytest for anyone
who has it.

    py -3 tests/run_tests.py            # everything
    py -3 tests/run_tests.py wr tokens  # only cases whose name contains these

Each case is a script that asserts its way down the page and prints what it
checked. They run in separate processes so one crash can't take the rest with
it, and from the repo root so the few that read source files find them.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
CASES = pathlib.Path(__file__).resolve().parent / "cases"


def discover(patterns: list[str]) -> list[pathlib.Path]:
    found = sorted(CASES.glob("test_*.py"))
    if not patterns:
        return found
    return [p for p in found if any(pat.lower() in p.stem.lower() for pat in patterns)]


def main(argv: list[str]) -> int:
    verbose = "-v" in argv
    patterns = [a for a in argv if not a.startswith("-")]
    cases = discover(patterns)
    if not cases:
        print("no cases matched", patterns)
        return 1

    failures: list[tuple[str, str]] = []
    started = time.time()
    for case in cases:
        # UTF-8 forced: several cases print emoji, and a Windows console
        # defaulting to cp1251 would fail them for the wrong reason entirely.
        result = subprocess.run(
            [sys.executable, str(case)],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
            env={**__import__("os").environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
        ok = result.returncode == 0 and "PASS" in (result.stdout or "")
        print(f"{'PASS' if ok else 'FAIL'}  {case.stem}")
        if verbose and result.stdout:
            print("\n".join("      " + line for line in result.stdout.strip().splitlines()))
        if not ok:
            detail = (result.stdout or "") + (result.stderr or "")
            failures.append((case.stem, detail.strip()))

    elapsed = time.time() - started
    print(f"\n{len(cases) - len(failures)}/{len(cases)} passed in {elapsed:.1f}s")
    for name, detail in failures:
        print(f"\n--- {name} " + "-" * (60 - len(name)))
        # The tail carries the assertion; the head is usually just progress.
        print("\n".join(detail.splitlines()[-25:]))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
