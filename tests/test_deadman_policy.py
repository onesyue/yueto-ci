from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "alert-chain-deadman.yml"


def test_public_deadman_uses_canonical_private_policy() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "cron: '*/30 * * * *'" in text
    assert "repository: onesyue/yueops" in text
    assert "token: ${{ secrets.YUETO_CI_PAT }}" in text
    assert "persist-credentials: false" in text
    assert ".ci-yueops/scripts/alert-chain-deadman-check.py" in text


def test_public_deadman_key_is_restricted_by_contract_and_fail_closed() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    fetch = text.split("Fetch heartbeat receipt", 1)[1].split(
        "Decide using the canonical", 1
    )[0]
    fetch_code = "\n".join(
        line for line in fetch.splitlines() if not line.lstrip().startswith("#")
    )

    assert "DEADMAN_SSH_KEY_B64" in fetch
    assert "if [ -z \"${SSH_KEY_B64}\" ]" in fetch
    assert "exit 1" in fetch
    assert "StrictHostKeyChecking=yes" in fetch
    assert "UserKnownHostsFile=~/.ssh/known_hosts_deadman" in fetch
    assert "ServerAliveInterval=15" in fetch
    assert "ServerAliveCountMax=2" in fetch
    assert "accept-new" not in fetch_code
    assert "StrictHostKeyChecking=no" not in fetch_code
    assert "YUEOPS_SSH_PRIVATE_KEY" not in fetch
    assert "yueops_rotation" not in fetch


def test_public_deadman_failure_creates_private_incident() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    incident = text.split("Open or update the private YueOps incident", 1)[1]

    assert "if: failure() || cancelled()" in incident
    assert "repo='onesyue/yueops'" in incident
    assert "GH_TOKEN: ${{ secrets.YUETO_CI_PAT }}" in incident
    assert "gh issue create" in incident
