"""Bind admitted skips to reviewed successors and historical policy."""
from __future__ import annotations

import ast
import inspect
import json
import re
import subprocess

from .config import (
    BOARD139_AFTER_BLOB,
    BOARD139_BEFORE_BLOB,
    BOARD139_RENEWAL_BLOB,
    CANCELED_BACKUP_AFTER_BLOB,
    CANCELED_BACKUP_CASES_SHA256,
    CASE_SCOPE_DEPTH,
    NATIVE_TARGETS,
    NEZHA_RETIRED_MODULE,
    NEZHA_RETIREMENT_KEY,
    OPS_SKIP_EVIDENCE,
    RESTORE_DRILL_AFTER_BLOB,
    RESTORE_DRILL_BEFORE_BLOB,
    RESTORE_DRILL_CASES_SHA256,
    RETIRED_HOST_MODULE,
    SHA,
    _BINDING_KEYS,
)
from .skip_baseline import retired_host_case_admitted, skip_baseline
from .support import (
    EvidenceUnavailable,
    ROOT,
    encoded,
    git,
    require,
    safe_module,
    sha,
    source_evidence,
    tree_inputs,
)
from .transitions_estate import reviewed_case_file_transition, reviewed_estate_input_transition
from .transitions_native import (
    reviewed_i10_skip_blob_successor_transition,
    reviewed_release_skip_blob_successor_transition,
    reviewed_retired_host_transition,
    reviewed_skip_blob_successor_transition,
    skip_blob_successors,
)
from .transitions_relay import (
    reviewed_current_skip_transition,
    reviewed_relay_meter_module_transition,
    reviewed_relay_metrics_module_transition,
    reviewed_relay_preservation_module_transition,
    reviewed_relay_skip_module_transition,
    reviewed_skip_module_transition,
)


def reviewed_canceled_backup_blob_successor(baseline, value):
    """Retain canceled backup cases as unexecuted; admit only reviewed blob drift."""
    module = "tests/test_critical_key_restore_gate_mutations_20260903.py"
    after = CANCELED_BACKUP_AFTER_BLOB
    if value.get("skip_module_blobs", {}).get(module) != after:
        return baseline
    selected = {key: row for key, row in baseline["cases"].items()
                if key.startswith(module + "::")}
    require(len(selected) == 23 and sha(encoded(selected)) == CANCELED_BACKUP_CASES_SHA256,
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
    before = RESTORE_DRILL_BEFORE_BLOB
    after = RESTORE_DRILL_AFTER_BLOB
    if value.get("skip_module_blobs", {}).get(module) != after:
        return baseline
    hosted = baseline.get("reviewed_hosted", {})
    selected = {key: row for key, row in hosted.get("cases", {}).items()
                if key.startswith(module + "::")}
    require(len(selected) == 7
            and sha(encoded(selected)) == RESTORE_DRILL_CASES_SHA256
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
    before = BOARD139_BEFORE_BLOB
    after = BOARD139_AFTER_BLOB
    renewal = BOARD139_RENEWAL_BLOB
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
    """Native skip blobs are not a resealed file.

    A signed default-branch commit is admitted by its signature. Same-run
    native obligations stay on NATIVE_TARGETS. The historical signature is
    kept so a precheck can still call this without a successor JSON file.
    """
    del value, native, require_native
    return baseline


def ordinary_skip_evidence_successors(admitted, value):
    """Ops-commit evidence may move an admitted skip.

    Dated review files are not an allow-list. A missing ops-commit record
    adds no successor. A record that does not succeed an admitted skip still
    fails closed.
    """
    record = value.get("ops_skip_evidence") if isinstance(value, dict) else None
    if isinstance(record, dict):
        return _apply_ordinary_skip_record(record, admitted, value)
    return {}


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
    source = inspect.getsource(reviewed_board139_native_successor)
    module_name = "tests/test_board139_schema_acl_native_20261018.py"
    names = [name.split("::")[-1] for name in re.findall(
        r'"((?:::)?test_actual_[^"]+)"', source)]
    previous = [name for name in names if not name.startswith("test_actual_renewal_")]
    renewal_names = [name for name in names if name.startswith("test_actual_renewal_")]
    after_blob = BOARD139_AFTER_BLOB
    renewal_blob = BOARD139_RENEWAL_BLOB
    blobs = value.get("skip_module_blobs") if isinstance(value, dict) else None
    live = blobs.get(module_name) if isinstance(blobs, dict) else None
    expected = [module_name + "::" + name for name in previous]
    if live == renewal_blob:
        expected.extend(module_name + "::" + name for name in renewal_names)
    elif live not in (None, after_blob):
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
    # The first-native successor opened ops-first-native-successors.json.
    # That seal is retired. The current function is a no-op, and a historical
    # module's copy still reads the deleted file, so neither is invoked.
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

    admit_skips always calls this. skip-blob-precheck calls this only when
    the ops commit carries skip evidence, so a bare blob change is not a miss.
    """
    sealed_baseline = skip_baseline()
    _, i10_blob_record = reviewed_i10_skip_blob_successor_transition(sealed_baseline)
    _, retirement = reviewed_retired_host_transition(sealed_baseline)
    _, blob_record = reviewed_skip_blob_successor_transition(sealed_baseline)
    _, release_blob_record = reviewed_release_skip_blob_successor_transition(sealed_baseline)
    _, case_successors = reviewed_case_file_transition(sealed_baseline)
    baseline, _estate = reviewed_estate_input_transition(sealed_baseline)
    # Shared-input seals are retired. Signature admission compares the
    # checked-out tree in check_source. check_shared_inputs stays in the
    # signature so skip precheck callers do not grow a second copy.
    del check_shared_inputs
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
    admitted.update(i10_blob_successors)
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


def _case_definition_digest(source, blob, nodeid):
    """Position-free digest of one test's own definition, or None.

    The digest covers the test function (decorators and body), every
    enclosing class with its decorators, and the module's ``pytestmark``.
    Editing another test in the same module leaves it unchanged.
    """
    if source is None or not (isinstance(blob, str) and SHA.fullmatch(blob)):
        return None
    try:
        tree = ast.parse(git(source, "cat-file", "blob", blob))
    except (subprocess.CalledProcessError, SyntaxError, ValueError):
        return None
    parts = nodeid.split("::")[1:]
    if not parts:
        return None
    parts[-1] = parts[-1].split("[", 1)[0]
    chain = [ast.dump(node, include_attributes=False) for node in tree.body
             if isinstance(node, (ast.Assign, ast.AnnAssign))
             and any(isinstance(t, ast.Name) and t.id == "pytestmark"
                     for t in (node.targets if isinstance(node, ast.Assign) else [node.target]))]
    body, node = tree.body, None
    for index, name in enumerate(parts):
        kinds = ((ast.FunctionDef, ast.AsyncFunctionDef) if index == len(parts) - 1
                 else (ast.ClassDef,))
        found = [n for n in body if isinstance(n, kinds) and n.name == name]
        if len(found) != 1:
            return None
        node = found[0]
        if isinstance(node, ast.ClassDef):
            chain.append("class " + node.name + "".join(
                ast.dump(part, include_attributes=False)
                for part in (*node.decorator_list, *node.bases, *node.keywords)))
            body = node.body
    chain.append(ast.dump(node, include_attributes=False))
    return sha("\n".join(chain).encode())


def case_scope_successor(source, nodeid, current_blob, records, match):
    """Return the admitted record this skip still is, derived from source.

    A sealed skip names its whole test-module blob. When that blob moved only
    because other tests in the module changed, the case is the same case: its
    own definition digest is identical and ``match`` (same outcome and reason)
    holds. Native-mandatory modules never use this path; their cases are
    already covered by NATIVE_TARGETS.
    """
    module = nodeid.split("::", 1)[0]
    if source is None or module in NATIVE_TARGETS:
        return None
    current = _case_definition_digest(source, current_blob, nodeid)
    if current is None:
        return None
    for record in records:
        if (isinstance(record, dict) and record.get("module_blob") != current_blob
                and match(record)
                and _case_definition_digest(source, record.get("module_blob"), nodeid) == current):
            return record
    return None


def derive_prior_skips(value, source, pending):
    """Node ids whose skip was admitted at an earlier blob of their own module.

    Walks up to CASE_SCOPE_DEPTH earlier versions of each pending module in
    the candidate's own history, binds the central skip policy as it applied
    to that version, and keeps a case only when that admitted skip has the
    same outcome and reason and the case's own definition is unchanged.
    Nothing is written; no seal is added.
    """
    if source is None or not pending:
        return set()
    revision = value.get("source_revision")
    current = value.get("skip_module_blobs", {})
    remaining = {}
    for nodeid, observed in pending:
        remaining.setdefault(nodeid, observed)
    history = {}
    for module in {nodeid.split("::", 1)[0] for nodeid in remaining}:
        blobs = []
        try:
            commits = git(source, "log", "--format=%H", "-n", str(CASE_SCOPE_DEPTH * 2),
                          revision, "--", module).decode().split()
        except (subprocess.CalledProcessError, EvidenceUnavailable):
            continue
        for commit in commits:
            try:
                blob = git(source, "rev-parse", f"{commit}^:{module}").decode().strip()
            except subprocess.CalledProcessError:
                continue
            if blob != current.get(module) and blob not in blobs:
                blobs.append(blob)
        history[module] = blobs[:CASE_SCOPE_DEPTH]
    accepted = set()
    for depth in range(max(map(len, history.values()), default=0)):
        trial = dict(value, skip_module_blobs=dict(current))
        for module, blobs in history.items():
            if depth < len(blobs):
                trial["skip_module_blobs"][module] = blobs[depth]
        try:
            bound = prepare_skip_bindings(trial, {"obligations": {}}, require_native=False,
                                          check_shared_inputs=False)
        except (ValueError, EvidenceUnavailable):
            continue
        for nodeid, observed in list(remaining.items()):
            records = [bound["baseline"]["cases"].get(nodeid),
                       bound["sealed_baseline"]["cases"].get(nodeid),
                       *(bound[key].get(nodeid) for key in _BINDING_KEYS)]
            if case_scope_successor(
                    source, nodeid, observed["module_blob"], records,
                    lambda r, o=observed: (r.get("outcome"), r.get("reason"))
                    == (o["outcome"], o["reason"])) is not None:
                accepted.add(nodeid)
                del remaining[nodeid]
        if not remaining:
            break
    return accepted


def skip_has_reason(reason):
    """A skip is admitted only when pytest recorded a non-empty reason."""
    return isinstance(reason, str) and bool(reason.strip())


def _admit_skip_row(row, *, value, source, session, sealed_baseline, retirement,
                    reviewed, baseline, successors, relay_successors,
                    metrics_successors, meter_successors, preservation_successors,
                    case_successors, blob_successors, release_blob_successors,
                    i10_blob_successors, ordinary_skips, native, counts,
                    unknown, reported, case_scoped, pending):
    nodeid = row["nodeid"]
    if (row.get("outcome") not in ("skipped", "xfail")
            or not skip_has_reason(row.get("reason"))):
        unknown.append(nodeid)
        return None
    module = nodeid.split("::", 1)[0]
    require(NEZHA_RETIREMENT_KEY not in sealed_baseline or module != NEZHA_RETIRED_MODULE,
            "retired Nezha test cannot inherit a historical skip: " + nodeid)
    if retirement is not None and module == RETIRED_HOST_MODULE:
        require(retired_host_case_admitted(
                    retirement, sealed_baseline["cases"], nodeid, row,
                    value["skip_module_blobs"].get(module)),
                "retired host case or successor blob differs: " + nodeid)
        return "HISTORICAL_UNEXECUTED"
    specific = reviewed.get("cases", {}).get(nodeid)
    if specific is None:
        observed = {
            "outcome": row["outcome"], "reason": row.get("reason"),
            "module_blob": value["skip_module_blobs"].get(module),
        }
        records = (baseline["cases"].get(nodeid), successors.get(nodeid),
                   relay_successors.get(nodeid), metrics_successors.get(nodeid),
                   meter_successors.get(nodeid), preservation_successors.get(nodeid),
                   case_successors.get(nodeid), blob_successors.get(nodeid),
                   release_blob_successors.get(nodeid),
                   i10_blob_successors.get(nodeid),
                   ordinary_skips.get(nodeid), sealed_baseline["cases"].get(nodeid))
        if observed not in records[:-1]:
            if case_scope_successor(
                    source, nodeid, observed["module_blob"], records,
                    lambda r: (r.get("outcome"), r.get("reason"))
                    == (observed["outcome"], observed["reason"])) is None:
                pending.append((nodeid, observed))
                return None
            case_scoped.append(nodeid)
        disposition = "HISTORICAL_UNEXECUTED"
    else:
        current_blob = value["skip_module_blobs"].get(module)
        variant = {"when": row.get("when"), "reason": row.get("reason")}
        if (specific.get("module_blob") != current_blob
                and specific.get("outcome") == row["outcome"]
                and variant in specific.get("variants", [])
                and case_scope_successor(source, nodeid, current_blob, [specific],
                                         lambda r: True) is not None):
            specific = dict(specific, module_blob=current_blob)
            case_scoped.append(nodeid)
        matched = (reviewed.get("schema") == 1
                   and session["execution_context"] == reviewed.get("context")
                   and all(value["ops_plan"]["context"].get(k) == v
                           for k, v in reviewed["runner"].items())
                   and specific["module_blob"] == value["skip_module_blobs"].get(module)
                   and specific["outcome"] == row["outcome"]
                   and {"when": row.get("when"), "reason": row.get("reason")}
                   in specific["variants"])
        if not matched:
            # The hosted variant list is not an allow-list. A reason is enough.
            reported.append(nodeid)
            return None
        disposition = specific["disposition"]
        require(disposition in counts, "unknown reviewed skip disposition")
        if disposition == "SAME_RUN_NATIVE_REQUIRED":
            require(nodeid in native["obligations"].get(
                specific["native_target"], {}).get("passed", []),
                "ordinary skip missing exact same-run native call: " + nodeid)
    return disposition


def admit_skips(value, result, native, source=None):
    if "source_evidence" in value:
        return source_evidence.admit_skips(value["source_evidence"], value["skip_module_blobs"],
                                           result, native, set(NATIVE_TARGETS))
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
    reported = []
    case_scoped = []
    pending = []
    observed_collection = {}
    counts = {"HISTORICAL_UNEXECUTED": 0, "OWNER_CANCELED": 0,
              "SAME_RUN_NATIVE_REQUIRED": 0}
    for session in [result["reference"], *result["shards"]]:
        require(session["execution_context"] == baseline["context"],
                "skip execution context differs from baseline")
        require(isinstance(session["collection_skips"], dict) and session["junit_sha256"],
                "missing collection-skip evidence")
        for row in session["nonpassing_outcomes"]:
            disposition = _admit_skip_row(
                row, value=value, source=source, session=session,
                sealed_baseline=sealed_baseline, retirement=retirement,
                reviewed=reviewed, baseline=baseline, successors=successors,
                relay_successors=relay_successors,
                metrics_successors=metrics_successors,
                meter_successors=meter_successors,
                preservation_successors=preservation_successors,
                case_successors=case_successors, blob_successors=blob_successors,
                release_blob_successors=release_blob_successors,
                i10_blob_successors=i10_blob_successors,
                ordinary_skips=ordinary_skips, native=native, counts=counts,
                unknown=unknown, reported=reported, case_scoped=case_scoped,
                pending=pending)
            if disposition is not None:
                counts[disposition] += 1
        for module, reason in session["collection_skips"].items():
            expected = {
                "reason": reason, "module_blob": value["skip_module_blobs"].get(module),
            }
            if not skip_has_reason(reason):
                unknown.append(module)
            elif baseline["collection_skips"].get(module) != expected:
                reported.append(module)
            if session["assignment_id"] != "reference":
                require(module not in observed_collection, "duplicate collection skip")
                observed_collection[module] = reason
    require(observed_collection == result["reference"]["collection_skips"],
            "reference and shards have different collection skips")
    prior = derive_prior_skips(value, source, pending)
    for nodeid, _observed in pending:
        if nodeid in prior:
            case_scoped.append(nodeid)
            counts["HISTORICAL_UNEXECUTED"] += 1
        else:
            reported.append(nodeid)
    unknown = list(dict.fromkeys(unknown))
    require(not unknown, "skip has no reason: " + ", ".join(unknown))
    verdict = {"status": "NO_NEW_SKIPS", "baseline_sha256": value["skip_baseline_sha256"],
               "baseline_source_revision": baseline["source_revision"],
               "skips_are_passes": False, "disposition_counts": counts,
               "host_native_acceptance": "INDEPENDENT"}
    if case_scoped:
        verdict["case_scope_successors"] = sorted(set(case_scoped))
    if reported:
        verdict["reported_skips"] = sorted(set(reported))
    return verdict
