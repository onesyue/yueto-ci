#!/usr/bin/env python3
"""Fail when the weekly vulnerability scan has no success inside its window.

The scheduled workflow is the alert: a red run is what the alert chain
surfaces. This checker only decides freshness from a run list.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

WEEKLY_SCAN_SUCCESS_MAX_AGE = timedelta(days=8)


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp lacks a timezone: {value}")
    return parsed.astimezone(timezone.utc)


def latest_success(runs: object) -> datetime | None:
    if not isinstance(runs, list):
        raise ValueError("run list must be a JSON array")
    latest: datetime | None = None
    for run in runs:
        if not isinstance(run, dict) or run.get("conclusion") != "success":
            continue
        created = run.get("createdAt") or run.get("created_at")
        if not isinstance(created, str):
            raise ValueError("successful run is missing createdAt")
        moment = _parse_time(created)
        if latest is None or moment > latest:
            latest = moment
    return latest


def evaluate(runs: object, now: datetime) -> tuple[bool, str]:
    if now.tzinfo is None:
        raise ValueError("now lacks a timezone")
    now = now.astimezone(timezone.utc)
    latest = latest_success(runs)
    if latest is None:
        return False, "weekly scan has no successful run"
    age = now - latest
    if age > WEEKLY_SCAN_SUCCESS_MAX_AGE:
        return (
            False,
            "weekly scan last succeeded "
            f"{latest.isoformat()} which is outside "
            f"{WEEKLY_SCAN_SUCCESS_MAX_AGE.days} days",
        )
    return True, f"weekly scan last succeeded {latest.isoformat()}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--now", required=True)
    args = parser.parse_args(argv)
    runs = json.loads(args.runs.read_text(encoding="utf-8"))
    ok, detail = evaluate(runs, _parse_time(args.now))
    print(detail)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
