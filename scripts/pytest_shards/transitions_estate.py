"""Reviewed case, site, estate and retired-host baseline transitions."""
from __future__ import annotations

import json
import re
import subprocess

from .config import (
    CASE_FILE_TRANSITION_SHA256,
    ESTATE_ADDED_INPUT,
    ESTATE_INPUT_PATHS,
    RETIRED_HOST_AFTER_BLOB,
    RETIRED_HOST_BEFORE_BLOB,
    RETIRED_HOST_KEY,
    RETIRED_HOST_MODULE,
    RETIRED_HOST_PRIOR_SHA256,
    SHA,
    SITE_LOCK_INPUT,
    TEMPLATE_WRITER_BEFORE_BLOB,
    TEMPLATE_WRITER_RETIREMENT,
)
from .support import (
    RETIRED_HOST_IDS,
    _brand,
    encoded,
    git,
    read_json,
    require,
    safe_module,
    sha,
    tree_inputs,
)
from .transitions_native import reviewed_bot_packaging_transition
from .transitions_relay import (
    reviewed_current_skip_transition,
    reviewed_relay_meter_module_transition,
    reviewed_relay_metrics_module_transition,
    reviewed_relay_preservation_module_transition,
    reviewed_relay_skip_module_transition,
    reviewed_skip_module_transition,
)


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


def _require_case_file_identity(record, original):
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


def _admit_case_file_updates(updates, effective, module_blob, successors, files):
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


def _admit_case_file_additions(additions, module_blob, successors, files):
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
    _require_case_file_identity(record, original)
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
    _admit_case_file_updates(updates, effective, module_blob, successors, files)
    _admit_case_file_additions(additions, module_blob, successors, files)
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
        "host": _brand.RETIRED_MINI_PRIMARY_HOST,
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
