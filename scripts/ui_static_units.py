#!/usr/bin/env python3
"""Static UI units: scratch images, unit-scoped inputs, frontend-only checks.

Each unit is an image in services.json and a validation profile in
validation-targets.json. The image build context stays the source
repository root (the same context/dockerfile convention as the other
services). A package-layout unit's fingerprint contains that unit's path
and its Dockerfile. A pnpm-workspace unit (ui-board-web) also contains the
root package.json, pnpm-workspace.yaml, pnpm-lock.yaml, and the workspace
packages required to install and build its artifact paths. A Dockerfile
that copies a path outside that set is unknown. Promotion still goes through
promote-source-gate.py and the SBOM, cosign, and SLSA steps. Poll
dispatches a unit with promote=true only when those inputs changed; it
never deploys.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
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
    "layout", "artifact_paths",
}
PACKAGE_NAME = re.compile(r"^(?:@[A-Za-z0-9._-]+/)?[A-Za-z0-9._-]+$")
DEP_FIELDS = ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies")
ROOT_MANIFESTS = ("package.json", "pnpm-workspace.yaml", "pnpm-lock.yaml")
# Board's build runs contract tests against these repository-level inputs.
# Keep backend and shared-test COPY sources at file granularity.
BOARD_BUILD_FILES = (
    "schema-floor.txt",
    "internal/platform/featureflag/flags.json",
    "internal/platform/errcode/errcode.go",
    "internal/platform/ticketcategory/ticketcategory.go",
    "internal/platform/audit/audit.go",
    "test/frontend/session-rejection.ts",
    "test/frontend/reload-guard.ts",
    "docs/contracts/yueboard-economy.golden.json",
)
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


def source_covered(src: str, allowed: str) -> bool:
    """True when a COPY source is exactly an allowed input or a file inside it."""
    if not src or src == "." or src.startswith("/") or src.startswith("..") or "/../" in src:
        return False
    return src == allowed or src.startswith(allowed + "/")


def path_in_inputs(path: str, allowed: list[str], dockerfile: str) -> bool:
    """True for the unit Dockerfile and every file under an allowed COPY source."""
    if path == dockerfile or path == dockerfile + ".dockerignore":
        return True
    return any(source_covered(path, item) for item in allowed)


def _target(service: str) -> dict:
    matches = [row for row in ui_targets() if row.get("service") == service]
    if len(matches) != 1:
        raise ScopeError(f"{service} is not a registered static UI unit")
    return matches[0]


def _layout(target: dict) -> str:
    layout = target.get("layout")
    if layout not in ("package", "pnpm-workspace"):
        raise ScopeError(f"{target.get('service')} layout is not package or pnpm-workspace")
    return layout


def _artifact_paths(target: dict) -> list[str]:
    raw = target.get("artifact_paths")
    if not isinstance(raw, list) or not raw:
        raise ScopeError(f"{target.get('service')} artifact_paths is empty")
    paths = []
    for item in raw:
        path = _rel(item) if isinstance(item, str) else ""
        if not path:
            raise ScopeError(f"{target.get('service')} artifact path is unsafe")
        paths.append(path)
    if len(paths) != len(set(paths)):
        raise ScopeError(f"{target.get('service')} artifact_paths has a duplicate")
    unit = _rel(target.get("unit_path"))
    if unit not in paths:
        raise ScopeError(f"{target.get('service')} unit_path is not an artifact path")
    return paths


def _strip_yaml_comment(line: str) -> str:
    out: list[str] = []
    quote = ""
    for char in line:
        if quote:
            if char == quote:
                quote = ""
        elif char in ("'", '"'):
            quote = char
        elif char == "#":
            break
        out.append(char)
    return "".join(out).rstrip()


def parse_pnpm_workspace_packages(text: str) -> list[str]:
    """Package globs from a pnpm-workspace.yaml. Other keys are ignored."""
    packages: list[str] = []
    in_list = False
    for raw in text.splitlines():
        line = _strip_yaml_comment(raw)
        if not line.strip():
            continue
        stripped = line.strip()
        indented = line[:1] in (" ", "\t") or stripped.startswith("- ")
        if not indented:
            in_list = False
            if stripped == "packages:" or stripped.startswith("packages:"):
                rest = stripped[len("packages:"):].strip()
                if rest.startswith("[") and rest.endswith("]"):
                    for part in rest[1:-1].split(","):
                        value = part.strip().strip("'\"")
                        if value:
                            packages.append(value)
                elif rest:
                    packages.append(rest.strip("'\""))
                else:
                    in_list = True
            continue
        if in_list and stripped.startswith("- "):
            value = stripped[2:].strip().strip("'\"")
            if value:
                packages.append(value)
    if not packages:
        raise ScopeError("pnpm-workspace.yaml has no packages")
    return packages


def _glob_regex(pattern: str) -> re.Pattern[str]:
    body = pattern.strip()
    if body.startswith("./"):
        body = body[2:]
    body = body.rstrip("/")
    if not body:
        raise ScopeError("empty pnpm workspace pattern")
    out: list[str] = []
    index = 0
    while index < len(body):
        if body.startswith("**/", index):
            out.append("(?:.*/)?")
            index += 3
        elif body.startswith("**", index):
            out.append(".*")
            index += 2
        elif body[index] == "*":
            out.append("[^/]*")
            index += 1
        elif body[index] == "?":
            out.append("[^/]")
            index += 1
        else:
            out.append(re.escape(body[index]))
            index += 1
    return re.compile("^" + "".join(out) + "$")


def match_workspace_dirs(patterns: list[str], directories: list[str]) -> list[str]:
    """Last matching pnpm-workspace pattern wins, including `!` exclusions."""
    compiled = []
    for pattern in patterns:
        negate = pattern.startswith("!")
        compiled.append((negate, _glob_regex(pattern[1:] if negate else pattern)))
    chosen = []
    for directory in sorted(set(directories)):
        matched = False
        for negate, regex in compiled:
            if regex.match(directory):
                matched = not negate
        if matched:
            chosen.append(directory)
    return chosen


def _read_json(read_text, path: str) -> dict:
    text = read_text(path)
    if text is None:
        raise ScopeError(f"{path} is missing")
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ScopeError(f"{path} is not JSON") from exc
    if not isinstance(value, dict):
        raise ScopeError(f"{path} is not an object")
    return value


def _dep_items(package: dict, path: str) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for field in DEP_FIELDS:
        value = package.get(field)
        if value is None:
            continue
        if not isinstance(value, dict):
            raise ScopeError(f"{path} {field} is not an object")
        for name, spec in value.items():
            if not isinstance(name, str) or not isinstance(spec, str):
                raise ScopeError(f"{path} {field} has a non-string entry")
            items.append((name, spec))
    return items


def _resolve_rel(from_dir: str, rel: str) -> str:
    base = [] if from_dir in ("", ".") else from_dir.split("/")
    for part in rel.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not base:
                raise ScopeError(f"workspace path escapes the repository: {rel}")
            base.pop()
            continue
        base.append(part)
    if not base:
        raise ScopeError("workspace dependency resolves to the repository root")
    return "/".join(base)


def _workspace_target(spec: str, from_dir: str, name: str, by_name: dict[str, str]) -> str | None:
    if spec.startswith("workspace:"):
        rest = spec[len("workspace:"):]
        if rest.startswith("/") or rest.startswith("..") or rest.startswith("./") or rest.startswith("."):
            if rest.startswith("/"):
                raise ScopeError(f"workspace dependency {name} has an absolute path")
            return _resolve_rel(from_dir, rest)
        if name not in by_name:
            raise ScopeError(f"workspace dependency {name} ({spec}) is not in the workspace")
        return by_name[name]
    if spec.startswith("file:") or spec.startswith("link:"):
        rest = spec.split(":", 1)[1]
        if rest.startswith("/"):
            raise ScopeError(f"{spec} is outside the build context")
        if rest.startswith("."):
            return _resolve_rel(from_dir, rest)
    return None


def _package_dirs(paths: list[str]) -> list[str]:
    found = []
    for path in paths:
        if not path.endswith("/package.json") or path == "package.json":
            continue
        parts = path.split("/")
        if "node_modules" in parts or ".git" in parts:
            continue
        found.append(path[: -len("/package.json")])
    return found


def _members(read_text, paths: list[str]) -> dict[str, str]:
    text = read_text("pnpm-workspace.yaml")
    if text is None:
        raise ScopeError("pnpm-workspace.yaml is missing")
    selected = match_workspace_dirs(parse_pnpm_workspace_packages(text), _package_dirs(paths))
    by_name: dict[str, str] = {}
    for directory in selected:
        package = _read_json(read_text, f"{directory}/package.json")
        name = package.get("name")
        if not isinstance(name, str) or not name:
            raise ScopeError(f"{directory}/package.json has no name")
        if name in by_name:
            raise ScopeError(f"duplicate workspace package name {name}")
        by_name[name] = directory
    return by_name


def _safe_copy_path(path: str) -> str:
    cleaned = _rel(path)
    if not cleaned or not re.fullmatch(r"[A-Za-z0-9._@+/-]+", cleaned):
        raise ScopeError(f"unsafe workspace path {path}")
    return cleaned


def workspace_plan(read_text, paths: list[str], artifact_paths: list[str], service: str) -> dict:
    """Root manifests plus the workspace packages the artifact builds need.

    `pnpm install --frozen-lockfile` runs at the repository root. Only the
    artifact packages and their workspace-protocol (and relative file:/link:)
    dependency closure are copied; other workspace members stay out.
    """
    root = _read_json(read_text, "package.json")
    pin = root.get("packageManager")
    if not isinstance(pin, str) or not pin.startswith("pnpm@"):
        raise ScopeError(f"{service} root package.json packageManager must be a pnpm@ pin")
    root_files = []
    for name in ROOT_MANIFESTS:
        if read_text(name) is None:
            raise ScopeError(f"{service} workspace is missing {name}")
        root_files.append(name)
    if read_text(".npmrc") is not None:
        root_files.append(".npmrc")
    patches: list[str] = []
    pnpm_meta = root.get("pnpm")
    if pnpm_meta is not None:
        if not isinstance(pnpm_meta, dict):
            raise ScopeError(f"{service} root package.json pnpm field is not an object")
        patched = pnpm_meta.get("patchedDependencies") or {}
        if not isinstance(patched, dict):
            raise ScopeError(f"{service} pnpm.patchedDependencies is not an object")
        for key in sorted(patched):
            rel = patched[key]
            if not isinstance(rel, str):
                raise ScopeError(f"{service} patch for {key} is not a path")
            safe = _safe_copy_path(rel)
            if read_text(safe) is None:
                raise ScopeError(f"{service} patched dependency file is missing: {safe}")
            patches.append(safe)
    by_name = _members(read_text, paths)
    member_dirs = set(by_name.values())
    for directory in artifact_paths:
        if directory not in member_dirs:
            raise ScopeError(f"{directory} is not a pnpm workspace package")
    names: list[str] = []
    for directory in artifact_paths:
        package = _read_json(read_text, f"{directory}/package.json")
        name = package.get("name")
        if not isinstance(name, str) or PACKAGE_NAME.fullmatch(name) is None:
            raise ScopeError(f"{directory} package name is unsafe")
        names.append(name)
    copy_dirs: list[str] = []
    walked: set[str] = set()

    def covered(directory: str) -> bool:
        return any(directory == root_dir or directory.startswith(root_dir + "/") for root_dir in copy_dirs)

    def visit(directory: str) -> None:
        if directory in walked:
            return
        if directory in ("", "."):
            raise ScopeError(f"{service} workspace dependency resolves to the repository root")
        walked.add(directory)
        if not covered(directory):
            copy_dirs.append(_safe_copy_path(directory))
        package_path = f"{directory}/package.json"
        if read_text(package_path) is None:
            raise ScopeError(f"{service} workspace dependency has no {package_path}")
        package = _read_json(read_text, package_path)
        for name, spec in _dep_items(package, package_path):
            dest = _workspace_target(spec, directory, name, by_name)
            if dest:
                visit(dest)

    for directory in artifact_paths:
        visit(directory)
    for name, spec in _dep_items(root, "package.json"):
        dest = _workspace_target(spec, ".", name, by_name)
        if dest:
            visit(dest)
    build_files = []
    if service == "ui-board-web":
        for path in BOARD_BUILD_FILES:
            if read_text(path) is None:
                raise ScopeError(f"{service} build input is missing: {path}")
            build_files.append(path)
    return {
        "root_files": root_files,
        "patch_files": patches,
        "build_files": build_files,
        "package_dirs": sorted(copy_dirs),
        "package_names": names,
    }


def workspace_copy_sources(plan: dict) -> list[str]:
    return [*plan["root_files"], *plan["patch_files"], *plan["build_files"], *plan["package_dirs"]]


def _directory_reader(source: Path):
    def read_text(path: str) -> str | None:
        file = source / path
        if not file.is_file():
            return None
        try:
            return file.read_text(encoding="utf-8")
        except UnicodeError as exc:
            raise ScopeError(f"{path} is not utf-8") from exc

    def paths() -> list[str]:
        found = []
        for file in source.rglob("*"):
            if not file.is_file():
                continue
            rel = file.relative_to(source).as_posix()
            parts = rel.split("/")
            if "node_modules" in parts or ".git" in parts:
                continue
            found.append(rel)
        return found

    return read_text, paths


def allowed_copy_sources(entry: dict, read_text, paths: list[str]) -> list[str] | None:
    """COPY sources a ui-* Dockerfile may use, or None for every other service.

    A pnpm-workspace unit with no pnpm-workspace.yaml in the tree stays on
    the unit path so an older per-package layout remains measurable.
    """
    service = entry.get("service")
    if not isinstance(service, str) or not service.startswith("ui-"):
        return None
    target = _target(service)
    unit = unit_scope(entry)
    if unit is None:
        raise ScopeError(f"{service} has no unit scope")
    if _layout(target) == "package":
        return [unit]
    if read_text("pnpm-workspace.yaml") is None:
        return [unit]
    plan = workspace_plan(read_text, paths, _artifact_paths(target), service)
    return workspace_copy_sources(plan)


def _assert_package_is_self_contained(source: Path, unit: str, service: str) -> None:
    """Refuse a unit-only Dockerfile when the checkout is actually a workspace."""
    read_text, paths = _directory_reader(source)
    yaml = read_text("pnpm-workspace.yaml")
    if yaml is not None:
        members = match_workspace_dirs(parse_pnpm_workspace_packages(yaml), _package_dirs(paths()))
        if unit in members:
            raise ScopeError(
                f"{service} is a member of the repository pnpm workspace; "
                "unit-only COPY cannot see the workspace root"
            )
    package_path = f"{unit}/package.json"
    if read_text(package_path) is None:
        raise ScopeError(f"{service} unit package.json is missing")
    package = _read_json(read_text, package_path)
    for name, spec in _dep_items(package, package_path):
        if spec.startswith("workspace:"):
            raise ScopeError(f"{service} {package_path} depends on {name} via {spec}")
        if spec.startswith("file:") or spec.startswith("link:"):
            rest = spec.split(":", 1)[1]
            escaped = rest.startswith("/")
            if rest.startswith("."):
                dest = _resolve_rel(unit, rest)
                escaped = not (dest == unit or dest.startswith(unit + "/"))
            if escaped:
                raise ScopeError(f"{service} {package_path} depends on {name} via {spec}")


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


def _scratch_tail(script: str, run: str) -> str:
    return (
        f"FROM {NODE_IMAGE} AS build\n"
        "ARG COMMIT\n"
        "ENV COMMIT=${COMMIT}\n"
        "WORKDIR /src\n"
        f"{run}"
        " && node <<'MANIFEST'\n"
        f"{script}"
        "MANIFEST\n"
        "\n"
        "FROM scratch\n"
        "COPY --from=build /src/unit/dist /dist\n"
        "COPY --from=build /out/ui-manifest.json /ui-manifest.json\n"
    )


def _render_package_dockerfile(service: str, unit: str, manager: object) -> str:
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
    body = f"COPY {unit}/ /src/unit/\nWORKDIR /src/unit\nRUN {install}"
    return _scratch_tail(_manifest_script(), body)


def _render_workspace_dockerfile(plan: dict, unit: str) -> str:
    copies = [f"COPY {' '.join(plan['root_files'])} ./"]
    copies.extend(f"COPY {patch} {patch}" for patch in plan["patch_files"])
    copies.extend(f"COPY {path} {path}" for path in plan["build_files"])
    copies.extend(f"COPY {directory}/ {directory}/" for directory in plan["package_dirs"])
    filters = " ".join(f"--filter {name}" for name in plan["package_names"])
    artifacts = plan["package_dirs_to_build"]
    stage = ["mkdir -p " + " ".join(f"/src/unit/dist/{path}" for path in artifacts)]
    if len(artifacts) == 1:
        stage = [
            "mkdir -p /src/unit/dist",
            f"cp -a {artifacts[0]}/dist/. /src/unit/dist/",
        ]
    else:
        stage.extend(f"cp -a {path}/dist/. /src/unit/dist/{path}/" for path in artifacts)
    commands = [
        "corepack enable",
        'PM=$(node -p "require(\'./package.json\').packageManager || \'\'")',
        '[ -n "$PM" ]',
        'corepack prepare "$PM" --activate',
        "pnpm install --frozen-lockfile --ignore-scripts",
        f"pnpm {filters} run build",
        *stage,
        f"cp {unit}/ui-requires.json /src/unit/ui-requires.json",
        "cd /src/unit",
    ]
    run = "".join(line + "\n" for line in copies) + "RUN " + " \\\n && ".join(commands) + " \\\n"
    return _scratch_tail(_manifest_script(), run)


def render_dockerfile(service: str, source: Path | None = None) -> str:
    """Dockerfile text that belongs in the source repo at services/<service>/Dockerfile.

    A pnpm-workspace unit reads the checkout at ``source`` and copies the
    root manifests plus the workspace packages required by its artifact
    paths. Package-layout units copy only the unit directory. Pass
    ``source`` for those too to refuse a checkout that is actually a
    workspace.
    """
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
    if unit is None:
        raise ScopeError(f"{service} has no unit scope")
    layout = _layout(target)
    artifacts = _artifact_paths(target)
    if layout == "package":
        if artifacts != [unit]:
            raise ScopeError(f"{service} package layout builds the unit path only")
        if source is not None:
            _assert_package_is_self_contained(source, unit, service)
        return _render_package_dockerfile(service, unit, target.get("package_manager"))
    if source is None:
        raise ScopeError(f"{service} pnpm workspace render needs the source checkout (--source)")
    read_text, list_paths = _directory_reader(source)
    if read_text("pnpm-workspace.yaml") is None:
        raise ScopeError(f"{service} source has no pnpm-workspace.yaml")
    plan = workspace_plan(read_text, list_paths(), artifacts, service)
    plan["package_dirs_to_build"] = artifacts
    return _render_workspace_dockerfile(plan, unit)


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
    docker.add_argument("--source", default="", help="source checkout; required for a pnpm workspace unit")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "poll":
            json.dump(poll_dispatches(), sys.stdout)
            sys.stdout.write("\n")
            return 0
        if args.cmd == "dockerfile":
            source = Path(args.source).resolve() if args.source else None
            sys.stdout.write(render_dockerfile(args.service, source))
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
