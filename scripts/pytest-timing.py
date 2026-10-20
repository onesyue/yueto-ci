#!/usr/bin/env python3
"""Install the canonical passive recorder and summarize its bounded evidence.

This tool never invokes pytest, selects tests, or supplies a release verdict.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def revision(path):
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True,
        stderr=subprocess.DEVNULL,
    ).strip()


def install(output, site):
    plugin = ROOT / "scripts/lens_report.py"
    manifest = json.loads((ROOT / "scripts/lens-report-source.json").read_text())
    if (manifest.get("schema") != 1
            or manifest.get("canonical_owner") != "yueto-workspace"
            or manifest.get("canonical_path") != "scripts/linux-lens/lens_report.py"
            or manifest.get("generated_path") != "scripts/lens_report.py"
            or plugin.is_symlink() or digest(plugin) != manifest.get("sha256")):
        raise ValueError("canonical recorder projection verification failed")
    output.mkdir(parents=True, exist_ok=False)
    source = Path.cwd()
    identity = {
        "schema": 1,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "source_revision": revision(source),
        "source_tracked_dirty": bool(subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"], cwd=source)),
        "policy_revision": revision(ROOT),
        "recorder_sha256": digest(plugin),
        "entry": "scripts/run-pytest-parallel.sh",
        "entry_sha256": digest(source / "scripts/run-pytest-parallel.sh"),
        "serial": True,
        "python": sys.version,
        "python_executable": sys.executable,
        "identity": {
            key: os.environ.get(key) or None for key in (
                "GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_RUN_ID",
                "GITHUB_RUN_ATTEMPT", "GITHUB_JOB", "RUNNER_OS", "RUNNER_ARCH",
                "ImageOS", "ImageVersion",
            )
        },
        "resource_scope": "UNKNOWN: aggregate CPU and process-tree memory not sampled",
    }
    if (identity["identity"]["GITHUB_SHA"]
            and identity["identity"]["GITHUB_SHA"] != identity["policy_revision"]):
        raise ValueError("central checkout differs from the workflow revision")
    identity["invocation_id"] = hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()
    ).hexdigest()
    (output / "metadata.json").write_text(json.dumps(identity, indent=2) + "\n")
    site.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(plugin, site / "yueto_lens_report.py")
    distribution = site / "yueto_lens_report-0.dist-info"
    distribution.mkdir(exist_ok=True)
    (distribution / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: yueto-lens-report\nVersion: 0\n")
    (distribution / "entry_points.txt").write_text(
        "[pytest11]\nyueto_lens_report = yueto_lens_report\n")
    (distribution / "RECORD").write_text("")
    print(identity["invocation_id"])


def summarize(output):
    result = {
        "schema": 1, "evidence_status": "MISSING", "release_acceptance": False,
        "problems": [], "sessions": [], "resources": {"status": "UNKNOWN"},
    }
    metadata = output / "metadata.json"
    events = output / "events.jsonl"
    if not metadata.is_file():
        result["problems"].append("preparation metadata missing")
    else:
        try:
            result["metadata"] = json.loads(metadata.read_text())
        except (ValueError, OSError):
            result["problems"].append("preparation metadata invalid")
    if not events.is_file():
        result["problems"].append("pytest never recorded a start")
    else:
        current = None
        try:
            for line in events.read_text().splitlines():
                row = json.loads(line)
                event = row.get("event")
                if event == "start":
                    if current is not None:
                        result["problems"].append("session was replaced before finish")
                    current = {"records": [], "exitstatus": None}
                    result["sessions"].append(current)
                if current is None:
                    result["problems"].append("record outside a session")
                    continue
                current["records"].append(row)
                if event == "finish":
                    current["exitstatus"] = row.get("exitstatus")
                    current = None
        except (ValueError, OSError):
            result["problems"].append("event stream is unreadable or truncated")
        if current is not None:
            result["problems"].append("session has no terminal finish record")
        if len(result["sessions"]) != 1:
            result["problems"].append("formal serial entry requires exactly one session")
        try:
            raw_exit = (output / "pytest-exit-code.txt").read_text().strip()
            actual_exit = int(raw_exit)
            if not result["sessions"] or any(
                s["exitstatus"] != actual_exit for s in result["sessions"]
            ):
                result["problems"].append("pytest process exit differs from session terminal")
            result["pytest_process_exit_code"] = actual_exit
        except (ValueError, OSError):
            result["problems"].append("pytest process exit receipt missing or invalid")
        try:
            started = int((output / "pytest-start-unix-ns.txt").read_text())
            finished = int((output / "pytest-finish-unix-ns.txt").read_text())
            if finished < started:
                raise ValueError("wall clock moved backwards")
            result["process_window"] = {
                "started_unix_ns": started, "finished_unix_ns": finished,
                "duration_seconds": (finished - started) / 1_000_000_000,
                "scope": "shell-observed command window including timestamp-process overhead",
            }
        except (ValueError, OSError):
            result["problems"].append("pytest process wall-clock window unavailable")
        for session in result["sessions"]:
            records = session.pop("records")
            identities = [r for r in records if r.get("event") == "session_identity"]
            timings = [r for r in records if r.get("event") == "session_timing"]
            collections = [r for r in records if r.get("event") == "collection_timing"]
            corpora = [r for r in records if r.get("event") == "collection_corpus"
                       and r.get("scope") == "controller_selected"]
            if len(identities) != 1 or len(timings) != 1 or len(collections) != 1 or len(corpora) != 1:
                result["problems"].append("session identity/collection/timing is incomplete")
                continue
            identity, timing, collection, corpus = identities[0], timings[0], collections[0], corpora[0]
            session.update(identity=identity, timing=timing, collection=collection,
                           corpus={k: v for k, v in corpus.items() if k != "nodeids"})
            if identity.get("invocation_id") != result.get("metadata", {}).get("invocation_id"):
                result["problems"].append("session does not match prepared invocation")
            if identity.get("executor") != "serial":
                result["problems"].append("this summary requires the formal serial executor")
            if timing.get("lost_records") != 0 or timing.get("terminal") != "finished":
                result["problems"].append("recorder loss or interrupted pytest session")
            if collection.get("status") != "finished" or any(
                r.get("event") == "collect_error" for r in records
            ):
                result["problems"].append("collection did not finish without errors")
            nodeids = corpus.get("nodeids", [])
            expected_hash = hashlib.sha256(json.dumps(nodeids, ensure_ascii=False).encode()).hexdigest()
            if corpus.get("count") != len(nodeids) or corpus.get("ordered_nodeids_sha256") != expected_hash:
                result["problems"].append("collected corpus digest/count mismatch")
            phases = [r for r in records if r.get("event") == "phase_timing"]
            parents = [r for r in phases if r.get("report_kind") == "case"]
            if any(r.get("report_kind") not in ("case", "subtest") for r in phases):
                result["problems"].append("unknown report type prevents complete attribution")
            session["subtest_reports_excluded_from_totals"] = sum(
                r.get("report_kind") == "subtest" for r in phases)
            session["phase_seconds"] = dict.fromkeys(("setup", "call", "teardown"), 0.0)
            grouped = {}
            for phase in parents:
                grouped.setdefault(phase["nodeid"], []).append(phase)
                duration = phase.get("duration_seconds")
                if (phase.get("duration_status") != "measured" or
                        type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0):
                    result["problems"].append("case duration unavailable")
                elif phase.get("when") in session["phase_seconds"]:
                    session["phase_seconds"][phase["when"]] += duration
            if set(grouped) != set(nodeids):
                result["problems"].append("selected corpus and reported cases differ")
            for nodeid, reports in grouped.items():
                by_phase = Counter(r["when"] for r in reports)
                setup = next((r for r in reports if r["when"] == "setup"), {})
                expected = {"setup": 1, "teardown": 1}
                if setup.get("outcome") == "passed":
                    expected["call"] = 1
                if by_phase != expected:
                    result["problems"].append(f"incomplete or duplicate case phases: {nodeid}")
            session["reported_cases"] = len(grouped)
        result["evidence_status"] = "PARTIAL" if result["problems"] else "COMPLETE"
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"evidence_status": result["evidence_status"],
                      "problems": result["problems"], "release_acceptance": False}))
    # Diagnostic completeness does not replace or mask the original gate result.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "summarize"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--site", type=Path, default=Path(sysconfig.get_paths()["purelib"]))
    args = parser.parse_args()
    if args.action == "install":
        install(args.output, args.site)
    else:
        summarize(args.output)


if __name__ == "__main__":
    main()
