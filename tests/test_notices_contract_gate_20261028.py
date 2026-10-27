"""Decoupling S2: the YueBoard→YueOps notices wire contract runs inside validate."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"
STEP = "- name: Validate YueBoard→YueOps notices wire contract"


class NoticesContractGateTest(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")
        start = self.text.index(STEP)
        end = self.text.index("\n      - name:", start + len(STEP))
        self.step = self.text[start:end]

    def test_step_runs_once_in_native_ops_validation_with_both_repos(self):
        self.assertEqual(self.text.count(STEP), 1)
        self.assertIn("if: matrix.validation == 'yueops' && matrix.ops_role == 'native'", self.step)
        self.assertIn("YUEBOARD_REPO_PATH: ${{ github.workspace }}/.ci-yueboard", self.step)
        self.assertIn('YUEOPS_REQUIRE_PRODUCER_CONTRACT: "1"', self.step)
        self.assertIn('test -d "$YUEBOARD_REPO_PATH/.git"', self.step)
        self.assertIn("set -euo pipefail", self.step)

    def test_step_follows_pinned_board_checkout_and_dependency_install(self):
        at = self.text.index(STEP)
        self.assertLess(self.text.index("Checkout pinned YueBoard canonical contract"), at)
        self.assertLess(self.text.index("- name: Install yueops dependencies"), at)
        self.assertLess(at, self.text.index("- name: Execute owned Ops pytest selection"))

    def test_step_has_no_bypass_switches(self):
        for forbidden in ("continue-on-error", "|| true", "YUEOPS_REQUIRE_PRODUCER_CONTRACT: \"0\""):
            self.assertNotIn(forbidden, self.step)


if __name__ == "__main__":
    unittest.main()
