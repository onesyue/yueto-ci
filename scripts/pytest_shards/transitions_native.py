"""Reviewed native, packaging and skip-blob successor transitions."""
from __future__ import annotations

import copy
import json
import re

from .config import (
    AUDIT_LOCK_INPUT,
    BOT_PACKAGING_INPUT,
    COLLECTION_SHUFFLE_INPUT,
    COLLECTION_SHUFFLE_KEY,
    COLLECTION_SHUFFLE_TRANSITION_SHA256,
    HANG_GUARD_INPUT,
    HANG_GUARD_INPUT_TRANSITION_SHA256,
    HISTORICAL_NATIVE_INPUTS,
    I10_SKIP_BLOB_SUCCESSOR_TRANSITION_SHA256,
    NATIVE_INPUTS,
    NATIVE_INPUT_SUCCESSOR_KEY,
    NATIVE_INPUT_SUCCESSOR_SHA256,
    NEZHA_PRIOR_BASELINE_SHA256,
    NEZHA_RETIRED_MODULE,
    NEZHA_RETIREMENT_KEY,
    NEZHA_RETIRED_CASE_BLOB,
    OPS_PACKAGING_ADDED_INPUT,
    OPS_PACKAGING_INPUT,
    OPS_PACKAGING_INPUTS,
    OPS_PACKAGING_KEY,
    OPS_PACKAGING_TRANSITION_SHA256,
    RELEASE_SKIP_BLOB_SUCCESSOR_TRANSITION_SHA256,
    RETIRED_HOST_AFTER_BLOB,
    RETIRED_HOST_BEFORE_BLOB,
    RETIRED_HOST_KEY,
    RETIRED_HOST_MODULE,
    RETIRED_HOST_PRIOR_SHA256,
    RETIRED_HOST_TRANSITION_SHA256,
    RUNTIME_DEPENDENCY_INPUTS,
    SECURITY_INPUT_KEY,
    SECURITY_INPUT_PATHS,
    SECURITY_INPUT_TRANSITION_SHA256,
    SHA,
    SKIP_BLOB_SUCCESSOR_TRANSITION_SHA256,
    TORNADO66_DEPENDENCY_TRANSITION_SHA256,
)
from .support import RETIRED_HOST_IDS, ROOT, baseline_bytes, encoded, require, safe_module, sha


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
            "module_blob": NEZHA_RETIRED_CASE_BLOB,
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
