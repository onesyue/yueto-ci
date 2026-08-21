from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "alert-chain-deadman.yml"
MIRROR = ROOT / "deadman" / "canonical"
CONTRACT = MIRROR / "config" / "alert-chain-deadman-observer-contract.json"
CHECKER = MIRROR / "scripts" / "alert-chain-deadman-check.py"


def _checker():
    spec = importlib.util.spec_from_file_location("_public_deadman_check", CHECKER)
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
    assert "ref: main" in text
    assert "token: ${{ secrets.YUETO_CI_PAT }}" in text
    assert text.count("persist-credentials: false") == 2
    assert text.count(
        "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803"
    ) == 2


def test_public_deadman_trigger_permissions_and_missing_drill_are_fail_closed() -> None:
    text = _active_workflow()
    assert "cron: '17,47 * * * *'" in text
    assert "workflow_dispatch:" in text
    assert "drill_missing:" in text
    assert "type: boolean" in text and "default: false" in text
    assert "contents: read" in text
    # Incidents are created in private YueOps with YUETO_CI_PAT. The public
    # repository token never needs write permission to either repository.
    assert "issues: write" not in text
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


def test_public_deadman_verdict_and_incident_are_not_best_effort() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "--max-age-seconds 2700" in text
    incident = text.split("Open or update the private YueOps incident", 1)[1]
    assert "always() && (failure() || cancelled())" in incident
    assert "repo='onesyue/yueops'" in incident
    assert "GH_TOKEN: ${{ secrets.YUETO_CI_PAT }}" in incident
    assert "gh label create alert-chain" in incident
    assert "gh issue create" in incident and "--assignee onesyue" in incident
    assert "DRILL_MISSING:" in incident
    assert "告警链失联演练（public deadman）" in incident
    assert "请人工确认收到后关闭本演练单" in incident
    assert '--search "in:title $title"' in incident
    assert "receipt.json" not in incident
    assert "ssh.err" not in incident
    assert "continue-on-error" not in incident


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
