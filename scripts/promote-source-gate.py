#!/usr/bin/env python3
"""Promote source gate (P2 #11, design §3 step 9, 2026-09-24).

The promote step used to demand that the candidate source is *still* the default
branch HEAD, re-checked immediately before ``:latest`` moves.  That turned every
unrelated push (a README, a pin commit, a test) into a voided release.  The gate is
now what the design specified — all three, re-checked immediately before the tags move:

1. **on the default branch**: the candidate is identical to or an ancestor of the
   current default-branch HEAD (GitHub compare ``SOURCE...HEAD`` is ``identical`` or
   ``ahead``) — a diverged or unmerged commit is refused;
2. **relevant inputs identical to HEAD**: ``input-fingerprint.py`` gives the same
   build-input fingerprint for this image at the candidate and at HEAD — whatever landed
   after the candidate does not change this image; ``unknown`` is refused;
3. **no older candidate over a newer promotion**: the image currently at ``:latest``
   must carry a revision that is identical to or an ancestor of the candidate — a
   candidate older than (or diverged from) what is already promoted is refused
   (the negative case "old candidate overwriting a newer desired").  The first promote
   of an image (``--latest-revision none``) passes this leg.

The signed ``desired.generation`` lives in the private workspace root release.yaml,
which this public builder must never read or write (policy test
``test_promotion_records_nothing_in_the_workspace_root_repo``); its monotonic check is
enforced where desired is written (root ``release-yaml.py write --expect-generation``
plus its ancestry gate) and where it is read (yueops readers).  This gate is the
registry-side half of the same rule.

Exit 0 = authorized (one ``PROMOTE-SOURCE-OK …`` line); 1 = refused; 2 = usage;
75 = cannot measure (never authorizes).
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHA40 = re.compile(r"^[0-9a-f]{40}$")
EXIT_OK, EXIT_REFUSED, EXIT_USAGE, EXIT_UNMEASURABLE = 0, 1, 2, 75


class Refused(Exception):
    pass


def _fingerprint():
    spec = importlib.util.spec_from_file_location("promote_gate_fingerprint", ROOT / "scripts" / "input-fingerprint.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def compare_status(api, older: str, newer: str, fp) -> str:
    if older == newer:
        return "identical"
    body = api._get(f"compare/{urllib.parse.quote(older, safe='')}...{urllib.parse.quote(newer, safe='')}")
    status = body.get("status")
    if status not in ("identical", "ahead", "behind", "diverged"):
        raise fp.Unknown(f"compare {older[:12]}...{newer[:12]} returned {status!r}")
    return status


def gate(api, fp, *, entry: dict, source: str, head: str, latest: str | None) -> str:
    # 1. on the default branch
    if compare_status(api, source, head, fp) not in ("identical", "ahead"):
        raise Refused(f"source {source[:12]} is not on the default branch (not an ancestor of HEAD {head[:12]})")
    # 2. relevant inputs identical to HEAD
    if source != head:
        at_source, at_head = fp.compute(api, source, entry), fp.compute(api, head, entry)
        state = fp.compare(at_source, at_head)
        if state == "unknown":
            raise fp.Unknown(f"input fingerprint unknown: {at_source.get('unknown') or at_head.get('unknown')}")
        if state != "unchanged":
            changed = fp.changed_paths(at_source, at_head)
            raise Refused(f"{entry['service']} build inputs changed between source {source[:12]} and HEAD "
                          f"{head[:12]}: {', '.join(changed[:6])}")
    # 3. never move :latest backwards (old candidate over a newer promotion)
    if latest is not None and compare_status(api, latest, source, fp) not in ("identical", "ahead"):
        raise Refused(f"refusing to promote {source[:12]} over the newer or diverged {latest[:12]} already at "
                      ":latest (an older candidate may not overwrite a newer promotion)")
    relation = "== HEAD" if source == head else f"inputs identical to HEAD {head[:12]}"
    return (f"PROMOTE-SOURCE-OK service={entry['service']} source={source} ({relation}; on default branch; "
            f"latest={'none' if latest is None else latest[:12]})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--service", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--latest-revision", required=True, help="revision label at :latest, or 'none' (never promoted)")
    args = parser.parse_args(argv)
    if not (SHA40.match(args.source) and re.fullmatch(r"onesyue/[A-Za-z0-9._-]+", args.repo)
            and re.fullmatch(r"[A-Za-z0-9._-]+", args.branch)
            and (args.latest_revision == "none" or SHA40.match(args.latest_revision))):
        print("::error::promote-source-gate: malformed arguments", file=sys.stderr)
        return EXIT_USAGE
    fp = _fingerprint()
    services = fp.load_services()
    entry = services.get(args.service)
    if entry is None or entry["repo"] != args.repo:
        print(f"::error::{args.service} is not an image of {args.repo}", file=sys.stderr)
        return EXIT_USAGE
    api = fp.GitHubTree(args.repo, os.environ.get("GH_API_TOKEN", ""))
    try:
        body = api._get(f"branches/{urllib.parse.quote(args.branch, safe='')}")
        head = (body.get("commit") or {}).get("sha", "")
        if not SHA40.match(head):
            raise fp.Unknown(f"cannot read {args.repo}/{args.branch} HEAD")
        print(gate(api, fp, entry=entry, source=args.source, head=head,
                   latest=None if args.latest_revision == "none" else args.latest_revision))
        return EXIT_OK
    except Refused as exc:
        print(f"::error::refusing promotion: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    except fp.Unknown as exc:
        print(f"::error::refusing promotion: cannot measure ({exc}) — unmeasured never authorizes", file=sys.stderr)
        return EXIT_UNMEASURABLE


if __name__ == "__main__":
    raise SystemExit(main())
