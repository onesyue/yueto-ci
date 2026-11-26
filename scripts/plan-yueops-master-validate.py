#!/usr/bin/env python3
"""Resolve official validation-only inputs for yueops origin/master.

Private yueops has no hosted Actions, so native+ordinary validate used to run
only at ship time. This planner feeds the existing ``build.yml``
``validation_only`` path: the current yueops default-branch SHA, the newest
promoted yueops-web revision as ``migration_base`` (the registry-side record
of the last trusted release), and the reviewed Board contract pin.

    GH_API_TOKEN=... python3 scripts/plan-yueops-master-validate.py

Prints one JSON object with ``source``, ``migration_base`` and
``board_revision`` (each a 40-hex SHA). Fail closed: an enumeration problem
must never look like "nothing to validate".
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

_CI_LIB = str(Path(__file__).resolve().parent / "lib")
if _CI_LIB not in sys.path:
    sys.path.insert(0, _CI_LIB)
from ci_constants import GITHUB_API_ORIGIN, GITHUB_HTTP_TIMEOUT_SECONDS

SCRIPTS = Path(__file__).resolve().parent
OWNER = "onesyue"
YUEOPS_REPO = f"{OWNER}/yueops"
PROMOTED_SERVICE = "yueops-web"
SHA = re.compile(r"^[0-9a-f]{40}$")
PROMOTED_TAG = re.compile(r"^promoted-([0-9a-f]{40})-([0-9a-f]{64})$")


class PlanError(Exception):
    pass


def load_sibling(name: str):
    path = SCRIPTS / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise PlanError(f"cannot load {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def request_json(url: str, token: str) -> object:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=GITHUB_HTTP_TIMEOUT_SECONDS) as response:  # noqa: S310
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise PlanError(f"cannot read {url.split('?', 1)[0]}: {exc}") from exc


def resolve_source_sha(token: str, *, ref: str = "master") -> str:
    if SHA.fullmatch(ref):
        return ref
    encoded = urllib.request.quote(ref, safe="")
    payload = request_json(
        f"{GITHUB_API_ORIGIN}/repos/{YUEOPS_REPO}/commits/{encoded}",
        token,
    )
    if not isinstance(payload, dict):
        raise PlanError("yueops default-branch commit payload is malformed")
    sha = payload.get("sha")
    if not isinstance(sha, str) or SHA.fullmatch(sha) is None:
        raise PlanError("yueops default-branch SHA is missing or malformed")
    return sha


def newest_promoted_revision(versions: list[dict]) -> str:
    newest: tuple[str, str] | None = None
    for version in versions:
        tags = (((version.get("metadata") or {}).get("container") or {}).get("tags")) or []
        if not isinstance(tags, list):
            raise PlanError(f"{PROMOTED_SERVICE}: malformed package version tags")
        updated = version.get("updated_at")
        for tag in tags:
            if not isinstance(tag, str) or not tag.startswith("promoted-"):
                continue
            match = PROMOTED_TAG.match(tag)
            if not match:
                raise PlanError(f"{PROMOTED_SERVICE}: malformed promotion marker {tag!r}")
            if not isinstance(updated, str) or not updated:
                raise PlanError(f"{PROMOTED_SERVICE}: promoted version without updated_at")
            if newest is None or updated > newest[0]:
                newest = (updated, match.group(1))
    if newest is None:
        raise PlanError(f"{PROMOTED_SERVICE}: no promoted-* marker in package versions")
    return newest[1]


def resolve_board_revision() -> str:
    contract = load_sibling("validate-native-node-contract.py")
    revision = contract.resolve_yueboard_contract_ref("")
    if not isinstance(revision, str) or SHA.fullmatch(revision) is None:
        raise PlanError("reviewed Board contract pin is missing or malformed")
    return revision


def plan(*, token: str, ref: str, source_token: str | None = None, versions_for=None) -> dict[str, str]:
    package_token = token
    commit_token = source_token or token
    if not package_token:
        raise PlanError("GH_API_TOKEN is required to resolve the promoted baseline")
    if not commit_token:
        raise PlanError("GH_SOURCE_TOKEN is required to resolve yueops master")
    if versions_for is None:
        rescan = load_sibling("plan-rescan-targets.py")
        versions_for = rescan.fetch_versions
    source = resolve_source_sha(commit_token, ref=ref)
    migration_base = newest_promoted_revision(versions_for(PROMOTED_SERVICE))
    return {
        "source": source,
        "migration_base": migration_base,
        "board_revision": resolve_board_revision(),
    }


def main() -> int:
    token = os.environ.get("GH_API_TOKEN", "")
    source_token = os.environ.get("GH_SOURCE_TOKEN", "") or token
    ref = os.environ.get("YUEOPS_VALIDATE_REF", "master").strip() or "master"
    try:
        payload = plan(token=token, ref=ref, source_token=source_token)
    except PlanError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
