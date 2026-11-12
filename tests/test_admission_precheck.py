import contextlib
import importlib.util
import inspect
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import admission_diagnostics
spec = importlib.util.spec_from_file_location("precheck", ROOT / "scripts/admission-precheck.py")
PRE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(PRE)


class AdmissionPrecheck(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.source = Path(temporary.name)
        self.git("init", "-q", "-b", "master")
        (self.source / "pytest.ini").write_text("[pytest]\n")
        (self.source / "pyproject.toml").write_text("# dependencies\n")
        self.base = self.commit()
        # Small historical fixture; discovery, Git trees and the entire production
        # admission chain remain real. No production policy/seal is changed.
        self.baseline = {"common_inputs": PRE.POLICY.shared_inputs(self.source, self.base)}
        real_skip_baseline = PRE.POLICY.skip_baseline

        def skip_baseline():
            # The fixture baseline only satisfies shared-input admission.
            # The skip binder must keep the production catalog, or this
            # precheck would not see the cases join rejects.
            if any(frame.function == "prepare_skip_bindings" for frame in inspect.stack()):
                return real_skip_baseline()
            return self.baseline

        patched = patch.object(PRE.POLICY, "skip_baseline", skip_baseline)
        patched.start()
        self.addCleanup(patched.stop)

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.source), *args], stderr=subprocess.PIPE).decode().strip()

    def commit(self):
        self.git("add", ".")
        self.git("-c", "commit.gpgsign=false", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture", "--no-gpg-sign")
        return self.git("rev-parse", "HEAD")

    def test_unsigned_commit_on_master_is_rejected(self):
        (self.source / "tests").mkdir()
        (self.source / "tests" / "_helper.py").write_text("HELPER = 1\n")
        (self.source / "conftest.py").write_text("def pytest_configure(config):\n    return None\n")
        (self.source / "app.py").write_text("raise RuntimeError('must never execute')\n")
        head = self.commit()
        accepted, reason = PRE.precheck(self.source, self.base, head)
        self.assertFalse(accepted)
        self.assertIn("unauthorized source signature", reason)

    def test_worktree_dirt_is_ignored(self):
        (self.source / "pyproject.toml").write_text("uncommitted change")
        accepted, reason = PRE.precheck(self.source, self.base, self.base)
        self.assertFalse(accepted)
        self.assertIn("unauthorized source signature", reason)

    def test_changed_catalog_skip_uses_the_shard_precheck(self):
        # Run 43210004432 rejected this nodeid after admission-precheck had
        # accepted the range. The module blob moved and the case still skips.
        module = self.source / "tests" / "test_runtime_release_holds_20261009.py"
        module.parent.mkdir()
        module.write_text(
            "import pytest\n\n"
            "def test_native_dns_apply_noop_rollback_hold_lock_and_unknown_state():\n"
            "    pytest.skip('changed fixture skip')\n"
        )
        head = self.commit()
        lines = PRE.POLICY.skip_blob_precheck(self.source, head)
        self.assertTrue(lines)
        self.assertTrue(all(
            "test_native_dns_apply_noop_rollback_hold_lock_and_unknown_state" in line
            for line in lines))
        accepted, reason = PRE.precheck(self.source, self.base, head)
        self.assertFalse(accepted)
        for line in lines:
            self.assertIn(line, reason)

    def test_skip_rejection_is_the_shard_function_result(self):
        sentinel = (
            "tests/test_runtime_release_holds_20261009.py  old -> new  "
            "(tests/test_runtime_release_holds_20261009.py::"
            "test_native_dns_apply_noop_rollback_hold_lock_and_unknown_state)"
        )
        with patch.object(PRE.POLICY, "skip_blob_precheck", return_value=[sentinel]) as called:
            accepted, reason = PRE.precheck(self.source, self.base, self.base)
        called.assert_called_once_with(self.source, self.base)
        self.assertFalse(accepted)
        self.assertIn(sentinel, reason)

    def test_invalid_sha_and_missing_object_are_input_errors(self):
        for revision in ("HEAD", "f" * 40):
            with patch("sys.argv", ["precheck", "--repo", "yueops", "--source", str(self.source),
                                    "--base", self.base, "--head", revision]):
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(PRE.main(), 2)

    def test_missing_default_branch_is_a_rejection_not_a_seal_error(self):
        self.git("update-ref", "-d", "refs/heads/master")
        with patch("sys.argv", ["precheck", "--repo", "yueops", "--source", str(self.source),
                                "--base", self.base, "--head", self.base]):
            with contextlib.redirect_stderr(io.StringIO()) as output:
                self.assertEqual(PRE.main(), 1)
            self.assertIn("ADMISSION_REJECTED:", output.getvalue())
            self.assertIn("default branch ref is missing", output.getvalue())

    def test_available_nonancestor_remains_policy_rejection(self):
        self.git("checkout", "--orphan", "unrelated")
        (self.source / "pyproject.toml").write_text("unrelated history")
        unrelated = self.commit()
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            PRE.POLICY.git(self.source, "merge-base", "--is-ancestor", self.base, unrelated)
        self.assertEqual(caught.exception.returncode, 1)
        with patch.object(PRE.POLICY, "reviewed_estate_input_transition",
                          return_value=(self.baseline, {"source_after": self.base})):
            with patch("sys.argv", ["precheck", "--repo", "yueops", "--source", str(self.source),
                                    "--base", self.base, "--head", unrelated]):
                with contextlib.redirect_stderr(io.StringIO()) as output:
                    self.assertEqual(PRE.main(), 1)
                self.assertIn("ADMISSION_REJECTED:", output.getvalue())

    def test_cli_rejection_exit_and_marker(self):
        (self.source / "pyproject.toml").write_text("unsealed")
        head = self.commit()
        with patch("sys.argv", ["precheck", "--repo", "yueops", "--source", str(self.source),
                                "--base", self.base, "--head", head]), patch.dict(os.environ, {}, clear=True):
            with contextlib.redirect_stderr(io.StringIO()) as output:
                self.assertEqual(PRE.main(), 1)
            self.assertTrue(output.getvalue().startswith("ADMISSION_REJECTED:"))

    def test_annotation_summary_single_line_and_escape(self):
        summary = self.source / "summary"
        step_output = self.source / "output"
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true", "GITHUB_STEP_SUMMARY": str(summary),
                                     "GITHUB_OUTPUT": str(step_output)}):
            with contextlib.redirect_stderr(io.StringIO()) as output:
                admission_diagnostics.rejection("pyproject.toml changed\n::notice::100%")
        self.assertEqual(step_output.read_text(), "admission_rejected=true\n")
        self.assertEqual(len(output.getvalue().splitlines()), 1)
        self.assertIn("::error::ADMISSION_REJECTED:", output.getvalue())
        self.assertIn("100%25", output.getvalue())
        self.assertTrue(summary.read_text().startswith("ADMISSION_REJECTED:"))

    def test_real_expand_failure_emits_marker_and_summary(self):
        summary = self.source / "summary"
        targets = self.source / "targets.json"
        targets.write_text('{}')
        env = dict(os.environ, GITHUB_ACTIONS="true", GITHUB_STEP_SUMMARY=str(summary))
        result = subprocess.run([sys.executable, str(ROOT / "scripts/pytest-shards.py"), "expand",
                                 "--targets", str(targets), "--board", "a" * 40,
                                 "--runner", "ubuntu-24.04", "--capacity", "2", "--shards", "2"],
                                env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("::error::ADMISSION_REJECTED:", result.stderr)
        self.assertIn("ADMISSION_REJECTED:", summary.read_text())
        self.assertIn("scripts/pytest-shards.py expand", (ROOT / ".github/workflows/build.yml").read_text())
