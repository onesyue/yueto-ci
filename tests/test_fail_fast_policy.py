"""Publication waits for complete validation; failed candidate work stops early."""

from __future__ import annotations

import itertools
import os
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"
REQUIRED = {"plan", "build", "validate", "validation-evidence"}


def _jobs(text: str) -> dict[str, str]:
    body = text.split("\njobs:\n", 1)[1]
    parts = re.split(r"(?m)^  ([A-Za-z0-9_-]+):\s*$", body)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


class FailFastPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")
        self.jobs = _jobs(self.text)

    def test_every_job_has_a_timeout(self) -> None:
        self.assertTrue(REQUIRED | {"publish", "abort-on-validate-failure", "abort-on-build-failure"} <= self.jobs.keys())
        for name, job in self.jobs.items():
            self.assertRegex(job, r"(?m)^    timeout-minutes: \d+", name)

    def test_gating_matrices_fail_fast(self) -> None:
        # Image candidates stay all-or-nothing. Validate shards do not: one
        # runner's DNS or apt failure must not cancel the others. A test
        # failure still fails that shard immediately.
        self.assertRegex(self.jobs["build"], r"(?m)^      fail-fast: true$")
        self.assertRegex(self.jobs["validate"], r"(?m)^      fail-fast: false$")
        pytest_step = self.jobs["validate"].split(
            "      - name: Execute owned Ops pytest selection\n", 1)[1].split("      - name:", 1)[0]
        self.assertNotIn("continue-on-error", pytest_step)
        # Publication must never be interrupted half-way through a retag.
        self.assertRegex(self.jobs["publish"], r"(?m)^      fail-fast: false$")

    def test_concurrency_is_per_target_ref_and_never_interrupts(self) -> None:
        header = self.text.split("\njobs:\n", 1)[0]
        block = header.split("\nconcurrency:\n", 1)[1].split("\n\n", 1)[0]
        self.assertIn("github.event.inputs.ref", block)
        self.assertIn("cancel-in-progress: false", block)

    def assert_publication_gate(self, text: str) -> set[str]:
        publish = _jobs(text)["publish"]
        match = re.search(r"(?m)^    needs: \[([^\]]+)\]$", publish)
        self.assertIsNotNone(match)
        assert match is not None
        needs = {name.strip() for name in match.group(1).split(",")}
        self.assertEqual(needs, REQUIRED)
        expected = (
            "always() && needs.plan.result == 'success' && needs.validate.result == 'success'"
            " && needs.validation-evidence.result == 'success' && needs.plan.outputs.has_builds == 'true'"
            " && !inputs.validation_only && (needs.build.result == 'success'"
            " || (needs.plan.outputs.resume == 'true' && needs.build.result == 'skipped'))"
        )
        self.assertIn("    if: " + expected + "\n", publish)
        self.assertNotIn("continue-on-error:", publish)
        return needs

    def test_publication_requires_success_for_every_prerequisite(self) -> None:
        self.assert_publication_gate(self.text)
        expression = re.search(r"(?m)^    if: (.+)$", self.jobs['publish']).group(1)
        names = sorted(REQUIRED)
        for states in itertools.product(("success", "failure", "skipped", "cancelled", "in_progress"), repeat=4):
            results = dict(zip(names, states))
            for resume in (False, True):
                actual = expression.replace('always()', 'True').replace('!inputs.validation_only', 'True')
                actual = actual.replace("needs.plan.outputs.has_builds == 'true'", 'True')
                actual = actual.replace("needs.plan.outputs.resume == 'true'", str(resume))
                for name, state in results.items():
                    actual = actual.replace('needs.' + name + '.result', repr(state))
                admitted = eval(actual.replace('&&', ' and ').replace('||', ' or '), {'__builtins__': {}}, {})
                expected = all(results[n] == 'success' for n in REQUIRED - {'build'}) and (results['build'] == 'success' or (resume and results['build'] == 'skipped'))
                with self.subTest(results=results, resume=resume):
                    self.assertEqual(admitted, expected)

    def test_old_async_graph_and_status_overrides_are_rejected(self) -> None:
        original = "needs: [build, plan, validate, validation-evidence]"
        for replacement in (
            "needs: [build, plan]", "needs: [build, plan, validate]",
            "needs: [build, plan, validation-evidence]", "needs: [plan, validate, validation-evidence]",
        ):
            with self.subTest(replacement=replacement), self.assertRaises(AssertionError):
                self.assert_publication_gate(self.text.replace(original, replacement))
        for status in ("always()", "failure()", "!cancelled()"):
            changed = self.text.replace(re.search(r"(?m)^    if: (.+)$", self.jobs["publish"]).group(0), f"    if: {status}")
            with self.subTest(status=status), self.assertRaises(AssertionError):
                self.assert_publication_gate(changed)

    def test_abort_jobs_cancel_only_this_failed_run_with_minimal_privilege(self) -> None:
        for gate in ("validate", "build"):
            job = self.jobs[f"abort-on-{gate}-failure"]
            self.assertIn(f"    needs: [plan, {gate}]\n", job)
            self.assertIn("    if: failure() && !inputs.validation_only\n", job)
            self.assertIn("    permissions:\n      actions: write\n    steps:\n", job)
            self.assertRegex(job, r"(?m)^    timeout-minutes: [1-5]$")
            self.assertEqual(job.count("      - name:"), 1)
            self.assertNotIn("uses:", job)
            self.assertIn("RUN_ID: ${{ github.run_id }}", job)
            self.assertNotIn("gh api", job)
            script = job.split("        run: |\n", 1)[1]
            for status in (0, 7):
                with self.subTest(gate=gate, cancel_status=status):
                    result = subprocess.run(
                        ["bash", "-c", f'gh() {{ printf "GH:%s %s %s\\n" "$1" "$2" "$3"; return {status}; }}\n' + script],
                        capture_output=True, text=True,
                        env=dict(os.environ, RUN_ID="123", GH_REPO="example/repo"),
                    )
                    self.assertEqual(result.returncode, status, result.stderr)
                    self.assertIn("GH:run cancel 123", result.stdout)
        for needs in re.findall(r"(?m)^    needs: (.+)$", self.text):
            self.assertNotIn("abort-", needs)

    def test_async_alert_and_marker_plumbing_is_removed(self) -> None:
        self.assertNotIn("validation-alert", self.jobs)
        self.assertNotIn("validation-recovered", self.jobs)
        self.assertNotIn("tag-written", self.text)
        self.assertNotIn("steps.published.outputs", self.text)
        self.assertNotIn("issues: write", self.text)

    def test_built_marker_still_fails_closed_on_registry_failure(self) -> None:
        step = self.jobs["publish"].split("      - name: Mark this source revision as built\n", 1)[1].split("      - name:", 1)[0]
        script = step.split("        run: |\n", 1)[1]
        script = "\n".join(line[10:] for line in script.splitlines() if line.startswith("          "))
        for status in (0, 7):
            with self.subTest(write_status=status):
                result = subprocess.run(
                    ["bash", "-c", f'docker() {{ printf "DOCKER:%s\\n" "$*"; return {status}; }}\n' + script],
                    capture_output=True, text=True,
                    env=dict(os.environ, IMAGE="example/image", DIGEST="sha256:test", SOURCE_SHA="a" * 40),
                )
                self.assertEqual(result.returncode, status, result.stderr)
                self.assertIn("--tag example/image:built-" + "a" * 40 + " example/image@sha256:test", result.stdout)
                self.assertEqual("marked example/image:" in result.stdout, status == 0)


if __name__ == "__main__":
    unittest.main()
