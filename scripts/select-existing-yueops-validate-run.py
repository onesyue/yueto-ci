#!/usr/bin/env python3
"""Decide whether an official yueops validation_only run already covers SOURCE.

Reads a ``gh run list --json databaseId,displayTitle,conclusion,status``
payload from stdin. Prints ``success <id>``, ``pending <id>``, ``failed <id>``
or ``none``. Only titles for this exact yueops SHA are considered.

A finished red run means the SHA *has run*: the hourly schedule reports it
and never dispatches the same SHA again (owner t1520u/t1525u: one build per
head). Only a cancelled run (superseded, never a verdict) leaves ``none``.
"""

from __future__ import annotations

import json
import os
import re
import sys

SHA = re.compile(r"^[0-9a-f]{40}$")
# Finished verdicts that are not success. "cancelled"/"skipped" are not verdicts.
RED = frozenset({"failure", "timed_out", "startup_failure", "action_required"})
TITLE = re.compile(
    r"^Build & publish images yueops ([0-9a-f]{40})(?: \[nonce:[0-9a-f]{32}\])?$"
)


def select(source: str, runs: list[dict]) -> tuple[str, int | None]:
    if SHA.fullmatch(source) is None:
        raise SystemExit("SOURCE must be a 40-hex SHA")
    pending: list[int] = []
    successes: list[int] = []
    failures: list[int] = []
    for row in runs:
        title = row.get("displayTitle")
        run_id = row.get("databaseId")
        if not isinstance(title, str) or not isinstance(run_id, int) or run_id < 1:
            continue
        match = TITLE.fullmatch(title)
        if match is None or match.group(1) != source:
            continue
        status = row.get("status")
        conclusion = row.get("conclusion")
        if status in {"queued", "in_progress", "waiting", "pending"}:
            pending.append(run_id)
        elif status == "completed" and conclusion == "success":
            successes.append(run_id)
        elif status == "completed" and conclusion in RED:
            failures.append(run_id)
    if successes:
        return "success", successes[0]
    if pending:
        return "pending", pending[0]
    if failures:
        return "failed", failures[0]
    return "none", None


def main() -> int:
    source = os.environ.get("SOURCE", "")
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(f"malformed run list: {exc}", file=sys.stderr)
        return 2
    if not isinstance(payload, list):
        print("malformed run list: expected a JSON array", file=sys.stderr)
        return 2
    decision, run_id = select(source, payload)
    if run_id is None:
        print("none")
    else:
        print(f"{decision} {run_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
