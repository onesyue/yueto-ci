"""Sharded pytest steps carry a step budget well under the job budget.

2026-11-26: one hung test (checkin lifespan drain) held each affected
hosted runner for the full 120-minute validate budget. Seven such shards
sat on 7 of the 20 account-wide hosted slots and every queued premerge
waited behind them. The step budget frees the runner within minutes.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "build.yml"
REF = "        timeout-minutes: ${{ fromJSON(env.OPS_PYTEST_STEP_TIMEOUT_MINUTES) }}\n"
STEPS = ("Execute owned Ops pytest selection", "Run service-owned pytest selection")


def assert_step_budget(text: str) -> None:
    found = re.search(r'(?m)^  OPS_PYTEST_STEP_TIMEOUT_MINUTES: "([1-9][0-9]*)"$', text)
    if found is None:
        raise AssertionError("OPS_PYTEST_STEP_TIMEOUT_MINUTES missing from workflow env")
    if not 10 <= int(found.group(1)) < 60:
        raise AssertionError("step budget must stay well under the validate job budget")
    for name in STEPS:
        body = re.search(rf"(?ms)^      - name: {name}\n(?P<body>.*?)(?=^      - name:|\Z)", text)
        if body is None:
            raise AssertionError(f"{name} missing")
        if REF not in body.group("body"):
            raise AssertionError(f"{name} lost its step timeout")


class PytestStepTimeout(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_sharded_pytest_steps_are_bounded(self) -> None:
        assert_step_budget(self.text)

    def test_dropping_a_budget_fails(self) -> None:
        for mutated in (
            self.text.replace(REF, "", 1),
            self.text.replace(REF, "", 2),
            self.text.replace('OPS_PYTEST_STEP_TIMEOUT_MINUTES: "25"', 'OPS_PYTEST_STEP_TIMEOUT_MINUTES: "120"', 1),
        ):
            self.assertNotEqual(mutated, self.text)
            with self.assertRaises(AssertionError):
                assert_step_budget(mutated)


if __name__ == "__main__":
    unittest.main()
