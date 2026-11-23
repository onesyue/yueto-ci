import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


class PolicyHelperFailureTests(unittest.TestCase):
    def run_command(self, *command, **kwargs):
        return subprocess.run(command, capture_output=True, text=True, timeout=45, **kwargs)

    def test_integration_discovery_reports_go_list_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            env = dict(os.environ, GOTOOLCHAIN="local", GOPROXY="off", GOWORK="off", GOFLAGS="")
            helper = source / "list-integration-tests"
            build = self.run_command(
                "go", "build", "-o", str(helper), str(SCRIPTS / "list-integration-tests.go"),
                cwd=source, env=env,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            (source / "go.mod").write_text("module example.invalid/fixture\ninvalid-directive\n")
            result = self.run_command(str(helper), cwd=source, env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown directive: invalid-directive", result.stderr)
        self.assertIn("go package discovery", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_static_ui_cli_rejects_unregistered_units(self):
        result = self.run_command(
            sys.executable, str(SCRIPTS / "ui_static_units.py"), "dockerfile", "fixture-unregistered",
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("is not a registered static UI unit", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_failure_summary_cli_returns_nonzero_and_deduplicates(self):
        node = "tests/test_fixture.py::test_case[with spaces]"
        result = self.run_command(
            sys.executable, str(SCRIPTS / "ci_check_failures.py"),
            input=f"FAILED {node} - fixture error\nERROR {node} - fixture error\n",
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [node])

    def test_brand_module_refuses_disagreeing_host_on_import(self):
        text = (SCRIPTS / "brand_literals.py").read_text()
        drifted, replacements = re.subn(
            r'^PANEL_HOST = "[^"]+"', 'PANEL_HOST = "mismatch.example.invalid"', text, flags=re.M,
        )
        self.assertEqual(replacements, 1)
        with self.assertRaisesRegex(ValueError, "brand URL and host disagree"):
            exec(compile(drifted, "brand_literals.py", "exec"), {})

    def test_scanner_authority_does_not_mark_malformed_version_ready(self):
        text = (SCRIPTS / "scanner-tool-versions.sh").read_text()
        drifted, replacements = re.subn(
            r"^readonly UV_VERSION='[^']+'", "readonly UV_VERSION='malformed'", text, flags=re.M,
        )
        self.assertEqual(replacements, 1)
        with tempfile.TemporaryDirectory() as directory:
            authority = Path(directory) / "scanner-tool-versions.sh"
            authority.write_text(drifted)
            result = self.run_command(
                "bash", "-c",
                'unset SCANNER_TOOL_VERSIONS_READY; source "$1"; rc=$?; '
                'test -z "${SCANNER_TOOL_VERSIONS_READY:-}" || exit 99; exit "$rc"',
                "--", str(authority),
            )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("invalid uv version authority", result.stderr)
