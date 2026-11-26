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
    expires: 2099-01-01
    commit: 0123456789abcdef0123456789abcdef01234567
    failed: https://github.com/onesyue/yueto-ci/actions/runs/1
    passed: https://github.com/onesyue/yueto-ci/actions/runs/2
"""

REAL_FAILURES = (
    "tests/test_ops_unit_manifest.py::test_check_matches_committed_json",
    "tests/test_alert_chain_deadman_dispatch_20261125.py::test_shell_syntax_and_shellcheck",
    "tests/test_panel_deploy_bundle.py::test_manifest_and_projection",
    "tests/test_panel_deploy_bundle.py::test_missing_library_fails_standalone_self_test",
    "tests/test_panel_deploy_bundle.py::test_reproducible",
    "tests/test_panel_deploy_bundle.py::test_self_test",
    "tests/test_panel_deploy_bundle.py::test_sidecar_digest_mismatch",
    "tests/test_relay_coordinator_management_dial_20261112.py::test_check_dials_inventory_literal_and_plans_the_stale_public_record",
    "tests/test_relay_coordinator_management_dial_20261112.py::test_hostname_management_field_is_not_a_dial_target",
    "tests/test_relay_coordinator_management_dial_20261112.py::test_unreadable_management_inventory_is_named",
)


class PolicyQuarantineTest(unittest.TestCase):
    def test_committed_policy_has_no_real_failures(self):
        text = QUARANTINE.POLICY_FILE.read_text(encoding="utf-8")
        for nodeid in REAL_FAILURES:
            self.assertNotIn(nodeid, text)
        cases = QUARANTINE.policy_cases(QUARANTINE.POLICY_FILE, today=date(2026, 11, 26))
        self.assertEqual(list(cases), [])
        for reason in cases.values():
            self.assertIn("proven flake", reason)

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

    def test_real_failure_without_a_passing_rerun_is_rejected(self):
        missing = DOCUMENT.replace(
            "    passed: https://github.com/onesyue/yueto-ci/actions/runs/2\n",
            "",
        )
        with self.assertRaisesRegex(ValueError, "invalid quarantine"):
            QUARANTINE.parse_quarantine_yaml(missing)
        same_run = DOCUMENT.replace("actions/runs/2", "actions/runs/1")
        with self.assertRaisesRegex(ValueError, "flake evidence"):
            QUARANTINE.parse_quarantine_yaml(same_run)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quarantine.yaml"
            path.write_text(DOCUMENT, encoding="utf-8")
            cases = QUARANTINE.policy_cases(path, today=date(2026, 11, 26))
        self.assertEqual(
            list(cases),
            ["tests/test_quarantine_case.py::test_bad"],
        )
        self.assertIn("proven flake", next(iter(cases.values())))

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
