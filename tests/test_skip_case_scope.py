"""Case-scoped skip admission: an unrelated edit to a test module keeps a skip.

The admitted record names a module blob. When only other tests in that module
changed, the case's own definition digest is unchanged and the skip stays the
same skip. Any edit to the case itself, its class, or ``pytestmark`` is new.
"""
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("case_scope_shards", ROOT / "scripts/pytest-shards.py")
SHARDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARDS)

MODULE = "tests/test_sample.py"
NODE = MODULE + "::test_needs_binary"
BASE = (
    "import pytest\n\n"
    "def test_needs_binary():\n"
    "    pytest.skip('binary missing')\n\n"
    "def test_other():\n"
    "    assert 1\n"
)
OTHER_EDIT = BASE.replace("assert 1", "assert 2 == 2") + "\n\ndef test_new():\n    assert True\n"
CASE_EDIT = BASE.replace("pytest.skip('binary missing')", "pytest.skip('binary missing')\n    assert 0")
MARK_EDIT = "pytestmark = []\n" + BASE


def blob(repo, text):
    return subprocess.run(["git", "-C", str(repo), "hash-object", "-w", "--stdin"], input=text.encode(),
                          capture_output=True, check=True).stdout.decode().strip()


class CaseScopeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.base = blob(self.repo, BASE)
        self.record = {"outcome": "skipped", "reason": "Skipped: binary missing", "module_blob": self.base}

    def tearDown(self):
        self.tmp.cleanup()

    def successor(self, text, nodeid=NODE, record=None):
        return SHARDS.case_scope_successor(
            self.repo, nodeid, blob(self.repo, text), [record or self.record],
            lambda r: r["reason"] == "Skipped: binary missing")

    def test_unrelated_edit_keeps_the_admitted_skip(self):
        self.assertEqual(self.successor(OTHER_EDIT), self.record)

    def test_parametrized_id_uses_the_function(self):
        self.assertEqual(self.successor(OTHER_EDIT, NODE + "[x]"), self.record)

    def test_edit_to_the_case_is_new(self):
        self.assertIsNone(self.successor(CASE_EDIT))

    def test_pytestmark_edit_is_new(self):
        self.assertIsNone(self.successor(MARK_EDIT))

    def test_reason_must_match(self):
        other = dict(self.record, reason="Skipped: different")
        self.assertIsNone(SHARDS.case_scope_successor(
            self.repo, NODE, blob(self.repo, OTHER_EDIT), [other],
            lambda r: r["reason"] == "Skipped: binary missing"))

    def test_missing_source_or_unknown_case_is_new(self):
        self.assertIsNone(SHARDS.case_scope_successor(
            None, NODE, blob(self.repo, OTHER_EDIT), [self.record], lambda r: True))
        self.assertIsNone(self.successor(OTHER_EDIT, MODULE + "::test_absent"))

    def test_native_modules_never_derive(self):
        native = next(iter(SHARDS.NATIVE_TARGETS))
        self.assertIsNone(SHARDS.case_scope_successor(
            self.repo, native + "::test_needs_binary", blob(self.repo, OTHER_EDIT),
            [self.record], lambda r: True))

    def test_derive_prior_skips_without_source_admits_nothing(self):
        self.assertEqual(SHARDS.derive_prior_skips({}, None, [(NODE, {})]), set())


if __name__ == "__main__":
    unittest.main()
