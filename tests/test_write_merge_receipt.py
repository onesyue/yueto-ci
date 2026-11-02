"""Offline controls for writing receipts at the actual merged head."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "write_merge_receipt", Path(__file__).resolve().parents[1] / "scripts/write-merge-receipt.py")
WRITER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WRITER)
HEAD = "a" * 40


class WriteMergeReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root_patch = patch.object(WRITER, "ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        (self.root / "review.md").write_text("Independent approval of actual head.\n")
        (self.root / "parity.log").write_bytes(b"tests passed\r\n")
        self.pr = {"number": 75, "merged": True, "merged_at": "2026-11-02T12:00:00Z",
                   "head": {"sha": HEAD}, "user": {"login": "author"}}
        self.api_patch = patch.object(WRITER.AUDIT, "api", side_effect=self.api)
        self.api_patch.start()
        self.addCleanup(self.api_patch.stop)
        self.destination = self.root / "merge-receipts/yueops/75.json"
        self.args = {
            "repo": "yueops", "pr": "75", "review-artifact": "review.md",
            "reviewed-head": HEAD, "reviewed-at": "2026-11-02T11:00:00Z",
            "parity-log": "parity.log", "parity-head": HEAD,
            "parity-command": "python3 -m pytest -q", "ran-at": "2026-11-02T12:00:00Z",
            "runner": "box", "verdict": "approve", "result": "pass",
        }

    def api(self, endpoint):
        self.assertEqual(endpoint, "repos/onesyue/yueops/pulls/75")
        return self.pr

    def run_writer(self, *flags, **changes):
        args = self.args | changes
        argv = [part for key, value in args.items() for part in ("--" + key, value)]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = WRITER.main(argv + list(flags))
        return status, out.getvalue(), err.getvalue()

    def test_merged_head_success(self):
        status, _, error = self.run_writer()
        self.assertEqual(status, 0, error)
        receipt = json.loads(self.destination.read_text())
        self.assertEqual(receipt["head"], HEAD)
        self.assertEqual(receipt["review"]["reviewed_head"], HEAD)
        self.assertEqual(receipt["parity"]["head"], HEAD)
        self.assertEqual(receipt["review"]["reviewer"], "codex")
        self.assertFalse(receipt["backfilled"])
        self.assertEqual(receipt["parity"]["log_sha256"],
                         hashlib.sha256(b"tests passed\r\n").hexdigest())

    def test_pre_merge_head_refused(self):
        for field, label in (("reviewed-head", "review"), ("parity-head", "parity")):
            with self.subTest(field=field):
                status, _, error = self.run_writer(**{field: "b" * 40})
                self.assertEqual(status, 2)
                self.assertIn(f"{label} must be redone at the merged head", error)
                self.assertIn("master merge-in", error)
                self.assertFalse(self.destination.exists())

    def test_unmerged_refused(self):
        self.pr.update(merged=False, merged_at=None)
        status, _, error = self.run_writer()
        self.assertEqual(status, 2)
        self.assertIn("not merged", error)
        self.assertFalse(self.destination.exists())

    def test_over_24_hours_refused(self):
        for field in ("reviewed-at", "ran-at"):
            with self.subTest(field=field):
                status, _, error = self.run_writer(**{field: "2026-11-03T12:00:01Z"})
                self.assertEqual(status, 2)
                self.assertIn("more than 24h", error)
                self.assertFalse(self.destination.exists())

    def test_timezone_required(self):
        for field in ("reviewed-at", "ran-at"):
            with self.subTest(field=field):
                status, _, error = self.run_writer(**{field: "2026-11-02T12:00:00"})
                self.assertEqual(status, 2)
                self.assertIn("timezone", error)
                self.assertFalse(self.destination.exists())

    def test_backfilled_computed_for_either_timestamp_including_24h_boundary(self):
        for field in ("reviewed-at", "ran-at"):
            with self.subTest(field=field):
                status, output, error = self.run_writer(
                    "--dry-run", **{field: "2026-11-03T20:00:00+08:00"})
                self.assertEqual(status, 0, error)
                self.assertTrue(json.loads(output)["backfilled"])

    def test_refuse_overwrite_and_replace_without_backup(self):
        self.destination.parent.mkdir(parents=True)
        self.destination.write_text("old receipt\n")
        status, _, error = self.run_writer()
        self.assertEqual(status, 2)
        self.assertIn("--replace", error)
        self.assertEqual(self.destination.read_text(), "old receipt\n")
        status, _, error = self.run_writer("--replace")
        self.assertEqual(status, 0, error)
        self.assertEqual(json.loads(self.destination.read_text())["head"], HEAD)
        self.assertEqual(list(self.destination.parent.iterdir()), [self.destination])

    def test_dry_run_writes_nothing(self):
        before = {p.relative_to(self.root): p.read_bytes()
                  for p in self.root.rglob("*") if p.is_file()}
        status, output, error = self.run_writer("--dry-run")
        self.assertEqual(status, 0, error)
        self.assertEqual(json.loads(output)["head"], HEAD)
        self.assertFalse((self.root / "merge-receipts").exists())
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes()
                                 for p in self.root.rglob("*") if p.is_file()})

    def test_dry_run_replace_preserves_existing(self):
        self.destination.parent.mkdir(parents=True)
        self.destination.write_text("old receipt\n")
        status, _, error = self.run_writer("--replace", "--dry-run")
        self.assertEqual(status, 0, error)
        self.assertEqual(self.destination.read_text(), "old receipt\n")

    def test_evidence_paths_must_exist_inside_repository(self):
        for field in ("review-artifact", "parity-log"):
            for path in ("missing", "../review.md", str(self.root / "review.md")):
                with self.subTest(field=field, path=path):
                    status, _, error = self.run_writer(**{field: path})
                    self.assertEqual(status, 2)
                    self.assertIn("repo-relative", error)
                    self.assertFalse(self.destination.exists())

    def test_audit_validation_rejects_author_as_reviewer_and_empty_command(self):
        for change in ({"reviewer": "AUTHOR"}, {"parity-command": " "}):
            with self.subTest(change=change):
                status, _, error = self.run_writer(**change)
                self.assertEqual(status, 2)
                self.assertIn("invalid receipt evidence", error)
                self.assertFalse(self.destination.exists())

    def test_audit_rejection_preserves_existing_receipt(self):
        self.destination.parent.mkdir(parents=True)
        self.destination.write_text("old receipt\n")
        status, _, _ = self.run_writer("--replace", reviewer="author")
        self.assertEqual(status, 2)
        self.assertEqual(self.destination.read_text(), "old receipt\n")


if __name__ == "__main__":
    unittest.main()
