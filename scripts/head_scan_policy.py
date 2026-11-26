#!/usr/bin/env python3
"""Daily gate for fixed HIGH/CRITICAL findings in shipped service images.

build.yml blocks a ship when Trivy finds a fixed HIGH or CRITICAL in the
image it just built. This module is that gate: severity, ignore file, and
the action flags below. The daily job calls this script. ``parity`` reads
build.yml and the scan workflow and refuses when those flags differ.

The line formatter reads Trivy JSON. The declared ``format`` stays ``table``,
the same value the ship action uses. ``GATE_INPUT_FORMAT`` is only how this
process reads the findings it turns into one line per finding.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_CI_LIB = str(Path(__file__).resolve().parent / "lib")
if _CI_LIB not in sys.path:
    sys.path.insert(0, _CI_LIB)
from ci_constants import (  # noqa: E402
    GITHUB_HTTP_TIMEOUT_SECONDS,
    GITHUB_HTTPS_ORIGIN,
    GIT_REV_PARSE_TIMEOUT_SECONDS,
    HEAD_SCAN_CHECKOUT_MINUTES,
    SCAN_COMMAND_TIMEOUT_SECONDS,
    TRIVY_ACTION_TIMEOUT_MINUTES,
)

ROOT = Path(__file__).resolve().parents[1]
BUILD_WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"
SCAN_WORKFLOW = ROOT / ".github" / "workflows" / "weekly-vuln-sbom.yml"
SERVICES_JSON = "services.json"
IGNORE_FILE_NAME = ".trivyignore"

# The ship action's inputs. One name per flag. Do not add a second copy.
SEVERITY = "HIGH,CRITICAL"
SEVERITY_SET = frozenset(SEVERITY.split(","))
IGNORE_UNFIXED = "true"
VULN_TYPE = "os,library"
SCANNERS = "vuln"
EXIT_CODE = "1"
TRIVY_ACTION_FORMAT = "table"
TRIVY_ACTION_TIMEOUT = f"{TRIVY_ACTION_TIMEOUT_MINUTES}m"
TRIVY_ACTION_TIMEOUT_SECONDS = TRIVY_ACTION_TIMEOUT_MINUTES * 60
TRIVY_IGNORES = f".ci-policy/{IGNORE_FILE_NAME}"
SKIP_SETUP_TRIVY = "true"
GATE_INPUT_FORMAT = "json"
TRIVY_SUBPROCESS_EXIT = "0"

AMD64_PLATFORM = "linux/amd64"
DOCKER_BUILDKIT = "1"
HEAD_SCAN_BUILD_TIMEOUT_SECONDS = SCAN_COMMAND_TIMEOUT_SECONDS
IMAGE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
ACTION_KEYS = (
    "format",
    "exit-code",
    "ignore-unfixed",
    "vuln-type",
    "scanners",
    "severity",
    "timeout",
    "trivyignores",
    "skip-setup-trivy",
)
BLOCK_PREFIX = "Block fixed HIGH/CRITICAL vulnerabilities"
SCAN_COMMAND = "head_scan_policy.py scan-heads"
VERIFIED_TRIVY = "scripts/install-verified-trivy.sh"

# Brief order. services.json must name this set and no other shipped image.
SHIPPED_SERVICES = (
    "yueops-web",
    "checkin-api",
    "yue-bot",
    "yueboard",
    "yue-node",
)
YUE_NODE_SERVICE = "yue-node"
NODE_BUILD_PROFILE = "auto"
HEAD_REPOS = ("yueops", "yueboard", "yue-node")
CHECKOUT_DIR = {
    "onesyue/yueops": "yueops",
    "onesyue/yueboard": "yueboard",
    "onesyue/yue-node": "yue-node",
}
HEAD_SCAN_JOB_TIMEOUT_MINUTES = HEAD_SCAN_CHECKOUT_MINUTES + len(SHIPPED_SERVICES) * (
    HEAD_SCAN_BUILD_TIMEOUT_SECONDS + TRIVY_ACTION_TIMEOUT_SECONDS
) // 60



class PolicyError(Exception):
    """Named infrastructure failure. A vulnerability line is exit 1, not this."""


def canonical_action_flags() -> dict[str, str]:
    return {
        "format": TRIVY_ACTION_FORMAT,
        "exit-code": EXIT_CODE,
        "ignore-unfixed": IGNORE_UNFIXED,
        "vuln-type": VULN_TYPE,
        "scanners": SCANNERS,
        "severity": SEVERITY,
        "timeout": TRIVY_ACTION_TIMEOUT,
        "trivyignores": TRIVY_IGNORES,
        "skip-setup-trivy": SKIP_SETUP_TRIVY,
    }


def named_steps(text: str) -> list[tuple[str, str]]:
    steps: list[tuple[str, str]] = []
    matches = list(re.finditer(r"(?m)^      - name: (.+)\n", text))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        steps.append((match.group(1).strip(), text[start:end]))
    return steps


def flags_from_action_step(body: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for key in ACTION_KEYS:
        match = re.search(
            rf"(?m)^[ ]+{re.escape(key)}:\s+'?([^'\n#]+?)'?\s*$",
            body,
        )
        if match:
            found[key] = match.group(1).strip()
    return found


def flags_from_scan(text: str) -> dict[str, str]:
    steps = [body for name, body in named_steps(text) if SCAN_COMMAND in body]
    if len(steps) != 1:
        raise PolicyError("head-scan: scan workflow does not import head_scan_policy.py once")
    body = steps[0]
    found: dict[str, str] = {}
    for key in ACTION_KEYS:
        match = re.search(rf"--{re.escape(key)}\s+(\S+)", body)
        if match is None:
            raise PolicyError(f"head-scan: scan workflow is missing --{key}")
        found[key] = match.group(1)
    return found


def block_flags(text: str) -> list[dict[str, str]]:
    return [
        flags_from_action_step(body)
        for name, body in named_steps(text)
        if name.startswith(BLOCK_PREFIX)
    ]


def parity_mismatch(build_text: str, scan_text: str) -> str | None:
    """Return a named drift reason, or None when the gates match."""
    if SCAN_COMMAND not in scan_text:
        return "scan workflow does not import head_scan_policy.py"
    if VERIFIED_TRIVY not in scan_text:
        return "scan workflow does not install verified trivy"
    if scan_text.index(VERIFIED_TRIVY) > scan_text.index(SCAN_COMMAND):
        return "scan workflow installs trivy after the gate"
    try:
        scan_flags = flags_from_scan(scan_text)
    except PolicyError as exc:
        return str(exc).removeprefix("head-scan: ")
    built = block_flags(build_text)
    if len(built) != 2:
        return "build.yml block-fixed gate count drifted"
    if any(len(item) != len(ACTION_KEYS) for item in built):
        return "build.yml block-fixed gate is missing a flag"
    if built[0] != built[1]:
        drifted = [key for key in ACTION_KEYS if built[0].get(key) != built[1].get(key)]
        return f"build.yml {', '.join(drifted)} drifted"
    canonical = canonical_action_flags()
    if built[0] != canonical:
        drifted = [key for key in ACTION_KEYS if built[0].get(key) != canonical[key]]
        return f"build.yml {', '.join(drifted)} drifted"
    if scan_flags != canonical:
        drifted = [key for key in ACTION_KEYS if scan_flags.get(key) != canonical[key]]
        return f"scan workflow {', '.join(drifted)} drifted"
    return None


def finding_lines(document: object, image: str) -> list[str]:
    if IMAGE_NAME.fullmatch(image) is None:
        raise PolicyError("head-scan: image name is not a shipped service id")
    if not isinstance(document, dict):
        raise PolicyError("head-scan: trivy report is not an object")
    results = document.get("Results", [])
    if results is None:
        results = []
    if not isinstance(results, list):
        raise PolicyError("head-scan: trivy report Results is not a list")
    lines: list[str] = []
    for result in results:
        if not isinstance(result, dict):
            raise PolicyError("head-scan: trivy result is not an object")
        vulns = result.get("Vulnerabilities") or []
        if not isinstance(vulns, list):
            raise PolicyError("head-scan: trivy vulnerabilities are not a list")
        for vuln in vulns:
            if not isinstance(vuln, dict):
                raise PolicyError("head-scan: trivy vulnerability is not an object")
            if vuln.get("Severity") not in SEVERITY_SET:
                continue
            fixed = vuln.get("FixedVersion")
            if not isinstance(fixed, str) or not fixed.strip():
                continue
            package = vuln.get("PkgName")
            installed = vuln.get("InstalledVersion")
            cve = vuln.get("VulnerabilityID")
            fields = (package, installed, cve)
            if not all(isinstance(item, str) and item.strip() for item in fields):
                raise PolicyError(
                    "head-scan: trivy finding is missing package, installed version, or CVE"
                )
            if any("\n" in item or "\r" in item for item in (image, package, installed, fixed, cve)):
                raise PolicyError("head-scan: trivy finding contains a newline")
            lines.append(
                f"{image}: {package}, {installed} → {fixed.strip()}, {cve}"
            )
    return sorted(set(lines))


def repo_relative(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise PolicyError(f"head-scan: {label} is missing")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise PolicyError(f"head-scan: {label} escapes the source checkout")
    return path


def load_shipped(path: Path) -> dict[str, dict]:
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PolicyError("head-scan: services.json is unreadable") from exc
    if not isinstance(catalog, list) or not catalog:
        raise PolicyError("head-scan: services.json must be a non-empty list")
    found: dict[str, dict] = {}
    for entry in catalog:
        if not isinstance(entry, dict):
            raise PolicyError("head-scan: services.json entry is not an object")
        name = entry.get("service")
        if not isinstance(name, str) or name in found:
            raise PolicyError("head-scan: services.json service names drifted")
        found[name] = entry
    if set(found) != set(SHIPPED_SERVICES):
        raise PolicyError("head-scan: shipped service set drifted")
    for name in SHIPPED_SERVICES:
        entry = found[name]
        if entry.get("repo") not in CHECKOUT_DIR:
            raise PolicyError(f"head-scan: {name} repo is not a head checkout")
        platforms = entry.get("platforms")
        if not isinstance(platforms, str) or AMD64_PLATFORM not in platforms.split(","):
            raise PolicyError(f"head-scan: {name} does not ship {AMD64_PLATFORM}")
        repo_relative(entry.get("dockerfile"), f"{name} dockerfile")
        repo_relative(entry.get("context"), f"{name} context")
    return found


def run_command(argv: list[str], *, timeout: int, runner=None, env=None):
    execute = runner or subprocess.run
    kwargs = {
        "text": True,
        "capture_output": True,
        "timeout": timeout,
        "check": False,
    }
    if env is not None:
        kwargs["env"] = env
    try:
        return execute(argv, **kwargs)
    except subprocess.TimeoutExpired as exc:
        raise PolicyError("head-scan: command timed out") from exc


def siblings_module():
    path = Path(__file__).resolve().parent / "update-siblings-lock.py"
    spec = importlib.util.spec_from_file_location("update_siblings_lock", path)
    if spec is None or spec.loader is None:
        raise PolicyError("head-scan: sibling lock module is missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_ls_remote(stdout: str, ref: str, repo: str) -> str:
    lines = [line for line in stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise PolicyError(f"head-scan: ls-remote returned an unexpected line for {repo}")
    sha, separator, found = lines[0].partition("\t")
    if (
        separator != "\t"
        or found != ref
        or FULL_SHA.fullmatch(sha) is None
    ):
        raise PolicyError(f"head-scan: ls-remote returned an unexpected line for {repo}")
    return sha


def resolve_heads(runner=None) -> str:
    token = os.environ.get("YUETO_CI_PAT", "")
    if not token:
        raise PolicyError("head-scan: YUETO_CI_PAT is missing")
    module = siblings_module()
    unknown = [repo for repo in HEAD_REPOS if repo not in module.REPOS]
    if unknown:
        raise PolicyError("head-scan: head repository is not a sibling")
    env = os.environ.copy()
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = "http.extraheader"
    env["GIT_CONFIG_VALUE_0"] = f"AUTHORIZATION: bearer {token}"
    lines = []
    for repo in HEAD_REPOS:
        argv = [
            "git",
            "ls-remote",
            f"{GITHUB_HTTPS_ORIGIN}/onesyue/{repo}.git",
            module.REF,
        ]
        try:
            proc = run_command(
                argv,
                timeout=GITHUB_HTTP_TIMEOUT_SECONDS,
                runner=runner,
                env=env,
            )
        except PolicyError as exc:
            raise PolicyError(f"head-scan: ls-remote timed out for {repo}") from exc
        if proc.returncode != 0:
            raise PolicyError(f"head-scan: ls-remote failed for {repo}")
        sha = parse_ls_remote(proc.stdout or "", module.REF, repo)
        lines.append(f"{module.output_key(repo)}={sha}")
    return "\n".join(lines) + "\n"


def git_text(argv: list[str], *, runner, reason: str) -> str:
    try:
        proc = run_command(argv, timeout=GIT_REV_PARSE_TIMEOUT_SECONDS, runner=runner)
    except PolicyError as exc:
        raise PolicyError(reason) from exc
    if proc.returncode != 0:
        raise PolicyError(reason)
    text = (proc.stdout or "").strip()
    if not text or any(char in text for char in "\n\r\t "):
        raise PolicyError(reason)
    return text


def build_args(source: Path, service: str, runner) -> list[tuple[str, str]]:
    reason = f"head-scan: {service} source is not a full commit"
    revision = git_text(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        runner=runner,
        reason=reason,
    )
    if FULL_SHA.fullmatch(revision) is None:
        raise PolicyError(reason)
    built = git_text(
        ["git", "-C", str(source), "show", "-s", "--format=%cI", "HEAD"],
        runner=runner,
        reason=f"head-scan: {service} source has no commit time",
    )
    args = [("VERSION", revision), ("COMMIT", revision), ("BUILD_TIME", built)]
    if service == YUE_NODE_SERVICE:
        args.append(("BUILD_PROFILE", NODE_BUILD_PROFILE))
    return args


def docker_build_argv(
    *,
    context: Path,
    dockerfile: Path,
    tag: str,
    build: list[tuple[str, str]],
) -> list[str]:
    argv = [
        "docker",
        "build",
        "--pull",
        "--platform",
        AMD64_PLATFORM,
        "--file",
        str(dockerfile),
        "--tag",
        tag,
    ]
    for key, value in build:
        argv.extend(["--build-arg", f"{key}={value}"])
    argv.append(str(context))
    return argv


def trivy_argv(image: str, report: Path, ignore: Path) -> list[str]:
    return [
        "trivy",
        "image",
        "--severity",
        SEVERITY,
        "--ignore-unfixed",
        "--vuln-type",
        VULN_TYPE,
        "--scanners",
        SCANNERS,
        "--exit-code",
        TRIVY_SUBPROCESS_EXIT,
        "--format",
        GATE_INPUT_FORMAT,
        "--timeout",
        TRIVY_ACTION_TIMEOUT,
        "--ignorefile",
        str(ignore),
        "--output",
        str(report),
        image,
    ]


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise PolicyError(f"head-scan: {name} is not on PATH")


def scan_heads(sources: Path, policy_root: Path, declared: dict[str, str], runner=None) -> int:
    canonical = canonical_action_flags()
    if declared != canonical:
        drifted = [key for key in ACTION_KEYS if declared.get(key) != canonical[key]]
        raise PolicyError(f"head-scan: declared policy drifted: {', '.join(drifted)}")
    ignore = policy_root / IGNORE_FILE_NAME
    if not ignore.is_file():
        raise PolicyError("head-scan: .trivyignore is missing")
    catalog = load_shipped(policy_root / SERVICES_JSON)
    if runner is None:
        require_tool("docker")
        require_tool("trivy")
    lines: list[str] = []
    for service in SHIPPED_SERVICES:
        entry = catalog[service]
        checkout = sources / CHECKOUT_DIR[entry["repo"]]
        dockerfile = checkout / repo_relative(entry["dockerfile"], f"{service} dockerfile")
        context = checkout / repo_relative(entry["context"], f"{service} context")
        if not dockerfile.is_file():
            raise PolicyError(f"head-scan: {service} dockerfile is missing")
        if not context.is_dir():
            raise PolicyError(f"head-scan: {service} context is missing")
        tag = f"headscan-{service}:local"
        built = build_args(checkout, service, runner)
        docker_env = os.environ.copy()
        docker_env["DOCKER_BUILDKIT"] = DOCKER_BUILDKIT
        try:
            proc = run_command(
                docker_build_argv(
                    context=context,
                    dockerfile=dockerfile,
                    tag=tag,
                    build=built,
                ),
                timeout=HEAD_SCAN_BUILD_TIMEOUT_SECONDS,
                runner=runner,
                env=docker_env,
            )
        except PolicyError as exc:
            raise PolicyError(f"head-scan: {service} image build timed out") from exc
        if proc.returncode != 0:
            raise PolicyError(f"head-scan: {service} image build failed")
        with tempfile.TemporaryDirectory(prefix="head-scan-") as tmp:
            report_path = Path(tmp) / f"{service}.json"
            try:
                scanned = run_command(
                    trivy_argv(tag, report_path, ignore),
                    timeout=TRIVY_ACTION_TIMEOUT_SECONDS,
                    runner=runner,
                )
            except PolicyError as exc:
                raise PolicyError(f"head-scan: trivy timed out for {service}") from exc
            if scanned.returncode != 0:
                raise PolicyError(f"head-scan: trivy failed for {service}")
            try:
                raw = report_path.read_text(encoding="utf-8")
            except OSError as exc:
                raise PolicyError(f"head-scan: trivy report is missing for {service}") from exc
            if not raw.strip():
                raise PolicyError(f"head-scan: trivy report is empty for {service}")
            try:
                document = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise PolicyError(f"head-scan: trivy report is not JSON for {service}") from exc
        lines.extend(finding_lines(document, service))
    if not lines:
        return 0
    text = "\n".join(lines) + "\n"
    sys.stdout.write(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        try:
            with open(summary, "a", encoding="utf-8") as handle:
                handle.write(text)
        except OSError as exc:
            raise PolicyError("head-scan: step summary is not writable") from exc
    return 1


def declared_from_namespace(args: argparse.Namespace) -> dict[str, str]:
    return {
        "format": args.format,
        "exit-code": args.exit_code,
        "ignore-unfixed": args.ignore_unfixed,
        "vuln-type": args.vuln_type,
        "scanners": args.scanners,
        "severity": args.severity,
        "timeout": args.timeout,
        "trivyignores": args.trivyignores,
        "skip-setup-trivy": args.skip_setup_trivy,
    }


def load_report(path: Path) -> object:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PolicyError("head-scan: trivy report is unreadable") from exc
    if not raw.strip():
        raise PolicyError("head-scan: trivy report is empty")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PolicyError("head-scan: trivy report is not JSON") from exc


def command_gate(args: argparse.Namespace) -> int:
    lines = finding_lines(load_report(args.report), args.image)
    if not lines:
        return 0
    sys.stdout.write("\n".join(lines) + "\n")
    return 1


def command_parity(args: argparse.Namespace) -> int:
    root = args.policy_root
    try:
        build_text = (root / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
        scan_text = (root / ".github" / "workflows" / "weekly-vuln-sbom.yml").read_text(encoding="utf-8")
    except OSError as exc:
        raise PolicyError("head-scan: workflow is unreadable") from exc
    reason = parity_mismatch(build_text, scan_text)
    if reason is None:
        print("head-scan parity ok")
        return 0
    print(reason, file=sys.stderr)
    return 1


def command_scan(args: argparse.Namespace) -> int:
    return scan_heads(
        args.sources,
        args.policy_root,
        declared_from_namespace(args),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy-root", type=Path, default=ROOT)
    sub = parser.add_subparsers(dest="command", required=True)

    gate = sub.add_parser("gate")
    gate.add_argument("--image", required=True)
    gate.add_argument("--report", type=Path, required=True)
    gate.set_defaults(func=command_gate)

    parity = sub.add_parser("parity")
    parity.set_defaults(func=command_parity)

    resolve = sub.add_parser("resolve-heads")
    resolve.set_defaults(func=lambda _args: print(resolve_heads(), end="") or 0)

    scan = sub.add_parser("scan-heads")
    scan.add_argument("--sources", type=Path, required=True)
    for flag in ACTION_KEYS:
        scan.add_argument(f"--{flag}", required=True, dest=flag.replace("-", "_"))
    scan.set_defaults(func=command_scan)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except PolicyError as exc:
        print(exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
