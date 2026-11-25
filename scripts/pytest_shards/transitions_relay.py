"""Reviewed relay, scanner, lock and skip-module input transitions."""
from __future__ import annotations

import json
import re

from . import config
from .config import (
    AUDIT_DEPENDENCY_TRANSITION_SHA256,
    CURRENT_SKIP_TRANSITION_SHA256,
    RELAY_METER_MODULE_TRANSITION_SHA256,
    RELAY_METRICS_MODULE_TRANSITION_SHA256,
    RELAY_PRESERVATION_MODULE_TRANSITION_SHA256,
    RELAY_SKIP_MODULE_TRANSITION_SHA256,
    SCANNER_INPUT_TRANSITION_SHA256,
    SHA,
    SSH_SKIP_CASES,
    W85_INPUT_TRANSITION_SHA256,
    W85_OBSERVABILITY_TRANSITION_SHA256,
    ZOD_LOCK_TRANSITION_SHA256,
)
from .support import encoded, require, sha


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
    require(sha(encoded(record)) == config.SSH_SKIP_TRANSITION_SHA256,
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
