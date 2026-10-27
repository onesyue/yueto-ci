"""Fail-fast contract for build.yml: a failed release must stop, not keep running."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"


class FailFastPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.doc = yaml.safe_load(WORKFLOW.read_text())
        self.jobs = self.doc["jobs"]

    def test_every_job_has_a_timeout(self) -> None:
        for name, job in self.jobs.items():
            self.assertIn("timeout-minutes", job, name)

    def test_gating_matrices_fail_fast(self) -> None:
        for name in ("validate", "build"):
            self.assertIs(self.jobs[name]["strategy"]["fail-fast"], True, name)
        # Publication must never be interrupted half-way through a retag.
        self.assertIs(self.jobs["publish"]["strategy"]["fail-fast"], False)

    def test_concurrency_is_per_target_ref_and_never_interrupts(self) -> None:
        conc = self.doc["concurrency"]
        self.assertIn("github.event.inputs.ref", conc["group"])
        self.assertIs(conc["cancel-in-progress"], False)

    def test_abort_jobs_cancel_the_run_with_minimal_privilege(self) -> None:
        for gate in ("validate", "build"):
            job = self.jobs[f"abort-on-{gate}-failure"]
            self.assertEqual(job["if"], "failure()")
            self.assertIn(gate, job["needs"])
            self.assertEqual(job["permissions"], {"actions": "write"})
            self.assertLessEqual(job["timeout-minutes"], 5)
            steps = job["steps"]
            self.assertEqual(len(steps), 1)
            self.assertNotIn("uses", steps[0])
            self.assertIn('gh run cancel "$RUN_ID"', steps[0]["run"])
            self.assertEqual(steps[0]["env"]["RUN_ID"], "${{ github.run_id }}")
        # Nothing downstream may wait on an abort job.
        for name, job in self.jobs.items():
            needs = job.get("needs", [])
            needs = [needs] if isinstance(needs, str) else needs
            self.assertFalse(any(n.startswith("abort-") for n in needs), name)


if __name__ == "__main__":
    unittest.main()
