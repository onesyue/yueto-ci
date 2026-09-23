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
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SCHEMA = "yue-input-fingerprint/1"
RECIPE_SCHEMA = "yue-build-recipe/1"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
PINNED_IMAGE = re.compile(r"@sha256:[0-9a-f]{64}$")
ROOT = Path(__file__).resolve().parents[1]


class Unknown(Exception):
    """The inputs cannot be proved; callers must treat this as changed."""


# ---------------------------------------------------------------- tree sources


class LocalGit:
    """Read a commit's tree and blobs straight from git objects.

    Never reads the working tree: untracked or modified files are not what
    the central builder sees (it checks out the exact commit).
    """

    def __init__(self, repo: str | os.PathLike):
        self.repo = str(repo)

    def _git(self, *args: str) -> bytes:
        proc = subprocess.run(
            ["git", "-C", self.repo, *args], capture_output=True, check=False
        )
        if proc.returncode != 0:
            raise Unknown(f"git {' '.join(args[:2])} failed: {proc.stderr.decode(errors='replace').strip()[:200]}")
        return proc.stdout

    def resolve(self, rev: str) -> str:
        sha = self._git("rev-parse", "--verify", f"{rev}^{{commit}}").decode().strip()
        if not SHA40.match(sha):
            raise Unknown(f"cannot resolve {rev}")
        return sha

    def entries(self, rev: str) -> dict[str, tuple[str, str, str]]:
        out = self._git("ls-tree", "-r", "-z", "--full-tree", rev)
        result: dict[str, tuple[str, str, str]] = {}
        for record in out.split(b"\0"):
            if not record:
                continue
            meta, _, path = record.partition(b"\t")
            mode, kind, oid = meta.decode().split(" ")
            result[path.decode("utf-8", "surrogateescape")] = (mode, kind, oid)
        return result

    def blob(self, oid: str) -> bytes:
        return self._git("cat-file", "blob", oid)


class GitHubTree:
    """The same data through the GitHub REST API (CI planning job)."""

    def __init__(self, repo: str, token: str, api: str = "https://api.github.com"):
        if not re.fullmatch(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+", repo):
            raise Unknown(f"invalid repository name {repo!r}")
        self.repo, self.token, self.api = repo, token, api.rstrip("/")

    def _get(self, path: str) -> dict:
        request = urllib.request.Request(
            f"{self.api}/repos/{self.repo}/{path}",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise Unknown(f"GitHub API {path.split('?')[0]} unavailable: {exc}") from exc

    def resolve(self, rev: str) -> str:
        sha = self._get(f"commits/{urllib.parse.quote(rev, safe='')}").get("sha", "")
        if not SHA40.match(sha):
            raise Unknown(f"cannot resolve {rev}")
        return sha

    def entries(self, rev: str) -> dict[str, tuple[str, str, str]]:
        tree = self._get(f"git/trees/{urllib.parse.quote(rev, safe='')}?recursive=1")
        if tree.get("truncated") is not False:
            # The recursive endpoint silently drops entries past its limit.
            raise Unknown("GitHub tree listing truncated or malformed")
        result = {}
        for item in tree.get("tree", []):
            if item.get("type") in ("blob", "commit"):
                result[item["path"]] = (item["mode"], item["type"], item["sha"])
        return result

    def blob(self, oid: str) -> bytes:
        body = self._get(f"git/blobs/{oid}")
        if body.get("encoding") != "base64":
            raise Unknown(f"blob {oid} has unexpected encoding")
        return base64.b64decode(body.get("content", ""))


# ------------------------------------------------------- .dockerignore matching


def _clean(pattern: str) -> str:
    """filepath.Clean + ToSlash + strip one leading '/', like moby/patternmatcher."""
    absolute = pattern.startswith("/")
    parts: list[str] = []
    for part in pattern.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts and parts[-1] != "..":
                parts.pop()
            elif not absolute:
                parts.append(part)
            continue
        parts.append(part)
    return "/".join(parts) or "."


def _pattern_regex(pattern: str) -> re.Pattern[str]:
    """Port of moby/patternmatcher Pattern.compile (unix separator)."""
    out = "^"
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "*":
            if i + 1 < len(pattern) and pattern[i + 1] == "*":
                i += 1
                if i + 1 < len(pattern) and pattern[i + 1] == "/":
                    i += 1
                if i + 1 >= len(pattern):
                    out += ".*"
                else:
                    out += "(.*/)?"
            else:
                out += "[^/]*"
        elif ch == "?":
            out += "[^/]"
        elif ch in ".+()|{}$":
            out += "\\" + ch
        elif ch == "\\":
            if i + 1 < len(pattern):
                i += 1
                out += "\\" + pattern[i]
            else:
                out += "\\\\"
        elif ch in "[]":
            out += ch
        elif ch == "^":
            out += "\\^"
        else:
            out += ch
        i += 1
    return re.compile(out + "$")


class IgnoreRules:
    # Plain class, not a dataclass: importlib-by-path loaders (release-state,
    # tests) need not register the module in sys.modules first.
    def __init__(self) -> None:
        self.patterns: list[tuple[bool, re.Pattern[str]]] = []

    @classmethod
    def parse(cls, text: str) -> "IgnoreRules":
        rules = cls()
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            negate = line.startswith("!")
            if negate:
                line = line[1:].strip()
            cleaned = _clean(line)
            if cleaned == ".":
                continue
            rules.patterns.append((negate, _pattern_regex(cleaned)))
        return rules

    def ignored(self, path: str) -> bool:
        """moby PatternMatcher.MatchesOrParentMatches."""
        matched = False
        parts = path.split("/")
        parents = ["/".join(parts[: i + 1]) for i in range(len(parts) - 1)]
        for negate, regex in self.patterns:
            if negate != matched:
                continue
            hit = bool(regex.match(path)) or any(regex.match(p) for p in parents)
            if hit:
                matched = not negate
        return matched


# ------------------------------------------------------------ Dockerfile facts


class DockerfileFacts:
    def __init__(self) -> None:
        self.sources: list[str] = []          # context-relative COPY/ADD/bind sources
        self.external_images: list[str] = []
        self.syntax = ""
        self.caveats: list[str] = []
        self.problems: list[str] = []         # any entry => unknown


HEREDOC = re.compile(r"<<(-?)([\"']?)([A-Za-z_][A-Za-z0-9_]*)\2")


def _logical_lines(text: str) -> tuple[list[str], str]:
    """Join continuations, drop comments, skip heredoc bodies."""
    lines = text.splitlines()
    escape = "\\"
    syntax = ""
    for raw in lines:  # parser directives only at the very top
        m = re.match(r"^#\s*([a-zA-Z]+)\s*=\s*(\S+)\s*$", raw)
        if not m:
            break
        key = m.group(1).lower()
        if key == "escape":
            escape = m.group(2)
        elif key == "syntax":
            syntax = m.group(2)
    logical: list[str] = []
    buf = ""
    i = 0
    while i < len(lines):
        raw = lines[i]
        i += 1
        stripped = raw.strip()
        if stripped.startswith("#") or (not stripped and buf):
            continue
        if not stripped:
            continue
        if stripped.endswith(escape):
            buf += stripped[: -len(escape)] + " "
            continue
        line = (buf + stripped).strip()
        buf = ""
        heredocs = HEREDOC.finditer(line) if line.split(" ", 1)[0].upper() in ("RUN", "COPY", "ADD") else ()
        for m in heredocs:
            strip_tabs, _, word = m.groups()
            while i < len(lines):
                body = lines[i]
                i += 1
                if (body.lstrip("\t") if strip_tabs else body) == word:
                    break
            else:
                raise Unknown(f"unterminated heredoc {word}")
        logical.append(line)
    if buf:
        logical.append(buf.strip())
    return logical, syntax


def _split_args(rest: str) -> list[str]:
    rest = rest.strip()
    if rest.startswith("["):
        try:
            values = json.loads(rest)
        except ValueError as exc:
            raise Unknown(f"unparseable JSON-form instruction: {rest[:60]}") from exc
        if not all(isinstance(v, str) for v in values):
            raise Unknown("non-string JSON-form argument")
        return values
    return rest.split()


def parse_dockerfile(text: str) -> DockerfileFacts:
    facts = DockerfileFacts()
    logical, facts.syntax = _logical_lines(text)
    if facts.syntax and not PINNED_IMAGE.search(facts.syntax):
        facts.caveats.append(
            f"floating Dockerfile frontend `# syntax={facts.syntax}` (not digest-pinned)"
        )
    stages: list[str] = []
    for line in logical:
        word, _, rest = line.partition(" ")
        instr = word.upper()
        if instr == "FROM":
            tokens = [t for t in rest.split() if not t.startswith("--")]
            if not tokens:
                facts.problems.append("FROM without image")
                continue
            image = tokens[0]
            internal = image == "scratch" or image.lower() in stages
            if len(tokens) >= 3 and tokens[1].upper() == "AS":
                stages.append(tokens[2].lower())
            if internal:
                continue
            if "$" in image:
                facts.problems.append(f"FROM image uses a build arg: {image}")
            elif not PINNED_IMAGE.search(image):
                facts.problems.append(f"FROM image not digest-pinned: {image}")
            else:
                facts.external_images.append(image)
        elif instr in ("COPY", "ADD"):
            args = _split_args(rest)
            flags = [a for a in args if a.startswith("--")]
            operands = [a for a in args if not a.startswith("--")]
            if len(operands) < 2:
                facts.problems.append(f"{instr} with fewer than two operands")
                continue
            from_ref = ""
            has_checksum = False
            for flag in flags:
                name, _, value = flag.partition("=")
                if name == "--from":
                    from_ref = value
                elif name == "--exclude":
                    facts.problems.append(f"{instr} --exclude is not modelled")
                elif name == "--checksum":
                    has_checksum = True
            if from_ref:
                if from_ref.lower() in stages or from_ref.isdigit():
                    continue
                if not PINNED_IMAGE.search(from_ref):
                    facts.problems.append(f"{instr} --from image not digest-pinned: {from_ref}")
                else:
                    facts.external_images.append(from_ref)
                continue
            for src in operands[:-1]:
                if src.startswith("<<"):
                    continue  # heredoc: content is Dockerfile text
                if "://" in src or src.startswith("git@"):
                    if instr == "ADD" and has_checksum:
                        facts.caveats.append(f"remote ADD with --checksum: {src}")
                    else:
                        facts.problems.append(f"remote {instr} source without checksum: {src}")
                    continue
                if "$" in src:
                    facts.problems.append(f"{instr} source uses a variable: {src}")
                    continue
                facts.sources.append(_clean(src))
        elif instr == "RUN":
            for m in re.finditer(r"--mount=(\S+)", rest):
                opts = dict(
                    (kv.partition("=")[0], kv.partition("=")[2]) for kv in m.group(1).split(",")
                )
                kind = opts.get("type", "bind")
                if kind == "bind":
                    if opts.get("from"):
                        continue
                    src = opts.get("source", opts.get("src", "."))
                    if "$" in src:
                        facts.problems.append(f"bind mount source uses a variable: {src}")
                    else:
                        facts.sources.append(_clean(src))
                elif kind == "secret":
                    facts.problems.append("RUN secret mount is an unfingerprinted input")
        elif instr == "ONBUILD" and re.search(r"\b(COPY|ADD)\b", rest, re.I):
            facts.caveats.append("ONBUILD COPY/ADD (applies to child builds only)")
    return facts


def _source_regex(source: str) -> re.Pattern[str] | None:
    if not any(c in source for c in "*?["):
        return None
    out = ""
    for ch in source:
        if ch == "*":
            out += "[^/]*"
        elif ch == "?":
            out += "[^/]"
        elif ch in "[]":
            out += ch
        else:
            out += re.escape(ch)
    return re.compile(out + "$")


def selected(path: str, sources: list[str]) -> bool:
    for src in sources:
        if src == ".":
            return True
        regex = _source_regex(src)
        if regex is None:
            if path == src or path.startswith(src + "/"):
                return True
            continue
        depth = src.count("/") + 1
        prefix = "/".join(path.split("/")[:depth])
        if regex.match(prefix):
            return True
    return False


# ---------------------------------------------------------------- fingerprints


def _digest(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def load_services(path: Path | None = None) -> dict[str, dict]:
    data = json.loads((path or ROOT / "services.json").read_text(encoding="utf-8"))
    return {entry["service"]: entry for entry in data}


def compute(source, rev: str, entry: dict) -> dict:
    """Return {"fingerprint", "files", ...} or {"unknown": reason, ...}."""
    result: dict = {"schema": SCHEMA, "service": entry["service"], "revision": rev}
    try:
        if entry.get("context", ".") != ".":
            raise Unknown(f"non-root build context {entry.get('context')!r} is not modelled")
        dockerfile = _clean(entry["dockerfile"])
        tree = source.entries(rev)
        if dockerfile not in tree:
            raise Unknown(f"{dockerfile} not present at {rev[:12]}")
        facts = parse_dockerfile(source.blob(tree[dockerfile][2]).decode("utf-8"))
        result["caveats"] = facts.caveats
        if facts.problems:
            raise Unknown("; ".join(facts.problems))
        specific = dockerfile + ".dockerignore"
        ignore_path = specific if specific in tree else (".dockerignore" if ".dockerignore" in tree else "")
        rules = IgnoreRules.parse(source.blob(tree[ignore_path][2]).decode("utf-8")) if ignore_path else IgnoreRules()
        docker_dir = dockerfile.rpartition("/")[0]
        dead = sorted(
            p for p in tree
            if p.rpartition("/")[0] == docker_dir and p.rsplit("/", 1)[-1] == ".dockerignore"
            and p != ignore_path
        )
        attributes = sorted(p for p in tree if p.rsplit("/", 1)[-1] == ".gitattributes")
        for attr in attributes:
            if re.search(rb"(^|\s)filter=", source.blob(tree[attr][2])):
                raise Unknown(f"{attr} declares a checkout filter")
        files = sorted(
            [path, tree[path][0], tree[path][2]]
            for path in tree
            if selected(path, facts.sources) and not rules.ignored(path)
        )
        if not files:
            raise Unknown("no build-context file selected (scan floor)")
        payload = {
            "schema": SCHEMA,
            "context": ".",
            "dockerfile": [dockerfile, tree[dockerfile][2]],
            "ignore": [ignore_path, tree[ignore_path][2]] if ignore_path else None,
            "gitattributes": [[p, tree[p][2]] for p in attributes],
            "files": files,
        }
        result.update(
            fingerprint=_digest(payload),
            dockerfile=dockerfile,
            ignore_file=ignore_path or None,
            dead_ignore_files=dead,
            sources=sorted(set(facts.sources)),
            external_images=sorted(set(facts.external_images)),
            file_count=len(files),
            files=files,
        )
    except Unknown as exc:
        result["unknown"] = str(exc)
    return result


BUILD_JOB = re.compile(r"(?ms)^  build:[ \t]*\n.*?(?=^  [A-Za-z0-9_-]+:[ \t]*$|\Z)")


def recipe(entry: dict, workflow_text: str) -> dict:
    match = BUILD_JOB.search(workflow_text)
    if not match:
        return {"schema": RECIPE_SCHEMA, "unknown": "build job not found in build.yml"}
    stable = {k: v for k, v in entry.items() if k != "ref"}
    return {
        "schema": RECIPE_SCHEMA,
        "fingerprint": _digest({"schema": RECIPE_SCHEMA, "service": stable, "build_job": match.group(0).rstrip()}),
    }


def compare(base: dict, head: dict) -> str:
    """unchanged | changed | unknown -- unknown never collapses into unchanged."""
    if "unknown" in base or "unknown" in head or "fingerprint" not in base or "fingerprint" not in head:
        return "unknown"
    return "unchanged" if base["fingerprint"] == head["fingerprint"] else "changed"


def changed_paths(base: dict, head: dict) -> list[str]:
    a = {p: (m, o) for p, m, o in base.get("files", [])}
    b = {p: (m, o) for p, m, o in head.get("files", [])}
    return sorted(p for p in a.keys() | b.keys() if a.get(p) != b.get(p))


def verdict(inputs: str, recipe_state: str) -> str:
    if inputs == "unchanged" and recipe_state == "unchanged":
        return "would-skip"
    if inputs == "unknown" or recipe_state == "unknown":
        return "would-build (unknown)"
    return "would-build"


# ----------------------------------------------------------- CI shadow support


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


# ------------------------------------------------------------------------ CLI


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
    args = parser.parse_args(argv)

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
