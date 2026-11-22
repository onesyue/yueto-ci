import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts/validate-native-node-contract.py"


@pytest.fixture
def resolve(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    validator = scripts / VALIDATOR.name
    validator.write_bytes(VALIDATOR.read_bytes())
    # No native-node-contract.json in the policy tree.
    (scripts / "input-fingerprint.py").write_text(
        "import os\n"
        "class Unknown(Exception): pass\n"
        "def ghcr_latest(service, user, password):\n"
        "    assert (service, user, password) == ('yueboard', 'fixture', 'fixture')\n"
        "    return 'sha256:' + 'a' * 64, os.environ['FIXTURE_REVISION']\n"
    )

    def run(explicit="", promoted=None):
        env = dict(os.environ, GHCR_USER="fixture", GHCR_PASSWORD="fixture")
        if promoted is not None:
            env["FIXTURE_REVISION"] = promoted
        return subprocess.run(
            [sys.executable, validator, "resolve-yueboard-ref", "--explicit", explicit],
            capture_output=True, text=True, env=env, check=False,
        )

    return run


def test_explicit_ref_skips_registry(resolve):
    result = resolve(explicit="1" * 40)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "1" * 40 + "\n"


def test_default_uses_promoted_revision(resolve):
    result = resolve(promoted="2" * 40)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "2" * 40 + "\n"


@pytest.mark.parametrize("explicit,promoted", [("master", "2" * 40), ("", "bad"), ("", None)])
def test_resolution_fails_closed(resolve, explicit, promoted):
    result = resolve(explicit=explicit, promoted=promoted)
    assert result.returncode != 0
    assert result.stdout == ""


def test_workflows_check_out_the_resolved_revision():
    import yaml

    workflows = ROOT / ".github/workflows"
    build = yaml.safe_load((workflows / "build.yml").read_text())["jobs"]
    plan = next(s for s in build["plan"]["steps"] if s.get("id") == "plan")
    assert 'resolve-yueboard-ref --explicit="$YUEBOARD_CONTRACT_REF"' in plan["run"]
    assert 'echo "yueboard_contract_ref=$yueboard_contract_ref"' in plan["run"]
    board = next(s for s in build["validate"]["steps"] if s.get("with", {}).get("path") == ".ci-yueboard")
    assert board["if"] == "matrix.validation == 'yue-node' || matrix.validation == 'yueops'"
    assert board["with"]["ref"] == "${{ needs.plan.outputs.yueboard_contract_ref }}"
    capture = yaml.safe_load((workflows / "board-visual-capture.yml").read_text())["jobs"]["capture"]
    source = next(s for s in capture["steps"] if s.get("id") == "source")
    assert 'resolve-yueboard-ref --explicit="$YUEBOARD_CONTRACT_REF"' in source["run"]
    checkout = next(s for s in capture["steps"] if s.get("with", {}).get("path") == "source")
    assert checkout["with"]["ref"] == "${{ steps.source.outputs.revision }}"
    for path in (workflows / "build.yml", workflows / "board-visual-capture.yml",
                 ROOT / "scripts/ci_check_board_local.py", VALIDATOR):
        assert "yueboard_contract_pin" not in path.read_text()
