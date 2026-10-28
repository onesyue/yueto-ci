#!/usr/bin/env python3
"""Static UI units: scratch images, unit-scoped inputs, frontend-only checks.

Each unit is an image in services.json and a validation profile in
validation-targets.json. The image build context stays the source
repository root (the same context/dockerfile convention as the other
services). The fingerprint, though, may contain only that unit's path
and its Dockerfile. Promotion still goes through promote-source-gate.py
and the SBOM, cosign, and SLSA steps. Poll dispatches a unit with
promote=true only when those inputs changed; it never deploys.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKS = ["lint", "tsc", "unit", "a11y", "bundle-budget"]
# Index digest of library/node:24-bookworm-slim (linux manifest list), 2026-10-28.
NODE_IMAGE = (
    "node:24-bookworm-slim"
    "@sha256:8579e5fce559544b50072d05cc5d3b84b6a14d0989ae56c331d9e983a36a21f1"
)
SOURCE_ONLY_KEYS = {"service", "group", "repo", "ref", "validation"}
UI_TARGET_KEYS = SOURCE_ONLY_KEYS | {
    "unit_path", "checks", "frontend_step", "package_manager",
}
SERVICE_KEYS = SOURCE_ONLY_KEYS | {"context", "dockerfile", "platforms"}


class ScopeError(Exception):
    """A ui-* service has no usable unit scope. Callers must not guess."""


def _load(name: str) -> list:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def services() -> list[dict]:
    return _load("services.json")


def targets() -> list[dict]:
    return _load("validation-targets.json")


def ui_services() -> list[dict]:
    return [row for row in services() if str(row.get("service", "")).startswith("ui-")]


def ui_targets() -> list[dict]:
    return [row for row in targets() if str(row.get("service", "")).startswith("ui-")]


def _rel(path: object) -> str:
    if not isinstance(path, str) or not path or path.startswith("/") or path.endswith("/"):
        return ""
    parts = path.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return ""
    return path


def unit_scope(entry: dict) -> str | None:
    """Unit path for a static UI image, or None for every other service.

    A ui-* service with a missing or unsafe validation target raises
    ScopeError so the fingerprint becomes unknown instead of widening.
    """
    service = entry.get("service")
    if not isinstance(service, str) or not service.startswith("ui-"):
        return None
    matches = [row for row in ui_targets() if row.get("service") == service]
    if len(matches) != 1:
        raise ScopeError(f"{service} has no single validation target")
    path = _rel(matches[0].get("unit_path"))
    if not path:
        raise ScopeError(f"{service} unit_path is unsafe")
    return path


def path_in_unit(path: str, unit_path: str, dockerfile: str) -> bool:
    """True for the unit tree, the unit Dockerfile, and its BuildKit ignore file."""
    if path == dockerfile or path == dockerfile + ".dockerignore":
        return True
    return path == unit_path or path.startswith(unit_path + "/")


def decide_unit(state: str) -> bool:
    """Whether poll may dispatch this unit with promote=true.

    ``changed`` is a proved unit-input difference. ``absent`` is the first
    image (no promoted revision to compare). ``unchanged`` and ``unknown``
    do not auto-promote: unknown is not evidence that the unit path changed.
    """
    return state in {"changed", "absent"}


def _manifest_script() -> str:
    return """const fs = require('fs');
const crypto = require('crypto');
const path = require('path');
const commit = process.env.COMMIT || '';
if (!/^[0-9a-f]{40}$/.test(commit)) {
  console.error('COMMIT must be the 40-hex source revision');
  process.exit(1);
}
function walk(dir, out) {
  for (const name of fs.readdirSync(dir)) {
    const abs = path.join(dir, name);
    const rel = path.relative('dist', abs).split(path.sep).join('/');
    if (fs.statSync(abs).isDirectory()) walk(abs, out);
    else {
      const sha256 = crypto.createHash('sha256').update(fs.readFileSync(abs)).digest('hex');
      out.push({path: rel, sha256});
    }
  }
}
const files = [];
walk('dist', files);
files.sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
const req = JSON.parse(fs.readFileSync('ui-requires.json', 'utf8'));
if (!Object.prototype.hasOwnProperty.call(req, 'requires_backend')) {
  console.error('ui-requires.json is missing requires_backend');
  process.exit(1);
}
fs.mkdirSync('/out', {recursive: true});
fs.writeFileSync('/out/ui-manifest.json', JSON.stringify({
  files,
  source_revision: commit,
  requires_backend: req.requires_backend,
}) + '\\n');
"""


def render_dockerfile(service: str) -> str:
    """Dockerfile text that belongs in the source repo at services/<service>/Dockerfile."""
    rows = [row for row in ui_targets() if row.get("service") == service]
    images = [row for row in ui_services() if row.get("service") == service]
    if len(rows) != 1 or len(images) != 1:
        raise ScopeError(f"{service} is not a registered static UI unit")
    target, image = rows[0], images[0]
    if image.get("dockerfile") != f"services/{service}/Dockerfile":
        raise ScopeError(f"{service} dockerfile path drifted")
    if image.get("context") != ".":
        raise ScopeError(f"{service} context must stay the source repository root")
    unit = unit_scope(image)
    manager = target.get("package_manager")
    if manager == "npm":
        install = "npm ci --ignore-scripts \\\n && npm run build \\\n"
    elif manager == "pnpm":
        install = (
            "corepack enable \\\n"
            ' && PM=$(node -p "require(\'./package.json\').packageManager || \'\'") \\\n'
            ' && [ -n "$PM" ] \\\n'
            ' && corepack prepare "$PM" --activate \\\n'
            " && pnpm install --frozen-lockfile --ignore-scripts \\\n"
            " && pnpm run build \\\n"
        )
    else:
        raise ScopeError(f"{service} package_manager is not npm or pnpm")
    script = _manifest_script()
    return (
        f"FROM {NODE_IMAGE} AS build\n"
        "ARG COMMIT\n"
        "ENV COMMIT=${COMMIT}\n"
        "WORKDIR /src\n"
        f"COPY {unit}/ /src/unit/\n"
        "WORKDIR /src/unit\n"
        f"RUN {install}"
        " && node <<'MANIFEST'\n"
        f"{script}"
        "MANIFEST\n"
        "\n"
        "FROM scratch\n"
        "COPY --from=build /src/unit/dist /dist\n"
        "COPY --from=build /out/ui-manifest.json /ui-manifest.json\n"
    )


def _npm_commands() -> list[list[str]]:
    return [
        ["npm", "ci", "--ignore-scripts"],
        ["npm", "run", "lint"],
        ["npx", "--no-install", "tsc", "--noEmit"],
        ["npm", "test"],
        ["npm", "run", "test:a11y"],
        ["npm", "run", "bundle-budget"],
    ]


def _pnpm_commands(package_name: str | None) -> list[list[str]]:
    prefix = ["pnpm", "--filter", package_name] if package_name else ["pnpm"]
    return [
        ["pnpm", "install", "--frozen-lockfile", "--ignore-scripts"],
        [*prefix, "run", "lint"],
        [*prefix, "exec", "tsc", "--noEmit"],
        [*prefix, "test"],
        [*prefix, "run", "test:a11y"],
        [*prefix, "run", "bundle-budget"],
    ]


def validation_plan(source: Path, validation: str) -> tuple[Path, list[list[str]], list[list[str]]]:
    """Return (workdir, prelude, checks) for one UI validation.

    Prelude is the package-manager pin used by the existing frontend steps.
    Checks are only lint, tsc, unit, a11y, and bundle budget, in that order.
    """
    matches = [row for row in ui_targets() if row.get("validation") == validation]
    if len(matches) != 1:
        raise ScopeError(f"{validation} is not a static UI validation")
    target = matches[0]
    if target.get("checks") != CHECKS:
        raise ScopeError(f"{validation} checks are not the frontend fastlane")
    unit = source / target["unit_path"]
    if not unit.is_dir():
        raise ScopeError(f"{validation} unit path is not a directory: {target['unit_path']}")
    manager = target.get("package_manager")
    package = json.loads((unit / "package.json").read_text(encoding="utf-8"))
    if manager == "npm":
        return unit, [], _npm_commands()
    if manager != "pnpm":
        raise ScopeError(f"{validation} package_manager is not npm or pnpm")
    pin = package.get("packageManager") or ""
    if not isinstance(pin, str) or not pin:
        raise ScopeError(f"{validation} package.json has no packageManager pin")
    prelude = [
        ["corepack", "enable"],
        ["corepack", "install", "--global", pin],
    ]
    # Workspace layout (the YueBoard frontend step): one root install, then
    # the named package only. A unit-local lockfile installs in the unit.
    if (source / "pnpm-workspace.yaml").is_file():
        name = package.get("name")
        if not isinstance(name, str) or not name:
            raise ScopeError(f"{validation} workspace package has no name")
        return source, prelude, _pnpm_commands(name)
    return unit, prelude, _pnpm_commands(None)


def run_validate(source: Path, validation: str) -> None:
    workdir, prelude, checks = validation_plan(source, validation)
    for command in [*prelude, *checks]:
        subprocess.run(command, cwd=workdir, check=True)


def _fingerprint():
    spec = importlib.util.spec_from_file_location(
        "ui_static_fingerprint", ROOT / "scripts" / "input-fingerprint.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _gh_json(path: str) -> dict:
    proc = subprocess.run(
        ["gh", "api", path], capture_output=True, text=True, timeout=60, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip()[-300:] or f"gh api {path} failed")
    value = json.loads(proc.stdout)
    if not isinstance(value, dict):
        raise RuntimeError(f"gh api {path} did not return an object")
    return value


def _promoted_revision(fp, service: str) -> str | None:
    user = os.environ.get("GHCR_USER", "")
    password = os.environ.get("GHCR_PASSWORD", "")
    try:
        _digest, revision = fp.ghcr_latest(service, user, password)
    except fp.Unknown as exc:
        text = str(exc)
        if "404" in text or "Not Found" in text:
            return None
        raise
    return revision


def poll_dispatches() -> list[dict]:
    """UI units whose unit inputs changed, or that have no promoted image yet."""
    fp = _fingerprint()
    token = os.environ.get("GH_API_TOKEN") or os.environ.get("GH_TOKEN") or ""
    by_service = {row["service"]: row for row in ui_targets()}
    heads: dict[str, tuple[str, object]] = {}
    rows: list[dict] = []
    for image in ui_services():
        service = image["service"]
        target = by_service.get(service)
        if target is None or target.get("repo") != image.get("repo") or target.get("validation") != image.get("validation"):
            print(f"::error::{service} validation target does not match services.json", file=sys.stderr)
            raise SystemExit(1)
        repo = image["repo"]
        if repo not in heads:
            meta = _gh_json(f"repos/{repo}")
            branch = meta.get("default_branch")
            if not isinstance(branch, str) or not branch:
                print(f"::warning::{repo}: no default branch; not auto-promoting", file=sys.stderr)
                continue
            commit = _gh_json(f"repos/{repo}/commits/{branch}")
            sha = commit.get("sha")
            if not isinstance(sha, str) or len(sha) != 40:
                print(f"::warning::{repo}: HEAD is not a full SHA; not auto-promoting", file=sys.stderr)
                continue
            heads[repo] = (sha, fp.GitHubTree(repo, token))
        sha, api = heads[repo]
        try:
            baseline = _promoted_revision(fp, service)
        except fp.Unknown as exc:
            print(f"::warning::{service}: promoted revision unreadable ({exc}); not auto-promoting", file=sys.stderr)
            continue
        if baseline is None:
            if decide_unit("absent"):
                rows.append({"group": service, "sha": sha, "repo": repo})
            continue
        at_base = fp.compute(api, baseline, image)
        at_head = fp.compute(api, sha, image)
        state = fp.compare(at_base, at_head)
        if decide_unit(state):
            rows.append({"group": service, "sha": sha, "repo": repo})
        elif state == "unknown":
            reason = at_head.get("unknown") or at_base.get("unknown") or "unknown"
            print(f"::warning::{service}: inputs unknown ({reason}); not auto-promoting", file=sys.stderr)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("poll", help="print UI units to dispatch with promote=true")
    validate = sub.add_parser("validate", help="run one unit's frontend fastlane")
    validate.add_argument("--validation", default=os.environ.get("UI_VALIDATION", ""))
    validate.add_argument("--source", default=".")
    docker = sub.add_parser("dockerfile", help="print the source-repo Dockerfile")
    docker.add_argument("service")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "poll":
            json.dump(poll_dispatches(), sys.stdout)
            sys.stdout.write("\n")
            return 0
        if args.cmd == "dockerfile":
            sys.stdout.write(render_dockerfile(args.service))
            return 0
        if not args.validation:
            print("::error::UI validation name is required", file=sys.stderr)
            return 2
        run_validate(Path(args.source).resolve(), args.validation)
        return 0
    except ScopeError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        return exc.returncode or 1
    except (OSError, json.JSONDecodeError, RuntimeError, KeyError, TypeError) as exc:
        print(f"::error::{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
