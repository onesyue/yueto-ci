#!/usr/bin/env python3
"""Keep the public deadman copy generated from one named YueOps commit.

YueOps is the only producer. ``yueops-producer.json`` names that commit and
the sha256 of each generated file. ``--check`` fails when a copy's digest
does not match the pin. ``--check --repo <checkout>`` also reads the named
commit and fails when the copy drifted from it. ``--apply --repo`` rewrites
the copies from that commit. The copies stay byte-identical to YueOps; this
script does not insert a header.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


REPOSITORY = "onesyue/yueops"
PIN_NAME = "yueops-producer.json"
COPIES = (
    (
        "scripts/alert-chain-deadman-check.py",
        "scripts/alert-chain-deadman-check.py",
    ),
    (
        "config/alert-chain-deadman-observer-contract.json",
        "config/alert-chain-deadman-observer-contract.json",
    ),
)


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_COUNT"] = "0"
    return env


def _git(repo: Path, args: tuple[str, ...]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "--no-replace-objects", "-C", str(repo), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_git_env(),
    )


def _git_bytes(repo: Path, args: tuple[str, ...]) -> bytes:
    result = _git(repo, args)
    if result.returncode != 0:
        raise SystemExit("deadman producer could not read the named yueops commit")
    return result.stdout


def _copy_path(root: Path, relative: str) -> Path:
    parts = Path(relative).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise SystemExit(f"deadman copy path is not relative: {relative}")
    return root.joinpath(*parts)


def _hex(value: object, size: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == size
        and all(character in "0123456789abcdef" for character in value)
    )


def _copy_row_ok(row: object, expected: tuple[str, str]) -> bool:
    if not isinstance(row, dict) or set(row) != {"source", "copy", "sha256"}:
        return False
    return row["source"] == expected[0] and row["copy"] == expected[1] and _hex(row["sha256"], 64)


def _pin_ok(pin: object) -> bool:
    if not isinstance(pin, dict) or set(pin) != {"repository", "sha", "copies"}:
        return False
    copies = pin["copies"]
    if pin["repository"] != REPOSITORY or not _hex(pin["sha"], 40):
        return False
    if not isinstance(copies, list) or len(copies) != len(COPIES):
        return False
    return all(_copy_row_ok(row, expected) for row, expected in zip(copies, COPIES))


def load_pin(root: Path) -> dict:
    path = root / PIN_NAME
    if not path.is_file() or path.is_symlink():
        raise SystemExit("deadman producer pin is absent")
    try:
        pin = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit("deadman producer pin is not the yueops contract") from exc
    if not _pin_ok(pin):
        raise SystemExit("deadman producer pin does not name the yueops copies")
    return pin


def _read_copy(path: Path, relative: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise SystemExit(f"hand-edited deadman copy: {relative}")
    return path.read_bytes()


def blob_at(repo: Path, sha: str, source: str) -> bytes:
    if _git(repo, ("cat-file", "-e", f"{sha}^{{commit}}")).returncode != 0:
        raise SystemExit(f"named yueops SHA is absent: {sha}")
    if _git(repo, ("cat-file", "-e", f"{sha}:{source}")).returncode != 0:
        raise SystemExit(f"deadman source is absent from {sha}: {source}")
    oid = _git_bytes(repo, ("rev-parse", "--verify", f"{sha}:{source}")).decode("ascii").strip()
    return _git_bytes(repo, ("cat-file", "blob", oid))


def check(root: Path, repo: Path | None = None) -> None:
    pin = load_pin(root)
    for row in pin["copies"]:
        relative = row["copy"]
        data = _read_copy(_copy_path(root, relative), relative)
        if hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise SystemExit(f"hand-edited deadman copy: {relative}")
        if repo is None:
            continue
        if blob_at(repo, pin["sha"], row["source"]) != data:
            raise SystemExit(
                f"deadman copy drifted from yueops SHA {pin['sha']}: {row['source']}"
            )
    print(f"deadman producer: ok ({pin['sha']})")


def apply(root: Path, repo: Path, sha: str | None = None) -> None:
    if sha is None:
        sha = load_pin(root)["sha"]
    if not _hex(sha, 40):
        raise SystemExit("yueops SHA must be 40 lowercase hex characters")
    copies = []
    for source, copy in COPIES:
        data = blob_at(repo, sha, source)
        path = _copy_path(root, copy)
        if path.is_symlink():
            raise SystemExit(f"hand-edited deadman copy: {copy}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        copies.append(
            {"source": source, "copy": copy, "sha256": hashlib.sha256(data).hexdigest()}
        )
    pin = {"repository": REPOSITORY, "sha": sha, "copies": copies}
    (root / PIN_NAME).write_text(json.dumps(pin, indent=2) + "\n", encoding="utf-8")
    print(f"deadman producer: wrote {sha}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--sha")
    parser.add_argument("--root", type=Path)
    args = parser.parse_args(argv)
    root = args.root if args.root is not None else Path(__file__).resolve().parents[1]
    if args.apply:
        if args.repo is None:
            raise SystemExit("--apply requires --repo")
        apply(root, args.repo, args.sha)
        return 0
    if args.sha is not None:
        raise SystemExit("--sha is only valid with --apply")
    check(root, args.repo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
