import contextlib
import importlib.util
import io
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
        self.git("init", "-q")
        (self.source / "pytest.ini").write_text("[pytest]\n")
        (self.source / "pyproject.toml").write_text("# dependencies\n")
        self.base = self.commit()
        # Small historical fixture; discovery, Git trees and the entire production
        # admission chain remain real. No production policy/seal is changed.
        self.baseline = {"common_inputs": PRE.POLICY.shared_inputs(self.source, self.base)}
        patched = patch.object(PRE.POLICY, "skip_baseline", return_value=self.baseline)
        patched.start()
        self.addCleanup(patched.stop)

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.source), *args], stderr=subprocess.PIPE).decode().strip()

    def commit(self):
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture")
        return self.git("rev-parse", "HEAD")

    def test_unchanged_tree_accepted_and_worktree_ignored(self):
        (self.source / "pyproject.toml").write_text("uncommitted change")
        self.assertTrue(PRE.precheck(self.source, self.base, self.base)[0])

    def test_dependency_helper_and_deletion_rejected(self):
        for path in ("pyproject.toml", "uv.lock", "tests/_shared.py"):
            with self.subTest(path=path):
                target = self.source / path
                target.parent.mkdir(exist_ok=True)
                target.write_text("changed\n")
                head = self.commit()
                accepted, reason = PRE.precheck(self.source, self.base, head)
                self.assertFalse(accepted)
                self.assertIn(path, reason)
                self.assertIn("reviewed seal in reviews/", reason)
        (self.source / "pytest.ini").unlink()
        self.assertFalse(PRE.precheck(self.source, self.base, self.commit())[0])

    def test_ordinary_source_change_accepted(self):
        (self.source / "app.py").write_text("raise RuntimeError('must never execute')\n")
        self.assertTrue(PRE.precheck(self.source, self.base, self.commit())[0])

    def test_invalid_sha_and_missing_object_are_input_errors(self):
        for revision in ("HEAD", "f" * 40):
            with patch("sys.argv", ["precheck", "--repo", "yueops", "--source", str(self.source),
                                    "--base", self.base, "--head", revision]):
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(PRE.main(), 2)

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
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true", "GITHUB_STEP_SUMMARY": str(summary)}):
            with contextlib.redirect_stderr(io.StringIO()) as output:
                admission_diagnostics.rejection("pyproject.toml changed\n::notice::100%")
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
