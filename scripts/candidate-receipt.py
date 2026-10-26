#!/usr/bin/env python3
"""Bind the verified candidate digest to one immutable workflow handoff."""

import argparse
import json
import os
from pathlib import Path
import re


def identity() -> dict[str, str | int]:
    patterns = {
        "service": ("CANDIDATE_SERVICE", r"[a-z0-9][a-z0-9-]*"),
        "repository": ("CANDIDATE_REPOSITORY", r"onesyue/[A-Za-z0-9._-]+"),
        "source_sha": ("CANDIDATE_SOURCE_SHA", r"[0-9a-f]{40}"),
        "workflow_sha": ("GITHUB_SHA", r"[0-9a-f]{40}"),
        "run_id": ("GITHUB_RUN_ID", r"[1-9][0-9]*"),
        "run_attempt": ("GITHUB_RUN_ATTEMPT", r"[1-9][0-9]*"),
    }
    record: dict[str, str | int] = {"schema": 1}
    for key, (variable, pattern) in patterns.items():
        value = os.environ.get(variable, "")
        if not re.fullmatch(pattern, value):
            raise ValueError(f"invalid candidate identity: {key}")
        record[key] = value
    record["image"] = f"ghcr.io/onesyue/{record['service']}"
    return record


def digest(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise ValueError("invalid immutable candidate digest")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("write", "read"))
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    expected = identity()
    if args.operation == "write":
        expected["digest"] = digest(os.environ.get("CANDIDATE_DIGEST"))
        # Each run/attempt/service is emitted once, after all candidate gates.
        with args.path.open("x", encoding="utf-8") as stream:
            json.dump(expected, stream, sort_keys=True)
            stream.write("\n")
    else:
        record = json.loads(args.path.read_text(encoding="utf-8"))
        if not isinstance(record, dict):
            raise ValueError("candidate receipt must be an object")
        value = digest(record.pop("digest", None))
        if record != expected:
            raise ValueError("candidate receipt identity differs from admitted plan")
        print(f"digest={value}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        raise SystemExit(f"candidate receipt refused: {error}") from error
