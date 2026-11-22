#!/usr/bin/env python3
"""Verify the YueBoard commit under build.

The reviewed ``yueboard_contract_pin`` is not an input. Baseline-relative
checks use ``YUEBOARD_BASELINE_REV`` or a yueto release ledger passed with
``--ledger`` / ``YUEBOARD_RELEASE_LEDGER``. When neither is set, those checks
log a warning and today's checks still run.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


SHA = re.compile(r"^[0-9a-f]{40}$")
KEY = re.compile(r"[A-Za-z0-9_-]+")
TODAY_WARNING = (
    "no YUEBOARD_BASELINE_REV and no release ledger; "
    "baseline-relative checks skipped; today's checks still run"
)


class CheckError(Exception):
    pass


def fail(message: str) -> None:
    print(f"::error::{message}", file=sys.stderr)
    raise SystemExit(1)


def positive_int(raw: str, label: str) -> int:
    text = raw.strip()
    if not re.fullmatch(r"[1-9][0-9]*", text):
        raise CheckError(f"{label} must be a positive integer")
    return int(text)


def read_text(path: Path, label: str) -> str:
    if not path.is_file():
        raise CheckError(f"{label} is missing")
    return path.read_text()


def schema_floor(source: Path) -> int:
    return positive_int(read_text(source / "schema-floor.txt", "schema-floor.txt"), "schema-floor.txt")


def check_schema_compat(source: Path) -> int:
    floor = schema_floor(source)
    raw = read_text(source / "schema-compat.txt", "schema-compat.txt").strip()
    if not re.fullmatch(r"[0-9]+", raw):
        raise CheckError("schema-compat.txt must be a non-negative integer")
    compat = int(raw)
    if compat > floor:
        raise CheckError(f"schema-compat.txt {compat} exceeds schema floor {floor}")
    return floor


def ledger_values(text: str) -> dict[tuple[str, ...], str]:
    found: dict[tuple[str, ...], str] = {}
    stack: list[tuple[int, str]] = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        body = raw.strip()
        if body.startswith("- "):
            continue
        key, sep, value = body.partition(":")
        if sep != ":" or KEY.fullmatch(key) is None:
            continue
        while stack and stack[-1][0] >= indent:
            stack.pop()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        path = tuple(item[1] for item in stack) + (key,)
        if value and not value.startswith(("|", ">")):
            found[path] = value
        else:
            stack.append((indent, key))
    return found


def baseline_from_ledger(path: Path) -> str:
    if not path.is_file():
        raise CheckError("release ledger was passed but is not a file")
    found = ledger_values(path.read_text())
    for key in (
        ("components", "yueboard", "revision"),
        ("desired", "production", "yueboard", "revision"),
    ):
        value = found.get(key, "")
        if SHA.fullmatch(value):
            return value
    raise CheckError("release ledger has no yueboard revision")


def resolve_baseline(ledger: Path | None) -> str | None:
    explicit = os.environ.get("YUEBOARD_BASELINE_REV", "").strip()
    if explicit:
        if SHA.fullmatch(explicit) is None:
            raise CheckError("YUEBOARD_BASELINE_REV must be an exact lowercase 40-hex commit")
        return explicit
    chosen = ledger
    if chosen is None:
        raw = os.environ.get("YUEBOARD_RELEASE_LEDGER", "").strip()
        if raw:
            chosen = Path(raw)
    if chosen is not None:
        return baseline_from_ledger(chosen)
    print(f"::warning::{TODAY_WARNING}", file=sys.stderr)
    return None


def git_bytes(source: Path, revision: str, rel: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(source), "show", f"{revision}:{rel}"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise CheckError(f"cannot read {rel} at baseline {revision}")
    return result.stdout


def check_floor_monotonic(source: Path, baseline: str) -> None:
    current = schema_floor(source)
    previous = positive_int(
        git_bytes(source, baseline, "schema-floor.txt").decode(),
        "baseline schema-floor.txt",
    )
    if current < previous:
        raise CheckError(
            f"schema floor regression: {current} < previous promoted floor {previous}"
        )
    print(f"schema floor {current} is monotonic against {baseline} floor {previous}")


def safe_proto_path(rel: str) -> bool:
    if not rel.startswith("proto/") or rel.endswith("/"):
        return False
    return all(part not in ("", ".", "..") for part in rel.split("/"))


def buf_breaking_against_revision(source: Path, baseline: str) -> None:
    listing = subprocess.run(
        ["git", "-C", str(source), "ls-tree", "-r", "--name-only", baseline, "proto"],
        capture_output=True,
        text=True,
        check=False,
    )
    if listing.returncode != 0:
        raise CheckError(f"cannot list proto at baseline {baseline}")
    paths = [line for line in listing.stdout.splitlines() if safe_proto_path(line)]
    if not paths:
        raise CheckError(f"baseline {baseline} has no proto tree")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for rel in paths:
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(git_bytes(source, baseline, rel))
        result = subprocess.run(
            ["buf", "breaking", str(source / "proto"), "--against", str(root / "proto")],
            capture_output=True,
            text=True,
            check=False,
        )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise CheckError(f"buf breaking against {baseline} failed\n{detail}")
    print(f"buf breaking against previously promoted revision {baseline}")


def require_proto_inputs(source: Path) -> None:
    proto = source / "proto/yuenode/v1/yuenode.proto"
    image = source / "proto/breaking-baseline.binpb"
    if not proto.is_file() or not image.is_file():
        raise CheckError(
            "YueBoard proto check inputs are missing "
            "(proto/yuenode/v1/yuenode.proto and proto/breaking-baseline.binpb)"
        )


def check_proto(source: Path, baseline: str | None) -> None:
    gate = source / "scripts/ci/proto-gate.sh"
    if baseline and shutil.which("buf"):
        buf_breaking_against_revision(source, baseline)
        return
    if shutil.which("buf") and gate.is_file():
        result = subprocess.run(
            ["bash", str(gate)],
            cwd=source,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.stdout:
            print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise CheckError(f"YueBoard proto-gate failed\n{detail}")
        print("today proto check: scripts/ci/proto-gate.sh")
        return
    if gate.is_file():
        require_proto_inputs(source)
        print(
            "::warning::buf is not on PATH; checked committed proto-gate inputs. "
            "buf breaking was not re-run in this process",
            file=sys.stderr,
        )
        return
    raise CheckError("YueBoard proto check is unavailable")


def check_openapi(source: Path) -> None:
    snapshot = source / "contracts/openapi/yueboard-api.v1.json"
    try:
        document = json.loads(read_text(snapshot, "OpenAPI snapshot"))
    except json.JSONDecodeError as exc:
        raise CheckError("OpenAPI snapshot is not JSON") from exc
    if not isinstance(document, dict) or not document:
        raise CheckError("OpenAPI snapshot is empty")
    exporter = source / "cmd/export-openapi"
    if not exporter.is_dir():
        raise CheckError("OpenAPI exporter is missing; snapshot freshness cannot be checked")
    if shutil.which("go") is None:
        print(
            "::warning::go is not on PATH; OpenAPI snapshot parsed, generator freshness not re-run",
            file=sys.stderr,
        )
        return
    result = subprocess.run(
        ["go", "run", "./cmd/export-openapi", "--check"],
        cwd=source,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise CheckError(f"OpenAPI snapshot is stale\n{detail}")
    print("OpenAPI snapshot fresh")


def verify(source: Path, ledger: Path | None) -> None:
    source = source.resolve()
    if not (source / "go.mod").is_file():
        raise CheckError("YueBoard source directory with go.mod is required")
    check_schema_compat(source)
    baseline = resolve_baseline(ledger)
    if baseline is not None:
        check_floor_monotonic(source, baseline)
    check_proto(source, baseline)
    check_openapi(source)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--ledger", type=Path)
    args = parser.parse_args()
    try:
        verify(args.source, args.ledger)
    except CheckError as exc:
        fail(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
