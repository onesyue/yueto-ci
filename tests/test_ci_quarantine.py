"""Policy quarantine expires closed and does not fail a shard by itself."""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ops_quarantine", ROOT / "scripts/ops_quarantine.py")
QUARANTINE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(QUARANTINE)

DOCUMENT = """schema: 1
entries:
  - id: tests/test_quarantine_case.py::test_bad
    owner: yueops
    issue: https://github.com/onesyue/yueto-ci/actions/runs/45673449414
    expires: 2099-01-01
"""


class PolicyQuarantineTest(unittest.TestCase):
    def test_committed_entries_are_active(self):
        cases = QUARANTINE.policy_cases(QUARANTINE.POLICY_FILE, today=date(2026, 11, 26))
        self.assertGreaterEqual(len(cases), 1)
        for nodeid in cases:
            self.assertTrue(nodeid.startswith("tests/"))
            self.assertIn("::", nodeid)

    def test_expired_entry_fails_the_policy_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quarantine.yaml"
            path.write_text(DOCUMENT.replace("2099-01-01", "2026-11-26"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "expired quarantine entry"):
                QUARANTINE.policy_cases(path, today=date(2026, 11, 26))

    def test_closed_empty_document_and_trailing_junk_are_rejected(self):
        self.assertEqual(QUARANTINE.parse_quarantine_yaml("schema: 1\nentries: []\n"), [])
        with self.assertRaises(ValueError):
            QUARANTINE.parse_quarantine_yaml("schema: 1\nentries: []\n  - id: tests/a.py::test_b\n")

    def test_quarantined_failure_runs_and_does_not_fail_the_shard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tests = root / "tests"
            tests.mkdir()
            (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
            module = "tests/test_quarantine_case.py"
            (root / module).write_text(
                "def test_bad():\n    assert False\ndef test_other():\n    assert False\n",
                encoding="utf-8",
            )
            policy = root / "quarantine.yaml"
            policy.write_text(DOCUMENT, encoding="utf-8")
            nodeid = module + "::test_bad"
            env = dict(
                os.environ,
                PYTHONPATH=str(ROOT / "scripts"),
                PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
                YUETO_OPS_TEST_SOURCE=tmp,
                YUETO_CI_QUARANTINE=str(policy),
                YUETO_OWNED_FAILURES=tmp,
                YUETO_SHARED_SELECTION="[]",
            )

            def run(case):
                return subprocess.run(
                    [sys.executable, "-m", "pytest", "-p", "ops_quarantine", "-q", case],
                    cwd=root, env=env, capture_output=True, text=True, check=False,
                )

            quarantined = run(nodeid)
            self.assertEqual(quarantined.returncode, 0, quarantined.stderr)
            self.assertIn("1 xfailed", quarantined.stdout)
            self.assertEqual(run(module + "::test_other").returncode, 1)
            policy.write_text(DOCUMENT.replace("2099-01-01", "2020-01-01"), encoding="utf-8")
            expired = run(nodeid)
            self.assertNotEqual(expired.returncode, 0)
            self.assertIn("expired quarantine entry", expired.stderr)

    def test_shard_runner_points_pytest_at_the_policy_file(self):
        source = json.dumps((ROOT / "scripts/pytest_shards/cli.py").read_text(encoding="utf-8"))
        self.assertIn("YUETO_CI_QUARANTINE", source)
        owned = (ROOT / "scripts/ops-service-owned.sh").read_text(encoding="utf-8")
        backend = (ROOT / "scripts/ops-validation-backend.sh").read_text(encoding="utf-8")
        self.assertIn('YUETO_CI_QUARANTINE="$policy_quarantine"', owned)
        self.assertIn('YUETO_CI_QUARANTINE="$policy_quarantine"', backend)
