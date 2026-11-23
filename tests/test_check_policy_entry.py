"""Exercise the workflow entry against the policy job before extraction."""

import importlib.util
import os
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ENTRY = Path("scripts/check-policy.sh")
WORKFLOW = Path(".github/workflows/policy-ci.yml")

# Validate central policy, from git show a403860d806569d7f491cf6664152b606f00c49e:
# .github/workflows/policy-ci.yml. Keep the oracle available in shallow checkouts.
BASE_BODY = """
set -euo pipefail
python3 scripts/run-policy-tests.py
python3 -m compileall -q scripts tests
for script in scripts/*.sh; do
  bash -n "$script"
done
command -v shellcheck
shellcheck --severity=warning scripts/*.sh
actionlint .github/workflows/*.yml
"""


class PolicyEntryTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for path in (ENTRY, Path("scripts/lint-tool-versions.sh"), WORKFLOW):
            (self.root / path.parent).mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / path, self.root / path)
        (self.root / ".github/workflows/second.yml").touch()
        self.trace = self.root / "trace"
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        self.env = {**os.environ, "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
                    "TRACE": str(self.trace)}
        for tool in ("python3", "bash", "actionlint", "shellcheck", "go"):
            stub = bin_dir / tool
            # Only record validation. Let bash execute the actual shared entry.
            stub.write_text(
                '#!/bin/sh\n'
                'case "${0##*/}:$*" in\n'
                f'  bash:-n*) ;; bash:*) exec {shlex.quote(shutil.which("bash"))} "$@" ;;\n'
                '  actionlint:-version) echo "v$TEST_ACTIONLINT_VERSION"; exit 0 ;;\n'
                '  python3:*--check-tools) exit 0 ;;\n'
                'esac\n'
                'printf "%s" "${0##*/}" >> "$TRACE"\n'
                'printf "|%s" "$@" >> "$TRACE"\n'
                'printf "\\n" >> "$TRACE"\n'
            )
            stub.chmod(0o755)
        version = subprocess.check_output(
            ["bash", "-c", "source scripts/lint-tool-versions.sh && echo \"$ACTIONLINT_VERSION\""],
            cwd=ROOT, text=True,
        )
        self.env["TEST_ACTIONLINT_VERSION"] = version.strip()
        steps = yaml.safe_load((ROOT / WORKFLOW).read_text())["jobs"]["policy"]["steps"]
        self.command = next(step["run"] for step in steps if step.get("name") == "Validate central policy")

    def commands(self, body):
        self.trace.write_text("")
        subprocess.run(["bash", "-c", body], cwd=self.root, env=self.env,
                       check=True, capture_output=True, text=True)
        return self.trace.read_text().splitlines()

    def test_ci_commands_match_base_policy_job(self):
        self.assertEqual(self.command, "scripts/check-policy.sh ci")
        self.assertEqual(self.commands(BASE_BODY), self.commands(self.command))

    def test_missing_workflow_lint_changes_command_trace(self):
        path = self.root / ENTRY
        path.write_text(path.read_text().replace("actionlint .github/workflows/*.yml", ":"))
        expected = self.commands(BASE_BODY)
        self.assertEqual(self.commands(self.command), expected[:-1])
        self.assertTrue(expected[-1].startswith("actionlint|"))

    def test_wrong_actionlint_pin_fails_before_validation(self):
        self.env["TEST_ACTIONLINT_VERSION"] = "0.0.0"
        result = subprocess.run(["bash", "-c", self.command], cwd=self.root, env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("requires actionlint", result.stderr)
        self.assertFalse(self.trace.exists())

    def test_quick_selects_committed_staged_and_untracked_changes(self):
        spec = importlib.util.spec_from_file_location("runner", ROOT / "scripts/run-policy-tests.py")
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        tests = self.root / "tests"
        tests.mkdir()
        (tests / "test_tool.py").write_text('# Uses example.sh')
        (tests / "test_unrelated.py").touch()
        def git(*args):
            subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)
        git("init", "-q")
        git("add", ".")
        def commit():
            git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                "-c", "commit.gpgsign=false", "commit", "-qm", "fixture")
        commit()
        git("update-ref", "refs/remotes/origin/master", "HEAD")
        (self.root / "scripts/example.sh").touch()
        git("add", "scripts/example.sh")
        commit()
        (tests / "test_staged.py").touch()
        git("add", "tests/test_staged.py")
        (tests / "test_new.py").touch()
        self.assertEqual(runner.changed_modules(self.root),
                         ["test_check_policy_entry", "test_new", "test_staged", "test_tool"])
