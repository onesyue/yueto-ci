"""Exercise the test/build timeout guard with actual Board and Docker steps."""
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts/check_step_timeouts.py"
BUILD = ROOT / ".github/workflows/build.yml"
BOARD_RACE = "Validate YueBoard race"
REFERENCE = "${{ fromJSON(env.BOARD_TEST_STEP_TIMEOUT_MINUTES) }}"


class StepTimeoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = yaml.safe_load(BUILD.read_text())

    def run_guard(self, steps, minutes="2"):
        workflow = {"env": {"BOARD_TEST_STEP_TIMEOUT_MINUTES": minutes},
                    "jobs": {"validate": {"steps": steps}}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "build.yml"
            path.write_text(yaml.safe_dump(workflow))
            return subprocess.run([sys.executable, str(CHECKER), str(path)],
                                  text=True, capture_output=True, timeout=10, check=False)

    def test_removed_board_budget_names_the_step(self):
        race = next(deepcopy(step) for step in self.workflow["jobs"]["validate"]["steps"]
                    if step.get("name") == BOARD_RACE)
        race["timeout-minutes"] = REFERENCE
        self.assertEqual(self.run_guard([race]).returncode, 0)
        del race["timeout-minutes"]
        rejected = self.run_guard([race])
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn(f"validate / {BOARD_RACE}: timeout-minutes", rejected.stderr)

    def test_direct_tests_builds_and_actions_require_a_named_budget(self):
        cases = [
            {"run": "go test -race ./..."}, {"run": "python -m pytest"},
            {"run": "pnpm run build"}, {"run": "docker buildx build ."},
            next(step for step in self.workflow["jobs"]["build"]["steps"] if step.get("id") == "build"),
        ]
        for step in cases:
            with self.subTest(step=step.get("uses") or step.get("run")):
                self.assertNotEqual(self.run_guard([step | {"timeout-minutes": 2}]).returncode, 0)
                self.assertEqual(self.run_guard([step | {"timeout-minutes": REFERENCE}]).returncode, 0)

    def test_undefined_or_nonpositive_budget_is_rejected(self):
        step = {"run": "go build ./...", "timeout-minutes": REFERENCE}
        for value in (None, "0", "1.5"):
            with self.subTest(value=value):
                self.assertNotEqual(self.run_guard([step], minutes=value).returncode, 0)

    def test_shell_file_checks_and_comments_are_not_test_executors(self):
        skipped = {"run": "# go test ./...\ntest -f receipt.json\npython scripts/pytest-timing.py summary"}
        result = self.run_guard([skipped])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no test or build steps found", result.stderr)
        self.assertEqual(self.run_guard([skipped, {"run": "npm test", "timeout-minutes": REFERENCE}]).returncode, 0)


if __name__ == "__main__":
    unittest.main()
