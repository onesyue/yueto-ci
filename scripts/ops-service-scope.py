#!/usr/bin/env python3
"""Per-service YueOps build scope, owned pytest selection, and promotion verdicts.

Path filtering is logical ownership. Dockerfile COPY closure is intentionally
not the selector: a telegram-bot change must rebuild yue-bot only.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

OPS_VALIDATION = "yueops"
SCHEMA = 1
MANIFEST_KEYS = {"schema", "services", "owned", "shared", "tests"}
MODULE_RE = re.compile(r"tests/(?:[A-Za-z0-9_.-]+/)*test_[A-Za-z0-9_.-]+\.py")
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")
HEX = set("0123456789abcdef")


class ScopeError(Exception):
    """The scope document, plan, or verdict cannot be trusted."""


class PromotionRefused(ScopeError):
    """This image has no passed owned-selection verdict."""


def manifest_path() -> Path:
    return Path(__file__).resolve().parents[1] / "ops-service-scope.json"


def services_catalog_path() -> Path:
    return Path(__file__).resolve().parents[1] / "services.json"


def _prefix_overlap(left: str, right: str) -> bool:
    return left.startswith(right) or right.startswith(left)


def _check_prefix(prefix: str) -> None:
    if not isinstance(prefix, str) or prefix.strip() != prefix or prefix == "":
        raise ScopeError(f"bad prefix {prefix!r}")
    if ".." in prefix.split("/"):
        raise ScopeError(f"bad prefix {prefix!r}")


def load_manifest(path: Path | None = None, services_path: Path | None = None) -> dict:
    document = Path(path) if path is not None else manifest_path()
    catalog_path = Path(services_path) if services_path is not None else services_catalog_path()
    try:
        raw = json.loads(document.read_text(encoding="utf-8"))
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScopeError(f"scope manifest is unreadable: {exc}") from exc
    if not isinstance(raw, dict) or set(raw) != MANIFEST_KEYS:
        raise ScopeError("manifest keys must be schema, services, owned, shared, tests")
    if type(raw["schema"]) is not int or raw["schema"] != SCHEMA:
        raise ScopeError("schema must be 1")
    services = raw["services"]
    if (
        not isinstance(services, list)
        or not services
        or len(services) != len(set(services))
        or services != sorted(services)
        or any(not isinstance(name, str) or name == "" for name in services)
    ):
        raise ScopeError("services must be a sorted list of unique names")
    if not isinstance(catalog, list):
        raise ScopeError("services.json must be a list")
    ops = sorted(
        item["service"]
        for item in catalog
        if isinstance(item, dict)
        and (item.get("group") == OPS_VALIDATION or item.get("validation") == OPS_VALIDATION)
    )
    if services != ops:
        raise ScopeError("manifest services must equal the sorted ops services")
    owned = raw["owned"]
    tests = raw["tests"]
    shared = raw["shared"]
    if not isinstance(owned, dict) or set(owned) != set(services):
        raise ScopeError("owned keys must equal services")
    if not isinstance(tests, dict) or set(tests) != set(services):
        raise ScopeError("tests keys must equal services")
    if not isinstance(shared, list):
        raise ScopeError("shared must be a list")
    owned_prefixes: list[tuple[str, str]] = []
    test_prefixes: list[tuple[str, str]] = []
    for name in services:
        service_owned = owned[name]
        service_tests = tests[name]
        if not isinstance(service_owned, list) or not service_owned:
            raise ScopeError(f"{name} owned prefixes must be non-empty")
        if not isinstance(service_tests, list) or not service_tests:
            raise ScopeError(f"{name} test prefixes must be non-empty")
        for prefix in service_owned:
            _check_prefix(prefix)
            owned_prefixes.append((name, prefix))
        for prefix in service_tests:
            _check_prefix(prefix)
            test_prefixes.append((name, prefix))
    for index, (_, left) in enumerate(owned_prefixes):
        for _, right in owned_prefixes[index + 1 :]:
            if _prefix_overlap(left, right):
                raise ScopeError(f"owned prefixes overlap: {left} and {right}")
    for index, (_, left) in enumerate(test_prefixes):
        for _, right in test_prefixes[index + 1 :]:
            if _prefix_overlap(left, right):
                raise ScopeError(f"test prefixes overlap: {left} and {right}")
    for prefix in shared:
        _check_prefix(prefix)
        for _, owned_prefix in owned_prefixes:
            if _prefix_overlap(prefix, owned_prefix):
                raise ScopeError(f"shared overlaps owned: {prefix} and {owned_prefix}")
    return raw


def normalize_path(raw: object) -> str | None:
    """Return a repo-relative path. Empty input is unknown. Absolute or `..` fails."""
    if not isinstance(raw, str):
        raise ScopeError("path must be a string")
    text = raw.replace("\\", "/").strip()
    if text == "":
        return None
    while text.startswith("./"):
        text = text[2:]
    if text.startswith("/") or (len(text) >= 3 and text[1] == ":" and text[2] == "/"):
        raise ScopeError("absolute path refused")
    parts: list[str] = []
    for part in text.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise ScopeError("parent path refused")
        parts.append(part)
    if not parts:
        return None
    return "/".join(parts)


def _matches_prefix(path: str, prefix: str) -> bool:
    if prefix.endswith("/"):
        base = prefix[:-1]
        return path == base or path.startswith(prefix)
    return path == prefix or path.startswith(prefix + "/")


def affected_services(paths: list[str] | None, manifest: dict | None = None) -> list[str]:
    document = manifest if manifest is not None else load_manifest()
    services = list(document["services"])
    if not paths:
        return services
    chosen: set[str] = set()
    saw_path = False
    for raw in paths:
        if not isinstance(raw, str) or raw.strip() == "":
            return services
        normalized = normalize_path(raw)
        if normalized is None:
            return services
        saw_path = True
        hits = [
            name
            for name in services
            if any(_matches_prefix(normalized, prefix) for prefix in document["owned"][name])
        ]
        shared_hit = any(_matches_prefix(normalized, prefix) for prefix in document["shared"])
        if hits and shared_hit:
            raise ScopeError(f"path matches owned and shared: {normalized}")
        if len(hits) > 1:
            raise ScopeError(f"path matches multiple services: {normalized}")
        if shared_hit or not hits:
            return services
        chosen.add(hits[0])
    if not saw_path:
        return services
    return [name for name in services if name in chosen]


def _ops_builds(plan: dict) -> list[dict]:
    return [row for row in plan["matrix"] if row.get("validation") == OPS_VALIDATION]


def _ops_validations(plan: dict) -> list[dict]:
    return [row for row in plan["validation_matrix"] if row.get("validation") == OPS_VALIDATION]


def _selection_from(rows: list[dict], services: list[str]) -> list[dict]:
    order = {name: index for index, name in enumerate(services)}
    selected = []
    for row in rows:
        name = row.get("service")
        if name not in order:
            raise ScopeError(f"unknown ops service {name}")
        selected.append(row)
    selected.sort(key=lambda row: order[row["service"]])
    return [
        {
            "service": row["service"],
            "repo": row["repo"],
            "ref": row["ref"],
            "validation": OPS_VALIDATION,
        }
        for row in selected
    ]


def _stamp(row: dict, chosen: list[str]) -> None:
    row["ops_services"] = list(chosen)
    if len(chosen) == 1:
        row["ops_service"] = chosen[0]
    else:
        row.pop("ops_service", None)


def filter_plan(
    plan: dict,
    paths: list[str] | None,
    dispatch: str,
    *,
    paths_known: bool = True,
    keep_all: bool = False,
    manifest: dict | None = None,
) -> tuple[dict, list[dict], bool]:
    """Return (plan, selection, stamped). Unstamped plans must be byte-copied."""
    document = manifest if manifest is not None else load_manifest()
    services = list(document["services"])
    if not isinstance(plan, dict) or "matrix" not in plan or "validation_matrix" not in plan:
        raise ScopeError("plan is missing matrix or validation_matrix")
    if not isinstance(plan["matrix"], list) or not isinstance(plan["validation_matrix"], list):
        raise ScopeError("plan matrix must be a list")
    copied = json.loads(json.dumps(plan))
    builds = _ops_builds(copied)
    validations = _ops_validations(copied)
    build_names = [row.get("service") for row in builds]
    if len(build_names) != len(set(build_names)):
        raise ScopeError("duplicate ops build rows")
    if len(validations) > 1:
        raise ScopeError("duplicate yueops validation rows")
    if builds and len(validations) != 1:
        raise ScopeError("ops builds require exactly one yueops validation row")

    explicit = dispatch in services
    if explicit or keep_all or not paths_known:
        if builds:
            selection = _selection_from(builds, services)
        elif validations:
            names = [dispatch] if explicit else services
            selection = _selection_from(
                [
                    {"service": name, "repo": validations[0]["repo"], "ref": validations[0]["ref"]}
                    for name in names
                ],
                services,
            )
        else:
            selection = []
        return copied, selection, False

    affected = affected_services(list(paths or []), document)
    if builds:
        present = set(build_names)
        chosen = [name for name in services if name in affected and name in present]
    elif validations:
        chosen = [name for name in services if name in affected]
    else:
        return copied, [], False

    if builds:
        copied["matrix"] = [
            row
            for row in copied["matrix"]
            if row.get("validation") != OPS_VALIDATION or row.get("service") in chosen
        ]
        copied["has_builds"] = len(copied["matrix"]) > 0
    if not chosen:
        copied["validation_matrix"] = [
            row for row in copied["validation_matrix"] if row.get("validation") != OPS_VALIDATION
        ]
        return copied, [], True

    for row in copied["validation_matrix"]:
        if row.get("validation") == OPS_VALIDATION:
            _stamp(row, chosen)
    if builds:
        selection = _selection_from(_ops_builds(copied), services)
    else:
        validation = _ops_validations(copied)[0]
        selection = _selection_from(
            [
                {"service": name, "repo": validation["repo"], "ref": validation["ref"]}
                for name in chosen
            ],
            services,
        )
    return copied, selection, True


def owned_modules(
    service: str,
    modules: list[str] | None = None,
    source: Path | None = None,
    manifest: dict | None = None,
) -> list[str]:
    document = manifest if manifest is not None else load_manifest()
    services = list(document["services"])
    if service not in services:
        raise ScopeError(f"unknown service {service}")
    if source is not None:
        tests = Path(source) / "tests"
        if not tests.is_dir():
            raise ScopeError(f"owned selection is empty for {service}")
        modules = sorted(path.relative_to(source).as_posix() for path in tests.rglob("test_*.py"))
    if modules is None:
        raise ScopeError("modules or source required")
    owned: list[str] = []
    for raw in modules:
        relative = str(raw).replace("\\", "/")
        matches = [
            name
            for name in services
            if any(relative.startswith(prefix) for prefix in document["tests"][name])
        ]
        if len(matches) > 1:
            raise ScopeError(f"module matches two services: {relative}")
        if service not in matches:
            continue
        if (
            relative.startswith("-")
            or not relative.startswith("tests/")
            or MODULE_RE.fullmatch(relative) is None
        ):
            raise ScopeError(f"owned module path refused: {relative}")
        owned.append(relative)
    if not owned:
        raise ScopeError(f"owned selection is empty for {service}")
    return owned


def service_verdicts(results: dict[str, str], manifest: dict | None = None) -> dict[str, str]:
    document = manifest if manifest is not None else load_manifest()
    known = set(document["services"])
    parsed: dict[str, str] = {}
    for name, status in results.items():
        if name not in known:
            raise ScopeError(f"unknown service {name}")
        if status not in {"passed", "failed"}:
            raise ScopeError(f"unknown status {status}")
        parsed[name] = status
    return parsed


def assert_promotable(service: str, verdicts: dict[str, str], manifest: dict | None = None) -> None:
    document = manifest if manifest is not None else load_manifest()
    if service not in set(document["services"]):
        raise PromotionRefused(f"unknown service {service}")
    if verdicts.get(service) != "passed":
        raise PromotionRefused(f"{service} selection is not passed")


def verdict_from_outcome(service: str, outcome: str, manifest: dict | None = None) -> dict[str, str]:
    document = manifest if manifest is not None else load_manifest()
    if service not in set(document["services"]):
        raise ScopeError(f"unknown service {service}")
    return {"service": service, "status": "passed" if outcome == "success" else "failed"}


def write_verdict(service: str, outcome: str, output: Path, manifest: dict | None = None) -> None:
    verdict = verdict_from_outcome(service, outcome, manifest)
    path = Path(output)
    if path.name != f"{service}.json":
        raise ScopeError("verdict filename must be the service name")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(verdict, separators=(",", ":")) + "\n", encoding="utf-8")


def load_verdicts(directory: Path, service: str | None = None) -> dict:
    root = Path(directory)
    files = sorted(path for path in root.rglob("*.json") if path.is_file())
    by_service: dict[str, dict] = {}
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ScopeError(f"invalid verdict JSON: {path.name}") from exc
        if not isinstance(data, dict):
            raise ScopeError(f"invalid verdict JSON: {path.name}")
        name = data.get("service")
        status = data.get("status")
        if not isinstance(name, str) or path.name != f"{name}.json":
            raise ScopeError("filename does not match service")
        if status not in {"passed", "failed"}:
            raise ScopeError("status must be passed or failed")
        if name in by_service:
            raise ScopeError(f"duplicate verdict for {name}")
        by_service[name] = data
    if service is None:
        return by_service
    matches = [path for path in files if path.name == f"{service}.json"]
    if len(matches) != 1 or by_service.get(service, {}).get("service") != service:
        raise ScopeError(f"expected exactly one {service}.json")
    return by_service[service]


def image_digests(previous: dict[str, str], plan: dict, new_for_selected: dict[str, str]) -> dict[str, str]:
    selected: list[str] = []
    seen: set[str] = set()
    for row in plan["matrix"]:
        name = row.get("service")
        if not isinstance(name, str) or name in seen:
            raise ScopeError(f"duplicate matrix service {name}")
        seen.add(name)
        selected.append(name)
    extra = set(new_for_selected) - seen
    if extra:
        raise ScopeError(f"digest for service not in matrix: {sorted(extra)}")
    missing = seen - set(new_for_selected)
    if missing:
        raise ScopeError(f"selected service missing a rebuilt digest: {sorted(missing)}")
    result = dict(previous)
    for name in selected:
        digest = new_for_selected[name]
        if not isinstance(digest, str) or DIGEST_RE.fullmatch(digest) is None:
            raise ScopeError(f"rebuilt digest is not sha256 for {name}")
        if previous.get(name) == digest:
            raise ScopeError(f"selected digest unchanged for {name}")
        result[name] = digest
    return result


def changed_paths(source: Path, base: str) -> list[str]:
    if not isinstance(base, str) or len(base) != 40 or any(character not in HEX for character in base):
        raise ScopeError("migration base must be 40 lowercase hex")
    root = str(source)
    listed = subprocess.run(
        ["git", "-C", root, "cat-file", "-e", f"{base}^{{commit}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if listed.returncode != 0:
        raise ScopeError("migration base is not a commit")
    diff = subprocess.run(
        [
            "git",
            "-C",
            root,
            "diff",
            "--name-only",
            "--no-renames",
            "--diff-filter=ACMRD",
            base,
            "HEAD",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if diff.returncode != 0:
        raise ScopeError("git diff failed")
    paths: list[str] = []
    for line in diff.stdout.splitlines():
        normalized = normalize_path(line)
        if normalized is None:
            raise ScopeError("git diff returned an empty path")
        paths.append(normalized)
    return paths


def _read_plan() -> tuple[bytes, dict]:
    raw = sys.stdin.buffer.read()
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ScopeError("invalid plan JSON") from exc
    if not isinstance(parsed, dict):
        raise ScopeError("invalid plan JSON")
    return raw, parsed


def _write_selection(path: str, selection: list[dict]) -> None:
    Path(path).write_text(json.dumps(selection, separators=(",", ":")) + "\n", encoding="utf-8")


def command_filter_plan(args: argparse.Namespace) -> None:
    raw, parsed = _read_plan()
    if args.keep_all:
        paths: list[str] = []
        keep_all = True
    else:
        if not args.paths:
            raise ScopeError("paths file is required")
        path = Path(args.paths)
        if not path.is_file():
            raise ScopeError("paths file is missing")
        paths = path.read_text(encoding="utf-8").splitlines()
        keep_all = False
    updated, selection, stamped = filter_plan(
        parsed,
        paths,
        args.dispatch,
        paths_known=True,
        keep_all=keep_all,
    )
    if args.selection_output:
        _write_selection(args.selection_output, selection)
    if stamped or updated != parsed:
        sys.stdout.write(json.dumps(updated, separators=(",", ":")) + "\n")
        return
    sys.stdout.buffer.write(raw if raw.endswith(b"\n") else raw + b"\n")


def command_owned_modules(args: argparse.Namespace) -> None:
    for module in owned_modules(args.service, source=Path(args.source)):
        print(module)


def command_write_verdict(args: argparse.Namespace) -> None:
    write_verdict(args.service, args.outcome, Path(args.output))


def command_assert_promotable(args: argparse.Namespace) -> None:
    loaded = load_verdicts(Path(args.verdicts))
    assert_promotable(args.service, {name: item["status"] for name, item in loaded.items()})


def command_changed_paths(args: argparse.Namespace) -> None:
    for path in changed_paths(Path(args.source), args.base):
        print(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="YueOps per-service scope")
    commands = parser.add_subparsers(dest="command", required=True)

    filter_plan_command = commands.add_parser("filter-plan")
    filter_plan_command.add_argument("--dispatch", required=True)
    filter_plan_command.add_argument("--paths")
    filter_plan_command.add_argument("--keep-all", action="store_true")
    filter_plan_command.add_argument("--selection-output")
    filter_plan_command.set_defaults(func=command_filter_plan)

    owned = commands.add_parser("owned-modules")
    owned.add_argument("--service", required=True)
    owned.add_argument("--source", required=True)
    owned.set_defaults(func=command_owned_modules)

    verdict = commands.add_parser("write-verdict")
    verdict.add_argument("--service", required=True)
    verdict.add_argument("--outcome", required=True)
    verdict.add_argument("--output", required=True)
    verdict.set_defaults(func=command_write_verdict)

    promote = commands.add_parser("assert-promotable")
    promote.add_argument("--service", required=True)
    promote.add_argument("--verdicts", required=True)
    promote.set_defaults(func=command_assert_promotable)

    changed = commands.add_parser("changed-paths")
    changed.add_argument("--source", required=True)
    changed.add_argument("--base", required=True)
    changed.set_defaults(func=command_changed_paths)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except ScopeError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
