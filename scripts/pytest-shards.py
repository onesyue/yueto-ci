#!/usr/bin/env python3
"""Plan Ops jobs, execute the source-owned selection and strictly join evidence.

The ordinary corpus verdict alone never supplies complete release acceptance.
"""
from __future__ import annotations

import argparse
import ast
import concurrent.futures
import configparser
import copy
import hashlib
import importlib.util
import inspect
import json
import os
import re
import subprocess
import sys
import sysconfig
import tempfile
import time
import types
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
_SOURCE_SPEC = importlib.util.spec_from_file_location("trusted_source_evidence", ROOT / "scripts/source_evidence.py")
source_evidence = importlib.util.module_from_spec(_SOURCE_SPEC)
_SOURCE_SPEC.loader.exec_module(source_evidence)
SHA = re.compile(r"[0-9a-f]{40}")
EXPECTED_CONFIG = {
    "testpaths": "tests", "python_files": "test_*.py",
    "python_functions": "test_*", "asyncio_mode": "auto",
}
# Temp-dir retention keys only bound what pytest keeps on disk after a run;
# they never change which modules or tests are collected.
OPTIONAL_RETENTION_CONFIG = {
    "tmp_path_retention_policy": "failed", "tmp_path_retention_count": "1",
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
AUDIT_DEPENDENCY_TRANSITION_SHA256 = "ff5a2514cd10c6c9cc81cb1e4e52afab20ba789b8a8af92ef4dcbd21cbbb1b6a"
ZOD_LOCK_TRANSITION_SHA256 = "691c045988e884f360dc6925bffea7798295970f2d62763ffec180ff2b20e842"
CURRENT_SKIP_TRANSITION_SHA256 = "302153cd755ac54d2346e0c3114fcfde776ba8ea79fbe2fd4d7de9d7cdae726d"
SCANNER_INPUT_TRANSITION_SHA256 = "5a639c8b455a5934d206af1f4e03d386d91b55a986f2e52ffc79cbedd2d1563c"
RELAY_SKIP_MODULE_TRANSITION_SHA256 = "afab000651dcbd556b14b27b27ecfc283f935f78be984293dbf2f1dcf971042b"
RELAY_METER_MODULE_TRANSITION_SHA256 = "99945322ac036c84b3a4a87e6f9378156e14e5cc1ec6d04680d69c54d44ad2df"
RELAY_PRESERVATION_MODULE_TRANSITION_SHA256 = "f5d43ba785159b00ab42f7034d29c77d78d8d9164f89b46b76d88a093c81407b"
RELAY_METRICS_MODULE_TRANSITION_SHA256 = "777214bee79eb25858c97781aaa065b53770693252185f3ee61e19c3c61efa07"
CASE_FILE_TRANSITION_SHA256 = "75190b489a8b271e693c52e78c183894f47e34e930183b9f433e538045afb9c7"
SKIP_BLOB_SUCCESSOR_TRANSITION_SHA256 = "befa7b3d2cb2c5d3bbeb6e225f908087b1cd42c0bedbe290033a73b3fffe799d"
I10_SKIP_BLOB_SUCCESSOR_TRANSITION_SHA256 = "f17408349a9f920c4712e112381a0b1ad40b00abc5d9357b6e423812b7e3ba20"
RELEASE_SKIP_BLOB_SUCCESSOR_TRANSITION_SHA256 = "efa7c2e8c9944feeccbcf0bf1111b3b4b67f8b15c94e1b6d41879654136d274b"
HANG_GUARD_INPUT_TRANSITION_SHA256 = "eb65c84d7ddab61a441c54d2f64a30e992f039b2c0c6ba709b570f5d3787fff0"
# Sealed to the signed Tornado successor and authentic review/qualification receipts.
TORNADO66_DEPENDENCY_TRANSITION_SHA256 = "bed6e74fdb1a4b40775bc6fc9c4c4c6857ee6de8a245910e91809e7672756876"
# Sealed to the signed yueops 65887947/22a82f65 four-input successor and its receipts.
OPS_PACKAGING_TRANSITION_SHA256 = "755b998311346730753ebc2c44dd8a3dcb4b3bb9216756b6f126125b07b8fb27"
SSH_SKIP_CASES = {
    "tests/test_host_service_contracts_20261013.py::test_node_producer_is_durable_and_idempotent",
    "tests/test_installed_checker_transport_20261014.py::"
    "test_real_pinned_sshd_json_transport_plan_apply_readback_and_old_n_negative",
}
HISTORICAL_NATIVE_INPUTS = {
    "tests/native_loadshed_installer_20261030.py": "a861b1d6b30b3ba59d5321051430c73c099d25c2",
}
NATIVE_INPUTS = {
    "tests/native_loadshed_installer_20261030.py": "441aa89516d7a8afa651486cb893090563efe9d9",
}
# Reviewed pins of the same installer, oldest admitted tip last excluded.
# The historical predecessor stays rejected. Unknown blobs stay rejected.
# Each entry was the signed after-blob of a loadshed row-count ratchet.
NATIVE_INPUT_CHAIN = {
    "tests/native_loadshed_installer_20261030.py": frozenset({
        "b4a70d6d7c6c1b3e20e7263d8f12c4a69143b385",
        "4fe2c7b40110f20fa496b0fdd85cfe8c75da8591",
        "441aa89516d7a8afa651486cb893090563efe9d9",
    }),
}
NATIVE_INPUT_SUCCESSOR_KEY = "reviewed_loadshed_native_input_successor"
# Filled only from the actual signed source/review/qualification record.
NATIVE_INPUT_SUCCESSOR_SHA256 = "1c6883845729d08bb3ff932f54630a4cb25420b95b97650e5ee468c83333891f"
NATIVE_TARGETS = {
    "tests/native_loadshed_installer_20261030.py": (14, 0),
    "tests/test_board139_schema_acl_native_20261018.py": (6, 1001),
    "tests/test_node_systemd_pilot_20261018.py": (38, 0),
    "tests/test_schema_contract_receipt_20261020.py": (30, 0),
    "tests/test_panel_subscribe_delivery_alert_20261012.py": (17, 0),
    "tests/test_frozen_manifest_reader_20261015.py": (4, 0),
    "tests/test_status_tls_installer_20261027.py": (7, 0),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode()


class EvidenceUnavailable(ValueError):
    """Local Git history cannot establish the admission policy's ancestry."""


def git(source, *args):
    try:
        return subprocess.check_output(["git", "-C", str(source), *args],
                                       stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as error:
        # merge-base exit 1 means proven non-ancestry; higher codes mean the
        # proof could not run (for example a missing sealed predecessor).
        if args[:2] == ("merge-base", "--is-ancestor") and error.returncode != 1:
            raise EvidenceUnavailable("local ancestry evidence unavailable") from None
        raise


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


def collection_config_ok(actual):
    """Exact collection keys, plus only the reviewed retention keys/values."""
    extra = {k: v for k, v in actual.items() if k not in EXPECTED_CONFIG}
    return (all(actual.get(k) == v for k, v in EXPECTED_CONFIG.items())
            and all(OPTIONAL_RETENTION_CONFIG.get(k) == v for k, v in extra.items()))


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


def reviewed_relay_preservation_module_transition(baseline, files=None):
    """Bind the reviewed preservation repair without relabeling any predecessor."""
    original = dict(baseline)
    key = "reviewed_relay_preservation_module_transition"
    record = original.pop(key, None)
    if key not in baseline:
        return original, {}
    require(isinstance(record, dict) and set(record) == {
        "schema", "prior_baseline_sha256", "source_before", "source_after",
        "qualified_policy_revision", "independent_review_sha256",
        "source_freeze_sha256", "qualification_receipt_sha256", "module",
    } and type(record["schema"]) is int and record["schema"] == 1,
            "invalid reviewed relay preservation transition")
    require(sha(encoded(record)) == RELAY_PRESERVATION_MODULE_TRANSITION_SHA256,
            "unreviewed relay preservation transition identity")
    restored = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
    require(record["prior_baseline_sha256"] == sha(restored),
            "relay preservation transition historical baseline changed")
    predecessor = original.get("reviewed_relay_meter_module_transition")
    require(isinstance(predecessor, dict)
            and record["source_before"] == predecessor.get("source_after")
            and record["source_before"] != record["source_after"]
            and all(isinstance(record[k], str) and SHA.fullmatch(record[k]) for k in
                    ("source_before", "source_after", "qualified_policy_revision"))
            and all(isinstance(record[k], str) and re.fullmatch(r"[0-9a-f]{64}", record[k])
                    for k in ("independent_review_sha256", "source_freeze_sha256",
                              "qualification_receipt_sha256")),
            "missing exact relay preservation review identity")
    module = record["module"]
    require(isinstance(module, dict) and set(module) == {
        "path", "mode", "before_blob", "after_blob",
    } and module["path"] == "tests/test_relay4_tuning_20261025.py"
            and module["mode"] == "100644"
            and all(isinstance(module[k], str) and SHA.fullmatch(module[k])
                    for k in ("before_blob", "after_blob"))
            and module["before_blob"] != module["after_blob"],
            "invalid reviewed relay preservation module identity")
    if files is not None and files.get(module["path"], (None, None))[1] == module["after_blob"]:
        require(files[module["path"]][0] == module["mode"], "relay preservation module mode changed")
    # Removing this outer record terminates the predecessor's peeling recursion.
    _, cases = reviewed_relay_meter_module_transition(original, files)
    require(len(cases) == 10 and all(case["module_blob"] == module["before_blob"]
                                   for case in cases.values()),
            "relay preservation predecessor cases differ")
    return original, {nodeid: case | {"module_blob": module["after_blob"]}
                      for nodeid, case in cases.items()}


def reviewed_relay_meter_module_transition(baseline, files=None):
    """Bind the reviewed meter repair without relabeling any predecessor."""
    original, _ = reviewed_relay_preservation_module_transition(baseline, files)
    key = "reviewed_relay_meter_module_transition"
    record = original.pop(key, None)
    if key not in baseline:
        return original, {}
    require(isinstance(record, dict) and set(record) == {
        "schema", "prior_baseline_sha256", "source_before", "source_after",
        "qualified_policy_revision", "independent_review_sha256",
        "source_freeze_sha256", "qualification_receipt_sha256", "module",
    } and type(record["schema"]) is int and record["schema"] == 1,
            "invalid reviewed relay meter transition")
    require(sha(encoded(record)) == RELAY_METER_MODULE_TRANSITION_SHA256,
            "unreviewed relay meter transition identity")
    restored = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
    require(record["prior_baseline_sha256"] == sha(restored),
            "relay meter transition historical baseline changed")
    predecessor = original.get("reviewed_relay_metrics_module_transition")
    require(isinstance(predecessor, dict)
            and record["source_before"] == predecessor.get("source_after")
            and record["source_before"] != record["source_after"]
            and all(isinstance(record[k], str) and SHA.fullmatch(record[k]) for k in
                    ("source_before", "source_after", "qualified_policy_revision"))
            and all(isinstance(record[k], str) and re.fullmatch(r"[0-9a-f]{64}", record[k])
                    for k in ("independent_review_sha256", "source_freeze_sha256",
                              "qualification_receipt_sha256")),
            "missing exact relay meter review identity")
    module = record["module"]
    require(isinstance(module, dict) and set(module) == {
        "path", "mode", "before_blob", "after_blob",
    } and module["path"] == "tests/test_relay4_tuning_20261025.py"
            and module["mode"] == "100644"
            and all(isinstance(module[k], str) and SHA.fullmatch(module[k])
                    for k in ("before_blob", "after_blob"))
            and module["before_blob"] != module["after_blob"],
            "invalid reviewed relay meter module identity")
    if files is not None and files.get(module["path"], (None, None))[1] == module["after_blob"]:
        require(files[module["path"]][0] == module["mode"], "relay meter module mode changed")
    # Removing this outer record terminates the predecessor's peeling recursion.
    _, cases = reviewed_relay_metrics_module_transition(original, files)
    require(len(cases) == 10 and all(case["module_blob"] == module["before_blob"]
                                   for case in cases.values()),
            "relay meter predecessor cases differ")
    return original, {nodeid: case | {"module_blob": module["after_blob"]}
                      for nodeid, case in cases.items()}


def reviewed_relay_metrics_module_transition(baseline, files=None):
    """Bind the reviewed metrics repair without relabeling either predecessor."""
    original, _ = reviewed_relay_meter_module_transition(baseline, files)
    key = "reviewed_relay_metrics_module_transition"
    record = original.pop(key, None)
    if key not in baseline:
        return original, {}
    require(isinstance(record, dict) and set(record) == {
        "schema", "prior_baseline_sha256", "source_before", "source_after",
        "qualified_policy_revision", "independent_review_sha256",
        "source_freeze_sha256", "qualification_receipt_sha256", "module",
    } and type(record["schema"]) is int and record["schema"] == 1,
            "invalid reviewed relay metrics transition")
    require(sha(encoded(record)) == RELAY_METRICS_MODULE_TRANSITION_SHA256,
            "unreviewed relay metrics transition identity")
    restored = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
    require(record["prior_baseline_sha256"] == sha(restored),
            "relay metrics transition historical baseline changed")
    predecessor = original.get("reviewed_relay_skip_module_transition")
    require(isinstance(predecessor, dict)
            and record["source_before"] == predecessor.get("source_after")
            and record["source_before"] != record["source_after"]
            and all(isinstance(record[k], str) and SHA.fullmatch(record[k]) for k in
                    ("source_before", "source_after", "qualified_policy_revision"))
            and all(isinstance(record[k], str) and re.fullmatch(r"[0-9a-f]{64}", record[k])
                    for k in ("independent_review_sha256", "source_freeze_sha256",
                              "qualification_receipt_sha256")),
            "missing exact relay metrics review identity")
    module = record["module"]
    require(isinstance(module, dict) and set(module) == {
        "path", "mode", "before_blob", "after_blob",
    } and module["path"] == "tests/test_relay4_tuning_20261025.py"
            and module["mode"] == "100644"
            and all(isinstance(module[k], str) and SHA.fullmatch(module[k])
                    for k in ("before_blob", "after_blob"))
            and module["before_blob"] != module["after_blob"],
            "invalid reviewed relay metrics module identity")
    if files is not None and files.get(module["path"], (None, None))[1] == module["after_blob"]:
        require(files[module["path"]][0] == module["mode"], "relay metrics module mode changed")
    # Removing this outer record terminates the predecessor's peeling recursion.
    _, cases = reviewed_relay_skip_module_transition(original, files)
    require(len(cases) == 10 and all(case["module_blob"] == module["before_blob"]
                                   for case in cases.values()),
            "relay metrics predecessor cases differ")
    return original, {nodeid: case | {"module_blob": module["after_blob"]}
                      for nodeid, case in cases.items()}


def reviewed_relay_skip_module_transition(baseline, files=None):
    """Add one reviewed module identity without replacing historical skip facts."""
    original, _ = reviewed_relay_metrics_module_transition(baseline, files)
    key = "reviewed_relay_skip_module_transition"
    record = original.pop(key, None)
    if key not in baseline:
        return original, {}
    require(isinstance(record, dict) and set(record) == {
        "schema", "prior_baseline_sha256", "source_before", "source_after",
        "qualified_policy_revision", "independent_review_sha256",
        "source_freeze_sha256", "qualification_receipt_sha256", "module",
    } and type(record["schema"]) is int and record["schema"] == 1,
            "invalid reviewed relay skip transition")
    require(sha(encoded(record)) == RELAY_SKIP_MODULE_TRANSITION_SHA256,
            "unreviewed relay skip transition identity")
    restored = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
    require(record["prior_baseline_sha256"] == sha(restored),
            "relay skip transition historical baseline changed")
    require(all(isinstance(record[k], str) and SHA.fullmatch(record[k]) for k in
                ("source_before", "source_after", "qualified_policy_revision"))
            and record["source_before"] != record["source_after"]
            and all(isinstance(record[k], str) and re.fullmatch(r"[0-9a-f]{64}", record[k])
                    for k in ("independent_review_sha256", "source_freeze_sha256",
                              "qualification_receipt_sha256")),
            "missing exact relay skip review identity")
    module = record["module"]
    require(isinstance(module, dict) and set(module) == {
        "path", "mode", "before_blob", "after_blob",
    } and module["path"] == "tests/test_relay4_tuning_20261025.py"
            and module["mode"] == "100644"
            and all(isinstance(module[k], str) and SHA.fullmatch(module[k])
                    for k in ("before_blob", "after_blob"))
            and module["before_blob"] != module["after_blob"],
            "invalid reviewed relay module identity")
    if files is not None and files.get(module["path"], (None, None))[1] == module["after_blob"]:
        require(files[module["path"]][0] == module["mode"], "relay skip module mode changed")
    cases = {nodeid: case for nodeid, case in original[
        "reviewed_current_skip_transition"]["additions"].items()
        if nodeid.startswith(module["path"] + "::")}
    require(len(cases) == 10 and all(
        case["outcome"] == "skipped" and case["module_blob"] == module["before_blob"]
        for case in cases.values()), "relay skip predecessor cases differ")
    return original, {nodeid: case | {"module_blob": module["after_blob"]}
                      for nodeid, case in cases.items()}


def reviewed_scanner_input_transition(baseline):
    """Peel the exact scanner-helper successor without relabeling old evidence."""
    baseline, _ = reviewed_relay_skip_module_transition(baseline)
    original = dict(baseline)
    key = "reviewed_scanner_input_transition"
    record = original.pop(key, None)
    if key not in baseline:
        return original, None
    require(isinstance(record, dict) and set(record) == {
        "schema", "prior_baseline_sha256", "source_before", "source_after",
        "qualified_policy_revision", "independent_review_sha256",
        "source_freeze_sha256", "qualification_receipt_sha256", "changes",
    } and type(record["schema"]) is int and record["schema"] == 1,
            "invalid reviewed scanner input transition")
    require(sha(encoded(record)) == SCANNER_INPUT_TRANSITION_SHA256,
            "unreviewed scanner input transition identity")
    restored = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
    require(record["prior_baseline_sha256"] == sha(restored),
            "scanner input transition historical baseline changed")
    require(all(isinstance(record[k], str) and SHA.fullmatch(record[k]) for k in
                ("source_before", "source_after", "qualified_policy_revision"))
            and record["source_before"] != record["source_after"]
            and all(isinstance(record[k], str) and re.fullmatch(r"[0-9a-f]{64}", record[k])
                    for k in ("independent_review_sha256", "source_freeze_sha256",
                              "qualification_receipt_sha256")),
            "missing exact scanner input review identity")
    return original, record


def reviewed_current_skip_transition(baseline):
    """Admit the exact new host skips and refreshed module blobs."""
    baseline, _ = reviewed_scanner_input_transition(baseline)
    original = dict(baseline)
    key = "reviewed_current_skip_transition"
    record = original.pop(key, None)
    if key not in baseline:
        return original, {}
    require(isinstance(record, dict) and set(record) == {
        "schema", "prior_baseline_sha256", "source_revision",
        "independent_review_sha256", "additions", "updates",
    } and type(record["schema"]) is int and record["schema"] == 1,
            "invalid reviewed current skip transition")
    require(sha(encoded(record)) == CURRENT_SKIP_TRANSITION_SHA256,
            "unreviewed current skip transition identity")
    restored = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
    require(record["prior_baseline_sha256"] == sha(restored),
            "current skip transition historical baseline changed")
    require(isinstance(record["source_revision"], str) and SHA.fullmatch(record["source_revision"])
            and isinstance(record["independent_review_sha256"], str)
            and re.fullmatch(r"[0-9a-f]{64}", record["independent_review_sha256"]),
            "missing exact current skip review identity")
    additions = record["additions"]
    updates = record["updates"]
    require(isinstance(additions, dict) and isinstance(updates, dict)
            and not (set(additions) & set(updates) or set(additions) & set(original["cases"])),
            "current skip cases overlap history")
    successors = {}
    for nodeid, change in updates.items():
        historical = original["cases"].get(nodeid)
        require(isinstance(historical, dict) and historical.get("outcome") == "skipped"
                and isinstance(change, dict) and set(change) == {"before_blob", "after_blob"}
                and change["before_blob"] == historical.get("module_blob")
                and change["before_blob"] != change["after_blob"]
                and SHA.fullmatch(change["after_blob"]),
                "unreviewed current skip blob update: " + nodeid)
        successors[nodeid] = {
            "outcome": "skipped", "reason": historical["reason"],
            "module_blob": change["after_blob"],
        }
    for nodeid, case in additions.items():
        require(isinstance(case, dict) and set(case) == {"outcome", "reason", "module_blob"}
                and case["outcome"] == "skipped" and isinstance(case["reason"], str) and case["reason"]
                and SHA.fullmatch(case["module_blob"]),
                "unreviewed current skip addition: " + nodeid)
        successors[nodeid] = dict(case)
    return original, successors


def reviewed_zod_lock_transition(baseline):
    """Peel the exact zod 4.6.7 lock successor without changing history."""
    baseline, _ = reviewed_current_skip_transition(baseline)
    original = dict(baseline)
    key = "reviewed_zod_lock_transition"
    record = original.pop(key, None)
    if key not in baseline:
        return original, None
    require(isinstance(record, dict) and set(record) == {
        "schema", "prior_baseline_sha256", "source_before", "source_after",
        "qualified_policy_revision", "independent_review_sha256",
        "source_freeze_sha256", "qualification_receipt_sha256", "changes",
    } and type(record["schema"]) is int and record["schema"] == 1,
            "invalid reviewed zod lock transition")
    require(sha(encoded(record)) == ZOD_LOCK_TRANSITION_SHA256,
            "unreviewed zod lock transition identity")
    restored = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
    require(record["prior_baseline_sha256"] == sha(restored),
            "zod lock transition historical baseline changed")
    return original, record


def reviewed_audit_dependency_transition(baseline):
    baseline, _ = reviewed_zod_lock_transition(baseline)
    original = dict(baseline)
    key = "reviewed_audit_dependency_transition"
    record = original.pop(key, None)
    if key not in baseline:
        return original, None
    require(isinstance(record, dict) and set(record) == {
        "schema", "prior_baseline_sha256", "source_before", "source_after",
        "qualified_policy_revision", "independent_review_sha256",
        "source_freeze_sha256", "qualification_receipt_sha256", "changes",
    } and type(record["schema"]) is int and record["schema"] == 1,
            "invalid reviewed audit dependency transition")
    require(sha(encoded(record)) == AUDIT_DEPENDENCY_TRANSITION_SHA256,
            "unreviewed audit dependency transition identity")
    restored = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
    require(record["prior_baseline_sha256"] == sha(restored),
            "audit dependency transition historical baseline changed")
    return original, record


def reviewed_w85_observability_transition(baseline):
    """Peel the exact observability successor without changing historical evidence."""
    baseline, _ = reviewed_audit_dependency_transition(baseline)
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


ESTATE_INPUT_PATHS = {
    "qa/package.json", "qa/package-lock.json", "telegram-bot/yue/pyproject.toml",
    "tests/node_resource_fixture.py", "tests/native/subscribe_template_baseline_cas_pg.py",
}
ESTATE_ADDED_INPUT = "tests/native/subscribe_template_baseline_cas_pg.py"

# Preserve the historical estate seal, but retire its source-copy writer probe
# only after the exact reviewed deletion. No historical execution is credited.
TEMPLATE_WRITER_RETIREMENT = "6f7a1f635c94c9c5a0aeeb993c7893d7efe48dfc"
TEMPLATE_WRITER_BEFORE_BLOB = "1933467673713272e85f47a5732692d1c285a858"


def template_writer_retirement_proof(source, revision):
    """Prove the one retired helper disappeared in the reviewed source history."""
    try:
        git(source, "cat-file", "-e", TEMPLATE_WRITER_RETIREMENT + "^{commit}")
    except subprocess.CalledProcessError:
        return None  # Old checkouts need not contain a future retirement commit.
    try:
        git(source, "merge-base", "--is-ancestor", TEMPLATE_WRITER_RETIREMENT, revision)
    except subprocess.CalledProcessError as exc:
        require(exc.returncode == 1, "template writer retirement ancestry unavailable")
        return None
    parent = git(source, "rev-parse", TEMPLATE_WRITER_RETIREMENT + "^1").decode().strip()
    before = tree_inputs(source, parent)
    retired = tree_inputs(source, TEMPLATE_WRITER_RETIREMENT)
    current = tree_inputs(source, revision)
    require(before.get(ESTATE_ADDED_INPUT) == ("100644", TEMPLATE_WRITER_BEFORE_BLOB)
            and ESTATE_ADDED_INPUT not in retired and ESTATE_ADDED_INPUT not in current,
            "template writer retirement tree differs")
    return TEMPLATE_WRITER_RETIREMENT


def admit_retired_template_writer(baseline, common, files, source_revision,
                                  estate_successor_of, template_writer_retired_at):
    if template_writer_retired_at is None:
        return common, files
    _, estate = reviewed_estate_input_transition(baseline)
    require(template_writer_retired_at == TEMPLATE_WRITER_RETIREMENT
            and isinstance(source_revision, str) and SHA.fullmatch(source_revision)
            and estate is not None and source_revision != estate["source_after"]
            and estate_successor_of == estate["source_after"]
            and estate["changes"][ESTATE_ADDED_INPUT]["after_blob"] == TEMPLATE_WRITER_BEFORE_BLOB
            and isinstance(common, dict) and ESTATE_ADDED_INPUT not in common,
            "invalid template writer retirement admission")
    if files is not None:
        require(ESTATE_ADDED_INPUT not in files, "retired template writer is present")
        files = dict(files) | {ESTATE_ADDED_INPUT: ("100644", TEMPLATE_WRITER_BEFORE_BLOB)}
    # Comparison-only copy: the sealed current source map still records absence.
    return dict(common) | {ESTATE_ADDED_INPUT: TEMPLATE_WRITER_BEFORE_BLOB}, files


SITE_LOCK_INPUT = "site/pnpm-lock.yaml"
BOT_PACKAGING_INPUT = "telegram-bot/yue/pyproject.toml"
HANG_GUARD_INPUT = "tests/_subprocess.py"


AUDIT_LOCK_INPUT = "uv.lock"


# Each runtime dependency input is bound to the exact after-blob of the seal that
# last reviewed it; nothing outside these three paths may move.
RUNTIME_DEPENDENCY_INPUTS = {
    "pyproject.toml": "reviewed_audit_dependency_transition",
    "telegram-bot/yue/requirements.txt": "reviewed_python_input_transition",
    "uv.lock": "reviewed_audit_lock_transition",
}


RETIRED_HOST_KEY = "reviewed_retired_host_transition"
RETIRED_HOST_MODULE = "tests/test_miniapp_existing_app_nginx_native_20261013.py"
RETIRED_HOST_PRIOR_SHA256 = "927f711ddbdd4aa14012ccb687183e969610922e0c9b17b55eef06545ec86e91"
RETIRED_HOST_BEFORE_BLOB = "812e3509c7213cf16f507271f5a1d4f8c0cefe29"
RETIRED_HOST_AFTER_BLOB = "ba19e043309d0805710e0a2d3fc9cc76ea6ce55f"
RETIRED_HOST_TRANSITION_SHA256 = "961fa6fd314c9d292e766e1cea5b8571f0d97b489adbebb63d4f35d16af6d7b0"
RETIRED_HOST_IDS = {
    RETIRED_HOST_MODULE + "::" + name + "[mini.xn--jdu596h.com]"
    for name in (
        "test_native_mini_index_assets_and_telegram_frame_policy",
        "test_native_auth_is_not_panel_cookie_or_bearer_and_secret_paths_do_not_log",
        "test_native_alias_upload_method_body_limits_and_cache",
    )
}

# 2026-11-10 (owner t836u, yueops fdf97f87e / 3ed500a0f): the sibling Mini host
# mini.xn--9kq451mn9g.com was retired too and the fixture certificate moved to
# app.yue.to.  This is a code-reviewed successor on top of the sealed transition
# above; it changes no baseline bytes.  With exactly this module blob, the three
# mini.xn--9kq451mn9g.com cases must be absent and every other survivor keeps its
# sealed outcome and reason.  Any other blob still has to equal the sealed case.
RETIRED_HOST_SECOND_AFTER_BLOB = "6c3e8eca2a185a9b89aedbc3abec63c7cc2eb2fd"
RETIRED_HOST_SECOND_IDS = {
    RETIRED_HOST_MODULE + "::" + name + "[mini.xn--9kq451mn9g.com]"
    for name in (
        "test_native_mini_index_assets_and_telegram_frame_policy",
        "test_native_auth_is_not_panel_cookie_or_bearer_and_secret_paths_do_not_log",
        "test_native_alias_upload_method_body_limits_and_cache",
    )
}


def retired_host_case_admitted(retirement, sealed_cases, nodeid, row, live_blob):
    if nodeid not in retirement["surviving_ids"]:
        return False
    sealed = sealed_cases.get(nodeid)
    if live_blob == RETIRED_HOST_SECOND_AFTER_BLOB:
        return (nodeid not in RETIRED_HOST_SECOND_IDS and isinstance(sealed, dict)
                and sealed.get("module_blob") == RETIRED_HOST_AFTER_BLOB
                and {"outcome": row["outcome"], "reason": row.get("reason")}
                == {"outcome": sealed.get("outcome"), "reason": sealed.get("reason")})
    return {"outcome": row["outcome"], "reason": row.get("reason"),
            "module_blob": live_blob} == sealed


def baseline_bytes(baseline):
    return (json.dumps(baseline, indent=2, ensure_ascii=False) + "\n").encode()


NEZHA_RETIREMENT_KEY = "owner_nezha_retirement_20261103"
NEZHA_RETIRED_MODULE = "tests/test_nezha_retirement_20261013.py"
NEZHA_PRIOR_BASELINE_SHA256 = "190f2ad9a50a78d0d8bfac1eb383f350e36586688510aa025e74435e6c28332d"


def reviewed_native_input_successor(baseline):
    """Peel the exact reviewed native successor without changing any old seal."""
    if NATIVE_INPUT_SUCCESSOR_KEY not in baseline:
        return baseline, None
    original = dict(baseline)
    record = original.pop(NATIVE_INPUT_SUCCESSOR_KEY)
    require(isinstance(record, dict) and set(record) == {
        "schema", "prior_baseline_sha256", "source_before", "source_after",
        "independent_review_sha256", "source_freeze_sha256",
        "qualification_receipt_sha256", "changes",
    } and type(record["schema"]) is int and record["schema"] == 1,
            "invalid native input successor")
    require(sha(encoded(record)) == NATIVE_INPUT_SUCCESSOR_SHA256,
            "unreviewed native input successor identity")
    require(record["prior_baseline_sha256"] == sha(baseline_bytes(original)),
            "native input successor changed historical baseline")
    require(all(isinstance(record[k], str) and SHA.fullmatch(record[k])
                for k in ("source_before", "source_after"))
            and record["source_before"] != record["source_after"],
            "native input successor source identity missing")
    require(all(isinstance(record[k], str)
                and re.fullmatch(r"[0-9a-f]{64}", record[k])
                and record[k] != "0" * 64 for k in (
                    "independent_review_sha256", "source_freeze_sha256",
                    "qualification_receipt_sha256")),
            "native input successor evidence missing")
    changes = record["changes"]
    require(isinstance(changes, dict) and set(changes) == set(NATIVE_INPUTS),
            "unreviewed native input successor paths")
    for path, after_blob in NATIVE_INPUTS.items():
        require(changes[path] == {
            "before_blob": HISTORICAL_NATIVE_INPUTS[path], "after_blob": after_blob,
            "mode": "100644", "floor": 14, "uid": 0,
        } and type(changes[path].get("floor")) is int
          and type(changes[path].get("uid")) is int,
                "invalid native input successor blob, mode, floor or UID")
    return original, record


def restore_nezha_history(baseline):
    """Restore only the owner's two retired cases for existing historical seals."""
    baseline, _ = reviewed_native_input_successor(baseline)
    if NEZHA_RETIREMENT_KEY not in baseline:
        return baseline
    original = dict(baseline)
    record = original.pop(NEZHA_RETIREMENT_KEY)
    require(isinstance(record, dict) and type(record.get("schema")) is int
            and type(record.get("removed_case_count")) is int
            and record == {"schema": 1, "prior_baseline_sha256": NEZHA_PRIOR_BASELINE_SHA256,
                           "removed_case_count": 2}, "invalid Nezha retirement record")
    cases = original["cases"]
    require(not any(n.split("::", 1)[0] == NEZHA_RETIRED_MODULE for n in cases),
            "retired Nezha cases remain in active baseline")
    items = list(cases.items())
    for index, name in enumerate(("test_apply_archives_then_removes_only_reviewed_bytes",
                                  "test_changed_file_blocks_before_stop"), start=445):
        items.insert(index, (NEZHA_RETIRED_MODULE + "::" + name, {
            "outcome": "skipped",
            "reason": "Skipped: real archive ownership requires isolated Linux root",
            "module_blob": "f378f0ec5098b6f2664e97b266efd4031df0165c",
        }))
    # Existing inner seals verify these exact bytes, including insertion order.
    original["cases"] = dict(items)
    return original


def historical_skip_baseline_bytes():
    # Sidecar seals bind the repository baseline, not a caller's execution fixture.
    raw = (ROOT / "ops-pytest-skip-baseline.json").read_bytes()
    baseline, successor = reviewed_native_input_successor(json.loads(raw))
    if NEZHA_RETIREMENT_KEY not in baseline:
        return baseline_bytes(baseline) if successor else raw
    restored = baseline_bytes(restore_nezha_history(baseline))
    require(sha(restored) == NEZHA_PRIOR_BASELINE_SHA256,
            "Nezha retirement changed historical baseline")
    return restored


SECURITY_INPUT_KEY = "reviewed_npm_security_transition"
SECURITY_INPUT_PATHS = frozenset({"frontend/package.json", "frontend/package-lock.json",
    "telegram-bot/yue/miniapp/package.json", "telegram-bot/yue/miniapp/package-lock.json"})
SECURITY_INPUT_TRANSITION_SHA256 = "92aae6604a0d8a027c667313be6fbaf9dc1f87ee260cf7baed00d57f2f767bb2"


def reviewed_npm_security_transition(baseline):
    baseline = restore_nezha_history(baseline)
    if SECURITY_INPUT_KEY not in baseline:
        return baseline, None
    original = dict(baseline)
    record = original.pop(SECURITY_INPUT_KEY)
    require(isinstance(record, dict) and set(record) == {
        "schema", "prior_baseline_sha256", "source_before", "source_after",
        "independent_review_sha256", "source_freeze_sha256",
        "qualification_receipt_sha256", "changes"}
        and type(record["schema"]) is int and record["schema"] == 1,
        "invalid npm security transition")
    require(sha(encoded(record)) == SECURITY_INPUT_TRANSITION_SHA256,
            "unreviewed npm security transition")
    require(record["prior_baseline_sha256"] == sha(baseline_bytes(original)),
            "npm security transition changed historical baseline")
    require(all(isinstance(record[k], str) and SHA.fullmatch(record[k])
                for k in ("source_before", "source_after"))
            and record["source_before"] != record["source_after"],
            "invalid npm security source")
    require(all(isinstance(record[k], str) and re.fullmatch(r"[0-9a-f]{64}", record[k])
                and record[k] != "0" * 64 for k in ("independent_review_sha256",
                    "source_freeze_sha256", "qualification_receipt_sha256")),
            "missing npm security evidence")
    require(isinstance(record["changes"], dict)
            and set(record["changes"]) == SECURITY_INPUT_PATHS,
            "invalid npm security paths")
    for change in record["changes"].values():
        require(isinstance(change, dict) and set(change) == {
            "before_blob", "after_blob", "mode", "source"}
            and change["mode"] == "100644"
            and all(isinstance(change[k], str) and SHA.fullmatch(change[k])
                    for k in ("before_blob", "after_blob", "source"))
            and change["before_blob"] != change["after_blob"]
            and change["source"] == record["source_after"],
            "invalid npm security blob identity")
    return original, record


COLLECTION_SHUFFLE_KEY = "reviewed_collection_shuffle_transition"
COLLECTION_SHUFFLE_INPUT = "conftest.py"
# Exact independently reviewed record and actual same-source collection receipt.
COLLECTION_SHUFFLE_TRANSITION_SHA256 = "2140ecb94164f962036d2cd6353285042d5d955ffecc0817c753fed0fe2fa139"


def reviewed_collection_shuffle_transition(baseline):
    """Peel exactly the reviewed optional root collection hook, preserving history."""
    baseline, _ = reviewed_npm_security_transition(baseline)
    if COLLECTION_SHUFFLE_KEY not in baseline:
        return baseline, None
    original = dict(baseline)
    record = original.pop(COLLECTION_SHUFFLE_KEY)
    require(isinstance(record, dict) and set(record) == {
        "schema", "prior_baseline_sha256", "source_before", "source_after",
        "independent_review_sha256", "source_freeze_sha256",
        "qualification_receipt_sha256", "changes",
    } and type(record["schema"]) is int and record["schema"] == 1,
            "invalid collection shuffle transition")
    require(sha(encoded(record)) == COLLECTION_SHUFFLE_TRANSITION_SHA256,
            "unreviewed collection shuffle transition identity")
    require(record["prior_baseline_sha256"] == sha(baseline_bytes(original)),
            "collection shuffle transition changed historical baseline")
    require(all(isinstance(record[k], str) and SHA.fullmatch(record[k])
                for k in ("source_before", "source_after"))
            and record["source_before"] != record["source_after"],
            "collection shuffle source identity missing")
    require(all(isinstance(record[k], str) and re.fullmatch(r"[0-9a-f]{64}", record[k])
                and record[k] != "0" * 64 for k in (
                    "independent_review_sha256", "source_freeze_sha256",
                    "qualification_receipt_sha256")),
            "collection shuffle review or qualification missing")
    changes = record["changes"]
    require(isinstance(changes, dict) and set(changes) == {COLLECTION_SHUFFLE_INPUT},
            "unreviewed collection shuffle paths")
    change = changes[COLLECTION_SHUFFLE_INPUT]
    require(isinstance(change, dict)
            and set(change) == {"before_blob", "after_blob", "mode", "source"}
            and change["before_blob"] is None and change["mode"] == "100644"
            and all(isinstance(change[k], str) and SHA.fullmatch(change[k])
                    for k in ("after_blob", "source"))
            and COLLECTION_SHUFFLE_INPUT not in original.get("common_inputs", {})
            and COLLECTION_SHUFFLE_INPUT not in original.get(
                "reviewed_shared_input_transition", {}).get("common_input_modes", {}),
            "invalid collection shuffle blob, mode or source")
    return original, record


OPS_PACKAGING_KEY = "reviewed_ops_packaging_transition"
OPS_PACKAGING_INPUT = "pyproject.toml"
OPS_PACKAGING_ADDED_INPUT = "tests/_runtime_module_patch.py"
OPS_PACKAGING_INPUTS = frozenset({
    OPS_PACKAGING_INPUT, OPS_PACKAGING_ADDED_INPUT,
    "tests/_bot_real_modules.py", "tests/_yueboard_internal_source.py",
})


def reviewed_ops_packaging_transition(baseline):
    """Peel the reviewed four-input yueops successor sealed on top of every other seal.

    Exactly these shared inputs move, each from its exact reviewed predecessor:
    the root pyproject (from the Tornado seal's after-blob), two existing test
    helpers (from their historical common-input blobs) and one new test helper.
    Each change names the signed source commit that introduced it; nothing else
    is admitted.
    """
    baseline, _ = reviewed_collection_shuffle_transition(baseline)
    if OPS_PACKAGING_KEY not in baseline:
        return baseline, None
    original = dict(baseline)
    record = original.pop(OPS_PACKAGING_KEY)
    require(isinstance(record, dict) and set(record) == {
        "schema", "prior_baseline_sha256", "source_before", "source_after",
        "independent_review_sha256", "source_freeze_sha256",
        "qualification_receipt_sha256", "changes",
    } and type(record["schema"]) is int and record["schema"] == 1,
            "invalid ops packaging transition")
    require(sha(encoded(record)) == OPS_PACKAGING_TRANSITION_SHA256,
            "unreviewed ops packaging transition identity")
    prior = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
    require(record["prior_baseline_sha256"] == sha(prior),
            "ops packaging transition changed historical baseline")
    _, tornado = reviewed_tornado66_dependency_transition(original)
    require(isinstance(tornado, dict)
            and all(isinstance(record[k], str) and SHA.fullmatch(record[k])
                    for k in ("source_before", "source_after"))
            and record["source_before"] == tornado.get("source_after")
            and record["source_before"] != record["source_after"],
            "ops packaging transition source identity missing")
    require(all(isinstance(record[k], str)
                and re.fullmatch(r"[0-9a-f]{64}", record[k])
                and record[k] != "0" * 64 for k in (
                    "independent_review_sha256", "source_freeze_sha256",
                    "qualification_receipt_sha256")),
            "ops packaging transition review or qualification missing")
    changes = record["changes"]
    require(isinstance(changes, dict) and set(changes) == OPS_PACKAGING_INPUTS,
            "unreviewed ops packaging paths")
    common = original.get("common_inputs")
    modes = original.get("reviewed_shared_input_transition", {}).get("common_input_modes", {})
    tornado_change = tornado.get("changes", {}).get(OPS_PACKAGING_INPUT)
    require(isinstance(common, dict) and isinstance(modes, dict)
            and isinstance(tornado_change, dict), "ops packaging predecessor missing")
    sources = set()
    for path, change in changes.items():
        require(isinstance(change, dict)
                and set(change) == {"before_blob", "after_blob", "mode", "source"}
                and isinstance(change["after_blob"], str) and SHA.fullmatch(change["after_blob"])
                and isinstance(change["source"], str) and SHA.fullmatch(change["source"])
                and change["source"] != record["source_before"]
                and change["before_blob"] != change["after_blob"]
                and change["mode"] == "100644",
                "invalid ops packaging blob, mode or source: " + path)
        if path == OPS_PACKAGING_ADDED_INPUT:
            expected = None
        elif path == OPS_PACKAGING_INPUT:
            expected = tornado_change.get("after_blob")
            require(tornado_change.get("mode") == change["mode"],
                    "invalid ops packaging blob, mode or source: " + path)
        else:
            expected = common.get(path)
            require(modes.get(path) == change["mode"],
                    "invalid ops packaging blob, mode or source: " + path)
        require(change["before_blob"] == expected
                and (expected is None) == (path not in common),
                "ops packaging predecessor differs: " + path)
        sources.add(change["source"])
    require(record["source_after"] == changes[OPS_PACKAGING_INPUT]["source"]
            and record["source_after"] in sources,
            "ops packaging transition source identity missing")
    return original, record


def reviewed_i10_skip_blob_successor_transition(baseline):
    """Peel reviewed I10 blob successors of already-admitted skips, sealed outermost.

    Same contract as the first skip blob successor seal, reviewed separately: only
    cases whose admitted skip (after every inner seal) names the exact before blob
    may move to the reviewed after blob; outcome and reason stay historical and no
    case is added.
    """
    baseline, _ = reviewed_ops_packaging_transition(baseline)
    key = "reviewed_i10_skip_blob_successor_transition"
    if key not in baseline:
        return baseline, None
    original = dict(baseline)
    record = original.pop(key)
    require(isinstance(record, dict) and set(record) == {
        "schema", "prior_baseline_sha256", "source_before", "source_after",
        "independent_review_sha256", "updates",
    } and type(record["schema"]) is int and record["schema"] == 1,
            "invalid I10 skip blob successor transition")
    require(sha(encoded(record)) == I10_SKIP_BLOB_SUCCESSOR_TRANSITION_SHA256,
            "unreviewed I10 skip blob successor transition identity")
    prior = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
    require(record["prior_baseline_sha256"] == sha(prior),
            "I10 skip blob successor transition changed historical baseline")
    require(all(isinstance(record[k], str) and SHA.fullmatch(record[k])
                for k in ("source_before", "source_after"))
            and record["source_before"] != record["source_after"],
            "I10 skip blob successor transition source identity missing")
    require(isinstance(record["independent_review_sha256"], str)
            and re.fullmatch(r"[0-9a-f]{64}", record["independent_review_sha256"])
            and record["independent_review_sha256"] != "0" * 64,
            "I10 skip blob successor transition review missing")
    updates = record["updates"]
    require(isinstance(updates, dict) and updates,
            "unreviewed I10 skip blob successor cases")
    module_blob = {}
    for nodeid, change in updates.items():
        module = nodeid.split("::", 1)[0] if isinstance(nodeid, str) else None
        require(isinstance(nodeid, str) and "::" in nodeid and safe_module(module)
                and isinstance(change, dict) and set(change) == {"before_blob", "after_blob"}
                and all(isinstance(change[k], str) and SHA.fullmatch(change[k])
                        for k in ("before_blob", "after_blob"))
                and change["before_blob"] != change["after_blob"],
                "unreviewed I10 skip blob successor: " + str(nodeid))
        pair = (change["before_blob"], change["after_blob"])
        require(module_blob.setdefault(module, pair) == pair,
                "I10 skip blob successor module diverges: " + module)
    return original, record


def reviewed_retired_host_transition(baseline):
    """Undo only D, then let F and every historical seal validate unchanged."""
    baseline, _ = reviewed_i10_skip_blob_successor_transition(baseline)
    if RETIRED_HOST_KEY not in baseline:
        return baseline, None
    original = copy.deepcopy(baseline)
    record = original.pop(RETIRED_HOST_KEY)
    require(isinstance(record, dict)
            and sha(encoded(record)) == RETIRED_HOST_TRANSITION_SHA256,
            "unreviewed retired host transition identity")
    require(record["prior_baseline_sha256"] == RETIRED_HOST_PRIOR_SHA256
            and set(record["removed"]) == RETIRED_HOST_IDS,
            "invalid retired host predecessor or IDs")
    cases = original["cases"]
    updates = original["reviewed_current_skip_transition"]["updates"]
    survivors = record["surviving_ids"]
    for rows in (cases, updates):
        require({n for n in rows if n.startswith(RETIRED_HOST_MODULE + "::")}
                == set(survivors), "retired host removal set differs")
    for nodeid in survivors:
        require(cases[nodeid]["module_blob"] == RETIRED_HOST_AFTER_BLOB
                and updates[nodeid]["after_blob"] == RETIRED_HOST_AFTER_BLOB,
                "retired host successor blob differs")
        cases[nodeid]["module_blob"] = record["historical_blob"]
        updates[nodeid]["after_blob"] = RETIRED_HOST_BEFORE_BLOB
    # Restore insertion order too: historical seals bind the complete JSON bytes.
    for rows, field in ((cases, "case"), (updates, "update")):
        items = list(rows.items())
        for nodeid, removed in sorted(record["removed"].items(),
                                      key=lambda item: item[1][field + "_index"]):
            items.insert(removed[field + "_index"], (nodeid, removed[field]))
        rows.clear()
        rows.update(items)
    require(sha(baseline_bytes(original)) == RETIRED_HOST_PRIOR_SHA256,
            "retired host transition changed historical baseline")
    return original, record


def generate_retired_host_baseline(predecessor, source, revision):
    """One reviewed migration from F; output is deterministic, not execution proof."""
    require(sha(predecessor.read_bytes()) == RETIRED_HOST_PRIOR_SHA256,
            "retired host generator requires the exact F predecessor")
    files = tree_inputs(source, revision)
    require(files.get(RETIRED_HOST_MODULE) == ("100644", RETIRED_HOST_AFTER_BLOB),
            "retired host source blob or mode differs")
    baseline = read_json(predecessor)
    reviewed_estate_input_transition(baseline)
    cases = baseline["cases"]
    updates = baseline["reviewed_current_skip_transition"]["updates"]
    module_ids = [n for n in cases if n.startswith(RETIRED_HOST_MODULE + "::")]
    require(len(module_ids) == 15 and RETIRED_HOST_IDS <= set(module_ids)
            and all(updates[n]["after_blob"] == RETIRED_HOST_BEFORE_BLOB
                    and cases[n]["module_blob"] == updates[n]["before_blob"]
                    for n in module_ids), "retired host predecessor cases differ")
    record = {
        "schema": 1,
        "prior_baseline_sha256": RETIRED_HOST_PRIOR_SHA256,
        "host": "mini.xn--jdu596h.com",
        "retired_by": "Jim",
        "retired_at": "2026-10-30 01:26 SGT",
        "reason": "Owner retired this Mini host; sibling Mini and app hosts remain required.",
        "baseline_migration_approved_at": "2026-10-30 01:50 SGT",
        "module": RETIRED_HOST_MODULE,
        "before_blob": RETIRED_HOST_BEFORE_BLOB,
        "after_blob": RETIRED_HOST_AFTER_BLOB,
        "historical_blob": cases[module_ids[0]]["module_blob"],
        "removed": {
            n: {"case_index": list(cases).index(n), "case": cases[n],
                "update_index": list(updates).index(n), "update": updates[n]}
            for n in sorted(RETIRED_HOST_IDS)
        },
        "surviving_ids": sorted(set(module_ids) - RETIRED_HOST_IDS),
    }
    for nodeid in RETIRED_HOST_IDS:
        del cases[nodeid]
        del updates[nodeid]
    for nodeid in record["surviving_ids"]:
        cases[nodeid]["module_blob"] = RETIRED_HOST_AFTER_BLOB
        updates[nodeid]["after_blob"] = RETIRED_HOST_AFTER_BLOB
    baseline[RETIRED_HOST_KEY] = record
    reviewed_estate_input_transition(baseline)
    return baseline


def required_native_inputs(baseline):
    """Separate new required execution inputs from immutable historical skips."""
    baseline, successor = reviewed_native_input_successor(baseline)
    baseline, _ = reviewed_retired_host_transition(baseline)
    original = dict(baseline)
    record = original.pop("required_native_inputs", None)
    if record is None:
        return original, {}
    require(isinstance(record, dict) and set(record) == {"prior_baseline_sha256", "inputs"}
            and record["inputs"] == HISTORICAL_NATIVE_INPUTS, "invalid required native inputs")
    prior = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
    require(record["prior_baseline_sha256"] == sha(prior),
            "required native inputs changed historical baseline")
    return original, dict(NATIVE_INPUTS) if successor else record["inputs"]


def reviewed_tornado66_dependency_transition(baseline):
    """Peel only the reviewed Tornado security successor above the historical seals."""
    baseline, _ = required_native_inputs(baseline)
    key = "reviewed_tornado66_dependency_transition"
    if key not in baseline:
        return baseline, None
    original = dict(baseline)
    record = original.pop(key)
    require(isinstance(record, dict) and set(record) == {
        "schema", "prior_baseline_sha256", "source_before", "source_after",
        "independent_review_sha256", "source_freeze_sha256",
        "qualification_receipt_sha256", "changes",
    } and type(record["schema"]) is int and record["schema"] == 1,
            "invalid Tornado dependency transition")
    require(sha(encoded(record)) == TORNADO66_DEPENDENCY_TRANSITION_SHA256,
            "unreviewed Tornado dependency transition identity")
    prior = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
    require(record["prior_baseline_sha256"] == sha(prior),
            "Tornado dependency transition changed historical baseline")
    require(all(isinstance(record[k], str) and SHA.fullmatch(record[k])
                for k in ("source_before", "source_after"))
            and record["source_before"] != record["source_after"],
            "Tornado dependency transition source identity missing")
    require(all(isinstance(record[k], str)
                and re.fullmatch(r"[0-9a-f]{64}", record[k])
                and record[k] != "0" * 64 for k in (
                    "independent_review_sha256", "source_freeze_sha256",
                    "qualification_receipt_sha256")),
            "Tornado dependency transition review or qualification missing")
    changes = record["changes"]
    predecessor = original.get("reviewed_runtime_dependency_transition")
    require(isinstance(changes, dict) and set(changes) == set(RUNTIME_DEPENDENCY_INPUTS),
            "unreviewed Tornado dependency paths")
    if not isinstance(predecessor, dict):
        raise ValueError("unreviewed Tornado dependency paths")
    for path, change in changes.items():
        prior_change = predecessor.get("changes", {}).get(path)
        require(isinstance(change, dict) and set(change) == {"before_blob", "after_blob", "mode"}
                and all(isinstance(change[k], str) and SHA.fullmatch(change[k])
                        for k in ("before_blob", "after_blob"))
                and change["before_blob"] != change["after_blob"]
                and change["mode"] == "100644"
                and isinstance(prior_change, dict)
                and change["before_blob"] == prior_change.get("after_blob")
                and change["mode"] == prior_change.get("mode"),
                "invalid Tornado dependency blob or mode")
    return original, record


def reviewed_release_skip_blob_successor_transition(baseline):
    """Peel reviewed release-time blob successors of already-admitted skips, sealed outermost.

    Same contract as the first skip blob successor seal, reviewed separately: only
    cases whose admitted skip (after every inner seal) names the exact before blob
    may move to the reviewed after blob; outcome and reason stay historical and no
    case is added.
    """
    key = "reviewed_release_skip_blob_successor_transition"
    baseline, _ = reviewed_tornado66_dependency_transition(baseline)
    if key not in baseline:
        return baseline, None
    original = dict(baseline)
    record = original.pop(key)
    require(isinstance(record, dict) and set(record) == {
        "schema", "prior_baseline_sha256", "source_before", "source_after",
        "independent_review_sha256", "updates",
    } and type(record["schema"]) is int and record["schema"] == 1,
            "invalid release skip blob successor transition")
    require(sha(encoded(record)) == RELEASE_SKIP_BLOB_SUCCESSOR_TRANSITION_SHA256,
            "unreviewed release skip blob successor transition identity")
    prior = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
    require(record["prior_baseline_sha256"] == sha(prior),
            "release skip blob successor transition changed historical baseline")
    require(all(isinstance(record[k], str) and SHA.fullmatch(record[k])
                for k in ("source_before", "source_after"))
            and record["source_before"] != record["source_after"],
            "release skip blob successor transition source identity missing")
    require(isinstance(record["independent_review_sha256"], str)
            and re.fullmatch(r"[0-9a-f]{64}", record["independent_review_sha256"])
            and record["independent_review_sha256"] != "0" * 64,
            "release skip blob successor transition review missing")
    updates = record["updates"]
    require(isinstance(updates, dict) and updates,
            "unreviewed release skip blob successor cases")
    module_blob = {}
    for nodeid, change in updates.items():
        module = nodeid.split("::", 1)[0] if isinstance(nodeid, str) else None
        require(isinstance(nodeid, str) and "::" in nodeid and safe_module(module)
                and isinstance(change, dict) and set(change) == {"before_blob", "after_blob"}
                and all(isinstance(change[k], str) and SHA.fullmatch(change[k])
                        for k in ("before_blob", "after_blob"))
                and change["before_blob"] != change["after_blob"],
                "unreviewed release skip blob successor: " + str(nodeid))
        pair = (change["before_blob"], change["after_blob"])
        require(module_blob.setdefault(module, pair) == pair,
                "release skip blob successor module diverges: " + module)
    return original, record


def reviewed_hang_guard_input_transition(baseline):
    """Peel the reviewed shared hang-guard helper addition, sealed outermost.

    Exactly one new shared test input (tests/_subprocess.py) may appear, with one
    exact reviewed blob and mode 100644. Peeling restores the historical baseline
    byte-for-byte; nothing historical is relabeled and no other path is admitted.
    """
    key = "reviewed_hang_guard_input_transition"
    baseline, _ = reviewed_release_skip_blob_successor_transition(baseline)
    if key not in baseline:
        return baseline, None
    original = dict(baseline)
    record = original.pop(key)
    require(isinstance(record, dict) and set(record) == {
        "schema", "prior_baseline_sha256", "source_before", "source_after",
        "independent_review_sha256", "source_freeze_sha256", "changes",
    } and type(record["schema"]) is int and record["schema"] == 1,
            "invalid hang guard input transition")
    require(sha(encoded(record)) == HANG_GUARD_INPUT_TRANSITION_SHA256,
            "unreviewed hang guard input transition identity")
    prior = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
    require(record["prior_baseline_sha256"] == sha(prior),
            "hang guard input transition changed historical baseline")
    require(all(isinstance(record[k], str) and SHA.fullmatch(record[k])
                for k in ("source_before", "source_after"))
            and record["source_before"] != record["source_after"],
            "hang guard input transition source identity missing")
    require(all(isinstance(record[k], str) and re.fullmatch(r"[0-9a-f]{64}", record[k])
                and record[k] != "0" * 64
                for k in ("independent_review_sha256", "source_freeze_sha256")),
            "hang guard input transition review missing")
    changes = record["changes"]
    require(isinstance(changes, dict) and set(changes) == {HANG_GUARD_INPUT},
            "unreviewed hang guard input paths")
    change = changes[HANG_GUARD_INPUT]
    require(isinstance(change, dict) and set(change) == {"before_blob", "after_blob", "mode"}
            and change["before_blob"] is None and change["mode"] == "100644"
            and isinstance(change["after_blob"], str) and SHA.fullmatch(change["after_blob"]),
            "invalid hang guard input blob or mode")
    return original, record


def reviewed_skip_blob_successor_transition(baseline):
    """Peel reviewed test-module blob successors of already-admitted skips, sealed outermost.

    Only cases that already carry an admitted skip may move. Each update names the
    exact module blob of the admitted record and the reviewed successor blob; the
    historical outcome and reason stay on the admitted record. No case is added.
    """
    key = "reviewed_skip_blob_successor_transition"
    baseline, _ = reviewed_hang_guard_input_transition(baseline)
    if key not in baseline:
        return baseline, None
    original = dict(baseline)
    record = original.pop(key)
    require(isinstance(record, dict) and set(record) == {
        "schema", "prior_baseline_sha256", "source_before", "source_after",
        "independent_review_sha256", "updates",
    } and type(record["schema"]) is int and record["schema"] == 1,
            "invalid skip blob successor transition")
    require(sha(encoded(record)) == SKIP_BLOB_SUCCESSOR_TRANSITION_SHA256,
            "unreviewed skip blob successor transition identity")
    prior = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
    require(record["prior_baseline_sha256"] == sha(prior),
            "skip blob successor transition changed historical baseline")
    require(all(isinstance(record[k], str) and SHA.fullmatch(record[k])
                for k in ("source_before", "source_after"))
            and record["source_before"] != record["source_after"],
            "skip blob successor transition source identity missing")
    require(isinstance(record["independent_review_sha256"], str)
            and re.fullmatch(r"[0-9a-f]{64}", record["independent_review_sha256"])
            and record["independent_review_sha256"] != "0" * 64,
            "skip blob successor transition review missing")
    updates = record["updates"]
    require(isinstance(updates, dict) and updates, "unreviewed skip blob successor cases")
    module_blob = {}
    for nodeid, change in updates.items():
        module = nodeid.split("::", 1)[0] if isinstance(nodeid, str) else None
        require(isinstance(nodeid, str) and "::" in nodeid and safe_module(module)
                and isinstance(change, dict) and set(change) == {"before_blob", "after_blob"}
                and all(isinstance(change[k], str) and SHA.fullmatch(change[k])
                        for k in ("before_blob", "after_blob"))
                and change["before_blob"] != change["after_blob"],
                "unreviewed skip blob successor: " + str(nodeid))
        pair = (change["before_blob"], change["after_blob"])
        require(module_blob.setdefault(module, pair) == pair,
                "skip blob successor module diverges: " + module)
    return original, record


def skip_blob_successors(record, admitted, reviewed_cases):
    """Map each reviewed blob update onto the admitted skip it succeeds."""
    if record is None:
        return {}
    successors = {}
    for nodeid, change in record["updates"].items():
        historical = admitted.get(nodeid)
        require(nodeid not in reviewed_cases
                and isinstance(historical, dict) and historical.get("outcome") == "skipped"
                and isinstance(historical.get("reason"), str) and historical["reason"]
                and historical.get("module_blob") == change["before_blob"],
                "skip blob successor does not succeed an admitted skip: " + nodeid)
        successors[nodeid] = {"outcome": "skipped", "reason": historical["reason"],
                              "module_blob": change["after_blob"]}
    return successors


def reviewed_runtime_dependency_transition(baseline):
    """Peel the reviewed runtime dependency successor sealed on top of every other seal.

    Exactly the three runtime dependency inputs may move, together, from the
    after-blobs of the seals that last reviewed them to this review's after-blobs.
    """
    key = "reviewed_runtime_dependency_transition"
    baseline, _ = reviewed_skip_blob_successor_transition(baseline)
    if key not in baseline:
        return baseline, None
    original = dict(baseline)
    record = original.pop(key)
    require(isinstance(record, dict) and set(record) == {
        "schema", "prior_baseline_sha256", "source_before", "source_after",
        "independent_review_sha256", "source_freeze_sha256",
        "qualification_receipt_sha256", "changes",
    } and type(record["schema"]) is int and record["schema"] == 1,
            "invalid runtime dependency transition")
    prior = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
    require(record["prior_baseline_sha256"] == sha(prior),
            "runtime dependency transition changed historical baseline")
    lock = original.get("reviewed_audit_lock_transition")
    require(isinstance(lock, dict)
            and all(isinstance(record[k], str) and SHA.fullmatch(record[k])
                    for k in ("source_before", "source_after"))
            and record["source_before"] != record["source_after"]
            and record["source_after"] != lock.get("source_after"),
            "runtime dependency transition source identity missing")
    require(all(isinstance(record[k], str)
                and re.fullmatch(r"[0-9a-f]{64}", record[k])
                and record[k] != "0" * 64 for k in (
                    "independent_review_sha256", "source_freeze_sha256",
                    "qualification_receipt_sha256")),
            "runtime dependency transition review or qualification missing")
    changes = record["changes"]
    require(isinstance(changes, dict) and set(changes) == set(RUNTIME_DEPENDENCY_INPUTS),
            "unreviewed runtime dependency paths")
    for path, predecessor_key in RUNTIME_DEPENDENCY_INPUTS.items():
        change = changes[path]
        predecessor = original.get(predecessor_key)
        prior_change = (predecessor.get("changes", {}).get(path)
                        if isinstance(predecessor, dict) else None)
        require(isinstance(change, dict) and set(change) == {"before_blob", "after_blob", "mode"}
                and all(isinstance(change[k], str) and SHA.fullmatch(change[k])
                        for k in ("before_blob", "after_blob"))
                and change["before_blob"] != change["after_blob"]
                and change["mode"] == "100644"
                and isinstance(prior_change, dict)
                and change["before_blob"] == prior_change.get("after_blob")
                and change["mode"] == prior_change.get("mode"),
                "invalid runtime dependency blob or mode")
    return original, record


def reviewed_audit_lock_transition(baseline):
    """Peel the reviewed audit-group lock successor sealed on top of every other seal.

    Exactly one shared input (uv.lock) may move from the audit dependency seal's
    reviewed after-blob to this review's after-blob; nothing else is admitted.
    """
    key = "reviewed_audit_lock_transition"
    baseline, _ = reviewed_runtime_dependency_transition(baseline)
    if key not in baseline:
        return baseline, None
    original = dict(baseline)
    record = original.pop(key)
    require(isinstance(record, dict) and set(record) == {
        "schema", "prior_baseline_sha256", "source_before", "source_after",
        "independent_review_sha256", "source_freeze_sha256",
        "qualification_receipt_sha256", "changes",
    } and type(record["schema"]) is int and record["schema"] == 1,
            "invalid audit lock transition")
    prior = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
    require(record["prior_baseline_sha256"] == sha(prior),
            "audit lock transition changed historical baseline")
    bot = original.get("reviewed_bot_packaging_transition")
    audit = original.get("reviewed_audit_dependency_transition")
    require(isinstance(bot, dict) and isinstance(audit, dict)
            and all(isinstance(record[k], str) and SHA.fullmatch(record[k])
                    for k in ("source_before", "source_after"))
            and record["source_before"] != record["source_after"]
            and record["source_after"] != bot.get("source_after"),
            "audit lock transition source identity missing")
    require(all(isinstance(record[k], str)
                and re.fullmatch(r"[0-9a-f]{64}", record[k])
                and record[k] != "0" * 64 for k in (
                    "independent_review_sha256", "source_freeze_sha256",
                    "qualification_receipt_sha256")),
            "audit lock transition review or qualification missing")
    changes = record["changes"]
    require(isinstance(changes, dict) and set(changes) == {AUDIT_LOCK_INPUT},
            "unreviewed audit lock paths")
    change = changes[AUDIT_LOCK_INPUT]
    audit_change = audit.get("changes", {}).get(AUDIT_LOCK_INPUT)
    require(isinstance(change, dict) and set(change) == {"before_blob", "after_blob", "mode"}
            and all(isinstance(change[k], str) and SHA.fullmatch(change[k])
                    for k in ("before_blob", "after_blob"))
            and change["before_blob"] != change["after_blob"]
            and change["mode"] == "100644"
            and isinstance(audit_change, dict)
            and change["before_blob"] == audit_change.get("after_blob")
            and change["mode"] == audit_change.get("mode"),
            "invalid audit lock blob or mode")
    return original, record


def reviewed_bot_packaging_transition(baseline):
    """Peel the reviewed bot packaging successor sealed on top of every other seal.

    Exactly one estate input (the bot pyproject) may move from the estate seal's
    reviewed after-blob to this review's after-blob; nothing else is admitted.
    """
    key = "reviewed_bot_packaging_transition"
    baseline, _ = reviewed_audit_lock_transition(baseline)
    if key not in baseline:
        return baseline, None
    original = dict(baseline)
    record = original.pop(key)
    require(isinstance(record, dict) and set(record) == {
        "schema", "prior_baseline_sha256", "source_before", "source_after",
        "independent_review_sha256", "source_freeze_sha256",
        "qualification_receipt_sha256", "changes",
    } and type(record["schema"]) is int and record["schema"] == 1,
            "invalid bot packaging transition")
    prior = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
    require(record["prior_baseline_sha256"] == sha(prior),
            "bot packaging transition changed historical baseline")
    estate = original.get("reviewed_estate_input_transition")
    require(isinstance(estate, dict)
            and all(isinstance(record[k], str) and SHA.fullmatch(record[k])
                    for k in ("source_before", "source_after"))
            and record["source_before"] == estate.get("source_after")
            and record["source_before"] != record["source_after"],
            "bot packaging transition source identity missing")
    require(all(isinstance(record[k], str)
                and re.fullmatch(r"[0-9a-f]{64}", record[k])
                and record[k] != "0" * 64 for k in (
                    "independent_review_sha256", "source_freeze_sha256",
                    "qualification_receipt_sha256")),
            "bot packaging transition review or qualification missing")
    changes = record["changes"]
    require(isinstance(changes, dict) and set(changes) == {BOT_PACKAGING_INPUT},
            "unreviewed bot packaging paths")
    change = changes[BOT_PACKAGING_INPUT]
    estate_change = estate.get("changes", {}).get(BOT_PACKAGING_INPUT)
    require(isinstance(change, dict) and set(change) == {"before_blob", "after_blob", "mode"}
            and all(isinstance(change[k], str) and SHA.fullmatch(change[k])
                    for k in ("before_blob", "after_blob"))
            and change["before_blob"] != change["after_blob"]
            and change["mode"] == "100644"
            and isinstance(estate_change, dict)
            and change["before_blob"] == estate_change.get("after_blob")
            and change["mode"] == estate_change.get("mode"),
            "invalid bot packaging blob or mode")
    return original, record


def reviewed_case_file_transition(baseline, files=None):
    """Admit reviewed file versions of existing environmental skips.

    The historical reason and outcome stay on the predecessor record. A later
    test-module blob is accepted only when this exact review names that blob.
    New cases are limited to the pinned additions and never replace a case
    that already has an admitted skip.
    """
    baseline, _ = reviewed_bot_packaging_transition(baseline)
    original = dict(baseline)
    key = "reviewed_case_file_transition"
    record = original.pop(key, None)
    if key not in baseline:
        return original, {}
    require(isinstance(record, dict) and set(record) == {
        "schema", "prior_baseline_sha256", "source_revision",
        "independent_review_sha256", "additions", "updates",
    } and type(record["schema"]) is int and record["schema"] == 1,
            "invalid reviewed case file transition")
    require(sha(encoded(record)) == CASE_FILE_TRANSITION_SHA256,
            "unreviewed case file transition identity")
    restored = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
    require(record["prior_baseline_sha256"] == sha(restored),
            "case file transition historical baseline changed")
    require(isinstance(record["source_revision"], str)
            and SHA.fullmatch(record["source_revision"])
            and isinstance(record["independent_review_sha256"], str)
            and re.fullmatch(r"[0-9a-f]{64}", record["independent_review_sha256"])
            and record["independent_review_sha256"] != "0" * 64,
            "missing exact case file review identity")
    peeled, _ = reviewed_estate_input_transition(original)
    peeled, preservation = reviewed_relay_preservation_module_transition(peeled)
    peeled, meter = reviewed_relay_meter_module_transition(peeled)
    peeled, metrics = reviewed_relay_metrics_module_transition(peeled)
    peeled, relay = reviewed_relay_skip_module_transition(peeled)
    peeled, extra = reviewed_current_skip_transition(peeled)
    _, ssh = reviewed_skip_module_transition(peeled)
    effective = {nodeid: dict(case) for nodeid, case in original["cases"].items()}
    for mapping in (ssh, extra, relay, metrics, meter, preservation):
        for nodeid, case in mapping.items():
            effective[nodeid] = case
    additions = record["additions"]
    updates = record["updates"]
    require(isinstance(additions, dict) and isinstance(updates, dict)
            and not (set(additions) & set(updates) or set(additions) & set(effective)),
            "case file transition cases overlap history")
    module_blob = {}
    successors = {}
    for nodeid, change in updates.items():
        historical = effective.get(nodeid)
        require(isinstance(nodeid, str) and "::" in nodeid
                and isinstance(historical, dict) and historical.get("outcome") == "skipped"
                and isinstance(historical.get("reason"), str) and historical["reason"]
                and isinstance(change, dict) and set(change) == {"before_blob", "after_blob"}
                and change["before_blob"] == historical.get("module_blob")
                and change["before_blob"] != change["after_blob"]
                and SHA.fullmatch(change["after_blob"]),
                "unreviewed case file blob update: " + str(nodeid))
        module = nodeid.split("::", 1)[0]
        require(safe_module(module), "unreviewed case file module: " + str(nodeid))
        require(module_blob.setdefault(module, change["after_blob"]) == change["after_blob"],
                "case file module blob diverges: " + module)
        if files is not None and files.get(module, (None, None))[1] == change["after_blob"]:
            require(files[module][0] == "100644", "case file module mode changed")
        successors[nodeid] = {
            "outcome": "skipped", "reason": historical["reason"],
            "module_blob": change["after_blob"],
        }
    for nodeid, case in additions.items():
        require(isinstance(nodeid, str) and "::" in nodeid
                and isinstance(case, dict) and set(case) == {"outcome", "reason", "module_blob"}
                and case["outcome"] == "skipped" and isinstance(case["reason"], str)
                and case["reason"] and SHA.fullmatch(case["module_blob"]),
                "unreviewed case file addition: " + str(nodeid))
        module = nodeid.split("::", 1)[0]
        require(safe_module(module), "unreviewed case file module: " + str(nodeid))
        require(module_blob.setdefault(module, case["module_blob"]) == case["module_blob"],
                "case file module blob diverges: " + module)
        if files is not None and files.get(module, (None, None))[1] == case["module_blob"]:
            require(files[module][0] == "100644", "case file module mode changed")
        successors[nodeid] = dict(case)
    return original, successors


def reviewed_site_lock_transition(baseline, files=None):
    """Peel the reviewed static-site lock successor sealed on top of the estate seal."""
    baseline, _ = reviewed_case_file_transition(baseline, files)
    key = "reviewed_site_lock_transition"
    if key not in baseline:
        return baseline, None
    original = dict(baseline)
    record = original.pop(key)
    require(isinstance(record, dict) and set(record) == {
        "schema", "prior_baseline_sha256", "source_before", "source_after",
        "independent_review_sha256", "source_freeze_sha256",
        "qualification_receipt_sha256", "changes",
    } and type(record["schema"]) is int and record["schema"] == 1,
            "invalid site lock transition")
    prior = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
    require(record["prior_baseline_sha256"] == sha(prior),
            "site lock transition changed historical baseline")
    estate = original.get("reviewed_estate_input_transition")
    require(isinstance(estate, dict)
            and all(isinstance(record[k], str) and SHA.fullmatch(record[k])
                    for k in ("source_before", "source_after"))
            and record["source_before"] == estate.get("source_after")
            and record["source_before"] != record["source_after"],
            "site lock transition source identity missing")
    require(all(isinstance(record[k], str)
                and re.fullmatch(r"[0-9a-f]{64}", record[k])
                and record[k] != "0" * 64 for k in (
                    "independent_review_sha256", "source_freeze_sha256",
                    "qualification_receipt_sha256")),
            "site lock transition review or qualification missing")
    changes = record["changes"]
    require(isinstance(changes, dict) and set(changes) == {SITE_LOCK_INPUT},
            "unreviewed site lock paths")
    change = changes[SITE_LOCK_INPUT]
    require(isinstance(change, dict) and set(change) == {"before_blob", "after_blob", "mode"}
            and all(isinstance(change[k], str) and SHA.fullmatch(change[k])
                    for k in ("before_blob", "after_blob"))
            and change["before_blob"] != change["after_blob"]
            and change["mode"] == "100644"
            and change["before_blob"] == original.get("common_inputs", {}).get(SITE_LOCK_INPUT),
            "invalid site lock blob or mode")
    return original, record


def reviewed_estate_input_transition(baseline):
    """Validate the complete seal before exposing its historical predecessor."""
    key = "reviewed_estate_input_transition"
    if key not in baseline:
        return baseline, None
    baseline, _ = reviewed_site_lock_transition(baseline)
    original = dict(baseline)
    record = original.pop(key)
    require(isinstance(record, dict) and set(record) == {
        "schema", "prior_baseline_sha256", "source_before", "source_after",
        "independent_review_sha256", "source_freeze_sha256",
        "qualification_receipt_sha256", "changes",
    } and type(record["schema"]) is int and record["schema"] == 1,
            "invalid estate shared-input transition")
    prior = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
    require(record["prior_baseline_sha256"] == sha(prior),
            "estate transition changed historical baseline")
    require(all(isinstance(record[k], str) and SHA.fullmatch(record[k])
                for k in ("source_before", "source_after"))
            and record["source_before"] == original[
                "reviewed_scanner_input_transition"]["source_after"]
            and record["source_before"] != record["source_after"],
            "estate transition source identity missing")
    require(all(isinstance(record[k], str)
                and re.fullmatch(r"[0-9a-f]{64}", record[k])
                and record[k] != "0" * 64 for k in (
                    "independent_review_sha256", "source_freeze_sha256",
                    "qualification_receipt_sha256")),
            "estate transition review or qualification missing")
    changes = record["changes"]
    require(isinstance(changes, dict) and set(changes) == ESTATE_INPUT_PATHS,
            "unreviewed estate shared-input paths")
    for path, change in changes.items():
        require(isinstance(change, dict) and set(change) == {
            "before_blob", "after_blob", "mode",
        } and isinstance(change["after_blob"], str)
                and SHA.fullmatch(change["after_blob"])
                and change["mode"] == "100644"
                and change["before_blob"] != change["after_blob"]
                and (change["before_blob"] is None if path == ESTATE_ADDED_INPUT
                     else isinstance(change["before_blob"], str)
                     and SHA.fullmatch(change["before_blob"])),
                "invalid estate shared-input blob or mode")
    return original, record


def estate_successor_proof(baseline, source, revision):
    """Prove a later Ops revision descends from the sealed estate successor.

    Only the planner has the full source history. It records the proven
    predecessor inside the sealed admission; validators and the join re-admit
    against that sealed value and still compare every estate input blob.
    """
    native_protocol_helper_proof(source, revision)
    pr_shared_input_successor_proof(source, revision)
    reviewed_pr_input_proof(source, revision)
    _, security = reviewed_npm_security_transition(baseline)
    if security is not None:
        successor = revision == security["source_after"]
        if revision not in (security["source_before"], security["source_after"]):
            try:
                git(source, "merge-base", "--is-ancestor", security["source_after"], revision)
                successor = True
            except subprocess.CalledProcessError as exc:
                require(exc.returncode == 1, "npm security ancestry unavailable")
        files = tree_inputs(source, revision)
        changed = any(files.get(path, (None, None))[1] == item["after_blob"]
                      for path, item in security["changes"].items())
        if successor or changed:
            try:
                git(source, "merge-base", "--is-ancestor", security["source_before"], security["source_after"])
                git(source, "merge-base", "--is-ancestor", security["source_after"], revision)
                parent_revision = git(source, "rev-parse", security["source_after"] + "^1").decode().strip()
                parent = tree_inputs(source, parent_revision)
                introduced = tree_inputs(source, security["source_after"])
                before = tree_inputs(source, security["source_before"])
            except subprocess.CalledProcessError:
                raise ValueError("npm security source ancestry differs") from None
            for path, item in security["changes"].items():
                require(files.get(path) == introduced.get(path) == (item["mode"], item["after_blob"])
                        and parent.get(path) == before.get(path) == (item["mode"], item["before_blob"]),
                        "npm security successor blob or mode differs")
    _, shuffle = reviewed_collection_shuffle_transition(baseline)
    if shuffle is not None:
        change = shuffle["changes"][COLLECTION_SHUFFLE_INPUT]
        try:
            blob = git(source, "rev-parse", f"{revision}:{COLLECTION_SHUFFLE_INPUT}").decode().strip()
        except subprocess.CalledProcessError:
            blob = None
        qualified_successor = revision == shuffle["source_after"]
        if revision not in (shuffle["source_before"], shuffle["source_after"]):
            try:
                git(source, "merge-base", "--is-ancestor", shuffle["source_after"], revision)
                qualified_successor = True
            except subprocess.CalledProcessError as exc:
                require(exc.returncode == 1,
                        "collection shuffle successor ancestry unavailable")
        # Absence is historical only before the qualified source. A descendant
        # cannot delete the hook and silently regain the old baseline admission.
        if qualified_successor or blob is not None:
            try:
                git(source, "merge-base", "--is-ancestor", shuffle["source_before"], change["source"])
                git(source, "merge-base", "--is-ancestor", change["source"], shuffle["source_after"])
                git(source, "merge-base", "--is-ancestor", shuffle["source_after"], revision)
                introduced = git(source, "rev-parse",
                                 f"{change['source']}:{COLLECTION_SHUFFLE_INPUT}").decode().strip()
            except subprocess.CalledProcessError:
                raise ValueError("collection shuffle successor source revision differs") from None
            try:
                parent = git(source, "rev-parse",
                             f"{change['source']}^1:{COLLECTION_SHUFFLE_INPUT}").decode().strip()
            except subprocess.CalledProcessError:
                parent = None
            require(blob == introduced == change["after_blob"] and parent is None,
                    "collection shuffle successor source revision differs")
    _, packaging = reviewed_ops_packaging_transition(baseline)
    _, tornado = reviewed_tornado66_dependency_transition(baseline)
    _, hang = reviewed_hang_guard_input_transition(baseline)
    _, runtime = reviewed_runtime_dependency_transition(baseline)
    _, lock = reviewed_audit_lock_transition(baseline)
    _, bot = reviewed_bot_packaging_transition(baseline)
    _, site = reviewed_site_lock_transition(baseline)
    _, record = reviewed_estate_input_transition(baseline)
    if record is None or revision == record["source_after"]:
        return None
    if hang is not None:
        try:
            blob = git(source, "rev-parse", f"{revision}:{HANG_GUARD_INPUT}").decode().strip()
        except subprocess.CalledProcessError:
            blob = None
        if blob is not None:
            try:
                git(source, "merge-base", "--is-ancestor", hang["source_after"], revision)
            except subprocess.CalledProcessError:
                raise ValueError("hang guard successor source revision differs") from None
    after = record["source_after"]
    try:
        git(source, "merge-base", "--is-ancestor", after, revision)
    except subprocess.CalledProcessError:
        raise ValueError("estate successor source revision differs") from None
    if site is not None:
        try:
            blob = git(source, "rev-parse", f"{revision}:{SITE_LOCK_INPUT}").decode().strip()
        except subprocess.CalledProcessError:
            blob = None
        if blob == site["changes"][SITE_LOCK_INPUT]["after_blob"]:
            try:
                git(source, "merge-base", "--is-ancestor", site["source_after"], revision)
            except subprocess.CalledProcessError:
                raise ValueError("site lock successor source revision differs") from None
    if bot is not None:
        try:
            blob = git(source, "rev-parse", f"{revision}:{BOT_PACKAGING_INPUT}").decode().strip()
        except subprocess.CalledProcessError:
            blob = None
        if blob == bot["changes"][BOT_PACKAGING_INPUT]["after_blob"]:
            try:
                git(source, "merge-base", "--is-ancestor", bot["source_after"], revision)
            except subprocess.CalledProcessError:
                raise ValueError("bot packaging successor source revision differs") from None
    if lock is not None:
        try:
            blob = git(source, "rev-parse", f"{revision}:{AUDIT_LOCK_INPUT}").decode().strip()
        except subprocess.CalledProcessError:
            blob = None
        if blob == lock["changes"][AUDIT_LOCK_INPUT]["after_blob"]:
            try:
                git(source, "merge-base", "--is-ancestor", lock["source_after"], revision)
            except subprocess.CalledProcessError:
                raise ValueError("audit lock successor source revision differs") from None
    if packaging is not None:
        for path, change in sorted(packaging["changes"].items()):
            try:
                blob = git(source, "rev-parse", f"{revision}:{path}").decode().strip()
            except subprocess.CalledProcessError:
                blob = None
            if blob != change["after_blob"]:
                continue
            # The named signed source must descend from the Tornado successor, must
            # itself introduce exactly this blob transition, and must be an
            # ancestor of the revision being planned.
            try:
                git(source, "merge-base", "--is-ancestor",
                    packaging["source_before"], change["source"])
                git(source, "merge-base", "--is-ancestor", change["source"], revision)
                introduced = git(source, "rev-parse",
                                 f"{change['source']}:{path}").decode().strip()
            except subprocess.CalledProcessError:
                raise ValueError("ops packaging successor source revision differs") from None
            try:
                parent = git(source, "rev-parse",
                             f"{change['source']}^1:{path}").decode().strip()
            except subprocess.CalledProcessError:
                parent = None
            require(introduced == change["after_blob"] and parent == change["before_blob"],
                    "ops packaging successor source revision differs")
    if tornado is not None:
        for path, change in tornado["changes"].items():
            try:
                blob = git(source, "rev-parse", f"{revision}:{path}").decode().strip()
            except subprocess.CalledProcessError:
                blob = None
            if blob == change["after_blob"]:
                try:
                    git(source, "merge-base", "--is-ancestor",
                        tornado["source_before"], tornado["source_after"])
                    git(source, "merge-base", "--is-ancestor", tornado["source_after"], revision)
                except subprocess.CalledProcessError:
                    raise ValueError("Tornado dependency successor source revision differs") from None
                break
    if runtime is not None:
        for path, change in runtime["changes"].items():
            try:
                blob = git(source, "rev-parse", f"{revision}:{path}").decode().strip()
            except subprocess.CalledProcessError:
                blob = None
            if blob == change["after_blob"]:
                try:
                    git(source, "merge-base", "--is-ancestor", runtime["source_after"], revision)
                except subprocess.CalledProcessError:
                    raise ValueError(
                        "runtime dependency successor source revision differs") from None
    return after


def first_native_policy():
    """Trusted central policy; it grants no historical execution credit."""
    policy = read_json(ROOT / "ops-first-native-successors.json")
    require(policy.get("schema") == 1 and len(policy.get("cases", {})) == 4
            and len(policy.get("module_blobs", {})) == 3,
            "invalid first native successor policy")
    return policy


def release_pin():
    return first_native_policy()["source_revision"]


def release_pin_is_ancestor(source, revision):
    """True when revision is the release pin or a descendant of it.

    A repository that does not contain the pin commit is not a descendant.
    That keeps fixture repositories on the exact-pin rule. A present pin with
    unreadable history still raises EvidenceUnavailable. Sealed blobs stay exact.
    """
    pin = release_pin()
    if revision == pin:
        return True
    try:
        git(source, "cat-file", "-e", pin + "^{commit}")
    except subprocess.CalledProcessError:
        return False
    try:
        git(source, "merge-base", "--is-ancestor", pin, revision)
    except subprocess.CalledProcessError as exc:
        require(exc.returncode == 1, "release pin ancestry unavailable")
        return False
    return True


def holds_release_pin(source_revision, *, pin_is_ancestor):
    """Exact pin, or a caller-proved descendant. The blob checks stay exact."""
    return source_revision == release_pin() or pin_is_ancestor is True


def admit_first_native_helper(common, files, source_revision, *, pin_is_ancestor=False):
    policy = first_native_policy()
    item = policy["shared_input"]
    path = item["path"]
    if path not in common and not holds_release_pin(
            source_revision, pin_is_ancestor=pin_is_ancestor):
        return common, files
    require(holds_release_pin(source_revision, pin_is_ancestor=pin_is_ancestor)
            and common.get(path) == item["blob"],
            "first native helper requires the signed release pin or its descendant, and the exact blob")
    if files is not None:
        require(files.get(path) == (item["mode"], item["blob"]),
                "first native helper mode or tree changed")
        files = {p: v for p, v in files.items() if p != path}
    return {p: v for p, v in common.items() if p != path}, files


def native_protocol_helper_policy():
    payload = (ROOT / "reviews/ops-native-protocol-helper-20261106/helper-policy.json").read_bytes()
    require(sha(payload) == "1ee4183d8f902df6839936adfc6ec8bfcb995892352cf2fcdf44d51f993383ee", "unreviewed native protocol helper policy")
    return json.loads(payload)


def native_protocol_helper_proof(source, revision):
    policy = native_protocol_helper_policy()
    item = policy["shared_input"]
    files = tree_inputs(source, revision)
    if item["path"] not in files:
        return
    try:
        git(source, "merge-base", "--is-ancestor", policy["source_revision"], revision)
        introduced = tree_inputs(source, policy["source_revision"])
    except subprocess.CalledProcessError:
        raise ValueError("native protocol helper source ancestry differs") from None
    require(files[item["path"]] == introduced.get(item["path"])
            == (item["mode"], item["blob"]), "native protocol helper blob or mode differs")


def admit_native_protocol_helper(common, files, source_revision, *, pin_is_ancestor=False):
    path = "tests/native_protocol_fixture.py"
    if path not in common:
        return common, files
    item = native_protocol_helper_policy()["shared_input"]
    require(holds_release_pin(source_revision, pin_is_ancestor=pin_is_ancestor)
            and common.get(path) == item["blob"],
            "native protocol helper requires the signed release pin or its descendant, and the exact blob")
    if files is not None:
        require(files.get(path) == (item["mode"], item["blob"]),
                "native protocol helper mode or tree changed")
        files = {p: v for p, v in files.items() if p != path}
    return {p: v for p, v in common.items() if p != path}, files


def admit_p015_offline_helper(common, files, source_revision, *, pin_is_ancestor=False):
    if "tests/p015_offline_plugin.py" not in common:
        return common, files
    payload = (ROOT / "reviews/ops-p015-20261105/helper-policy.json").read_bytes()
    require(sha(payload) == "cb32a56317731b0e57429ac7ca333c24bb527a7e3bc778af518e3ebc95c918a5",
            "unreviewed p015 helper policy")
    policy = json.loads(payload)
    item = policy["shared_input"]
    path = item["path"]
    if path not in common:
        return common, files
    # Blob and mode stay exact. A descendant of the pin is enough when they match.
    require(holds_release_pin(source_revision, pin_is_ancestor=pin_is_ancestor)
            and common.get(path) == item["blob"],
            "p015 offline helper requires the signed release pin or its descendant, and the exact blob")
    if files is not None:
        require(files.get(path) == (item["mode"], item["blob"]),
                "p015 offline helper mode or tree changed")
        files = {p: v for p, v in files.items() if p != path}
    return {p: v for p, v in common.items() if p != path}, files


# Outermost first; historical seals remain unchanged.
PR_SHARED_INPUT_SEALS = (
    (256, "894176392f12701905ae38034d84fbb1ed922a9a76266e5ec08f23abd1db3636",
     frozenset({"pyproject.toml", "uv.lock"})),
    (122, "c2d8f9c57343ec12fcbaecda2bd3ef2e4fcf68c0fba3c4b86dd2f4c4bbdd7a46",
     frozenset({"checkin-api/requirements.txt", "pyproject.toml",
                "telegram-bot/yue/requirements.txt", "uv.lock"})),
)


# Activate only for these exact after-blobs; historical policy fixtures need no new evidence.
PR_SHARED_INPUT_AFTER_BLOBS = frozenset({
    ('pyproject.toml', '1d861dc9e1da3fbe876ded02f454a3fd26f2cd27'),
    ('uv.lock', 'a432bb987a9b6f8f7871647680e9078c6a56b6a3'),

    ('checkin-api/requirements.txt', 'a5bd445e3f132c2fd090490ab07bb8ee79de6a2f'),
    ('pyproject.toml', 'ba32ad966dc0d67280ba04c03c1f911c8839780a'),
    ('telegram-bot/yue/requirements.txt', '6d87484afee325a2c00630c6eb1c9ed411b130f1'),
    ('uv.lock', '18d0dc71583fcd55ae726dd6c533e0f2111539f2'),
})


PR_SHARED_INPUT_SOURCE_REVISIONS = (
    "4b64bf9a9b26a24aecdc551bbe7eaa7a840558cd",
    "56a7e0412e9bd1d297ba4a5dd3d363147fac463c",
)


def reviewed_pr_shared_input_transitions():
    """Peel exact outermost successors without modifying any historical seal."""
    original = dict(read_json(ROOT / "ops-shared-input-successors.json"))
    records = []
    for number, identity, paths in PR_SHARED_INPUT_SEALS:
        record = original.pop(f"reviewed_pr{number}_shared_input_transition", None)
        require(isinstance(record, dict) and set(record) == {
            "schema", "reviewer", "prior_baseline_sha256", "prior_successors_sha256",
            "source_before", "source_after", "independent_review_sha256",
            "source_freeze_sha256", "qualification_receipt_sha256", "changes"}
            and type(record["schema"]) is int and record["schema"] == 1,
            "invalid PR shared-input transition")
        require(sha(encoded(record)) == identity, "unreviewed PR shared-input transition")
        require(record["prior_successors_sha256"] == sha(baseline_bytes(original))
                and record["prior_baseline_sha256"] == sha(
                    historical_skip_baseline_bytes()),
                "PR shared-input transition changed historical predecessor")
        require(all(isinstance(record[k], str) and SHA.fullmatch(record[k])
                    for k in ("source_before", "source_after"))
                and record["source_before"] != record["source_after"],
                "invalid PR shared-input source")
        require(all(isinstance(record[k], str) and re.fullmatch(r"[0-9a-f]{64}", record[k])
                    and record[k] != "0" * 64 for k in (
                        "independent_review_sha256", "source_freeze_sha256",
                        "qualification_receipt_sha256")), "missing PR shared-input evidence")
        require(isinstance(record["changes"], dict) and set(record["changes"]) == paths,
                "invalid PR shared-input paths")
        for item in record["changes"].values():
            require(isinstance(item, dict) and set(item) == {
                "before_blob", "after_blob", "mode", "source"}
                and item["mode"] == "100644"
                and all(isinstance(item[k], str) and SHA.fullmatch(item[k])
                        for k in ("before_blob", "after_blob", "source"))
                and item["before_blob"] != item["after_blob"]
                and item["source"] == record["source_after"],
                "invalid PR shared-input blob identity")
        records.append(record)
    for outer, inner in zip(records, records[1:]):
        require(outer["source_before"] == inner["source_after"] and all(
            item["before_blob"] == inner["changes"][path]["after_blob"]
            for path, item in outer["changes"].items()), "PR shared-input merge order differs")
    return records


def admit_pr_shared_inputs(common, files, source_revision, *, pin_is_ancestor=False):
    """Undo reviewed PR bundles before any inner seal sees the shared map."""
    if source_revision not in PR_SHARED_INPUT_SOURCE_REVISIONS and not any(
            common.get(path) == blob for path, blob in PR_SHARED_INPUT_AFTER_BLOBS):
        return common, files
    for record in reviewed_pr_shared_input_transitions():
        changes = record["changes"]
        if source_revision != record["source_after"] and not any(
                common.get(path) == item["after_blob"] for path, item in changes.items()):
            continue
        require(holds_release_pin(source_revision, pin_is_ancestor=pin_is_ancestor),
                "PR shared-input successor requires the signed release pin or its descendant")
        common = dict(common)
        if files is not None:
            files = dict(files)
        for path, item in changes.items():
            require(common.get(path) == item["after_blob"],
                    "PR shared-input successor bundle missing or changed")
            common[path] = item["before_blob"]
            if files is not None:
                require(files.get(path) == (item["mode"], item["after_blob"]),
                        "PR shared-input successor mode or tree differs")
                files[path] = (item["mode"], item["before_blob"])
    return common, files


def pr_shared_input_successor_proof(source, revision):
    """Bind bundles to reviewed source ancestry and exact before/after trees."""
    files = tree_inputs(source, revision)
    # Exact outer Ruff successor must be proved and peeled before PR256/122.
    reviewed_pr_input_proof(source, revision, names=("ruff_retired_video",))
    _, files = admit_reviewed_pr_inputs(
        {p: value[1] for p, value in files.items()}, files, revision,
        names=("ruff_retired_video",),
        pin_is_ancestor=release_pin_is_ancestor(source, revision))
    successors = set()
    for after in PR_SHARED_INPUT_SOURCE_REVISIONS:
        try:
            git(source, "cat-file", "-e", after + "^{commit}")
        except subprocess.CalledProcessError:
            continue  # Historical source repositories may predate these merges.
        try:
            git(source, "merge-base", "--is-ancestor", after, revision)
            successors.add(after)
        except subprocess.CalledProcessError as exc:
            require(exc.returncode == 1, "PR shared-input ancestry unavailable")
    if not successors and not any(files.get(path, (None, None))[1] == blob
                                  for path, blob in PR_SHARED_INPUT_AFTER_BLOBS):
        return
    for record in reviewed_pr_shared_input_transitions():
        changes = record["changes"]
        if record["source_after"] not in successors and not any(
                files.get(path, (None, None))[1] == item["after_blob"]
                for path, item in changes.items()):
            continue
        try:
            git(source, "merge-base", "--is-ancestor", record["source_after"], revision)
            git(source, "merge-base", "--is-ancestor", record["source_before"], revision)
            before = tree_inputs(source, record["source_before"])
            after = tree_inputs(source, record["source_after"])
        except subprocess.CalledProcessError:
            raise ValueError("PR shared-input successor ancestry differs") from None
        files = dict(files)
        for path, item in changes.items():
            require(files.get(path) == after.get(path) == (item["mode"], item["after_blob"])
                    and before.get(path) == (item["mode"], item["before_blob"]),
                    "PR shared-input successor blob or mode differs")
            files[path] = (item["mode"], item["before_blob"])


MINIAPP_MEMBERSHIP_TRANSITION_SHA256 = "ca92f22e6699afa5e9dd48457b79968d8cfb540a43c6e2f7d715158423703638"
MINIAPP_MEMBERSHIP_INPUT = "tests/_miniapp_source.py"


def reviewed_miniapp_membership_transition():
    """Codex-reviewed successor of one shared input, kept outside the sealed skip baseline.

    The record follows the historical transition format (plus a reviewer label);
    storing it separately leaves every sealed prior_baseline_sha256 untouched.
    """
    value = read_json(ROOT / "ops-shared-input-successors.json")
    record = value.get("reviewed_miniapp_membership_transition")
    require(value.get("schema") == 1 and isinstance(record, dict) and set(record) == {
        "schema", "reviewer", "prior_baseline_sha256", "source_before", "source_after",
        "independent_review_sha256", "source_freeze_sha256",
        "qualification_receipt_sha256", "changes",
    } and record["schema"] == 1, "invalid miniapp membership transition")
    require(sha(encoded(record)) == MINIAPP_MEMBERSHIP_TRANSITION_SHA256,
            "unreviewed miniapp membership transition identity")
    require(record["prior_baseline_sha256"] == sha(historical_skip_baseline_bytes()),
            "miniapp membership transition changed historical baseline")
    require(all(re.fullmatch(r"[0-9a-f]{64}", record[k]) and record[k] != "0" * 64
                for k in ("independent_review_sha256", "source_freeze_sha256",
                          "qualification_receipt_sha256")),
            "miniapp membership review or qualification missing")
    changes = record["changes"]
    require(set(changes) == {MINIAPP_MEMBERSHIP_INPUT}, "unreviewed miniapp membership paths")
    change = changes[MINIAPP_MEMBERSHIP_INPUT]
    require(set(change) == {"before_blob", "after_blob", "mode", "source"}
            and SHA.fullmatch(change["before_blob"]) and SHA.fullmatch(change["after_blob"])
            and change["before_blob"] != change["after_blob"] and change["mode"] == "100644"
            and change["source"] == record["source_after"] != record["source_before"],
            "invalid miniapp membership blob, mode or source")
    return record


def admit_miniapp_membership(common, files, source_revision, *, pin_is_ancestor=False):
    """Swap the reviewed after-blob back to its predecessor at the pin or a descendant."""
    if not isinstance(common, dict) or MINIAPP_MEMBERSHIP_INPUT not in common:
        return common, files
    change = reviewed_miniapp_membership_transition()["changes"][MINIAPP_MEMBERSHIP_INPUT]
    if common[MINIAPP_MEMBERSHIP_INPUT] != change["after_blob"]:
        return common, files
    require(holds_release_pin(source_revision, pin_is_ancestor=pin_is_ancestor),
            "miniapp membership successor requires the signed release pin or its descendant")
    common = dict(common) | {MINIAPP_MEMBERSHIP_INPUT: change["before_blob"]}
    if files is not None:
        require(files.get(MINIAPP_MEMBERSHIP_INPUT) == (change["mode"], change["after_blob"]),
                "miniapp membership input mode or tree changed")
        files = dict(files) | {MINIAPP_MEMBERSHIP_INPUT: (change["mode"], change["before_blob"])}
    return common, files


# New shared-input seals are outermost, as with the MiniApp membership seal.
# Keep the historical baseline and every prior_baseline_sha256 byte-identical.
REVIEWED_PR_INPUTS = {
    "ruff_retired_video": ("7c952fe87ad22cce6bcadd7408c727afe31075d5a11650e9a714fa2cb0d6f88e", frozenset({"pyproject.toml"})),
    "deploy_ai_exit": (
        "e2c2ccc85646e12c1172fc83b1da76efa9e8c4e30884ddfc4abe7ce006ec6f81",
        frozenset({"tests/_deploy_source.py"}),
    ),
    "site_devdeps": (
        "b9fc088633186556e350eee3c090748d7dc18655e3aea6bbd83bd5bd92fe9de0",
        frozenset({"site/package.json", "site/pnpm-lock.yaml"}),
    ),
    # yueops #411 (short PG socket dir) + #415 (pytest tmp retention), pin 3beb7b8c.
    "test_inputs_1105": (
        "2113cfed645784355f1cbd250def65e000076f5b71f6a4d9e65772a3003d3510",
        frozenset({"pytest.ini", "tests/_native_postgres.py"}),
    ),
    # yueops 00f1063f0 (t823u): drop site npm script refresh-plans; lockfile unchanged.
    "site_refresh_plans": (
        "9e2912667e20acb474d995fffe67bbfae47a79d3e2842207fa900e49b80f3568",
        frozenset({"site/package.json"}),
    ),
    # yueops a8bdd4684 + 5c4cc83a7 (ship 9): tests/conftest.py empty retired-entry
    # quarantine fixture and direct-gfw domestic probe off in tests.
    "conftest_quarantine_1111": (
        "f0d8ba5b5660dadf4caf8690384a30ca99f540d47b519bd04d1736a1b608ccf5",
        frozenset({"tests/conftest.py"}),
    ),
}

# Later sidecars live in their own file so earlier outer seals' hashes stay exact.
REVIEWED_PR_INPUT_FILES = {"ruff_retired_video": "ops-shared-input-successors-1106.json", "test_inputs_1105": "ops-shared-input-successors-1105.json", "site_refresh_plans": "ops-shared-input-successors-1110.json", "conftest_quarantine_1111": "ops-shared-input-successors-1111.json"}
# Activate these sidecars only for their exact after-blobs (historical trees need no evidence).
REVIEWED_PR_INPUT_ACTIVATION = {"ruff_retired_video": frozenset({
    ("pyproject.toml", "fbedf7789a78aaa402835eb3747e8be2e24772d2"),
}), "test_inputs_1105": frozenset({
    ("pytest.ini", "9599c104c7dcfcfa3718c9be2335362731d4758f"),
    ("tests/_native_postgres.py", "5ac0ed066b88979b123bb0dab037ca497e41e23c"),
}), "site_devdeps": frozenset({
    # Activate only on the reviewed after package.json. The lockfile after-blob
    # is unchanged by later site_refresh_plans, so using it here would keep
    # this bundle live and reject the new package.json successor.
    ("site/package.json", "09ceb094c9286134cce8e770196ce70159a5bec6"),
}), "site_refresh_plans": frozenset({
    ("site/package.json", "2ee14b2010387075336100cd89318730b23c5c06"),
}), "conftest_quarantine_1111": frozenset({
    ("tests/conftest.py", "3776755a872e2919f9ca3360fb9a4c630b5b2ec8"),
})}


def reviewed_pr_input_active(name, blob_of):
    blobs = REVIEWED_PR_INPUT_ACTIVATION.get(name)
    return blobs is None or any(blob_of(path) == blob for path, blob in blobs)


def reviewed_pr_input_transition(name):
    """Validate an exact reviewed sidecar seal without rewriting inner seals."""
    identity, paths = REVIEWED_PR_INPUTS[name]
    value = read_json(ROOT / REVIEWED_PR_INPUT_FILES.get(name, "ops-shared-input-successors.json"))
    record = value.get("reviewed_" + name + "_transition")
    require(value.get("schema") == 1 and isinstance(record, dict) and set(record) == {
        "schema", "reviewer", "prior_baseline_sha256", "source_before", "source_after",
        "independent_review_sha256", "source_freeze_sha256",
        "qualification_receipt_sha256", "changes",
    } and type(record["schema"]) is int and record["schema"] == 1,
            "invalid reviewed PR input transition: " + name)
    require(sha(encoded(record)) == identity,
            "unreviewed PR input transition identity: " + name)
    require(record["prior_baseline_sha256"] == sha(historical_skip_baseline_bytes()),
            "reviewed PR input transition changed historical baseline: " + name)
    require(all(isinstance(record[k], str) and SHA.fullmatch(record[k])
                for k in ("source_before", "source_after"))
            and record["source_before"] != record["source_after"],
            "invalid reviewed PR input source: " + name)
    require(all(isinstance(record[k], str) and re.fullmatch(r"[0-9a-f]{64}", record[k])
                and record[k] != "0" * 64 for k in (
                    "independent_review_sha256", "source_freeze_sha256",
                    "qualification_receipt_sha256")),
            "reviewed PR input evidence missing: " + name)
    changes = record["changes"]
    require(isinstance(changes, dict) and set(changes) == paths,
            "unreviewed PR input paths: " + name)
    for change in changes.values():
        require(isinstance(change, dict) and set(change) == {
            "before_blob", "after_blob", "mode", "source"}
            and all(isinstance(change[k], str) and SHA.fullmatch(change[k])
                    for k in ("before_blob", "after_blob", "source"))
            and change["before_blob"] != change["after_blob"]
            and change["mode"] == "100644"
            and change["source"] == record["source_after"],
            "invalid reviewed PR input blob, mode or source: " + name)
    return record


def reviewed_pr_input_proof(source, revision, *, names=None):
    """The planner proves source ancestry for each selected exact input bundle."""
    files = tree_inputs(source, revision)
    for name, (_, paths) in REVIEWED_PR_INPUTS.items():
        if names is not None and name not in names:
            continue
        if not paths.intersection(files) or not reviewed_pr_input_active(
                name, lambda p: files.get(p, (None, None))[1]):
            continue
        record = reviewed_pr_input_transition(name)
        if not any(files.get(p, (None, None))[1] == c["after_blob"]
                   for p, c in record["changes"].items()):
            continue
        try:
            for ancestor in (record["source_before"], record["source_after"]):
                git(source, "merge-base", "--is-ancestor", ancestor, revision)
            before = tree_inputs(source, record["source_before"])
            after = tree_inputs(source, record["source_after"])
        except subprocess.CalledProcessError:
            raise ValueError("reviewed PR input source ancestry differs: " + name) from None
        for path, change in record["changes"].items():
            require(before.get(path) == (change["mode"], change["before_blob"])
                    and after.get(path) == files.get(path)
                    == (change["mode"], change["after_blob"]),
                    "reviewed PR input successor blob or mode differs: " + path)


def admit_reviewed_pr_inputs(common, files, source_revision, *, names=None, pin_is_ancestor=False):
    """Peel exact bundles at the release pin, or a descendant, before historical validators.

    Stacked successors must peel to a fixpoint. A later map entry can expose a
    predecessor's after-blob (site_refresh_plans leaves the site_devdeps lockfile
    and package.json after-blobs); a single pass over insertion order would skip
    the earlier name and leave those blobs for _admit_existing_shared_inputs.
    """
    if not isinstance(common, dict):
        return common, files
    peeled = set()
    progressed = True
    while progressed:
        progressed = False
        for name, (_, paths) in REVIEWED_PR_INPUTS.items():
            if name in peeled or (names is not None and name not in names):
                continue
            if not paths.intersection(common) or not reviewed_pr_input_active(name, common.get):
                continue
            record = reviewed_pr_input_transition(name)
            changes = record["changes"]
            if not any(common.get(p) == c["after_blob"] for p, c in changes.items()):
                continue
            require(holds_release_pin(source_revision, pin_is_ancestor=pin_is_ancestor),
                    "reviewed PR input successor requires the signed release pin or its descendant: " + name)
            common = dict(common)
            if files is not None:
                files = dict(files)
            for path, change in changes.items():
                require(common.get(path) == change["after_blob"],
                        "reviewed PR input bundle missing or changed: " + path)
                common[path] = change["before_blob"]
                if files is not None:
                    require(files.get(path) == (change["mode"], change["after_blob"]),
                            "reviewed PR input mode or tree changed: " + path)
                    files[path] = (change["mode"], change["before_blob"])
            peeled.add(name)
            progressed = True
    return common, files


def admit_shared_inputs(baseline, common, files=None, *, source_revision=None,
                        estate_successor_of=None, template_writer_retired_at=None,
                        pin_is_ancestor=False):
    """Admit a sealed estate successor without rewriting historical skip evidence."""
    common, files = admit_retired_template_writer(
        baseline, common, files, source_revision, estate_successor_of,
        template_writer_retired_at)
    _, active_required = required_native_inputs(baseline)
    # Historical transition validators may receive an already-peeled baseline.
    # All production entry points first use skip_baseline(), which requires the
    # current successor; its effective inputs still reject the predecessor blob.
    common, files = admit_reviewed_pr_inputs(
        common, files, source_revision, pin_is_ancestor=pin_is_ancestor)
    common, files = admit_pr_shared_inputs(
        common, files, source_revision, pin_is_ancestor=pin_is_ancestor)
    common, files = admit_native_protocol_helper(
        common, files, source_revision, pin_is_ancestor=pin_is_ancestor)
    common, files = admit_p015_offline_helper(
        common, files, source_revision, pin_is_ancestor=pin_is_ancestor)
    common, files = admit_first_native_helper(
        common, files, source_revision, pin_is_ancestor=pin_is_ancestor)
    common, files = admit_miniapp_membership(
        common, files, source_revision, pin_is_ancestor=pin_is_ancestor)
    baseline, security = reviewed_npm_security_transition(baseline)
    if security is not None:
        require(isinstance(common, dict), "npm security inputs must be a mapping")
        changed = any(common.get(path) == item["after_blob"]
                      for path, item in security["changes"].items())
        if changed or source_revision == security["source_after"]:
            estate = baseline.get("reviewed_estate_input_transition", {})
            require(estate_successor_of == estate.get("source_after")
                    and isinstance(source_revision, str), "npm security requires proven successor")
            common = dict(common)
            if files is not None:
                files = dict(files)
            for path, item in security["changes"].items():
                require(common.get(path) == item["after_blob"], "npm security input missing or changed")
                common[path] = item["before_blob"]
                if files is not None:
                    require(files.get(path) == (item["mode"], item["after_blob"]),
                            "npm security input mode differs")
                    files[path] = (item["mode"], item["before_blob"])
    baseline, shuffle = reviewed_collection_shuffle_transition(baseline)
    if shuffle is not None:
        require(isinstance(common, dict), "collection shuffle shared inputs must be a mapping")
        require(source_revision != shuffle["source_after"] or COLLECTION_SHUFFLE_INPUT in common,
                "qualified collection shuffle input is missing")
        if COLLECTION_SHUFFLE_INPUT in common:
            change = shuffle["changes"][COLLECTION_SHUFFLE_INPUT]
            estate = baseline.get("reviewed_estate_input_transition", {})
            require(common[COLLECTION_SHUFFLE_INPUT] == change["after_blob"]
                    and ESTATE_ADDED_INPUT in common and isinstance(source_revision, str)
                    and source_revision != estate.get("source_after")
                    and estate_successor_of == estate.get("source_after"),
                    "collection shuffle requires the reviewed blob in a proven estate successor")
            if files is not None:
                require(files.get(COLLECTION_SHUFFLE_INPUT) == (change["mode"], change["after_blob"]),
                        "collection shuffle input mode or tree changed")
                files = {p: v for p, v in files.items() if p != COLLECTION_SHUFFLE_INPUT}
            common = {p: v for p, v in common.items() if p != COLLECTION_SHUFFLE_INPUT}
    # The complete existing admission chain still consumes every other input.
    _, packaging = reviewed_ops_packaging_transition(baseline)
    baseline, _ = required_native_inputs(baseline)
    required = active_required
    if required:
        require(isinstance(common, dict), "missing or changed required native input")
        for path, blob in required.items():
            presented = common.get(path)
            chain = (NATIVE_INPUT_CHAIN[path]
                     if path in NATIVE_INPUT_CHAIN and blob == NATIVE_INPUTS[path]
                     else frozenset({blob}))
            require(blob in chain and isinstance(presented, str) and presented in chain,
                    "missing or changed required native input")
            if files is not None:
                require(files.get(path) == ("100644", presented),
                        "required native input mode or tree changed")
        if files is not None:
            files = {p: v for p, v in files.items() if p not in required}
        common = {p: v for p, v in common.items() if p not in required}
    _, tornado = reviewed_tornado66_dependency_transition(baseline)
    _, hang = reviewed_hang_guard_input_transition(baseline)
    _, runtime = reviewed_runtime_dependency_transition(baseline)
    _, lock = reviewed_audit_lock_transition(baseline)
    _, bot = reviewed_bot_packaging_transition(baseline)
    _, site = reviewed_site_lock_transition(baseline, files)
    original, record = reviewed_estate_input_transition(baseline)
    if record is None:
        return _admit_existing_shared_inputs(original, common, files)
    changes = record["changes"]
    require(isinstance(common, dict), "estate shared inputs must be a mapping")
    if hang is not None and HANG_GUARD_INPUT in common:
        # The only admissible new shared input: the exact reviewed helper blob, in a
        # proven estate successor (planner proved ancestry from the helper's source).
        change = hang["changes"][HANG_GUARD_INPUT]
        require(common[HANG_GUARD_INPUT] == change["after_blob"]
                and ESTATE_ADDED_INPUT in common and isinstance(source_revision, str)
                and source_revision != record["source_after"]
                and estate_successor_of == record["source_after"],
                "hang guard input requires the reviewed blob in a proven estate successor")
        if files is not None:
            require(files.get(HANG_GUARD_INPUT) == (change["mode"], change["after_blob"]),
                    "hang guard input mode or tree changed")
            files = {p: v for p, v in files.items() if p != HANG_GUARD_INPUT}
        common = {p: v for p, v in common.items() if p != HANG_GUARD_INPUT}
    if site is not None and common.get(SITE_LOCK_INPUT) == site["changes"][SITE_LOCK_INPUT]["after_blob"]:
        # Only an estate successor (ancestry proven by the planner) may carry the
        # reviewed site lock; the exact predecessor blob is then re-admitted below.
        change = site["changes"][SITE_LOCK_INPUT]
        require(ESTATE_ADDED_INPUT in common and isinstance(source_revision, str)
                and source_revision != record["source_after"]
                and estate_successor_of == record["source_after"],
                "site lock successor requires a proven estate successor")
        if files is not None:
            require(files.get(SITE_LOCK_INPUT) == (change["mode"], change["after_blob"]),
                    "site lock successor mode or tree changed")
            files = dict(files) | {SITE_LOCK_INPUT: (change["mode"], change["before_blob"])}
        common = dict(common) | {SITE_LOCK_INPUT: change["before_blob"]}
    if bot is not None and common.get(BOT_PACKAGING_INPUT) == bot["changes"][BOT_PACKAGING_INPUT]["after_blob"]:
        # Same rule as the site lock: only a proven estate successor may carry the
        # reviewed bot packaging blob; its exact estate after-blob is re-admitted below.
        change = bot["changes"][BOT_PACKAGING_INPUT]
        require(ESTATE_ADDED_INPUT in common and isinstance(source_revision, str)
                and source_revision != record["source_after"]
                and estate_successor_of == record["source_after"],
                "bot packaging successor requires a proven estate successor")
        if files is not None:
            require(files.get(BOT_PACKAGING_INPUT) == (change["mode"], change["after_blob"]),
                    "bot packaging successor mode or tree changed")
            files = dict(files) | {BOT_PACKAGING_INPUT: (change["mode"], change["before_blob"])}
        common = dict(common) | {BOT_PACKAGING_INPUT: change["before_blob"]}
    if packaging is not None and any(
            common.get(path) == change["after_blob"]
            for path, change in packaging["changes"].items()):
        # Same rule as the Tornado bundle: only a proven estate successor may carry
        # the reviewed inputs, and only all four together. Each exact predecessor is
        # then re-admitted below (the added helper is removed), so the complete
        # Tornado bundle and every historical input are still required underneath.
        require(ESTATE_ADDED_INPUT in common and isinstance(source_revision, str)
                and source_revision != record["source_after"]
                and estate_successor_of == record["source_after"]
                and all(common.get(path) == change["after_blob"]
                        for path, change in packaging["changes"].items()),
                "ops packaging successor requires a proven estate successor")
        if files is not None:
            require(all(files.get(path) == (change["mode"], change["after_blob"])
                        for path, change in packaging["changes"].items()),
                    "ops packaging successor mode or tree changed")
            files = dict(files)
            for path, change in packaging["changes"].items():
                if change["before_blob"] is None:
                    files.pop(path)
                else:
                    files[path] = (change["mode"], change["before_blob"])
        common = dict(common)
        for path, change in packaging["changes"].items():
            if change["before_blob"] is None:
                common.pop(path)
            else:
                common[path] = change["before_blob"]
    if tornado is not None and any(common.get(path) == change["after_blob"]
                                   for path, change in tornado["changes"].items()):
        # Admit only the complete reviewed bundle, then restore the exact runtime
        # predecessor for every existing seal and historical skip consumer.
        require(ESTATE_ADDED_INPUT in common and isinstance(source_revision, str)
                and source_revision != record["source_after"]
                and estate_successor_of == record["source_after"]
                and all(common.get(path) == change["after_blob"]
                        for path, change in tornado["changes"].items()),
                "Tornado dependency successor requires a proven estate successor")
        if files is not None:
            require(all(files.get(path) == (change["mode"], change["after_blob"])
                        for path, change in tornado["changes"].items()),
                    "Tornado dependency successor mode or tree changed")
            files = dict(files) | {path: (change["mode"], change["before_blob"])
                                   for path, change in tornado["changes"].items()}
        common = dict(common) | {path: change["before_blob"]
                                 for path, change in tornado["changes"].items()}
    if runtime is not None and any(common.get(path) == change["after_blob"]
                                   for path, change in runtime["changes"].items()):
        # Only a proven estate successor may carry the reviewed runtime dependency
        # blobs, and only all three together; each predecessor after-blob is then
        # re-admitted below by the seal that reviewed it.
        require(ESTATE_ADDED_INPUT in common and isinstance(source_revision, str)
                and source_revision != record["source_after"]
                and estate_successor_of == record["source_after"]
                and all(common.get(path) == change["after_blob"]
                        for path, change in runtime["changes"].items()),
                "runtime dependency successor requires a proven estate successor")
        if files is not None:
            require(all(files.get(path) == (change["mode"], change["after_blob"])
                        for path, change in runtime["changes"].items()),
                    "runtime dependency successor mode or tree changed")
            files = dict(files) | {path: (change["mode"], change["before_blob"])
                                   for path, change in runtime["changes"].items()}
        common = dict(common) | {path: change["before_blob"]
                                 for path, change in runtime["changes"].items()}
    if lock is not None and common.get(AUDIT_LOCK_INPUT) == lock["changes"][AUDIT_LOCK_INPUT]["after_blob"]:
        # Same rule as the site lock and bot packaging: only a proven estate successor
        # may carry the reviewed lock blob; the audit seal's after-blob is re-admitted below.
        change = lock["changes"][AUDIT_LOCK_INPUT]
        require(ESTATE_ADDED_INPUT in common and isinstance(source_revision, str)
                and source_revision != record["source_after"]
                and estate_successor_of == record["source_after"],
                "audit lock successor requires a proven estate successor")
        if files is not None:
            require(files.get(AUDIT_LOCK_INPUT) == (change["mode"], change["after_blob"]),
                    "audit lock successor mode or tree changed")
            files = dict(files) | {AUDIT_LOCK_INPUT: (change["mode"], change["before_blob"])}
        common = dict(common) | {AUDIT_LOCK_INPUT: change["before_blob"]}
    if ESTATE_ADDED_INPUT not in common:
        return _admit_existing_shared_inputs(original, common, files)
    # The exact sealed revision, or a later revision whose ancestry from it was
    # proven by the planner. Either way every estate input below must still be
    # byte-identical to the reviewed successor blobs.
    require(isinstance(source_revision, str) and SHA.fullmatch(source_revision) is not None
            and (source_revision == record["source_after"]
                 or estate_successor_of == record["source_after"]),
            "estate successor source revision differs")
    predecessor = dict(common)
    predecessor_files = dict(files) if files is not None else None
    for path, change in changes.items():
        require(common.get(path) == change["after_blob"],
                "estate successor input blob changed: " + path)
        if files is not None:
            require(files.get(path) == (change["mode"], change["after_blob"]),
                    "estate successor input mode or tree changed: " + path)
        if path == ESTATE_ADDED_INPUT:
            predecessor.pop(path)
            if predecessor_files is not None:
                predecessor_files.pop(path)
        else:
            predecessor[path] = change["before_blob"]
            if predecessor_files is not None:
                predecessor_files[path] = (change["mode"], change["before_blob"])
    # The original admission still checks every unchanged input and the exact
    # preimages. Extra helpers, changed dependencies and weakened historical
    # records cannot become accepted by adding this transition.
    return _admit_existing_shared_inputs(original, predecessor, predecessor_files)


def _admit_existing_shared_inputs(baseline, common, files=None):
    """Admit complete historical maps and each exact reviewed input successor.

    The historical skip/collection evidence is never relabeled as a new run.
    Exact effective inputs remain sealed into this run's admission envelope.
    """
    baseline, _ = reviewed_relay_skip_module_transition(baseline, files)
    baseline, scanner_record = reviewed_scanner_input_transition(baseline)
    baseline, zod_record = reviewed_zod_lock_transition(baseline)
    baseline, audit_record = reviewed_audit_dependency_transition(baseline)
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
    if audit_record is not None:
        require(observability_record is not None
                and audit_record["source_before"] == observability_record["source_after"]
                and audit_record["source_before"] != audit_record["source_after"],
                "audit dependency transition requires its observability predecessor")
        changes = audit_record["changes"]
        require(isinstance(changes, dict) and set(changes) == {"pyproject.toml", "uv.lock"},
                "unreviewed audit dependency input paths")
        successor = dict(accepted[-1])
        for path, change in changes.items():
            require(isinstance(change, dict) and set(change) == {
                "before_blob", "after_blob", "mode",
            } and all(isinstance(change[k], str) and SHA.fullmatch(change[k])
                      for k in ("before_blob", "after_blob"))
                    and change["before_blob"] == successor.get(path)
                    and change["before_blob"] != change["after_blob"]
                    and change["mode"] == modes.get(path) == "100644",
                    "unreviewed audit dependency input blob or mode")
            successor[path] = change["after_blob"]
        accepted.append(successor)
    if zod_record is not None:
        require(audit_record is not None
                and zod_record["source_before"] == audit_record["source_after"]
                and zod_record["source_before"] != zod_record["source_after"],
                "zod lock transition requires its audit predecessor")
        changes = zod_record["changes"]
        require(isinstance(changes, dict) and set(changes) == {
            "frontend/package.json", "frontend/package-lock.json",
            "telegram-bot/yue/miniapp/package.json",
            "telegram-bot/yue/miniapp/package-lock.json",
        }, "unreviewed zod lock input paths")
        successor = dict(accepted[-1])
        for path, change in changes.items():
            require(isinstance(change, dict) and set(change) == {
                "before_blob", "after_blob", "mode",
            } and all(isinstance(change[k], str) and SHA.fullmatch(change[k])
                      for k in ("before_blob", "after_blob"))
                    and change["before_blob"] == successor.get(path)
                    and change["before_blob"] != change["after_blob"]
                    and change["mode"] == modes.get(path) == "100644",
                    "unreviewed zod lock input blob or mode")
            successor[path] = change["after_blob"]
        accepted.append(successor)
    if scanner_record is not None:
        require(zod_record is not None, "scanner input transition requires its zod predecessor")
        changes = scanner_record["changes"]
        path = "tests/_shell_early_exit_pipes.py"
        require(isinstance(changes, dict) and set(changes) == {path},
                "unreviewed scanner input paths")
        change = changes[path]
        require(isinstance(change, dict) and set(change) == {
            "before_blob", "after_blob", "mode",
        } and all(isinstance(change[k], str) and SHA.fullmatch(change[k])
                  for k in ("before_blob", "after_blob"))
                and change["before_blob"] == accepted[-1].get(path)
                and change["before_blob"] != change["after_blob"]
                and change["mode"] == baseline["reviewed_shared_input_transition"][
                    "common_input_modes"].get(path) == "100644",
                "unreviewed scanner input blob or mode")
        accepted.append(accepted[-1] | {path: change["after_blob"]})
    if common not in accepted:
        nearest = min(
            accepted,
            key=lambda item: sum(item.get(path) != common.get(path) for path in set(item) | set(common)),
        )
        drifted = sorted(
            path for path in set(nearest) | set(common) if nearest.get(path) != common.get(path)
        )
        require(False, "shared collection/dependency inputs changed: " + ", ".join(drifted))
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
    _, required = required_native_inputs(value)
    require(not required or required == NATIVE_INPUTS,
            "required native input successor missing")
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
    collect_only = reference or bool(isinstance(assignment, dict) and assignment.get("collect_only"))
    modules = ["tests"] if reference else assignment["modules"]
    role = "reference" if reference else assignment["id"]
    require(set(selection) == {"plan_sha256", "assignment_id", "modules", "pytest_argv",
                               "pytest_addopts"}
            and selection["plan_sha256"] == value["plan_sha256"]
            and selection["assignment_id"] == role and selection["modules"] == modules
            and selection["pytest_addopts"] in ("", "--durations=25"),
            "selection does not match the exact plan")
    argv = selection["pytest_argv"]
    # Receipts may move; bind the cache to the original JUnit path, not the reader's cwd.
    if (collect_only and not reference and isinstance(argv, list)
            and len(argv) >= 4 and isinstance(argv[-1], str) and argv[-2] == "--junitxml"
            and argv[-4:-2] == ["-o", f"cache_dir={Path(argv[-1]).parent / 'pytest-cache'}"]):
        argv = argv[:-4] + argv[-2:]
    suffix = ["-m", "pytest", *(["--collect-only"] if collect_only else []), "-q", *modules]
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
    if collect_only:
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


def join_reference_collections(parts):
    """Union collect-only parts. One process per assignment, never xdist."""
    require(isinstance(parts, list) and parts, "missing reference part")
    nodeids = []
    seen = set()
    skips = {}
    for part in parts:
        require(isinstance(part, dict) and isinstance(part.get("nodeids"), list)
                and isinstance(part.get("collection_skips"), dict), "invalid reference part")
        for nodeid in part["nodeids"]:
            require(isinstance(nodeid, str) and nodeid not in seen, "duplicate node id")
            seen.add(nodeid)
            nodeids.append(nodeid)
        for module, reason in part["collection_skips"].items():
            require(isinstance(module, str) and isinstance(reason, str) and reason,
                    "invalid collection skip")
            if module in skips and skips[module] != reason:
                require(False, "collection skip mismatch: " + module)
            skips[module] = reason
    return {"nodeids": nodeids, "collection_skips": skips}


def require_reference_join(parts, expected_nodeids, expected_skips):
    joined = join_reference_collections(parts)
    have = set(joined["nodeids"])
    missing = [nodeid for nodeid in expected_nodeids if nodeid not in have]
    require(not missing, "missing node id: " + ", ".join(missing))
    extra = [nodeid for nodeid in joined["nodeids"] if nodeid not in set(expected_nodeids)]
    require(not extra, "missing node id: " + ", ".join(extra))
    require(joined["collection_skips"] == expected_skips, "collection skip mismatch")
    return joined


def map_bounded(functions, limit):
    """Run independent functions with a fixed ceiling. Preserve order."""
    if limit < 1:
        raise ValueError("worker limit must be positive")
    if len(functions) <= 1 or limit == 1:
        return [fn() for fn in functions]
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(limit, len(functions))) as pool:
        return list(pool.map(lambda fn: fn(), functions))


def shard_pythonpath(source, site):
    """Expose the recorder and admitted source to pytest and its children.

    Use only absolute, policy-selected entries: inherited/relative entries
    would change meaning when a test launches Python from telegram-bot/yue.
    Keep the verified recorder first, including each reference part's copy.
    """
    return os.pathsep.join(str(path.resolve()) for path in (site, source))


def _collect_reference_part(expected, source, output, site, actual_runner, timing, assignment):
    part = output / "parts" / assignment["id"]
    site = part / "site"
    timing.install(part, site)
    metadata = read_json(part / "metadata.json")
    runner = runner_context(expected["context"], metadata["identity"])
    require(runner == actual_runner, "runner identity changed during preparation")
    cache = part / "pytest-cache"
    parent_opts = os.environ.get("PYTEST_ADDOPTS", "")
    env = os.environ | {
        "LENS_REPORT": str(part / "events.jsonl"),
        "LENS_INVOCATION_ID": metadata["invocation_id"],
        "YUEOPS_PYTEST_SERIAL": "1",
        "PYTHONPATH": shard_pythonpath(source, site),
        "PYTEST_ADDOPTS": parent_opts,
    }
    xml = part / "pytest.xml"
    argv = [sys.executable, "-m", "pytest", "--collect-only", "-q",
            *assignment["modules"], "-o", f"cache_dir={cache}", "--junitxml", str(xml)]
    (part / "pytest-start-unix-ns.txt").write_text(str(time.time_ns()))
    result = subprocess.run(argv, cwd=source, env=env, check=False)
    (part / "pytest-finish-unix-ns.txt").write_text(str(time.time_ns()))
    (part / "pytest-exit-code.txt").write_text(str(result.returncode))
    require(result.returncode in (0, 5), "reference part failed")
    rows = [json.loads(line) for line in (part / "events.jsonl").read_text().splitlines()]
    corpus = next(row for row in rows if row.get("event") == "collection_corpus")
    nodeids = corpus.get("nodeids")
    require(isinstance(nodeids, list), "reference part has no corpus")
    start = next(row for row in rows if row.get("event") == "start")
    execution_context = {key: start.get(key) for key in ("platform", "uid")}
    skips = collection_skips(xml, set(assignment["modules"])) if xml.is_file() else {}
    (part / "selection.json").write_text(json.dumps({
        "plan_sha256": expected["plan_sha256"], "assignment_id": assignment["id"],
        "modules": assignment["modules"], "pytest_argv": argv,
        "pytest_addopts": parent_opts,
    }))
    return {"assignment_id": assignment["id"], "nodeids": nodeids,
            "collection_skips": skips, "invocation_id": metadata["invocation_id"],
            "runner": runner, "execution_context": execution_context}


def collect_reference_parts(expected, source, output, site, actual_runner, timing):
    """Collect-only once per module assignment, in parallel processes.

    Each part is its own interpreter. That is not xdist: workers there reuse
    one process and the Ops import path then leaks across files. The serial
    loop made this job the 40-minute critical path after the test shards
    had already finished.
    """
    assignments = expected["assignments"]
    limit = min(len(assignments), os.cpu_count() or 2)
    collected = map_bounded([
        (lambda item=item: _collect_reference_part(
            expected, source, output, site, actual_runner, timing, item))
        for item in assignments
    ], limit)
    require(all(part["runner"] == actual_runner for part in collected),
            "runner identity changed during preparation")
    invocation = collected[0]["invocation_id"]
    # The summary names the first part; every part retains its own prepared identity.
    parts = [{"assignment_id": part["assignment_id"], "nodeids": part["nodeids"],
              "collection_skips": part["collection_skips"]} for part in collected]
    joined = join_reference_collections(parts)
    payload = {
        "schema": 1, "assignment_id": "reference", "invocation_id": invocation,
        "nodeids": joined["nodeids"], "collection_skips": joined["collection_skips"],
        "runner_context": actual_runner, "execution_context": collected[0]["execution_context"],
        "junit_sha256": sha(json.dumps(joined, sort_keys=True).encode()),
        "parts": [part["assignment_id"] for part in parts],
    }
    (output / "joined.json").write_text(json.dumps(payload) + "\n")
    require(runner_context(expected["context"], os.environ) == actual_runner,
            "runner identity changed during execution")
    return 0


def aggregate(value, reference, directories):
    value = validate_plan(value)
    joined_path = reference / "joined.json"
    if joined_path.is_file():
        payload = read_json(joined_path)
        live_skips = {}
        for role_name in payload.get("parts") or []:
            junit = reference / "parts" / role_name / "pytest.xml"
            require(junit.is_file() and not junit.is_symlink(), "missing reference junit")
            selection = read_json(reference / "parts" / role_name / "selection.json")
            for module, reason in collection_skips(junit, set(selection["modules"])).items():
                if module in live_skips and live_skips[module] != reason:
                    require(False, "reference and shards have different collection skips")
                live_skips[module] = reason
        require(live_skips == payload.get("collection_skips"),
                "reference and shards have different collection skips")
        require(payload.get("schema") == 1 and isinstance(payload.get("nodeids"), list)
                and isinstance(payload.get("collection_skips"), dict)
                and payload.get("junit_sha256") and payload.get("invocation_id"),
                "invalid reference join")
        expected = {
            "assignment_id": "reference", "invocation_id": payload["invocation_id"],
            "nodeids": payload["nodeids"], "collection_skips": payload["collection_skips"],
            "runner_context": payload["runner_context"],
            "execution_context": payload["execution_context"],
            "nonpassing_outcomes": [], "junit_sha256": payload["junit_sha256"],
            "pytest_process_exit_code": 0, "empty_assigned_collection": False,
        }
    else:
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
            if "source_evidence" in value:
                bound = value["source_evidence"]
                require(bound.get("source_revision") == value["source_revision"]
                        and bound.get("status") == "BOUND_SOURCE_EVIDENCE"
                        and bound.get("admission") is False, "invalid source evidence binding")
                source_evidence.validate_baseline(bound, value.get("skip_module_blobs", {}))
                reviewed_runner = skip_baseline()["reviewed_hosted"]["runner"]
                require(all(planned["context"].get(k) == v
                            for k, v in reviewed_runner.items()),
                        "source evidence runner differs from reviewed hosted scope")
                require(value.get("skip_baseline_sha256") ==
                        bound["evidence"][source_evidence.BASELINE]["sha256"],
                        "source baseline digest differs")
            else:
                baseline = skip_baseline()
                require(value.get("skip_baseline_sha256") == sha((ROOT / SKIP_BASELINE).read_bytes())
                        and isinstance(value.get("skip_module_blobs"), dict),
                        "skip baseline or shared collection inputs differ")
                if value.get("admission_rule") == "signed-default-branch":
                    require(value.get("estate_successor_of") is None
                            and value.get("template_writer_retired_at") is None
                            and value.get("pin_is_ancestor") is not True,
                            "signed admission does not carry a seal marker")
                else:
                    admit_shared_inputs(baseline, value.get("common_inputs"),
                                        source_revision=value["source_revision"],
                                        estate_successor_of=value.get("estate_successor_of"),
                                        template_writer_retired_at=value.get("template_writer_retired_at"),
                                        pin_is_ancestor=value.get("pin_is_ancestor") is True)
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


def _commit_ref(source, ref):
    try:
        return git(source, "rev-parse", "--verify", "--end-of-options",
                   ref + "^{commit}").decode().strip()
    except subprocess.CalledProcessError:
        return ""


def on_default_branch(source, revision):
    """True when revision is the default branch tip or its ancestor.

    The plan checkout of a SHA does not create origin/master by itself.
    The workflow fetches refs/remotes/origin/master first. A local fixture
    may use refs/heads/master. A missing ref fails closed.
    """
    require(isinstance(revision, str) and SHA.fullmatch(revision),
            "exact source SHA required")
    found = False
    for ref in ("refs/remotes/origin/master", "refs/heads/master"):
        tip = _commit_ref(source, ref)
        if not tip:
            continue
        found = True
        if tip == revision:
            return True
        try:
            git(source, "merge-base", "--is-ancestor", revision, ref)
            return True
        except subprocess.CalledProcessError:
            continue
    require(found, "default branch ref is missing")
    return False


def admit_signed_default_branch(source, revision, policy_dir=None):
    """Admit a source SHA that is on the default branch and owner-signed.

    Timing shards are chosen by the caller. File lists, helper additions and
    conftest edits are not a separate seal. policy_dir defaults to the
    validator's policy directory.
    """
    require(on_default_branch(source, revision),
            "source SHA is not on the default branch")
    try:
        source_evidence.verify_commit(
            git(source, "cat-file", "commit", revision), policy_dir)
    except source_evidence.Rejected as error:
        raise ValueError("unauthorized source signature") from error


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
            bound = source_evidence.optional(source, ops["ref"])
            expected = plan(source, context, shards, serial_modules(source))
            require(expected["source_revision"] == ops["ref"], "planned source checkout differs")
            if bound is not None:
                files = tree_inputs(source, ops["ref"])
                blobs = {p: files[p][1] for p in expected["modules"]}
                source_evidence.validate_baseline(bound, blobs)
                value.update(mode="sharded", ops_plan=expected,
                             common_inputs=shared_inputs(source, ops["ref"]),
                             source_evidence=bound, skip_module_blobs=blobs,
                             skip_baseline_sha256=bound["evidence"][source_evidence.BASELINE]["sha256"])
            else:
                admit_signed_default_branch(source, ops["ref"])
                common = shared_inputs(source, ops["ref"])
                files = tree_inputs(source, ops["ref"])
                value.update(mode="sharded", ops_plan=expected, common_inputs=common,
                             admission_rule="signed-default-branch",
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
    if source is not None and isinstance(value.get("source_revision"), str):
        record = load_ops_skip_evidence(source, value["source_revision"])
        if record is not None:
            value["ops_skip_evidence"] = record
    return seal(value, "admission_sha256")


def verify_source_evidence(value, source):
    if "source_evidence" in value:
        require(source is not None, "source checkout required for owner evidence")
        require(source_evidence.load(source, value["source_revision"]) == value["source_evidence"],
                "source evidence differs from original admission")


def check_source(value, source, board):
    envelope(value)
    verify_source_evidence(value, source)
    if (value.get("mode") == "sharded"
            and value.get("admission_rule") == "signed-default-branch"):
        admit_signed_default_branch(source, value["source_revision"])
        require(shared_inputs(source, value["source_revision"]) == value.get("common_inputs"),
                "shared inputs differ from the signed commit")
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
    if role == "reference":
        return collect_reference_parts(expected, source, output, site, actual_runner, timing)
    modules = assignments[role]["modules"]
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
                        "PYTHONPATH": shard_pythonpath(source, site),
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


def reviewed_canceled_backup_blob_successor(baseline, value):
    """Retain canceled backup cases as unexecuted; admit only reviewed blob drift."""
    module = "tests/test_critical_key_restore_gate_mutations_20260903.py"
    after = "a609746c0f11d0965861bbecd25044c659c5eabe"
    if value.get("skip_module_blobs", {}).get(module) != after:
        return baseline
    selected = {key: row for key, row in baseline["cases"].items()
                if key.startswith(module + "::")}
    require(len(selected) == 23 and sha(encoded(selected)) == "8f23edcedaac436947b770f5d028c0deb4d2889201fa4bbdf63a68bec2b37ddf",
            "canceled backup historical case identities or reasons differ")
    require(not any(key.startswith(module + "::")
                    for key in baseline.get("reviewed_hosted", {}).get("cases", {})),
            "canceled backup cases must remain historically unexecuted")
    updated = baseline["cases"] | {
        key: row | {"module_blob": after} for key, row in selected.items()}
    return baseline | {"cases": updated}


def reviewed_restore_drill_blob_successor(baseline, value):
    """Move the seven owner-canceled restore-drill cases to the cdn-in-backup blob.

    yueops ed2106b26 (owner t935u) makes the daily dump include
    cdn_entry_observations data, changing the module 2f57ec05 -> 3cca4792. The
    seven e2e cases stay OWNER_CANCELED with the same two reviewed setup
    variants (run 42887205152 skipped them for the base-image reason). Only the
    module blob moves; identities, dispositions and variants are sealed.
    """
    module = "tests/test_yueops_pg_restore_drill_20260924.py"
    before = "2f57ec05cab6f9af631f66650feaaf76a7770222"
    after = "3cca4792fbd3319411901ad3588a879e7b52193f"
    if value.get("skip_module_blobs", {}).get(module) != after:
        return baseline
    hosted = baseline.get("reviewed_hosted", {})
    selected = {key: row for key, row in hosted.get("cases", {}).items()
                if key.startswith(module + "::")}
    require(len(selected) == 7
            and sha(encoded(selected)) == "3fa2693d80385d2531d1d10e17cf6f529be968c2be53d503b0cb432d8a8de32e"
            and all(row["module_blob"] == before and row["disposition"] == "OWNER_CANCELED"
                    for row in selected.values()),
            "restore-drill reviewed case identities, variants or dispositions differ")
    cases = hosted["cases"] | {key: row | {"module_blob": after} for key, row in selected.items()}
    return baseline | {"reviewed_hosted": hosted | {"cases": cases}}


def reviewed_board139_native_successor(baseline, value, native, *, require_native=True):
    """Keep the historical skip seal; qualify two exact Board139 successors.

    Ops 6a894a36 adds the production-shaped orders_archive fixture and a seventh
    negative ACL case. It changes neither the fixture skip nor the native gate.
    Original run 41186871728 passed all seven native calls; its ordinary skips
    must still require those exact same-run calls, never become historical PASS.
    Ops 26f7abe1b and bc4ab688f add the renewal ACL cases at blob 0509528f.
    Run 42300780238 job 128177818905 passed all twenty-two native calls.
    Ordinary shards still skip without the frozen fixture. That skip stays
    bound to those twenty-two same-run calls.
    """
    module = "tests/test_board139_schema_acl_native_20261018.py"
    before = "7031c88d7b25d3b61ff40429cc8e54f3e7248466"
    after = "2d510c6a2e765ae7eb0379ab7671ba64d6770ef4"
    renewal = "0509528f81cd39c6e308e130650670a874b1b3df"
    blob = value.get("skip_module_blobs", {}).get(module)
    if blob not in (after, renewal):
        return baseline
    names = (
        "test_actual_bootstrap_adopts_139_trigger_owner_and_empty_acl",
        "test_actual_audit_refuses_grant_option_and_foreign_owner",
        "test_actual_audit_refuses_nonowner_execute[PUBLIC]",
        "test_actual_audit_refuses_nonowner_execute[app_yue_bot]",
        "test_actual_audit_refuses_nonowner_execute[app_checkin]",
        "test_actual_audit_refuses_nonowner_execute[yueboard_runtime]",
    )
    previous = {module + "::" + name for name in names}
    added = module + "::test_actual_bootstrap_and_audit_stay_strict_around_orders_archive"
    cases = baseline["reviewed_hosted"]["cases"]
    selected = {key for key in cases if key.startswith(module + "::")}
    require(selected == previous, "Board139 historical native case set differs")
    variant = [{"when": "setup", "reason":
                "Skipped: requires frozen Board139 schema fixture; set YUEBOARD_MONEY_SCHEMA_FIXTURE"}]
    for key in previous:
        require(cases[key]["module_blob"] == before
                and cases[key]["outcome"] == "skipped"
                and cases[key]["variants"] == variant
                and cases[key]["disposition"] == "SAME_RUN_NATIVE_REQUIRED"
                and cases[key]["native_target"] == module,
                "Board139 historical native skip binding differs")
    renewal_names = (
        "test_actual_renewal_audit_rejects_extra_callers[PUBLIC-function-exchange_points_renewal(bigint, bigint, text)-]",
        "test_actual_renewal_audit_rejects_extra_callers[PUBLIC-function-renewal_credit_month(timestamp with time zone)-]",
        "test_actual_renewal_audit_rejects_extra_callers[PUBLIC-function-renewal_credit_state(bigint)-yueboard_runtime:EXECUTE:false]",
        "test_actual_renewal_audit_rejects_extra_callers[PUBLIC-function-reserve_order_renewal_credit()-]",
        "test_actual_renewal_audit_rejects_extra_callers[PUBLIC-sequence-renewal_credit_exchanges_id_seq-]",
        "test_actual_renewal_audit_rejects_extra_callers[app_yue_bot-function-exchange_points_renewal(bigint, bigint, text)-]",
        "test_actual_renewal_audit_rejects_extra_callers[app_yue_bot-function-renewal_credit_month(timestamp with time zone)-]",
        "test_actual_renewal_audit_rejects_extra_callers[app_yue_bot-function-renewal_credit_state(bigint)-yueboard_runtime:EXECUTE:false]",
        "test_actual_renewal_audit_rejects_extra_callers[app_yue_bot-function-reserve_order_renewal_credit()-]",
        "test_actual_renewal_audit_rejects_extra_callers[app_yue_bot-sequence-renewal_credit_exchanges_id_seq-]",
        "test_actual_renewal_exact_acl_matches_reviewed_floor[function-exchange_points_renewal(bigint, bigint, text)-]",
        "test_actual_renewal_exact_acl_matches_reviewed_floor[function-renewal_credit_month(timestamp with time zone)-]",
        "test_actual_renewal_exact_acl_matches_reviewed_floor[function-renewal_credit_state(bigint)-yueboard_runtime:EXECUTE:false]",
        "test_actual_renewal_exact_acl_matches_reviewed_floor[function-reserve_order_renewal_credit()-]",
        "test_actual_renewal_exact_acl_matches_reviewed_floor[sequence-renewal_credit_exchanges_id_seq-]",
    )
    expected = previous | {added}
    message = "Board139 successor requires seven exact same-run native calls"
    if blob == renewal:
        expected |= {module + "::" + name for name in renewal_names}
        message = "Board139 renewal successor requires twenty-two exact same-run native calls"
    if require_native:
        passed = native["obligations"].get(module, {}).get("passed", [])
        require(set(passed) == expected and len(passed) == len(expected), message)
    updated = dict(cases)
    for key in expected:
        updated[key] = {"module_blob": blob, "outcome": "skipped",
                        "variants": variant, "disposition": "SAME_RUN_NATIVE_REQUIRED",
                        "native_target": module}
    return baseline | {"reviewed_hosted": baseline["reviewed_hosted"] | {"cases": updated}}


def reviewed_first_native_successor(baseline, value, native, *, require_native=True):
    policy = first_native_policy()
    # Identical native-test blobs on a descendant keep the same skip binding.
    # The native job in this run still has to pass every bound case.
    if not holds_release_pin(value.get("source_revision"),
                             pin_is_ancestor=value.get("pin_is_ancestor") is True):
        return baseline
    require(all(value["skip_module_blobs"].get(module) == blob
                for module, blob in policy["module_blobs"].items()),
            "first native module source differs")
    cases = dict(baseline["reviewed_hosted"]["cases"])
    for nodeid, row in policy["cases"].items():
        module = nodeid.split("::", 1)[0]
        if require_native:
            require(nodeid in native["obligations"].get(module, {}).get("passed", []),
                    "first native successor lacks exact same-run call: " + nodeid)
        cases[nodeid] = row | {"module_blob": policy["module_blobs"][module],
                              "disposition": "SAME_RUN_NATIVE_REQUIRED",
                              "native_target": module}
    return baseline | {"reviewed_hosted": baseline["reviewed_hosted"] | {"cases": cases}}


ORDINARY_SKIP_EVIDENCE_SHA256 = "0015923faa21c5658538563df31b58c2c17beab227b78ff0c9b59f8540669f0d"
ORDINARY_SKIP_EVIDENCE = Path("reviews/ops-ordinary-skip-evidence-20261107.json")
# 2026-11-10: run 42817758699 (yueops 01aaffe41) passed every selected job; its
# ordinary shards skipped 134 cases for the same environmental reasons after
# owner-approved LA retirement / domain cutover edits moved their test modules.
# Each reviewed file is evaluated independently against the same admitted set
# and admits only its own exact after_blob, never a later one.
ORDINARY_SKIP_EVIDENCE_20261110_SHA256 = "b1163b8acd2f71ac6f16d5e17815befc817bade11f4547df72c187b1084063c6"
ORDINARY_SKIP_EVIDENCE_20261110 = Path("reviews/ops-ordinary-skip-evidence-20261110.json")
# Owner t935u (2026-11-10): the yueops backup includes cdn_entry_observations.
# The restore-drill module changed; its seven Docker e2e skips (same reason as
# run 42817758699) move to the reviewed successor blob. No case is added.
ORDINARY_SKIP_EVIDENCE_20261110B_SHA256 = "2f1cfa9a2d32de58b4b19f013989e29c5858905932114e7dbce34147ff099388"
ORDINARY_SKIP_EVIDENCE_20261110B = Path("reviews/ops-ordinary-skip-evidence-20261110b.json")
# yueops 0e8c29c02 (#477 R-16): the dead-backed autohide now reads pool owners,
# so this module gains a per-module owners fixture (a6a629cd -> 57146f4b). Its one
# before_blob is the admitted baseline blob cbfe9f4b: ordinary evidence files are
# each checked against the admitted set, not chained (run 42878457376 rejected a6a629cd).
# native VLESS skip keeps the same XRAY_PROBE_TEST_BIN reason. No case is added.
ORDINARY_SKIP_EVIDENCE_20261111_SHA256 = "acfcca51c3bb471587816c78f55ef3ce846eba791fe32994c7619f579f3403cd"
ORDINARY_SKIP_EVIDENCE_20261111 = Path("reviews/ops-ordinary-skip-evidence-20261111.json")
# yueops #482 (group-5 CF autohide): the module gains one unskipped test
# (a visible row outside the probe account's groups stays UNKNOWN), so the same
# admitted XRAY_PROBE_TEST_BIN skip moves cbfe9f4b -> b6509a58. Checked against the
# admitted baseline like 20261111 (not chained). No case is added.
ORDINARY_SKIP_EVIDENCE_20261111B_SHA256 = "516146046639bbbd1bcda7565a8c60b736471e13e952951a7b47bd8e28b5db91"
ORDINARY_SKIP_EVIDENCE_20261111B = Path("reviews/ops-ordinary-skip-evidence-20261111b.json")
# yueops 3f6b045c0 (ship 9, group-5 credential): the module's hide fixture now
# stubs catalog group lookups and the notifier; the same admitted XRAY_PROBE_TEST_BIN
# skip moves cbfe9f4b -> 89199841. Local run on 5c4cc83a7: 38 passed, 1 skipped
# with the same reason. Checked against the admitted baseline (not chained).
ORDINARY_SKIP_EVIDENCE_20261111C_SHA256 = "9b9b669ed2037a275c5a86b7293df6a0fc5cb3da51ab91443adcf3a4d8aae3a6"
ORDINARY_SKIP_EVIDENCE_20261111C = Path("reviews/ops-ordinary-skip-evidence-20261111c.json")
# Ship 9 fix ace262936: the compose mount floor test adds the read-only
# retired-entry list mount (#493). The admitted Docker-image skip in the same
# module keeps its reason and moves 03118c49 -> c0037189. Checked against the
# admitted baseline (not chained). No case is added.
ORDINARY_SKIP_EVIDENCE_20261111D_SHA256 = "e297ce3a7eb9fa0459b527f1cd5851b13a6621a90c76dc88ff8967f75b60cc6e"
ORDINARY_SKIP_EVIDENCE_20261111D = Path("reviews/ops-ordinary-skip-evidence-20261111d.json")
# Ship 9 fix 9e628afe1: the signed-closure pin test admits
# scripts/lib/retired_entry_quarantine.py as a REQUIRED sealed-root input. The
# admitted explicit-GPG skip in the same module keeps its reason and moves
# 3b3443dc -> c697afa5 (3b3443dc is the admitted blob after the reviewed
# release skip-blob successor 1a88653d -> 3b3443dc). Not chained.
# No case is added.
ORDINARY_SKIP_EVIDENCE_20261111E_SHA256 = "249428bfb964c061815058bd0f4018faba69bed44fdea5865fbb1c89137bcdf5"
ORDINARY_SKIP_EVIDENCE_20261111E = Path("reviews/ops-ordinary-skip-evidence-20261111e.json")
# Ship 9 8bb2ce01b (run 43024038775): the relay-coordinator delivery-closure
# module moved its admitted real-root-installer skips to blob 3c9f5d4f (22
# updates, same reasons; transitive-input ids are now repo-relative) and adds
# 9 new skips with the same root-installer class of reason. Updates are checked
# against the admitted baseline (not chained); additions must be new ids.
ORDINARY_SKIP_EVIDENCE_20261111F_SHA256 = "0322d89329822d0226409ea75a5c438b92b58039557c005242bf0b792b84a3d6"
ORDINARY_SKIP_EVIDENCE_20261111F = Path("reviews/ops-ordinary-skip-evidence-20261111f.json")
ORDINARY_SKIP_EVIDENCE_FILES = (
    (ORDINARY_SKIP_EVIDENCE, ORDINARY_SKIP_EVIDENCE_SHA256),
    (ORDINARY_SKIP_EVIDENCE_20261110, ORDINARY_SKIP_EVIDENCE_20261110_SHA256),
    (ORDINARY_SKIP_EVIDENCE_20261110B, ORDINARY_SKIP_EVIDENCE_20261110B_SHA256),
    (ORDINARY_SKIP_EVIDENCE_20261111, ORDINARY_SKIP_EVIDENCE_20261111_SHA256),
    (ORDINARY_SKIP_EVIDENCE_20261111B, ORDINARY_SKIP_EVIDENCE_20261111B_SHA256),
    (ORDINARY_SKIP_EVIDENCE_20261111C, ORDINARY_SKIP_EVIDENCE_20261111C_SHA256),
    (ORDINARY_SKIP_EVIDENCE_20261111D, ORDINARY_SKIP_EVIDENCE_20261111D_SHA256),
    (ORDINARY_SKIP_EVIDENCE_20261111E, ORDINARY_SKIP_EVIDENCE_20261111E_SHA256),
    (ORDINARY_SKIP_EVIDENCE_20261111F, ORDINARY_SKIP_EVIDENCE_20261111F_SHA256),
)
OPS_SKIP_EVIDENCE = "tests/admission/ordinary-skip-evidence.json"


def ordinary_skip_evidence_file(relative=None):
    """Reviewed evidence inside this policy root, or None when this tree has none.

    Isolated copies carry the shard script without this reviews file. Walk only
    real entries under this root and refuse a symlink, so the lookup cannot
    leave the isolated tree for another checkout.
    """
    root = ROOT.resolve()
    current = root
    for part in (ORDINARY_SKIP_EVIDENCE if relative is None else relative).parts:
        current = current / part
        if current.is_symlink() or not current.exists():
            return None
    resolved = current.resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        return None
    return resolved


def ordinary_skip_evidence_successors(admitted, value):
    """Admit one reviewed ordinary-skip evidence set, and no later blob.

    Run 42307825077 passed the selected matrix. Its ordinary shards skipped
    these cases for unchanged environmental reasons, or moved an already
    admitted skip to a new test-module blob. The dynamic service-grant xfails
    are not in this set. A different current blob is omitted, not inherited,
    including an earlier baseline whose admitted blob has not reached before_blob.
    The live after_blob still has to succeed that admitted skip exactly.
    """
    successors = {}
    for relative, digest in ORDINARY_SKIP_EVIDENCE_FILES:
        path = ordinary_skip_evidence_file(relative)
        if path is not None:
            successors.update(_ordinary_skip_evidence_record(path, digest, admitted, value))
    record = value.get("ops_skip_evidence") if isinstance(value, dict) else None
    if isinstance(record, dict):
        successors.update(_apply_ordinary_skip_record(record, admitted, value))
    return successors


def _ordinary_skip_evidence_record(path, digest, admitted, value):
    raw = path.read_bytes()
    require(sha(raw) == digest, "unreviewed ordinary skip evidence")
    return _apply_ordinary_skip_record(json.loads(raw), admitted, value)


def load_ops_skip_evidence(checkout, revision):
    """Ops-commit skip evidence, or None when that path is absent.

    The ops commit is the seal. This policy tree does not pin another digest.
    A missing path adds no successors. Any other git or record failure is an error.
    """
    require(isinstance(revision, str) and SHA.fullmatch(revision),
            "ops skip evidence requires an exact revision")
    spec = f"{revision}:{OPS_SKIP_EVIDENCE}"
    try:
        raw = git(checkout, "show", spec)
    except subprocess.CalledProcessError as error:
        err = error.stderr or b""
        if error.returncode == 128 and OPS_SKIP_EVIDENCE.encode() in err:
            return None
        raise
    try:
        record = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError("invalid ops skip evidence") from error
    _skip_evidence_shape(record)
    return {"schema": record["schema"], "updates": record["updates"],
            "additions": record["additions"]}


def _skip_evidence_shape(record):
    require(isinstance(record, dict) and record.get("schema") == 1
            and isinstance(record.get("updates"), dict)
            and isinstance(record.get("additions"), dict)
            and (record["updates"] or record["additions"]),
            "invalid ordinary skip evidence")


def _apply_ordinary_skip_record(record, admitted, value):
    _skip_evidence_shape(record)
    blobs = value.get("skip_module_blobs") if isinstance(value, dict) else None
    blobs = blobs if isinstance(blobs, dict) else {}
    successors = {}
    for nodeid, change in record["updates"].items():
        module = nodeid.split("::", 1)[0] if isinstance(nodeid, str) and "::" in nodeid else ""
        require(isinstance(nodeid, str) and safe_module(module)
                and isinstance(change, dict) and set(change) == {"before_blob", "after_blob"}
                and change["before_blob"] != change["after_blob"]
                and SHA.fullmatch(change["before_blob"]) and SHA.fullmatch(change["after_blob"]),
                "invalid ordinary skip evidence")
        if blobs.get(module) != change["after_blob"]:
            continue
        historical = admitted.get(nodeid)
        require(isinstance(historical, dict) and historical.get("outcome") == "skipped"
                and isinstance(historical.get("reason"), str) and historical["reason"]
                and historical.get("module_blob") == change["before_blob"],
                "ordinary skip evidence does not succeed an admitted skip: " + str(nodeid))
        successors[nodeid] = {"outcome": "skipped", "reason": historical["reason"],
                              "module_blob": change["after_blob"]}
    for nodeid, case in record["additions"].items():
        module = nodeid.split("::", 1)[0] if isinstance(nodeid, str) and "::" in nodeid else ""
        require(isinstance(nodeid, str) and safe_module(module) and nodeid not in admitted
                and isinstance(case, dict) and set(case) == {"outcome", "reason", "module_blob"}
                and case["outcome"] == "skipped" and isinstance(case["reason"], str) and case["reason"]
                and SHA.fullmatch(case["module_blob"]),
                "ordinary skip evidence addition is not a new skip: " + str(nodeid))
        if blobs.get(module) != case["module_blob"]:
            continue
        successors[nodeid] = {"outcome": "skipped", "reason": case["reason"],
                              "module_blob": case["module_blob"]}
    return successors


def _invoke_native_successor(fn, baseline, value, native, require_native):
    """Call one native blob successor, including a historical signature.

    Current policy accepts require_native=False so a precheck can rewrite
    blobs without a same-run receipt. A historical module still requires the
    receipt argument list; feed it the case ids from its own source only
    after the live blob has selected that successor.
    """
    if "require_native" in fn.__code__.co_varnames:
        return fn(baseline, value, native, require_native=require_native)
    if require_native:
        return fn(baseline, value, native)
    return fn(baseline, value, synthetic_native_obligations(value))


def synthetic_native_obligations(value):
    """Native case ids a historical successor checks once its blob matches."""
    obligations = {}
    policy = first_native_policy()
    for nodeid in policy["cases"]:
        module = nodeid.split("::", 1)[0]
        obligations.setdefault(module, []).append(nodeid)
    source = inspect.getsource(reviewed_board139_native_successor)
    module_name = "tests/test_board139_schema_acl_native_20261018.py"
    names = [name.split("::")[-1] for name in re.findall(
        r'"((?:::)?test_actual_[^"]+)"', source)]
    previous = [name for name in names if not name.startswith("test_actual_renewal_")]
    renewal_names = [name for name in names if name.startswith("test_actual_renewal_")]
    after = re.search(r'\bafter = "([0-9a-f]{40})"', source)
    renewal = re.search(r'\brenewal = "([0-9a-f]{40})"', source)
    blobs = value.get("skip_module_blobs") if isinstance(value, dict) else None
    live = blobs.get(module_name) if isinstance(blobs, dict) else None
    expected = [module_name + "::" + name for name in previous]
    if renewal and live == renewal.group(1):
        expected.extend(module_name + "::" + name for name in renewal_names)
    elif after and live not in (None, after.group(1)):
        expected = []
    if expected:
        obligations[module_name] = expected
    return {"obligations": {module: {"passed": ids} for module, ids in obligations.items()}}


def apply_reviewed_skip_blob_successors(baseline, value, native, *, require_native=True):
    """Apply the same reviewed blob seals join applies before it compares cases."""
    baseline = reviewed_canceled_backup_blob_successor(baseline, value)
    restore = globals().get("reviewed_restore_drill_blob_successor")
    if restore is not None:
        baseline = restore(baseline, value)
    baseline = _invoke_native_successor(
        reviewed_board139_native_successor, baseline, value, native, require_native)
    baseline = _invoke_native_successor(
        reviewed_first_native_successor, baseline, value, native, require_native)
    return apply_ops_reviewed_skip_blobs(baseline, value)


def apply_ops_reviewed_skip_blobs(baseline, value):
    """Rewrite a reviewed case blob when the ops commit seals that pair.

    Join compares a reviewed case blob directly. An ordinary successor does
    not reach it. Disposition, variants and outcome stay on the reviewed row.
    A blob a hardcoded successor already moved is left as it is.
    """
    record = value.get("ops_skip_evidence") if isinstance(value, dict) else None
    if not isinstance(record, dict) or not isinstance(baseline, dict):
        return baseline
    hosted = baseline.get("reviewed_hosted")
    cases = hosted.get("cases") if isinstance(hosted, dict) else None
    if not isinstance(cases, dict):
        return baseline
    blobs = value.get("skip_module_blobs")
    blobs = blobs if isinstance(blobs, dict) else {}
    updates = record.get("updates") if isinstance(record.get("updates"), dict) else {}
    rewritten = dict(cases)
    changed = False
    for nodeid, change in updates.items():
        module = nodeid.split("::", 1)[0] if isinstance(nodeid, str) and "::" in nodeid else ""
        if not isinstance(change, dict) or blobs.get(module) != change.get("after_blob"):
            continue
        row = rewritten.get(nodeid)
        if not isinstance(row, dict) or row.get("module_blob") == change.get("after_blob"):
            continue
        require(row.get("module_blob") == change.get("before_blob"),
                "ordinary skip evidence does not succeed an admitted skip: " + str(nodeid))
        rewritten[nodeid] = row | {"module_blob": change["after_blob"]}
        changed = True
    if not changed:
        return baseline
    return baseline | {"reviewed_hosted": hosted | {"cases": rewritten}}


def prepare_skip_bindings(value, native, *, require_native=True, check_shared_inputs=True):
    """Bind every admitted skip to the module blob join will require.

    admit_skips and skip-blob-precheck both call this. A later copy of the
    successor order would let a reviewed blob drift out of the precheck.
    """
    sealed_baseline = skip_baseline()
    _, i10_blob_record = reviewed_i10_skip_blob_successor_transition(sealed_baseline)
    _, retirement = reviewed_retired_host_transition(sealed_baseline)
    _, blob_record = reviewed_skip_blob_successor_transition(sealed_baseline)
    _, release_blob_record = reviewed_release_skip_blob_successor_transition(sealed_baseline)
    _, case_successors = reviewed_case_file_transition(sealed_baseline)
    baseline, estate = reviewed_estate_input_transition(sealed_baseline)
    if (check_shared_inputs and estate is not None
            and value.get("admission_rule") != "signed-default-branch"):
        admit_shared_inputs(sealed_baseline, value.get("common_inputs"),
                            source_revision=value.get("source_revision"),
                            estate_successor_of=value.get("estate_successor_of"),
                            template_writer_retired_at=value.get("template_writer_retired_at"),
                            pin_is_ancestor=value.get("pin_is_ancestor") is True)
    baseline, preservation_successors = reviewed_relay_preservation_module_transition(baseline)
    baseline, meter_successors = reviewed_relay_meter_module_transition(baseline)
    baseline, metrics_successors = reviewed_relay_metrics_module_transition(baseline)
    baseline, relay_successors = reviewed_relay_skip_module_transition(baseline)
    baseline, extra = reviewed_current_skip_transition(baseline)
    _, successors = reviewed_skip_module_transition(baseline)
    successors.update(extra)
    admitted = {nodeid: dict(case) for nodeid, case in baseline["cases"].items()}
    for mapping in (successors, relay_successors, metrics_successors, meter_successors,
                    preservation_successors, case_successors):
        admitted.update(mapping)
    hosted = baseline.get("reviewed_hosted", {}).get("cases", {})
    blob_successors = skip_blob_successors(blob_record, admitted, hosted)
    admitted.update(blob_successors)
    release_blob_successors = skip_blob_successors(release_blob_record, admitted, hosted)
    admitted.update(release_blob_successors)
    i10_blob_successors = skip_blob_successors(i10_blob_record, admitted, hosted)
    ordinary_skips = ordinary_skip_evidence_successors(admitted, value)
    baseline = apply_reviewed_skip_blob_successors(
        baseline, value, native, require_native=require_native)
    return {
        "sealed_baseline": sealed_baseline,
        "retirement": retirement,
        "successors": successors,
        "relay_successors": relay_successors,
        "metrics_successors": metrics_successors,
        "meter_successors": meter_successors,
        "preservation_successors": preservation_successors,
        "case_successors": case_successors,
        "blob_successors": blob_successors,
        "release_blob_successors": release_blob_successors,
        "i10_blob_successors": i10_blob_successors,
        "ordinary_skips": ordinary_skips,
        "baseline": baseline,
        "reviewed": baseline.get("reviewed_hosted", {}),
    }


def admit_skips(value, result, native):
    if "source_evidence" in value:
        return source_evidence.admit_skips(value["source_evidence"], value["skip_module_blobs"],
                                           result, native, set(NATIVE_TARGETS),
                                           set(first_native_policy()["cases"]))
    bound = prepare_skip_bindings(value, native)
    sealed_baseline = bound["sealed_baseline"]
    retirement = bound["retirement"]
    successors = bound["successors"]
    relay_successors = bound["relay_successors"]
    metrics_successors = bound["metrics_successors"]
    meter_successors = bound["meter_successors"]
    preservation_successors = bound["preservation_successors"]
    case_successors = bound["case_successors"]
    blob_successors = bound["blob_successors"]
    release_blob_successors = bound["release_blob_successors"]
    i10_blob_successors = bound["i10_blob_successors"]
    ordinary_skips = bound["ordinary_skips"]
    baseline = bound["baseline"]
    reviewed = bound["reviewed"]
    unknown = []
    observed_collection = {}
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
            require(NEZHA_RETIREMENT_KEY not in sealed_baseline or module != NEZHA_RETIRED_MODULE,
                    "retired Nezha test cannot inherit a historical skip: " + nodeid)
            if retirement is not None and module == RETIRED_HOST_MODULE:
                require(retired_host_case_admitted(
                            retirement, sealed_baseline["cases"], nodeid, row,
                            value["skip_module_blobs"].get(module)),
                        "retired host case or successor blob differs: " + nodeid)
                counts["HISTORICAL_UNEXECUTED"] += 1
                continue
            specific = reviewed.get("cases", {}).get(nodeid)
            if specific is None:
                observed = {
                    "outcome": row["outcome"], "reason": row.get("reason"),
                    "module_blob": value["skip_module_blobs"].get(module),
                }
                if observed not in (baseline["cases"].get(nodeid), successors.get(nodeid),
                                    relay_successors.get(nodeid), metrics_successors.get(nodeid),
                                    meter_successors.get(nodeid), preservation_successors.get(nodeid),
                                    case_successors.get(nodeid), blob_successors.get(nodeid),
                                    release_blob_successors.get(nodeid),
                                    i10_blob_successors.get(nodeid),
                                    ordinary_skips.get(nodeid)):
                    unknown.append(nodeid)
                    continue
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
    require(not unknown, "new or changed case skip/xfail: " + ", ".join(unknown))
    return {"status": "NO_NEW_SKIPS", "baseline_sha256": value["skip_baseline_sha256"],
            "baseline_source_revision": baseline["source_revision"],
            "skips_are_passes": False, "disposition_counts": counts,
            "host_native_acceptance": "INDEPENDENT"}


def export_source_baseline(source, revision):
    """Migrate approved records only. New observations never create approvals."""
    files = source_evidence.tree_inputs(source, revision)
    blobs = {path: row["git_blob"] for path, row in files.items() if safe_module(path)}
    value = {"source_revision": revision, "skip_module_blobs": blobs,
             "pin_is_ancestor": release_pin_is_ancestor(source, revision)}
    bound = prepare_skip_bindings(value, {}, require_native=False, check_shared_inputs=False)
    baseline = bound["baseline"]
    candidates = {}
    for name in ("successors", "relay_successors", "metrics_successors", "meter_successors",
                 "preservation_successors", "case_successors", "blob_successors",
                 "release_blob_successors", "i10_blob_successors", "ordinary_skips"):
        for nodeid, case in bound[name].items():
            candidates.setdefault(nodeid, []).append(case)
    for nodeid, case in baseline["cases"].items():
        candidates.setdefault(nodeid, []).append(case)
    hosted = bound["reviewed"].get("cases", {})
    mandatory_nodes = set(first_native_policy()["cases"])
    records, unmatched = {}, []
    for nodeid in sorted(candidates.keys() | hosted.keys()):
        module = nodeid.split("::", 1)[0]
        live = blobs.get(module)
        variants = []
        specific = hosted.get(nodeid)
        if specific is not None:
            if specific["module_blob"] == live:
                for variant in specific["variants"]:
                    case = {key: specific[key] for key in ("outcome", "module_blob", "disposition")}
                    if "native_target" in specific:
                        case["native_target"] = specific["native_target"]
                    variants.append(case | variant)
        else:
            for case in candidates.get(nodeid, []):
                if case["module_blob"] == live:
                    # Historical non-hosted records did not constrain pytest phase.
                    # Enumerate that existing allowance, never infer a new reason/blob.
                    for phase in ("setup", "call", "teardown"):
                        variants.append(case | {"when": phase, "disposition": "HISTORICAL_UNEXECUTED"})
        if variants:
            if module in NATIVE_TARGETS or nodeid in mandatory_nodes:
                # This tightens a historical label to an already mandatory
                # public same-run obligation. It does not manufacture a pass.
                for case in variants:
                    case.update(disposition="SAME_RUN_NATIVE_REQUIRED", native_target=module)
            records[nodeid] = list({source_evidence.canonical(row): row for row in variants}.values())
        else:
            unmatched.append(nodeid)
    collection = {}
    for module, case in baseline["collection_skips"].items():
        if case["module_blob"] == blobs.get(module):
            collection[module] = case
        else:
            unmatched.append(module)
    inputs = {path: row for path, row in files.items() if path not in source_evidence.EVIDENCE_PATHS}
    digest = source_evidence.digest(source_evidence.canonical(inputs))
    exported = {"schema": 1, "status": "HISTORICAL_SKIPS_NOT_PASSES", "inputs_sha256": digest,
                "context": baseline["context"], "cases": records, "collection_skips": collection}
    source_evidence.validate_baseline({"baseline": exported}, blobs)
    return {"schema": 1, "status": "EXPORT_WITH_UNMATCHED_HISTORY" if unmatched else "EXPORT_READY",
            "source_revision": revision, "public_policy_revision":
            git(ROOT, "rev-parse", "HEAD").decode().strip(),
            "authority_baseline_sha256": sha((ROOT / SKIP_BASELINE).read_bytes()),
            "unmatched": unmatched, "baseline": exported,
            "shared_inputs": {"schema": 1, "inputs": inputs, "inputs_sha256": digest},
            "admission": False}


def join(value, evidence, validation_result, expected_sha, source=None):
    envelope(value)
    verify_source_evidence(value, source)
    if (value.get("mode") == "sharded"
            and value.get("admission_rule") == "signed-default-branch"):
        require(source is not None, "source checkout required")
        admit_signed_default_branch(source, value["source_revision"])
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


_SKIP_UNKNOWN = object()
ORDINARY_BINDING_KEYS = (
    "successors", "relay_successors", "metrics_successors", "meter_successors",
    "preservation_successors", "case_successors", "blob_successors",
    "release_blob_successors", "i10_blob_successors", "ordinary_skips",
)
_POLICY_HELPERS = (
    "_invoke_native_successor", "synthetic_native_obligations",
    "apply_ops_reviewed_skip_blobs", "apply_reviewed_skip_blob_successors",
    "prepare_skip_bindings",
)


def _case_blob(case):
    if not isinstance(case, dict):
        return None
    blob = case.get("module_blob")
    if isinstance(blob, str) and SHA.fullmatch(blob):
        return blob
    return None


def _dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _const_arg(call, index):
    if index >= len(call.args):
        return None
    arg = call.args[index]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    return None


def _list_strings(node):
    if not isinstance(node, ast.List):
        return None
    values = []
    for item in node.elts:
        if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
            return None
        values.append(item.value)
    return values


def _docker_returncode(args):
    """Return code the central runner produces for one docker invocation.

    Docker and nginx are installed. A pinned image is not already loaded, and
    this precheck does not pull it: image inspect fails. info, run, and the
    other provisioning commands succeed.
    """
    if not args:
        return _SKIP_UNKNOWN
    if args[0] == "info":
        return 0
    if args[:2] == ["image", "inspect"]:
        return 1
    if args[0] in {"run", "rm", "exec", "build", "network", "cp", "pull"}:
        return 0
    return _SKIP_UNKNOWN


def _command_prefix(node, count):
    if not isinstance(node, ast.List) or len(node.elts) < count:
        return None
    values = []
    for item in node.elts[:count]:
        if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
            return None
        values.append(item.value)
    return values


def _positional_docker_code(call):
    first = _const_arg(call, 0)
    if first is None:
        return _SKIP_UNKNOWN
    second = _const_arg(call, 1)
    if second is None:
        return _docker_returncode([first])
    return _docker_returncode([first, second])


def _subprocess_docker_code(call):
    if not call.args:
        return _SKIP_UNKNOWN
    prefix = _command_prefix(call.args[0], 2)
    if prefix is None or prefix[0] != "docker":
        return _SKIP_UNKNOWN
    longer = _command_prefix(call.args[0], 3)
    return _docker_returncode((longer or prefix)[1:])


def _eval_call(node, env):
    dotted = _dotted(node.func)
    if dotted == "os.geteuid":
        return 0
    if dotted == "shutil.which":
        name = _const_arg(node, 0)
        if name in {"docker", "nginx"}:
            return "/usr/bin/" + name
        return _SKIP_UNKNOWN
    if dotted in {"os.environ.get", "os.getenv"}:
        key = _const_arg(node, 0)
        if key == "GITHUB_ACTIONS":
            return "true"
        if key in {"YUEOPS_RELEASE_ENV", "XRAY_PROBE_TEST_BIN", "TICKET_JOBS_TEST_DSN"}:
            return None
        return _SKIP_UNKNOWN
    if dotted in {"_docker", "docker"}:
        code = _positional_docker_code(node)
        return code if code is _SKIP_UNKNOWN else {"returncode": code}
    if dotted == "subprocess.run":
        code = _subprocess_docker_code(node)
        return code if code is _SKIP_UNKNOWN else {"returncode": code}
    if dotted == "os.uname":
        return {"sysname": "Linux"}
    if isinstance(node.func, ast.Attribute) and node.func.attr == "is_file":
        owner = node.func.value
        if isinstance(owner, ast.Name) and "SCHEMA" in owner.id:
            return True
        return _SKIP_UNKNOWN
    if isinstance(node.func, ast.Name) and not node.args and not node.keywords:
        return _call_function_return(node.func.id, env)
    return _SKIP_UNKNOWN


def _call_function_return(name, env):
    """Evaluate a zero-argument helper whose body is a single return."""
    if name in env["stack"]:
        return _SKIP_UNKNOWN
    function = env["functions"].get(name)
    if function is None:
        return _SKIP_UNKNOWN
    body = [stmt for stmt in function.body
            if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Constant)]
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        return _SKIP_UNKNOWN
    env["stack"].add(name)
    try:
        return _eval_skip_expr(body[0].value, env)
    finally:
        env["stack"].discard(name)


def _eval_skip_expr(node, env):
    """True/False when the central runner decides the expression, else unknown."""
    if node is None:
        return _SKIP_UNKNOWN
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in env["values"]:
            return _SKIP_UNKNOWN
        value = env["values"][node.id]
        if isinstance(value, ast.AST):
            return _eval_skip_expr(value, env)
        return value
    if isinstance(node, ast.Attribute):
        if _dotted(node) == "sys.platform":
            return "linux"
        base = _eval_skip_expr(node.value, env)
        if isinstance(base, dict) and node.attr in base:
            return base[node.attr]
        return _SKIP_UNKNOWN
    if isinstance(node, ast.Call):
        return _eval_call(node, env)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        value = _eval_skip_expr(node.operand, env)
        if value is _SKIP_UNKNOWN:
            return _SKIP_UNKNOWN
        return not value
    if isinstance(node, ast.BoolOp):
        values = [_eval_skip_expr(item, env) for item in node.values]
        if isinstance(node.op, ast.And):
            if any(value is False for value in values):
                return False
            if any(value is _SKIP_UNKNOWN for value in values):
                return _SKIP_UNKNOWN
            return all(value is True or value not in (False, _SKIP_UNKNOWN) and bool(value)
                       for value in values)
        if any(value is True for value in values):
            return True
        if any(value is _SKIP_UNKNOWN for value in values):
            return _SKIP_UNKNOWN
        return any(bool(value) for value in values)
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1:
        left = _eval_skip_expr(node.left, env)
        right = _eval_skip_expr(node.comparators[0], env)
        if left is _SKIP_UNKNOWN or right is _SKIP_UNKNOWN:
            return _SKIP_UNKNOWN
        op = node.ops[0]
        if isinstance(op, (ast.Eq, ast.Is)):
            return left == right
        if isinstance(op, (ast.NotEq, ast.IsNot)):
            return left != right
    return _SKIP_UNKNOWN


def _remember_assign(stmt, env):
    if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)):
        env["values"][stmt.targets[0].id] = _eval_skip_expr(stmt.value, env)


def _contains_direct_fail(stmts):
    for stmt in stmts:
        if isinstance(stmt, ast.Raise):
            return True
        if (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
                and _dotted(stmt.value.func) == "pytest.fail"):
            return True
    return False


def _skip_calls(stmts):
    found = []
    for stmt in stmts:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Call) and _dotted(node.func) in {"pytest.skip", "pytest.xfail"}:
                found.append(node)
    return found


def _walk_skip_block(stmts, env, *, reached=True):
    """Record whether each pytest.skip/xfail in this block fires.

    False means the central runner does not reach it. None means the guard
    could not be decided, which the precheck treats as a skip it must report.
    """
    sites = []
    if not reached:
        return [False for _ in _skip_calls(stmts)]
    local = {"values": dict(env["values"]), "functions": env["functions"], "stack": env["stack"]}
    dominated = False
    for stmt in stmts:
        if dominated:
            sites.extend(False for _ in _skip_calls([stmt]))
            continue
        if isinstance(stmt, ast.Assign):
            _remember_assign(stmt, local)
            continue
        if isinstance(stmt, ast.If):
            sites.extend(_walk_skip_if(stmt, local))
            if _eval_skip_expr(stmt.test, local) is True and _contains_direct_fail(stmt.body):
                dominated = True
            continue
        if isinstance(stmt, ast.Try):
            sites.extend(_walk_skip_block(stmt.body, local))
            # A skip in an exception handler is a failed docker/postgres setup.
            # The validation runner's ordinary shards complete those fixtures.
            for handler in stmt.handlers:
                sites.extend(False for _ in _skip_calls(handler.body))
            sites.extend(_walk_skip_block(stmt.orelse, local))
            sites.extend(_walk_skip_block(stmt.finalbody, local))
            continue
        if isinstance(stmt, (ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith)):
            sites.extend(_walk_skip_block(stmt.body, local))
            continue
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call) and _dotted(
                stmt.value.func) in {"pytest.skip", "pytest.xfail"}:
            sites.append(True)
    return sites


def _walk_skip_if(stmt, env):
    condition = _eval_skip_expr(stmt.test, env)
    if condition is True:
        return _walk_skip_block(stmt.body, env)
    if condition is False:
        return _walk_skip_block(stmt.orelse, env)
    if _skip_calls(stmt.body) or _skip_calls(stmt.orelse):
        return [None]
    return []


def _decorator_skip_sites(decorators, env):
    sites = []
    for decorator in decorators:
        if not isinstance(decorator, ast.Call):
            continue
        name = _dotted(decorator.func)
        if name == "pytest.mark.skip" or name == "pytest.mark.xfail" and not decorator.args:
            sites.append(True)
        elif name in {"pytest.mark.skipif", "pytest.mark.xfail"} and decorator.args:
            condition = _eval_skip_expr(decorator.args[0], env)
            sites.append(None if condition is _SKIP_UNKNOWN else bool(condition))
    return sites


def _module_mark_sites(tree, env):
    sites = []
    for stmt in tree.body:
        if not isinstance(stmt, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "pytestmark"
                   for target in stmt.targets):
            continue
        value = stmt.value
        marks = value.elts if isinstance(value, (ast.List, ast.Tuple)) else [value]
        sites.extend(_decorator_skip_sites(marks, env))
    return sites


def _fixture_names(function):
    names = [arg.arg for arg in function.args.args if arg.arg not in {"self", "cls"}]
    for decorator in function.decorator_list:
        if isinstance(decorator, ast.Call) and _dotted(decorator.func) == "pytest.mark.usefixtures":
            names.extend(arg.value for arg in decorator.args
                         if isinstance(arg, ast.Constant) and isinstance(arg.value, str))
    return names


def _autouse(function):
    for decorator in function.decorator_list:
        if not isinstance(decorator, ast.Call) or _dotted(decorator.func) != "pytest.fixture":
            continue
        for keyword in decorator.keywords:
            if (keyword.arg == "autouse" and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True):
                return True
    return False


def _index_functions(tree):
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name not in found:
            found[node.name] = node
    return found


def _reachable_functions(seeds, functions):
    queue = list(seeds)
    queue.extend(function for function in functions.values() if _autouse(function))
    seen = set()
    ordered = []
    while queue:
        function = queue.pop()
        if function.name in seen:
            continue
        seen.add(function.name)
        ordered.append(function)
        for name in _fixture_names(function):
            if name in functions:
                queue.append(functions[name])
        for node in ast.walk(function):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                callee = functions.get(node.func.id)
                if callee is not None:
                    queue.append(callee)
    return ordered


def central_runner_observes_skip(source, nodeid):
    """Whether the validation runner still skips or xfails this catalog case.

    That runner is Linux, root, and GitHub Actions, with Docker, nginx, and the
    yueboard schema checkout. XRAY_PROBE_TEST_BIN is unset, so an opt-in native
    probe still skips. A pinned image that a test only inspects is absent, so
    that skip still happens. Skips that require a missing docker binary, a
    non-root user, or a missing schema do not. GitHub Actions turns the locale
    image guard into a failure rather than a skip. Join never sees the skips
    this function rejects, so a stale catalog row is not a release blocker.
    """
    if not isinstance(source, str) or not source:
        return True
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return True
    functions = _index_functions(tree)
    env = {"values": {}, "functions": functions, "stack": set()}
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            _remember_assign(stmt, env)
    test_name = nodeid.split("::")[-1].split("[", 1)[0]
    test = functions.get(test_name)
    if test is None:
        return True
    sites = _module_mark_sites(tree, env)
    for function in _reachable_functions([test], functions):
        sites.extend(_decorator_skip_sites(function.decorator_list, env))
        sites.extend(_walk_skip_block(function.body, env))
    return any(site is not False for site in sites)


def _ordinary_blobs(bound, nodeid):
    found = set()
    blob = _case_blob(bound["baseline"]["cases"].get(nodeid))
    if blob:
        found.add(blob)
    for key in ORDINARY_BINDING_KEYS:
        blob = _case_blob(bound[key].get(nodeid))
        if blob:
            found.add(blob)
    return found


def _retired_blob_admitted(bound, nodeid, live):
    retirement = bound.get("retirement")
    sealed = bound["sealed_baseline"]["cases"].get(nodeid)
    if retirement is None or not isinstance(sealed, dict):
        return False
    if nodeid not in retirement.get("surviving_ids", []):
        return False
    sealed_blob = sealed.get("module_blob")
    if live == sealed_blob:
        return True
    return (live == RETIRED_HOST_SECOND_AFTER_BLOB and nodeid not in RETIRED_HOST_SECOND_IDS
            and sealed_blob == RETIRED_HOST_AFTER_BLOB)


def _source_of(sources, module):
    if callable(sources):
        return sources(module)
    if isinstance(sources, dict):
        return sources.get(module)
    return None


def skip_blob_mismatch_lines(bound, live_blobs, sources):
    """Lines for catalog skips whose live module blob join would reject.

    Reviewed cases and collection skips are exact: the evidence join compares
    those blobs whenever the file is still in the tree. Ordinary and retired-host
    rows are reported only when the central runner still emits that skip.
    """
    live_blobs = live_blobs if isinstance(live_blobs, dict) else {}
    grouped = {}

    def add(module, old, new, nodeid):
        row = grouped.setdefault(module, {"olds": set(), "new": new, "ids": set()})
        if isinstance(old, str) and old:
            row["olds"].add(old)
        row["ids"].add(nodeid)

    for module, row in bound["baseline"].get("collection_skips", {}).items():
        live = live_blobs.get(module)
        expected = _case_blob(row)
        if live is None or expected is None or live == expected:
            continue
        add(module, expected, live, module + "::collection")
    reviewed = bound["reviewed"].get("cases", {})
    for nodeid, case in reviewed.items():
        module = nodeid.split("::", 1)[0]
        live = live_blobs.get(module)
        expected = _case_blob(case)
        if live is None or expected is None or live == expected:
            continue
        add(module, expected, live, nodeid)
    ordinary_ids = set(bound["baseline"]["cases"])
    for key in ORDINARY_BINDING_KEYS:
        ordinary_ids.update(bound[key])
    retirement = bound.get("retirement")
    for nodeid in ordinary_ids:
        if not isinstance(nodeid, str) or "::" not in nodeid or nodeid in reviewed:
            continue
        module = nodeid.split("::", 1)[0]
        live = live_blobs.get(module)
        if live is None or module == NEZHA_RETIRED_MODULE:
            continue
        if retirement is not None and module == RETIRED_HOST_MODULE:
            if _retired_blob_admitted(bound, nodeid, live):
                continue
            accepted = set()
            sealed_blob = _case_blob(bound["sealed_baseline"]["cases"].get(nodeid))
            if sealed_blob:
                accepted.add(sealed_blob)
        else:
            accepted = _ordinary_blobs(bound, nodeid)
        if live in accepted:
            continue
        source = _source_of(sources, module)
        if source is not None and not central_runner_observes_skip(source, nodeid):
            continue
        old = ",".join(sorted(accepted))
        add(module, old, live, nodeid)
    lines = []
    for module in sorted(grouped):
        row = grouped[module]
        old = ",".join(sorted(row["olds"])) if row["olds"] else "none"
        shown = ", ".join(sorted(row["ids"]))
        lines.append(f"{module}  {old} -> {row['new']}  ({shown})")
    return lines


def skip_blob_report(value, sources, *, policy=None):
    """Bind skips with join's successor order, then list blob mismatches."""
    prepare = prepare_skip_bindings if policy is None else policy.prepare_skip_bindings
    bound = prepare(
        value, {"obligations": {}}, require_native=False, check_shared_inputs=False)
    blobs = value.get("skip_module_blobs") if isinstance(value, dict) else {}
    return skip_blob_mismatch_lines(bound, blobs if isinstance(blobs, dict) else {}, sources)


def load_policy_module(ci_revision, checkout=None):
    """Return this module, or pytest-shards.py as of one historical ci revision.

    The checked-out baseline JSON is what join reads. A historical script is
    executed with this checkout's file path so those seals stay the current
    ones, while its successor functions stay the ones that revision shipped.
    Helper functions that did not exist yet are installed into that module so
    both paths call one binder. ``checkout`` defaults to this repository. A
    revision this clone does not contain is an input error.
    """
    if ci_revision in (None, ""):
        return sys.modules[__name__]
    require(isinstance(ci_revision, str) and SHA.fullmatch(ci_revision),
            "skip-blob-precheck requires an exact ci revision")
    repo = ROOT if checkout is None else checkout
    try:
        source = git(repo, "show", f"{ci_revision}:scripts/pytest-shards.py")
    except subprocess.CalledProcessError as error:
        raise ValueError("historical pytest-shards policy is not in this clone") from error
    path = Path(tempfile.mkdtemp(prefix="skip-blob-policy-")) / "pytest-shards.py"
    path.write_bytes(source)
    module = types.ModuleType("skip_blob_policy_" + ci_revision[:12])
    module.__file__ = str(Path(__file__).resolve())
    module.__dict__["__file__"] = module.__file__
    try:
        exec(compile(source, str(path), "exec"), module.__dict__)
    except SyntaxError as error:
        raise ValueError("historical pytest-shards policy is unreadable") from error
    if "prepare_skip_bindings" not in module.__dict__:
        module.__dict__["inspect"] = inspect
        for name in _POLICY_HELPERS:
            exec(inspect.getsource(globals()[name]), module.__dict__)
    return module


def _read_ops_module(checkout, revision, module):
    if not safe_module(module):
        return None
    try:
        return git(checkout, "show", f"{revision}:{module}").decode()
    except subprocess.CalledProcessError:
        return None
    except UnicodeDecodeError:
        return None


def skip_blob_precheck(checkout, revision, *, ci_revision=None):
    """Compare one ops tree's test-module blobs with the admitted skip seals."""
    require(isinstance(revision, str) and SHA.fullmatch(revision),
            "skip-blob-precheck requires an exact ops revision")
    policy = load_policy_module(ci_revision) if ci_revision else None
    if policy is None:
        bound = source_evidence.optional(checkout, revision)
        if bound is not None:
            files = tree_inputs(checkout, revision)
            source_evidence.validate_baseline(bound, {p: blob for p, (_, blob) in files.items()})
            return []
    pin_is_ancestor = (release_pin_is_ancestor if policy is None
                       else policy.release_pin_is_ancestor)
    files = tree_inputs(checkout, revision)
    blobs = {path: blob for path, (mode, blob) in files.items() if safe_module(path)}
    value = {
        "skip_module_blobs": blobs,
        "source_revision": revision,
        "pin_is_ancestor": pin_is_ancestor(checkout, revision),
    }
    record = load_ops_skip_evidence(checkout, revision)
    if record is not None:
        value["ops_skip_evidence"] = record
    cache = {}

    def sources(module):
        if module not in cache:
            cache[module] = _read_ops_module(checkout, revision, module)
        return cache[module]

    return skip_blob_report(value, sources, policy=policy)


def skip_blob_precheck_command(args):
    """Read-only precheck. Exit 1 on a skip-blob miss, 2 on a usage or git error."""
    revision = getattr(args, "ops_rev", None)
    ci_revision = getattr(args, "ci_rev", None)
    checkout = getattr(args, "ops_checkout", None)
    if not isinstance(revision, str) or not SHA.fullmatch(revision):
        print("skip-blob-precheck: --ops-rev must be a 40-character commit", file=sys.stderr)
        return 2
    if ci_revision not in (None, "") and not (isinstance(ci_revision, str) and SHA.fullmatch(ci_revision)):
        print("skip-blob-precheck: --ci-rev must be a 40-character commit", file=sys.stderr)
        return 2
    if not isinstance(checkout, Path) or not checkout.is_dir():
        print("skip-blob-precheck: --ops-checkout is not a directory", file=sys.stderr)
        return 2
    try:
        lines = skip_blob_precheck(checkout, revision, ci_revision=ci_revision or None)
    except subprocess.CalledProcessError:
        print("skip-blob-precheck: git could not read the ops checkout", file=sys.stderr)
        return 2
    except (EvidenceUnavailable, ValueError, OSError) as error:
        print("skip-blob-precheck: " + str(error), file=sys.stderr)
        return 2
    if lines:
        print("\n".join(lines))
        return 1
    print("skip-blob-precheck ok")
    return 0

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
    join_cli.add_argument("--source", type=Path)
    export_cli = sub.add_parser("export-source-baseline")
    export_cli.add_argument("--source", type=Path, required=True)
    export_cli.add_argument("--revision", required=True)
    baseline_cli = sub.add_parser("generate-skip-baseline")
    for key in ("source", "events", "collection-xml", "collection-events"):
        baseline_cli.add_argument("--" + key, type=Path, required=True)
    for key in ("revision", "collection-revision", "collection-at"):
        baseline_cli.add_argument("--" + key, required=True)
    retirement_cli = sub.add_parser("generate-retired-host-baseline")
    for key in ("predecessor", "source"):
        retirement_cli.add_argument("--" + key, type=Path, required=True)
    retirement_cli.add_argument("--revision", required=True)
    precheck_cli = sub.add_parser(
        "skip-blob-precheck",
        help="compare admitted skip module blobs with one ops revision")
    precheck_cli.add_argument("--ops-checkout", type=Path, required=True)
    precheck_cli.add_argument("--ops-rev", required=True)
    precheck_cli.add_argument("--ci-rev")
    args = parser.parse_args()
    if args.command == "skip-blob-precheck":
        return skip_blob_precheck_command(args)
    try:
        if args.command == "plan":
            result = plan(args.source, read_json(args.context), args.shards, args.serial_module)
        elif args.command == "aggregate":
            result = aggregate(read_json(args.plan), args.reference, args.shard)
        elif args.command == "expand":
            result = expand(read_json(args.targets), args.source, args.board,
                            args.runner, args.capacity, args.shards)
        elif args.command == "export-source-baseline":
            result = export_source_baseline(args.source, args.revision)
        elif args.command == "generate-retired-host-baseline":
            result = generate_retired_host_baseline(args.predecessor, args.source, args.revision)
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
                          args.expected_sha, args.source)
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        if args.command == "expand":
            from admission_diagnostics import rejection
            rejection(str(error))
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
