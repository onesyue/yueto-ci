"""validation_only admits an owner signature and leaves the seal path closed."""

from workflow_source import workflow_text
import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "ci_check_shards", ROOT / "scripts/pytest-shards.py")
assert SPEC is not None and SPEC.loader is not None
SHARDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARDS)
FAIL_SPEC = importlib.util.spec_from_file_location(
    "ci_check_failures", ROOT / "scripts/ci_check_failures.py")
assert FAIL_SPEC is not None and FAIL_SPEC.loader is not None
FAILURES = importlib.util.module_from_spec(FAIL_SPEC)
FAIL_SPEC.loader.exec_module(FAILURES)


def _git(repo, *args):
    env = os.environ.copy()
    env.update({
        "GIT_AUTHOR_NAME": "Unsigned",
        "GIT_AUTHOR_EMAIL": "unsigned@example.invalid",
        "GIT_COMMITTER_NAME": "Unsigned",
        "GIT_COMMITTER_EMAIL": "unsigned@example.invalid",
    })
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True, env=env).strip()


def _unsigned_repo():
    directory = tempfile.TemporaryDirectory()
    repo = Path(directory.name)
    _git(repo, "init", "-q", "-b", "master")
    (repo / "README").write_text("unsigned\n", encoding="utf-8")
    _git(repo, "add", "--", "README")
    _git(repo, "-c", "commit.gpgsign=false", "commit", "-qm", "fixture", "--no-gpg-sign")
    return directory, repo, _git(repo, "rev-parse", "HEAD")


def _targets(sha):
    return {
        "matrix": [],
        "validation_matrix": [{
            "validation": "yueops",
            "repo": "onesyue/yueops",
            "ref": sha,
        }],
        "has_builds": False,
    }


class ValidationOnlyAdmission(unittest.TestCase):
    def setUp(self):
        head = _git(ROOT, "rev-parse", "HEAD")
        self.env = patch.dict(os.environ, {
            "GITHUB_SHA": head,
            "GITHUB_RUN_ID": "1",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_REPOSITORY": "onesyue/yueto-ci",
            "RUNNER_OS": "Linux",
            "RUNNER_ARCH": "X64",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_unsigned_commit_is_rejected_before_planning(self):
        directory, repo, sha = _unsigned_repo()
        self.addCleanup(directory.cleanup)
        with self.assertRaisesRegex(
                SHARDS.source_evidence.Rejected,
                "exactly one OpenPGP signature required"):
            SHARDS.expand(
                _targets(sha), repo, "b" * 40, "ubuntu-24.04", 20, 16,
                validation_only=True)

    def test_promote_path_does_not_use_the_signature_message(self):
        directory, repo, sha = _unsigned_repo()
        self.addCleanup(directory.cleanup)
        with self.assertRaises(Exception) as caught:
            SHARDS.expand(
                _targets(sha), repo, "b" * 40, "ubuntu-24.04", 20, 16,
                validation_only=False)
        self.assertNotIn(
            "exactly one OpenPGP signature required", str(caught.exception))

    def test_signed_validation_skips_shared_input_seals(self):
        directory, repo, sha = _unsigned_repo()
        self.addCleanup(directory.cleanup)
        expected = {
            "source_revision": sha,
            "modules": [],
            "assignments": [{"id": "ordinary-000"}],
        }
        with patch.object(SHARDS.source_evidence, "verify_signed_commit", return_value=None), \
                patch.object(SHARDS.source_evidence, "optional", side_effect=AssertionError("stale seal read")), \
                patch.object(SHARDS, "plan", return_value=expected), \
                patch.object(SHARDS, "serial_modules", return_value=["tests/test_serial.py"]), \
                patch.object(SHARDS, "tree_inputs", return_value={}), \
                patch.object(SHARDS, "shared_inputs", return_value={}), \
                patch.object(SHARDS, "admit_shared_inputs",
                             side_effect=AssertionError("seal opened")):
            result = SHARDS.expand(
                _targets(sha), repo, "b" * 40, "ubuntu-24.04", 20, 16,
                validation_only=True)
        self.assertIs(result["validation_only"], True)
        self.assertEqual(result["mode"], "sharded")
        self.assertNotIn("pin_is_ancestor", result)


class CiCheckSurface(unittest.TestCase):
    def test_workflow_flag_is_only_inside_the_validation_guard(self):
        text = workflow_text()
        self.assertEqual(text.count("--validation-only"), 1)
        guard = text.split('if [ "${VALIDATION_ONLY:-false}" = true ]; then', 1)[1]
        guard = guard.split("\n          fi", 1)[0]
        self.assertIn("expand_args+=(--validation-only)", guard)

    def test_usage_exits_before_dispatch(self):
        script = ROOT / "scripts/ci-check.sh"
        syntax = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        cases = ([], ["yueboard", "abcdef1"], ["yueops", "not-a-sha"], ["yueops"])
        for args in cases:
            with self.subTest(args=args):
                result = subprocess.run(
                    ["bash", str(script), *args], capture_output=True, text=True)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertNotIn("workflow run", result.stdout + result.stderr)

    def test_node_ids_keep_spaces_inside_parameter_brackets(self):
        text = (
            "2026-11-13T00:00:00.0000000Z FAILED "
            "tests/test_a.py::test_b[versions 1-skipped 1] - AssertionError: boom\n"
            "2026-11-13T00:00:01.0000000Z ERROR "
            "tests/test_a.py::test_b[versions 1-skipped 1] - duplicate\n"
        )
        self.assertEqual(
            FAILURES.node_ids(text),
            ["tests/test_a.py::test_b[versions 1-skipped 1]"])


if __name__ == "__main__":
    unittest.main()
