"""Exercise failures at the entrypoints called by the hosted workflows."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


class WorkflowScriptFailures(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.source = Path(scratch.name).resolve()
        self.bin = self.source / "bin"
        self.bin.mkdir()
        self.runner = self.source / "runner"
        self.runner.mkdir()
        self.log = self.source / "calls"
        (self.source / ".ci-policy").symlink_to(ROOT, target_is_directory=True)
        self.env = {
            "PATH": str(self.bin) + os.pathsep + os.defpath,
            "GITHUB_WORKSPACE": str(self.source),
            "GITHUB_PATH": str(self.runner / "path"),
            "RUNNER_TEMP": str(self.runner),
            "GITHUB_RUN_ID": "1",
            "GITHUB_RUN_ATTEMPT": "1",
            "OPS_ROLE": "legacy",
            "YUE_CI_PYTHON": sys.executable,
            "CALLS": str(self.log),
        }

    def executable(self, path, body):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\nset -eu\n" + body, encoding="utf-8")
        path.chmod(0o755)

    def run_script(self, name):
        return self.run_command("/bin/bash", str(ROOT / "scripts" / name))

    def run_command(self, *command):
        return subprocess.run(command, cwd=self.source, env=self.env,
                              capture_output=True, text=True, timeout=20)

    def test_failed_dependency_setup_stops_all_followup_tools(self):
        self.executable(self.bin / "uv", 'printf "%s\n" "$1" >> "$CALLS"\nexit 37\n')
        self.executable(self.bin / "npm", 'echo unexpected-npm >> "$CALLS"\n')
        result = self.run_script("ops-validation-dependencies.sh")
        self.assertEqual(result.returncode, 37, result.stderr)
        self.assertEqual(self.log.read_text().splitlines(), ["venv"])
        self.assertFalse(Path(self.env["GITHUB_PATH"]).exists())

    def test_backend_lock_failure_stops_before_source_checks_and_cleans_scratch(self):
        self.executable(self.bin / "uv", 'echo "$*" >> "$CALLS"\nexit 37\n')
        self.executable(self.source / ".venv/bin/python", 'echo unexpected-python >> "$CALLS"\n')
        result = self.run_script("ops-validation-backend.sh")
        self.assertEqual(result.returncode, 37, result.stderr)
        self.assertEqual(self.log.read_text().splitlines(), ["lock --check"])
        self.assertEqual(list(self.runner.iterdir()), [])

    def test_miniapp_lint_failure_prevents_build(self):
        self.executable(self.bin / "npm", 'echo "$*" >> "$CALLS"\nexit 37\n')
        result = self.run_script("ops-validation-miniapp.sh")
        self.assertEqual(result.returncode, 37, result.stderr)
        self.assertEqual(self.log.read_text().splitlines(), ["run lint"])

    def test_node_without_package_manager_pin_cannot_install_or_run_site(self):
        for program in ("npm", "corepack", "pnpm"):
            self.executable(self.bin / program, f'echo "{program} $*" >> "$CALLS"\n')
        self.executable(self.bin / "node", 'echo package-manager-query >> "$CALLS"\n')
        result = self.run_script("ops-validation-node.sh")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("has no packageManager pin", result.stdout)
        self.assertEqual(self.log.read_text().splitlines(), [
            "npm --prefix telegram-bot/yue/miniapp test",
            "npm --prefix frontend test", "corepack enable", "package-manager-query",
        ])

    def test_notices_contract_requires_board_checkout_when_adopted(self):
        contract = self.source / "tests/test_yueboard_notices_contract_20261028.py"
        contract.parent.mkdir()
        contract.touch()
        self.executable(self.source / ".venv/bin/python", 'echo "$*" >> "$CALLS"\n')
        result = self.run_script("ops-validation-notices.sh")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("pinned YueBoard checkout is missing", result.stderr)
        self.assertFalse(self.log.exists())

    def test_migration_selection_failure_stops_before_download(self):
        self.env["MIGRATION_BASE"] = "fixture-base"
        self.executable(self.bin / "python3", 'echo "$*" >> "$CALLS"\nexit 37\n')
        self.executable(self.bin / "curl", 'echo unexpected-download >> "$CALLS"\n')
        result = self.run_script("ops-validation-migrations.sh")
        self.assertEqual(result.returncode, 37, result.stderr)
        self.assertEqual(self.log.read_text().splitlines(), [
            ".ci-policy/scripts/changed-migrations.py --base fixture-base",
        ])

    def test_missing_admission_is_rejected_by_selection_and_terminal(self):
        python = self.source / ".venv/bin/python"
        python.parent.mkdir(parents=True)
        python.symlink_to(sys.executable)
        for phase in ("selection", "terminal"):
            with self.subTest(phase=phase):
                result = self.run_script(f"ops-validation-{phase}.sh")
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn('"status": "REJECTED"', result.stderr)
                self.assertIn('"release_acceptance": false', result.stderr)
                self.assertIn("ops-admission.json", result.stderr)
                self.assertEqual(result.stdout, "")

    def test_native_obligation_refuses_a_different_board_revision(self):
        self.executable(self.bin / "jq", "echo " + "a" * 40 + "\n")
        self.executable(self.bin / "git", 'echo "$*" >> "$CALLS"\necho ' + "b" * 40 + "\n")
        self.executable(self.source / ".venv/bin/python", 'echo unexpected-python >> "$CALLS"\n')
        result = self.run_script("ops-validation-obligations.sh")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(self.log.read_text().splitlines(), ["-C .ci-yueboard rev-parse HEAD"])
        self.assertFalse((self.runner / "ops-shard-evidence").exists())

    def test_invalid_node_release_metadata_never_downloads_an_archive(self):
        self.executable(self.bin / "curl", """
printf 'download\n' >> "$CALLS"
while [ "$1" != --output ]; do shift; done
printf 'fixture another-platform.tar.xz\n' > "$2"
""")
        result = self.run_script("ops-validation-node-toolchain.sh")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("must select exactly one Linux x64 archive", result.stderr)
        self.assertEqual(self.log.read_text().splitlines(), ["download"])
        self.assertFalse(Path(self.env["GITHUB_PATH"]).exists())

    def test_unknown_static_ui_validation_is_rejected(self):
        result = self.run_command(sys.executable, str(ROOT / "scripts/ui_static_units.py"),
                                  "validate", "--validation", "fixture-ui")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("fixture-ui is not a static UI validation", result.stderr)

    def test_toolchain_invalid_pin_or_image_digest_cannot_publish(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/ci-toolchain.yml").read_text())
        steps = {step["name"]: step for job in workflow["jobs"].values()
                 for step in job["steps"] if "name" in step}
        pin = self.source / "images/yueops-ci-toolchain/uv.sha256"
        pin.parent.mkdir(parents=True)
        pin.write_text("fixture-invalid-digest\n")
        output = self.runner / "output"
        self.env.update(GITHUB_OUTPUT=str(output), DIGEST="sha256:1234")
        read_pin = self.run_command("/bin/bash", "-c", steps["Read the uv pin"]["run"])
        self.assertEqual(read_pin.returncode, 1, read_pin.stderr)
        self.assertIn("uv.sha256 must be 64 hex digits", read_pin.stdout)
        self.assertFalse(output.exists())
        print_digest = self.run_command("/bin/bash", "-c", steps["Print the image digest"]["run"])
        self.assertEqual(print_digest.returncode, 1, print_digest.stderr)
        self.assertNotIn("toolchain image ghcr.io", print_digest.stdout)


if __name__ == "__main__":
    unittest.main()
