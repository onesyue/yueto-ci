from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import textwrap
import re
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "alert-chain-deadman.yml"
MIRROR = ROOT / "deadman" / "canonical"
CONTRACT = MIRROR / "config" / "alert-chain-deadman-observer-contract.json"
CHECKER = MIRROR / "scripts" / "alert-chain-deadman-check.py"
HOSTS = MIRROR / "config" / "hosts.json"
BASTION_HOST = MIRROR / "scripts" / "bastion_host.py"
BASTION_IP = "23.80.91.14"
BASTION_IP_ALLOWED = {
    "deadman/canonical/config/hosts.json",
    "tests/test_deadman_policy.py",
}


def _checker():
    spec = importlib.util.spec_from_file_location("_public_deadman_check", CHECKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

def _bastion_host():
    spec = importlib.util.spec_from_file_location("_public_bastion_host", BASTION_HOST)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _active_workflow() -> str:
    return "\n".join(
        line for line in WORKFLOW.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )


def test_public_deadman_mirror_matches_its_canonical_contract() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    expected = contract["canonical"]["checker_sha256"]
    assert contract["schema_version"] == 1
    assert contract["canonical"]["repository"] == "onesyue/yueops"
    assert contract["receiver"]["repository"] == "onesyue/yueto-ci"
    assert hashlib.sha256(CHECKER.read_bytes()).hexdigest() == expected
    assert contract["receiver"]["schedule_cron"] == "17,47 * * * *"
    assert contract["receiver"]["max_age_seconds"] == 2700
    assert contract["receiver"]["manual_missing_drill_input"] == "drill_missing"
    assert contract["receiver"]["schedule_liveness_audit_days"] == 45
    assert contract["transport"]["user"] == "deadman-reader"


def test_public_deadman_checks_both_mirror_and_private_canonical_bytes() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    verify = text.split("Verify the mirrored contract", 1)[1].split(
        "Prepare deliberate missing-receipt drill", 1
    )[0]
    assert "receiver_contract != canonical_contract" in verify
    assert "hashlib.sha256" in verify
    assert "receiver mirror" in verify
    assert "YueOps canonical" in verify
    assert "repository: onesyue/yueops" in text
    assert "ref: master" in text
    assert (
        "token: ${{ steps.yueops_read_token.outputs.token || secrets.YUETO_CI_PAT }}"
        in text
    )
    assert text.count("persist-credentials: false") == 2
    assert text.count(
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
    ) == 2


def test_public_deadman_trigger_permissions_and_missing_drill_are_fail_closed() -> None:
    text = _active_workflow()
    assert "cron: '17,47 * * * *'" in text
    assert "workflow_dispatch:" in text
    assert "drill_missing:" in text
    assert "type: boolean" in text and "default: false" in text
    assert "contents: read" in text
    # Incidents are created in private YueOps with a separately minted App
    # token (or the legacy YUETO_CI_PAT). The public repository's own
    # GITHUB_TOKEN never needs write permission to either repository.
    permissions = text.split("\npermissions:\n", 1)[1].split("\n\n", 1)[0]
    assert "write" not in permissions
    assert re.search(r"(?m)^\s+issues:\s*write", text) is None
    assert "pull_request:" not in text
    assert "push:" not in text

    drill = text.split("Prepare deliberate missing-receipt drill", 1)[1].split(
        "Fetch heartbeat receipt", 1
    )[0]
    fetch_header = text.split("Fetch heartbeat receipt", 1)[1].split("env:", 1)[0]
    assert (
        "github.event_name == 'workflow_dispatch' && inputs.drill_missing == true"
        in drill
    )
    assert (
        "github.event_name != 'workflow_dispatch' || inputs.drill_missing != true"
        in fetch_header
    )
    assert ": > receipt.json" in drill


def test_public_deadman_transport_is_dedicated_pinned_and_bounded() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    fetch = text.split("Fetch heartbeat receipt", 1)[1].split(
        "Decide using the canonical", 1
    )[0]
    active = "\n".join(
        line for line in fetch.splitlines()
        if not line.lstrip().startswith("#")
    )
    for marker in (
        "DEADMAN_SSH_KEY_B64",
        "if [ -z \"@@{SSH_KEY_B64}\" ]",
        "exit 1",
        "BASTION_USER: 'deadman-reader'",
        "StrictHostKeyChecking=yes",
        "BatchMode=yes",
        "PasswordAuthentication=no",
        "KbdInteractiveAuthentication=no",
        "ServerAliveInterval=15",
        "ServerAliveCountMax=2",
        "timeout --signal=TERM --kill-after=5s 75s",
        "/usr/bin/cat -- /var/lib/yue-alert-heartbeat/heartbeat.json",
        "AAAAC3NzaC1lZDI1NTE5AAAAI",
    ):
        assert marker.replace("@@", "$") in fetch
    assert "accept-new" not in active
    assert "StrictHostKeyChecking=no" not in active
    assert "YUEOPS_SSH_PRIVATE_KEY" not in fetch
    assert "yueops_rotation" not in fetch
    assert "cat ssh.err" not in active and "sed " not in active
    assert ": > receipt.json" in fetch


def test_public_deadman_failure_reporting() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "--max-age-seconds 2700" in text
    report = text.split("Report deadman failure", 1)[1]
    assert "always() && (failure() || cancelled())" in report
    assert "gh issue" not in text and "permission-issues" not in text
    assert "continue-on-error" not in report
    script = textwrap.dedent(report.split("run: |\n", 1)[1])
    # The central runner calls these functions with no arguments.
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for drill in ("true", "false"):
            summary = root / drill
            result = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                                    env={**os.environ, "DRILL_MISSING": drill,
                                         "RUN_URL": "https://example.invalid/run/1",
                                         "GITHUB_STEP_SUMMARY": str(summary)}, timeout=10)
            assert result.returncode == 1
            assert "::error::" in result.stdout
            assert "https://example.invalid/run/1" in summary.read_text()
            assert ("Intentional" in summary.read_text()) == (drill == "true")


def _receipt(**overrides: object) -> str:
    payload: dict[str, object] = {
        "ts": "2026-08-13T01:00:00Z",
        "epoch": 1_000_000,
        "seq": 7,
        "status": "ok",
        "problems": [],
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_mirrored_checker_distinguishes_every_failure_state() -> None:
    checker = _checker()
    assert checker.DEFAULT_MAX_AGE_SECONDS == 2700
    assert checker.evaluate(
        _receipt(), now=1_000_060, max_age_seconds=2700
    ).state == "ok"
    assert checker.evaluate(None, now=1_000_060, max_age_seconds=2700).state == "missing"
    assert checker.evaluate("", now=1_000_060, max_age_seconds=2700).state == "missing"
    assert checker.evaluate(
        "not-json", now=1_000_060, max_age_seconds=2700
    ).state == "corrupt"
    assert checker.evaluate(
        _receipt(), now=1_004_000, max_age_seconds=2700
    ).state == "stale"
    assert checker.evaluate(
        _receipt(), now=900_000, max_age_seconds=2700
    ).state == "corrupt"
    assert checker.evaluate(
        _receipt(status="degraded", problems=["delivery unavailable"]),
        now=1_000_060,
        max_age_seconds=2700,
    ).state == "degraded"


def test_mirrored_checker_cli_alarms_when_receipt_cannot_be_opened() -> None:
    with tempfile.TemporaryDirectory() as directory:
        receipt = Path(directory) / "missing.json"
        result = subprocess.run(
            [sys.executable, str(CHECKER), "--receipt", str(receipt)],
            capture_output=True,
            text=True,
            timeout=10,
        )

    assert result.returncode == 1
    assert result.stdout.startswith("::error::")
    assert "[missing]" in result.stdout


def test_mirrored_checker_cli_alarms_on_empty_stdin() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--receipt", "-"],
        input="",
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 1
    assert result.stdout.startswith("::error::")
    assert "[missing]" in result.stdout


def test_mirrored_checker_cli_rejects_zero_max_age() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--receipt", "-", "--max-age-seconds", "0"],
        input="",
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 2
    assert "--max-age-seconds" in result.stderr
    assert result.stdout == ""

def test_bastion_address_resolves_from_the_inventory_name() -> None:
    module = _bastion_host()
    assert module.HOST_NAME == "bastion"
    assert module.ENV_NAME == "YUEOPS_HOST_BASTION"
    host = module.resolve_bastion_host(env={})
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    inventory = json.loads(HOSTS.read_text(encoding="utf-8"))
    assert contract["transport"]["host_name"] == "bastion"
    assert "host" not in contract["transport"]
    assert inventory["hosts"] == [
        {
            "name": "bastion",
            "role": "Operations services and PostgreSQL standby",
            "ip": BASTION_IP,
        }
    ]
    assert host == BASTION_IP
    key = contract["transport"]["host_key"]
    fetch = WORKFLOW.read_text(encoding="utf-8").split("Fetch heartbeat receipt", 1)[1]
    assert f"${{BASTION_HOST}}" in fetch
    assert key["algorithm"] in fetch and key["public_key"] in fetch
    assert f"{host} {key['algorithm']} {key['public_key']}".startswith(BASTION_IP + " ssh-ed25519 ")
    rendered = subprocess.run(
        [sys.executable, str(BASTION_HOST)],
        capture_output=True,
        text=True,
        timeout=30,
        env={key: value for key, value in os.environ.items() if key != module.ENV_NAME},
        check=False,
    )
    assert rendered.returncode == 0
    assert rendered.stdout == BASTION_IP + "\n"


def test_bastion_env_overrides_inventory_and_works_without_it() -> None:
    module = _bastion_host()
    assert module.resolve_bastion_host(env={module.ENV_NAME: "203.0.113.10"}) == "203.0.113.10"
    with tempfile.TemporaryDirectory() as directory:
        missing = Path(directory) / "hosts.json"
        absent_contract = Path(directory) / "contract.json"
        only_env = module.resolve_bastion_host(
            inventory=missing,
            contract=absent_contract,
            env={module.ENV_NAME: "203.0.113.11"},
        )
        assert only_env == "203.0.113.11"
        try:
            module.resolve_bastion_host(
                inventory=missing, contract=absent_contract, env={}
            )
        except SystemExit as exc:
            assert exc.code == "YUEOPS_HOST_BASTION is unset and the host inventory is absent"
        else:
            raise AssertionError("missing inventory must fail closed")
        try:
            module.resolve_bastion_host(env={module.ENV_NAME: "not-an-address"})
        except SystemExit as exc:
            assert exc.code == "bastion host must be an IPv4 address"
        else:
            raise AssertionError("invalid override must fail closed")
    overridden = subprocess.run(
        [sys.executable, str(BASTION_HOST)],
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, module.ENV_NAME: "203.0.113.10"},
        check=False,
    )
    assert overridden.returncode == 0
    assert overridden.stdout == "203.0.113.10\n"


def test_bastion_address_stays_in_the_inventory() -> None:
    assert HOSTS.read_text(encoding="utf-8").count(BASTION_IP) == 1
    assert BASTION_IP not in WORKFLOW.read_text(encoding="utf-8")
    assert BASTION_IP not in CONTRACT.read_text(encoding="utf-8")
    assert BASTION_IP not in BASTION_HOST.read_text(encoding="utf-8")
    result = subprocess.run(
        ["git", "grep", "-F", "-l", "--", BASTION_IP],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode in (0, 1), result.stderr
    found = set(result.stdout.splitlines())
    tracked = subprocess.run(
        ["git", "ls-files", "--", "deadman/canonical/config/hosts.json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    if tracked.stdout.strip():
        assert "deadman/canonical/config/hosts.json" in found
    assert sorted(found - BASTION_IP_ALLOWED) == []

def load_tests(
    loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str | None
) -> unittest.TestSuite:
    # These policies also run under the workspace's pytest gate. Expose the
    # same functions to the dependency-free central unittest runner so merely
    # compiling this file cannot be mistaken for executing its assertions.
    checks = sorted(
        (name, check)
        for name, check in globals().items()
        if name.startswith("test_") and callable(check)
    )
    if len(checks) < 6:
        raise RuntimeError("deadman policy coverage fell below six checks")
    return unittest.TestSuite(unittest.FunctionTestCase(check) for _, check in checks)


if __name__ == "__main__":
    unittest.main()
