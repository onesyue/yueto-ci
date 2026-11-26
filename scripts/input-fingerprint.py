#!/usr/bin/env python3
"""Deterministic build-input fingerprints for the central image builds.

SHADOW MODE ONLY (P2, 2026-09-24).  Nothing in the build or promotion path
consumes a verdict from this file: it computes and *reports* whether an image's
build inputs changed relative to the last promoted image.  Turning a verdict
into a skipped build is a separate, reviewed P3 change.

What is fingerprinted, per image (``services.json`` entry):

* the Dockerfile blob (this also covers every ``FROM``/``COPY --from`` image
  digest, every ``ARG`` default and the ``# syntax=`` directive);
* the *effective* ignore file -- BuildKit reads ``<Dockerfile>.dockerignore``
  next to the Dockerfile, otherwise ``<context>/.dockerignore``.  A
  ``.dockerignore`` merely sitting in the Dockerfile's directory is **not**
  read (measured locally with buildx, see ``dead_ignore_files``);
* every tracked file that a ``COPY``/``ADD`` (or a context bind mount) of any
  stage can see after ignore filtering, as ``(path, git mode, blob oid)``;
* every ``.gitattributes`` in the tree (checkout may transform bytes).

Separately, a *recipe* fingerprint covers the builder side that lives in this
repository: the ``services.json`` entry minus ``ref`` and the text of the
``build`` job in ``.github/workflows/build.yml``.  The source identity build
args (``VERSION``/``COMMIT``/``BUILD_TIME`` and the revision label) are
excluded on purpose: reusing an artifact keeps its *original* source identity,
it never gets relabelled (plan section 6.2).

Anything this parser cannot prove is reported ``unknown`` with a reason and
must be treated as "changed": unpinned base images, ``$VAR`` in a source
path, remote ``ADD`` without ``--checksum``, ``COPY --exclude``, secret
mounts, truncated API trees, ``filter=`` git attributes, a non-``.`` context.

Two tree sources give byte-identical results: a local git repository
(``git ls-tree``) and the GitHub REST git-trees API (used by CI, which has no
source checkout in the planning job).  Only the standard library is used so
the planner runner and the workstation (3.9+) can both run it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from input_fingerprint.constants import (
    BUILD_JOB,
    FEEDBACK_SCHEMA,
    FULL_GATES,
    PINNED_IMAGE,
    RECIPE_SCHEMA,
    ROOT,
    SCHEMA,
    SHA40,
    Unknown,
)
from input_fingerprint.dockerfile import DockerfileFacts, parse_dockerfile, selected
from input_fingerprint.fingerprint import (
    _digest,
    _feedback_changes,
    _feedback_policy,
    _feedback_tree,
    changed_paths,
    compare,
    compute,
    feedback_command,
    feedback_manifest,
    load_services,
    recipe,
    validate_feedback_manifest,
    verdict,
)
from input_fingerprint.ignore import IgnoreRules
from input_fingerprint.shadow import (
    ghcr_latest,
    history,
    provenance_builder,
    shadow_ci,
    workflow_at,
)
from input_fingerprint.tree import GitHubTree, LocalGit

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compute", help="fingerprint one image at one local revision")
    c.add_argument("--repo", required=True)
    c.add_argument("--rev", required=True)
    c.add_argument("--service", required=True)
    c.add_argument("--services", type=Path)
    c.add_argument("--files", action="store_true", help="include the per-file list")
    d = sub.add_parser("compare", help="compare two local revisions of one image")
    d.add_argument("--repo", required=True)
    d.add_argument("--base", required=True)
    d.add_argument("--head", required=True)
    d.add_argument("--service", required=True)
    d.add_argument("--services", type=Path)
    h = sub.add_parser("history", help="shadow verdicts for the last N first-parent commits")
    h.add_argument("--repo", required=True)
    h.add_argument("--group", required=True, help="services.json group (yueops, yueboard, yue-node)")
    h.add_argument("--baseline", required=True, help="last promoted revision to compare against")
    h.add_argument("--head", default="HEAD")
    h.add_argument("-n", type=int, default=10)
    h.add_argument("--services", type=Path)
    s = sub.add_parser("shadow-ci", help="annotate a build plan (CI, read-only)")
    s.add_argument("--matrix", required=True, help="the plan job's build matrix JSON")
    f = sub.add_parser("feedback", help="persist advisory Ops source changes; never skip a gate")
    f.add_argument("--repo", help="local Git object source; CI uses the existing read-only API")
    f.add_argument("--base", required=True, help="explicit exact previous-source baseline")
    f.add_argument("--matrix", required=True)
    f.add_argument("--validation-matrix", required=True)
    f.add_argument("--policy-commit", default=os.environ.get("GITHUB_SHA", ""))
    f.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    f.add_argument("--run-attempt", default=os.environ.get("GITHUB_RUN_ATTEMPT", ""))
    f.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    if args.cmd == "feedback":
        return feedback_command(args)
    if args.cmd == "shadow-ci":
        return shadow_ci(args)
    services = load_services(args.services)
    if args.cmd == "history":
        return history(args, services)
    if args.service not in services:
        print(f"unknown service {args.service}", file=sys.stderr)
        return 2
    entry = services[args.service]
    git = LocalGit(args.repo)
    if args.cmd == "compute":
        out = compute(git, git.resolve(args.rev), entry)
        if not args.files:
            out.pop("files", None)
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0 if "unknown" not in out else 3
    base = compute(git, git.resolve(args.base), entry)
    head = compute(git, git.resolve(args.head), entry)
    state = compare(base, head)
    print(json.dumps({
        "service": args.service, "inputs": state,
        "base": base.get("fingerprint") or base.get("unknown"),
        "head": head.get("fingerprint") or head.get("unknown"),
        "changed_paths": changed_paths(base, head) if state == "changed" else [],
    }, indent=2, sort_keys=True))
    return {"unchanged": 0, "changed": 1}.get(state, 3)


if __name__ == "__main__":
    raise SystemExit(main())
