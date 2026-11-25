"""The public deadman copy is generated from one named YueOps commit."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deadman" / "canonical" / "scripts" / "deadman_producer.py"
PIN = ROOT / "deadman" / "canonical" / "yueops-producer.json"
CONTRACT = (
    ROOT / "deadman" / "canonical" / "config" / "alert-chain-deadman-observer-contract.json"
)
WORKFLOW = ROOT / ".github" / "workflows" / "alert-chain-deadman.yml"
YUEOPS = Path("/Users/j/Projects/yueto/yueops")
CHECKOUT_PIN = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1"
APP_PIN = (
    "actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1 # v3.2.0"
)


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _git(repo: Path, *args: str) -> str:
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "Deadman Producer",
            "GIT_AUTHOR_EMAIL": "deadman-producer@example.com",
            "GIT_COMMITTER_NAME": "Deadman Producer",
            "GIT_COMMITTER_EMAIL": "deadman-producer@example.com",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_COUNT": "0",
        }
    )
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def _seed(directory: Path) -> tuple[Path, Path, str]:
    repo = directory / "yueops"
    root = directory / "canonical"
    (repo / "scripts").mkdir(parents=True)
    (repo / "config").mkdir()
    root.mkdir()
    (repo / "scripts" / "alert-chain-deadman-check.py").write_bytes(b"checker-v1\n")
    (repo / "config" / "alert-chain-deadman-observer-contract.json").write_bytes(
        b'{"schema_version":1}\n'
    )
    _git(repo, "init", "-q")
    _git(
        repo,
        "add",
        "scripts/alert-chain-deadman-check.py",
        "config/alert-chain-deadman-observer-contract.json",
    )
    _git(repo, "commit", "-q", "-m", "producer")
    sha = _git(repo, "rev-parse", "HEAD")
    applied = _run(["--apply", "--root", str(root), "--repo", str(repo), "--sha", sha])
    if applied.returncode != 0:
        raise AssertionError(applied.stderr)
    return root, repo, sha


def test_public_copy_matches_the_named_yueops_sha() -> None:
    result = _run(["--check"])
    assert result.returncode == 0, result.stderr
    assert "deadman producer: ok (" in result.stdout
    pin = json.loads(PIN.read_text(encoding="utf-8"))
    assert pin["repository"] == "onesyue/yueops"
    assert len(pin["sha"]) == 40
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    checker = next(
        row for row in pin["copies"] if row["source"] == "scripts/alert-chain-deadman-check.py"
    )
    assert checker["sha256"] == contract["canonical"]["checker_sha256"]
    if YUEOPS.is_dir():
        live = _run(["--check", "--repo", str(YUEOPS)])
        assert live.returncode == 0, live.stderr


def test_hand_edited_copy_fails_check() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root, _repo, _sha = _seed(Path(directory))
        target = root / "scripts" / "alert-chain-deadman-check.py"
        target.write_bytes(target.read_bytes() + b"# hand edit\n")
        result = _run(["--check", "--root", str(root)])
    assert result.returncode != 0
    assert "hand-edited deadman copy: scripts/alert-chain-deadman-check.py" in result.stderr


def test_updated_hash_without_the_named_commit_is_drift() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root, repo, sha = _seed(Path(directory))
        target = root / "scripts" / "alert-chain-deadman-check.py"
        edited = target.read_bytes() + b"x"
        target.write_bytes(edited)
        pin_path = root / "yueops-producer.json"
        pin = json.loads(pin_path.read_text(encoding="utf-8"))
        for row in pin["copies"]:
            if row["copy"] == "scripts/alert-chain-deadman-check.py":
                row["sha256"] = hashlib.sha256(edited).hexdigest()
        pin_path.write_text(json.dumps(pin, indent=2) + "\n", encoding="utf-8")
        result = _run(["--check", "--root", str(root), "--repo", str(repo)])
    assert result.returncode != 0
    assert f"drifted from yueops SHA {sha}: scripts/alert-chain-deadman-check.py" in result.stderr


def test_pin_sha_that_does_not_match_the_copy_fails() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root, repo, _first = _seed(Path(directory))
        path = repo / "scripts" / "alert-chain-deadman-check.py"
        path.write_bytes(b"checker-v2\n")
        _git(repo, "add", "scripts/alert-chain-deadman-check.py")
        _git(repo, "commit", "-q", "-m", "next")
        second = _git(repo, "rev-parse", "HEAD")
        pin_path = root / "yueops-producer.json"
        pin = json.loads(pin_path.read_text(encoding="utf-8"))
        pin["sha"] = second
        pin_path.write_text(json.dumps(pin, indent=2) + "\n", encoding="utf-8")
        result = _run(["--check", "--root", str(root), "--repo", str(repo)])
    assert result.returncode != 0
    assert f"drifted from yueops SHA {second}" in result.stderr


def test_apply_rewrites_the_copy_from_the_named_sha() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root, repo, first = _seed(Path(directory))
        path = repo / "scripts" / "alert-chain-deadman-check.py"
        path.write_bytes(b"checker-v2\n")
        _git(repo, "add", "scripts/alert-chain-deadman-check.py")
        _git(repo, "commit", "-q", "-m", "next")
        second = _git(repo, "rev-parse", "HEAD")
        applied = _run(
            ["--apply", "--root", str(root), "--repo", str(repo), "--sha", second]
        )
        assert applied.returncode == 0, applied.stderr
        assert path.read_bytes() == (root / "scripts" / "alert-chain-deadman-check.py").read_bytes()
        checked = _run(["--check", "--root", str(root), "--repo", str(repo)])
        assert checked.returncode == 0, checked.stderr
        pin = json.loads((root / "yueops-producer.json").read_text(encoding="utf-8"))
        assert pin["sha"] == second
        assert pin["sha"] != first


def test_apply_rejects_a_sha_that_is_not_40_hex() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "canonical"
        root.mkdir()
        result = _run(["--apply", "--root", str(root), "--repo", str(root), "--sha", "abc"])
    assert result.returncode != 0
    assert "40 lowercase hex" in result.stderr
    assert not (root / "yueops-producer.json").exists()


def test_pin_must_name_yueops() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root, _repo, _sha = _seed(Path(directory))
        pin_path = root / "yueops-producer.json"
        pin = json.loads(pin_path.read_text(encoding="utf-8"))
        pin["repository"] = "elsewhere/tree"
        pin_path.write_text(json.dumps(pin) + "\n", encoding="utf-8")
        result = _run(["--check", "--root", str(root)])
    assert result.returncode != 0
    assert "does not name the yueops copies" in result.stderr


def test_workflow_checks_the_producer_without_bumping_action_pins() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "deadman/canonical/scripts/deadman_producer.py --check" in text
    assert "deadman_producer.py --check --repo .ci-yueops" in text
    assert text.count(CHECKOUT_PIN) == 2
    assert APP_PIN in text
    assert "ref: master" in text


def load_tests(
    loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str | None
) -> unittest.TestSuite:
    checks = sorted(
        (name, check)
        for name, check in globals().items()
        if name.startswith("test_") and callable(check)
    )
    if len(checks) < 6:
        raise RuntimeError("deadman producer coverage fell below six checks")
    return unittest.TestSuite(unittest.FunctionTestCase(check) for _, check in checks)


if __name__ == "__main__":
    unittest.main()
