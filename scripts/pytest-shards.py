#!/usr/bin/env python3
"""Plan complete Ops modules and inspect ordinary shard evidence, without running tests.

This primitive is not connected to build.yml. It never supplies release acceptance:
native obligations, skip policy and every other existing gate remain separate.
"""
from __future__ import annotations

import argparse
import configparser
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
SHA = re.compile(r"[0-9a-f]{40}")
EXPECTED_CONFIG = {
    "testpaths": "tests", "python_files": "test_*.py",
    "python_functions": "test_*", "asyncio_mode": "auto",
}
IDENTITY_FIELDS = ("policy_revision", "board_revision", "run_id", "run_attempt",
                   "runner_os", "runner_arch", "runner_image")
FILES = ("metadata.json", "events.jsonl", "pytest-exit-code.txt",
         "pytest-start-unix-ns.txt", "pytest-finish-unix-ns.txt", "selection.json")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode()


def git(source, *args):
    return subprocess.check_output(["git", "-C", str(source), *args],
                                   stderr=subprocess.PIPE)


def safe_module(name):
    path = PurePosixPath(name)
    return (isinstance(name, str) and path.as_posix() == name
            and not path.is_absolute() and ".." not in path.parts
            and len(path.parts) >= 2 and path.parts[0] == "tests"
            and path.name.startswith("test_") and path.suffix == ".py"
            and "::" not in name and not any(ord(c) < 32 for c in name))


def context_ok(context):
    require(set(context) == set(IDENTITY_FIELDS), "incomplete or extra run identity")
    for key in ("policy_revision", "board_revision"):
        require(isinstance(context[key], str) and SHA.fullmatch(context[key]),
                f"invalid {key}")
    for key in ("run_id", "run_attempt"):
        require(isinstance(context[key], str) and re.fullmatch(r"[1-9][0-9]*", context[key]),
                f"invalid {key}")
    for key in ("runner_os", "runner_arch", "runner_image"):
        require(isinstance(context[key], str) and context[key].strip()
                and context[key] != "UNKNOWN", f"missing {key}")


def plan(source, context, count, serial):
    """Select whole tracked modules before importing pytest or product code."""
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
            and dict(config["pytest"]) == EXPECTED_CONFIG,
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
    assignments = [
        {"id": f"ordinary-{i:03d}", "modules": ordinary[i::count]}
        for i in range(count)
    ]
    if serial:
        assignments.append({"id": "serial", "modules": sorted(serial)})
    result = {
        "schema": 1, "kind": "ops-pytest-module-plan",
        "source_revision": revision, "context": context,
        "pytest_ini_sha256": sha(config_path.read_bytes()),
        "entry_sha256": sha((source / "scripts/run-pytest-parallel.sh").read_bytes()),
        "recorder_sha256": sha((ROOT / "scripts/lens_report.py").read_bytes()),
        "modules": hashes, "assignments": assignments,
    }
    result["plan_sha256"] = sha(encoded(result))
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


def read_json(path):
    require(path.is_file() and not path.is_symlink(), f"missing or symlink evidence: {path.name}")
    return json.loads(path.read_text())


def load_timing():
    spec = importlib.util.spec_from_file_location("existing_pytest_timing",
                                                 ROOT / "scripts/pytest-timing.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inspect_session(directory, value, assignment, *, expected_empty=False):
    """Validate immutable invocation binding before consuming passive case evidence."""
    require(directory.is_dir() and not directory.is_symlink(), "invalid evidence directory")
    for name in FILES:
        require((directory / name).is_file() and not (directory / name).is_symlink(),
                f"missing or symlink evidence: {name}")
    metadata = read_json(directory / "metadata.json")
    selection = read_json(directory / "selection.json")
    reference = assignment is None
    modules = ["tests"] if reference else assignment["modules"]
    role = "reference" if reference else assignment["id"]
    require(set(selection) == {"plan_sha256", "assignment_id", "modules", "pytest_argv",
                               "pytest_addopts"}
            and selection["plan_sha256"] == value["plan_sha256"]
            and selection["assignment_id"] == role and selection["modules"] == modules
            and selection["pytest_addopts"] in ("", "--durations=25"),
            "selection does not match the exact plan")
    argv = selection["pytest_argv"]
    suffix = ["-m", "pytest", *(["--collect-only"] if reference else []), "-q", *modules]
    require(isinstance(argv, list) and len(argv) == len(suffix) + 1
            and isinstance(argv[0], str) and argv[0] and argv[1:] == suffix,
            "unexpected pytest arguments or filtering")
    require(metadata.get("source_revision") == value["source_revision"]
            and metadata.get("policy_revision") == value["context"]["policy_revision"]
            and metadata.get("source_tracked_dirty") is False
            and metadata.get("recorder_sha256") == value["recorder_sha256"]
            and metadata.get("entry") == "scripts/run-pytest-parallel.sh"
            and metadata.get("entry_sha256") == value["entry_sha256"]
            and metadata.get("serial") is True, "source/policy/recorder identity mismatch")
    identity = metadata.get("identity", {})
    mapping = {"GITHUB_RUN_ID": "run_id", "GITHUB_RUN_ATTEMPT": "run_attempt",
               "GITHUB_SHA": "policy_revision", "RUNNER_OS": "runner_os",
               "RUNNER_ARCH": "runner_arch", "ImageVersion": "runner_image"}
    require(identity.get("GITHUB_REPOSITORY") == "onesyue/yueto-ci"
            and all(identity.get(k) == value["context"][v] for k, v in mapping.items()),
            "run/attempt/runner identity mismatch")
    identity_copy = dict(metadata)
    invocation = identity_copy.pop("invocation_id", None)
    require(invocation == sha(json.dumps(identity_copy, sort_keys=True).encode()),
            "prepared invocation digest mismatch")
    require(argv[0] == metadata.get("python_executable"), "wrong Python executable")
    rows = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
    require(all(isinstance(row, dict) for row in rows), "invalid event record")
    def one(event):
        selected = [r for r in rows if r.get("event") == event]
        require(len(selected) == 1, f"missing or duplicate {event}")
        return selected[0]
    require(rows and rows[0].get("event") == "start"
            and rows[-1].get("event") == "finish", "absent session boundary")
    one("start")
    terminal = one("finish")
    session = one("session_identity")
    timing = one("session_timing")
    collection = one("collection_timing")
    corpus = one("collection_corpus")
    require(session.get("invocation_id") == metadata.get("invocation_id")
            and isinstance(session.get("invocation_id"), str)
            and session["invocation_id"] and session.get("executor") == "serial",
            "wrong invocation or executor")
    require(isinstance(session.get("session_id"), str) and session["session_id"],
            "missing session identity")
    require(all(r.get("session_id") == session.get("session_id")
                for r in (timing, collection, corpus)), "mixed session identities")
    require(timing.get("terminal") == "finished" and timing.get("lost_records") == 0
            and collection.get("status") == "finished"
            and not any(r.get("event") in ("collect_error", "collection_deselected")
                        for r in rows), "collection or recorder incomplete")
    nodeids = corpus.get("nodeids")
    require(corpus.get("scope") == "controller_selected" and isinstance(nodeids, list)
            and all(isinstance(n, str) for n in nodeids)
            and len(nodeids) == len(set(nodeids)) and corpus.get("count") == len(nodeids)
            and corpus.get("ordered_nodeids_sha256")
            == sha(json.dumps(nodeids, ensure_ascii=False).encode()),
            "invalid selected corpus")
    allowed = set(value["modules"]) if reference else set(modules)
    require(all(n.split("::", 1)[0] in allowed for n in nodeids),
            "collected case outside assigned modules")
    rc = int((directory / "pytest-exit-code.txt").read_text())
    expected_rc = 5 if expected_empty and not nodeids and not reference else 0
    require(type(terminal.get("exitstatus")) is int and type(timing.get("exitstatus")) is int
            and rc == terminal.get("exitstatus") == timing.get("exitstatus") == expected_rc,
            "pytest failed or process/session exits disagree")
    begin = int((directory / "pytest-start-unix-ns.txt").read_text())
    end = int((directory / "pytest-finish-unix-ns.txt").read_text())
    require(0 < begin <= end, "invalid process window")
    if reference:
        require(nodeids and not any(r.get("event") == "phase_timing" for r in rows),
                "reference must be full collection-only evidence")
    else:
        diagnostic = load_timing().inspect(directory)
        require(diagnostic["evidence_status"] == "COMPLETE",
                "incomplete diagnostic evidence: " + "; ".join(diagnostic["problems"]))
        require(not any(r.get("outcome") == "failed" for r in rows),
                "failed outcome contradicts successful exit")
    outcomes = [r for r in rows if "event" not in r and r.get("outcome") in ("skipped", "xfail")]
    return {
        "assignment_id": role, "invocation_id": session["invocation_id"], "nodeids": nodeids,
        "pytest_process_exit_code": rc, "empty_assigned_collection": expected_rc == 5,
        "nonpassing_outcomes": outcomes,
        "evidence_sha256": {n: sha((directory / n).read_bytes()) for n in FILES},
        "process_seconds": (end - begin) / 1_000_000_000,
    }


def aggregate(value, reference, directories):
    value = validate_plan(value)
    expected = inspect_session(reference, value, None)
    assignments = {item["id"]: item for item in value["assignments"]}
    require(len(directories) == len(assignments), "missing or extra shard receipts")
    results, ids, invocations, union = [], [], [expected["invocation_id"]], []
    for directory in directories:
        role = read_json(directory / "selection.json").get("assignment_id")
        require(role in assignments and role not in ids, "unknown or duplicate shard")
        expected_empty = not any(n.split("::", 1)[0] in assignments[role]["modules"]
                                 for n in expected["nodeids"])
        result = inspect_session(directory, value, assignments[role], expected_empty=expected_empty)
        results.append(result)
        ids.append(role)
        invocations.append(result["invocation_id"])
        union.extend(result["nodeids"])
    require(len(invocations) == len(set(invocations)), "reused invocation evidence")
    require(len(union) == len(set(union)), "shards overlap")
    require(set(union) == set(expected["nodeids"]), "shard union differs from full collection")
    return {
        "schema": 1, "status": "ORDINARY_CORPUS_COMPLETE",
        "release_acceptance": False, "native_and_skip_policy_acceptance": "NOT_EVALUATED",
        "plan_sha256": value["plan_sha256"], "source_revision": value["source_revision"],
        "context": value["context"], "case_count": len(union),
        "modules_without_selected_cases": sorted(set(value["modules"])
                                                - {n.split("::", 1)[0] for n in union}),
        "reference": expected, "shards": sorted(results, key=lambda r: r["assignment_id"]),
        "resources": {"status": "UNKNOWN"},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("plan")
    create.add_argument("--source", type=Path, required=True)
    create.add_argument("--context", type=Path, required=True)
    create.add_argument("--shards", type=int, required=True)
    create.add_argument("--serial-module", action="append", default=[])
    verify = sub.add_parser("aggregate")
    verify.add_argument("--plan", type=Path, required=True)
    verify.add_argument("--reference", type=Path, required=True)
    verify.add_argument("--shard", type=Path, action="append", required=True)
    args = parser.parse_args()
    try:
        if args.command == "plan":
            result = plan(args.source, read_json(args.context), args.shards, args.serial_module)
        else:
            result = aggregate(read_json(args.plan), args.reference, args.shard)
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        print(json.dumps({"status": "REJECTED", "release_acceptance": False,
                          "problem": str(error)}), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
