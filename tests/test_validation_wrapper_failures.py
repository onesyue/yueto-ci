import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


class ValidationWrapperFailureTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.workspace = Path(temp.name)
        self.bin = self.workspace / "bin"
        self.bin.mkdir()
        self.runner_temp = self.workspace / "runner"
        self.runner_temp.mkdir()
        self.calls = self.workspace / "calls"
        self.env = {
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "GITHUB_WORKSPACE": str(self.workspace),
            "RUNNER_TEMP": str(self.runner_temp),
            "GITHUB_PATH": str(self.runner_temp / "path"),
            "GITHUB_RUN_ID": "1",
            "GITHUB_RUN_ATTEMPT": "1",
            "OPS_ROLE": "fixture",
            "YUE_CI_PYTHON": str(self.bin / "python"),
            "CALLS": str(self.calls),
        }

    def stub(self, name, script):
        path = self.workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/bash\nset -eu\n" + script + "\n", encoding="utf-8")
        path.chmod(0o755)

    def run_script(self, name):
        return subprocess.run(
            ["bash", str(SCRIPTS / name)],
            cwd=self.workspace,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def assert_exit(self, result, code):
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)

    def test_dependency_install_stops_before_export_if_venv_fails(self):
        self.stub("bin/uv", 'printf "%s\\n" "$*" >> "$CALLS"\nexit 24')
        self.assert_exit(self.run_script("ops-validation-dependencies.sh"), 24)
        self.assertEqual(
            self.calls.read_text().splitlines(),
            [f"venv --python {self.bin / 'python'} .venv"],
        )
        self.assertFalse(Path(self.env["GITHUB_PATH"]).exists())

    def test_frontend_and_miniapp_require_the_source_audit_gate(self):
        self.stub("bin/npm", 'printf "%s\\n" "$*" >> "$CALLS"')
        self.stub("bin/python", 'echo unexpected-audit >> "$CALLS"')
        for script, expected_calls in (
            ("ops-validation-frontend.sh", ["ci --ignore-scripts", "run lint", "run build"]),
            ("ops-validation-miniapp.sh", ["run lint", "run build"]),
        ):
            with self.subTest(script=script):
                self.calls.write_text("")
                result = self.run_script(script)
                self.assert_exit(result, 1)
                self.assertIn("source-owned npm audit gate is missing", result.stdout)
                self.assertEqual(self.calls.read_text().splitlines(), expected_calls)

    def test_node_toolchain_refuses_ambiguous_release_metadata(self):
        self.stub(
            ".ci-policy/scripts/ci-retry.sh",
            """ci_download() {
                printf '%s\\n' "${@: -3:1}" >> "$CALLS"
                [ "${@: -3:1}" = https://nodejs.org/dist/latest-v24.x/SHASUMS256.txt ]
                printf 'digest node-v24.1.2-linux-x64.tar.xz\\ndigest node-v24.1.3-linux-x64.tar.xz\\n' > "${@: -1}"
            }""",
        )
        result = self.run_script("ops-validation-node-toolchain.sh")
        self.assert_exit(result, 1)
        self.assertIn("must select exactly one Linux x64 archive", result.stderr)
        self.assertEqual(
            self.calls.read_text().splitlines(),
            ["https://nodejs.org/dist/latest-v24.x/SHASUMS256.txt"],
        )
        self.assertFalse(Path(self.env["GITHUB_PATH"]).exists())

    def test_node_refuses_missing_package_manager_pin(self):
        for tool in ("npm", "corepack", "node", "pnpm"):
            self.stub(f"bin/{tool}", f'printf "%s\\n" "{tool} $*" >> "$CALLS"')
        result = self.run_script("ops-validation-node.sh")
        self.assert_exit(result, 1)
        self.assertIn("site/package.json has no packageManager pin", result.stdout)
        calls = self.calls.read_text().splitlines()
        self.assertEqual(calls[:3], [
            "npm --prefix telegram-bot/yue/miniapp test",
            "npm --prefix frontend test",
            "corepack enable",
        ])
        self.assertEqual(len(calls), 4)
        self.assertTrue(calls[-1].startswith("node -p "))

    def test_notices_requires_board_once_source_adopts_contract(self):
        self.stub(".venv/bin/python", 'echo unexpected-pytest >> "$CALLS"')
        self.assert_exit(self.run_script("ops-validation-notices.sh"), 0)
        contract = self.workspace / "tests/test_yueboard_notices_contract_20261028.py"
        contract.parent.mkdir()
        contract.touch()
        result = self.run_script("ops-validation-notices.sh")
        self.assert_exit(result, 1)
        self.assertIn("pinned YueBoard checkout is missing", result.stderr)
        self.assertFalse(self.calls.exists())

    def test_native_obligations_stop_on_board_revision_mismatch(self):
        self.stub("bin/jq", "printf '%040d\\n' 1")
        self.stub("bin/git", 'printf "%s\\n" "$*" >> "$CALLS"\nprintf "%040d\\n" 2')
        self.stub(".venv/bin/python", 'echo unexpected-obligation >> "$CALLS"')
        self.assert_exit(self.run_script("ops-validation-obligations.sh"), 1)
        self.assertEqual(self.calls.read_text().splitlines(), ["-C .ci-yueboard rev-parse HEAD"])

    def test_selection_and_terminal_propagate_evidence_failure(self):
        self.stub(".venv/bin/python", 'printf "%s\\n" "$*" >> "$CALLS"\nexit 26')
        for script, command in (
            ("ops-validation-selection.sh", "run"),
            ("ops-validation-terminal.sh", "native-terminal"),
        ):
            with self.subTest(script=script):
                self.calls.write_text("")
                self.assert_exit(self.run_script(script), 26)
                args = self.calls.read_text().split()
                self.assertEqual(args[:3], [
                    ".ci-policy/scripts/pytest-shards.py",
                    command,
                    "--admission",
                ])
                self.assertEqual(
                    args[3], str(self.runner_temp / "ops-admission/ops-admission.json"),
                )

    def test_migrations_does_not_mask_selector_failure_as_empty(self):
        self.env["MIGRATION_BASE"] = "fixture-base"
        self.stub("bin/python3", 'printf "%s\\n" "$*" >> "$CALLS"\nexit 27')
        self.stub("bin/curl", 'echo unexpected-download >> "$CALLS"')
        self.assert_exit(self.run_script("ops-validation-migrations.sh"), 27)
        self.assertEqual(
            self.calls.read_text().splitlines(),
            [".ci-policy/scripts/changed-migrations.py --base fixture-base"],
        )

    def test_local_role_wrappers_reject_missing_role_before_copy(self):
        self.env.update({
            "CI_CHECK_SOURCE": str(self.workspace / "source"),
            "CI_CHECK_BOARD": str(self.workspace / "board"),
            "CI_CHECK_POLICY": str(self.workspace / "policy"),
            "CI_CHECK_JOB": str(self.workspace / "job"),
        })
        self.env.pop("OPS_ROLE")
        for script, role in (
            ("ci-check-container.sh", "OPS_ROLE"),
            ("ci-check-board-container.sh", "BOARD_ROLE"),
        ):
            with self.subTest(script=script):
                result = self.run_script(script)
                self.assert_exit(result, 1)
                self.assertIn(f"{role}:", result.stderr)
                self.assertFalse((self.workspace / "job").exists())

    def test_private_daemon_refuses_failed_start(self):
        ready = self.workspace / "daemon-started"
        os.mkfifo(ready)
        self.env["DAEMON_STARTED"] = str(ready)
        self.stub(
            "bin/sudo",
            'echo "fixture daemon start failed" >&2\necho ready > "$DAEMON_STARTED"\nexit 29',
        )
        self.stub(
            "bin/timeout",
            'if [ -p "$DAEMON_STARTED" ]; then read -r _ < "$DAEMON_STARTED"; rm "$DAEMON_STARTED"; fi\nexit 1',
        )
        self.stub("bin/sleep", "exit 0")
        script = SCRIPTS / "ci-check-private-daemon.sh"
        result = subprocess.run(
            ["bash", "-ec", 'source "$1"; ci_check_daemon_start', "--", str(script)],
            cwd=self.workspace,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assert_exit(result, 1)
        self.assertIn("fixture daemon start failed", result.stderr)

    def test_syft_digest_failure_cannot_extract_or_publish(self):
        sha256sum = shutil.which("gsha256sum") or shutil.which("sha256sum")
        self.assertIsNotNone(sha256sum, "GNU sha256sum is required by the installer fixture")
        (self.bin / "sha256sum").symlink_to(sha256sum)
        self.stub("bin/uname", 'case "$1" in -s) echo Linux ;; -m) echo x86_64 ;; *) exit 97 ;; esac')
        self.stub(
            "bin/curl",
            """while [ "$#" -gt 0 ]; do
                if [ "$1" = --output ]; then
                    echo downloaded >> "$CALLS"
                    echo 'corrupt fixture bytes' > "$2"
                    exit 0
                fi
                shift
            done
            exit 97""",
        )
        self.stub("bin/tar", 'echo unexpected-extraction >> "$CALLS"\nexit 97')
        result = self.run_script("install-verified-syft.sh")
        self.assert_exit(result, 1)
        self.assertIn("FAILED", result.stdout)
        self.assertEqual(self.calls.read_text().splitlines(), ["downloaded"])
        self.assertEqual(list(self.runner_temp.iterdir()), [])
