"""Collect reference parts and inspect one shard session."""
from __future__ import annotations

import concurrent.futures
import json
import os
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath

from .config import FILES, LOG_LINE_LIMIT
from .skip_baseline import collection_skips
from .support import read_json, require, runner_context, sha
from .timing import load_timing


def _require_evidence_directory(directory):
    require(directory.is_dir() and not directory.is_symlink(), "invalid evidence directory")
    require(not (directory / "rejected.json").exists()
            and not (directory / "rejected.json").is_symlink(), "rejected execution evidence")
    for name in FILES:
        require((directory / name).is_file() and not (directory / name).is_symlink(),
                f"missing or symlink evidence: {name}")


def _selection_plan(selection, value, assignment):
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
    return reference, collect_only, modules, role


def _normalize_pytest_argv(argv, collect_only, reference, modules):
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
    return argv, has_xml


def _require_run_identity(metadata, value, argv):
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
    return actual_runner


def _require_session_events(directory):
    rows = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
    require(all(isinstance(row, dict) for row in rows), "invalid event record")

    def one(event):
        selected = [r for r in rows if r.get("event") == event]
        require(len(selected) == 1, f"missing or duplicate {event}")
        return selected[0]

    require(rows and rows[0].get("event") == "start"
            and rows[-1].get("event") == "finish", "absent session boundary")
    return (
        rows,
        one("start"),
        one("finish"),
        one("session_identity"),
        one("session_timing"),
        one("collection_timing"),
        one("collection_corpus"),
    )


def _require_bound_session(metadata, session, timing, collection, corpus, rows):
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


def _require_corpus(corpus):
    nodeids = corpus.get("nodeids")
    require(corpus.get("scope") == "controller_selected" and isinstance(nodeids, list)
            and all(isinstance(n, str) for n in nodeids)
            and len(nodeids) == len(set(nodeids)) and corpus.get("count") == len(nodeids)
            and corpus.get("ordered_nodeids_sha256")
            == sha(json.dumps(nodeids, ensure_ascii=False).encode()),
            "invalid selected corpus")
    return nodeids


def _require_process_result(directory, collect_only, nodeids, reference, rows, terminal, timing,
                            expected_empty):
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
    return rc, expected_rc, begin, end


def inspect_session(directory, value, assignment, *, expected_empty=False):
    """Validate immutable invocation binding before consuming passive case evidence."""
    _require_evidence_directory(directory)
    metadata = read_json(directory / "metadata.json")
    selection = read_json(directory / "selection.json")
    reference, collect_only, modules, role = _selection_plan(selection, value, assignment)
    argv, has_xml = _normalize_pytest_argv(
        selection["pytest_argv"], collect_only, reference, modules)
    actual_runner = _require_run_identity(metadata, value, argv)
    rows, start, terminal, session, timing, collection, corpus = _require_session_events(directory)
    _require_bound_session(metadata, session, timing, collection, corpus, rows)
    nodeids = _require_corpus(corpus)
    allowed = set(value["modules"]) if reference else set(modules)
    require(all(n.split("::", 1)[0] in allowed for n in nodeids),
            "collected case outside assigned modules")
    rc, expected_rc, begin, end = _require_process_result(
        directory, collect_only, nodeids, reference, rows, terminal, timing, expected_empty)
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


def print_reference_listing(part_id, listing, returncode):
    """Echo a bounded summary; the whole listing is kept as part evidence."""
    lines = listing.read_text(errors="replace").splitlines()
    shown = lines[-40:] if returncode not in (0, 5) else lines[-1:]
    for line in shown:
        clipped = line if len(line) <= LOG_LINE_LIMIT else (
            line[:LOG_LINE_LIMIT] + f"... [{len(line)} chars, full text in evidence]")
        print(f"[{part_id}] {clipped}", flush=True)


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
    # The full node-id listing stays in the part's evidence, not the job log:
    # the hosted runner masks secrets per log line in super-linear time, and a
    # single ~1 MiB parametrized id held this step for 25+ minutes after every
    # pytest process had already exited in under a minute.
    listing = part / "pytest-collect-stdout.txt"
    (part / "pytest-start-unix-ns.txt").write_text(str(time.time_ns()))
    with listing.open("wb") as sink:
        result = subprocess.run(argv, cwd=source, env=env, check=False,
                                stdout=sink, stderr=subprocess.STDOUT)
    (part / "pytest-finish-unix-ns.txt").write_text(str(time.time_ns()))
    (part / "pytest-exit-code.txt").write_text(str(result.returncode))
    print_reference_listing(assignment["id"], listing, result.returncode)
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


def collect_reference_parts(expected, source, output, site, actual_runner, timing, only_id=None):
    """Collect-only once per module assignment.

    Each part is its own interpreter. That is not xdist: workers there reuse
    one process and the Ops import path then leaks across files. The workflow
    schedules `reference-<assignment>` as its own job. Collecting every
    assignment in one runner stalled for about half an hour after each pytest
    had already finished in under a minute. `only_id=None` still collects the
    whole plan so a test can compare that oracle with the split union.
    """
    assignments = expected["assignments"]
    if only_id is not None:
        assignments = [item for item in assignments if item["id"] == only_id]
        require(len(assignments) == 1, "unknown reference part")
    limit = 1 if only_id is not None else min(len(assignments), os.cpu_count() or 2)
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
