"""Whole-module shard assignment and plan digest."""
from __future__ import annotations

import configparser
import re
from pathlib import Path, PurePosixPath

from .config import SHA
from .support import ROOT, collection_config_ok, context_ok, encoded, git, require, safe_module, sha
from .timing import resolve_ordinary_weights


def assign_ordinary(modules, count, weights):
    """Stride when weights is None. Otherwise longest-processing-time.

    The tie break is (load, index). A positive weight makes the first
    ``count`` heaviest modules fill distinct shards, because an empty shard
    has load 0 and index 0 is not preferred once it is no longer empty.
    """
    if weights is None:
        grouped = [list(modules[i::count]) for i in range(count)]
    else:
        ranked = sorted(modules, key=lambda module: (-weights[module], module))
        grouped = [[] for _ in range(count)]
        loads = [0] * count
        for module in ranked:
            index = min(range(count), key=lambda shard: (loads[shard], shard))
            grouped[index].append(module)
            loads[index] += weights[module]
        for bucket in grouped:
            bucket.sort()
    require(all(grouped), "ordinary weight assignment left an empty shard")
    return [{"id": f"ordinary-{i:03d}", "modules": grouped[i]} for i in range(count)]


def plan(source, context, count, serial, weights=None, timing=None):
    """Select whole tracked modules before importing pytest or product code.

    ``weights`` or ``timing`` rebalance ordinary shards and stay outside the
    plan digest. Missing or unusable timing keeps the module-count stride.
    """
    source = source.resolve()
    require(Path(git(source, "rev-parse", "--show-toplevel").decode().strip()).resolve()
            == source, "source must be the exact Git repository root")
    require(not git(source, "status", "--porcelain", "--untracked-files=no"),
            "tracked source is dirty")
    context_ok(context)
    revision = git(source, "rev-parse", "HEAD").decode().strip()
    require(SHA.fullmatch(revision), "source is not an exact commit")
    config_path = source / "pytest.ini"
    require(not config_path.is_symlink(), "pytest config is a symlink")
    config = configparser.ConfigParser(interpolation=None)
    config.read_string(config_path.read_text())
    require(config.sections() == ["pytest"]
            and collection_config_ok(dict(config["pytest"])),
            "unsupported pytest collection configuration")
    tracked = git(source, "ls-files", "-z").decode().split("\0")[:-1]
    require("pytest.ini" in tracked, "pytest config is not tracked")
    modules = sorted(p for p in tracked if p.startswith("tests/")
                     and PurePosixPath(p).name.startswith("test_") and p.endswith(".py"))
    require(modules and all(safe_module(p) for p in modules), "empty or unsafe test inventory")
    actual = sorted(p.relative_to(source).as_posix()
                    for p in (source / "tests").rglob("test_*.py"))
    require(modules == actual, "tracked and on-disk module inventories differ")
    tracked_python = sorted(p for p in tracked if p.startswith("tests/") and p.endswith(".py"))
    disk_python = sorted(p.relative_to(source).as_posix()
                         for p in (source / "tests").rglob("*.py"))
    require(tracked_python == disk_python, "untracked or missing test Python input")
    untracked = git(source, "ls-files", "--others", "--exclude-standard", "-z",
                    "--", "tests").decode().split("\0")
    require(not any(p.endswith(".py") for p in untracked), "untracked test Python input")
    # The supported pytest.ini fixes confcutdir at source. Root conftest and
    # Python helpers below tests can execute before any selected test module.
    root_conftest = source / "conftest.py"
    collection_python = list(tracked_python)
    if root_conftest.exists() or root_conftest.is_symlink():
        require("conftest.py" in tracked, "untracked root conftest input")
        collection_python.append("conftest.py")
    for name in collection_python:
        path = source / name
        require(not any(p.is_symlink() for p in (path, *path.parents)
                        if p != source.parent), "test path contains a symlink")
        require(path.is_file() and path.resolve().is_relative_to(source),
                "test path escaped source or is missing")
    hashes = {name: sha((source / name).read_bytes()) for name in modules}
    require(len(set(serial)) == len(serial) and set(serial) <= set(modules),
            "serial modules are duplicate or outside the inventory")
    ordinary = [p for p in modules if p not in serial]
    require(type(count) is int and 1 <= count <= len(ordinary), "invalid shard capacity")
    used = resolve_ordinary_weights(ordinary, weights, timing)
    assignments = assign_ordinary(ordinary, count, used)
    if serial:
        assignments.append({"id": "serial", "modules": list(serial)})
    result = {
        "schema": 1, "kind": "ops-pytest-module-plan",
        "source_revision": revision, "context": context,
        "pytest_ini_sha256": sha(config_path.read_bytes()),
        "entry_sha256": sha((source / "scripts/run-pytest-parallel.sh").read_bytes()),
        "recorder_sha256": sha((ROOT / "scripts/lens_report.py").read_bytes()),
        "modules": hashes, "assignments": assignments,
    }
    result["plan_sha256"] = sha(encoded(result))
    if used is not None:
        result["ordinary_weights"] = {module: used[module] for module in ordinary}
    return result


def validate_plan(value):
    required = {"schema", "kind", "source_revision", "context", "pytest_ini_sha256", "entry_sha256",
                "recorder_sha256", "modules", "assignments", "plan_sha256"}
    require(set(value) == required and value["schema"] == 1
            and value["kind"] == "ops-pytest-module-plan", "invalid plan schema")
    expected = dict(value)
    digest = expected.pop("plan_sha256")
    require(sha(encoded(expected)) == digest, "plan digest mismatch")
    require(SHA.fullmatch(value["source_revision"]), "invalid source revision")
    context_ok(value["context"])
    modules = value["modules"]
    require(isinstance(modules, dict) and modules
            and all(safe_module(m) and re.fullmatch(r"[0-9a-f]{64}", h)
                    for m, h in modules.items()), "invalid module inventory")
    seen, ids = [], []
    for item in value["assignments"]:
        require(set(item) == {"id", "modules"} and item["modules"],
                "empty or malformed assignment")
        require(re.fullmatch(r"ordinary-[0-9]{3,}|serial", item["id"]),
                "invalid assignment id")
        ids.append(item["id"])
        seen.extend(item["modules"])
    require(len(ids) == len(set(ids)) and sorted(seen) == sorted(modules),
            "assignments omit or duplicate modules")
    return value
