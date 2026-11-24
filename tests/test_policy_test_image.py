"""The local policy-test image must include tools its official tests actually run."""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "images/policy-test/Dockerfile"
RUNNER = ROOT / "scripts/run-policy-docker.sh"
README = ROOT / "README.md"
PINS = ROOT / "tests/test_validate_toolchain_pins.py"
POLICY_TESTS = ROOT / "scripts/run-policy-tests.py"

_GIT_IDENT = {
    "GIT_AUTHOR_NAME": "policy-docker-test",
    "GIT_AUTHOR_EMAIL": "policy-docker-test@example.invalid",
    "GIT_COMMITTER_NAME": "policy-docker-test",
    "GIT_COMMITTER_EMAIL": "policy-docker-test@example.invalid",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
}


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, **_GIT_IDENT}
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "commit.gpgsign=false", *args],
        check=check,
        capture_output=True,
        text=True,
        env=env,
    )


def _init_repo_with_runner(path: Path) -> None:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "master", str(path)], check=True, capture_output=True)
    scripts = path / "scripts"
    scripts.mkdir()
    shutil.copy(RUNNER, scripts / "run-policy-docker.sh")
    (scripts / "run-policy-docker.sh").chmod(0o755)
    (path / "README").write_text("fixture\n", encoding="utf-8")
    _git(path, "add", "README", "scripts/run-policy-docker.sh")
    _git(path, "commit", "-m", "init")


def _rmtree(path: Path) -> None:
    if path.exists():
        subprocess.run(["chmod", "-R", "u+w", str(path)], check=False, capture_output=True)
        shutil.rmtree(path, ignore_errors=True)


class PolicyTestImageContract(unittest.TestCase):
    def test_dockerfile_installs_xz_for_tar_cJf_fixtures(self) -> None:
        dockerfile = DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn("xz-utils", dockerfile)
        self.assertIn('["tar", "-cJf"', PINS.read_text(encoding="utf-8"))
        # Host policy PATH checks stay on the existing closed tool set.
        # Linux gnu tar needs the xz helper for -J; macOS bsdtar does not.
        self.assertNotIn('"xz"', POLICY_TESTS.read_text(encoding="utf-8"))
        self.assertNotIn("'xz'", POLICY_TESTS.read_text(encoding="utf-8"))

    def test_official_docker_replay_uses_per_module_policy_runner(self) -> None:
        readme = README.read_text(encoding="utf-8")
        runner = RUNNER.read_text(encoding="utf-8")
        self.assertIn("scripts/run-policy-docker.sh", readme)
        self.assertIn("scripts/check-policy.sh", runner)
        self.assertIn("scripts/run-policy-tests.py", readme)
        local = readme.split("## Local policy checks", 1)[1].split("### ", 1)[0]
        self.assertNotIn("python3 -m unittest discover -s tests -p 'test_*.py' -v", local)
        self.assertIn("never pushes", runner)
        self.assertIn("read-only", runner)
        self.assertIn("--preflight", runner)
        self.assertIn("command -v", runner)
        self.assertNotIn("docker push", runner)
        self.assertNotIn("ssh-key", runner)
        self.assertNotIn("SSH_AUTH_SOCK", runner)
        self.assertIn('-v "$mount_src:/policy:ro"', runner)
        self.assertIn("GIT_CONFIG_VALUE_0=/policy", runner)
        self.assertIn("safe.directory", runner)
        self.assertIn("bash -c", runner)
        self.assertNotIn("bash -lc", runner)


class PolicyDockerSnapshotTests(unittest.TestCase):
    def test_runner_is_executable(self) -> None:
        self.assertTrue(RUNNER.is_file())
        self.assertTrue(os.access(RUNNER, os.X_OK), RUNNER)
        self.assertTrue(stat.S_IXUSR & RUNNER.stat().st_mode)

    def test_prepare_snapshot_for_a_worktree_is_independent_and_credential_free(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp) / "main"
            _init_repo_with_runner(main)
            _git(main, "config", "credential.helper", "osxkeychain")
            worktree = Path(tmp) / "worktree"
            _git(main, "worktree", "add", str(worktree))
            pointer_before = (worktree / ".git").read_text(encoding="utf-8")
            self.assertTrue(pointer_before.startswith("gitdir:"))
            source_head = _git(worktree, "rev-parse", "HEAD").stdout.strip()
            env = {**os.environ, "TMPDIR": str(Path(tmp) / "snaps")}
            Path(tmp, "snaps").mkdir()
            result = subprocess.run(
                ["bash", str(worktree / "scripts/run-policy-docker.sh"), "--prepare-only", "--keep-snapshot"],
                cwd=worktree,
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            snap = Path(result.stdout.strip())
            self.assertTrue((snap / ".git").is_dir(), snap)
            self.assertFalse((snap / ".git").is_file())
            snap_head = _git(snap, "rev-parse", "HEAD").stdout.strip()
            self.assertEqual(snap_head, source_head)
            config = _git(snap, "config", "--list", "--local").stdout
            helpers = [
                line.split("=", 1)[1]
                for line in config.splitlines()
                if line.startswith("credential.helper=")
            ]
            self.assertTrue(all(helper == "" for helper in helpers), config)
            self.assertNotIn("http.extraheader", config.lower())
            self.assertNotIn("osxkeychain", config)
            remotes = _git(snap, "remote")
            self.assertEqual(remotes.stdout.strip(), "")
            hooks = list((snap / ".git/hooks").glob("*"))
            self.assertEqual(hooks, [])
            self.assertEqual((worktree / ".git").read_text(encoding="utf-8"), pointer_before)
            self.assertTrue((main / ".git").is_dir())
            self.assertIn("worktree detected", result.stderr)
            self.assertIn("disposable credential-free snapshot", result.stderr)

    def test_prepare_on_a_regular_checkout_mounts_the_tree_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "regular"
            _init_repo_with_runner(repo)
            env = {**os.environ, "TMPDIR": str(Path(tmp) / "snaps")}
            Path(tmp, "snaps").mkdir()
            result = subprocess.run(
                ["bash", str(repo / "scripts/run-policy-docker.sh"), "--prepare-only"],
                cwd=repo,
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(Path(result.stdout.strip()).resolve(), repo.resolve())
            self.assertTrue((repo / ".git").is_dir())
            self.assertEqual(list(Path(tmp, "snaps").iterdir()), [])
            self.assertIn("regular checkout", result.stderr)

    def test_current_worktree_pointer_is_left_untouched(self) -> None:
        gitdir = ROOT / ".git"
        if not gitdir.is_file() or not gitdir.read_text(encoding="utf-8").startswith("gitdir:"):
            self.skipTest("source checkout is not a git worktree")
        before = gitdir.read_text(encoding="utf-8")
        source_head = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip()
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "TMPDIR": tmp}
            result = subprocess.run(
                ["bash", str(RUNNER), "--prepare-only", "--keep-snapshot"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            snap = Path(result.stdout.strip())
            self.addCleanup(_rmtree, snap.parent)
            self.assertEqual(
                subprocess.check_output(
                    ["git", "-C", str(snap), "rev-parse", "HEAD"], text=True
                ).strip(),
                source_head,
            )
            self.assertEqual(gitdir.read_text(encoding="utf-8"), before)
            self.assertIn("worktree detected", result.stderr)


if __name__ == "__main__":
    unittest.main()
