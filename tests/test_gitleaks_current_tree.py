"""yueto-ci gitleaks scans the current tree and an explicit commit range.

The installer in ops-validation-gitleaks.sh stays an installer. This gate
must not walk full history: historical credentials stay out of the allowlist.
"""

from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCAN = ROOT / "scripts" / "scan-yueto-ci-gitleaks.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "gitleaks.yml"
CONFIG = ROOT / ".gitleaks.toml"
INSTALLER = ROOT / "scripts" / "ops-validation-gitleaks.sh"
PIN = "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"
TRIAGE = "/workspace/handoff/r6-data/SEC-TRIAGE.md"
# Historical yueops telegram bot token prefix. Never allowlist it.
HISTORICAL_TOKEN_PREFIX = "7ba416b81d34"


class GitleaksCurrentTreeTest(unittest.TestCase):
    def test_pin_matches_the_installer_and_the_workflow_is_blocking(self) -> None:
        script = SCAN.read_text(encoding="utf-8")
        installer = INSTALLER.read_text(encoding="utf-8")
        workflow = WORKFLOW.read_text(encoding="utf-8")
        config = CONFIG.read_text(encoding="utf-8")
        self.assertIn(PIN, script)
        self.assertIn(PIN, installer)
        self.assertIn("8.30.1", script)
        self.assertIn("sha256sum --check --strict", script)
        self.assertLess(script.index("sha256sum --check --strict"), script.index('"$bin" dir'))
        self.assertIn("--redact", script)
        self.assertIn("--log-opts=", script)
        self.assertNotIn("--all", script)
        self.assertNotIn("gitleaks git --", workflow)
        self.assertIn("pull_request:", workflow)
        self.assertIn("branches: [master]", workflow)
        self.assertIn("bash scripts/scan-yueto-ci-gitleaks.sh", workflow)
        self.assertNotIn("continue-on-error", workflow)
        self.assertNotIn(HISTORICAL_TOKEN_PREFIX, config)
        self.assertNotIn(HISTORICAL_TOKEN_PREFIX, script)
        self.assertEqual(config.count(TRIAGE), 2)
        self.assertIn('useDefault = true', config)

    def test_bad_range_is_refused_before_a_scan(self) -> None:
        result = subprocess.run(
            ["bash", str(SCAN)],
            cwd=ROOT,
            env={**os.environ, "SCAN_BASE": "--all", "SCAN_HEAD": "HEAD"},
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing gitleaks range", result.stderr)
        self.assertNotIn("scanned", result.stderr.lower())

    def test_zero_push_ancestor_scans_the_tree_without_git_history(self) -> None:
        calls = ROOT / "tests" / ".gitleaks-calls"
        if calls.exists():
            calls.unlink()
        self.addCleanup(lambda: calls.unlink(missing_ok=True))
        fake = ROOT / "tests" / ".gitleaks-fake"
        self.addCleanup(lambda: fake.unlink(missing_ok=True))
        fake.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$*\" >> \"$CALLS\"\n"
            "if [ \"$1\" = version ]; then echo 8.30.1; fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        fake.chmod(0o755)
        result = subprocess.run(
            ["bash", str(SCAN)],
            cwd=ROOT,
            env={
                **os.environ,
                "GITLEAKS_BIN": str(fake),
                "CALLS": str(calls),
                "SCAN_BASE": "0000000000000000000000000000000000000000",
                "SCAN_HEAD": "0123456789abcdef0123456789abcdef01234567",
            },
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("push has no ancestor", result.stderr)
        recorded = calls.read_text(encoding="utf-8")
        self.assertIn("dir ", recorded)
        self.assertNotIn("git ", recorded)

    def test_current_tree_is_clean_and_a_planted_file_fails(self) -> None:
        clean = subprocess.run(
            ["bash", str(SCAN)],
            cwd=ROOT,
            env={**os.environ, "SCAN_BASE": "", "SCAN_HEAD": ""},
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        self.assertEqual(clean.returncode, 0, clean.stderr)
        self.assertIn("range skipped", clean.stderr)
        plant = ROOT / "gitleaks-plant-proof.txt"
        self.addCleanup(lambda: plant.unlink(missing_ok=True))
        token = "ghp_" + "1a2b3c4d5e6f7g8h" + "9i0j1k2l3m4n5o6p7q"
        plant.write_text(f'github_token = "{token}"\n', encoding="utf-8")
        planted = subprocess.run(
            ["bash", str(SCAN)],
            cwd=ROOT,
            env={**os.environ, "SCAN_BASE": "", "SCAN_HEAD": ""},
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        plant.unlink()
        self.assertNotEqual(planted.returncode, 0)
        self.assertNotIn(token, planted.stdout)
        self.assertNotIn(token, planted.stderr)
        self.assertIn("gitleaks-plant-proof.txt", planted.stderr + planted.stdout)


if __name__ == "__main__":
    unittest.main()
