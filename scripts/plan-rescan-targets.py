#!/usr/bin/env python3
"""Plan the scheduled vulnerability rescan of promoted production images.

C5 (2026-09-27). The rescan used to scan only ``:latest``. What production
actually runs is the signed ``desired`` in the root repository's release.yaml,
but that repository is private and deliberately outside every credential this
public repository holds, so it cannot be read here. The closest registry-side
truth is the ``promoted-<40-hex revision>-<64-hex digest>`` marker that the
build workflow writes on every successful promotion: production runs one of
the most recent promoted digests (``:latest`` itself, or an older one while a
deploy lags or after a rollback). So scan ``:latest`` plus the newest
``PROMOTED_DEPTH`` promoted digests of every service.

Fail closed: any enumeration problem (HTTP error, no ``latest``, malformed
marker, zero promoted versions) exits non-zero, which fails the run and opens
the rescan incident. "Could not list what to scan" must never read as
"nothing to scan".

Usage:
  plan-rescan-targets.py [--versions-dir DIR]   # DIR/<service>.json fixtures (tests)
Environment (live mode): GH_API_TOKEN, a token that can read the packages.
Writes ``matrix=<json>`` to $GITHUB_OUTPUT when set, and prints the matrix.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OWNER = "onesyue"
# Current promotion + its predecessor (the rollback target) + one more for a
# deploy that lags :latest by two promotions.
PROMOTED_DEPTH = 3
PROMOTED_TAG = re.compile(r"^promoted-([0-9a-f]{40})-([0-9a-f]{64})$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class PlanError(Exception):
    pass


def fetch_versions(service: str) -> list[dict]:
    token = os.environ.get("GH_API_TOKEN", "")
    if not token:
        raise PlanError("GH_API_TOKEN is required to enumerate promoted digests")
    request = urllib.request.Request(
        f"https://api.github.com/users/{OWNER}/packages/container/{service}/versions?per_page=100",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - fixed https URL
        payload = json.load(response)
    if not isinstance(payload, list):
        raise PlanError(f"{service}: package versions response is not a list")
    return payload


def select_digests(service: str, versions: list[dict]) -> list[tuple[str, str]]:
    """Return [(digest, role)] -- ``latest`` first, then promoted digests newest first."""
    latest: list[str] = []
    promoted: list[tuple[str, str]] = []
    for version in versions:
        name = version.get("name")
        tags = (((version.get("metadata") or {}).get("container") or {}).get("tags")) or []
        if not isinstance(name, str) or not DIGEST.match(name) or not isinstance(tags, list):
            raise PlanError(f"{service}: malformed package version entry")
        if "latest" in tags:
            latest.append(name)
        for tag in tags:
            if not isinstance(tag, str) or not tag.startswith("promoted-"):
                continue
            match = PROMOTED_TAG.match(tag)
            if not match:
                raise PlanError(f"{service}: malformed promotion marker {tag!r}")
            if f"sha256:{match.group(2)}" != name:
                raise PlanError(f"{service}: promotion marker {tag!r} names another digest")
            updated = version.get("updated_at")
            if not isinstance(updated, str) or not updated:
                raise PlanError(f"{service}: promoted version without updated_at")
            promoted.append((updated, name))
    if len(latest) != 1:
        raise PlanError(f"{service}: expected exactly one :latest version, found {len(latest)}")
    if not promoted:
        raise PlanError(f"{service}: no promoted-* marker in the newest package versions")
    selected: list[tuple[str, str]] = [(latest[0], "latest")]
    seen = {latest[0]}
    newest_first = [name for _, name in sorted(promoted, key=lambda item: item[0], reverse=True)]
    for index, name in enumerate(dict.fromkeys(newest_first)):
        if index >= PROMOTED_DEPTH:
            break
        if name not in seen:
            selected.append((name, f"promoted-{index}"))
            seen.add(name)
    return selected


def plan(services: list[dict], versions_for) -> dict:
    include = []
    for service in services:
        name = service["service"]
        platforms = service["platforms"].split(",")
        for digest, role in select_digests(name, versions_for(name)):
            for platform in platforms:
                include.append(
                    {"service": name, "platform": platform, "digest": digest, "role": role}
                )
    if not include:
        raise PlanError("rescan plan is empty")
    return {"include": include}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--versions-dir", type=Path)
    args = parser.parse_args()
    services = json.loads((ROOT / "services.json").read_text(encoding="utf-8"))
    if args.versions_dir:
        def versions_for(name: str) -> list[dict]:
            return json.loads((args.versions_dir / f"{name}.json").read_text(encoding="utf-8"))
    else:
        versions_for = fetch_versions
    try:
        matrix = plan(services, versions_for)
    except (PlanError, OSError, ValueError, KeyError) as exc:
        print(f"::error::cannot plan the promoted-image rescan: {exc}", file=sys.stderr)
        return 1
    encoded = json.dumps(matrix, separators=(",", ":"))
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"matrix={encoded}\n")
    for row in matrix["include"]:
        print(f"{row['service']} {row['platform']} {row['role']} {row['digest']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
