#!/usr/bin/env python3
"""P3 (P2 design §3 step 8, 2026-09-24): should poll-sources skip building an image
whose build inputs did not change since the promoted image?

poll-sources.yml asks this for every image of a group that has no ``built-<HEAD>``
marker.  An image is **skipped** only when every one of these is proved:

1. the promoted image (``:latest``) resolves to one digest with a full revision label;
2. that digest's GitHub build provenance is **verified** by ``gh attestation verify``
   (pinned repo + signer workflow + OIDC issuer + SLSA predicate), and names exactly
   one yueto-ci builder commit — an unverified parse is never trusted;
3. the recipe (``services.json`` entry minus ``ref`` + the ``build`` job text) at that
   builder commit equals the recipe of this checkout — same recipe, same bytes path;
4. the promoted revision is an ancestor of (or equal to) HEAD on the source default
   branch (GitHub compare API: ``identical`` or ``ahead``);
5. ``input-fingerprint.py`` says the inputs at the promoted revision and at HEAD are
   ``unchanged`` and HEAD's Dockerfile carries no floating ``# syntax=`` frontend
   (a floating frontend is a caveat for shadow reporting, a veto for skipping).

Anything else — ``unknown``, an unreachable API, an unverifiable attestation — is
**build**.  Skipping never retags or relabels anything: the old artifact keeps its
original source identity (plan §6.2), and no ``built-<HEAD>`` marker is written, so
the next poll asks again (cheap: a few API calls).

Output: one JSON object ``{"build": [...], "skip": [...], "reasons": {svc: why}}`` on
stdout.  Exit 0 whenever a decision was made (including "build everything"); exit 2
only on usage errors.  The workflow treats a crash of this tool as "build all".
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI_REPO = "onesyue/yueto-ci"
SIGNER_WORKFLOW = "github.com/onesyue/yueto-ci/.github/workflows/build.yml"
BUILDER_PREFIX = f"https://github.com/{CI_REPO}/.github/workflows/build.yml@"
ISSUER = "https://token.actions.githubusercontent.com"
SLSA_PREDICATE = "https://slsa.dev/provenance/v1"
SHA40 = re.compile(r"^[0-9a-f]{40}$")


def _fingerprint():
    spec = importlib.util.spec_from_file_location("poll_skip_fingerprint", ROOT / "scripts" / "input-fingerprint.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def verified_builder(image_ref: str, gh: str, fp) -> str:
    """yueto-ci commit that built ``image_ref`` (…@sha256:…), from gh-verified provenance."""
    env = dict(os.environ)
    if os.environ.get("GITHUB_TOKEN"):
        # the workflow's own token (attestations: read on this public repo), never the
        # source-repo token that GH_TOKEN carries in the scan step
        env["GH_TOKEN"] = os.environ["GITHUB_TOKEN"]
    try:
        proc = subprocess.run(
            [gh, "attestation", "verify", f"oci://{image_ref}", "--repo", CI_REPO,
             "--signer-workflow", SIGNER_WORKFLOW, "--cert-oidc-issuer", ISSUER,
             "--predicate-type", SLSA_PREDICATE, "--format", "json"],
            capture_output=True, text=True, timeout=180, check=False, env=env)
    except (OSError, subprocess.SubprocessError) as exc:
        raise fp.Unknown(f"gh attestation verify did not run: {exc}") from exc
    if proc.returncode != 0:
        raise fp.Unknown(f"provenance of {image_ref} does not verify (rc={proc.returncode})")
    try:
        results = json.loads(proc.stdout)
    except ValueError as exc:
        raise fp.Unknown("gh attestation verify output is not JSON") from exc
    digest = image_ref.rsplit("@sha256:", 1)[-1]
    commits = set()
    for result in results if isinstance(results, list) else []:
        try:
            statement = result["verificationResult"]["statement"]
            builder = statement["predicate"]["runDetails"]["builder"]["id"]
            deps = statement["predicate"]["buildDefinition"]["resolvedDependencies"]
            subjects = statement["subject"]
        except (KeyError, TypeError):
            continue
        if not builder.startswith(BUILDER_PREFIX):
            continue
        if not any((s.get("digest") or {}).get("sha256") == digest for s in subjects):
            continue
        for dep in deps:
            commit = (dep.get("digest") or {}).get("gitCommit", "")
            if SHA40.match(commit):
                commits.add(commit)
                break
    if len(commits) != 1:
        raise fp.Unknown(f"verified provenance of {image_ref} names {len(commits)} builder commits")
    return commits.pop()


def on_default_branch(api, repo: str, older: str, newer: str, fp) -> bool:
    body = api._get(f"compare/{urllib.parse.quote(older, safe='')}...{urllib.parse.quote(newer, safe='')}")
    status = body.get("status")
    if status not in ("identical", "ahead", "behind", "diverged"):
        raise fp.Unknown(f"compare {older[:12]}...{newer[:12]} returned {status!r}")
    return status in ("identical", "ahead")


def decide(service: str, head: str, target: dict, *, fp, api, ci_token: str, ghcr_user: str,
           ghcr_password: str, gh: str, current_workflow: str) -> tuple[str, str]:
    """('skip' | 'build', reason)."""
    try:
        digest, promoted = fp.ghcr_latest(service, ghcr_user, ghcr_password)
        image_ref = f"ghcr.io/onesyue/{service}@{digest}"
        builder = verified_builder(image_ref, gh, fp)
        old_text, old_services = fp.workflow_at(builder, ci_token)
        if service not in old_services:
            return "build", f"{service} not built by yueto-ci@{builder[:12]}"
        old_recipe = fp.recipe(old_services[service], old_text)
        new_recipe = fp.recipe(target, current_workflow)
        recipe_state = fp.compare(old_recipe, new_recipe)
        if recipe_state != "unchanged":
            return "build", f"recipe {recipe_state} since builder {builder[:12]}"
        if not on_default_branch(api, target["repo"], promoted, head, fp):
            return "build", f"promoted {promoted[:12]} is not an ancestor of HEAD {head[:12]}"
        base_fp, head_fp = fp.compute(api, promoted, target), fp.compute(api, head, target)
        inputs = fp.compare(base_fp, head_fp)
        if inputs != "unchanged":
            reason = head_fp.get("unknown") or base_fp.get("unknown") or ", ".join(fp.changed_paths(base_fp, head_fp)[:5])
            return "build", f"inputs {inputs}: {reason}"[:300]
        floating = [c for c in head_fp.get("caveats", []) if "floating Dockerfile frontend" in c]
        if floating:
            return "build", "floating # syntax= frontend (pin it to a digest before builds may be skipped)"
        return "skip", (f"inputs unchanged since promoted {promoted[:12]} ({digest[:19]}…), recipe unchanged, "
                        f"provenance verified (builder {builder[:12]})")
    except fp.Unknown as exc:
        return "build", f"unknown: {exc}"[:300]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", required=True, help="source repository (owner/name)")
    parser.add_argument("--head", required=True, help="exact 40-hex default-branch HEAD")
    parser.add_argument("--services", required=True, help="comma-separated images missing a built- marker")
    parser.add_argument("--gh", default="gh")
    args = parser.parse_args(argv)
    if not SHA40.match(args.head) or not re.fullmatch(r"onesyue/[A-Za-z0-9._-]+", args.repo):
        print("usage: exact 40-hex --head and onesyue/<repo> --repo required", file=sys.stderr)
        return 2
    fp = _fingerprint()
    entries = fp.load_services()
    wanted = [s for s in args.services.split(",") if s]
    unknown = [s for s in wanted if s not in entries or entries[s]["repo"] != args.repo]
    if unknown or not wanted:
        print(f"usage: services {unknown or wanted} are not images of {args.repo}", file=sys.stderr)
        return 2
    api = fp.GitHubTree(args.repo, os.environ.get("GH_API_TOKEN", ""))
    current_workflow = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
    out: dict = {"build": [], "skip": [], "reasons": {}}
    for service in wanted:
        verdict, reason = decide(
            service, args.head, entries[service], fp=fp, api=api, ci_token=os.environ.get("GITHUB_TOKEN", ""),
            ghcr_user=os.environ.get("GHCR_USER", "onesyue"), ghcr_password=os.environ.get("GHCR_PASSWORD", ""),
            gh=args.gh, current_workflow=current_workflow)
        out[verdict].append(service)
        out["reasons"][service] = reason
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
