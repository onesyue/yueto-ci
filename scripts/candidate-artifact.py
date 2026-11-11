#!/usr/bin/env python3
"""Select the attempt that stored one verified handoff artifact.

``gh run rerun --failed`` starts a new attempt of the same run. The build and
plan jobs keep the uploads from the attempt that produced them. Publish and
evidence must read that attempt, and must not invent a name for a missing one.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from pathlib import Path

REPOSITORY = "onesyue/yueto-ci"
RUN_ID = re.compile(r"[1-9][0-9]*")
SERVICE = re.compile(r"[a-z0-9][a-z0-9-]*")
SAFE_OUTPUT = re.compile(r"[A-Za-z0-9_.:*-]+")
RETRYABLE = {"no handoff artifact for this run", "artifact list is unreadable"}


def load_artifacts(path: Path | None, run_id: str) -> list:
    if path is not None:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            raw = raw.get("artifacts")
        if not isinstance(raw, list):
            raise ValueError("artifact list is not a list")
        return raw
    if not RUN_ID.fullmatch(run_id):
        raise ValueError("invalid run id")
    proc = subprocess.run(
        ["gh", "api", "--paginate",
         f"repos/{REPOSITORY}/actions/runs/{run_id}/artifacts",
         "--jq", ".artifacts"],
        check=False, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise ValueError("artifact list is unreadable")
    items: list = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        page = json.loads(line)
        if not isinstance(page, list):
            raise ValueError("artifact page is not a list")
        items.extend(page)
    return items


def _name(item: object) -> str | None:
    if not isinstance(item, dict):
        raise ValueError("artifact entry is not an object")
    if item.get("expired") is True:
        return None
    name = item.get("name")
    if not isinstance(name, str) or "\n" in name or "\r" in name:
        return None
    return name


def _attempt(name: str, *, family: str, run_id: str, service: str | None) -> int | None:
    if family == "candidate":
        prefix = f"candidate-{run_id}-"
        suffix = f"-{service}"
        if not (name.startswith(prefix) and name.endswith(suffix)):
            return None
        attempt = name[len(prefix):-len(suffix)]
    elif family == "admission":
        prefix = f"ops-admission-{run_id}-"
        if not name.startswith(prefix):
            return None
        attempt = name[len(prefix):]
    else:
        raise ValueError("unknown handoff family")
    if not RUN_ID.fullmatch(attempt):
        return None
    return int(attempt)


def select(artifacts: list, *, family: str, run_id: str,
           run_attempt: int, service: str | None) -> dict[str, str]:
    if family not in {"admission", "candidate"}:
        raise ValueError("unknown handoff family")
    if not RUN_ID.fullmatch(run_id) or run_attempt < 1:
        raise ValueError("invalid run id")
    if family == "candidate":
        if service is None or SERVICE.fullmatch(service) is None:
            raise ValueError("invalid candidate service")
    elif service is not None:
        raise ValueError("admission selection has no service")
    seen: set[str] = set()
    counts: dict[int, int] = {}
    for item in artifacts:
        name = _name(item)
        if name is None:
            continue
        attempt = _attempt(name, family=family, run_id=run_id, service=service)
        if attempt is None:
            continue
        if name in seen:
            raise ValueError("duplicate handoff artifact")
        seen.add(name)
        counts[attempt] = counts.get(attempt, 0) + 1
        if counts[attempt] > 1:
            raise ValueError("duplicate handoff artifact")
    eligible = [attempt for attempt in counts if attempt <= run_attempt]
    if not eligible:
        raise ValueError("no handoff artifact for this run")
    chosen = run_attempt if run_attempt in counts else max(eligible)
    if family == "candidate":
        selected = f"candidate-{run_id}-{chosen}-{service}"
    else:
        selected = f"ops-admission-{run_id}-{chosen}"
    return {"built_attempt": str(chosen), "name": selected}


def emit(selected: dict[str, str]) -> None:
    for key in ("built_attempt", "name"):
        value = selected[key]
        if SAFE_OUTPUT.fullmatch(value) is None:
            raise ValueError("refusing to emit an unexpected handoff value")
        print(f"{key}={value}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("select",))
    parser.add_argument("--family", required=True, choices=("admission", "candidate"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--service", default=None)
    parser.add_argument("--artifacts", type=Path)
    args = parser.parse_args()
    if RUN_ID.fullmatch(args.run_attempt) is None:
        raise ValueError("invalid run attempt")
    run_attempt = int(args.run_attempt)
    if args.artifacts is not None:
        emit(select(load_artifacts(args.artifacts, args.run_id), family=args.family,
                    run_id=args.run_id, run_attempt=run_attempt, service=args.service))
        return
    last: Exception | None = None
    for attempt in range(1, 4):
        try:
            emit(select(load_artifacts(None, args.run_id), family=args.family,
                        run_id=args.run_id, run_attempt=run_attempt, service=args.service))
            return
        except ValueError as error:
            last = error
            if str(error) not in RETRYABLE or attempt == 3:
                break
            time.sleep(2)
    raise ValueError(str(last) if last else "no handoff artifact for this run")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"handoff artifact refused: {error}") from error
