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
OPS_HOST = MIRROR / "scripts" / "ops_host_public.py"
# transport.host is the YueOps producer field. The address literal stays only
# in that byte-compared contract, not in a second inventory.
HOST_LITERAL_ALLOWED = {
    "deadman/canonical/config/alert-chain-deadman-observer-contract.json",
}


def _checker():
    spec = importlib.util.spec_from_file_location("_public_deadman_check", CHECKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

def _ops_host():
    spec = importlib.util.spec_from_file_location("_public_ops_host_public", OPS_HOST)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _registry(ip: str, *, name: str = "ops_host_public", extra: list | None = None) -> str:
    roles = [{"name": name, "kind": "ipv4", "current": ip}]
    if extra:
        roles.extend(extra)
    return json.dumps({"schema_version": 1, "roles": roles})


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
        "DEADMAN_USER: 'deadman-reader'",
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

def test_ops_host_public_resolves_from_the_native_role() -> None:
    module = _ops_host()
    assert module.ROLE == "ops_host_public"
    assert module.ENV_NAME == "YUEOPS_HOST_OPS_HOST_PUBLIC"
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    host = contract["transport"]["host"]
    assert "host_name" not in contract["transport"]
    assert "bastion" not in CONTRACT.read_text(encoding="utf-8")
    assert not (MIRROR / "config" / "hosts.json").exists()
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "bastion" not in workflow.lower()
    assert "ops_host_public.py" in workflow
    assert "--check" in workflow
    assert "--inventory .ci-yueops/config/hosts.json" in workflow
    assert "YUEOPS_HOST_OPS_HOST_PUBLIC" in workflow
    assert "YUEOPS_HOST_BASTION" not in workflow
    fetch = workflow.split("Fetch heartbeat receipt", 1)[1]
    assert f"${{OPS_HOST_PUBLIC}}" in fetch
    key = contract["transport"]["host_key"]
    assert key["algorithm"] in fetch and key["public_key"] in fetch
    assert f"{host} {key['algorithm']} {key['public_key']}".startswith(host + " ssh-ed25519 ")
    with tempfile.TemporaryDirectory() as directory:
        inventory = Path(directory) / "hosts.json"
        inventory.write_text(_registry(host), encoding="utf-8")
        assert module.resolve_ops_host_public(inventory=inventory, env={}) == host
        module.check_ops_host_public(inventory, CONTRACT)
        assert module.project_ops_host_public(inventory) == f"{module.ENV_NAME}={host}\n"
        clean_env = {key: value for key, value in os.environ.items() if key != module.ENV_NAME}
        rendered = subprocess.run(
            [sys.executable, str(OPS_HOST), "--inventory", str(inventory)],
            capture_output=True,
            text=True,
            timeout=30,
            env=clean_env,
            check=False,
        )
        assert rendered.returncode == 0
        assert rendered.stdout == host + "\n"
        projected = subprocess.run(
            [sys.executable, str(OPS_HOST), "--project", "--inventory", str(inventory)],
            capture_output=True,
            text=True,
            timeout=30,
            env=clean_env,
            check=False,
        )
        assert projected.returncode == 0
        assert projected.stdout == f"{module.ENV_NAME}={host}\n"
        checked = subprocess.run(
            [sys.executable, str(OPS_HOST), "--check", "--inventory", str(inventory)],
            capture_output=True,
            text=True,
            timeout=30,
            env=clean_env,
            check=False,
        )
        assert checked.returncode == 0
        assert checked.stdout == ""


def test_ops_host_public_override_and_drift_fail_closed() -> None:
    module = _ops_host()
    assert module.resolve_ops_host_public(
        inventory=None, env={module.ENV_NAME: "203.0.113.10"}
    ) == "203.0.113.10"
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        missing = root / "hosts.json"
        absent_contract = root / "contract.json"
        assert module.resolve_ops_host_public(
            inventory=missing,
            contract=absent_contract,
            env={module.ENV_NAME: "203.0.113.11"},
        ) == "203.0.113.11"
        try:
            module.resolve_ops_host_public(
                inventory=missing, contract=absent_contract, env={}
            )
        except SystemExit as exc:
            assert exc.code == f"{module.ENV_NAME} is unset and the host inventory is absent"
        else:
            raise AssertionError("missing inventory must fail closed")
        try:
            module.resolve_ops_host_public(env={module.ENV_NAME: "not-an-address"})
        except SystemExit as exc:
            assert exc.code == "ops_host_public must be an IPv4 address"
        else:
            raise AssertionError("invalid override must fail closed")
        pinned = json.loads(CONTRACT.read_text(encoding="utf-8"))["transport"]["host"]
        drifted = root / "drift.json"
        drifted.write_text(_registry("203.0.113.20"), encoding="utf-8")
        try:
            module.check_ops_host_public(drifted, CONTRACT)
        except SystemExit as exc:
            assert exc.code == "observer contract drifted from ops_host_public"
        else:
            raise AssertionError("drift must fail closed")
        both = root / "both.json"
        both.write_text(
            _registry(
                "203.0.113.21",
                name="pg_standby_host",
                extra=[{"name": "ops_host_public", "kind": "ipv4", "current": "203.0.113.10"}],
            ),
            encoding="utf-8",
        )
        local_contract = root / "local.json"
        local_contract.write_text(
            json.dumps({"transport": {"host": "203.0.113.10"}}),
            encoding="utf-8",
        )
        assert module.resolve_ops_host_public(
            inventory=both, contract=local_contract, env={}
        ) == "203.0.113.10"
        module.check_ops_host_public(both, local_contract)
        standby_contract = root / "standby-contract.json"
        standby_contract.write_text(
            json.dumps({"transport": {"host": "203.0.113.21"}}),
            encoding="utf-8",
        )
        try:
            module.check_ops_host_public(both, standby_contract)
        except SystemExit as exc:
            assert exc.code == "observer contract drifted from ops_host_public"
        else:
            raise AssertionError("pg_standby_host must not satisfy the contract")
        standby_only = root / "standby-only.json"
        standby_only.write_text(
            _registry("203.0.113.21", name="pg_standby_host"), encoding="utf-8"
        )
        try:
            module.resolve_ops_host_public(
                inventory=standby_only, contract=absent_contract, env={}
            )
        except SystemExit as exc:
            assert exc.code == "host inventory has no ops_host_public role"
        else:
            raise AssertionError("pg_standby_host must not satisfy ops_host_public")
        historic = root / "old.json"
        historic.write_text(
            json.dumps({"schema_version": 1, "hosts": [{"name": "bastion", "ip": pinned}]}),
            encoding="utf-8",
        )
        try:
            module.check_ops_host_public(historic, CONTRACT)
        except SystemExit as exc:
            assert exc.code == "historic host inventory"
        else:
            raise AssertionError("historic inventory must fail closed")
        named = root / "named.json"
        named.write_text(
            _registry(
                pinned,
                extra=[{"name": "bastion", "kind": "ipv4", "current": pinned}],
            ),
            encoding="utf-8",
        )
        try:
            module.check_ops_host_public(named, CONTRACT)
        except SystemExit as exc:
            assert exc.code == "historic host name"
        else:
            raise AssertionError("historic role name must fail closed")
        alias = root / "alias.json"
        alias.write_text(
            json.dumps({"transport": {"host_name": "ops_host_public", "host": pinned}}),
            encoding="utf-8",
        )
        try:
            module.check_ops_host_public(root / "unused.json", alias)
        except SystemExit as exc:
            assert exc.code == "deadman transport uses a historic host name"
        else:
            raise AssertionError("host_name must fail closed")
    overridden = subprocess.run(
        [sys.executable, str(OPS_HOST)],
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, module.ENV_NAME: "203.0.113.10"},
        check=False,
    )
    assert overridden.returncode == 0
    assert overridden.stdout == "203.0.113.10\n"


def test_ops_host_address_stays_in_the_mirrored_contract() -> None:
    host = json.loads(CONTRACT.read_text(encoding="utf-8"))["transport"]["host"]
    assert host not in WORKFLOW.read_text(encoding="utf-8")
    assert host not in OPS_HOST.read_text(encoding="utf-8")
    result = subprocess.run(
        ["git", "grep", "-F", "-l", "--", host],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode in (0, 1), result.stderr
    assert set(result.stdout.splitlines()) == HOST_LITERAL_ALLOWED
    tracked = subprocess.run(
        [
            "git", "ls-files", "--",
            "deadman/canonical/config/hosts.json",
            "deadman/canonical/scripts/bastion_host.py",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    assert tracked.stdout.strip() == ""

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
