"""Automatic ancestor closures must retain failures and prove the real merge source."""
import copy
import contextlib
import io
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("indirect_audit", ROOT / "scripts/merge-hygiene-audit.py")
assert spec is not None and spec.loader is not None
AUDIT = importlib.util.module_from_spec(spec)
spec.loader.exec_module(AUDIT)


class IndirectMergeSource(unittest.TestCase):
    def setUp(self):
        fixture = json.loads((ROOT / "tests/fixtures/merge-hygiene/approved.json").read_text())
        self.old = fixture["pr"] | {"number": 248, "state": "closed", "merge_commit_sha": "c" * 40,
                                   "merged_at": "2026-11-02T10:00:02Z"}
        self.old["base"] = {"sha": "b" * 40, "ref": "master", "repo": {"full_name": "onesyue/yueto-ci"}}
        self.direct = copy.deepcopy(self.old) | {"number": 252, "merged_at": "2026-11-02T10:00:00Z",
                                                "head": {"sha": "e" * 40}}
        self.parents = [{"sha": "b" * 40}, {"sha": "e" * 40}]
        self.commit_sha = "c" * 40
        self.associated = [self.old, self.direct]
        self.merged = [self.old, self.direct]
        self.direct_checks = fixture["checks"]
        self.old_checks = [fixture["checks"][0] | {"conclusion": "failure"}]
        self.reviews, self.statuses = fixture["reviews"], fixture["statuses"]
        self.proof = {"backfilled": False, "review": {"artifact": "reviews/merge-receipts-test/direct.md"}}
        self.second_compare = {"status": "ahead", "base_commit": {"sha": "a" * 40},
                               "merge_base_commit": {"sha": "a" * 40},
                               "ahead_by": 1, "behind_by": 0, "total_commits": 1}
        self.first_compare = {"status": "diverged", "base_commit": {"sha": "a" * 40},
                              "merge_base_commit": {"sha": "f" * 40},
                              "ahead_by": 2, "behind_by": 1, "total_commits": 2}
        self.paginated = False
        self.seen = []
        for name in ("read_cache", "write_cache"):
            mock = patch.object(AUDIT, name, return_value=None)
            mock.start()
            self.addCleanup(mock.stop)

    def api(self, endpoint):
        self.seen.append(endpoint)
        if "/pulls?state=closed" in endpoint:
            return self.merged
        if "/git/commits/" in endpoint:
            return {"sha": self.commit_sha, "parents": self.parents}
        if f'/commits/{"c" * 40}/pulls?' in endpoint:
            if self.paginated and endpoint.endswith("page=1"):
                return [self.old] * 100
            return self.associated
        if "/reviews?" in endpoint:
            return self.reviews
        if "/check-runs?" in endpoint:
            return {"check_runs": self.old_checks if f'/commits/{"a" * 40}/' in endpoint else self.direct_checks}
        if "/statuses?" in endpoint:
            return self.statuses
        if f'/compare/{"a" * 40}...{"e" * 40}' in endpoint:
            return self.second_compare
        if f'/compare/{"a" * 40}...{"b" * 40}' in endpoint:
            return self.first_compare
        if "/compare/" in endpoint:
            return {"files": [{"filename": "scripts/source.py", "status": "modified"}], "total_commits": 1}
        raise AssertionError(endpoint)

    def receipt(self, _repo, pr):
        return self.proof if pr["number"] == 252 else None

    def run_audit(self, api=None, receipt=None):
        with patch.object(AUDIT, "api", side_effect=api or self.api), patch.object(
                AUDIT, "receipt", side_effect=receipt or self.receipt), patch.object(
                AUDIT, "enforcement_cutoff", return_value=AUDIT.timestamp("2026-11-01T00:00:00Z")):
            return AUDIT.audit("onesyue", ["yueto-ci"], AUDIT.timestamp("2026-11-02T00:00:00Z"), {},
                               AUDIT.timestamp("2026-11-03T00:00:00Z"))

    def test_actual_delayed_ancestor_closure_retains_old_red_and_missing_receipt(self):
        old, direct = self.run_audit()
        self.assertEqual(old["findings"], [])
        binding = old["indirect_merge"]
        self.assertIn("check_nonpassing_at_merge:policy", binding["historical_findings"])
        self.assertIn("required_merge_receipt_missing", binding["historical_findings"])
        self.assertIsNone(old["receipt"])
        self.assertEqual(binding["direct_pr"], 252)
        self.assertEqual(binding["direct_merged_at"], "2026-11-02T10:00:00Z")
        self.assertEqual(binding["indirect_merged_at"], "2026-11-02T10:00:02Z")
        self.assertEqual(direct["findings"], [])
        self.assertNotIn("indirect_merge", direct)

    def test_direct_red_pending_unknown_and_later_green_cannot_be_borrowed(self):
        check = self.direct_checks[0]
        for checks in ([check | {"conclusion": "failure"}],
                       [check | {"status": "queued", "completed_at": None}],
                       [check | {"started_at": "2026-11-02T11:00:00Z", "completed_at": "2026-11-02T11:01:00Z"}],
                       [check | {"conclusion": "failure"}, check | {"id": 2, "started_at": "2026-11-02T11:00:00Z",
                                                                   "completed_at": "2026-11-02T11:01:00Z"}]):
            with self.subTest(checks=checks):
                self.direct_checks = checks
                with self.assertRaises(ValueError):
                    self.run_audit()

    def test_missing_and_invalid_direct_receipt_block(self):
        self.proof = None
        with self.assertRaises(ValueError):
            self.run_audit()
        def invalid(_repo, pr):
            if pr["number"] == 252:
                raise ValueError("uncommitted or wrong-head receipt")
        with self.assertRaises(ValueError):
            self.run_audit(receipt=invalid)

    def test_actual_direct_red_is_not_reclassified(self):
        self.merged = [self.direct, copy.deepcopy(self.direct) | {"number": 253}]
        self.direct_checks = [self.direct_checks[0] | {"conclusion": "failure"}]
        for row in self.run_audit():
            self.assertIn("check_nonpassing_at_merge:policy", row["findings"])
            self.assertNotIn("indirect_merge", row)

    def test_lone_bad_merge_never_searches_for_green_source(self):
        self.merged = [self.old]
        row, = self.run_audit()
        self.assertIn("check_nonpassing_at_merge:policy", row["findings"])
        self.assertFalse(any("/git/commits/" in e for e in self.seen))

    def test_complete_associated_pr_pagination_is_required(self):
        self.paginated = True
        self.associated = [self.direct]
        self.assertIn("indirect_merge", self.run_audit()[0])
        self.assertTrue(any("/pulls?" in e and e.endswith("page=2") for e in self.seen))
        def unavailable(endpoint):
            if "/pulls?" in endpoint and endpoint.endswith("page=2"):
                raise ValueError("API unavailable")
            return self.api(endpoint)
        with self.assertRaises(ValueError):
            self.run_audit(api=unavailable)

    def test_missing_duplicate_or_wrong_merge_direct_pr_is_incomplete(self):
        for associated in ([], [self.direct, copy.deepcopy(self.direct) | {"number": 254}],
                           [self.direct | {"merge_commit_sha": "f" * 40}], [None]):
            with self.subTest(associated=associated):
                self.associated = associated
                with self.assertRaises(ValueError):
                    self.run_audit()

    def test_only_exact_normal_two_parent_merge_is_supported(self):
        for parents in ([], self.parents[:1], self.parents * 2, [{"sha": "bad"}, self.parents[1]],
                        [self.parents[0], self.parents[0]]):
            with self.subTest(parents=parents):
                self.parents = parents
                with self.assertRaises(ValueError):
                    self.run_audit()

    def test_commit_identity_and_target_and_time_must_match(self):
        original = copy.deepcopy(self.direct)
        for key, value in (("base", original["base"] | {"ref": "other"}),
                           ("base", original["base"] | {"repo": {"full_name": "other/repo"}}),
                           ("merged_at", "2026-11-02T10:00:03Z"), ("merged_at", "invalid"),
                           ("state", "open")):
            with self.subTest(key=key, value=value):
                self.direct.clear()
                self.direct.update(copy.deepcopy(original) | {key: value})
                with self.assertRaises(ValueError):
                    self.run_audit()
        self.direct.clear()
        self.direct.update(original)
        self.commit_sha = "f" * 40
        with self.assertRaises(ValueError):
            self.run_audit()

    def test_strict_new_ancestry_required_with_complete_metadata(self):
        original_second, original_first = copy.deepcopy(self.second_compare), copy.deepcopy(self.first_compare)
        cases = [("second_compare", original_second | {"status": "identical", "ahead_by": 0, "total_commits": 0}),
                 ("second_compare", original_second | {"merge_base_commit": {"sha": "f" * 40}}),
                 ("second_compare", original_second | {"total_commits": True}),
                 ("second_compare", original_second | {"base_commit": {"sha": "b" * 40}}),
                 ("first_compare", original_second),
                 ("first_compare", original_first | {"behind_by": 0}),
                 ("first_compare", original_first | {"ahead_by": True}),
                 ("first_compare", original_first | {"merge_base_commit": {"sha": "bad"}})]
        for name, value in cases:
            with self.subTest(name=name, value=value):
                self.second_compare, self.first_compare = original_second, original_first
                setattr(self, name, value)
                with self.assertRaises(ValueError):
                    self.run_audit()

    def test_evidence_only_direct_does_not_certify_source_ancestor(self):
        original = AUDIT.merged_row
        def row(*args):
            result = original(*args)
            if result["pr"] == 252:
                result["evidence_only"] = True
            return result
        with patch.object(AUDIT, "merged_row", side_effect=row):
            with self.assertRaises(ValueError):
                self.run_audit()


    def test_text_output_distinguishes_indirect_from_old_head_success(self):
        rows = self.run_audit()
        output = io.StringIO()
        with patch.object(AUDIT, "audit", return_value=rows), patch.object(
                AUDIT, "baseline", return_value=(AUDIT.timestamp("2026-11-01T00:00:00Z"), {})), patch.object(
                AUDIT, "exceptions", return_value={}), patch("sys.argv", ["audit", "--repos", "yueto-ci"]), contextlib.redirect_stdout(output):
            self.assertEqual(AUDIT.main(), 0)
        self.assertIn("INDIRECT ", output.getvalue())
        self.assertIn("historical old-head findings (not passed):", output.getvalue())
        self.assertIn("check_nonpassing_at_merge:policy", output.getvalue())

    def test_premerge_still_checks_the_live_failed_head(self):
        candidate = self.old | {"state": "open", "merged_at": None}
        def live(endpoint):
            if endpoint.endswith("/pulls/248"):
                return candidate
            return self.api(endpoint)
        with patch.object(AUDIT, "api", side_effect=live), patch.object(
                AUDIT, "receipt", return_value=None), patch.object(
                AUDIT, "indirect_merge", side_effect=AssertionError("premerge cannot borrow a source")):
            row = AUDIT.premerge("onesyue", "yueto-ci", 248)
        self.assertIn("check_nonpassing_at_merge:policy", row["findings"])
        self.assertNotIn("indirect_merge", row)


if __name__ == "__main__":
    unittest.main()
