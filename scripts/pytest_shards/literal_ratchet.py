"""Fail when a new reviewed pin literal appears outside the shard config."""
from __future__ import annotations

import ast
import json
from pathlib import Path

AREA = Path(__file__).resolve().parent
BASELINE_PATH = AREA / "literal-baseline.json"
EXCLUDED = {"config.py", "literal_ratchet.py"}
PIN_LENGTHS = (40, 64)
HEX_DIGITS = frozenset("0123456789abcdef")


def pin_literal_count(source):
    count = 0
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        value = node.value
        if len(value) in PIN_LENGTHS and HEX_DIGITS.issuperset(value):
            count += 1
    return count


def current_counts():
    counts = {}
    for path in sorted(AREA.glob("*.py")):
        if path.name in EXCLUDED:
            continue
        counts[f"scripts/pytest_shards/{path.name}"] = pin_literal_count(
            path.read_text(encoding="utf-8"))
    return counts


def load_baseline(path=BASELINE_PATH):
    baseline = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(baseline, dict) or not baseline:
        raise ValueError("pin literal baseline must be a non-empty object")
    for name, count in baseline.items():
        if not isinstance(name, str) or not name.startswith("scripts/pytest_shards/"):
            raise ValueError("pin literal baseline path is outside the shard package")
        if name.endswith("/config.py") or name.endswith("/literal_ratchet.py"):
            raise ValueError("pin literal baseline must not cover the config module")
        if type(count) is not int or count < 0:
            raise ValueError("pin literal baseline counts must be nonnegative integers")
    return baseline


def violations(baseline=None, counts=None):
    baseline = load_baseline() if baseline is None else baseline
    counts = current_counts() if counts is None else counts
    found = []
    for path, count in sorted(counts.items()):
        allowed = baseline.get(path, 0)
        if count > allowed:
            found.append(f"{path}: pin literals grew from {allowed} to {count}")
    return found
