"""Fail-fast contract for build.yml: a failed release must stop, not keep running.

Standard library only: policy CI runs without third-party YAML parsers.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"


def _jobs(text: str) -> dict[str, str]:
    body = text.split("\njobs:\n", 1)[1]
    parts = re.split(r"(?m)^  ([A-Za-z0-9_-]+):\s*$", body)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


class FailFastPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")
        self.jobs = _jobs(self.text)

    def test_every_job_has_a_timeout(self) -> None:
        self.assertGreaterEqual(len(self.jobs), 8)
        for name, job in self.jobs.items():
            self.assertRegex(job, r"(?m)^    timeout-minutes: \d+", name)

    def test_gating_matrices_fail_fast(self) -> None:
        for name in ("validate", "build"):
            self.assertRegex(self.jobs[name], r"(?m)^      fail-fast: true$", name)
        # Publication must never be interrupted half-way through a retag.
        self.assertRegex(self.jobs["publish"], r"(?m)^      fail-fast: false$")

    def test_concurrency_is_per_target_ref_and_never_interrupts(self) -> None:
        header = self.text.split("\njobs:\n", 1)[0]
        block = header.split("\nconcurrency:\n", 1)[1].split("\n\n", 1)[0]
        self.assertIn("github.event.inputs.ref", block)
        self.assertIn("cancel-in-progress: false", block)

    def test_abort_jobs_cancel_the_run_with_minimal_privilege(self) -> None:
        # B1 (2026-10-30): a red validation no longer cancels the run (that
        # could interrupt publish mid-retag); only a failed build still does.
        self.assertNotIn("abort-on-validate-failure", self.jobs)
        for gate in ("build",):
            job = self.jobs[f"abort-on-{gate}-failure"]
            self.assertIn(f"    needs: [plan, {gate}]\n", job)
            self.assertIn("    if: failure()\n", job)
            self.assertIn("    permissions:\n      actions: write\n    steps:\n", job)
            self.assertRegex(job, r"(?m)^    timeout-minutes: [1-5]$")
            self.assertEqual(job.count("      - name:"), 1)
            self.assertNotIn("uses:", job)
            self.assertIn('gh run cancel "$RUN_ID"', job)
            self.assertIn("RUN_ID: ${{ github.run_id }}", job)
        # Nothing may wait on an abort job.
        for needs in re.findall(r"(?m)^    needs: (.+)$", self.text):
            self.assertNotIn("abort-", needs)
            self.assertNotIn("validation-alert", needs)

    def test_async_validation_alerts_without_blocking_publish(self) -> None:
        job = self.jobs["validation-alert"]
        self.assertIn("    needs: [plan, validate, validation-evidence]\n", job)
        self.assertIn("    if: failure()\n", job)
        self.assertIn("    permissions:\n      issues: write\n    steps:\n", job)
        self.assertNotIn("actions: write", job)
        self.assertNotIn("gh run cancel", job)
        self.assertNotIn("uses:", job)
        self.assertRegex(job, r"(?m)^    timeout-minutes: [1-5]$")
        self.assertTrue(self.jobs["publish"].startswith("\n    needs: [build, plan]\n"))


if __name__ == "__main__":
    unittest.main()
