"""Offline HTTP-boundary controls: no gh/network, real disk caches and verdicts."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import call, patch

ROOT = Path(__file__).resolve().parents[1]


def load_audit():
    spec = importlib.util.spec_from_file_location("cached_audit", ROOT / "scripts/merge-hygiene-audit.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def response(body=None, status=200, headers=None, returncode=None):
    headers = {"X-RateLimit-Remaining": "4000"} | (headers or {})
    output = f"HTTP/2.0 {status} Test\r\n"
    output += "".join(f"{key}: {value}\r\n" for key, value in headers.items()) + "\r\n"
    output += json.dumps(body) if body is not None else ""
    return subprocess.CompletedProcess([], int(status >= 400) if returncode is None else returncode,
                                       output, "private transport diagnostic")


class MergeCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"MERGE_HYGIENE_CACHE_DIR": self.tmp.name,
                                     "MERGE_HYGIENE_RATE_FLOOR": "300"})
        env.start()
        self.addCleanup(env.stop)
        self.audit = load_audit()
        self.fixture = json.loads((ROOT / "tests/fixtures/merge-hygiene/approved.json").read_text())
        self.pr = self.fixture["pr"]
        self.cutoff = self.audit.timestamp("2026-11-02T00:00:00Z")
        self.now = self.audit.timestamp("2026-11-03T00:00:00Z")
        self.requests = []
        self.not_modified = 0
        self.anchor = {"number": 71, "state": "open", "merged_at": None,
                       "base": {"repo": {"full_name": "onesyue/yueto-ci"}}}
        self.pulls = {1: [self.pr]}
        self.files = [{"filename": "scripts/tool.py", "status": "modified"}]
        self.conditional = False
        runner = patch.object(self.audit.subprocess, "run", side_effect=self.http)
        runner.start()
        self.addCleanup(runner.stop)
        receipts = patch.object(self.audit, "receipt", return_value=None)
        self.receipt = receipts.start()
        self.addCleanup(receipts.stop)

    def http(self, command, **kwargs):
        self.assertEqual(command[:2], ["gh", "api"])
        self.assertIn("--include", command)
        endpoint = command[2]
        self.requests.append(endpoint)
        if endpoint == "repos/onesyue/yueto-ci/pulls/71":
            body = self.anchor
        elif "/pulls?" in endpoint:
            body = self.pulls[int(endpoint.rsplit("page=", 1)[1])]
        elif "/reviews?" in endpoint:
            body = self.fixture["reviews"]
        elif "/check-runs?" in endpoint:
            body = {"check_runs": self.fixture["checks"]}
        elif "/statuses?" in endpoint:
            body = self.fixture["statuses"]
        elif "/compare/" in endpoint:
            body = {"files": self.files, "total_commits": 1}
        elif endpoint.endswith("/pulls/203"):
            body = self.pr | {"state": "open", "merged_at": None}
        else:
            self.fail("unexpected endpoint: " + endpoint)
        etag = '"' + hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest() + '"'
        if self.conditional and "If-None-Match: " + etag in command:
            self.not_modified += 1
            return response(status=304)
        return response(body, headers={"ETag": etag})

    def audit_rows(self, repo="yueto-ci", registered=None):
        return self.audit.audit("onesyue", [repo], self.cutoff, registered or {}, self.now)

    def test_disk_hit_after_reload_revalidates_evidence_and_reuses_compare(self):
        cold = self.audit.merged_findings("onesyue", "yueto-ci", self.pr)
        self.assertEqual(len(self.requests), 4)
        self.requests.clear()
        self.conditional = True
        reloaded = load_audit()
        self.assertEqual(reloaded.merged_findings("onesyue", "yueto-ci", self.pr), cold)
        self.assertEqual(len(self.requests), 3)
        self.assertEqual(self.not_modified, 3)
        self.assertFalse(any("/compare/" in endpoint for endpoint in self.requests))

    def test_full_rerun_counts_and_unchanged_verdict(self):
        self.fixture["reviews"] = []
        cold = self.audit_rows()
        self.assertEqual(len(self.requests), 6)  # anchor + PR list + four evidence requests
        self.requests.clear()
        self.conditional = True
        self.assertEqual(self.audit_rows(), cold)
        self.assertEqual(len(self.requests), 5)  # discovery and mutable evidence, all conditional
        self.assertEqual(self.not_modified, 5)

    def test_cache_key_separates_owner_repo_pr_merge_and_inputs(self):
        self.audit.merged_findings("onesyue", "yueto-ci", self.pr)
        cases = [("other", "yueto-ci", self.pr), ("onesyue", "yueops", self.pr),
                 ("onesyue", "yueto-ci", self.pr | {"number": 204}),
                 ("onesyue", "yueto-ci", self.pr | {"merge_commit_sha": "e" * 40}),
                 ("onesyue", "yueto-ci", self.pr | {"head": {"sha": "f" * 40}})]
        for owner, repo, pr in cases:
            with self.subTest(owner=owner, repo=repo, pr=pr):
                self.requests.clear()
                self.audit.merged_findings(owner, repo, pr)
                self.assertEqual(len(self.requests), 3 if repo == "yueops" else 4)

    def test_missing_merge_sha_and_corrupt_cache_never_pass_as_a_hit(self):
        for sha in (None, "", "invalid"):
            with self.subTest(sha=sha), self.assertRaises(ValueError):
                self.audit.merged_findings("onesyue", "yueto-ci", self.pr | {"merge_commit_sha": sha})
        self.assertEqual(self.requests, [])
        self.audit.merged_findings("onesyue", "yueto-ci", self.pr)
        path, = Path(self.tmp.name).glob("v*/compare/*.json")
        for content in ("{", "{}", '{"findings": [], "evidence_only": true}'):
            path.write_text(content)
            self.requests.clear()
            self.audit.merged_findings("onesyue", "yueto-ci", self.pr)
            self.assertEqual(len(self.requests), 4)

    def test_incomplete_fetch_and_failed_cache_write_never_create_a_result(self):
        with patch.object(self.audit, "evidence_only", side_effect=ValueError("unavailable")):
            with self.assertRaises(ValueError):
                self.audit.merged_findings("onesyue", "yueto-ci", self.pr)
        self.assertEqual(list(Path(self.tmp.name).glob("v*/compare/*.json")), [])
        with patch.object(self.audit, "write_cache", side_effect=PermissionError):
            with self.assertRaises(OSError):
                self.audit.merged_findings("onesyue", "yueto-ci", self.pr)
        self.assertEqual(list(Path(self.tmp.name).glob("v*/compare/*.json")), [])

    def test_revalidated_verdicts_match_cold_for_clean_missing_red_pending_and_unknown(self):
        original = copy.deepcopy(self.fixture)
        changes = [({}, []), ({"reviews": []}, ["no_approving_review_at_merge"]),
                   ({"checks": [], "statuses": []}, ["no_check_evidence_at_merge"])]
        for change, reason in (({"conclusion": "failure"}, "check_nonpassing_at_merge:policy"),
                               ({"status": "queued"}, "check_pending_at_merge:policy"),
                               ({"started_at": None}, "check_history_unavailable:policy")):
            changes.append(({"checks": [original["checks"][0] | change]}, [reason]))
        for number, (change, expected) in enumerate(changes, start=300):
            self.fixture = original | change
            pr = self.pr | {"number": number}
            with self.subTest(change=change):
                cold = self.audit.merged_findings("onesyue", "yueops", pr)
                self.assertEqual(cold, (expected, False))
                self.requests.clear()
                self.conditional = True
                self.assertEqual(self.audit.merged_findings("onesyue", "yueops", pr), cold)
                self.assertEqual(len(self.requests), 3)

    def test_legacy_green_verdict_cache_is_ignored(self):
        key = ["onesyue", "yueto-ci", self.pr["number"], self.pr["merge_commit_sha"]]
        inputs = {"key": key, "head": self.pr["head"]["sha"], "base": self.pr["base"]["sha"],
                  "merged_at": self.pr["merged_at"], "author": self.pr["user"]["login"]}
        digest = hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()
        legacy = Path(self.tmp.name) / "v1" / "merged" / (digest + ".json")
        self.audit.write_cache(legacy, {"inputs": inputs, "findings": [], "evidence_only": False})
        self.fixture["checks"][0]["conclusion"] = "failure"
        rows = self.audit_rows()
        self.assertIn("check_nonpassing_at_merge:policy", rows[0]["findings"])
        self.assertEqual(len(self.requests), 6)
        cached, = Path(self.tmp.name).glob("v2/compare/*.json")
        self.assertNotIn("findings", json.loads(cached.read_text()))

    def test_local_receipts_exceptions_and_activation_are_rechecked(self):
        self.fixture["reviews"] = []
        self.assertEqual(self.audit_rows()[0]["findings"], ["no_approving_review_at_merge"])
        registered = {("yueto-ci", 203): {"reason": "historical", "approver": "owner"}}
        self.assertEqual(self.audit_rows(registered=registered)[0]["exception"], registered[("yueto-ci", 203)])
        self.anchor["merged_at"] = "2026-11-01T00:00:00Z"
        row, = self.audit_rows(registered=registered)
        self.assertIsNone(row["exception"])
        self.assertIn("required_merge_receipt_missing", row["findings"])
        self.receipt.return_value = {"backfilled": True}
        row, = self.audit_rows()
        self.assertEqual(row["findings"], [])
        self.assertEqual(row["satisfied_by_receipt"], ["no_approving_review_at_merge"])
        self.receipt.side_effect = ValueError("uncommitted receipt")
        with self.assertRaises(ValueError):
            self.audit_rows()

    def test_evidence_only_waiver_still_preserves_red_checks_on_hit(self):
        self.files = [{"filename": "merge-receipts/yueops/203.json", "status": "added"}]
        self.fixture["reviews"] = []
        self.fixture["checks"][0]["conclusion"] = "failure"
        cold = self.audit_rows()
        self.assertTrue(cold[0]["evidence_only"])
        self.assertEqual(cold[0]["findings"], ["check_nonpassing_at_merge:policy"])
        self.assertEqual(self.audit_rows(), cold)

    def test_updated_cutoff_stops_full_page_but_old_recently_updated_merge_does_not(self):
        old = self.pr | {"merged_at": "2026-10-01T00:00:00Z", "updated_at": "2026-10-01T00:00:00Z"}
        self.pulls = {1: [old | {"updated_at": self.pr["updated_at"]}] * 100,
                      2: [self.pr] + [old] * 99}
        self.fixture["reviews"] = []
        rows = self.audit_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(sum("/pulls?" in r for r in self.requests), 2)
        self.assertTrue(all("sort=updated&direction=desc" in r for r in self.requests if "/pulls?" in r))

    def test_activation_extends_cutoff_and_equal_boundary_continues(self):
        self.anchor["merged_at"] = "2026-10-01T00:00:00Z"
        old = self.pr | {"merged_at": "2026-10-01T00:00:00Z", "updated_at": "2026-10-01T00:00:00Z"}
        self.pulls = {1: [old | {"merged_at": None}] * 100, 2: [old]}
        self.fixture["reviews"] = []
        self.assertEqual(len(self.audit_rows()), 1)
        self.assertEqual(sum("/pulls?" in r for r in self.requests), 2)

    def test_open_pr_always_refetches_evidence_and_detects_new_failure(self):
        self.files = [{"filename": "merge-receipts/yueops/203.json", "status": "added"}]
        self.audit.merged_findings("onesyue", "yueto-ci", self.pr)
        self.requests.clear()
        self.fixture["checks"][0]["conclusion"] = "failure"
        row = self.audit.premerge("onesyue", "yueto-ci", 203)
        self.assertIn("check_nonpassing_at_merge:policy", row["findings"])
        self.assertEqual(len(self.requests), 6)

    def test_warm_audit_detects_changed_checks_reviews_and_statuses(self):
        original = copy.deepcopy(self.fixture)
        mutations = [
            ("checks", {"conclusion": "failure"}, "check_nonpassing_at_merge:policy"),
            ("reviews", {"state": "DISMISSED"}, "no_approving_review_at_merge"),
            ("statuses", {"state": "failure"}, "status_nonpassing_at_merge:external-ci"),
        ]
        for field, change, reason in mutations:
            with self.subTest(field=field):
                self.fixture = copy.deepcopy(original)
                self.conditional = True
                self.assertEqual(self.audit_rows(), [])
                self.fixture[field][0].update(change)
                self.requests.clear()
                rows = self.audit_rows()
                self.assertEqual(len(rows), 1)
                self.assertIn(reason, rows[0]["findings"])
                self.assertEqual(len(self.requests), 5)
                self.assertFalse(any("/compare/" in endpoint for endpoint in self.requests))

    def test_warm_remote_failure_never_falls_back_to_green(self):
        self.assertEqual(self.audit_rows(), [])
        self.conditional = True
        for status, remaining in ((401, "4000"), (500, "4000"), (429, "299")):
            for output_format in ("json", "text"):
                def unavailable(command, **kwargs):
                    if "/check-runs?" in command[2]:
                        return response(status=status, headers={"X-RateLimit-Remaining": remaining})
                    return self.http(command, **kwargs)

                with self.subTest(status=status, output_format=output_format), patch.object(
                        self.audit.subprocess, "run", side_effect=unavailable), patch(
                        "sys.argv", ["audit", "--repos", "yueto-ci", "--hours", "240", "--format", output_format]), patch.object(
                        self.audit, "exceptions", return_value={}), patch.object(
                        self.audit, "datetime", wraps=self.audit.datetime) as clock, contextlib.redirect_stdout(io.StringIO()) as output:
                    clock.now.return_value = self.now
                    self.assertEqual(self.audit.main(), 2)
                    self.assertIn("incomplete", output.getvalue())
                    if output_format == "json":
                        self.assertFalse(json.loads(output.getvalue())["complete"])

    def test_http_304_reuses_body_and_200_replaces_etag(self):
        endpoint = "repos/onesyue/yueops/pulls?state=closed&per_page=100&page=1"
        responses = [response([1], headers={"ETag": 'W/"one"'}), response(status=304, returncode=1),
                     response([2], headers={"ETag": '"two"'}), response(status=304)]
        with patch.object(self.audit.subprocess, "run", side_effect=responses) as run:
            self.assertEqual([self.audit.api(endpoint) for _ in responses], [[1], [1], [2], [2]])
        self.assertNotIn("-H", run.call_args_list[0].args[0])
        self.assertIn('If-None-Match: W/"one"', run.call_args_list[1].args[0])
        self.assertIn('If-None-Match: "two"', run.call_args_list[3].args[0])

    def test_304_without_body_and_transport_failures_are_incomplete(self):
        for result in (response(status=304), response(status=401), response(status=404),
                       subprocess.CompletedProcess([], 1, "", "secret")):
            with self.subTest(result=result), patch.object(self.audit.subprocess, "run", return_value=result), patch.object(
                    self.audit.time, "sleep"):
                with self.assertRaises(ValueError):
                    self.audit.api("not-cached")

    def test_truncated_transport_retries_only_until_a_valid_response(self):
        malformed = subprocess.CompletedProcess([], 1, "HTTP/2.0 200 OK\nETag: partial", "secret")
        absent = subprocess.CompletedProcess([], 1, "", "secret")
        with patch.object(self.audit.subprocess, "run", side_effect=[malformed, absent, response([1])]) as run, patch.object(
                self.audit.time, "sleep") as sleep:
            self.assertEqual(self.audit.api("endpoint"), [1])
        self.assertEqual(run.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(1), call(2)])

    def test_exhausted_transport_never_uses_cached_success_or_leaks_diagnostics(self):
        endpoint = "endpoint"
        with patch.object(self.audit.subprocess, "run", return_value=response([1], headers={"ETag": '"old"'})):
            self.audit.api(endpoint)
        old = self.audit.cache_path("http", endpoint).read_bytes()
        absent = subprocess.CompletedProcess([], 1, "", "secret")
        with patch.object(self.audit.subprocess, "run", return_value=absent) as run, patch.object(
                self.audit.time, "sleep") as sleep, contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaisesRegex(ValueError, "invalid GitHub HTTP response"):
                self.audit.api(endpoint)
        self.assertEqual(run.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(1), call(2)])
        self.assertEqual(self.audit.cache_path("http", endpoint).read_bytes(), old)
        self.assertEqual(output.getvalue(), "")

    def test_recovered_transport_still_stops_at_rate_floor(self):
        absent = subprocess.CompletedProcess([], 1, "", "secret")
        low = response([], headers={"X-RateLimit-Remaining": "299"})
        with patch.object(self.audit.subprocess, "run", side_effect=[absent, low]) as run, patch.object(
                self.audit.time, "sleep") as sleep:
            with self.assertRaises(self.audit.RateFloorError):
                self.audit.api("endpoint")
        self.assertEqual(run.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_etags_are_per_page_and_never_served_on_error(self):
        self.audit.api("repos/onesyue/yueops/pulls?state=closed&per_page=100&page=1")
        with patch.object(self.audit.subprocess, "run", return_value=response([], status=404)) as run:
            with self.assertRaises(ValueError):
                self.audit.api("repos/onesyue/yueops/pulls?state=closed&per_page=100&page=2")
            self.assertNotIn("-H", run.call_args.args[0])
            with self.assertRaises(ValueError):
                self.audit.api("repos/onesyue/yueops/pulls?state=closed&per_page=100&page=1")

    def test_floor_exits_two_without_further_calls_or_secrets(self):
        for status in (200, 304, 403, 429):
            for output_format in ("json", "text"):
                with self.subTest(status=status, output_format=output_format), patch.object(
                        self.audit.subprocess, "run", return_value=response(
                            self.anchor, status=status, headers={"x-ratelimit-remaining": "299"})) as run, patch.object(
                        self.audit.time, "sleep") as sleep, patch("sys.argv", ["audit", "--format", output_format]), patch.object(
                        self.audit, "exceptions", return_value={}), contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(self.audit.main(), 2)
                    self.assertEqual(run.call_count, 1)
                    sleep.assert_not_called()
                    self.assertIn("incomplete: rate-floor", output.getvalue())
                    self.assertNotIn("private", output.getvalue())
                    if output_format == "json":
                        self.assertFalse(json.loads(output.getvalue())["complete"])

    def test_floor_equal_is_allowed_and_override_is_honored(self):
        with patch.object(self.audit.subprocess, "run", return_value=response([], headers={"X-RateLimit-Remaining": "300"})):
            self.assertEqual(self.audit.api("endpoint"), [])
            with patch.dict(os.environ, {"MERGE_HYGIENE_RATE_FLOOR": "301"}):
                with self.assertRaises(self.audit.RateFloorError):
                    self.audit.api("endpoint")

    def test_retry_after_reset_and_exponential_backoff_are_bounded(self):
        cases = [(429, {"Retry-After": "7"}, [7, 7]),
                 (403, {}, [60, 120]),
                 (429, {"Retry-After": "Thu, 01 Jan 1970 00:17:00 GMT"}, [20, 20]),
                 (403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1090"}, [91, 120])]
        for status, headers, delays in cases:
            with self.subTest(status=status, headers=headers), patch.dict(os.environ, {"MERGE_HYGIENE_RATE_FLOOR": "0"}), patch.object(
                    self.audit.subprocess, "run", return_value=response(status=status, headers=headers)) as run, patch.object(
                    self.audit.time, "time", return_value=1000), patch.object(self.audit.time, "sleep") as sleep:
                with self.assertRaises(ValueError):
                    self.audit.api("endpoint")
                self.assertEqual(run.call_count, 3)
                self.assertEqual(sleep.call_args_list, [call(delay) for delay in delays])

    def test_retry_success_and_long_reset_exit_without_early_retry(self):
        with patch.object(self.audit.subprocess, "run", side_effect=[response(status=429), response([1])]) as run, patch.object(
                self.audit.time, "sleep") as sleep:
            self.assertEqual(self.audit.api("endpoint"), [1])
            self.assertEqual(run.call_count, 2)
            sleep.assert_called_once_with(60)
        with patch.dict(os.environ, {"MERGE_HYGIENE_RATE_FLOOR": "0"}), patch.object(
                self.audit.subprocess, "run", return_value=response(status=403, headers={
                    "X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "5000"})) as run, patch.object(
                self.audit.time, "time", return_value=1000), patch.object(self.audit.time, "sleep") as sleep:
            with self.assertRaises(ValueError):
                self.audit.api("endpoint")
            self.assertEqual(run.call_count, 1)
            sleep.assert_not_called()
