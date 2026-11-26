"""Read-only GHCR and provenance reads for the shadow planner."""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request

from .constants import ROOT, SHA40, Unknown
from .fingerprint import changed_paths, compare, compute, recipe, verdict
from .tree import GitHubTree, LocalGit

def ghcr_latest(service: str, user: str, password: str) -> tuple[str, str]:
    """(digest, revision label) of ghcr.io/onesyue/<service>:latest, read-only."""
    repo = f"onesyue/{service}"
    auth = base64.b64encode(f"{user}:{password}".encode()).decode()
    token_req = urllib.request.Request(
        f"https://ghcr.io/token?scope=repository:{repo}:pull&service=ghcr.io",
        headers={"Authorization": f"Basic {auth}"},
    )
    try:
        with urllib.request.urlopen(token_req, timeout=30) as response:
            token = json.load(response)["token"]
        accept = ", ".join([
            "application/vnd.oci.image.index.v1+json",
            "application/vnd.docker.distribution.manifest.list.v2+json",
            "application/vnd.oci.image.manifest.v1+json",
            "application/vnd.docker.distribution.manifest.v2+json",
        ])

        def get(path: str, accept_header: str = accept):
            req = urllib.request.Request(
                f"https://ghcr.io/v2/{repo}/{path}",
                headers={"Authorization": f"Bearer {token}", "Accept": accept_header},
            )
            return urllib.request.urlopen(req, timeout=30)

        with get("manifests/latest") as response:
            digest = response.headers.get("Docker-Content-Digest", "")
            index = json.load(response)
        manifest = index
        if "manifests" in index:
            platform = [
                m for m in index["manifests"]
                if m.get("platform", {}).get("architecture") == "amd64"
                and m.get("platform", {}).get("os") == "linux"
            ]
            if not platform:
                raise Unknown("latest index has no linux/amd64 manifest")
            if service == "yueboard" and len(platform) != 1:
                raise Unknown("ambiguous linux/amd64 manifests for promoted YueBoard")
            with get(f"manifests/{platform[0]['digest']}") as response:
                manifest = json.load(response)
        with get(f"blobs/{manifest['config']['digest']}", "*/*") as response:
            config = json.load(response)
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
        raise Unknown(f"GHCR read of {service}:latest failed: {exc}") from exc
    revision = (config.get("config") or {}).get("Labels", {}).get("org.opencontainers.image.revision", "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest) or not SHA40.match(revision):
        raise Unknown(f"{service}:latest has no readable digest/revision label")
    return digest, revision


def provenance_builder(digest: str, token: str, repo: str = "onesyue/yueto-ci") -> str:
    """yueto-ci commit that built `digest`, from its GitHub build-provenance
    attestation.  Shadow mode parses it without verifying the signature; P3
    must verify (`gh attestation verify`) before acting on it."""
    body = GitHubTree(repo, token)._get(f"attestations/{digest}")
    for att in body.get("attestations", []):
        try:
            statement = json.loads(base64.b64decode(att["bundle"]["dsseEnvelope"]["payload"]))
            deps = statement["predicate"]["buildDefinition"]["resolvedDependencies"]
            builder = statement["predicate"]["runDetails"]["builder"]["id"]
        except (KeyError, ValueError, TypeError):
            continue
        if not builder.startswith(f"https://github.com/{repo}/.github/workflows/build.yml@"):
            continue
        for dep in deps:
            commit = dep.get("digest", {}).get("gitCommit", "")
            if SHA40.match(commit):
                return commit
    raise Unknown(f"no build provenance naming a {repo} commit for {digest[:19]}")


def workflow_at(commit: str, token: str, repo: str = "onesyue/yueto-ci") -> tuple[str, dict]:
    api = GitHubTree(repo, token)
    tree = api.entries(commit)
    text = api.blob(tree[".github/workflows/build.yml"][2]).decode()
    services = {e["service"]: e for e in json.loads(api.blob(tree["services.json"][2]))}
    return text, services


def shadow_ci(args: argparse.Namespace) -> int:
    """Annotate each target of this run; exit 0 unless the tool itself broke."""
    source_token = os.environ.get("GH_API_TOKEN", "")
    ci_token = os.environ.get("GITHUB_TOKEN", "")
    ghcr_user = os.environ.get("GHCR_USER", "onesyue")
    ghcr_password = os.environ.get("GHCR_PASSWORD", "")
    matrix = json.loads(args.matrix)
    current_workflow = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
    rows = []
    for target in matrix:
        service, repo = target["service"], target["repo"]
        row = {"service": service}
        try:
            api = GitHubTree(repo, source_token)
            head = api.resolve(target["ref"])
            row["head"] = head
            head_fp = compute(api, head, target)
            try:
                digest, base_rev = ghcr_latest(service, ghcr_user, ghcr_password)
                row["promoted"] = base_rev
                base_fp = compute(api, base_rev, target)
            except Unknown as exc:
                base_fp, digest = {"unknown": str(exc)}, ""
            inputs = compare(base_fp, head_fp)
            try:
                builder = provenance_builder(digest, ci_token) if digest else ""
                if not builder:
                    raise Unknown("no promoted digest")
                old_text, old_services = workflow_at(builder, ci_token)
                old = recipe(old_services.get(service, {}), old_text) if service in old_services else {"unknown": "service absent"}
            except Unknown as exc:
                old = {"unknown": str(exc)}
            recipe_state = compare(old, recipe(target, current_workflow))
            row.update(
                inputs=inputs, recipe=recipe_state, verdict=verdict(inputs, recipe_state),
                head_fp=head_fp.get("fingerprint", ""), reason=head_fp.get("unknown") or base_fp.get("unknown") or old.get("unknown", ""),
                caveats=head_fp.get("caveats", []),
                changed=changed_paths(base_fp, head_fp)[:8] if inputs == "changed" else [],
            )
        except Unknown as exc:
            row.update(inputs="unknown", recipe="unknown", verdict="would-build (unknown)", reason=str(exc))
        rows.append(row)
        print(
            f"::notice title=input-shadow {service}::{row['verdict']} "
            f"(inputs={row.get('inputs')}, recipe={row.get('recipe')}, "
            f"head={row.get('head', '?')[:12]}, promoted={row.get('promoted', '?')[:12]})"
            + (f" reason: {row['reason'][:180]}" if row.get("reason") else "")
        )
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("## Input fingerprint shadow (no build is skipped)\n\n")
            handle.write("| image | verdict | inputs | recipe | head | promoted | first changed paths / reason |\n|---|---|---|---|---|---|---|\n")
            for r in rows:
                detail = ", ".join(f"`{p}`" for p in r.get("changed", [])) or r.get("reason", "")
                if r.get("caveats"):
                    detail += " (caveat: " + "; ".join(r["caveats"]) + ")"
                handle.write(
                    f"| {r['service']} | {r['verdict']} | {r.get('inputs')} | {r.get('recipe')} | "
                    f"`{r.get('head', '?')[:7]}` | `{r.get('promoted', '?')[:7]}` | {detail[:300]} |\n"
                )
    print(json.dumps(rows, sort_keys=True))
    return 0


def history(args: argparse.Namespace, services: dict[str, dict]) -> int:
    """Local replay: would each recent commit, as a candidate, need a build?

    Compared against the promoted baseline (what a skip would reuse) and
    against the first parent (what that one commit changed).  The recipe is
    the same for every row (one yueto-ci checkout), so only inputs vary.
    """
    git = LocalGit(args.repo)
    entries = [e for e in services.values() if e["group"] == args.group]
    if not entries:
        print(f"unknown group {args.group}", file=sys.stderr)
        return 2
    baseline = git.resolve(args.baseline)
    base_fps = {e["service"]: compute(git, baseline, e) for e in entries}
    commits = git._git("rev-list", "--first-parent", f"-n{args.n}", git.resolve(args.head)).decode().split()
    cache: dict[tuple[str, str], dict] = {}

    def fp(rev: str, entry: dict) -> dict:
        key = (rev, entry["service"])
        if key not in cache:
            cache[key] = compute(git, rev, entry)
        return cache[key]

    rows = []
    for sha in commits:
        subject = git._git("show", "-s", "--format=%s", sha).decode().strip()
        parent = git._git("rev-parse", f"{sha}^1").decode().strip()
        row = {"commit": sha, "subject": subject, "images": {}}
        for e in entries:
            head = fp(sha, e)
            vs_base = compare(base_fps[e["service"]], head)
            row["images"][e["service"]] = {
                "vs_promoted": verdict(vs_base, "unchanged"),
                "vs_parent": compare(fp(parent, e), head),
                "changed_vs_promoted": len(changed_paths(base_fps[e["service"]], head)) if vs_base == "changed" else 0,
                "unknown": head.get("unknown", ""),
            }
        rows.append(row)
    print(json.dumps({"group": args.group, "baseline": baseline, "rows": rows}, indent=2))
    return 0
