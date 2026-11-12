"""Signed default-branch admission, with a fixture key rather than the owner key."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "signed_branch_admission", ROOT / "scripts" / "pytest-shards.py")
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)


class SignedDefaultBranchAdmission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.home = Path(cls.temporary.name) / "gpg"
        cls.home.mkdir(mode=0o700)
        cls.gpg = shutil.which("gpg")
        if cls.gpg is None:
            raise AssertionError("gpg is required to prove signature admission")
        cls.env = dict(os.environ, GNUPGHOME=str(cls.home))
        subprocess.run(
            [cls.gpg, "--batch", "--pinentry-mode", "loopback", "--passphrase", "",
             "--quick-generate-key", "Fixture <fixture@example.invalid>",
             "ed25519", "sign", "0"],
            env=cls.env, check=True, capture_output=True)
        listing = subprocess.check_output(
            [cls.gpg, "--with-colons", "--list-keys"], env=cls.env)
        cls.fingerprint = next(
            line.split(b":")[9].decode() for line in listing.splitlines()
            if line.startswith(b"fpr:"))
        cls.policy = Path(cls.temporary.name) / "policy"
        cls.policy.mkdir()
        key = subprocess.check_output([cls.gpg, "--export", cls.fingerprint], env=cls.env)
        (cls.policy / "yueops-owner.gpg").write_bytes(key)
        (cls.policy / "yueops-owner-signers.json").write_text(json.dumps({
            "schema": 1, "signer": cls.fingerprint, "primary": cls.fingerprint,
            "keyring_sha256": POLICY.source_evidence.digest(key),
        }))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "source"
        self.repo.mkdir()
        self.git("init", "-q", "-b", "master")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.signingkey", self.fingerprint)
        self.git("config", "gpg.program", self.gpg)

    def git(self, *args):
        return subprocess.check_output(
            ["git", "-C", str(self.repo), *args], env=self.env,
            stderr=subprocess.PIPE).decode().strip()

    def commit(self, message, signed):
        self.git("add", ".")
        self.git("commit", "-qm", message, "-S" if signed else "--no-gpg-sign")
        return self.git("rev-parse", "HEAD")

    def admit(self, revision):
        POLICY.admit_signed_default_branch(self.repo, revision, self.policy)

    def test_helper_and_conftest_on_a_signed_master_commit_are_admitted(self):
        tests = self.repo / "tests"
        tests.mkdir()
        (tests / "_helper.py").write_text("HELPER = 1\n")
        (self.repo / "conftest.py").write_text("def pytest_configure(config):\n    return None\n")
        head = self.commit("add helper and conftest", signed=True)
        self.admit(head)

    def test_ancestor_of_master_is_admitted_and_a_side_branch_is_not(self):
        (self.repo / "a.txt").write_text("a\n")
        first = self.commit("first", signed=True)
        (self.repo / "b.txt").write_text("b\n")
        self.commit("second", signed=True)
        self.admit(first)
        self.git("checkout", "-q", "-b", "side")
        (self.repo / "tests").mkdir()
        (self.repo / "tests" / "_helper.py").write_text("HELPER = 2\n")
        side = self.commit("side helper", signed=True)
        with self.assertRaises(ValueError) as caught:
            self.admit(side)
        self.assertIn("not on the default branch", str(caught.exception))

    def test_unsigned_master_commit_is_rejected(self):
        (self.repo / "a.txt").write_text("a\n")
        head = self.commit("unsigned", signed=False)
        with self.assertRaises(ValueError) as caught:
            self.admit(head)
        self.assertIn("unauthorized source signature", str(caught.exception))

    def test_missing_default_branch_fails_closed(self):
        (self.repo / "a.txt").write_text("a\n")
        head = self.commit("signed", signed=True)
        self.git("update-ref", "-d", "refs/heads/master")
        with self.assertRaises(ValueError) as caught:
            self.admit(head)
        self.assertIn("default branch ref is missing", str(caught.exception))
