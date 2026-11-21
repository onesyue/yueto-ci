#!/usr/bin/env python3
"""Report-only weekly first-party vulnerability and SBOM scan.

Findings are recorded. Missing catalog entries, missing checkouts, missing
scanner binaries, or a scan-floor miss exit 2. This never opens a pull request.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "policy" / "weekly-vuln-scan-targets.json"
DEFAULT_SCANNER_PINS = ROOT / "scripts" / "scanner-tool-versions.sh"
DEFAULT_LINT_PINS = ROOT / "scripts" / "lint-tool-versions.sh"
KNOWN_SCANNERS = (
    "govulncheck",
    "pip-audit",
    "npm-audit",
    "pnpm-audit",
    "dart-outdated",
    "syft",
)
REQUIRED_PINS = (
    "GOVULNCHECK_VERSION",
    "GOVULNCHECK_ZIP_SHA256",
    "DART_SDK_VERSION",
    "DART_SDK_SHA256",
    "UV_VERSION",
    "NODE_VERSION",
    "PIP_AUDIT_VERSION",
    "PNPM_VERSION",
    "PNPM_PACKAGE_MANAGER",
)
HEX64 = re.compile(r"^[0-9a-f]{64}$")
REPO_NAME = re.compile(r"^[a-z][a-z0-9-]*$")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
PIN_LINE = re.compile(r"^readonly ([A-Z0-9_]+)='([^']*)'$")
SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "testdata",
    "third_party",
    "vendor",
}


class ScanError(Exception):
    """Infrastructure failure. Vulnerability findings never raise this."""


Runner = Callable[..., subprocess.CompletedProcess[str]]


def load_pins(*paths: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            match = PIN_LINE.fullmatch(line)
            if match:
                pins[match[1]] = match[2]
    if not pins:
        raise ScanError("scanner pin authority was empty")
    return pins


def require_pins(pins: dict[str, str]) -> None:
    missing = [name for name in REQUIRED_PINS if not pins.get(name)]
    if missing:
        raise ScanError(f"scanner pin authority is missing {missing}")
    for name in ("GOVULNCHECK_ZIP_SHA256", "DART_SDK_SHA256"):
        if HEX64.fullmatch(pins[name]) is None:
            raise ScanError(f"{name} is not 64 hex digits")


def load_catalog(path: Path) -> dict:
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScanError(f"catalog is unreadable: {exc}") from exc
    if not isinstance(catalog, dict) or catalog.get("schema_version") != 1:
        raise ScanError("catalog schema_version must be 1")
    if catalog.get("report_only") is not True:
        raise ScanError("catalog must declare report_only true")
    repos = catalog.get("repositories")
    if not isinstance(repos, list) or not repos:
        raise ScanError("catalog repositories must be a non-empty list")
    names: list[str] = []
    for entry in repos:
        if not isinstance(entry, dict):
            raise ScanError("catalog repository entry must be an object")
        name = entry.get("name")
        scanners = entry.get("scanners")
        private = entry.get("private")
        if not isinstance(name, str) or REPO_NAME.fullmatch(name) is None:
            raise ScanError(f"invalid repository name: {name!r}")
        if name in names:
            raise ScanError(f"duplicate repository: {name}")
        if private not in (True, False):
            raise ScanError(f"{name}: private must be a boolean")
        if not isinstance(scanners, list) or not scanners:
            raise ScanError(f"{name}: scanners must be a non-empty list")
        unknown = [item for item in scanners if item not in KNOWN_SCANNERS]
        if unknown:
            raise ScanError(f"{name}: unknown scanners {unknown}")
        names.append(name)
    minimum = catalog.get("minimum_repositories")
    if not isinstance(minimum, int) or minimum < 1 or len(repos) < minimum:
        raise ScanError("catalog does not meet minimum_repositories")
    kinds = catalog.get("required_kinds")
    if not isinstance(kinds, list) or not kinds or any(k not in KNOWN_SCANNERS for k in kinds):
        raise ScanError("catalog required_kinds is incomplete")
    present = {scanner for entry in repos for scanner in entry["scanners"]}
    missing = [kind for kind in kinds if kind not in present]
    if missing:
        raise ScanError(f"catalog omits required kinds: {missing}")
    runs = catalog.get("minimum_scanner_runs")
    if not isinstance(runs, int) or runs < 1:
        raise ScanError("catalog minimum_scanner_runs must be a positive integer")
    return catalog


def run_command(
    argv: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 600,
    runner: Runner | None = None,
) -> subprocess.CompletedProcess[str]:
    execute = runner or subprocess.run
    return execute(
        argv,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def require_command(name: str) -> str:
    from shutil import which

    resolved = which(name)
    if resolved is None:
        raise ScanError(f"required scanner {name} is not on PATH")
    return resolved


def skip_dir(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    return any(part in SKIP_DIR_NAMES for part in relative.parts)


def find_files(root: Path, name: str) -> list[Path]:
    found = []
    for path in sorted(root.rglob(name)):
        if skip_dir(path.parent, root):
            continue
        if path.is_file():
            found.append(path)
    return found


def git_revision(source: Path, runner: Runner | None) -> str:
    result = run_command(["git", "-C", str(source), "rev-parse", "HEAD"], runner=runner, timeout=30)
    revision = (result.stdout or "").strip()
    if result.returncode != 0 or FULL_SHA.fullmatch(revision) is None:
        raise ScanError(f"{source}: cannot resolve a full commit SHA")
    return revision


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def record(
    kind: str,
    *,
    target: str,
    status: str,
    findings: int = 0,
    output: object | None = None,
    error: str | None = None,
) -> dict:
    row = {
        "kind": kind,
        "target": target,
        "status": status,
        "findings": findings,
    }
    if output is not None:
        row["output"] = output
    if error:
        row["error"] = error
    return row


def parse_json_output(text: str) -> object:
    text = text.strip()
    if not text:
        raise ScanError("scanner produced empty JSON")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        items = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ScanError(f"scanner produced invalid JSON: {exc}") from exc
        if not items:
            raise ScanError("scanner produced empty JSON")
        return items


def count_govulncheck(payload: object) -> int:
    if isinstance(payload, list):
        return sum(
            1 for item in payload if isinstance(item, dict) and "finding" in item
        )
    if isinstance(payload, dict):
        if isinstance(payload.get("Vulns"), list):
            return len(payload["Vulns"])
        if "finding" in payload:
            return 1
    return 0


def count_pip_audit(payload: object) -> int:
    if not isinstance(payload, dict):
        return 0
    deps = payload.get("dependencies")
    if not isinstance(deps, list):
        return 0
    total = 0
    for item in deps:
        if isinstance(item, dict) and isinstance(item.get("vulns"), list):
            total += len(item["vulns"])
    return total


def count_npm_audit(payload: object) -> int:
    if not isinstance(payload, dict):
        return 0
    vulns = payload.get("vulnerabilities")
    if isinstance(vulns, dict):
        return len(vulns)
    metadata = payload.get("metadata")
    if isinstance(metadata, dict) and isinstance(metadata.get("vulnerabilities"), dict):
        counts = metadata["vulnerabilities"]
        total = counts.get("total")
        if isinstance(total, int):
            return total
    return 0


def run_govulncheck(source: Path, runner: Runner | None) -> list[dict]:
    require_command("govulncheck")
    modules = find_files(source, "go.mod")
    if not modules:
        raise ScanError(f"{source}: govulncheck required but no go.mod")
    rows = []
    for module in modules:
        result = run_command(
            ["govulncheck", "-json", "./..."],
            cwd=module.parent,
            runner=runner,
        )
        if not (result.stdout or "").strip():
            raise ScanError(f"{module.parent}: govulncheck produced no JSON")
        payload = parse_json_output(result.stdout)
        rows.append(
            record(
                "govulncheck",
                target=str(module.parent.relative_to(source)),
                status="ran",
                findings=count_govulncheck(payload),
                output={"exit_code": result.returncode},
            )
        )
    return rows


def run_pip_audit(source: Path, runner: Runner | None) -> list[dict]:
    require_command("pip-audit")
    uv_lock = source / "uv.lock"
    rows = []
    if uv_lock.is_file():
        require_command("uv")
        exported = source / ".weekly-pip-audit.requirements.txt"
        export = run_command(
            [
                "uv",
                "export",
                "--frozen",
                "--all-groups",
                "--no-emit-local",
                "--no-annotate",
                "--no-header",
                "--output-file",
                str(exported),
            ],
            cwd=source,
            runner=runner,
        )
        if export.returncode != 0 or not exported.is_file():
            raise ScanError(f"{source}: uv export of uv.lock failed")
        result = run_command(
            [
                "pip-audit",
                "--requirement",
                str(exported),
                "--progress-spinner",
                "off",
                "--disable-pip",
                "--format",
                "json",
            ],
            cwd=source,
            runner=runner,
        )
        payload = parse_json_output(result.stdout)
        rows.append(
            record(
                "pip-audit",
                target="uv.lock",
                status="ran",
                findings=count_pip_audit(payload),
                output={"exit_code": result.returncode},
            )
        )
        return rows
    requirements = sorted(
        path for path in source.glob("requirements*.txt") if path.is_file()
    )
    if not requirements:
        raise ScanError(f"{source}: pip-audit required but no uv.lock or requirements*.txt")
    for req in requirements:
        argv = [
            "pip-audit",
            "--requirement",
            str(req),
            "--progress-spinner",
            "off",
            "--format",
            "json",
        ]
        if "sha256:" in req.read_text(encoding="utf-8"):
            argv.extend(["--require-hashes", "--disable-pip"])
        result = run_command(argv, cwd=source, runner=runner)
        payload = parse_json_output(result.stdout)
        rows.append(
            record(
                "pip-audit",
                target=req.name,
                status="ran",
                findings=count_pip_audit(payload),
                output={"exit_code": result.returncode},
            )
        )
    return rows


def run_npm_audit(source: Path, runner: Runner | None) -> list[dict]:
    require_command("npm")
    locks = find_files(source, "package-lock.json")
    if not locks:
        raise ScanError(f"{source}: npm-audit required but no package-lock.json")
    rows = []
    for lock in locks:
        result = run_command(
            ["npm", "audit", "--package-lock-only", "--json"],
            cwd=lock.parent,
            runner=runner,
        )
        payload = parse_json_output(result.stdout)
        rows.append(
            record(
                "npm-audit",
                target=str(lock.parent.relative_to(source)),
                status="ran",
                findings=count_npm_audit(payload),
                output={"exit_code": result.returncode},
            )
        )
    return rows


def run_pnpm_audit(source: Path, pins: dict[str, str], runner: Runner | None) -> list[dict]:
    require_command("corepack")
    lock = source / "pnpm-lock.yaml"
    if not lock.is_file():
        raise ScanError(f"{source}: pnpm-audit required but no pnpm-lock.yaml")
    package_manager = pins["PNPM_PACKAGE_MANAGER"]
    enable = run_command(["corepack", "enable"], runner=runner, timeout=60)
    if enable.returncode != 0:
        raise ScanError("corepack enable failed")
    prepare = run_command(
        ["corepack", "prepare", package_manager, "--activate"],
        runner=runner,
        timeout=180,
    )
    if prepare.returncode != 0:
        raise ScanError("corepack prepare of pinned pnpm failed")
    require_command("pnpm")
    result = run_command(["pnpm", "audit", "--json"], cwd=source, runner=runner)
    payload = parse_json_output(result.stdout)
    return [
        record(
            "pnpm-audit",
            target="pnpm-lock.yaml",
            status="ran",
            findings=count_npm_audit(payload),
            output={"exit_code": result.returncode},
        )
    ]


def run_dart_outdated(source: Path, runner: Runner | None) -> list[dict]:
    require_command("dart")
    pubspec = source / "pubspec.yaml"
    if not pubspec.is_file():
        raise ScanError(f"{source}: dart-outdated required but no pubspec.yaml")
    gotten = run_command(
        ["dart", "pub", "get", "--enforce-lockfile"],
        cwd=source,
        runner=runner,
        timeout=600,
    )
    if gotten.returncode != 0:
        raise ScanError(f"{source}: dart pub get --enforce-lockfile failed")
    result = run_command(
        ["dart", "pub", "outdated", "--json"],
        cwd=source,
        runner=runner,
        timeout=600,
    )
    if not (result.stdout or "").strip():
        raise ScanError(f"{source}: dart pub outdated produced no JSON")
    payload = parse_json_output(result.stdout)
    packages = payload.get("packages") if isinstance(payload, dict) else None
    outdated = 0
    if isinstance(packages, list):
        for item in packages:
            if not isinstance(item, dict):
                continue
            current = item.get("current")
            latest = item.get("latest")
            if current != latest:
                outdated += 1
    return [
        record(
            "dart-outdated",
            target="pubspec.yaml",
            status="ran",
            findings=outdated,
            output={"exit_code": result.returncode, "outdated": outdated},
        )
    ]


def run_syft(source: Path, destination: Path, runner: Runner | None) -> dict:
    require_command("syft")
    result = run_command(
        [
            "syft",
            f"dir:{source}",
            "-o",
            f"cyclonedx-json={destination}",
            "-q",
        ],
        cwd=source,
        runner=runner,
        timeout=600,
    )
    if result.returncode != 0 or not destination.is_file() or destination.stat().st_size < 2:
        raise ScanError(f"{source}: syft did not write an SBOM")
    payload = json.loads(destination.read_text(encoding="utf-8"))
    components = payload.get("components") if isinstance(payload, dict) else None
    count = len(components) if isinstance(components, list) else 0
    return record(
        "syft",
        target=".",
        status="ran",
        findings=0,
        output={"exit_code": result.returncode, "components": count, "sbom": destination.name},
    )


SCANNERS = {
    "govulncheck": lambda source, pins, runner: run_govulncheck(source, runner),
    "pip-audit": lambda source, pins, runner: run_pip_audit(source, runner),
    "npm-audit": lambda source, pins, runner: run_npm_audit(source, runner),
    "pnpm-audit": run_pnpm_audit,
    "dart-outdated": lambda source, pins, runner: run_dart_outdated(source, runner),
}


def scan_repository(
    entry: dict,
    source: Path,
    output: Path,
    pins: dict[str, str],
    runner: Runner | None,
) -> dict:
    if not source.is_dir():
        raise ScanError(f"{entry['name']}: source checkout is missing")
    revision = git_revision(source, runner)
    rows: list[dict] = []
    kinds = [kind for kind in entry["scanners"] if kind != "syft"]
    for kind in kinds:
        rows.extend(SCANNERS[kind](source, pins, runner))
    if "syft" in entry["scanners"]:
        sbom = output / "sbom" / f"{entry['name']}.cdx.json"
        rows.append(run_syft(source, sbom, runner))
    return {
        "name": entry["name"],
        "revision": revision,
        "private": entry["private"],
        "scanners": rows,
        "findings": sum(row["findings"] for row in rows),
    }


def enforce_floor(catalog: dict, reports: list[dict]) -> None:
    if len(reports) < catalog["minimum_repositories"]:
        raise ScanError(
            f"scan floor miss: {len(reports)} repositories, need {catalog['minimum_repositories']}"
        )
    kinds = {row["kind"] for report in reports for row in report["scanners"] if row["status"] == "ran"}
    missing = [kind for kind in catalog["required_kinds"] if kind not in kinds]
    if missing:
        raise ScanError(f"scan floor miss: required kinds not executed: {missing}")
    runs = sum(1 for report in reports for row in report["scanners"] if row["status"] == "ran")
    if runs < catalog["minimum_scanner_runs"]:
        raise ScanError(
            f"scan floor miss: {runs} scanner runs, need {catalog['minimum_scanner_runs']}"
        )


def write_report(output: Path, catalog: dict, reports: list[dict]) -> dict:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    findings = [report for report in reports if report["findings"]]
    summary = {
        "schema_version": 1,
        "report_only": True,
        "opens_pull_requests": False,
        "blocks_builds": False,
        "generated": generated,
        "repositories": len(reports),
        "scanner_runs": sum(len(report["scanners"]) for report in reports),
        "findings_count": sum(report["findings"] for report in reports),
        "repositories_with_findings": [report["name"] for report in findings],
    }
    write_json(output / "summary.json", summary)
    write_json(output / "findings.json", reports)
    lines = [
        "# Weekly first-party vulnerability and SBOM report",
        "",
        "Report-only. Findings do not block builds and do not open pull requests.",
        "",
        f"Generated: {generated}",
        f"Repositories: {summary['repositories']}",
        f"Scanner runs: {summary['scanner_runs']}",
        f"Finding records: {summary['findings_count']}",
        "",
    ]
    for report in reports:
        lines.append(
            f"- `{report['name']}` `{report['revision']}` findings={report['findings']}"
        )
    (output / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def cmd_catalog(args: argparse.Namespace) -> int:
    catalog = load_catalog(Path(args.catalog))
    payload = {
        "repositories": [
            {
                "repo": entry["name"],
                "private": entry["private"],
                "scanners": entry["scanners"],
            }
            for entry in catalog["repositories"]
        ]
    }
    text = json.dumps(payload, sort_keys=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
            handle.write(f"matrix={json.dumps({'include': payload['repositories']})}\n")
    print(text)
    return 0


def cmd_scan(args: argparse.Namespace, runner: Runner | None = None) -> int:
    catalog = load_catalog(Path(args.catalog))
    pins = load_pins(Path(args.scanner_pins), Path(args.lint_pins))
    require_pins(pins)
    sources = Path(args.sources)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "sbom").mkdir(parents=True, exist_ok=True)
    reports = []
    for entry in catalog["repositories"]:
        reports.append(
            scan_repository(entry, sources / entry["name"], output, pins, runner)
        )
    enforce_floor(catalog, reports)
    write_report(output, catalog, reports)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    catalog = sub.add_parser("catalog", help="validate the catalog and print the repo list")
    catalog.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    catalog.add_argument("--output")
    catalog.set_defaults(func=cmd_catalog)
    scan = sub.add_parser("scan", help="scan checked-out first-party sources")
    scan.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    scan.add_argument("--scanner-pins", default=str(DEFAULT_SCANNER_PINS))
    scan.add_argument("--lint-pins", default=str(DEFAULT_LINT_PINS))
    scan.add_argument("--sources", required=True)
    scan.add_argument("--output", required=True)
    scan.set_defaults(func=cmd_scan)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ScanError as exc:
        print(f"weekly-vuln-scan: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
