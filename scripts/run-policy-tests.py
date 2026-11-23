#!/usr/bin/env python3
"""Run discovered policy modules in parallel processes.

The module list is every ``test_*.py`` under the tests directory. A new file
runs without a workflow edit. Each module is its own ``unittest discover``
process, so an import error fails that module and the run.
"""

from __future__ import annotations

import argparse
import importlib.metadata
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
    directory: Path, *, cwd: Path | None = None, workers: int | None = None,
    names: list[str] | None = None,
) -> int:
    directory = directory.resolve()
    cwd = (cwd or directory).resolve()
    if names is None:
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


def check_tools(root: Path) -> int:
    for line in (root / "requirements-policy.txt").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        name, expected = line.split()[0].split("==")
        try:
            installed = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            installed = "missing"
        if installed != expected:
            print(f"policy requires {name}=={expected} (found {installed})", file=sys.stderr)
            return 2

    import yaml

    workflow = yaml.safe_load((root / ".github/workflows/policy-ci.yml").read_text())
    for step in workflow["jobs"]["policy"]["steps"]:
        pins = step.get("with", {})
        if "python-version" in pins:
            version = f"{sys.version_info.major}.{sys.version_info.minor}"
            if version != pins["python-version"]:
                print(f"policy requires Python {pins['python-version']} (found {version})", file=sys.stderr)
                return 2
        if "go-version" in pins:
            result = subprocess.run(["go", "env", "GOVERSION"], capture_output=True, text=True)
            if result.returncode or result.stdout.strip() != "go" + pins["go-version"]:
                print(f"policy requires Go {pins['go-version']} on PATH", file=sys.stderr)
                return 2
    return 0


def changed_modules(root: Path) -> list[str]:
    def git(*args: str) -> bytes:
        return subprocess.check_output(["git", *args], cwd=root)

    # Include committed branch changes, the index, working tree and new files.
    # A local-only or shallow checkout can still check its working tree.
    base = subprocess.run(["git", "merge-base", "HEAD", "origin/master"], cwd=root,
                          capture_output=True, text=True)
    revision = base.stdout.strip() if base.returncode == 0 else "HEAD"
    paths = (git("diff", "--no-renames", "--name-only", "-z", revision) +
             git("ls-files", "--others", "--exclude-standard", "-z"))
    changed = {Path(os.fsdecode(path)) for path in paths.split(b"\0") if path}
    names = {path.name for path in changed}
    selected = {"test_check_policy_entry"}
    for module in (root / "tests").glob("test_*.py"):
        if module.relative_to(root) in changed:
            selected.add(module.stem)
            continue
        source = module.read_text()
        if any(name in source for name in names):
            selected.add(module.stem)
    return sorted(selected)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    options = parser.add_mutually_exclusive_group()
    options.add_argument("--check-tools", action="store_true")
    options.add_argument("--changed", action="store_true")
    args = parser.parse_args()
    if args.check_tools:
        return check_tools(ROOT)
    names = changed_modules(ROOT) if args.changed else None
    return run_policy_tests(ROOT / "tests", cwd=ROOT, names=names)


if __name__ == "__main__":
    sys.exit(main())
