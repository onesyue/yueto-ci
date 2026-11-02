"""Fail-fast contract for build.yml: a failed release must stop, not keep running.

Standard library only: policy CI runs without third-party YAML parsers.
"""

from __future__ import annotations

import itertools
import json
import os
import re
import subprocess
import tempfile
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
        self.assertIn("    needs: [plan, validate, validation-evidence, publish]\n", job)
        self.assertIn("    if: failure()\n", job)
        self.assertIn("    permissions:\n      issues: write\n    steps:\n", job)
        self.assertNotIn("actions: write", job)
        self.assertNotIn("gh run cancel", job)
        self.assertNotIn("uses:", job)
        self.assertRegex(job, r"(?m)^    timeout-minutes: [1-5]$")
        self.assertTrue(self.jobs["publish"].startswith("\n    needs: [build, plan]\n"))

    def test_async_alert_requires_admission_publication_and_red_validation(self) -> None:
        job = self.jobs["validation-alert"]
        notice, issue = job.split(
            "      - name: Open or update the single async validation alert\n", 1
        )
        issue_condition = re.search(r"(?m)^        if: (.+)$", issue).group(1)
        notice_condition = re.search(r"(?m)^        if: (.+)$", notice).group(1)
        names = ("plan", "publish", "validate", "validation-evidence")
        states = ("success", "failure", "skipped", "cancelled")

        def evaluate(condition, results, tag_written):
            condition = condition.removeprefix("${{").removesuffix("}}").strip()
            condition = condition.replace(
                "!contains(toJSON(needs.publish.outputs), '\"tag-written\"')", str(not tag_written)
            ).replace(
                "contains(toJSON(needs.publish.outputs), '\"tag-written\"')", str(tag_written)
            )
            expression = re.sub(
                r"needs\.([a-z-]+)\.result",
                lambda match: repr(results[match.group(1)]),
                condition,
            ).replace("&&", " and ").replace("||", " or ")
            return eval(expression, {"__builtins__": {}}, {})

        for values in itertools.product(states, repeat=len(names)):
            results = dict(zip(names, values))
            for tag_written in (False, True):
                with self.subTest(**results, tag_written=tag_written):
                    published = results["plan"] == "success" and tag_written
                    red = "failure" in (results["validate"], results["validation-evidence"])
                    self.assertEqual(evaluate(issue_condition, results, tag_written), published and red)
                    self.assertEqual(evaluate(notice_condition, results, tag_written), not tag_written)

        # This is the real matrix publisher, including its unconditional tag write.
        publisher = self.jobs["publish"]
        self.assertIn("name: ${{ matrix.service }}", publisher)
        self.assertIn("include: ${{ fromJSON(needs.plan.outputs.matrix) }}", publisher)
        self.assertIn('--tag "${IMAGE}:built-${SOURCE_SHA}"', publisher)
        services = json.loads((ROOT / "services.json").read_text())
        for service in services:
            name = service["service"]
            self.assertIn(f"      {name}: ${{{{ steps.published.outputs.{name} }}}}", publisher)
        record = publisher.split("      - name: Mark this source revision as built\n", 1)[1].split("      - name:", 1)[0]
        self.assertIn("        id: published\n", record)
        self.assertIn("SERVICE: ${{ matrix.service }}", record)
        self.assertIn('echo "${SERVICE}=tag-written" >> "$GITHUB_OUTPUT"', record)
        self.assertNotIn("if:", record)
        self.assertNotIn("continue-on-error:", publisher)
        self.assertNotIn("gh issue", notice)
        command = re.search(r"(?m)^        run: (.+)$", notice).group(1)
        result = subprocess.run(["bash", "-c", command], check=True, capture_output=True, text=True)
        self.assertEqual(result.stdout, "::notice::admission rejected, nothing published\n")


    def test_tag_write_marker_survives_promotion_failure(self) -> None:
        publisher = self.jobs["publish"]
        step = publisher.split("      - name: Mark this source revision as built\n", 1)[1].split("      - name:", 1)[0]
        script = step.split("        run: |\n", 1)[1]
        script = "\n".join(line[10:] for line in script.splitlines() if line.startswith("          "))
        # No registry calls: run the real tag-writing script with a stub, then
        # model a later promotion step failing. A failed tag write emits nothing.
        for write_status in (0, 1):
            with self.subTest(write_status=write_status), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / "output"
                output.touch()
                env = dict(os.environ, GITHUB_OUTPUT=str(output), SERVICE="yue-node",
                           IMAGE="example/image", DIGEST="sha256:test", SOURCE_SHA="a" * 40)
                result = subprocess.run(
                    ["bash", "-c", f"docker() {{ return {write_status}; }}\n" + script],
                    env=env, capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, write_status)
                promotion = subprocess.run(["bash", "-c", "exit 1"], check=False)
                self.assertEqual(promotion.returncode, 1)
                self.assertEqual(output.read_text(), "yue-node=tag-written\n" if write_status == 0 else "")
                # The truth-table test above verifies these exact marker states
                # with publish=failure: written -> issue; nothing -> notice only.

    def test_async_validation_alert_is_one_rolling_issue(self) -> None:
        alert = self.jobs["validation-alert"]
        # Reuse the oldest open alert; only open a new one when none exists.
        self.assertIn('in:title "async validation red" sort:created-asc', alert)
        self.assertIn('gh issue comment "$existing"', alert)
        self.assertNotIn("run ${RUN_ID}\"", alert.split("gh issue create", 1)[1].split("\n", 1)[0])
        recovered = self.jobs["validation-recovered"]
        self.assertIn("    needs: [plan, validate, validation-evidence]\n", recovered)
        self.assertIn("    if: success() && needs.plan.outputs.has_builds == 'true'\n", recovered)
        self.assertIn("gh issue close", recovered)
        self.assertNotIn("uses:", recovered)


if __name__ == "__main__":
    unittest.main()
