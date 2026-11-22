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
