"""Real temporary signing keys exercise Git object admission, never owner keys."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import source_evidence as E


class SourceEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.home = Path(cls.temporary.name) / "gpg"
        cls.home.mkdir(mode=0o700)
        cls.env = dict(os.environ, GNUPGHOME=str(cls.home))
        cls.gpg = shutil.which("gpg")
        # No skip for missing cryptographic tooling: this module is a required gate.
        subprocess.run([cls.gpg, "--batch", "--pinentry-mode", "loopback", "--passphrase", "",
                        "--quick-generate-key", "Fixture <fixture@example.invalid>",
                        "ed25519", "sign", "0"], env=cls.env, check=True, capture_output=True)
        listing = subprocess.check_output([cls.gpg, "--with-colons", "--list-keys"], env=cls.env)
        cls.fingerprint = next(line.split(b":")[9].decode() for line in listing.splitlines()
                               if line.startswith(b"fpr:"))
        cls.policy = Path(cls.temporary.name) / "policy"
        cls.policy.mkdir()
        key = subprocess.check_output([cls.gpg, "--export", cls.fingerprint], env=cls.env)
        (cls.policy / "yueops-owner.gpg").write_bytes(key)
        cls.authority = {"schema": 1, "signer": cls.fingerprint, "primary": cls.fingerprint,
                         "keyring_sha256": E.digest(key)}
        (cls.policy / "yueops-owner-signers.json").write_text(json.dumps(cls.authority))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.signingkey", self.fingerprint)
        self.git("config", "gpg.program", self.gpg)
        (self.repo / "app.py").write_text("raise Exception('must never execute')\n")
        self.git("add", "app.py")
        self.git("commit", "-qm", "initial", "--no-gpg-sign")
        tree = E.tree_inputs(self.repo, self.git("rev-parse", "HEAD"))
        self.inputs = {"schema": 1, "inputs": tree, "inputs_sha256": E.digest(E.canonical(tree))}
        self.baseline = {"schema": 1, "status": "HISTORICAL_SKIPS_NOT_PASSES", "cases": {},
                         "collection_skips": {}, "inputs_sha256": self.inputs["inputs_sha256"]}
        for path, value in ((E.INPUTS, self.inputs), (E.BASELINE, self.baseline)):
            target = self.repo / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(value))
        self.head = self.commit()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], env=self.env,
                                       stderr=subprocess.PIPE).decode().strip()

    def commit(self, signed=True):
        self.git("add", ".")
        self.git("commit", "-qm", "fixture", "-S" if signed else "--no-gpg-sign")
        return self.git("rev-parse", "HEAD")

    def load(self, head=None):
        return E._load(self.repo, head or self.head, self.policy)

    def test_signed_exact_tree_bound_not_admitted(self):
        result = self.load()
        self.assertEqual(result["source_revision"], self.head)
        self.assertFalse(result["admission"])
        self.assertEqual(set(result["evidence"]), E.EVIDENCE_PATHS)

    def test_dirty_evidence_and_source_never_read(self):
        (self.repo / E.INPUTS).write_text("invalid")
        (self.repo / "app.py").write_text("changed")
        self.assertEqual(self.load()["source_revision"], self.head)

    def test_unsigned_commit_rejected(self):
        (self.repo / E.BASELINE).write_text(json.dumps(self.baseline) + "\n")
        with self.assertRaisesRegex(E.Rejected, "OpenPGP"):
            self.load(self.commit(signed=False))

    def test_authorized_signature_cannot_approve_wrong_blob(self):
        (self.repo / "app.py").write_text("changed")
        with self.assertRaisesRegex(E.Rejected, "manifest mismatch"):
            self.load(self.commit())

    def test_missing_or_symlink_evidence_rejected(self):
        for symlink in (False, True):
            with self.subTest(symlink=symlink):
                target = self.repo / E.BASELINE
                if target.exists():
                    target.unlink()
                if symlink:
                    target.symlink_to("shared-inputs.json")
                with self.assertRaisesRegex(E.Rejected, "nonregular evidence"):
                    self.load(self.commit())

    def test_untrusted_primary_or_signer_rejected(self):
        for field in ("signer", "primary"):
            with self.subTest(field=field):
                policy = self.repo / "test-policy"
                policy.mkdir(exist_ok=True)
                shutil.copyfile(self.policy / "yueops-owner.gpg", policy / "yueops-owner.gpg")
                (policy / "yueops-owner-signers.json").write_text(
                    json.dumps(self.authority | {field: "F" * 40}))
                with self.assertRaisesRegex(E.Rejected, "unauthorized"):
                    E._load(self.repo, self.head, policy)

    def test_injected_git_environment_cannot_redirect_source(self):
        with patch.dict(os.environ, {"GIT_DIR": "/nonexistent", "GIT_CONFIG_COUNT": "1",
                                    "GIT_CONFIG_KEY_0": "core.hooksPath",
                                    "GIT_CONFIG_VALUE_0": "/nonexistent"}):
            self.assertEqual(self.load()["source_revision"], self.head)

    def test_candidate_keyring_cannot_replace_public_authority(self):
        shutil.copytree(self.policy, self.repo / "policy")
        # A candidate-supplied valid fixture authority is not the public authority.
        with self.assertRaisesRegex(E.Rejected, "unauthorized"):
            E.load(self.repo, self.head)
        self.assertEqual(self.load()["source_revision"], self.head)

    def test_refs_and_missing_objects_rejected(self):
        for ref in ("HEAD", "f" * 40):
            with self.subTest(ref=ref), self.assertRaises(E.Rejected):
                self.load(ref)

    def test_duplicate_json_keys_and_mismatched_baseline_rejected(self):
        (self.repo / E.BASELINE).write_text('{"schema":1,"schema":1}')
        with self.assertRaisesRegex(E.Rejected, "JSON"):
            self.load(self.commit())
        (self.repo / E.BASELINE).write_text(json.dumps(self.baseline | {"inputs_sha256": "0" * 64}))
        with self.assertRaisesRegex(E.Rejected, "skip baseline"):
            self.load(self.commit())


if __name__ == "__main__":
    unittest.main()
