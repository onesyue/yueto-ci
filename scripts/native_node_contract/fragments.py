"""Shared contract readers and fragment guards."""

from __future__ import annotations

import re
from pathlib import Path


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"required contract file is unavailable: {path}") from exc


def read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise RuntimeError(f"required contract file is unavailable: {path}") from exc


def read_package(
    directory: Path,
    pattern: str,
    *,
    min_files: int,
    exclude_suffixes: tuple[str, ...] = (),
) -> str:
    """Concatenate every source file of a package.

    Contract fragments are asserted against a PACKAGE, not a file: Go lets a
    package be laid out across as many files as it likes, and a purely
    mechanical split must not read as a contract violation. (It did once —
    splitting yue-node's 2853-line internal/service/service.go moved
    `applyDeviceGeneration` into state.go and this guard reported the
    credential-generation boundary as missing.)

    `min_files` is the floor that keeps this from becoming the opposite
    failure: a glob that matches nothing yields "", every `forbid` passes, and
    only `require` would notice. Fail loudly instead of scanning air.
    """
    if not directory.is_dir():
        raise RuntimeError(f"required contract package is unavailable: {directory}")
    files = sorted(
        p
        for p in directory.glob(pattern)
        if p.is_file() and not p.name.endswith(exclude_suffixes)
    )
    if len(files) < min_files:
        raise RuntimeError(
            f"contract package {directory} matched {len(files)} file(s) for "
            f"{pattern!r} (floor {min_files}) — the scan did not run"
        )
    return "\n".join(p.read_text(encoding="utf-8") for p in files)


def read_tree(
    directory: Path,
    patterns: tuple[str, ...],
    *,
    min_files: int,
    exclude_suffixes: tuple[str, ...] = (),
) -> str:
    """Concatenate a runtime source tree without silently scanning zero files."""
    if not directory.is_dir():
        raise RuntimeError(f"required contract tree is unavailable: {directory}")
    files = sorted(
        {
            path
            for pattern in patterns
            for path in directory.rglob(pattern)
            if path.is_file() and not path.name.endswith(exclude_suffixes)
        }
    )
    if len(files) < min_files:
        raise RuntimeError(
            f"contract tree {directory} matched {len(files)} file(s) "
            f"(floor {min_files}) — the scan did not run"
        )
    return "\n".join(path.read_text(encoding="utf-8") for path in files)


def normalize_horizontal_whitespace(text: str) -> str:
    """Ignore alignment spacing while preserving line breaks and token content."""
    return re.sub(r"[ \t]+", " ", text)


def require(text: str, fragments: list[str], source: str) -> None:
    normalized = normalize_horizontal_whitespace(text)
    missing = [fragment for fragment in fragments
               if normalize_horizontal_whitespace(fragment) not in normalized]
    if missing:
        raise RuntimeError(
            f"{source} is missing native contract fragments: {missing!r}"
        )


def forbid(text: str, fragments: list[str], source: str) -> None:
    normalized = normalize_horizontal_whitespace(text)
    present = [fragment for fragment in fragments
               if normalize_horizontal_whitespace(fragment) in normalized]
    if present:
        raise RuntimeError(f"{source} contains retired contract fragments: {present!r}")


def forbid_casefold(text: str, fragments: list[str], source: str) -> None:
    folded = normalize_horizontal_whitespace(text).casefold()
    present = [fragment for fragment in fragments
               if normalize_horizontal_whitespace(fragment).casefold() in folded]
    if present:
        raise RuntimeError(f"{source} contains retired contract fragments: {present!r}")


def validate_managed_subscription_catalogue(text: str) -> None:
    """Manual node-list exports do not promise a managed routing profile."""
    catalogues = re.findall(
        r"export const SUBSCRIPTION_CLIENTS\b[^=]*=\s*(\[.*?\])\s*as const;",
        text, re.DOTALL,
    )
    if len(catalogues) != 1 or not re.search(r"\bid\s*:", catalogues[0]):
        raise RuntimeError("YueBoard managed client catalogue is missing or ambiguous")
    forbid_casefold(
        catalogues[0], ["shadowrocket", "小火箭", "surfboard"],
        "YueBoard unsupported managed client catalogue",
    )


def forbid_paths(root: Path, paths: list[str], source: str) -> None:
    """Fail if a retired source path is restored.

    Content guards alone do not distinguish a deliberately deleted authority
    implementation from an empty or renamed compatibility shell.  These paths
    were the Portal-installation token minting and beacon delivery surfaces;
    restoring either file is therefore itself a contract violation.
    """
    present = [path for path in paths if (root / path).exists()]
    if present:
        raise RuntimeError(f"{source} contains retired contract paths: {present!r}")


def rpc_name(path: str) -> str:
    return path.rsplit("/", 1)[-1]

