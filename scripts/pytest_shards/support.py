"""Shared git, digest, identity and evidence helpers for shard policy."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import time
from pathlib import Path, PurePosixPath

from .config import EXPECTED_CONFIG, IDENTITY_FIELDS, OPTIONAL_RETENTION_CONFIG, RETIRED_HOST_MODULE, SHA


ROOT = Path(__file__).resolve().parents[2]
_SOURCE_SPEC = importlib.util.spec_from_file_location("trusted_source_evidence", ROOT / "scripts/source_evidence.py")
source_evidence = importlib.util.module_from_spec(_SOURCE_SPEC)
_SOURCE_SPEC.loader.exec_module(source_evidence)
_BRAND_SPEC = importlib.util.spec_from_file_location(
    "ci_brand_literals", ROOT / "scripts/brand_literals.py")
_brand = importlib.util.module_from_spec(_BRAND_SPEC)
_BRAND_SPEC.loader.exec_module(_brand)


RETIRED_HOST_IDS = {
    RETIRED_HOST_MODULE + "::" + name + "[" + _brand.RETIRED_MINI_PRIMARY_HOST + "]"
    for name in (
        "test_native_mini_index_assets_and_telegram_frame_policy",
        "test_native_auth_is_not_panel_cookie_or_bearer_and_secret_paths_do_not_log",
        "test_native_alias_upload_method_body_limits_and_cache",
    )
}


RETIRED_HOST_SECOND_IDS = {
    RETIRED_HOST_MODULE + "::" + name + "[" + _brand.RETIRED_MINI_ALTERNATE_HOST + "]"
    for name in (
        "test_native_mini_index_assets_and_telegram_frame_policy",
        "test_native_auth_is_not_panel_cookie_or_bearer_and_secret_paths_do_not_log",
        "test_native_alias_upload_method_body_limits_and_cache",
    )
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode()


class EvidenceUnavailable(ValueError):
    """Local Git history cannot establish the admission policy's ancestry."""


def git(source, *args):
    try:
        return subprocess.check_output(["git", "-C", str(source), *args],
                                       stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as error:
        # merge-base exit 1 means proven non-ancestry; higher codes mean the
        # proof could not run (for example a missing sealed predecessor).
        if args[:2] == ("merge-base", "--is-ancestor") and error.returncode != 1:
            raise EvidenceUnavailable("local ancestry evidence unavailable") from None
        raise


def safe_module(name):
    path = PurePosixPath(name)
    return (isinstance(name, str) and path.as_posix() == name
            and not path.is_absolute() and ".." not in path.parts
            and len(path.parts) >= 2 and path.parts[0] == "tests"
            and path.name.startswith("test_") and path.suffix == ".py"
            and "::" not in name and not any(ord(c) < 32 for c in name))


def context_ok(context):
    require(set(context) == set(IDENTITY_FIELDS), "incomplete or extra run identity")
    for key in ("policy_revision", "board_revision"):
        require(isinstance(context[key], str) and SHA.fullmatch(context[key]),
                f"invalid {key}")
    for key in ("run_id", "run_attempt"):
        require(isinstance(context[key], str) and re.fullmatch(r"[1-9][0-9]*", context[key]),
                f"invalid {key}")
    for key in ("runner_os", "runner_arch", "runner_image"):
        require(isinstance(context[key], str) and context[key].strip()
                and context[key] != "UNKNOWN", f"missing {key}")


def runner_context(planned, environment):
    """Bind this allocation, not the separately allocated planning job's image."""
    observed = {key: environment.get(name) for name, key in (
        ("RUNNER_OS", "runner_os"), ("RUNNER_ARCH", "runner_arch"),
        ("ImageVersion", "runner_image"))}
    require(all(isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,128}", v)
                and v != "UNKNOWN" for v in observed.values()), "missing runner identity")
    require(all(observed[k] == planned[k] for k in ("runner_os", "runner_arch")),
            "executing runner OS or architecture differs")
    return observed


def runner_summary(planned, roles):
    images = sorted({r["runner_image"] for r in roles.values()})
    return {"planning_runner_image": planned["runner_image"], "roles": roles,
            "execution_images": images, "mixed_execution_images": len(images) > 1,
            "performance_comparison": "NOT_ESTABLISHED"}


def collection_config_ok(actual):
    """Exact collection keys, plus only the reviewed retention keys/values."""
    extra = {k: v for k, v in actual.items() if k not in EXPECTED_CONFIG}
    return (all(actual.get(k) == v for k, v in EXPECTED_CONFIG.items())
            and all(OPTIONAL_RETENTION_CONFIG.get(k) == v for k, v in extra.items()))


def read_json(path):
    require(path.is_file() and not path.is_symlink(), f"missing or symlink evidence: {path.name}")
    return json.loads(path.read_text())


def tree_inputs(source, revision):
    require(SHA.fullmatch(revision), "baseline requires an exact source revision")
    rows = git(source, "ls-tree", "-rz", revision).decode().split("\0")
    files = {}
    for row in rows:
        if row:
            metadata, path = row.split("\t", 1)
            mode, kind, blob = metadata.split()
            if kind == "blob":
                files[path] = (mode, blob)
    return files


def shared_inputs(source, revision):
    result = {}
    for path, (mode, blob) in tree_inputs(source, revision).items():
        name = PurePosixPath(path).name
        if (name in ("conftest.py", "pytest.ini", "pyproject.toml", "uv.lock",
                     "package.json", "package-lock.json", "pnpm-lock.yaml")
                or name.startswith("requirements") and name.endswith((".txt", ".lock"))
                or path.startswith("tests/") and path.endswith(".py") and not safe_module(path)):
            require(mode == "100644" or mode == "100755", "symlink shared test input")
            result[path] = blob
    require("pytest.ini" in result, "missing shared collection inputs")
    return result


def baseline_bytes(baseline):
    return (json.dumps(baseline, indent=2, ensure_ascii=False) + "\n").encode()


def _commit_ref(source, ref):
    try:
        return git(source, "rev-parse", "--verify", "--end-of-options",
                   ref + "^{commit}").decode().strip()
    except subprocess.CalledProcessError:
        return ""


def on_default_branch(source, revision):
    """True when revision is the default branch tip or its ancestor.

    The plan checkout of a SHA does not create origin/master by itself.
    The workflow fetches refs/remotes/origin/master first. A local fixture
    may use refs/heads/master. A missing ref fails closed.
    """
    require(isinstance(revision, str) and SHA.fullmatch(revision),
            "exact source SHA required")
    found = False
    for ref in ("refs/remotes/origin/master", "refs/heads/master"):
        tip = _commit_ref(source, ref)
        if not tip:
            continue
        found = True
        if tip == revision:
            return True
        try:
            git(source, "merge-base", "--is-ancestor", revision, ref)
            return True
        except subprocess.CalledProcessError:
            continue
    require(found, "default branch ref is missing")
    return False


def admit_signed_default_branch(source, revision, policy_dir=None):
    """Admit a source SHA that is on the default branch and owner-signed.

    Timing shards are chosen by the caller. File lists, helper additions and
    conftest edits are not a separate seal. policy_dir defaults to the
    validator's policy directory.
    """
    require(on_default_branch(source, revision),
            "source SHA is not on the default branch")
    try:
        source_evidence.verify_commit(
            git(source, "cat-file", "commit", revision), policy_dir)
    except source_evidence.Rejected as error:
        raise ValueError("unauthorized source signature") from error


def serial_modules(source):
    result = subprocess.run(["bash", "scripts/run-pytest-parallel.sh", "--describe-ci-selection"],
                            cwd=source, capture_output=True, text=True, check=True, timeout=15)
    description = json.loads(result.stdout)
    require(set(description) == {"schema", "serial_modules"} and description["schema"] == 1
            and isinstance(description["serial_modules"], list)
            and description["serial_modules"], "invalid source serial declaration")
    return description["serial_modules"]


def workflow_identity():
    identity = {
        "policy_revision": os.environ.get("GITHUB_SHA"),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
    }
    require(SHA.fullmatch(identity["policy_revision"] or "")
            and identity["policy_revision"] == git(ROOT, "rev-parse", "HEAD").decode().strip(),
            "workflow policy identity differs")
    for key in ("run_id", "run_attempt"):
        require(re.fullmatch(r"[1-9][0-9]*", identity[key] or ""), f"invalid {key}")
    require(os.environ.get("GITHUB_REPOSITORY") == "onesyue/yueto-ci",
            "unexpected workflow repository")
    handoff = os.environ.get("YUETO_HANDOFF_ATTEMPT", "")
    if handoff:
        require(re.fullmatch(r"[1-9][0-9]*", handoff) is not None,
                "invalid handoff attempt")
        require(int(handoff) <= int(identity["run_attempt"]),
                "handoff attempt is newer than this job")
        identity["run_attempt"] = handoff
    return identity


def seal(value, key):
    value[key] = sha(encoded(value))
    return value


def role_order(value):
    assignments = [a["id"] for a in value["assignments"]]
    parts = [f"reference-{assignment}" for assignment in assignments]
    return ["native", *parts, *[a for a in assignments if a == "serial"],
            *[a for a in assignments if a != "serial"]]


def verify_source_evidence(value, source):
    if "source_evidence" in value:
        require(source is not None, "source checkout required for owner evidence")
        require(source_evidence.load(source, value["source_revision"]) == value["source_evidence"],
                "source evidence differs from original admission")


def retain_rejection(args, error):
    """Keep a failed diagnostic, never a synthetic pytest/native terminal."""
    output = args.output.absolute()
    require(not any(p.is_symlink() for p in (output, *output.parents)),
            "unsafe rejection evidence directory")
    output.mkdir(parents=True, exist_ok=True)
    require(output.is_dir(), "invalid rejection evidence directory")
    safe = {}
    for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_SHA",
                "RUNNER_OS", "RUNNER_ARCH", "ImageVersion"):
        value = os.environ.get(key)
        safe[key] = (value if isinstance(value, str)
                     and re.fullmatch(r"[A-Za-z0-9._-]{1,128}", value) else None)
    record = {"schema": 1, "status": "REJECTED", "release_acceptance": False,
              "stage": args.command, "error_class": type(error).__name__,
              "identity": safe, "recorded_unix_ns": time.time_ns()}
    record["reason_code"] = {
        "missing runner identity": "RUNNER_IDENTITY_MISSING",
        "executing runner OS or architecture differs": "RUNNER_PLATFORM_MISMATCH",
        "executing source differs or is dirty": "SOURCE_IDENTITY_MISMATCH",
        "runner identity changed during preparation": "RUNNER_CHANGED",
        "runner identity changed during execution": "RUNNER_CHANGED",
        "native runner identity changed during execution": "RUNNER_CHANGED",
    }.get(str(error), "VALIDATION_REJECTED")
    role = getattr(args, "role", "native")
    record["assignment_id"] = role if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", role) else None
    if args.admission.is_file() and not args.admission.is_symlink():
        record["admission_file_sha256"] = sha(args.admission.read_bytes())
    with (output / "rejected.json").open("x") as handle:
        handle.write(json.dumps(record) + "\n")
