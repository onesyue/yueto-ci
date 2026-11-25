"""Admit the reviewed shared-input map for one source revision."""
from __future__ import annotations

import json
import re

from .config import (
    AUDIT_LOCK_INPUT,
    BOT_PACKAGING_INPUT,
    COLLECTION_SHUFFLE_INPUT,
    ESTATE_ADDED_INPUT,
    HANG_GUARD_INPUT,
    NATIVE_INPUTS,
    NATIVE_INPUT_CHAIN,
    SHA,
    SITE_LOCK_INPUT,
)
from .support import encoded, require, sha
from .transitions_estate import (
    admit_retired_template_writer,
    reviewed_estate_input_transition,
    reviewed_site_lock_transition,
)
from .transitions_native import (
    required_native_inputs,
    reviewed_audit_lock_transition,
    reviewed_bot_packaging_transition,
    reviewed_collection_shuffle_transition,
    reviewed_hang_guard_input_transition,
    reviewed_npm_security_transition,
    reviewed_ops_packaging_transition,
    reviewed_runtime_dependency_transition,
    reviewed_tornado66_dependency_transition,
)
from .transitions_pr import (
    admit_first_native_helper,
    admit_miniapp_membership,
    admit_native_protocol_helper,
    admit_p015_offline_helper,
    admit_pr_shared_inputs,
    admit_reviewed_pr_inputs,
)
from .transitions_relay import (
    reviewed_audit_dependency_transition,
    reviewed_relay_skip_module_transition,
    reviewed_scanner_input_transition,
    reviewed_skip_module_transition,
    reviewed_w85_observability_transition,
    reviewed_zod_lock_transition,
)


def _require_reviewed_blob_change(change, current, modes, path, message):
    require(isinstance(change, dict) and set(change) == {
        "before_blob", "after_blob", "mode",
    } and all(isinstance(change[k], str) and SHA.fullmatch(change[k])
              for k in ("before_blob", "after_blob"))
            and change["before_blob"] == current.get(path)
            and change["before_blob"] != change["after_blob"]
            and change["mode"] == modes.get(path) == "100644",
            message)


def _append_blob_successor(changes, modes, accepted, message):
    successor = dict(accepted[-1])
    for path, change in changes.items():
        _require_reviewed_blob_change(change, successor, modes, path, message)
        successor[path] = change["after_blob"]
    accepted.append(successor)


def _require_historical_input_predecessors(baseline, record, python_record, security_record,
                                           miniapp_record):
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


def _admit_shared_input_record(record, original, expected, files, common):
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
    return modes, effective, restored


def _admit_python_input_record(python_record, record, restored, effective, modes):
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
        _require_reviewed_blob_change(
            change, effective, modes, changed_path, "unreviewed Python input blob or mode")
        converted[changed_path] = change["after_blob"]
    return converted


def _admit_frontend_security_record(security_record, restored, converted, modes, prior_chain):
    require(set(security_record) == {
        "schema", "original_baseline_sha256", "prior_transition_chain_sha256",
        "source_before", "source_after", "independent_review_sha256",
        "source_freeze_sha256", "path", "before_blob", "after_blob", "mode",
    } and type(security_record["schema"]) is int
            and security_record["schema"] == 1,
            "invalid frontend security transition")
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
    return converted | {path: security_record["after_blob"]}


def _admit_miniapp_security_record(miniapp_record, security_record, restored, secured, modes,
                                   prior_chain):
    require(set(miniapp_record) == {
        "schema", "original_baseline_sha256", "prior_transition_chain_sha256",
        "source_before", "source_after", "independent_review_sha256",
        "source_freeze_sha256", "path", "before_blob", "after_blob", "mode",
    } and type(miniapp_record["schema"]) is int
            and miniapp_record["schema"] == 1,
            "invalid MiniApp security transition")
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
    return secured | {path: miniapp_record["after_blob"]}


def _extend_shared_input_chain(record, python_record, security_record, miniapp_record,
                               original, expected, accepted, files, common):
    modes, effective, restored = _admit_shared_input_record(
        record, original, expected, files, common)
    accepted.append(effective)
    if python_record is not None:
        converted = _admit_python_input_record(
            python_record, record, restored, effective, modes)
        accepted.append(converted)
        if security_record is not None:
            prior_chain = {"reviewed_shared_input_transition": record,
                           "reviewed_python_input_transition": python_record}
            secured = _admit_frontend_security_record(
                security_record, restored, converted, modes, prior_chain)
            accepted.append(secured)
            if miniapp_record is not None:
                prior_chain["reviewed_frontend_security_transition"] = security_record
                accepted.append(_admit_miniapp_security_record(
                    miniapp_record, security_record, restored, secured, modes, prior_chain))
    return modes


def _admit_w85_inputs(w85_record, miniapp_record, modes, accepted):
    require(miniapp_record is not None
            and w85_record["source_before"] == miniapp_record["source_after"],
            "W8.5 input transition requires its MiniApp predecessor")
    changes = w85_record["changes"]
    require(isinstance(changes, dict) and set(changes) == {"pyproject.toml", "uv.lock"},
            "unreviewed W8.5 input paths")
    _append_blob_successor(changes, modes, accepted, "unreviewed W8.5 input blob or mode")


def _admit_observability_inputs(observability_record, w85_record, modes, accepted):
    require(w85_record is not None
            and observability_record["source_before"] == w85_record["source_after"]
            and observability_record["source_before"] != observability_record["source_after"],
            "W8.5 observability transition requires its W8.5 predecessor")
    changes = observability_record["changes"]
    require(isinstance(changes, dict) and set(changes) == {"requirements-observability.txt"},
            "unreviewed W8.5 observability input paths")
    _append_blob_successor(
        changes, modes, accepted, "unreviewed W8.5 observability input blob or mode")


def _admit_audit_dependency_inputs(audit_record, observability_record, modes, accepted):
    require(observability_record is not None
            and audit_record["source_before"] == observability_record["source_after"]
            and audit_record["source_before"] != audit_record["source_after"],
            "audit dependency transition requires its observability predecessor")
    changes = audit_record["changes"]
    require(isinstance(changes, dict) and set(changes) == {"pyproject.toml", "uv.lock"},
            "unreviewed audit dependency input paths")
    _append_blob_successor(
        changes, modes, accepted, "unreviewed audit dependency input blob or mode")


def _admit_zod_lock_inputs(zod_record, audit_record, modes, accepted):
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
    _append_blob_successor(changes, modes, accepted, "unreviewed zod lock input blob or mode")


def _admit_scanner_input(scanner_record, zod_record, baseline, accepted):
    require(zod_record is not None, "scanner input transition requires its zod predecessor")
    changes = scanner_record["changes"]
    path = "tests/_shell_early_exit_pipes.py"
    require(isinstance(changes, dict) and set(changes) == {path},
            "unreviewed scanner input paths")
    change = changes[path]
    modes = baseline["reviewed_shared_input_transition"]["common_input_modes"]
    _require_reviewed_blob_change(
        change, accepted[-1], modes, path, "unreviewed scanner input blob or mode")
    accepted.append(accepted[-1] | {path: change["after_blob"]})


def _reject_unaccepted_shared_inputs(common, accepted):
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


def _rewind_npm_security(baseline, security, common, files, source_revision, estate_successor_of):
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
    return common, files


def _rewind_collection_shuffle(baseline, shuffle, common, files, source_revision,
                               estate_successor_of):
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
    return common, files


def _strip_required_native_inputs(required, common, files):
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
    return common, files


def _rewind_hang_guard(hang, common, files, source_revision, estate_successor_of, record):
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
    return common, files


def _rewind_named_successor(seal, path, common, files, source_revision, estate_successor_of,
                            record, admit_message, mode_message):
    if seal is not None and common.get(path) == seal["changes"][path]["after_blob"]:
        change = seal["changes"][path]
        require(ESTATE_ADDED_INPUT in common and isinstance(source_revision, str)
                and source_revision != record["source_after"]
                and estate_successor_of == record["source_after"],
                admit_message)
        if files is not None:
            require(files.get(path) == (change["mode"], change["after_blob"]),
                    mode_message)
            files = dict(files) | {path: (change["mode"], change["before_blob"])}
        common = dict(common) | {path: change["before_blob"]}
    return common, files


def _rewind_ops_packaging(packaging, common, files, source_revision, estate_successor_of, record):
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
    return common, files


def _rewind_tornado_dependencies(tornado, common, files, source_revision, estate_successor_of,
                                 record):
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
    return common, files


def _rewind_runtime_dependencies(runtime, common, files, source_revision, estate_successor_of,
                                 record):
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
    return common, files


def _admit_sealed_estate_successor(original, common, files, source_revision, estate_successor_of,
                                   record, changes):
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
    common, files = _rewind_npm_security(
        baseline, security, common, files, source_revision, estate_successor_of)
    baseline, shuffle = reviewed_collection_shuffle_transition(baseline)
    common, files = _rewind_collection_shuffle(
        baseline, shuffle, common, files, source_revision, estate_successor_of)
    # The complete existing admission chain still consumes every other input.
    _, packaging = reviewed_ops_packaging_transition(baseline)
    baseline, _ = required_native_inputs(baseline)
    common, files = _strip_required_native_inputs(active_required, common, files)
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
    common, files = _rewind_hang_guard(
        hang, common, files, source_revision, estate_successor_of, record)
    # Only an estate successor (ancestry proven by the planner) may carry the
    # reviewed site lock; the exact predecessor blob is then re-admitted below.
    common, files = _rewind_named_successor(
        site, SITE_LOCK_INPUT, common, files, source_revision, estate_successor_of, record,
        "site lock successor requires a proven estate successor",
        "site lock successor mode or tree changed")
    # Same rule as the site lock: only a proven estate successor may carry the
    # reviewed bot packaging blob; its exact estate after-blob is re-admitted below.
    common, files = _rewind_named_successor(
        bot, BOT_PACKAGING_INPUT, common, files, source_revision, estate_successor_of, record,
        "bot packaging successor requires a proven estate successor",
        "bot packaging successor mode or tree changed")
    common, files = _rewind_ops_packaging(
        packaging, common, files, source_revision, estate_successor_of, record)
    common, files = _rewind_tornado_dependencies(
        tornado, common, files, source_revision, estate_successor_of, record)
    common, files = _rewind_runtime_dependencies(
        runtime, common, files, source_revision, estate_successor_of, record)
    # Same rule as the site lock and bot packaging: only a proven estate successor
    # may carry the reviewed lock blob; the audit seal's after-blob is re-admitted below.
    common, files = _rewind_named_successor(
        lock, AUDIT_LOCK_INPUT, common, files, source_revision, estate_successor_of, record,
        "audit lock successor requires a proven estate successor",
        "audit lock successor mode or tree changed")
    return _admit_sealed_estate_successor(
        original, common, files, source_revision, estate_successor_of, record, changes)


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
    _require_historical_input_predecessors(
        baseline, record, python_record, security_record, miniapp_record)
    if record is not None:
        modes = _extend_shared_input_chain(
            record, python_record, security_record, miniapp_record,
            original, expected, accepted, files, common)
    if w85_record is not None:
        _admit_w85_inputs(w85_record, miniapp_record, modes, accepted)
    if observability_record is not None:
        _admit_observability_inputs(observability_record, w85_record, modes, accepted)
    if audit_record is not None:
        _admit_audit_dependency_inputs(audit_record, observability_record, modes, accepted)
    if zod_record is not None:
        _admit_zod_lock_inputs(zod_record, audit_record, modes, accepted)
    if scanner_record is not None:
        _admit_scanner_input(scanner_record, zod_record, baseline, accepted)
    _reject_unaccepted_shared_inputs(common, accepted)
