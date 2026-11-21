"""Repeated workflow timeouts keep one named value and the same rendered budget.

Job-level timeout-minutes cannot read workflow env. Those jobs stay bare
positive integers. Step inputs can read env, so the image-rescan Trivy
action timeout is the env reference. build.yml is not edited.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
JOB_TIMEOUT = re.compile(r"(?m)^    timeout-minutes: ([1-9][0-9]*)$")


def _job_body(text: str, job: str) -> str:
    header = re.search(rf"(?ms)^  {job}:\n(?P<body>.*?)^    steps:\n", text)
    if header is None:
        raise AssertionError(f"{job} job header missing")
    return header.group("body")


def _job_timeout(text: str, job: str) -> str:
    found = JOB_TIMEOUT.search(_job_body(text, job))
    if found is None:
        raise AssertionError(f"{job} timeout-minutes is not a positive integer")
    return found.group(1)


def _env_value(text: str, name: str) -> str:
    found = re.search(rf'(?m)^  {name}: "([1-9][0-9]*)"$', text)
    if found is None:
        raise AssertionError(f"{name} missing from workflow env")
    return found.group(1)


def assert_image_rescan(text: str) -> None:
    if "timeout-minutes: ${{" in text:
        raise AssertionError("job timeout-minutes must stay a bare integer")
    short = _env_value(text, "SHORT_JOB_TIMEOUT_MINUTES")
    if short != "5":
        raise AssertionError("SHORT_JOB_TIMEOUT_MINUTES changed")
    if _job_timeout(text, "plan") != short or _job_timeout(text, "incident") != short:
        raise AssertionError("plan and incident must both equal SHORT_JOB_TIMEOUT_MINUTES")
    if _job_timeout(text, "scan") != "30":
        raise AssertionError("scan job timeout changed")
    if not re.search(r"(?m)^  TRIVY_ACTION_TIMEOUT: 15m$", text):
        raise AssertionError("TRIVY_ACTION_TIMEOUT missing")
    if text.count("timeout: ${{ env.TRIVY_ACTION_TIMEOUT }}") != 1:
        raise AssertionError("Trivy action timeout must reference TRIVY_ACTION_TIMEOUT once")
    if re.search(r"(?m)^[ ]+timeout: 15m$", text):
        raise AssertionError("raw Trivy timeout literal returned outside the env assignment")


def assert_toolchain(text: str) -> None:
    if "timeout-minutes: ${{" in text:
        raise AssertionError("job timeout-minutes must stay a bare integer")
    minutes = _env_value(text, "TOOLCHAIN_IMAGE_TIMEOUT_MINUTES")
    if minutes != "45":
        raise AssertionError("TOOLCHAIN_IMAGE_TIMEOUT_MINUTES changed")
    if _job_timeout(text, "image") != minutes:
        raise AssertionError("image job timeout must equal TOOLCHAIN_IMAGE_TIMEOUT_MINUTES")
    if len(JOB_TIMEOUT.findall(text)) != 1:
        raise AssertionError("ci-toolchain.yml gained or lost a job timeout")


class WorkflowTimeoutConstants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image_rescan = (WORKFLOWS / "image-rescan.yml").read_text(encoding="utf-8")
        cls.toolchain = (WORKFLOWS / "ci-toolchain.yml").read_text(encoding="utf-8")
        cls.build = (WORKFLOWS / "build.yml").read_text(encoding="utf-8")

    def test_image_rescan_names_the_shared_budgets_without_changing_them(self):
        assert_image_rescan(self.image_rescan)

    def test_toolchain_image_timeout_matches_its_named_env_and_build_yml(self):
        assert_toolchain(self.toolchain)
        self.assertEqual(_job_timeout(self.build, "toolchain-image"),
                         _env_value(self.toolchain, "TOOLCHAIN_IMAGE_TIMEOUT_MINUTES"))

    def test_changing_one_short_job_without_the_env_fails(self):
        mutated = self.image_rescan.replace("    timeout-minutes: 5\n", "    timeout-minutes: 6\n", 1)
        self.assertNotEqual(mutated, self.image_rescan)
        with self.assertRaises(AssertionError):
            assert_image_rescan(mutated)

    def test_restoring_the_raw_trivy_timeout_fails(self):
        mutated = self.image_rescan.replace(
            "timeout: ${{ env.TRIVY_ACTION_TIMEOUT }}", "timeout: 15m", 1)
        self.assertNotEqual(mutated, self.image_rescan)
        with self.assertRaises(AssertionError):
            assert_image_rescan(mutated)

    def test_dropping_the_toolchain_env_assignment_fails(self):
        mutated = re.sub(r'(?m)^  TOOLCHAIN_IMAGE_TIMEOUT_MINUTES: "45"\n', "", self.toolchain, count=1)
        self.assertNotEqual(mutated, self.toolchain)
        with self.assertRaises(AssertionError):
            assert_toolchain(mutated)

    def test_replacing_a_job_timeout_with_an_expression_fails(self):
        mutated = self.toolchain.replace(
            "    timeout-minutes: 45\n",
            "    timeout-minutes: ${{ env.TOOLCHAIN_IMAGE_TIMEOUT_MINUTES }}\n",
            1)
        self.assertNotEqual(mutated, self.toolchain)
        with self.assertRaises(AssertionError):
            assert_toolchain(mutated)


if __name__ == "__main__":
    unittest.main()
