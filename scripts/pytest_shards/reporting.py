"""Aggregate shard sessions and check the admission envelope."""
from __future__ import annotations

from .collection import inspect_session
from .config import SKIP_BASELINE
from .sharding import validate_plan
from .skip_baseline import collection_skips, skip_baseline
from .support import (
    ROOT,
    encoded,
    read_json,
    require,
    role_order,
    runner_summary,
    sha,
    source_evidence,
    workflow_identity,
)


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
                require(value.get("validation_only") is None or value.get("validation_only") is True,
                        "validation_only must be absent or true")
                if value.get("validation_only") is True:
                    require(value.get("admission_rule") is None,
                            "validation-only does not carry a release admission rule")
                elif value.get("admission_rule") == "signed-default-branch":
                    require(value.get("estate_successor_of") is None
                            and value.get("template_writer_retired_at") is None
                            and value.get("pin_is_ancestor") is not True,
                            "signed admission does not carry a seal marker")
                else:
                    require(False,
                            "shared-input seals are retired; admit a signed default-branch commit")
            require(planned["source_revision"] == value["source_revision"]
                    and planned["context"]["board_revision"] == value["board_revision"]
                    and all(planned["context"][k] == v for k, v in value["identity"].items()),
                    "ordinary plan identity differs")
            require([m.get("ops_role") for m in ops]
                    == role_order(planned),
                    "missing or unexpected selected Ops roles")
    return value
