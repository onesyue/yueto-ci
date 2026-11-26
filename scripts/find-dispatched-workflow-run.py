#!/usr/bin/env python3
"""Return the new workflow run id whose display title matches TITLE.

Expects BEFORE_RUNS_JSON and AFTER_RUNS_JSON (gh run list --json
databaseId,displayTitle). Prints the single new matching databaseId, or
nothing if it is not unique yet. Exit 0 in either case so the caller can
retry; exit 2 only on malformed input.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def load_runs(path: Path) -> list[dict]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"malformed run list {path}: {exc}")
    if not isinstance(payload, list):
        raise SystemExit(f"malformed run list {path}: expected a JSON array")
    return payload


def find_run(title: str, before: list[dict], after: list[dict]) -> int | None:
    seen = {row["databaseId"] for row in before}
    matches = [
        row["databaseId"]
        for row in after
        if row.get("displayTitle") == title and row.get("databaseId") not in seen
    ]
    if len(matches) != 1 or not isinstance(matches[0], int) or matches[0] < 1:
        return None
    return matches[0]


def main() -> int:
    title = os.environ.get("TITLE", "")
    temp = Path(os.environ.get("RUNNER_TEMP", ""))
    if not title or not temp.is_dir():
        print("TITLE and RUNNER_TEMP are required", file=sys.stderr)
        return 2
    run_id = find_run(
        title,
        load_runs(temp / "before-runs.json"),
        load_runs(temp / "after-runs.json"),
    )
    if run_id is not None:
        print(run_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
