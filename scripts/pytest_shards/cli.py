"""Plan Ops jobs, execute the source-owned selection and strictly join evidence.

The ordinary corpus verdict alone never supplies complete release acceptance.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import time
from pathlib import Path, PurePosixPath

from .collection import collect_reference_parts, inspect_session, join_reference_collections, shard_pythonpath
from .config import NATIVE_TARGETS, SHA, SKIP_BASELINE
from .reporting import aggregate, envelope
from .sharding import plan, validate_plan
from .skip_baseline import generate_skip_baseline
from .policy_history import skip_blob_precheck_command
from .skip_bindings import admit_skips, load_ops_skip_evidence, prepare_skip_bindings
from .support import (
    ROOT,
    admit_signed_default_branch,
    git,
    read_json,
    require,
    retain_rejection,
    role_order,
    runner_context,
    runner_summary,
    safe_module,
    seal,
    serial_modules,
    sha,
    shared_inputs,
    source_evidence,
    tree_inputs,
    verify_source_evidence,
    workflow_identity,
)
from .timing import (
    detach_ordinary_weights,
    load_timing,
    load_weight_document,
    previous_ordinary_weights_command,
    publish_ordinary_weights_command,
)
from .transitions_estate import generate_retired_host_baseline


def expand(targets, source, board, runner, capacity, shards, timing=None, weights=None, *, validation_only=False):
    """Expand an exact target plan, without pytest collection or import."""
    require(isinstance(validation_only, bool), "validation_only must be boolean")
    require(type(capacity) is int and capacity > 0, "capacity must be positive")
    require(runner in ("ubuntu-24.04", "yue-local-release"), "unsupported runner")
    matrix = targets["validation_matrix"]
    require(isinstance(matrix, list) and matrix, "empty validation matrix")
    selected = [m for m in matrix if m.get("validation") == "yueops"]
    require(len(selected) <= 1, "duplicate Ops validation records")
    value = {"schema": 1, "identity": workflow_identity(), "mode": "none",
             "source_revision": None, "board_revision": board,
             "ops_plan": None, "validation_matrix": matrix}
    used_weights = None
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
            if validation_only:
                # Owner signature admits any branch. Promotion seals stay on the other path.
                source_evidence.verify_signed_commit(source, ops["ref"])
            context = value["identity"] | {
                "board_revision": board, "runner_os": os.environ.get("RUNNER_OS"),
                "runner_arch": os.environ.get("RUNNER_ARCH"),
                "runner_image": os.environ.get("ImageVersion"),
            }
            bound = None if validation_only else source_evidence.optional(source, ops["ref"])
            expected = plan(source, context, shards, serial_modules(source),
                            weights=weights, timing=timing)
            used_weights = detach_ordinary_weights(expected)
            require(expected["source_revision"] == ops["ref"], "planned source checkout differs")
            if validation_only:
                files = tree_inputs(source, ops["ref"])
                value["validation_only"] = True
                value.update(mode="sharded", ops_plan=expected,
                             common_inputs=shared_inputs(source, ops["ref"]),
                             skip_baseline_sha256=sha((ROOT / SKIP_BASELINE).read_bytes()),
                             skip_module_blobs={p: files[p][1] for p in expected["modules"]})
            elif bound is not None:
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
                key=lambda row: priority.get(
                    row.get("ops_role"),
                    1 if isinstance(row.get("ops_role"), str)
                    and row["ops_role"].startswith("reference-")
                    else 4 if row.get("ops_role") else 3))
    value["max_parallel"] = min(capacity, len(value["validation_matrix"]))
    if runner == "yue-local-release":
        value["max_parallel"] = 1
    if source is not None and isinstance(value.get("source_revision"), str):
        record = load_ops_skip_evidence(source, value["source_revision"])
        if record is not None:
            value["ops_skip_evidence"] = record
    if used_weights is not None:
        value["ordinary_weights"] = used_weights
    return seal(value, "admission_sha256")


def check_source(value, source, board):
    envelope(value)
    if value.get("validation_only") is True:
        source_evidence.verify_signed_commit(source, value["source_revision"])
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
    # The admitted exact revision is the contract identity, not a second policy pin.
    source_evidence.verify_signed_commit(board, value["board_revision"])


def execute(value, source, board, role, output, site):
    """Run exactly one actual source entry; preserve failed and empty exits."""
    check_source(value, source, board)
    require(value["mode"] == "sharded", "selection is hosted-only")
    expected = validate_plan(value["ops_plan"])
    assignments = {a["id"]: a for a in expected["assignments"]}
    part_id = role[len("reference-"):] if role.startswith("reference-") else None
    require(role == "reference" or role in assignments or part_id in assignments,
            "unknown execution role")
    current = plan(source, expected["context"],
                   sum(a["id"].startswith("ordinary-") for a in expected["assignments"]),
                   serial_modules(source),
                   weights=value.get("ordinary_weights"))
    detach_ordinary_weights(current)
    require(current == expected, "source collection inputs or assignments changed")
    actual_runner = runner_context(expected["context"], os.environ)
    require(os.environ.get("PYTEST_ADDOPTS", "") in ("", "--durations=25"),
            "unexpected pytest options")
    require(not os.environ.get("PYTEST_PLUGINS"), "unexpected pytest plugin override")
    timing = load_timing()
    timing.install(output, site)
    if role == "reference" or part_id is not None:
        return collect_reference_parts(
            expected, source, output, site, actual_runner, timing, only_id=part_id)
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
    quarantine = source / "tests/quarantine.json"
    if quarantine.is_symlink() or quarantine.exists() or os.environ.get("YUETO_SHARED_SELECTION", "[]") != "[]":
        env.update(PYTEST_PLUGINS="ops_quarantine", YUETO_OPS_TEST_SOURCE=str(source.resolve()),
                   PYTHONPATH=str(ROOT / "scripts") + os.pathsep + env["PYTHONPATH"])
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


def export_source_baseline(source, revision):
    """Migrate approved records only. New observations never create approvals."""
    files = source_evidence.tree_inputs(source, revision)
    blobs = {path: row["git_blob"] for path, row in files.items() if safe_module(path)}
    value = {"source_revision": revision, "skip_module_blobs": blobs,
             "pin_is_ancestor": False}
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
    mandatory_nodes = set()
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


def materialize_split_reference(evidence, prefix, assignments, dest):
    """Union per-assignment reference parts into the single tree aggregate reads."""
    dest.mkdir()
    (dest / "parts").mkdir()
    payloads = []
    for assignment in assignments:
        src = evidence / (prefix + "reference-" + assignment["id"])
        payload = read_json(src / "joined.json")
        require(payload.get("parts") == [assignment["id"]],
                "reference part does not match its assignment")
        shutil.copytree(src / "parts" / assignment["id"], dest / "parts" / assignment["id"])
        payloads.append(payload)
    require(len({item["invocation_id"] for item in payloads}) == len(payloads),
            "reused reference invocation")
    require(all(item.get("execution_context") == payloads[0]["execution_context"]
                for item in payloads),
            "reference part execution context differs")
    joined = join_reference_collections([
        {"assignment_id": item["parts"][0], "nodeids": item["nodeids"],
         "collection_skips": item["collection_skips"]}
        for item in payloads
    ])
    first = payloads[0]
    body = {
        "schema": 1, "assignment_id": "reference",
        "invocation_id": first["invocation_id"],
        "nodeids": joined["nodeids"],
        "collection_skips": joined["collection_skips"],
        "runner_context": first["runner_context"],
        "execution_context": first["execution_context"],
        "junit_sha256": sha(json.dumps(joined, sort_keys=True).encode()),
        "parts": [item["parts"][0] for item in payloads],
    }
    (dest / "joined.json").write_text(json.dumps(body) + "\n")
    return dest


def join(value, evidence, validation_result, expected_sha, source=None):
    envelope(value)
    if value.get("validation_only") is True:
        require(source is not None, "validation_only join requires the source checkout")
        source_evidence.verify_signed_commit(source, value["source_revision"])
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
    assignment_ids = [a["id"] for a in expected["assignments"]]
    legacy = ["reference", *assignment_ids, "native"]
    split = [*(f"reference-{assignment}" for assignment in assignment_ids),
             *assignment_ids, "native"]
    require(evidence.is_dir() and not evidence.is_symlink(), "missing evidence directory")
    names = sorted(p.name for p in evidence.iterdir())
    legacy_names = sorted(prefix + role for role in legacy)
    split_names = sorted(prefix + role for role in split)
    require(names in (legacy_names, split_names), "missing or unexpected evidence roles")
    native_directory = evidence / (prefix + "native")
    native = read_json(native_directory / "native.json")
    expected_native = (native_execution_context(value, native_directory)
                       | {"status": "success"} | native_receipts(value, native_directory))
    seal(expected_native, "native_sha256")
    require(native == expected_native, "native/source gate receipt differs")
    shard_dirs = [evidence / (prefix + assignment) for assignment in assignment_ids]
    if names == legacy_names:
        result = aggregate(expected, evidence / (prefix + "reference"), shard_dirs)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            reference = materialize_split_reference(
                evidence, prefix, expected["assignments"], Path(tmp) / "reference")
            result = aggregate(expected, reference, shard_dirs)
    runners = {r["assignment_id"]: r["runner_context"]
               for r in [result["reference"], *result["shards"]]}
    runners["native"] = native["runner_context"]
    return {"schema": 1, "status": "VALIDATION_MATRIX_COMPLETE", "mode": "sharded",
            "admission_sha256": value["admission_sha256"], "ordinary": result,
            "skip_admission": admit_skips(value, result, native, source),
            "runner_observations": runner_summary(expected["context"], runners),
            "native_and_source_gates": native, "host_linux_skip_policy": "ROOT_GATE_UNCHANGED"}


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
    expand_cli.add_argument("--validation-only", action="store_true")
    expand_cli.add_argument("--timing", type=Path)
    expand_cli.add_argument("--weights", type=Path)
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
    weights_cli = sub.add_parser("previous-ordinary-weights")
    weights_cli.add_argument("--output", type=Path, required=True)
    weights_cli.add_argument("--timing-output", type=Path, required=True)
    publish_cli = sub.add_parser("publish-ordinary-weights")
    publish_cli.add_argument("--admission", type=Path, required=True)
    publish_cli.add_argument("--evidence", type=Path, required=True)
    publish_cli.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "skip-blob-precheck":
        return skip_blob_precheck_command(args)
    if args.command == "previous-ordinary-weights":
        return previous_ordinary_weights_command(args)
    if args.command == "publish-ordinary-weights":
        return publish_ordinary_weights_command(args)
    try:
        if args.command == "plan":
            result = plan(args.source, read_json(args.context), args.shards, args.serial_module)
        elif args.command == "aggregate":
            result = aggregate(read_json(args.plan), args.reference, args.shard)
        elif args.command == "expand":
            result = expand(read_json(args.targets), args.source, args.board,
                            args.runner, args.capacity, args.shards,
                            timing=args.timing,
                            weights=load_weight_document(args.weights),
                            validation_only=args.validation_only)
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
