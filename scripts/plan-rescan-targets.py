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
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
OWNER = "onesyue"
# Current promotion + its predecessor (the rollback target) + one more for a
# deploy that lags :latest by two promotions.
PROMOTED_DEPTH = 3
PAGE_SIZE = 100
MAX_VERSION_PAGES = 100
REQUEST_TIMEOUT_SECONDS = 30
# Five catalogs are hundreds of version pages. Run 43121533913 used the whole
# five-minute plan job walking them one request at a time. Keep this many
# registry reads in flight, each with its own timeout.
REGISTRY_CONCURRENCY = 8
PROMOTED_TAG = re.compile(r"^promoted-([0-9a-f]{40})-([0-9a-f]{64})$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class PlanError(Exception):
    pass


def pagination_relations(service: str, header: str, page: int, *, empty_page: bool = False) -> dict[str, int]:
    """Validate GitHub pagination hints without following credential-bearing URLs."""
    if not isinstance(header, str):
        raise PlanError(f"{service}: malformed pagination header")
    if not header:
        return {}
    relations: dict[str, int] = {}
    package_path = rf"/(?:users/{OWNER}|user/[1-9][0-9]*)/packages/container/{re.escape(service)}/versions"
    for entry in header.split(","):
        match = re.fullmatch(r'\s*<([^>]+)>;\s*rel="(next|prev|first|last)"\s*', entry)
        if not match or match[2] in relations:
            raise PlanError(f"{service}: malformed or duplicate pagination relation")
        try:
            url = urlsplit(match[1])
            query = parse_qs(url.query, strict_parsing=True)
        except ValueError as exc:
            raise PlanError(f"{service}: malformed pagination URL") from exc
        if (url.scheme != "https" or url.netloc != "api.github.com" or url.fragment
                or re.fullmatch(package_path, url.path) is None
                or set(query) != {"per_page", "page"} or query["per_page"] != [str(PAGE_SIZE)]
                or len(query["page"]) != 1 or re.fullmatch(r"[1-9][0-9]*", query["page"][0]) is None):
            raise PlanError(f"{service}: untrusted or nonsequential pagination URL")
        target = int(query["page"][0])
        if ((match[2] == "next" and target != page + 1)
                or (match[2] == "prev" and (page == 1 or target != page - 1))
                or (match[2] == "first" and target != 1)
                or (match[2] == "last" and target < page
                    and not (empty_page and page > 1 and target == page - 1))):
            raise PlanError(f"{service}: untrusted or nonsequential pagination URL")
        relations[match[2]] = target
    if "last" in relations and (relations["last"] > page) != ("next" in relations):
        raise PlanError(f"{service}: contradictory pagination continuation")
    return relations


def read_version_page(service: str, page: int, token: str) -> tuple[object, str]:
    request = urllib.request.Request(
        f"https://api.github.com/users/{OWNER}/packages/container/{service}/versions"
        f"?per_page={PAGE_SIZE}&page={page}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310 - fixed https URL
        return json.load(response), response.headers.get("Link", "")


def fetch_versions(service: str) -> list[dict]:
    token = os.environ.get("GH_API_TOKEN", "")
    if not token:
        raise PlanError("GH_API_TOKEN is required to enumerate promoted digests")
    versions: list[dict] = []
    seen_ids: set[int] = set()
    seen_digests: set[str] = set()

    def consume(page: int, payload: object, link: str) -> tuple[bool, dict[str, int]]:
        if not isinstance(payload, list) or len(payload) > PAGE_SIZE:
            raise PlanError(f"{service}: malformed package versions page {page}")
        try:
            relations = pagination_relations(service, link, page, empty_page=not payload)
        except PlanError as exc:
            raise PlanError(f"{exc} (page {page}, entries {len(payload)})") from exc
        continuation = "next" in relations
        if not payload and continuation:
            raise PlanError(f"{service}: empty page advertises pagination continuation")
        for version in payload:
            if (not isinstance(version, dict) or type(version.get("id")) is not int
                    or version["id"] <= 0 or not isinstance(version.get("name"), str)
                    or DIGEST.fullmatch(version["name"]) is None):
                raise PlanError(f"{service}: malformed package version entry")
            if version["id"] in seen_ids or version["name"] in seen_digests:
                raise PlanError(f"{service}: duplicate package version during pagination")
            seen_ids.add(version["id"])
            seen_digests.add(version["name"])
        versions.extend(payload)
        # A full page is not a completeness proof, even if Link is omitted.
        return len(payload) < PAGE_SIZE and not continuation, relations

    with ThreadPoolExecutor(max_workers=REGISTRY_CONCURRENCY) as pool:
        pending: dict[int, Future[tuple[object, str]]] = {}

        def schedule(page_number: int) -> None:
            if page_number in pending or page_number > MAX_VERSION_PAGES:
                return
            pending[page_number] = pool.submit(read_version_page, service, page_number, token)

        schedule(1)
        for page in range(1, MAX_VERSION_PAGES + 1):
            payload, link = pending.pop(page).result()
            complete, relations = consume(page, payload, link)
            if complete:
                return versions
            nxt = page + 1
            if nxt > MAX_VERSION_PAGES:
                break
            # The validated `last` relation names every remaining page. Read
            # those together. Without it, request only the next page so a
            # finite catalog is not probed past its end.
            schedule(nxt)
            last = relations.get("last")
            if last is not None and last > nxt:
                for extra in range(nxt + 1, min(last, MAX_VERSION_PAGES) + 1):
                    schedule(extra)
    raise PlanError(f"{service}: package versions page limit reached before complete enumeration")


def resolve_index_digest(service: str, digest: str) -> str:
    """Return one index digest. Callers cache it across platforms.

    yueboard's amd64 and arm64 tags share one index digest. Resolving that
    digest on every platform repeats the same registry identity.
    """
    if DIGEST.fullmatch(digest) is None:
        raise PlanError(f"{service}: malformed digest")
    return digest




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
        shared_digest: dict[str, str] = {}
        for digest, role in select_digests(name, versions_for(name)):
            if digest not in shared_digest:
                shared_digest[digest] = resolve_index_digest(name, digest)
            for platform in platforms:
                include.append(
                    {
                        "service": name,
                        "platform": platform,
                        "digest": shared_digest[digest],
                        "role": role,
                    }
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
