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


class MergeHygieneAudit(unittest.TestCase):
    def setUp(self):
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
        for rows, expected in (([], 0), ([{"exception": None}], 1), ([{"exception": {"reason": "registered"}}], 0)):
            with patch("sys.argv", ["audit", "--format", "json"]), patch.object(AUDIT, "audit", return_value=rows):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(AUDIT.main(), expected)
                self.assertTrue(json.loads(output.getvalue())["complete"])
        with patch("sys.argv", ["audit", "--format", "json"]), patch.object(AUDIT, "audit", side_effect=ValueError("secret")):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(AUDIT.main(), 2)
            self.assertNotIn("secret", output.getvalue())


class MergeReceipts(unittest.TestCase):
    def setUp(self):
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
                            "sys.argv", ["audit", "--format", "json"]), patch.object(AUDIT, "datetime") as dt:
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
        self.fixture = json.loads((ROOT / "tests/fixtures/merge-hygiene/approved.json").read_text())
        self.pr = self.fixture["pr"]
        self.files = [{"filename": "merge-receipts/yueops/203.json", "status": "added"},
                      {"filename": "reviews/merge-receipts-20261102/review.md", "status": "modified"}]
        self.checks = []
        self.seen = []

    def api(self, endpoint):
        self.seen.append(endpoint)
        if "/files?" in endpoint:
            page = int(endpoint.rsplit("page=", 1)[1])
            return self.files[(page - 1) * 100:page * 100]
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

    def test_files_paginated_and_later_script_disqualifies(self):
        self.files = [self.files[0]] * 100 + [self.files[1]]
        self.assertTrue(self.run_gate("audit")["evidence_only"])
        self.assertIn(f'repos/owner/yueto-ci/pulls/{self.pr["number"]}/files?per_page=100&page=2', self.seen)
        self.files[-1] = {"filename": "scripts/example.py", "status": "added"}
        self.assertIn("required_merge_receipt_missing", self.run_gate("audit")["findings"])

    def test_incomplete_file_evidence(self):
        for files in ([self.files[0]] * 3000,
                      [self.files[0] | {"previous_filename": "scripts/example.py"}]):
            self.files = files
            for mode in ("audit", "premerge"):
                with self.subTest(mode=mode, count=len(files)), self.assertRaises(ValueError):
                    self.run_gate(mode)
        original_api = self.api
        def unavailable(endpoint):
            if "/files?" in endpoint:
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
