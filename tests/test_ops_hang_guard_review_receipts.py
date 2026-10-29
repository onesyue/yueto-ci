"""The 2026-10-29 hang-guard / release skip-blob seals bind committed review receipts."""
import hashlib
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEWS = ROOT / "reviews" / "ops-hang-guard-20261029"
HANG = "reviewed_hang_guard_input_transition"
RELEASE = "reviewed_release_skip_blob_successor_transition"
PLACEHOLDER = re.compile(r"^([0-9a-f])\1{63}$")


def sha_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


class ReviewReceiptBinding(unittest.TestCase):
    def setUp(self):
        self.baseline = json.loads((ROOT / "ops-pytest-skip-baseline.json").read_text())
        self.hang = self.baseline[HANG]
        self.release = self.baseline[RELEASE]
        self.document = json.loads((REVIEWS / "release-review-document.json").read_text())

    def test_hang_record_binds_committed_receipt_and_source_freeze(self):
        receipt = REVIEWS / "receipt-A-tests-_subprocess.md"
        self.assertEqual(self.hang["independent_review_sha256"], sha_file(receipt))
        self.assertIn("结论：APPROVE", receipt.read_text())
        self.assertEqual(self.hang["source_freeze_sha256"],
                         sha_file(REVIEWS / "source-freeze-03db123be.lstree"))

    def test_release_record_binds_committed_review_document_and_receipt(self):
        receipt = REVIEWS / "receipt-B-release-skip-blob-successors.md"
        self.assertIn("结论：APPROVE", receipt.read_text())
        self.assertEqual(self.document["review_receipt_sha256"], sha_file(receipt))
        self.assertEqual(self.release["independent_review_sha256"],
                         hashlib.sha256(encoded(self.document)).hexdigest())
        self.assertEqual(self.document["kind"], "independent-skip-blob-successor-review")
        self.assertEqual(self.document["reviewer"], "independent")
        self.assertEqual((self.document["source_before"], self.document["source_after"]),
                         (self.release["source_before"], self.release["source_after"]))
        cases = {c["nodeid"]: c for c in self.document["cases"]}
        self.assertEqual(len(cases), len(self.document["cases"]))
        self.assertEqual(set(cases), set(self.release["updates"]))
        for nodeid, update in self.release["updates"].items():
            case = cases[nodeid]
            self.assertEqual((case["verdict"], case["basis"], case["outcome"]),
                             ("approve", "environmental", "skipped"))
            self.assertEqual((case["before_blob"], case["after_blob"]),
                             (update["before_blob"], update["after_blob"]))

    def test_receipt_verification_covers_exactly_the_reviewed_cases(self):
        verification = json.loads((REVIEWS / "independent-verification.json").read_text())
        self.assertIn(sha_file(REVIEWS / "independent-verification.json"),
                      (REVIEWS / "receipt-B-release-skip-blob-successors.md").read_text())
        self.assertEqual((verification["rows"], verification["unique"]),
                         (len(self.release["updates"]), len(self.release["updates"])))
        self.assertEqual((verification["missing"], verification["failures"]), ([], []))
        self.assertEqual({row["nodeid"] for row in verification["extracted"]},
                         set(self.release["updates"]))

    def test_no_placeholder_digest_survives_in_the_new_seals(self):
        def digests(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key.endswith("sha256"):
                        yield item
                    yield from digests(item)
            elif isinstance(value, list):
                for item in value:
                    yield from digests(item)
        for value in (self.hang, self.release, self.document):
            for digest in digests(value):
                self.assertIsInstance(digest, str)
                self.assertFalse(PLACEHOLDER.match(digest), digest)


if __name__ == "__main__":
    unittest.main()
