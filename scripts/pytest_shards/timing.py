"""Ordinary-shard timing model and weight artifact selection."""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

from .config import ORDINARY_WEIGHTS_PREFIX, PASSIVE_TIMING_PREFIX
from .support import ROOT, read_json


def detach_ordinary_weights(value):
    """Remove the timing map. The sealed plan schema stays weights-free."""
    return value.pop("ordinary_weights", None)


def _positive_millis(value):
    return type(value) is int and value >= 1


def _measured_seconds(value):
    return (type(value) in (int, float)
            and value == value
            and value not in (float("inf"), float("-inf"))
            and value >= 0)


def _lower_median(values):
    ordered = sorted(values)
    return ordered[(len(ordered) - 1) // 2]


def align_weights(modules, raw):
    """Map current ordinary modules to positive integer milliseconds.

    Unknown keys are dropped. A module with no usable measurement takes the
    lower median of the known positive weights. No known weight means stride.
    """
    if not isinstance(raw, dict):
        return None
    module_set = set(modules)
    known = []
    aligned = {}
    for key, value in raw.items():
        if key not in module_set or not _positive_millis(value):
            continue
        aligned[key] = value
        known.append(value)
    if not known:
        return None
    fill = _lower_median(known)
    return {module: aligned.get(module, fill) for module in modules}


def weights_from_events(path, ordinary):
    """Sum measured case phases into integer milliseconds, minimum 1."""
    if not isinstance(path, Path) or not path.is_file() or path.is_symlink():
        return {}
    try:
        text = path.read_text()
    except (OSError, UnicodeError):
        return {}
    ordinary = set(ordinary)
    seconds = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        if row.get("event") != "phase_timing" or row.get("report_kind") != "case":
            continue
        if row.get("duration_status") != "measured" or not _measured_seconds(row.get("duration_seconds")):
            continue
        nodeid = row.get("nodeid")
        if not isinstance(nodeid, str) or not nodeid:
            continue
        module = nodeid.split("::", 1)[0]
        if module not in ordinary:
            continue
        seconds[module] = seconds.get(module, 0.0) + row["duration_seconds"]
    result = {}
    for module, total in seconds.items():
        if not _measured_seconds(total):
            continue
        result[module] = max(1, int(round(total * 1000)))
    return result


def resolve_ordinary_weights(modules, weights, timing):
    """Return a complete weight map, or None when the stride must be kept."""
    if weights is not None:
        return align_weights(modules, weights)
    events = timing
    if isinstance(timing, Path) and timing.is_dir():
        events = timing / "events.jsonl"
    if not isinstance(events, Path):
        return None
    try:
        measured = weights_from_events(events, modules)
    except (OSError, UnicodeError, ValueError):
        return None
    return align_weights(modules, measured)


def load_weight_document(path):
    """Read a weight JSON file. A missing or corrupt file keeps the stride."""
    if path is None:
        return None
    try:
        if not path.is_file() or path.is_symlink():
            return None
        value = json.loads(path.read_text())
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def choose_weight_artifact(names):
    """Prefer an ordinary-weights name over a passive timing name."""
    chosen = select_weight_artifact([(None, list(names))])
    return None if chosen is None else chosen[1]


def select_weight_artifact(catalog):
    """Pick from a newest-first ``(run id, artifact names)`` catalog.

    Any ordinary-weights artifact wins over a passive timing artifact. Within
    one kind, the newest run wins.
    """
    weights = None
    timing = None
    for run_id, names in catalog:
        for name in names:
            if not isinstance(name, str):
                continue
            if weights is None and name.startswith(ORDINARY_WEIGHTS_PREFIX):
                weights = (run_id, name)
            elif timing is None and name.startswith(PASSIVE_TIMING_PREFIX):
                timing = (run_id, name)
        if weights is not None:
            break
    return weights or timing


def artifact_names_from_listing(text):
    """Parse ``name<TAB>expired`` lines. Expired and unrelated names are omitted."""
    names = []
    for line in text.splitlines():
        name, separator, expired = line.partition("\t")
        if separator != "\t" or expired != "false":
            continue
        if name.startswith(ORDINARY_WEIGHTS_PREFIX) or name.startswith(PASSIVE_TIMING_PREFIX):
            names.append(name)
    return names


def _default_gh(argv):
    try:
        completed = subprocess.run(argv, capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return 1, "", ""
    # stderr can echo a request URL. Keep it off the console.
    return completed.returncode, completed.stdout, ""


def fetch_previous_ordinary_weights(output, timing_output, runner=None):
    """Download the previous run's weights. Failure returns the stride status."""
    run = runner or _default_gh
    code, stdout, _stderr = run([
        "gh", "run", "list", "-R", "onesyue/yueto-ci", "-w", "build.yml",
        "-s", "success", "-L", "8", "--json", "databaseId",
    ])
    if code != 0:
        return "stride", "run list failed"
    try:
        listed = json.loads(stdout)
    except json.JSONDecodeError:
        return "stride", "run list was not JSON"
    if not isinstance(listed, list):
        return "stride", "run list was not a list"
    catalog = []
    for item in listed:
        if not isinstance(item, dict) or type(item.get("databaseId")) is not int:
            continue
        run_id = item["databaseId"]
        if run_id < 1:
            continue
        code, stdout, _stderr = run([
            "gh", "api", "--paginate",
            f"/repos/onesyue/yueto-ci/actions/runs/{run_id}/artifacts",
            "--jq", ".artifacts[] | [.name, .expired] | @tsv",
        ])
        if code != 0:
            continue
        catalog.append((run_id, artifact_names_from_listing(stdout)))
    chosen = select_weight_artifact(catalog)
    if chosen is None:
        return "stride", "no usable artifact"
    run_id, name = chosen
    destination = Path(tempfile.mkdtemp(prefix="ordinary-weights-"))
    try:
        code, _stdout, _stderr = run([
            "gh", "run", "download", str(run_id), "-R", "onesyue/yueto-ci",
            "-n", name, "-D", str(destination),
        ])
        if code != 0:
            return "stride", "artifact download failed"
        if name.startswith(ORDINARY_WEIGHTS_PREFIX):
            found = [path for path in destination.rglob("ordinary-weights.json")
                     if path.is_file() and not path.is_symlink()]
            if len(found) != 1:
                return "stride", "ordinary weights file missing"
            document = load_weight_document(found[0])
            if not document:
                return "stride", "ordinary weights file unusable"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(document, sort_keys=True) + "\n")
            return "timed", ""
        found = [path for path in destination.rglob("events.jsonl")
                 if path.is_file() and not path.is_symlink()]
        if len(found) != 1:
            return "stride", "timing events missing"
        timing_output.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(found[0], timing_output / "events.jsonl")
        return "timed-events", ""
    finally:
        shutil.rmtree(destination, ignore_errors=True)


def ordinary_shard_evidence_dirs(evidence):
    """Ordinary shard directories, excluding reference collect-only copies."""
    if not isinstance(evidence, Path) or not evidence.is_dir():
        return []
    selected = []
    for child in sorted(evidence.iterdir()):
        name = child.name
        if not child.is_dir() or child.is_symlink():
            continue
        if not name.startswith("ops-shard-") or "-ordinary-" not in name or "-reference-" in name:
            continue
        selected.append(child)
    return selected


def publish_ordinary_weights(admission, evidence, output):
    """Write module milliseconds from ordinary shard events. Return whether written."""
    try:
        assignments = admission["ops_plan"]["assignments"]
        ordinary = [
            module
            for item in assignments
            if isinstance(item, dict) and str(item.get("id", "")).startswith("ordinary-")
            for module in item.get("modules", [])
        ]
    except (KeyError, TypeError, AttributeError):
        return False
    if not ordinary:
        return False
    totals = {}
    for directory in ordinary_shard_evidence_dirs(evidence):
        for module, millis in weights_from_events(directory / "events.jsonl", ordinary).items():
            totals[module] = totals.get(module, 0) + millis
    if not totals:
        return False
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(totals, sort_keys=True, indent=2) + "\n")
    return True


def previous_ordinary_weights_command(args, runner=None):
    try:
        status, reason = fetch_previous_ordinary_weights(
            args.output, args.timing_output, runner=runner)
    except (OSError, ValueError, TypeError):
        status, reason = "stride", "previous weights unavailable"
    if status == "timed":
        print("ORDINARY_WEIGHTS: timed", file=sys.stderr)
    elif status == "timed-events":
        print("ORDINARY_WEIGHTS: timed-events", file=sys.stderr)
    else:
        print(f"ORDINARY_WEIGHTS: stride ({reason})", file=sys.stderr)
    return 0


def publish_ordinary_weights_command(args):
    try:
        wrote = publish_ordinary_weights(read_json(args.admission), args.evidence, args.output)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        wrote = False
    print("ORDINARY_WEIGHTS: published" if wrote else "ORDINARY_WEIGHTS: absent", file=sys.stderr)
    return 0


def load_timing():
    spec = importlib.util.spec_from_file_location("existing_pytest_timing",
                                                 ROOT / "scripts/pytest-timing.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
