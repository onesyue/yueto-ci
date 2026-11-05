import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("hygiene", ROOT / "scripts/merge-hygiene-audit.py")
AUDIT = importlib.util.module_from_spec(spec)
spec.loader.exec_module(AUDIT)


def fresh_remote_evidence(test):
    # These verdict controls mutate evidence under the same fixture SHA.
    # Disk cache/restart behavior has its own suite in test_merge_hygiene_cache.
    for name in ("read_cache", "write_cache"):
        mock = patch.object(AUDIT, name, return_value=None)
        mock.start()
        test.addCleanup(mock.stop)


class MergeHygieneAudit(unittest.TestCase):
    def setUp(self):
        fresh_remote_evidence(self)
        activation = patch.object(AUDIT, "enforcement_cutoff", return_value=None)
        activation.start()
        self.addCleanup(activation.stop)
        self.fixture = json.loads((ROOT / "tests/fixtures/merge-hygiene/approved.json").read_text())

    def findings(self):
        return AUDIT.findings(**self.fixture)

    def test_clean(self):
        self.assertEqual(self.findings(), [])

    def test_no_late_self_bot_or_dismissed_approval(self):
        for change in ({"submitted_at": "2026-11-02T11:00:00Z"}, {"state": "DISMISSED"},
                       {"user": {"login": "author"}}, {"user": {"login": "bot", "type": "Bot"}}):
            with self.subTest(change=change):
                original = self.fixture["reviews"][0]
                self.fixture["reviews"] = [original | change]
                self.assertIn("no_approving_review_at_merge", self.findings())
                self.fixture["reviews"] = [original]
        self.fixture["reviews"].append(self.fixture["reviews"][0] | {
            "id": 2, "state": "CHANGES_REQUESTED", "submitted_at": "2026-11-02T09:45:00Z"})
        self.assertIn("no_approving_review_at_merge", self.findings())

    def test_failing_pending_and_late_success_checks(self):
        check = self.fixture["checks"][0]
        for change, expected in (({"conclusion": "failure"}, "nonpassing"),
                                 ({"conclusion": "cancelled"}, "nonpassing"),
                                 ({"status": "queued", "completed_at": None}, "pending"),
                                 ({"completed_at": "2026-11-02T11:00:00Z"}, "pending")):
            with self.subTest(change=change):
                self.fixture["checks"] = [check | change]
                self.assertIn(f"check_{expected}_at_merge:policy", self.findings())

    def test_postmerge_rerun_does_not_hide_failure(self):
        check = self.fixture["checks"][0]
        self.fixture["checks"] = [check | {"conclusion": "failure"}, check | {
            "id": 2, "started_at": "2026-11-02T11:00:00Z", "completed_at": "2026-11-02T11:30:00Z"}]
        self.assertIn("check_nonpassing_at_merge:policy", self.findings())
        self.fixture["checks"][1].update(started_at="2026-11-02T09:40:00Z",
                                          completed_at="2026-11-02T09:50:00Z")
        self.assertEqual(self.findings(), [])

    def test_independent_suites_with_shared_name_preserve_failure(self):
        check = self.fixture["checks"][0]
        failed = check | {"conclusion": "failure"}
        success = check | {"id": 2, "check_suite": {"id": 20},
                           "started_at": "2026-11-02T09:40:00Z"}
        for checks in ([failed, success], [success, failed]):
            self.fixture["checks"] = checks
            self.assertIn("check_nonpassing_at_merge:policy", self.findings())

    def test_missing_suite_identity_cannot_supersede_failure(self):
        check = self.fixture["checks"][0]
        check.pop("check_suite")
        self.fixture["checks"] = [check | {"conclusion": "failure"}, check | {
            "id": 2, "started_at": "2026-11-02T09:40:00Z"}]
        self.assertIn("check_nonpassing_at_merge:policy", self.findings())

    def test_queued_rerun_before_merge_with_postmerge_start(self):
        check = self.fixture["checks"][0]
        for started in (None, "2026-11-02T10:10:00Z"):
            with self.subTest(started=started):
                self.fixture["checks"] = [check, check | {
                    "id": 2, "created_at": "2026-11-02T09:50:00Z",
                    "started_at": started, "completed_at": "2026-11-02T10:20:00Z"}]
                self.assertIn("check_pending_at_merge:policy", self.findings())

    def test_rest_rerun_without_creation_time_cannot_certify_old_success(self):
        check = self.fixture["checks"][0]
        for started in (None, "2026-11-02T10:10:00Z"):
            with self.subTest(started=started):
                self.fixture["checks"] = [check, check | {
                    "id": 2, "started_at": started,
                    "completed_at": "2026-11-02T10:20:00Z"}]
                self.assertIn("check_history_unavailable:policy", self.findings())

    def test_proven_postmerge_creation_preserves_premerge_success(self):
        check = self.fixture["checks"][0]
        self.fixture["checks"] = [check, check | {
            "id": 2, "created_at": "2026-11-02T10:05:00Z",
            "started_at": "2026-11-02T10:10:00Z",
            "completed_at": "2026-11-02T10:20:00Z"}]
        self.assertEqual(self.findings(), [])

    def test_status_history_uses_merge_time_not_current_combined_status(self):
        status = self.fixture["statuses"][0]
        for state in ("pending", "failure", "error"):
            self.fixture["statuses"] = [status | {"state": state}, status | {
                "id": 2, "created_at": "2026-11-02T11:00:00Z"}]
            self.assertIn("status_nonpassing_at_merge:external-ci", self.findings())

    def test_missing_history_fails_closed(self):
        self.fixture.update(checks=[], statuses=[])
        self.assertIn("no_check_evidence_at_merge", self.findings())

    def test_overwritten_rerun_is_unknown_even_with_green_status(self):
        self.fixture["checks"][0].update(started_at="2026-11-02T11:00:00Z",
                                          completed_at="2026-11-02T11:30:00Z")
        self.assertIn("check_history_unavailable:policy", self.findings())

    def test_exception_requires_reason_approver_and_exact_pr(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "exceptions.json"
            entry = {"repo": "yueops", "pr": 203, "reason": "incident recovery", "approver": "operator"}
            path.write_text(json.dumps({"schema": 1, "exceptions": [entry]}))
            self.assertEqual(AUDIT.exceptions(path), {("yueops", 203): entry})
            for bad in (entry | {"reason": " "}, entry | {"approver": ""}, entry | {"pr": "*"}):
                path.write_text(json.dumps({"schema": 1, "exceptions": [bad]}))
                with self.assertRaises(ValueError):
                    AUDIT.exceptions(path)

    def test_pagination_and_head_sha_endpoints(self):
        fixture = self.fixture
        pr = fixture["pr"]
        seen = []
        def api(endpoint):
            seen.append(endpoint)
            if "/pulls?" in endpoint:
                return [pr | {"merged_at": None}] * 100 if endpoint.endswith("&page=1") else [pr]
            if "/reviews?" in endpoint:
                return []
            if "/check-runs?" in endpoint:
                return {"check_runs": fixture["checks"]}
            return fixture["statuses"]
        with patch.object(AUDIT, "api", side_effect=api):
            rows = AUDIT.audit("onesyue", ["yueops"], AUDIT.timestamp("2026-11-02T00:00:00Z"), {},
                               AUDIT.timestamp("2026-11-03T00:00:00Z"))
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["exception"])
        self.assertTrue(any("filter=all" in url and pr["head"]["sha"] in url for url in seen))
        self.assertTrue(any("page=2" in url for url in seen))

    def test_exit_codes_and_machine_output(self):
        import contextlib
        import io
        row = {"repo": "yueops", "pr": 203, "head": self.fixture["pr"]["head"]["sha"],
               "merged_at": self.fixture["pr"]["merged_at"],
               "findings": ["no_approving_review_at_merge"], "exception": None}
        for rows, expected in (([], 0), ([row], 1), ([row | {"exception": {"reason": "registered"}}], 0)):
            with patch("sys.argv", ["audit", "--format", "json"]), patch.object(AUDIT, "audit", return_value=rows):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(AUDIT.main(), expected)
                self.assertTrue(json.loads(output.getvalue())["complete"])
        with patch("sys.argv", ["audit", "--format", "json"]), patch.object(AUDIT, "audit", side_effect=ValueError("secret")):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(AUDIT.main(), 2)
            self.assertNotIn("secret", output.getvalue())


class AcceptedHistory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "accepted-history-20261103.json"
        self.entry = {"repo": "yueops", "pr": 203, "head": "a" * 40,
                      "findings": ["no_approving_review_at_merge", "required_merge_receipt_missing"],
                      "reason": "Frozen historical evidence accepted by coordinator"}
        self.value = {"schema": 1, "frozen_at": "2026-11-03T02:00:00Z",
                      "approver": "coordinator (owner mandate t454u) 2026-11-03",
                      "entries": [self.entry]}
        self.write_baseline()
        self.row = {"repo": "yueops", "pr": 203, "head": "a" * 40,
                    "url": "https://github.com/onesyue/yueops/pull/203",
                    "merged_at": "2026-11-02T10:00:00Z", "findings": self.entry["findings"][:],
                    "exception": None, "receipt": None, "satisfied_by_receipt": []}
        self.candidate = self.row | {"pr": 204, "merged_at": None, "findings": [],
                                     "url": "https://github.com/onesyue/yueops/pull/204"}

    def write_baseline(self, contents=None):
        self.path.write_text(json.dumps(self.value) if contents is None else contents)
        self.enterContext(patch.object(AUDIT, "ACCEPTED_HISTORY_SHA256",
                                       hashlib.sha256(self.path.read_bytes()).hexdigest()))

    def run_cli(self, mode="full", output_format="text", default_path=False):
        import contextlib
        import io
        args = ["audit", "--format", output_format]
        if not default_path:
            args += ["--baseline", str(self.path)]
        if mode == "premerge":
            args += ["--premerge", self.candidate["repo"], str(self.candidate["pr"])]
        with patch("sys.argv", args), patch.object(AUDIT, "audit", return_value=[self.row.copy()]), patch.object(
                AUDIT, "premerge", return_value=self.candidate.copy()), patch.object(
                AUDIT, "exceptions", return_value={}), contextlib.redirect_stdout(io.StringIO()) as output:
            rc = AUDIT.main()
        return rc, output.getvalue()

    def test_matched_entry_is_info_and_passes_in_both_modes(self):
        for remaining in (self.entry["findings"], self.entry["findings"][:1]):
            self.row["findings"] = remaining
            for mode in ("full", "premerge"):
                with self.subTest(mode=mode, remaining=remaining):
                    rc, output = self.run_cli(mode)
                    self.assertEqual(rc, 0)
                    self.assertIn(f'INFO accepted-history {self.row["url"]}: {", ".join(remaining)}', output)
                    self.assertIn(self.entry["reason"], output)
                    self.assertNotIn("UNREGISTERED", output)
                    rc, output = self.run_cli(mode, "json")
                    result = json.loads(output)
                    self.assertEqual(rc, 0)
                    self.assertEqual(result["accepted_history"], 1)
                    self.assertEqual(result["unregistered"], 0)

    def test_head_repo_pr_mismatch_or_extra_finding_is_unregistered(self):
        original = self.row.copy()
        for change in ({"head": "b" * 40}, {"repo": "yueboard"}, {"pr": 205},
                       {"findings": self.entry["findings"] + ["check_nonpassing_at_merge:policy"]}):
            self.row = original | change
            for mode in ("full", "premerge"):
                with self.subTest(mode=mode, change=change):
                    rc, output = self.run_cli(mode)
                    self.assertEqual(rc, 1)
                    self.assertIn(f'UNREGISTERED {self.row["url"]}', output)
                    self.assertNotIn("INFO accepted-history", output)
                    rc, output = self.run_cli(mode, "json")
                    result = json.loads(output)
                    self.assertEqual(rc, 1)
                    self.assertEqual(result["accepted_history"], 0)
                    self.assertEqual(result["unregistered"], 1)

    def test_premerge_findings_cannot_be_covered_by_baseline(self):
        self.candidate["findings"] = self.entry["findings"][:]
        self.value["entries"].append(self.entry | {"pr": self.candidate["pr"]})
        self.write_baseline()
        rc, output = self.run_cli("premerge")
        self.assertEqual(rc, 1)
        self.assertIn("UNREGISTERED " + self.candidate["url"], output)
        self.assertNotIn("INFO accepted-history " + self.candidate["url"], output)
        rc, output = self.run_cli("premerge", "json")
        result = json.loads(output)
        self.assertEqual(rc, 1)
        self.assertEqual(result["accepted_history"], 1)
        self.assertEqual(result["unregistered"], 1)

    def test_default_baseline_path(self):
        with patch.object(AUDIT, "ROOT", self.path.parent):
            self.assertEqual(self.run_cli(default_path=True)[0], 0)

    def test_merge_after_frozen_at_is_unregistered(self):
        for merged_at in ("2026-11-03T02:00:00.000001Z", "2026-11-03T03:00:00Z",
                          "2026-11-03T01:00:01-01:00"):
            self.row["merged_at"] = merged_at
            for mode in ("full", "premerge"):
                with self.subTest(mode=mode, merged_at=merged_at):
                    rc, output = self.run_cli(mode)
                    self.assertEqual(rc, 1)
                    self.assertIn(f'UNREGISTERED {self.row["url"]}', output)
                    self.assertNotIn("INFO accepted-history", output)
                    rc, output = self.run_cli(mode, "json")
                    self.assertEqual(rc, 1)
                    self.assertEqual(json.loads(output)["accepted_history"], 0)

    def test_merge_at_frozen_at_is_accepted(self):
        for merged_at in (self.value["frozen_at"], "2026-11-03T10:00:00+08:00"):
            self.row["merged_at"] = merged_at
            for mode in ("full", "premerge"):
                with self.subTest(mode=mode, merged_at=merged_at):
                    rc, output = self.run_cli(mode, "json")
                    self.assertEqual(rc, 0)
                    self.assertEqual(json.loads(output)["accepted_history"], 1)

    def test_tampered_baseline_bytes_are_incomplete(self):
        original = self.path.read_bytes()
        for contents in (original + b"\n", original.replace(b"2026-11-03T02", b"2026-11-04T02")):
            self.path.write_bytes(contents)
            with self.subTest(contents=contents):
                with self.assertRaises(ValueError):
                    AUDIT.baseline(self.path)
                for default_path in (True, False):
                    for mode in ("full", "premerge"):
                        with patch.object(AUDIT, "ROOT", self.path.parent):
                            rc, output = self.run_cli(mode, "json", default_path=default_path)
                        self.assertEqual(rc, 2)
                        self.assertFalse(json.loads(output)["complete"])

    def test_cli_cannot_override_snapshot_with_another_path(self):
        import subprocess
        import sys
        result = subprocess.run([sys.executable, str(ROOT / "scripts/merge-hygiene-audit.py"),
                                 "--baseline", str(self.path), "--format", "json"],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertFalse(json.loads(result.stdout)["complete"])

    def test_empty_baseline_does_not_accept_history(self):
        self.value["entries"] = []
        self.write_baseline()
        self.assertEqual(AUDIT.baseline(self.path), (AUDIT.timestamp(self.value["frozen_at"]), {}))
        self.assertEqual(self.run_cli()[0], 1)

    def test_invalid_baseline_is_value_error_and_incomplete(self):
        invalid_values = [None, [], {}, self.value | {"extra": True},
                          {k: v for k, v in self.value.items() if k != "approver"}]
        for field, values in (("schema", (True, "1", 2)),
                              ("frozen_at", (None, "", "invalid", "2026-11-03T02:00:00",
                                             "2026-11-03", "20261103T020000Z", "2026-W45-2T02:00:00Z",
                                             "2026-11-03X02:00:00Z", "2026-11-03T02:00:00+00:60",
                                             "2026-11-03T02:00:00+00:00:01", "2026-11-31T02:00:00Z",
                                             "2026-11-03T02:00:00Z\n")),
                              ("approver", (None, " ")), ("entries", (None, {}))):
            invalid_values.extend(self.value | {field: value} for value in values)
        invalid_entries = [None, [], {}, self.entry | {"extra": True},
                           {k: v for k, v in self.entry.items() if k != "reason"}]
        for field, values in (("repo", (None, "unknown")), ("pr", (True, "203", 0, -1)),
                              ("head", (None, "a" * 39, "g" * 40, "a" * 41, "a" * 40 + "\n")),
                              ("findings", (None, "*", [None], [" "], ["duplicate", "duplicate"])),
                              ("reason", (None, " "))):
            invalid_entries.extend(self.entry | {field: value} for value in values)
        invalid_values.extend(self.value | {"entries": [entry]} for entry in invalid_entries)
        invalid_values.append(self.value | {"entries": [self.entry, self.entry.copy()]})
        for value in invalid_values:
            with self.subTest(value=value):
                self.write_baseline(json.dumps(value))
                with self.assertRaises(ValueError):
                    AUDIT.baseline(self.path)
                for mode in ("full", "premerge"):
                    rc, output = self.run_cli(mode, "json")
                    self.assertEqual(rc, 2)
                    self.assertFalse(json.loads(output)["complete"])

    def test_malformed_json_and_duplicate_keys_fail_closed(self):
        contents = json.dumps(self.value)
        for bad in ('{"schema":', contents.replace('"schema": 1', '"schema": 1, "schema": 1'),
                    contents.replace('"pr": 203', '"pr": 203, "pr": 203')):
            with self.subTest(bad=bad):
                self.write_baseline(bad)
                with self.assertRaises(ValueError):
                    AUDIT.baseline(self.path)
                self.assertEqual(self.run_cli()[0], 2)

    def test_missing_baseline_is_incomplete(self):
        self.path.unlink()
        for mode in ("full", "premerge"):
            with self.subTest(mode=mode):
                rc, output = self.run_cli(mode, "json")
                self.assertEqual(rc, 2)
                self.assertFalse(json.loads(output)["complete"])


class FrozenAcceptedHistoryExtension(unittest.TestCase):
    def setUp(self):
        # Independent literals from the 2026-11-04 GitHub evidence, never from
        # the snapshot under test. These merges were not compliant.
        no_checks = ["no_approving_review_at_merge", "no_check_evidence_at_merge",
                     "required_merge_receipt_missing"]
        no_review = ["no_approving_review_at_merge", "required_merge_receipt_missing"]
        historical = [
            ("yueboard", 104, "501911cbe5f69e38bfbebf048c9cbcc548c3998b",
             "2026-11-03T09:29:43Z", no_checks),
            ("yueboard", 106, "7151cf3f2cae8f0d2ae8de2d0011a374ba02a747",
             "2026-11-03T09:22:31Z", no_checks),
            ("yueboard", 107, "3a1a224d43400157ae4dcc722c70874731f440f3",
             "2026-11-03T09:43:21Z", no_checks),
            ("yueboard", 108, "ae53f2f31f6dcce2d338c365edee1a92ffe0d8bd",
             "2026-11-03T10:07:36Z", no_checks),
            ("yueops", 298, "837675c2e2cb89676a386a6034c302e46476a80b",
             "2026-11-03T04:01:07Z", no_checks),
            ("yueto-ci", 179, "bd051adae75a3f924b2cb9faae5b933c1aa66283",
             "2026-11-03T04:18:34Z", no_review),
            ("yueto-ci", 187, "b525bfa5d6c9ca22fc881f2ea5f1b883ab46c216",
             "2026-11-03T04:59:10Z", no_review),
            ("yueto-ci", 188, "112a795ff72d357e3df6278c5a7b63d172107948",
             "2026-11-03T04:51:37Z", no_review),
            ("yueto-ci", 190, "c92237522f1193002cd3f00a8941289b4efbc80c",
             "2026-11-03T14:10:43Z", no_review),
            ("yueto-ci", 191, "f66a1b762072c568ab76f9fd467ae2869fcf5a4e",
             "2026-11-03T05:03:46Z", no_review),
            ("yueto-ci", 212, "2b4db0f396cf234a35f83f1912b8ad6d8cfc9c48",
             "2026-11-03T12:24:14Z", no_review),
            # Owner instruction t658s4004: Codex P2 already fixed by yueboard #144.
            ("yueboard", 142, "2b2acde3ad635c627ddfef68ec51bf29a5c48c42",
             "2026-11-04T19:38:41Z", no_checks),
        ]
        self.rows = [{"repo": repo, "pr": pr, "head": head, "merged_at": merged_at,
                      "url": f"https://github.com/onesyue/{repo}/pull/{pr}",
                      "findings": findings[:], "exception": None, "receipt": None,
                      "satisfied_by_receipt": []}
                     for repo, pr, head, merged_at, findings in historical]

    def run_cli(self, rows):
        import contextlib
        import io
        with patch("sys.argv", ["audit", "--format", "json"]), patch.object(
                AUDIT, "audit", return_value=rows), patch.object(
                AUDIT, "exceptions", return_value={}), contextlib.redirect_stdout(io.StringIO()) as output:
            rc = AUDIT.main()
        return rc, json.loads(output.getvalue())

    def test_frozen_cutoff_matches_latest_verified_merge(self):
        path = ROOT / "accepted-history-20261103.json"
        frozen_at, accepted = AUDIT.baseline(path)
        self.assertEqual(frozen_at, max(AUDIT.timestamp(row["merged_at"]) for row in self.rows))
        self.assertEqual(json.loads(path.read_text())["approver"],
                         "coordinator (owner mandate t497u) 2026-11-03; owner instruction t658s4004 2026-11-05 (yueboard #142)")
        self.assertEqual(len(accepted), 32)
        for row in self.rows:
            with self.subTest(repo=row["repo"], pr=row["pr"]):
                entry = accepted[(row["repo"], row["pr"], row["head"])]
                self.assertEqual(entry["findings"], row["findings"])

    def test_verified_historical_rows_are_accepted(self):
        rc, result = self.run_cli(self.rows)
        self.assertEqual(rc, 0)
        self.assertTrue(result["complete"])
        self.assertEqual(result["accepted_history"], 12)
        self.assertEqual(result["unregistered"], 0)
        for row in result["findings"]:
            with self.subTest(repo=row["repo"], pr=row["pr"]):
                self.assertIn("accepted_history", row)

    def test_identical_findings_after_cutoff_are_rejected(self):
        # Keep the same repo, PR, head and findings; move only the timestamp
        # one second past the independently recorded latest historical merge.
        rows = [row | {"merged_at": "2026-11-04T19:38:42Z"} for row in self.rows]
        rc, result = self.run_cli(rows)
        self.assertEqual(rc, 1)
        self.assertTrue(result["complete"])
        self.assertEqual(result["accepted_history"], 0)
        self.assertEqual(result["unregistered"], 12)
        for row in result["findings"]:
            self.assertNotIn("accepted_history", row)


class MergeReceipts(unittest.TestCase):
    def setUp(self):
        fresh_remote_evidence(self)
        activation = patch.object(AUDIT, "enforcement_cutoff", return_value=None)
        activation.start()
        self.addCleanup(activation.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.patch = patch.object(AUDIT, "ROOT", self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.fixture = json.loads((ROOT / "tests/fixtures/merge-hygiene/approved.json").read_text())
        self.pr = self.fixture["pr"]
        self.sha = self.pr["head"]["sha"]
        (self.root / "review.md").write_text("Independent review: approve")
        self.path = self.root / "merge-receipts/yueops/203.json"
        self.path.parent.mkdir(parents=True)
        self.value = dict(schema=1, repo="yueops", pr=203, head=self.sha, backfilled=True,
            review=dict(tool="codex", verdict="approve", reviewed_head=self.sha,
                        artifact="review.md", reviewer="codex", reviewed_at="2026-11-02T11:00:00Z"),
            parity=dict(result="pass", head=self.sha, command="make test", log_sha256="a" * 64,
                        ran_at="2026-11-02T11:00:00Z", runner="box"))

    def api(self, endpoint):
        if "/pulls?" in endpoint:
            return [self.pr]
        if "/reviews?" in endpoint:
            return []
        if "/check-runs?" in endpoint:
            return {"check_runs": self.fixture["checks"]}
        return self.fixture["statuses"]

    def run_audit(self):
        self.path.write_text(json.dumps(self.value))
        # git show is mocked separately from gh API; receipt bytes must be committed.
        import subprocess
        with patch.object(AUDIT, "api", side_effect=self.api), patch.object(
                AUDIT.subprocess, "run", side_effect=lambda args, **kwargs: subprocess.CompletedProcess(
                    [], 0, (self.root / args[-1].removeprefix("HEAD:")).read_text(), "")):
            return AUDIT.audit("onesyue", ["yueops"], AUDIT.timestamp("2026-11-02T00:00:00Z"),
                               {}, AUDIT.timestamp("2026-11-03T00:00:00Z"))

    def test_accept_exact_committed_receipt(self):
        self.fixture.update(checks=[], statuses=[])
        row, = self.run_audit()
        self.assertEqual(row["findings"], [])
        self.assertEqual(set(row["satisfied_by_receipt"]),
                         {"no_approving_review_at_merge", "no_check_evidence_at_merge"})

    def test_wrong_sha_and_missing_artifact(self):
        for field in ("head", "review", "parity"):
            with self.subTest(field=field):
                if field == "head": self.value[field] = "b" * 40
                else: self.value[field]["reviewed_head" if field == "review" else "head"] = "b" * 40
                with self.assertRaises(ValueError): self.run_audit()
                self.reset_sha()
        (self.root / "review.md").unlink()
        with self.assertRaises(ValueError): self.run_audit()

    def reset_sha(self):
        self.value["head"] = self.value["review"]["reviewed_head"] = self.value["parity"]["head"] = self.sha

    def test_red_pending_and_unknown_not_suppressed(self):
        for change, reason in (({"conclusion": "failure"}, "check_nonpassing_at_merge:policy"),
                               ({"status": "queued"}, "check_pending_at_merge:policy"),
                               ({"started_at": "2026-11-02T11:00:00Z"}, "check_history_unavailable:policy")):
            original = self.fixture["checks"][0]
            self.fixture["checks"] = [original | change]
            self.fixture["statuses"][0]["state"] = "failure"
            row, = self.run_audit()
            self.assertIn(reason, row["findings"])
            self.assertIn("status_nonpassing_at_merge:external-ci", row["findings"])
            self.fixture["checks"] = [original]

    def test_strict_schema_and_times(self):
        import copy
        original = copy.deepcopy(self.value)
        mutations = [lambda v: v.update(extra=1), lambda v: v.update(schema=True),
                     lambda v: v.update(backfilled="true"), lambda v: v.pop("backfilled"),
                     lambda v: v.update(backfilled=False),
                     lambda v: v["review"].update(reviewer="AUTHOR"),
                     lambda v: v["review"].update(reviewer=" AUTHOR "),
                     lambda v: v["review"].update(artifact="../outside.md"),
                     lambda v: v["review"].update(reviewed_at="2026-11-02T11:00:00"),
                     lambda v: v["parity"].update(ran_at="2026-11-03T10:00:01Z"),
                     lambda v: v["parity"].update(log_sha256="bad"),
                     lambda v: v["parity"].update(runner="unknown")]
        for mutate in mutations:
            self.value = copy.deepcopy(original)
            mutate(self.value)
            with self.assertRaises(ValueError): self.run_audit()
        self.value = original
        self.value["parity"]["ran_at"] = "2026-11-03T10:00:00Z"
        self.run_audit()

    def test_malformed_receipt_is_incomplete_even_with_exception(self):
        import contextlib
        import io
        import subprocess
        self.path.write_text('{"schema":')
        with patch.object(AUDIT, "api", side_effect=self.api), patch.object(
                AUDIT.subprocess, "run", return_value=subprocess.CompletedProcess(
                    [], 0, self.path.read_text(), "")), patch.object(AUDIT, "exceptions", return_value={
                        ("yueops", 203): {"reason": "exception"}}), patch(
                            "sys.argv", ["audit", "--format", "json", "--baseline",
                                         str(ROOT / "accepted-history-20261103.json")]), patch.object(AUDIT, "datetime") as dt:
            from datetime import datetime
            dt.fromisoformat.side_effect = datetime.fromisoformat
            dt.now.return_value = AUDIT.timestamp("2026-11-02T12:00:00Z")
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(AUDIT.main(), 2)
            self.assertFalse(json.loads(output.getvalue())["complete"])

    def test_uncommitted_receipt_rejected(self):
        import subprocess
        self.path.write_text(json.dumps(self.value))
        with patch.object(AUDIT.subprocess, "run", return_value=subprocess.CompletedProcess([], 128, "", "")):
            with self.assertRaises(ValueError): AUDIT.receipt("yueops", self.pr)


    def test_actual_git_requires_committed_unchanged_artifact(self):
        import subprocess
        def git(*args):
            subprocess.run(["git", "-C", str(self.root), *args], check=True,
                           capture_output=True)
        git("init", "-q")
        git("config", "user.name", "Test")
        git("config", "user.email", "test@example.invalid")
        git("config", "commit.gpgsign", "false")
        self.path.write_text(json.dumps(self.value))
        git("add", "merge-receipts")
        git("commit", "-qm", "receipt only")
        with self.assertRaises(ValueError): AUDIT.receipt("yueops", self.pr)
        git("add", "review.md")
        git("commit", "-qm", "review artifact")
        self.assertEqual(AUDIT.receipt("yueops", self.pr), self.value)
        (self.root / "review.md").write_text("Uncommitted replacement")
        with self.assertRaises(ValueError): AUDIT.receipt("yueops", self.pr)


class EvidenceOnly(unittest.TestCase):
    def setUp(self):
        fresh_remote_evidence(self)
        self.fixture = json.loads((ROOT / "tests/fixtures/merge-hygiene/approved.json").read_text())
        self.pr = self.fixture["pr"]
        self.pr["base"] = {"sha": "b" * 40}
        self.files = [{"filename": "merge-receipts/yueops/203.json", "status": "added"},
                      {"filename": "reviews/merge-receipts-20261102/review.md", "status": "modified"}]
        self.checks = []
        self.seen = []

    def api(self, endpoint):
        self.seen.append(endpoint)
        if "/compare/" in endpoint:
            self.assertEqual(endpoint, f'repos/owner/yueto-ci/compare/{self.pr["base"]["sha"]}...{self.pr["head"]["sha"]}')
            return {"files": self.files, "total_commits": 1}
        if "/pulls?" in endpoint:
            return [self.pr]
        if endpoint.endswith(f'/pulls/{self.pr["number"]}'):
            return self.pr | {"state": "open", "merged_at": None}
        if "/reviews?" in endpoint or "/statuses?" in endpoint:
            return []
        if "/check-runs?" in endpoint:
            return {"check_runs": self.checks}
        raise AssertionError(endpoint)

    def run_gate(self, mode, repo="yueto-ci"):
        with patch.object(AUDIT, "api", side_effect=self.api), patch.object(
                AUDIT, "receipt", return_value=None), patch.object(
                AUDIT, "enforcement_cutoff", return_value=AUDIT.timestamp("2026-11-01T00:00:00Z")):
            if mode == "premerge":
                return AUDIT.premerge("owner", repo, self.pr["number"])
            row, = AUDIT.audit("owner", [repo], AUDIT.timestamp("2026-11-02T00:00:00Z"),
                               {}, AUDIT.timestamp("2026-11-03T00:00:00Z"))
            return row

    def test_passes_without_receipt(self):
        for mode in ("audit", "premerge"):
            with self.subTest(mode=mode):
                row = self.run_gate(mode)
                self.assertTrue(row["evidence_only"])
                self.assertEqual(row["findings"], [])
                self.assertIsNone(row["receipt"])
                self.assertEqual(row["satisfied_by_receipt"], [])

    def test_mixed_removed_renamed_and_other_repo_require_receipt(self):
        original = self.files[:]
        for extra, repo in (({"filename": "scripts/example.py", "status": "modified"}, "yueto-ci"),
                            ({"filename": "merge-receipts/old.json", "status": "removed"}, "yueto-ci"),
                            ({"filename": "merge-receipts/new.json", "status": "renamed",
                              "previous_filename": "merge-receipts/old.json"}, "yueto-ci"),
                            (None, "yueops")):
            self.files = original + ([extra] if extra else [])
            for mode in ("audit", "premerge"):
                with self.subTest(extra=extra, repo=repo, mode=mode):
                    row = self.run_gate(mode, repo)
                    self.assertFalse(row.get("evidence_only", False))
                    self.assertEqual(set(row["findings"]), {"required_merge_receipt_missing",
                        "no_approving_review_at_merge", "no_check_evidence_at_merge"})

    def test_red_pending_unknown_checks_remain(self):
        for change, reason in (({"conclusion": "failure"}, "check_nonpassing_at_merge:policy"),
                               ({"status": "queued"}, "check_pending_at_merge:policy"),
                               ({"started_at": None}, "check_history_unavailable:policy")):
            self.checks = [self.fixture["checks"][0] | change]
            for mode in ("audit", "premerge"):
                with self.subTest(mode=mode, change=change):
                    self.assertEqual(self.run_gate(mode)["findings"], [reason])

    def test_compare_files_beyond_100_and_later_script_disqualifies(self):
        self.files = [self.files[0]] * 100 + [self.files[1]]
        self.assertTrue(self.run_gate("audit")["evidence_only"])
        self.assertIn(f'repos/owner/yueto-ci/compare/{self.pr["base"]["sha"]}...{self.pr["head"]["sha"]}', self.seen)
        self.assertFalse(any("/files?" in url for url in self.seen))
        self.files[-1] = {"filename": "scripts/example.py", "status": "added"}
        self.assertIn("required_merge_receipt_missing", self.run_gate("audit")["findings"])

    def test_premerge_head_or_base_change_after_compare_fails_closed(self):
        original_api = self.api
        for ref in ("head", "base"):
            self.seen.clear()
            def changed(endpoint):
                result = original_api(endpoint)
                if endpoint.endswith(f'/pulls/{self.pr["number"]}') and any(
                        "/compare/" in url for url in self.seen):
                    return result | {ref: {"sha": "c" * 40}}
                return result
            with self.subTest(ref=ref), patch.object(self, "api", side_effect=changed):
                with self.assertRaisesRegex(ValueError, "head or base changed"):
                    self.run_gate("premerge")

    def test_premerge_a_to_b_to_a_waiver_uses_only_captured_compare(self):
        original_api = self.api
        head_a = self.pr["head"]["sha"]
        head_b = "c" * 40
        evidence_files = self.files[:]
        code_files = [{"filename": "scripts/example.py", "status": "modified"}]
        for captured_files, transient_files, waived in (
                (code_files, evidence_files, False), (evidence_files, code_files, True)):
            self.seen.clear()
            live_head = head_a
            observations = []

            def changed(endpoint):
                nonlocal live_head
                if endpoint.endswith(f'/pulls/{self.pr["number"]}'):
                    observations.append(live_head)
                    result = original_api(endpoint)
                    live_head = head_b  # A -> B after the initial capture.
                    return result
                if "/compare/" in endpoint:
                    self.assertEqual(live_head, head_b)
                    original_api(endpoint)  # Assert exact captured SHA endpoint.
                    live_head = head_a  # B -> A before the refetch.
                    return {"files": captured_files, "total_commits": 1}
                if "/files?" in endpoint:
                    self.seen.append(endpoint)
                    live_head = head_a
                    return transient_files
                return original_api(endpoint)

            with self.subTest(waived=waived), patch.object(self, "api", side_effect=changed):
                row = self.run_gate("premerge")
            self.assertEqual(observations, [head_a, head_a])
            self.assertEqual(row.get("evidence_only", False), waived)
            self.assertEqual("required_merge_receipt_missing" in row["findings"], not waived)
            self.assertFalse(any("/files?" in url for url in self.seen))

    def test_missing_or_inconsistent_compare_fails_closed(self):
        original_api = self.api
        for comparison in (None, [], {}, {"total_commits": 1}, {"files": None, "total_commits": 1},
                           {"files": self.files}, {"files": self.files, "total_commits": 0},
                           {"files": [], "total_commits": 1},
                           {"files": self.files, "total_commits": -1},
                           {"files": self.files, "total_commits": True},
                           {"files": self.files, "total_commits": "1"}):
            def malformed(endpoint):
                return comparison if "/compare/" in endpoint else original_api(endpoint)
            for mode in ("audit", "premerge"):
                with self.subTest(mode=mode, comparison=comparison), patch.object(
                        self, "api", side_effect=malformed), self.assertRaises(ValueError):
                    self.run_gate(mode)

    def test_empty_compare_does_not_qualify(self):
        original_api = self.api
        def empty(endpoint):
            return {"files": [], "total_commits": 0} if "/compare/" in endpoint else original_api(endpoint)
        with patch.object(self, "api", side_effect=empty):
            for mode in ("audit", "premerge"):
                self.assertIn("required_merge_receipt_missing", self.run_gate(mode)["findings"])

    def test_prefix_and_traversal_paths_do_not_qualify(self):
        for path in ("merge-receipts-evil/x.json",
                     "reviews/merge-receipts-x/../../scripts/a.py"):
            self.files = [{"filename": path, "status": "added"}]
            for mode in ("audit", "premerge"):
                with self.subTest(path=path, mode=mode):
                    row = self.run_gate(mode)
                    self.assertFalse(row.get("evidence_only", False))
                    self.assertIn("required_merge_receipt_missing", row["findings"])

    def test_incomplete_file_evidence(self):
        for files in ([self.files[0]] * 300,
                      [self.files[0] | {"previous_filename": "scripts/example.py"}]):
            self.files = files
            for mode in ("audit", "premerge"):
                with self.subTest(mode=mode, count=len(files)), self.assertRaises(ValueError):
                    self.run_gate(mode)
        original_api = self.api
        def unavailable(endpoint):
            if "/compare/" in endpoint:
                raise ValueError("API unavailable")
            return original_api(endpoint)
        with patch.object(self, "api", side_effect=unavailable):
            for mode in ("audit", "premerge"):
                with self.assertRaises(ValueError):
                    self.run_gate(mode)

    def test_clean_text_state_and_exit_code(self):
        import contextlib
        import io
        row = self.run_gate("audit")
        with patch.object(AUDIT, "audit", return_value=[row]), patch.object(
                AUDIT, "exceptions", return_value={}), patch("sys.argv", ["audit"]):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(AUDIT.main(), 0)
        self.assertIn("EVIDENCE-ONLY " + row["url"], output.getvalue())
        self.assertIn("0 unregistered", output.getvalue())
