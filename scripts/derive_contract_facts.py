"""Read immutable YueBoard migration inputs from a local Git checkout."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess


BOARD_COMMIT = re.compile(r"[0-9a-f]{40}")
MIGRATION_DIRECTORY = "internal/platform/db/migrations"
MIGRATION_FILENAME = re.compile(rb"([0-9]{5})_[^/]+\.sql")
GIT_REGULAR_FILE_MODES = {b"100644", b"100755"}


def _git(board: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "--no-replace-objects", "-C", str(board), *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
    ).stdout


def board_contract_ref(board: Path, sha: str) -> str:
    if not BOARD_COMMIT.fullmatch(sha):
        raise ValueError("board_contract_ref_invalid: expected an exact 40-hex commit SHA")
    try:
        if _git(board, "cat-file", "-t", sha).strip() == b"commit":
            return sha
    except subprocess.CalledProcessError:
        pass
    raise ValueError("board_commit_missing: expected a commit in the Board checkout")


def migration_head(board: Path, sha: str) -> int:
    commit = board_contract_ref(board, sha)
    try:
        entries = _git(board, "ls-tree", "-z", f"{commit}:{MIGRATION_DIRECTORY}")
    except subprocess.CalledProcessError as exc:
        raise ValueError("board_migration_head_missing: cannot read migration tree") from exc

    versions = []
    for entry in entries.split(b"\0"):
        metadata, _, filename = entry.partition(b"\t")
        match = MIGRATION_FILENAME.fullmatch(filename)
        if match and metadata.split()[0] in GIT_REGULAR_FILE_MODES:
            versions.append(int(match[1]))
    if not versions:
        raise ValueError("board_migration_head_missing: no numbered migration files")
    return max(versions)
