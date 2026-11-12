#!/usr/bin/env python3
"""Run discovered policy modules in parallel processes.

The module list is every ``test_*.py`` under the tests directory. A new file
runs without a workflow edit. Each module is its own ``unittest discover``
process, so an import error fails that module and the run.
"""

from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def discovered_modules(directory: Path) -> list[str]:
    return sorted(path.stem for path in directory.glob("test_*.py") if path.is_file())


def _run_module(directory: Path, cwd: Path, name: str) -> tuple[str, int, str]:
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                str(directory),
                "-p",
                f"{name}.py",
                "-v",
            ],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        return name, 1, str(error)
    return name, result.returncode, result.stdout + result.stderr


def run_policy_tests(
    directory: Path, *, cwd: Path | None = None, workers: int | None = None
) -> int:
    directory = directory.resolve()
    cwd = (cwd or directory).resolve()
    names = discovered_modules(directory)
    if not names:
        print("policy discovery found no tests", file=sys.stderr)
        return 1
    if workers is None:
        workers = os.cpu_count() or 1
    workers = max(1, min(int(workers), len(names)))
    failures = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_run_module, directory, cwd, name) for name in names]
        for future in as_completed(futures):
            name, code, output = future.result()
            if code == 0:
                print(f"ok {name}", flush=True)
                continue
            failures += 1
            print(f"FAIL {name} exit={code}", flush=True)
            if output:
                print(output, end="" if output.endswith("\n") else "\n", flush=True)
    if failures:
        print(
            f"policy tests failed: {failures} of {len(names)} modules",
            file=sys.stderr,
        )
        return 1
    print(f"policy tests ok: {len(names)} modules", flush=True)
    return 0


def main() -> int:
    return run_policy_tests(ROOT / "tests", cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main())
