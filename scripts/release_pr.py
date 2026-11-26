#!/usr/bin/env python3
"""Open a signed per-service release pull request after a green promote.

The root release.yaml ledger stays on the owner key. This tool renders one
component file with the workspace release_yaml library, and the workflow signs
that file with the keyless identity production already accepts for images.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

_CI_LIB = str(Path(__file__).resolve().parent / "lib")
if _CI_LIB not in sys.path:
    sys.path.insert(0, _CI_LIB)
from ci_constants import (
    ACTIONS_OIDC_ISSUER,
    GITHUB_HTTPS_ORIGIN,
    SLSA_PROVENANCE_PREDICATE,
)


WORKFLOW_IDENTITY = (
    f"{GITHUB_HTTPS_ORIGIN}/onesyue/yueto-ci/.github/workflows/build.yml@refs/heads/master"
)
OIDC_ISSUER = ACTIONS_OIDC_ISSUER
PROVENANCE_PREDICATE = SLSA_PROVENANCE_PREDICATE
SIGNER_WORKFLOW = "github.com/onesyue/yueto-ci/.github/workflows/build.yml"
YUETO_REPO = "onesyue/yueto"
CI_REPO = "onesyue/yueto-ci"
REGISTRY = "ghcr.io/onesyue"
PROMOTED_BY = "yueto-ci"
AUTHOR_NAME = "yueto-ci"
AUTHOR_EMAIL = "yueto-ci@users.noreply.github.com"
NODE_IMAGE_SERVICES = frozenset({"yue-node"})
ALLOWED_REMOTES = frozenset({
    f"{GITHUB_HTTPS_ORIGIN}/onesyue/yueto",
    f"{GITHUB_HTTPS_ORIGIN}/onesyue/yueto.git",
})
SHA12 = 12
ARCHITECTURES = frozenset({"amd64", "arm64"})

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
RUN_RE = re.compile(r"^[1-9][0-9]{0,19}$")
SERVICE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
GENERATION_RE = re.compile(r"^[1-9][0-9]{0,17}$")
BRANCH_RE = re.compile(r"^release/[a-z0-9][a-z0-9-]*-[0-9a-f]{12}$")
PR_NUMBER_RE = re.compile(r"^[1-9][0-9]{0,9}$")
INVOCATION_RE = re.compile(
    rf"^{GITHUB_HTTPS_ORIGIN}/{re.escape(CI_REPO)}/actions/runs/([1-9][0-9]*)/attempts/([1-9][0-9]*)$"
)

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "services.json"


class ReleasePrError(ValueError):
    """The release pull request cannot be recorded safely."""


def load_catalog() -> dict[str, dict]:
    try:
        payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleasePrError("services catalog is unreadable") from exc
    if not isinstance(payload, list):
        raise ReleasePrError("services catalog is not a list")
    catalog: dict[str, dict] = {}
    for item in payload:
        if not isinstance(item, dict) or not isinstance(item.get("service"), str):
            raise ReleasePrError("services catalog entry is missing a service name")
        catalog[item["service"]] = item
    return catalog


def require_service(service: str) -> dict:
    if not SERVICE_RE.fullmatch(service):
        raise ReleasePrError("service name is not a path token")
    catalog = load_catalog()
    item = catalog.get(service)
    if item is None:
        raise ReleasePrError("unknown service")
    return item


def auto_merge(service: str) -> bool:
    """E4 turns auto-merge on for every catalogued service except node images."""

    item = require_service(service)
    if service in NODE_IMAGE_SERVICES or item.get("group") == "yue-node":
        return False
    return True


def release_branch(service: str, revision: str) -> str:
    require_service(service)
    if not SHA_RE.fullmatch(revision):
        raise ReleasePrError("revision is not 40 hex characters")
    branch = f"release/{service}-{revision[:SHA12]}"
    git_push_args(branch)
    return branch


def git_push_args(branch: str) -> list[str]:
    if branch in {"master", "refs/heads/master"} or branch.startswith("refs/heads/master"):
        raise ReleasePrError("refusing to push master")
    if not BRANCH_RE.fullmatch(branch):
        raise ReleasePrError("refusing to push an unexpected branch")
    refspec = f"HEAD:refs/heads/{branch}"
    if refspec.rsplit("/", 1)[-1] == "master":
        raise ReleasePrError("refusing to push master")
    args = ["git", "push", "origin", refspec]
    if "--force" in args or "-f" in args or "--force-with-lease" in args:
        raise ReleasePrError("refusing to force-push")
    return args


def authed_git(root: Path) -> list[str]:
    """git against the private ledger origin with the gh credential helper.

    The ledger checkout keeps persist-credentials: false, so every network
    read (ls-remote, fetch) needs the same helper as the push.
    """
    return [
        "git", "-C", str(root),
        "-c", "credential.helper=",
        "-c", "credential.helper=!gh auth git-credential",
    ]


def git_push_command(root: Path, branch: str) -> list[str]:
    refspec = git_push_args(branch)[3]
    return [*authed_git(root), "push", "origin", refspec]


def pr_list_args(branch: str) -> list[str]:
    git_push_args(branch)
    return [
        "gh", "pr", "list",
        "--repo", YUETO_REPO,
        "--base", "master",
        "--head", branch,
        "--state", "open",
        "--json", "number,url",
    ]


def pr_create_args(branch: str, title: str, body_file: Path) -> list[str]:
    git_push_args(branch)
    if "\n" in title or title.strip() == "":
        raise ReleasePrError("pull request title is empty")
    return [
        "gh", "pr", "create",
        "--repo", YUETO_REPO,
        "--base", "master",
        "--head", branch,
        "--title", title,
        "--body-file", str(body_file),
    ]


def pr_merge_args(number: str) -> list[str]:
    if not PR_NUMBER_RE.fullmatch(number):
        raise ReleasePrError("pull request number is not a positive integer")
    args = [
        "gh", "pr", "merge", number,
        "--repo", YUETO_REPO,
        "--auto", "--squash",
    ]
    if {"--admin", "--force", "-f", "--rebase", "--merge"} & set(args):
        raise ReleasePrError("refusing an immediate or privileged merge")
    return args


def cosign_identity_args() -> list[str]:
    return [
        "--certificate-identity", WORKFLOW_IDENTITY,
        "--certificate-oidc-issuer", OIDC_ISSUER,
    ]


def attestation_argv(image: str, digest: str) -> list[str]:
    if not DIGEST_RE.fullmatch(digest):
        raise ReleasePrError("digest is not sha256:<64-hex>")
    if not image.startswith(REGISTRY + "/") or "@" in image or ":" in image.split("/", 1)[-1]:
        raise ReleasePrError("image is not a registry repository name")
    return [
        "gh", "attestation", "verify", f"oci://{image}@{digest}",
        "--repo", CI_REPO,
        "--bundle-from-oci",
        "--signer-workflow", SIGNER_WORKFLOW,
        "--cert-oidc-issuer", OIDC_ISSUER,
        "--predicate-type", PROVENANCE_PREDICATE,
        "--format", "json",
    ]


def _architectures(value: str) -> str:
    parts = [item.strip() for item in value.split(",")]
    if not parts or any(item == "" for item in parts):
        raise ReleasePrError("architectures are empty")
    if len(parts) != len(set(parts)) or any(item not in ARCHITECTURES for item in parts):
        raise ReleasePrError("architectures must be amd64 and arm64 only")
    return ",".join(parts)


def build_receipt(fields: dict[str, str]) -> dict[str, str]:
    service = fields["service"]
    require_service(service)
    revision = fields["revision"]
    digest = fields["digest"]
    image = fields["image"]
    workflow_sha = fields["workflow_sha"]
    promoted_at = fields["promoted_at"]
    run_id = fields["run_id"]
    run_attempt = fields["run_attempt"]
    if not SHA_RE.fullmatch(revision) or not SHA_RE.fullmatch(workflow_sha):
        raise ReleasePrError("revision or workflow sha is not 40 hex characters")
    if not DIGEST_RE.fullmatch(digest):
        raise ReleasePrError("digest is not sha256:<64-hex>")
    if image != f"{REGISTRY}/{service}":
        raise ReleasePrError("image does not match the service repository")
    if not TS_RE.fullmatch(promoted_at):
        raise ReleasePrError("promoted_at is not UTC second-resolution")
    if not RUN_RE.fullmatch(run_id) or not RUN_RE.fullmatch(run_attempt):
        raise ReleasePrError("run id or attempt is not a positive integer")
    return {
        "architectures": _architectures(fields["architectures"]),
        "digest": digest,
        "image": image,
        "promoted_at": promoted_at,
        "revision": revision,
        "run_attempt": run_attempt,
        "run_id": run_id,
        "service": service,
        "workflow_sha": workflow_sha,
    }


def load_receipt(path: Path) -> dict[str, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleasePrError("promoted receipt is unreadable") from exc
    if not isinstance(payload, dict) or any(not isinstance(value, str) for value in payload.values()):
        raise ReleasePrError("promoted receipt is not a string map")
    expected = {
        "architectures", "digest", "image", "promoted_at", "revision",
        "run_attempt", "run_id", "service", "workflow_sha",
    }
    if set(payload) != expected:
        raise ReleasePrError("promoted receipt fields differ")
    return build_receipt(payload)


def load_release_yaml(yueto_root: Path):
    scripts = Path(yueto_root) / "scripts"
    package = scripts / "release_yaml" / "__init__.py"
    if not package.is_file():
        raise ReleasePrError("scripts/release_yaml is required")
    inserted = str(scripts)
    if inserted not in sys.path:
        sys.path.insert(0, inserted)
    existing = sys.modules.get("release_yaml")
    origin = Path(getattr(existing, "__file__", "") or "")
    if existing is not None and origin.resolve() != package.resolve():
        sys.modules.pop("release_yaml", None)
    module = importlib.import_module("release_yaml")
    for name in ("parse", "validate", "render", "signature_input", "COMPONENTS", "SCHEMA"):
        if not hasattr(module, name):
            raise ReleasePrError("scripts/release_yaml is required")
    return module


def _same_promotion(record: dict, service: str, revision: str, digest: str) -> bool:
    components = record.get("components")
    desired = record.get("desired")
    if not isinstance(components, dict) or not isinstance(desired, dict):
        return False
    body = components.get(service)
    production = desired.get("production")
    if not isinstance(body, dict) or not isinstance(production, dict):
        return False
    wanted = production.get(service)
    if not isinstance(wanted, dict):
        return False
    return (
        body.get("revision") == revision
        and body.get("digest") == digest
        and wanted.get("revision") == revision
        and wanted.get("digest") == digest
    )


def apply_promotion(module, previous: str | None, receipt: dict[str, str]) -> str | None:
    service = receipt["service"]
    require_service(service)
    if service not in module.COMPONENTS:
        raise ReleasePrError("service is not a release component")
    record = None
    if previous is not None:
        record = module.parse(previous)
        problems = list(module.validate(record))
        if problems:
            raise ReleasePrError("existing release record failed validation")
        if set(record) - {"schema", "components", "desired"}:
            raise ReleasePrError("per-service file carries unexpected keys")
        if set(record.get("components") or {}) != {service}:
            raise ReleasePrError("per-service file must contain only this service")
        if _same_promotion(record, service, receipt["revision"], receipt["digest"]):
            return None
        generation_text = str(record["desired"]["generation"])
        if not GENERATION_RE.fullmatch(generation_text):
            raise ReleasePrError("existing generation is not a positive integer")
        generation = int(generation_text) + 1
        if len(str(generation)) > 18:
            raise ReleasePrError("generation overflow")
    else:
        generation = 1
    updated = {
        "schema": module.SCHEMA,
        "components": {
            service: {
                "revision": receipt["revision"],
                "digest": receipt["digest"],
                "promoted_at": receipt["promoted_at"],
                "run_id": receipt["run_id"],
                "promoted_by": PROMOTED_BY,
            },
        },
        "desired": {
            "generation": str(generation),
            "production": {
                service: {
                    "revision": receipt["revision"],
                    "digest": receipt["digest"],
                },
            },
        },
    }
    problems = list(module.validate(updated))
    if problems:
        raise ReleasePrError("release record failed validation")
    rendered = module.render(updated)
    reparsed = module.parse(rendered)
    problems = list(module.validate(reparsed))
    if problems:
        raise ReleasePrError("rendered release record failed validation")
    canonical = module.render(reparsed)
    if canonical != rendered:
        raise ReleasePrError("release render is not stable")
    if module.signature_input(reparsed) != canonical.encode("utf-8"):
        raise ReleasePrError("signature input diverges from render")
    return canonical


def release_yaml_path(root: Path, service: str) -> Path:
    require_service(service)
    directory = (root / "release").resolve()
    path = (directory / f"{service}.yaml").resolve()
    if path.parent != directory:
        raise ReleasePrError("release path escapes the release directory")
    return path


def release_paths(service: str) -> tuple[str, str]:
    require_service(service)
    yaml_path = f"release/{service}.yaml"
    return yaml_path, yaml_path + ".bundle"


def check_provenance(results, receipt: dict[str, str]) -> None:
    if not isinstance(results, list) or not results:
        raise ReleasePrError("provenance results are missing")
    identities = set()
    digest_hex = receipt["digest"][7:]
    for item in results:
        if not isinstance(item, dict):
            raise ReleasePrError("provenance result is not an object")
        verified = item.get("verificationResult")
        if not isinstance(verified, dict):
            raise ReleasePrError("provenance verification result is missing")
        signature = verified.get("signature")
        statement = verified.get("statement")
        if not isinstance(signature, dict) or not isinstance(statement, dict):
            raise ReleasePrError("provenance statement is missing")
        certificate = signature.get("certificate")
        if not isinstance(certificate, dict):
            raise ReleasePrError("provenance certificate is missing")
        if certificate.get("buildSignerURI") != WORKFLOW_IDENTITY:
            raise ReleasePrError("provenance signer is not this workflow on master")
        if certificate.get("sourceRepositoryRef") != "refs/heads/master":
            raise ReleasePrError("provenance source ref is not master")
        subjects = statement.get("subject")
        if not isinstance(subjects, list) or not any(
            isinstance(subject, dict)
            and isinstance(subject.get("digest"), dict)
            and subject["digest"].get("sha256") == digest_hex
            for subject in subjects
        ):
            raise ReleasePrError("provenance subject digest differs")
        invocation = INVOCATION_RE.fullmatch(str(certificate.get("runInvocationURI", "")))
        if invocation is None:
            raise ReleasePrError("provenance certificate has no run identity")
        identities.add((invocation.group(1), invocation.group(2), certificate.get("buildSignerDigest")))
    expected = {(receipt["run_id"], receipt["run_attempt"], receipt["workflow_sha"])}
    if identities != expected:
        raise ReleasePrError("provenance does not name this build")


def assert_push_remote(root: Path) -> str:
    result = _run(
        ["git", "-C", str(root), "remote", "get-url", "origin"],
        capture=True, text=True,
    )
    url = result.stdout.strip()
    if "://" in url and "@" in url.split("://", 1)[1].split("/", 1)[0]:
        raise ReleasePrError("refusing token-in-url remote")
    if url not in ALLOWED_REMOTES:
        raise ReleasePrError("refusing unexpected origin")
    return url


def commit_release(root: Path, service: str, message: str) -> None:
    yaml_path, bundle_path = release_paths(service)
    if "\n" in message or message.strip() == "":
        raise ReleasePrError("commit message is empty")
    _git(root, "add", "--", yaml_path, bundle_path)
    staged = _git(root, "diff", "--cached", "--name-only", capture=True, text=True).stdout.split()
    if set(staged) != {yaml_path, bundle_path}:
        raise ReleasePrError("refusing to commit unexpected paths")
    _git(
        root, "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null",
        "-c", f"user.name={AUTHOR_NAME}", "-c", f"user.email={AUTHOR_EMAIL}",
        "commit", "-m", message,
    )


def _git(root: Path, *args: str, capture: bool = False, text: bool = False):
    return _run(["git", "-C", str(root), *args], capture=capture, text=text)


def _run(args: list[str], *, check: bool = True, capture: bool = False, text: bool = False):
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    result = subprocess.run(args, check=False, capture_output=capture, text=text, env=env)
    if check and result.returncode != 0:
        raise ReleasePrError(f"command failed ({args[0]} exit {result.returncode})")
    return result


def _github_output(path: str, status: str) -> None:
    if status not in {"rendered", "unchanged"}:
        raise ReleasePrError("bad render status")
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"status={status}\n")


def _write_record(path: Path, rendered: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(rendered, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def render_release(root: Path, receipt: dict[str, str], github_output: str) -> str:
    module = load_release_yaml(root)
    path = release_yaml_path(root, receipt["service"])
    previous = path.read_text(encoding="utf-8") if path.is_file() else None
    rendered = apply_promotion(module, previous, receipt)
    if rendered is None:
        _github_output(github_output, "unchanged")
        return "unchanged"
    _write_record(path, rendered)
    _github_output(github_output, "rendered")
    return "rendered"


def _pr_list(branch: str) -> list[dict]:
    result = _run(pr_list_args(branch), capture=True, text=True)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ReleasePrError("pull request list is unreadable") from exc
    if not isinstance(payload, list):
        raise ReleasePrError("pull request list is not a list")
    found = []
    for item in payload:
        if not isinstance(item, dict):
            raise ReleasePrError("pull request list entry is not an object")
        number = str(item.get("number", ""))
        url = str(item.get("url", ""))
        if not PR_NUMBER_RE.fullmatch(number):
            raise ReleasePrError("pull request number is not a positive integer")
        found.append({"number": number, "url": url})
    return found


def _remote_branch_exists(root: Path, branch: str) -> bool:
    result = _run(
        [*authed_git(root), "ls-remote", "--exit-code", "origin", f"refs/heads/{branch}"],
        check=False, capture=True, text=True,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 2:
        return False
    raise ReleasePrError(f"command failed (git exit {result.returncode})")


def _remote_bytes(root: Path, branch: str, path: str) -> bytes:
    _run([
        *authed_git(root), "fetch", "--no-tags", "origin",
        f"+refs/heads/{branch}:refs/remotes/origin/{branch}",
    ])
    result = _run(
        ["git", "-C", str(root), "show", f"origin/{branch}:{path}"],
        capture=True, text=False,
    )
    return result.stdout


def _create_pr(branch: str, service: str, revision: str, generation: str) -> str:
    title = f"release {service} {revision[:SHA12]}"
    body = (
        f"service: {service}\n"
        f"revision: {revision}\n"
        f"generation: {generation}\n"
        "\n"
        "This pull request records a verified promote. It does not deploy.\n"
    )
    body_file = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / f"release-pr-{service}.md"
    body_file.write_text(body, encoding="utf-8")
    result = _run(pr_create_args(branch, title, body_file), capture=True, text=True)
    url = result.stdout.strip().splitlines()[-1]
    prefix = f"{GITHUB_HTTPS_ORIGIN}/{YUETO_REPO}/pull/"
    if not url.startswith(prefix) or not PR_NUMBER_RE.fullmatch(url[len(prefix):]):
        raise ReleasePrError("pull request create did not return a pull request url")
    return url


def _generation_of(root: Path, service: str) -> str:
    module = load_release_yaml(root)
    path = release_yaml_path(root, service)
    record = module.parse(path.read_text(encoding="utf-8"))
    problems = list(module.validate(record))
    if problems:
        raise ReleasePrError("release record failed validation")
    generation = str(record["desired"]["generation"])
    if not GENERATION_RE.fullmatch(generation):
        raise ReleasePrError("generation is not a positive integer")
    return generation


def open_release(root: Path, receipt: dict[str, str]) -> str:
    service = receipt["service"]
    branch = release_branch(service, receipt["revision"])
    assert_push_remote(root)
    existing = _pr_list(branch)
    if len(existing) > 1:
        raise ReleasePrError("more than one open release pull request")
    if len(existing) == 1:
        if auto_merge(service):
            _run(pr_merge_args(existing[0]["number"]))
        return existing[0]["url"]
    yaml_path = release_yaml_path(root, service)
    bundle_path = Path(str(yaml_path) + ".bundle")
    if not yaml_path.is_file() or not bundle_path.is_file() or bundle_path.stat().st_size == 0:
        raise ReleasePrError("rendered release record and bundle are required")
    generation = _generation_of(root, service)
    relative_yaml, relative_bundle = release_paths(service)
    if _remote_branch_exists(root, branch):
        remote_yaml = _remote_bytes(root, branch, relative_yaml)
        remote_bundle = _remote_bytes(root, branch, relative_bundle)
        if remote_yaml != yaml_path.read_bytes() or remote_bundle != bundle_path.read_bytes():
            raise ReleasePrError("existing release branch content differs")
    else:
        commit_release(root, service, f"release {service} {receipt['revision'][:SHA12]}")
        _run(git_push_command(root, branch))
    url = _create_pr(branch, service, receipt["revision"], generation)
    if auto_merge(service):
        number = url.rsplit("/", 1)[-1]
        _run(pr_merge_args(number))
    return url


def cmd_record(args: argparse.Namespace) -> int:
    receipt = build_receipt({
        "service": args.service,
        "revision": args.revision,
        "digest": args.digest,
        "image": args.image,
        "architectures": args.architectures,
        "run_id": args.run_id,
        "run_attempt": args.run_attempt,
        "workflow_sha": args.workflow_sha,
        "promoted_at": args.promoted_at,
    })
    destination = Path(args.output)
    destination.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


def cmd_field(args: argparse.Namespace) -> int:
    receipt = load_receipt(Path(args.receipt))
    if args.key not in receipt:
        raise ReleasePrError("unknown receipt field")
    print(receipt[args.key])
    return 0


def cmd_print(args: argparse.Namespace) -> int:
    if args.item == "identity":
        print(WORKFLOW_IDENTITY)
    elif args.item == "issuer":
        print(OIDC_ISSUER)
    else:
        raise ReleasePrError("unknown print item")
    return 0


def cmd_cosign_identity(_: argparse.Namespace) -> int:
    for arg in cosign_identity_args():
        print(arg)
    return 0


def cmd_attestation(args: argparse.Namespace) -> int:
    for arg in attestation_argv(args.image, args.digest):
        print(arg)
    return 0


def cmd_check_provenance(args: argparse.Namespace) -> int:
    receipt = load_receipt(Path(args.receipt))
    try:
        results = json.loads(Path(args.attestation).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleasePrError("attestation file is unreadable") from exc
    check_provenance(results, receipt)
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    render_release(Path(args.yueto_root), load_receipt(Path(args.receipt)), args.github_output)
    return 0


def cmd_open(args: argparse.Namespace) -> int:
    open_release(Path(args.yueto_root), load_receipt(Path(args.receipt)))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="release_pr")
    sub = parser.add_subparsers(dest="command", required=True)

    record = sub.add_parser("record-promoted")
    for name in (
        "service", "revision", "digest", "image", "architectures",
        "run_id", "run_attempt", "workflow_sha", "promoted_at",
    ):
        record.add_argument("--" + name.replace("_", "-"), dest=name, required=True)
    record.add_argument("--output", required=True)
    record.set_defaults(func=cmd_record)

    field = sub.add_parser("field")
    field.add_argument("receipt")
    field.add_argument("key")
    field.set_defaults(func=cmd_field)

    printer = sub.add_parser("print")
    printer.add_argument("item", choices=("identity", "issuer"))
    printer.set_defaults(func=cmd_print)

    identity = sub.add_parser("cosign-identity-args")
    identity.set_defaults(func=cmd_cosign_identity)

    attestation = sub.add_parser("attestation-args")
    attestation.add_argument("--image", required=True)
    attestation.add_argument("--digest", required=True)
    attestation.set_defaults(func=cmd_attestation)

    check = sub.add_parser("check-provenance")
    check.add_argument("--receipt", required=True)
    check.add_argument("--attestation", required=True)
    check.set_defaults(func=cmd_check_provenance)

    render = sub.add_parser("render")
    render.add_argument("--receipt", required=True)
    render.add_argument("--yueto-root", required=True)
    render.add_argument("--github-output", required=True)
    render.set_defaults(func=cmd_render)

    opened = sub.add_parser("open")
    opened.add_argument("--receipt", required=True)
    opened.add_argument("--yueto-root", required=True)
    opened.set_defaults(func=cmd_open)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ReleasePrError as exc:
        print(f"release-pr: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
