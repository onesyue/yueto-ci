"""Canonical YueBoard proto mirror checks."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .fragments import read, read_bytes


PROTO_RELATIVE_PATH = Path("proto/yuenode/v1/yuenode.proto")
PROTO_DIGEST_PATH = Path("proto/CANONICAL.sha256")

def canonical_digest(node_root: Path) -> str:
    """Read the yue-node mirror pin in its committed sha256sum format.

    The producer (yue-node scripts/sync-proto.sh) writes one sha256sum record
    followed by required ``# publisher/consumer/lockstep/...`` contract
    comments. Comments are not records; exactly one record must remain.
    """
    digest_path = node_root / PROTO_DIGEST_PATH
    lines = [
        line
        for line in read(digest_path).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if len(lines) != 1:
        raise RuntimeError(
            f"{PROTO_DIGEST_PATH} must contain exactly one non-empty sha256sum line"
        )
    fields = lines[0].split()
    expected_name = str(PROTO_RELATIVE_PATH.relative_to("proto"))
    if len(fields) != 2 or fields[1] != expected_name:
        raise RuntimeError(
            f"{PROTO_DIGEST_PATH} must pin {expected_name!r} in sha256sum format"
        )
    if re.fullmatch(r"[0-9a-f]{64}", fields[0]) is None:
        raise RuntimeError(f"{PROTO_DIGEST_PATH} does not contain a lowercase SHA-256")
    return fields[0]


def validate_canonical_proto_mirror(node_root: Path, yueboard_root: Path) -> None:
    """Prove the checked-out node mirror equals the real YueBoard authority.

    The yue-node repository already checks its mirror against a digest stored
    in that same repository.  That catches incomplete local updates, but a
    mirror and digest can drift together while remaining internally green.
    Central CI checks out the reviewed YueBoard commit separately and calls
    this gate before any yue-node build, so all three artifacts must agree:
    canonical bytes, mirror bytes, and the committed mirror digest.
    """
    mirror_path = node_root / PROTO_RELATIVE_PATH
    canonical_path = yueboard_root / PROTO_RELATIVE_PATH
    mirror = read_bytes(mirror_path)
    canonical = read_bytes(canonical_path)
    mirror_hash = hashlib.sha256(mirror).hexdigest()
    canonical_hash = hashlib.sha256(canonical).hexdigest()
    pinned_hash = canonical_digest(node_root)

    if mirror != canonical:
        raise RuntimeError(
            "yue-node proto mirror differs byte-for-byte from the checked-out "
            "YueBoard canonical source "
            f"(mirror sha256={mirror_hash}, canonical sha256={canonical_hash}, "
            f"pinned sha256={pinned_hash})"
        )
    if pinned_hash != canonical_hash:
        raise RuntimeError(
            f"{PROTO_DIGEST_PATH} does not pin the checked-out canonical bytes "
            f"(pinned sha256={pinned_hash}, canonical sha256={canonical_hash})"
        )

