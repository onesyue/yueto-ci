"""Cluster failing pytest ids from fixture logs without calling gh."""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "ci_failure_clusters", ROOT / "scripts/ci-failure-clusters.py")
CLUSTERS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLUSTERS)

LOG = """
validate	step	2026-11-26T00:00:00.0000000Z FAILED tests/test_one.py::test_alpha - AssertionError: assert 1 == 0
validate	step	2026-11-26T00:00:00.0000001Z FAILED tests/test_one.py::test_beta - NameError: name 'MISSING' is not defined
validate	step	2026-11-26T00:00:00.0000002Z PASSED tests/test_one.py::test_ok
"""


class FailureClusterTest(unittest.TestCase):
    def test_node_ids_and_reasons_come_from_the_log(self):
        self.assertEqual(CLUSTERS.ci_check_failures.node_ids(LOG), [
            "tests/test_one.py::test_alpha",
            "tests/test_one.py::test_beta",
        ])
        self.assertEqual(
            CLUSTERS.reason_for(LOG, "tests/test_one.py::test_alpha"),
            "AssertionError: assert 1 == 0",
        )
        self.assertEqual(CLUSTERS.reason_for(LOG, "tests/test_one.py::test_missing"), "")

    def test_secret_reasons_are_not_printed(self):
        text = "FAILED tests/test_one.py::test_alpha - token=should-not-appear\n"
        self.assertEqual(CLUSTERS.reason_for(text, "tests/test_one.py::test_alpha"), "redacted")

    def test_counts_are_per_run_and_rerun_success_is_a_flake(self):
        records = [
            {"run_id": 1, "yueops_sha": "a" * 40, "nodeids": [
                "tests/test_one.py::test_alpha", "tests/test_one.py::test_beta"], "reasons": {}},
            {"run_id": 1, "yueops_sha": "a" * 40, "nodeids": [
                "tests/test_one.py::test_alpha"], "reasons": {}},
            {"run_id": 2, "yueops_sha": "b" * 40, "nodeids": [
                "tests/test_one.py::test_alpha"], "reasons": {}},
        ]
        per_run = {}
        for record in records:
            bucket = per_run.setdefault(record["run_id"], {
                "run_id": record["run_id"], "yueops_sha": record["yueops_sha"],
                "nodeids": [], "reasons": {},
            })
            for nodeid in record["nodeids"]:
                if nodeid not in bucket["nodeids"]:
                    bucket["nodeids"].append(nodeid)
        rows = CLUSTERS.cluster(list(per_run.values()))
        self.assertEqual(rows[0]["id"], "tests/test_one.py::test_alpha")
        self.assertEqual(rows[0]["count"], 2)
        self.assertEqual(CLUSTERS.classify(rows[0], {"a" * 40, "b" * 40}), "flake")
        self.assertEqual(CLUSTERS.classify(rows[0], set()), "real")
        self.assertEqual(CLUSTERS.classify(rows[1], {"a" * 40}), "flake")
        self.assertEqual(CLUSTERS.classify(rows[1], {"c" * 40}), "real")

    def test_only_pytest_steps_are_selected(self):
        jobs = [
            {"conclusion": "failure", "name": "validate-yueops-ordinary-000", "steps": [
                {"name": "Execute owned Ops pytest selection", "conclusion": "failure"}]},
            {"conclusion": "failure", "name": "validate-yueops-ordinary-001", "steps": [
                {"name": "Validate native-node cross-repository contract", "conclusion": "failure"}]},
            {"conclusion": "success", "name": "select-yue-bot", "steps": [
                {"name": "Run service-owned pytest selection", "conclusion": "success"}]},
        ]
        selected = CLUSTERS.failed_pytest_jobs(jobs)
        self.assertEqual([job["name"] for job in selected], ["validate-yueops-ordinary-000"])

    def test_yueops_sha_comes_from_the_dispatch_title(self):
        title = "Build & publish images yueops " + "ab" * 20 + " [nonce:ec27d9f13cba4664bc1a1bcc006d41b4]"
        self.assertEqual(CLUSTERS.yueops_sha(title), "ab" * 20)
        self.assertEqual(CLUSTERS.yueops_sha("Build & publish images yueboard " + "cd" * 20), "")
