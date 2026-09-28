#!/usr/bin/env python3
"""Select YueOps SQL over an explicit, verified ancestor range; emit NUL paths.

The caller supplies a trusted release/validation baseline, never HEAD's parent.
Missing history, a deleted migration or a renamed migration is an error, not an
empty successful lint. Squawk itself remains the workflow's pinned binary.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

SQL_PATH = "telegram-bot/yue/migrations/*.sql"


def git(repo: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True).stdout


def changed(repo: Path, base: str) -> list[str]:
    if not re.fullmatch(r"[0-9a-f]{40}", base):
        raise ValueError("migration_base must be an explicit full 40-hex commit")
    if git(repo, "cat-file", "-t", base).strip() != b"commit":
        raise ValueError("migration_base must identify an existing commit")
    git(repo, "merge-base", "--is-ancestor", base, "HEAD")
    # No rename detection: a renamed SQL file includes a deletion and must fail.
    raw = git(repo, "diff", "--name-status", "-z", "--no-renames", base, "HEAD", "--", SQL_PATH)
    fields = raw.decode("utf-8").split("\0")
    if fields.pop() != "" or len(fields) % 2:
        raise ValueError("malformed migration diff")
    result = []
    for status, name in zip(fields[::2], fields[1::2]):
        if status not in ("A", "M"):
            raise ValueError(f"migration deletion/type change requires review: {status} {name}")
        if not (repo / name).is_file() or (repo / name).is_symlink():
            raise ValueError(f"migration is missing or not a regular file: {name}")
        if git(repo, "show", f"HEAD:{name}") != (repo / name).read_bytes():
            raise ValueError(f"migration bytes differ from the checked-out commit: {name}")
        result.append(name)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        paths = changed(args.repo, args.base)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"::error::cannot establish SQL migration coverage: {exc}", file=sys.stderr)
        return 1
    print(f"SQL migration range {args.base}..HEAD: {len(paths)} changed file(s)", file=sys.stderr)
    for path in paths:
        print(f"  lint {path}", file=sys.stderr)
    sys.stdout.buffer.write(b"".join(path.encode() + b"\0" for path in paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
