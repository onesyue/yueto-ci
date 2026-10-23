#!/usr/bin/env python3
"""Plan Ops jobs, execute the source-owned selection and strictly join evidence.

The ordinary corpus verdict alone never supplies complete release acceptance.
"""
from __future__ import annotations

import argparse
import ast
import configparser
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import sysconfig
import time
import xml.etree.ElementTree as ET
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
SKIP_BASELINE = "ops-pytest-skip-baseline.json"
# The exact reviewed record is pinned independently of its baseline payload.
SSH_SKIP_TRANSITION_SHA256 = "df44974b4d4e883d73ffa6d3067a378441650456d3d1a64655f4d7ae73d1547f"
W85_INPUT_TRANSITION_SHA256 = "975897eb2f19379c17e81bb26ebbd6ea0d362563519174c27ceef000ff14223c"
W85_OBSERVABILITY_TRANSITION_SHA256 = "aa2582effcfb53d71b11abe0a60db1e9231c9236da6badc6cf49a1c128548c98"
SSH_SKIP_CASES = {
    "tests/test_host_service_contracts_20261013.py::test_node_producer_is_durable_and_idempotent",
    "tests/test_installed_checker_transport_20261014.py::"
    "test_real_pinned_sshd_json_transport_plan_apply_readback_and_old_n_negative",
}
NATIVE_TARGETS = {
    "tests/test_board139_schema_acl_native_20261018.py": (6, 1001),
    "tests/test_node_systemd_pilot_20261018.py": (38, 0),
    "tests/test_schema_contract_receipt_20261020.py": (30, 0),
}


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


def runner_context(planned, environment):
    """Bind this allocation, not the separately allocated planning job's image."""
    observed = {key: environment.get(name) for name, key in (
        ("RUNNER_OS", "runner_os"), ("RUNNER_ARCH", "runner_arch"),
        ("ImageVersion", "runner_image"))}
    require(all(isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,128}", v)
                and v != "UNKNOWN" for v in observed.values()), "missing runner identity")
    require(all(observed[k] == planned[k] for k in ("runner_os", "runner_arch")),
            "executing runner OS or architecture differs")
    return observed


def runner_summary(planned, roles):
    images = sorted({r["runner_image"] for r in roles.values()})
    return {"planning_runner_image": planned["runner_image"], "roles": roles,
            "execution_images": images, "mixed_execution_images": len(images) > 1,
            "performance_comparison": "NOT_ESTABLISHED"}


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


def tree_inputs(source, revision):
    require(SHA.fullmatch(revision), "baseline requires an exact source revision")
    rows = git(source, "ls-tree", "-rz", revision).decode().split("\0")
    files = {}
    for row in rows:
        if row:
            metadata, path = row.split("\t", 1)
            mode, kind, blob = metadata.split()
            if kind == "blob":
                files[path] = (mode, blob)
    return files


def shared_inputs(source, revision):
    result = {}
    for path, (mode, blob) in tree_inputs(source, revision).items():
        name = PurePosixPath(path).name
        if (name in ("conftest.py", "pytest.ini", "pyproject.toml", "uv.lock",
                     "package.json", "package-lock.json", "pnpm-lock.yaml")
                or name.startswith("requirements") and name.endswith((".txt", ".lock"))
                or path.startswith("tests/") and path.endswith(".py") and not safe_module(path)):
            require(mode == "100644" or mode == "100755", "symlink shared test input")
            result[path] = blob
    require("pytest.ini" in result, "missing shared collection inputs")
    return result


def reviewed_w85_observability_transition(baseline):
    """Peel the exact observability successor without changing historical evidence."""
    original = dict(baseline)
    key = "reviewed_w85_observability_transition"
    record = original.pop(key, None)
    if key not in baseline:
        return original, None
    require(isinstance(record, dict) and set(record) == {
        "schema", "prior_baseline_sha256", "source_before", "source_after",
        "qualified_policy_revision", "independent_review_sha256",
        "source_freeze_sha256", "qualification_receipt_sha256", "changes",
    } and type(record["schema"]) is int and record["schema"] == 1,
            "invalid reviewed W8.5 observability transition")
    require(sha(encoded(record)) == W85_OBSERVABILITY_TRANSITION_SHA256,
            "unreviewed W8.5 observability transition identity")
    restored = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
    require(record["prior_baseline_sha256"] == sha(restored),
            "W8.5 observability transition historical baseline changed")
    return original, record


def reviewed_w85_input_transition(baseline):
    """Peel the exact dependency successor without changing historical evidence."""
    baseline, _ = reviewed_w85_observability_transition(baseline)
    original = dict(baseline)
    key = "reviewed_w85_input_transition"
    record = original.pop(key, None)
    if key not in baseline:
        return original, None
    require(isinstance(record, dict) and set(record) == {
        "schema", "prior_baseline_sha256", "source_before", "source_after",
        "qualified_policy_revision", "independent_review_sha256",
        "source_freeze_sha256", "dependency_audit_sha256", "changes",
    } and type(record["schema"]) is int and record["schema"] == 1,
            "invalid reviewed W8.5 input transition")
    require(sha(encoded(record)) == W85_INPUT_TRANSITION_SHA256,
            "unreviewed W8.5 input transition identity")
    restored = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
    require(record["prior_baseline_sha256"] == sha(restored),
            "W8.5 input transition historical baseline changed")
    return original, record


def reviewed_skip_module_transition(baseline, files=None):
    """Preserve historical skips while admitting two reviewed source successors.

    Independent UID0 qualification is evidence, not a same-run native receipt or
    an ordinary PASS. The signed policy and admission digest bind that evidence.
    """
    original, _ = reviewed_w85_input_transition(baseline)
    key = "reviewed_ssh_skip_module_transition"
    record = original.pop(key, None)
    if key not in baseline:
        return original, {}
    require(isinstance(record, dict) and set(record) == {
        "schema", "prior_baseline_sha256", "source_before", "source_after",
        "qualified_source", "independent_review_sha256", "source_freeze_sha256",
        "qualification_receipt_sha256", "composition_review_sha256", "cases",
    } and type(record["schema"]) is int and record["schema"] == 1,
            "invalid reviewed SSH skip transition")
    require(sha(encoded(record)) == SSH_SKIP_TRANSITION_SHA256,
            "unreviewed SSH skip transition identity")
    restored = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
    require(record["prior_baseline_sha256"] == sha(restored),
            "SSH skip transition historical baseline changed")
    require(all(isinstance(record[k], str) and SHA.fullmatch(record[k]) for k in
                ("source_before", "source_after", "qualified_source"))
            and record["source_before"] != record["source_after"]
            and all(isinstance(record[k], str) and re.fullmatch(r"[0-9a-f]{64}", record[k])
                    for k in ("independent_review_sha256", "source_freeze_sha256",
                              "qualification_receipt_sha256", "composition_review_sha256")),
            "missing exact SSH skip review identity")
    changes = record["cases"]
    require(isinstance(changes, dict) and set(changes) == SSH_SKIP_CASES,
            "unreviewed SSH skip cases")
    successors = {}
    for nodeid, change in changes.items():
        historical = original["cases"].get(nodeid)
        require(isinstance(historical, dict) and historical.get("outcome") == "skipped"
                and isinstance(historical.get("reason"), str)
                and nodeid not in original.get("reviewed_hosted", {}).get("cases", {})
                and isinstance(change, dict) and set(change) == {
                    "before_blob", "after_blob", "mode",
                } and all(isinstance(change[k], str) and SHA.fullmatch(change[k])
                          for k in ("before_blob", "after_blob"))
                and change["before_blob"] == historical.get("module_blob")
                and change["before_blob"] != change["after_blob"]
                and change["mode"] == "100644", "unreviewed SSH skip blob or mode")
        module = nodeid.split("::", 1)[0]
        if files is not None and files.get(module, (None, None))[1] == change["after_blob"]:
            require(files[module][0] == change["mode"], "SSH skip module mode changed")
        successors[nodeid] = historical | {"module_blob": change["after_blob"]}
    return original, successors


def admit_shared_inputs(baseline, common, files=None):
    """Admit complete historical maps and each exact reviewed input successor.

    The historical skip/collection evidence is never relabeled as a new run.
    Exact effective inputs remain sealed into this run's admission envelope.
    """
    baseline, observability_record = reviewed_w85_observability_transition(baseline)
    original, _ = reviewed_skip_module_transition(baseline, files)
    w85_record = baseline.get("reviewed_w85_input_transition")
    miniapp_record = original.pop("reviewed_miniapp_security_transition", None)
    security_record = original.pop("reviewed_frontend_security_transition", None)
    python_record = original.pop("reviewed_python_input_transition", None)
    record = original.pop("reviewed_shared_input_transition", None)
    expected = original["common_inputs"]
    accepted = [expected]
    require("reviewed_python_input_transition" not in baseline or isinstance(python_record, dict),
            "invalid reviewed Python input transition")
    require(python_record is None or record is not None,
            "Python input transition requires its frontend predecessor")
    require("reviewed_frontend_security_transition" not in baseline
            or isinstance(security_record, dict), "invalid frontend security transition")
    require(security_record is None or python_record is not None and record is not None,
            "frontend security transition requires both predecessors")
    require("reviewed_miniapp_security_transition" not in baseline
            or isinstance(miniapp_record, dict), "invalid MiniApp security transition")
    require(miniapp_record is None or security_record is not None,
            "MiniApp security transition requires its frontend security predecessor")
    if record is not None:
        require(isinstance(record, dict) and set(record) == {
            "schema", "original_baseline_sha256", "source_before", "source_after",
            "independent_review_sha256", "source_freeze_sha256", "path",
            "before_blob", "after_blob", "common_input_modes",
        } and record["schema"] == 1, "invalid reviewed shared-input transition")
        restored = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
        require(record["original_baseline_sha256"] == sha(restored),
                "historical skip baseline changed")
        require(all(isinstance(record[k], str) and SHA.fullmatch(record[k]) for k in
                    ("source_before", "source_after", "before_blob", "after_blob"))
                and record["source_before"] != record["source_after"]
                and record["before_blob"] != record["after_blob"]
                and all(isinstance(record[k], str) and re.fullmatch(r"[0-9a-f]{64}", record[k])
                        for k in ("independent_review_sha256", "source_freeze_sha256")),
                "missing exact shared-input review identity")
        path = record["path"]
        require(path == "frontend/package-lock.json"
                and expected.get(path) == record["before_blob"],
                "unreviewed shared-input path or original blob")
        modes = record["common_input_modes"]
        require(isinstance(modes, dict) and set(modes) == set(expected)
                and all(m in ("100644", "100755") for m in modes.values())
                and modes[path] == "100644", "incomplete reviewed shared-input modes")
        if files is not None:
            require({p: files.get(p, (None, None))[0] for p in common} == modes,
                    "shared collection/dependency input modes changed")
        effective = expected | {path: record["after_blob"]}
        accepted.append(effective)
        if python_record is not None:
            require(isinstance(python_record, dict) and set(python_record) == {
                "schema", "original_baseline_sha256", "prior_frontend_transition_sha256",
                "source_before", "source_after", "independent_review_sha256",
                "source_freeze_sha256", "changes",
            } and python_record["schema"] == 1, "invalid reviewed Python input transition")
            require(python_record["original_baseline_sha256"] == sha(restored)
                    and python_record["prior_frontend_transition_sha256"] == sha(encoded(record)),
                    "Python input history or predecessor changed")
            require(all(isinstance(python_record[k], str) and SHA.fullmatch(python_record[k])
                        for k in ("source_before", "source_after"))
                    and python_record["source_before"] == record["source_after"]
                    and python_record["source_before"] != python_record["source_after"]
                    and all(isinstance(python_record[k], str)
                            and re.fullmatch(r"[0-9a-f]{64}", python_record[k])
                            for k in ("independent_review_sha256", "source_freeze_sha256")),
                    "missing exact Python input review identity")
            changes = python_record["changes"]
            require(isinstance(changes, dict) and set(changes) == {
                "pyproject.toml", "uv.lock", "telegram-bot/yue/requirements.txt",
            }, "unreviewed Python input paths")
            converted = dict(effective)
            for changed_path, change in changes.items():
                require(isinstance(change, dict) and set(change) == {
                    "before_blob", "after_blob", "mode",
                } and all(isinstance(change[k], str) and SHA.fullmatch(change[k])
                          for k in ("before_blob", "after_blob"))
                        and change["before_blob"] == effective.get(changed_path)
                        and change["before_blob"] != change["after_blob"]
                        and change["mode"] == modes.get(changed_path) == "100644",
                        "unreviewed Python input blob or mode")
                converted[changed_path] = change["after_blob"]
            accepted.append(converted)
            if security_record is not None:
                require(set(security_record) == {
                    "schema", "original_baseline_sha256", "prior_transition_chain_sha256",
                    "source_before", "source_after", "independent_review_sha256",
                    "source_freeze_sha256", "path", "before_blob", "after_blob", "mode",
                } and type(security_record["schema"]) is int
                        and security_record["schema"] == 1,
                        "invalid frontend security transition")
                prior_chain = {"reviewed_shared_input_transition": record,
                               "reviewed_python_input_transition": python_record}
                require(security_record["original_baseline_sha256"] == sha(restored)
                        and security_record["prior_transition_chain_sha256"]
                        == sha(encoded(prior_chain)),
                        "frontend security history or predecessor changed")
                require(all(isinstance(security_record[k], str)
                            and SHA.fullmatch(security_record[k]) for k in
                            ("source_before", "source_after", "before_blob", "after_blob"))
                        and security_record["source_before"] != security_record["source_after"]
                        and security_record["before_blob"] != security_record["after_blob"]
                        and all(isinstance(security_record[k], str)
                                and re.fullmatch(r"[0-9a-f]{64}", security_record[k]) for k in
                                ("independent_review_sha256", "source_freeze_sha256")),
                        "missing exact frontend security review identity")
                path = security_record["path"]
                require(path == "frontend/package-lock.json"
                        and security_record["before_blob"] == converted.get(path)
                        and security_record["mode"] == modes.get(path) == "100644",
                        "unreviewed frontend security input blob or mode")
                secured = converted | {path: security_record["after_blob"]}
                accepted.append(secured)
                if miniapp_record is not None:
                    require(set(miniapp_record) == {
                        "schema", "original_baseline_sha256", "prior_transition_chain_sha256",
                        "source_before", "source_after", "independent_review_sha256",
                        "source_freeze_sha256", "path", "before_blob", "after_blob", "mode",
                    } and type(miniapp_record["schema"]) is int
                            and miniapp_record["schema"] == 1,
                            "invalid MiniApp security transition")
                    prior_chain["reviewed_frontend_security_transition"] = security_record
                    require(miniapp_record["original_baseline_sha256"] == sha(restored)
                            and miniapp_record["prior_transition_chain_sha256"]
                            == sha(encoded(prior_chain)),
                            "MiniApp security history or predecessor changed")
                    require(all(isinstance(miniapp_record[k], str)
                                and SHA.fullmatch(miniapp_record[k]) for k in
                                ("source_before", "source_after", "before_blob", "after_blob"))
                            and miniapp_record["source_before"] == security_record["source_after"]
                            and miniapp_record["source_before"] != miniapp_record["source_after"]
                            and miniapp_record["before_blob"] != miniapp_record["after_blob"]
                            and all(isinstance(miniapp_record[k], str)
                                    and re.fullmatch(r"[0-9a-f]{64}", miniapp_record[k]) for k in
                                    ("independent_review_sha256", "source_freeze_sha256")),
                            "missing exact MiniApp security review identity")
                    path = miniapp_record["path"]
                    require(path == "telegram-bot/yue/miniapp/package-lock.json"
                            and miniapp_record["before_blob"] == secured.get(path)
                            and miniapp_record["mode"] == modes.get(path) == "100644",
                            "unreviewed MiniApp security input blob or mode")
                    accepted.append(secured | {path: miniapp_record["after_blob"]})
    if w85_record is not None:
        require(miniapp_record is not None
                and w85_record["source_before"] == miniapp_record["source_after"],
                "W8.5 input transition requires its MiniApp predecessor")
        changes = w85_record["changes"]
        require(isinstance(changes, dict) and set(changes) == {"pyproject.toml", "uv.lock"},
                "unreviewed W8.5 input paths")
        successor = dict(accepted[-1])
        for path, change in changes.items():
            require(isinstance(change, dict) and set(change) == {
                "before_blob", "after_blob", "mode",
            } and all(isinstance(change[k], str) and SHA.fullmatch(change[k])
                      for k in ("before_blob", "after_blob"))
                    and change["before_blob"] == successor.get(path)
                    and change["before_blob"] != change["after_blob"]
                    and change["mode"] == modes.get(path) == "100644",
                    "unreviewed W8.5 input blob or mode")
            successor[path] = change["after_blob"]
        accepted.append(successor)
    if observability_record is not None:
        require(w85_record is not None
                and observability_record["source_before"] == w85_record["source_after"]
                and observability_record["source_before"] != observability_record["source_after"],
                "W8.5 observability transition requires its W8.5 predecessor")
        changes = observability_record["changes"]
        require(isinstance(changes, dict) and set(changes) == {"requirements-observability.txt"},
                "unreviewed W8.5 observability input paths")
        successor = dict(accepted[-1])
        for path, change in changes.items():
            require(isinstance(change, dict) and set(change) == {
                "before_blob", "after_blob", "mode",
            } and all(isinstance(change[k], str) and SHA.fullmatch(change[k])
                      for k in ("before_blob", "after_blob"))
                    and change["before_blob"] == successor.get(path)
                    and change["before_blob"] != change["after_blob"]
                    and change["mode"] == modes.get(path) == "100644",
                    "unreviewed W8.5 observability input blob or mode")
            successor[path] = change["after_blob"]
        accepted.append(successor)
    require(common in accepted, "shared collection/dependency inputs changed")


def collection_skips(path, modules):
    require(path.is_file() and not path.is_symlink(), "missing native JUnit evidence")
    data = path.read_bytes()
    require(len(data) <= 32 * 1024 * 1024
            and b"<!DOCTYPE" not in data and b"<!ENTITY" not in data, "unsafe JUnit evidence")
    root = ET.fromstring(data)
    require(root.tag == "testsuites" and len(root.findall("testsuite")) == 1,
            "unexpected JUnit document")
    suite = root.find("testsuite")
    require(suite.get("errors") == "0" and suite.get("failures") == "0",
            "failed JUnit evidence")
    result = {}
    for case in suite.findall("testcase"):
        skipped = case.find("skipped")
        if skipped is None or skipped.get("message") != "collection skipped":
            continue
        matches = [m for m in modules if m[:-3].replace("/", ".") == case.get("name")]
        require(case.get("classname") == "" and len(matches) == 1, "unbound collection skip")
        module = matches[0]
        detail = ast.literal_eval(skipped.text or "")
        require(isinstance(detail, tuple) and len(detail) == 3
                and isinstance(detail[0], str) and isinstance(detail[1], int)
                and isinstance(detail[2], str) and detail[2]
                and (detail[0] == module or detail[0].endswith("/" + module))
                and module not in result, "invalid collection skip identity")
        result[module] = detail[2]
    return result


def baseline_events(path, allowed_exit=(0,)):
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    starts = [r for r in rows if r.get("event") == "start"]
    ends = [r for r in rows if r.get("event") == "finish"]
    timings = [r for r in rows if r.get("event") == "session_timing"]
    require(rows and rows[0].get("event") == "start" and rows[-1].get("event") == "finish"
            and len(starts) == len(ends) == len(timings) == 1
            and ends[0].get("exitstatus") in allowed_exit
            and timings[0].get("exitstatus") == ends[0]["exitstatus"]
            and timings[0].get("terminal") == "finished" and timings[0].get("lost_records") == 0
            and not any(r.get("event") == "collect_error" or r.get("outcome") == "failed"
                        for r in rows), "incomplete or failed skip baseline")
    context = {k: starts[0].get(k) for k in ("platform", "uid")}
    require(isinstance(context["platform"], str) and type(context["uid"]) is int
            and context["uid"] > 0, "baseline context must be actual nonroot execution")
    return rows, context


def generate_skip_baseline(source, revision, events, collection_xml, collection_events,
                           collection_revision, collection_at):
    """Generate reviewed historical SKIP data; never infer PASS or refresh during a run."""
    files = tree_inputs(source, revision)
    rows, context = baseline_events(events)
    _, collection_context = baseline_events(collection_events, (0, 5))
    require(context == collection_context, "historical collection context differs")
    common = shared_inputs(source, revision)
    require(common == shared_inputs(source, collection_revision),
            "historical collection shared inputs differ")
    historical_files = tree_inputs(source, collection_revision)
    modules = {p for p in files if safe_module(p)}
    collected = collection_skips(collection_xml, modules)
    cases = {}
    for row in rows:
        if "event" in row or row.get("outcome") not in ("skipped", "xfail"):
            continue
        nodeid, reason = row.get("nodeid"), row.get("reason")
        require(isinstance(nodeid, str) and isinstance(reason, str) and reason,
                "unidentified baseline skip")
        module = nodeid.split("::", 1)[0]
        require(module in modules and files[module][0] in ("100644", "100755"),
                "baseline skip module is not owned")
        record = {"outcome": row["outcome"], "reason": reason, "module_blob": files[module][1]}
        require(nodeid not in cases or cases[nodeid] == record, "contradictory baseline skip")
        cases[nodeid] = record
    require(cases or collected, "empty skip baseline")
    collection = {}
    for module, reason in collected.items():
        require(files[module] == historical_files.get(module), "historical skipped module differs")
        collection[module] = {"reason": reason, "module_blob": files[module][1]}
    require(isinstance(collection_at, str) and collection_at.strip(),
            "historical collection timestamp missing")
    return {
        "schema": 1, "status": "HISTORICAL_SKIPS_NOT_PASSES", "source_revision": revision,
        "events_sha256": sha(events.read_bytes()), "context": context, "common_inputs": common,
        "cases": cases, "collection_skips": collection,
        "collection_evidence": {
            "source_revision": collection_revision, "recorded_at": collection_at,
            "xml_sha256": sha(collection_xml.read_bytes()),
            "events_sha256": sha(collection_events.read_bytes()), "context": collection_context,
            "inheritance": "Exact module and shared inputs only; not a new source execution.",
        },
    }


def skip_baseline():
    value = read_json(ROOT / SKIP_BASELINE)
    require(value.get("schema") == 1 and value.get("status") == "HISTORICAL_SKIPS_NOT_PASSES"
            and SHA.fullmatch(value.get("source_revision", ""))
            and value.get("common_inputs") and isinstance(value.get("cases"), dict)
            and isinstance(value.get("collection_skips"), dict), "invalid skip baseline")
    return value


def inspect_session(directory, value, assignment, *, expected_empty=False):
    """Validate immutable invocation binding before consuming passive case evidence."""
    require(directory.is_dir() and not directory.is_symlink(), "invalid evidence directory")
    require(not (directory / "rejected.json").exists()
            and not (directory / "rejected.json").is_symlink(), "rejected execution evidence")
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
    has_xml = (isinstance(argv, list) and len(argv) == len(suffix) + 3
               and argv[-2] == "--junitxml" and isinstance(argv[-1], str)
               and Path(argv[-1]).is_absolute() and Path(argv[-1]).name == "pytest.xml")
    require(isinstance(argv, list) and isinstance(argv[0], str) and argv[0]
            and (argv[1:-2] == suffix if has_xml else argv[1:] == suffix),
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
               "GITHUB_SHA": "policy_revision"}
    require(identity.get("GITHUB_REPOSITORY") == "onesyue/yueto-ci"
            and all(identity.get(k) == value["context"][v] for k, v in mapping.items()),
            "run/attempt/runner identity mismatch")
    actual_runner = runner_context(value["context"], identity)
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
    start = one("start")
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
        "execution_context": {k: start.get(k) for k in ("platform", "uid")},
        "runner_context": actual_runner,
        "collection_skips": collection_skips(directory / "pytest.xml", allowed) if has_xml else None,
        "junit_sha256": sha((directory / "pytest.xml").read_bytes()) if has_xml else None,
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
        "runner_observations": runner_summary(value["context"], {
            r["assignment_id"]: r["runner_context"] for r in [expected, *results]}),
        "resources": {"status": "UNKNOWN"},
    }


def workflow_identity():
    identity = {
        "policy_revision": os.environ.get("GITHUB_SHA"),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
    }
    require(SHA.fullmatch(identity["policy_revision"] or "")
            and identity["policy_revision"] == git(ROOT, "rev-parse", "HEAD").decode().strip(),
            "workflow policy identity differs")
    for key in ("run_id", "run_attempt"):
        require(re.fullmatch(r"[1-9][0-9]*", identity[key] or ""), f"invalid {key}")
    require(os.environ.get("GITHUB_REPOSITORY") == "onesyue/yueto-ci",
            "unexpected workflow repository")
    return identity


def seal(value, key):
    value[key] = sha(encoded(value))
    return value


def role_order(value):
    assignments = [a["id"] for a in value["assignments"]]
    return ["native", "reference", *[a for a in assignments if a == "serial"],
            *[a for a in assignments if a != "serial"]]


def envelope(value):
    expected = dict(value)
    digest = expected.pop("admission_sha256", None)
    require(value.get("schema") == 1 and digest == sha(encoded(expected)),
            "admission envelope digest differs")
    require(value.get("identity") == workflow_identity(), "stale workflow admission")
    require(value.get("mode") in ("none", "legacy", "sharded"), "unknown admission mode")
    matrix = value.get("validation_matrix")
    require(isinstance(matrix, list) and matrix, "missing selected validators")
    ops = [m for m in matrix if m.get("validation") == "yueops"]
    if value["mode"] == "none":
        require(not ops and value.get("ops_plan") is None, "unexpected Ops selection")
    else:
        require(all(m.get("ref") == value["source_revision"]
                    and m.get("repo") == "onesyue/yueops" for m in ops),
                "Ops matrix source differs")
        if value["mode"] == "legacy":
            require([m.get("ops_role") for m in ops] == ["legacy"]
                    and value.get("ops_plan") is None, "invalid legacy role selection")
        else:
            planned = validate_plan(value["ops_plan"])
            baseline = skip_baseline()
            require(value.get("skip_baseline_sha256") == sha((ROOT / SKIP_BASELINE).read_bytes())
                    and isinstance(value.get("skip_module_blobs"), dict),
                    "skip baseline or shared collection inputs differ")
            admit_shared_inputs(baseline, value.get("common_inputs"))
            require(planned["source_revision"] == value["source_revision"]
                    and planned["context"]["board_revision"] == value["board_revision"]
                    and all(planned["context"][k] == v for k, v in value["identity"].items()),
                    "ordinary plan identity differs")
            require([m.get("ops_role") for m in ops]
                    == role_order(planned),
                    "missing or unexpected selected Ops roles")
    return value


def serial_modules(source):
    result = subprocess.run(["bash", "scripts/run-pytest-parallel.sh", "--describe-ci-selection"],
                            cwd=source, capture_output=True, text=True, check=True, timeout=15)
    description = json.loads(result.stdout)
    require(set(description) == {"schema", "serial_modules"} and description["schema"] == 1
            and isinstance(description["serial_modules"], list)
            and description["serial_modules"], "invalid source serial declaration")
    return description["serial_modules"]


def expand(targets, source, board, runner, capacity, shards):
    """Expand an exact target plan, without pytest collection or import."""
    require(type(capacity) is int and capacity > 0, "capacity must be positive")
    require(runner in ("ubuntu-24.04", "yue-local-release"), "unsupported runner")
    matrix = targets["validation_matrix"]
    require(isinstance(matrix, list) and matrix, "empty validation matrix")
    selected = [m for m in matrix if m.get("validation") == "yueops"]
    require(len(selected) <= 1, "duplicate Ops validation records")
    value = {"schema": 1, "identity": workflow_identity(), "mode": "none",
             "source_revision": None, "board_revision": board,
             "ops_plan": None, "validation_matrix": matrix}
    if selected:
        ops = selected[0]
        require(ops.get("repo") == "onesyue/yueops" and SHA.fullmatch(ops.get("ref", "")),
                "Ops source must be resolved exactly")
        require(SHA.fullmatch(board), "invalid reviewed Board identity")
        require(all(m.get("ref") == ops["ref"] for m in targets["matrix"]
                    if m.get("validation") == "yueops"), "Ops image and validation differ")
        value["source_revision"] = ops["ref"]
        if runner == "yue-local-release":
            value["mode"] = "legacy"
            roles = ["legacy"]
        else:
            require(source is not None, "Ops source checkout missing")
            context = value["identity"] | {
                "board_revision": board, "runner_os": os.environ.get("RUNNER_OS"),
                "runner_arch": os.environ.get("RUNNER_ARCH"),
                "runner_image": os.environ.get("ImageVersion"),
            }
            expected = plan(source, context, shards, serial_modules(source))
            require(expected["source_revision"] == ops["ref"], "planned source checkout differs")
            baseline = skip_baseline()
            common = shared_inputs(source, ops["ref"])
            files = tree_inputs(source, ops["ref"])
            admit_shared_inputs(baseline, common, files)
            value.update(mode="sharded", ops_plan=expected, common_inputs=common,
                         skip_baseline_sha256=sha((ROOT / SKIP_BASELINE).read_bytes()),
                         skip_module_blobs={p: files[p][1] for p in expected["modules"]})
            roles = role_order(expected)
        value["validation_matrix"] = [
            row for m in matrix
            for row in ([m | {"ops_role": role} for role in roles] if m is ops else [m])
        ]
        if value["mode"] == "sharded":
            # Put short admission owners ahead of long ordinary groups even
            # for an all-target dispatch. Other validators keep their order.
            priority = {"native": 0, "reference": 1, "serial": 2}
            value["validation_matrix"].sort(
                key=lambda row: priority.get(row.get("ops_role"),
                                             4 if row.get("ops_role") else 3))
    value["max_parallel"] = min(capacity, len(value["validation_matrix"]))
    if runner == "yue-local-release":
        value["max_parallel"] = 1
    return seal(value, "admission_sha256")


def check_source(value, source, board):
    envelope(value)
    require(git(source, "rev-parse", "HEAD").decode().strip() == value["source_revision"]
            and not git(source, "status", "--porcelain", "--untracked-files=no"),
            "executing source differs or is dirty")
    require(git(board, "rev-parse", "HEAD").decode().strip() == value["board_revision"]
            and not git(board, "status", "--porcelain", "--untracked-files=no"),
            "executing Board fixture differs or is dirty")
    contract = read_json(ROOT / "native-node-contract.json")
    require(contract["yueboard_contract_pin"] == value["board_revision"],
            "Board fixture is not the reviewed policy pin")


def execute(value, source, board, role, output, site):
    """Run exactly one actual source entry; preserve failed and empty exits."""
    check_source(value, source, board)
    require(value["mode"] == "sharded", "selection is hosted-only")
    expected = validate_plan(value["ops_plan"])
    assignments = {a["id"]: a for a in expected["assignments"]}
    require(role == "reference" or role in assignments, "unknown execution role")
    current = plan(source, expected["context"],
                   sum(a["id"].startswith("ordinary-") for a in expected["assignments"]),
                   serial_modules(source))
    require(current == expected, "source collection inputs or assignments changed")
    actual_runner = runner_context(expected["context"], os.environ)
    require(os.environ.get("PYTEST_ADDOPTS", "") in ("", "--durations=25"),
            "unexpected pytest options")
    require(not os.environ.get("PYTEST_PLUGINS"), "unexpected pytest plugin override")
    timing = load_timing()
    timing.install(output, site)
    modules = ["tests"] if role == "reference" else assignments[role]["modules"]
    selection = {
        "schema": 1, "plan_sha256": expected["plan_sha256"],
        "source_revision": expected["source_revision"], "entry_sha256": expected["entry_sha256"],
        "assignment_id": role, "modules": modules,
    }
    selection_path = output / "command.json"
    selection_path.write_text(json.dumps(selection) + "\n")
    metadata = read_json(output / "metadata.json")
    require(runner_context(expected["context"], metadata["identity"]) == actual_runner,
            "runner identity changed during preparation")
    env = os.environ | {"LENS_REPORT": str(output / "events.jsonl"),
                        "LENS_INVOCATION_ID": metadata["invocation_id"],
                        "YUEOPS_PYTEST_SERIAL": "1"}
    (output / "pytest-start-unix-ns.txt").write_text(str(time.time_ns()))
    result = subprocess.run(
        ["bash", "scripts/run-pytest-parallel.sh", "--ci-selection", str(selection_path),
         "--selection-receipt", str(output / "selection.json")],
        cwd=source, env=env, check=False,
    )
    (output / "pytest-finish-unix-ns.txt").write_text(str(time.time_ns()))
    (output / "pytest-exit-code.txt").write_text(str(result.returncode))
    require(runner_context(expected["context"], os.environ) == actual_runner,
            "runner identity changed during execution")
    timing.summarize(output)
    if result.returncode == 5 and role != "reference":
        # A zero-case command is not passed; the independent reference must
        # still prove that its assigned modules were actually empty at join.
        inspect_session(output, expected, assignments[role], expected_empty=True)
        print("EMPTY_ASSIGNED_COLLECTION: exit 5 retained; reference join still required")
        return 0
    return result.returncode


def native_context(value):
    return {"schema": 1, "admission_sha256": value["admission_sha256"],
            "identity": value["identity"], "source_revision": value["source_revision"],
            "board_revision": value["board_revision"], "role": "native"}


def native_execution_context(value, output):
    result = read_json(output / "native-context.json")
    require(isinstance(result, dict), "invalid native context")
    observed = result.get("runner_context", {})
    require(isinstance(observed, dict)
            and set(observed) == {"runner_os", "runner_arch", "runner_image"},
            "missing native runner identity")
    validated = runner_context(value["ops_plan"]["context"], {
        "RUNNER_OS": observed["runner_os"], "RUNNER_ARCH": observed["runner_arch"],
        "ImageVersion": observed["runner_image"]})
    require(result == native_context(value) | {"runner_context": validated},
            "native context differs")
    return result


def native_start(value, source, board, output):
    check_source(value, source, board)
    require(value["mode"] in ("sharded", "legacy"), "unexpected native start")
    observed = (runner_context(value["ops_plan"]["context"], os.environ)
                if value["mode"] == "sharded" else None)
    output.mkdir(parents=True, exist_ok=False)
    result = native_context(value)
    if observed is not None:
        result["runner_context"] = observed
    (output / "native-context.json").write_text(json.dumps(result) + "\n")
    return result


def native_receipts(value, output):
    require(output.is_dir() and not output.is_symlink(), "invalid native evidence directory")
    context = native_execution_context(value, output)
    expected_files = {"native-context.json", *[Path(t).stem + ".json" for t in NATIVE_TARGETS]}
    actual_files = {p.name for p in output.iterdir()}
    require(actual_files in (expected_files, expected_files | {"native.json"}),
            "missing or unexpected native receipt files")
    records, hashes = {}, {}
    for target, (floor, uid) in NATIVE_TARGETS.items():
        path = output / (Path(target).stem + ".json")
        require(path.is_file() and not path.is_symlink()
                and path.stat().st_size <= 1024 * 1024, "missing or unsafe native receipt")
        row = read_json(path)
        require(isinstance(row, dict), "invalid native receipt")
        required, passed = row.get("required"), row.get("passed")
        require(isinstance(required, list) and isinstance(passed, list)
                and all(isinstance(n, str) and n.startswith(target + "::") for n in required)
                and all(isinstance(n, str) for n in passed)
                and len(required) >= floor and len(required) == len(set(required))
                and passed == sorted(set(passed)) == sorted(required), "native required calls differ")
        require(row.get("binding") == context and row.get("target") == target
                and row.get("platform") == "linux" and type(row.get("uid")) is int
                and row["uid"] == uid and row.get("floor") == floor
                and row.get("collection_bad") is False and row.get("failed_or_skipped") == []
                and type(row.get("exitstatus")) is int and row["exitstatus"] == 0
                and type(row.get("process_exitstatus")) is int and row["process_exitstatus"] == 0,
                "native failed, incomplete or wrong context")
        records[target] = row
        hashes[path.name] = sha(path.read_bytes())
    return {"obligations": records, "receipt_sha256": hashes}


def native_terminal(value, source, board, output):
    check_source(value, source, board)
    require(value["mode"] == "sharded", "unexpected native terminal")
    context = native_execution_context(value, output)
    require(context["runner_context"] == runner_context(value["ops_plan"]["context"], os.environ),
            "native runner identity changed during execution")
    result = context | {"status": "success"} | native_receipts(value, output)
    seal(result, "native_sha256")
    with (output / "native.json").open("x") as handle:
        handle.write(json.dumps(result) + "\n")
    return result


def admit_skips(value, result, native):
    baseline = skip_baseline()
    _, successors = reviewed_skip_module_transition(baseline)
    observed_collection = {}
    reviewed = baseline.get("reviewed_hosted", {})
    counts = {"HISTORICAL_UNEXECUTED": 0, "OWNER_CANCELED": 0,
              "SAME_RUN_NATIVE_REQUIRED": 0}
    for session in [result["reference"], *result["shards"]]:
        require(session["execution_context"] == baseline["context"],
                "skip execution context differs from baseline")
        require(isinstance(session["collection_skips"], dict) and session["junit_sha256"],
                "missing collection-skip evidence")
        for row in session["nonpassing_outcomes"]:
            nodeid = row["nodeid"]
            module = nodeid.split("::", 1)[0]
            specific = reviewed.get("cases", {}).get(nodeid)
            if specific is None:
                observed = {
                    "outcome": row["outcome"], "reason": row.get("reason"),
                    "module_blob": value["skip_module_blobs"].get(module),
                }
                require(observed in (baseline["cases"].get(nodeid), successors.get(nodeid)),
                        "new or changed case skip/xfail: " + nodeid)
                disposition = "HISTORICAL_UNEXECUTED"
            else:
                require(reviewed.get("schema") == 1
                        and session["execution_context"] == reviewed.get("context")
                        and all(value["ops_plan"]["context"].get(k) == v
                                for k, v in reviewed["runner"].items())
                        and specific["module_blob"] == value["skip_module_blobs"].get(module)
                        and specific["outcome"] == row["outcome"]
                        and {"when": row.get("when"), "reason": row.get("reason")}
                        in specific["variants"], "new or changed case skip/xfail: " + nodeid)
                disposition = specific["disposition"]
                require(disposition in counts, "unknown reviewed skip disposition")
                if disposition == "SAME_RUN_NATIVE_REQUIRED":
                    require(nodeid in native["obligations"].get(
                        specific["native_target"], {}).get("passed", []),
                        "ordinary skip missing exact same-run native call: " + nodeid)
            counts[disposition] += 1
        for module, reason in session["collection_skips"].items():
            require(baseline["collection_skips"].get(module) == {
                "reason": reason, "module_blob": value["skip_module_blobs"].get(module),
            }, "new or changed collection skip: " + module)
            if session["assignment_id"] != "reference":
                require(module not in observed_collection, "duplicate collection skip")
                observed_collection[module] = reason
    require(observed_collection == result["reference"]["collection_skips"],
            "reference and shards have different collection skips")
    return {"status": "NO_NEW_SKIPS", "baseline_sha256": value["skip_baseline_sha256"],
            "baseline_source_revision": baseline["source_revision"],
            "skips_are_passes": False, "disposition_counts": counts,
            "host_native_acceptance": "INDEPENDENT"}


def join(value, evidence, validation_result, expected_sha):
    envelope(value)
    require(value["admission_sha256"] == expected_sha, "plan job admission digest differs")
    require(validation_result == "success", "selected validation matrix did not succeed")
    if value["mode"] != "sharded":
        return {"schema": 1, "status": "VALIDATION_MATRIX_COMPLETE",
                "mode": value["mode"], "admission_sha256": value["admission_sha256"],
                "sharded_corpus_evaluated": False}
    expected = validate_plan(value["ops_plan"])
    prefix = f"ops-shard-{value['identity']['run_id']}-{value['identity']['run_attempt']}-"
    roles = ["reference", *[a["id"] for a in expected["assignments"]], "native"]
    require(evidence.is_dir() and not evidence.is_symlink(), "missing evidence directory")
    require(sorted(p.name for p in evidence.iterdir()) == sorted(prefix + r for r in roles),
            "missing or unexpected evidence roles")
    native_directory = evidence / (prefix + "native")
    native = read_json(native_directory / "native.json")
    expected_native = (native_execution_context(value, native_directory)
                       | {"status": "success"} | native_receipts(value, native_directory))
    seal(expected_native, "native_sha256")
    require(native == expected_native, "native/source gate receipt differs")
    result = aggregate(expected, evidence / (prefix + "reference"),
                       [evidence / (prefix + a["id"]) for a in expected["assignments"]])
    runners = {r["assignment_id"]: r["runner_context"]
               for r in [result["reference"], *result["shards"]]}
    runners["native"] = native["runner_context"]
    return {"schema": 1, "status": "VALIDATION_MATRIX_COMPLETE", "mode": "sharded",
            "admission_sha256": value["admission_sha256"], "ordinary": result,
            "skip_admission": admit_skips(value, result, native),
            "runner_observations": runner_summary(expected["context"], runners),
            "native_and_source_gates": native, "host_linux_skip_policy": "ROOT_GATE_UNCHANGED"}


def retain_rejection(args, error):
    """Keep a failed diagnostic, never a synthetic pytest/native terminal."""
    output = args.output.absolute()
    require(not any(p.is_symlink() for p in (output, *output.parents)),
            "unsafe rejection evidence directory")
    output.mkdir(parents=True, exist_ok=True)
    require(output.is_dir(), "invalid rejection evidence directory")
    safe = {}
    for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_SHA",
                "RUNNER_OS", "RUNNER_ARCH", "ImageVersion"):
        value = os.environ.get(key)
        safe[key] = (value if isinstance(value, str)
                     and re.fullmatch(r"[A-Za-z0-9._-]{1,128}", value) else None)
    record = {"schema": 1, "status": "REJECTED", "release_acceptance": False,
              "stage": args.command, "error_class": type(error).__name__,
              "identity": safe, "recorded_unix_ns": time.time_ns()}
    record["reason_code"] = {
        "missing runner identity": "RUNNER_IDENTITY_MISSING",
        "executing runner OS or architecture differs": "RUNNER_PLATFORM_MISMATCH",
        "executing source differs or is dirty": "SOURCE_IDENTITY_MISMATCH",
        "runner identity changed during preparation": "RUNNER_CHANGED",
        "runner identity changed during execution": "RUNNER_CHANGED",
        "native runner identity changed during execution": "RUNNER_CHANGED",
    }.get(str(error), "VALIDATION_REJECTED")
    role = getattr(args, "role", "native")
    record["assignment_id"] = role if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", role) else None
    if args.admission.is_file() and not args.admission.is_symlink():
        record["admission_file_sha256"] = sha(args.admission.read_bytes())
    with (output / "rejected.json").open("x") as handle:
        handle.write(json.dumps(record) + "\n")


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
    expand_cli = sub.add_parser("expand")
    expand_cli.add_argument("--targets", type=Path, required=True)
    expand_cli.add_argument("--source", type=Path)
    expand_cli.add_argument("--board", required=True)
    expand_cli.add_argument("--runner", required=True)
    expand_cli.add_argument("--capacity", type=int, required=True)
    expand_cli.add_argument("--shards", type=int, required=True)
    run_cli = sub.add_parser("run")
    run_cli.add_argument("--admission", type=Path, required=True)
    run_cli.add_argument("--source", type=Path, required=True)
    run_cli.add_argument("--board", type=Path, required=True)
    run_cli.add_argument("--role", required=True)
    run_cli.add_argument("--output", type=Path, required=True)
    run_cli.add_argument("--site", type=Path, default=Path(sysconfig.get_paths()["purelib"]))
    for name in ("native-start", "native-terminal"):
        native_cli = sub.add_parser(name)
        for key in ("admission", "source", "board", "output"):
            native_cli.add_argument("--" + key, type=Path, required=True)
    join_cli = sub.add_parser("join")
    join_cli.add_argument("--admission", type=Path, required=True)
    join_cli.add_argument("--evidence", type=Path, required=True)
    join_cli.add_argument("--validation-result", required=True)
    join_cli.add_argument("--expected-sha", required=True)
    baseline_cli = sub.add_parser("generate-skip-baseline")
    for key in ("source", "events", "collection-xml", "collection-events"):
        baseline_cli.add_argument("--" + key, type=Path, required=True)
    for key in ("revision", "collection-revision", "collection-at"):
        baseline_cli.add_argument("--" + key, required=True)
    args = parser.parse_args()
    try:
        if args.command == "plan":
            result = plan(args.source, read_json(args.context), args.shards, args.serial_module)
        elif args.command == "aggregate":
            result = aggregate(read_json(args.plan), args.reference, args.shard)
        elif args.command == "expand":
            result = expand(read_json(args.targets), args.source, args.board,
                            args.runner, args.capacity, args.shards)
        elif args.command == "generate-skip-baseline":
            result = generate_skip_baseline(
                args.source, args.revision, args.events, args.collection_xml,
                args.collection_events, args.collection_revision, args.collection_at)
        elif args.command == "run":
            return execute(read_json(args.admission), args.source, args.board, args.role,
                           args.output, args.site)
        elif args.command in ("native-start", "native-terminal"):
            function = native_start if args.command == "native-start" else native_terminal
            result = function(read_json(args.admission), args.source, args.board, args.output)
        else:
            result = join(read_json(args.admission), args.evidence, args.validation_result,
                          args.expected_sha)
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        if args.command in ("run", "native-start", "native-terminal"):
            try:
                retain_rejection(args, error)
            except (ValueError, OSError) as retained_error:
                print(json.dumps({"diagnostic_retention": "FAILED",
                                  "error_class": type(retained_error).__name__}), file=sys.stderr)
        print(json.dumps({"status": "REJECTED", "release_acceptance": False,
                          "problem": str(error)}), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
