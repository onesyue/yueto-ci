import hashlib
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pytest_shards_miniapp", ROOT / "scripts/pytest-shards.py")
SHARDS = importlib.util.module_from_spec(spec)
spec.loader.exec_module(SHARDS)
PATH = SHARDS.MINIAPP_MEMBERSHIP_INPUT
REVIEW = ROOT / "reviews/ops-miniapp-membership-20261102"


class MiniappMembershipTransitionTest(unittest.TestCase):
    def setUp(self):
        self.record = SHARDS.reviewed_miniapp_membership_transition()
        self.change = self.record["changes"][PATH]
        self.pin = SHARDS.first_native_policy()["source_revision"]

    def test_record_binds_real_review_artifacts(self):
        digest = lambda n: hashlib.sha256((REVIEW / n).read_bytes()).hexdigest()
        self.assertEqual(self.record["independent_review_sha256"], digest("independent-review.md"))
        self.assertEqual(self.record["source_freeze_sha256"], digest("source-freeze.json"))
        self.assertEqual(self.record["qualification_receipt_sha256"], digest("qualification.json"))
        self.assertTrue(self.record["reviewer"].startswith("Codex"))
        self.assertIn("VERDICT: APPROVE", (REVIEW / "independent-review.md").read_text())
        freeze = json.loads((REVIEW / "source-freeze.json").read_text())
        self.assertEqual((freeze["before_blob"], freeze["after_blob"]),
                         (self.change["before_blob"], self.change["after_blob"]))

    def test_admits_after_blob_only_at_signed_pin(self):
        common = {PATH: self.change["after_blob"], "x": "1"}
        files = {PATH: ("100644", self.change["after_blob"]), "x": ("100644", "1")}
        c, f = SHARDS.admit_miniapp_membership(common, files, self.pin)
        self.assertEqual(c[PATH], self.change["before_blob"])
        self.assertEqual(f[PATH], ("100644", self.change["before_blob"]))
        with self.assertRaises(ValueError):
            SHARDS.admit_miniapp_membership(common, files, "0" * 40)

    def test_other_blobs_and_modes_untouched_or_refused(self):
        common = {PATH: "f" * 40}
        self.assertEqual(SHARDS.admit_miniapp_membership(common, None, self.pin)[0], common)
        with self.assertRaises(ValueError):
            SHARDS.admit_miniapp_membership({PATH: self.change["after_blob"]},
                                            {PATH: ("100755", self.change["after_blob"])}, self.pin)

    def test_tampered_record_rejected(self):
        bad = json.loads((ROOT / "ops-shared-input-successors.json").read_text())
        bad["reviewed_miniapp_membership_transition"]["changes"][PATH]["after_blob"] = "e" * 40
        with patch.object(SHARDS, "read_json", return_value=bad):
            with self.assertRaises(ValueError):
                SHARDS.reviewed_miniapp_membership_transition()


if __name__ == "__main__":
    unittest.main()
