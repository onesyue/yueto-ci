"""Planner and run-selection helpers for scheduled yueops master validation."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _load(name: str, filename: str):
    path = SCRIPTS / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _version(updated: str, *tags: str) -> dict:
    return {
        "updated_at": updated,
        "metadata": {"container": {"tags": list(tags)}},
    }


class PlanYueopsMasterValidateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.planner = _load("plan_yueops_master_validate", "plan-yueops-master-validate.py")
        cls.find_run = _load("find_dispatched_workflow_run", "find-dispatched-workflow-run.py")
        cls.select_existing = _load(
            "select_existing_yueops_validate_run",
            "select-existing-yueops-validate-run.py",
        )

    def test_newest_promoted_revision_picks_the_latest_marker(self) -> None:
        old = "promoted-" + ("a" * 40) + "-" + ("1" * 64)
        new = "promoted-" + ("b" * 40) + "-" + ("2" * 64)
        latest = self.planner.newest_promoted_revision(
            [
                _version("2026-11-01T00:00:00Z", "latest", old),
                _version("2026-11-26T00:00:00Z", new),
            ]
        )
        self.assertEqual(latest, "b" * 40)

    def test_malformed_promotion_marker_fails_closed(self) -> None:
        with self.assertRaisesRegex(self.planner.PlanError, "malformed promotion marker"):
            self.planner.newest_promoted_revision(
                [_version("2026-11-26T00:00:00Z", "promoted-not-a-sha")]
            )

    def test_missing_promoted_marker_fails_closed(self) -> None:
        with self.assertRaisesRegex(self.planner.PlanError, "no promoted"):
            self.planner.newest_promoted_revision([_version("2026-11-26T00:00:00Z", "latest")])

    def test_plan_wires_source_baseline_and_board(self) -> None:
        planner = self.planner

        def source_sha(token, ref="master"):
            del token, ref
            return "c" * 40

        with mock.patch.object(planner, "resolve_source_sha", source_sha), mock.patch.object(
            planner, "resolve_board_revision", lambda: "d" * 40
        ):
            payload = planner.plan(
                token="t",
                ref="master",
                versions_for=lambda _name: [
                    _version("2026-11-26T00:00:00Z", "promoted-" + ("e" * 40) + "-" + ("3" * 64)),
                ],
            )
        self.assertEqual(
            payload,
            {
                "source": "c" * 40,
                "migration_base": "e" * 40,
                "board_revision": "d" * 40,
            },
        )

    def test_package_read_denial_surfaces_as_a_named_plan_error(self) -> None:
        planner = self.planner
        rescan = _load("plan_rescan_targets_for_master_validate", "plan-rescan-targets.py")
        denied = rescan.PlanError("yueops-web: package versions page 1 returned HTTP 404")

        def versions_for(_name):
            raise denied

        with mock.patch.object(planner, "resolve_source_sha", lambda *a, **k: "c" * 40):
            with self.assertRaisesRegex(planner.PlanError, "yueops-web.*HTTP 404"):
                planner.plan(token="t", ref="master", versions_for=versions_for)

    def test_plan_without_token_fails_closed(self) -> None:
        with self.assertRaisesRegex(self.planner.PlanError, "GH_API_TOKEN"):
            self.planner.plan(token="", ref="master", versions_for=lambda _name: [])

    def test_find_dispatched_workflow_run_returns_the_new_match(self) -> None:
        title = "Build & publish images yueops " + ("c" * 40) + " [nonce:abcd]"
        before = [{"databaseId": 1, "displayTitle": title}]
        after = before + [{"databaseId": 2, "displayTitle": title}]
        self.assertEqual(self.find_run.find_run(title, before, after), 2)
        self.assertIsNone(self.find_run.find_run(title, before, before))

    def test_select_existing_prefers_a_successful_run_for_the_same_sha(self) -> None:
        source = "c" * 40
        other = "d" * 40
        runs = [
            {
                "databaseId": 1,
                "displayTitle": f"Build & publish images yueops {source} [nonce:{'a' * 32}]",
                "status": "completed",
                "conclusion": "failure",
            },
            {
                "databaseId": 2,
                "displayTitle": f"Build & publish images yueops {other} [nonce:{'b' * 32}]",
                "status": "completed",
                "conclusion": "success",
            },
            {
                "databaseId": 3,
                "displayTitle": f"Build & publish images yueops {source} [nonce:{'c' * 32}]",
                "status": "completed",
                "conclusion": "success",
            },
            {
                "databaseId": 4,
                "displayTitle": f"Build & publish images yueops {source} [nonce:{'d' * 32}]",
                "status": "in_progress",
                "conclusion": "",
            },
        ]
        self.assertEqual(self.select_existing.select(source, runs), ("success", 3))
        self.assertEqual(self.select_existing.select(source, runs[:2] + runs[3:]), ("pending", 4))
        self.assertEqual(self.select_existing.select(source, runs[:1]), ("failed", 1))

    def test_select_existing_never_redispatches_a_red_sha(self) -> None:
        source = "e" * 40
        title = f"Build & publish images yueops {source} [nonce:{'a' * 32}]"
        red = [{"databaseId": 7, "displayTitle": title, "status": "completed", "conclusion": "failure"}]
        cancelled = [{"databaseId": 8, "displayTitle": title, "status": "completed", "conclusion": "cancelled"}]
        self.assertEqual(self.select_existing.select(source, red), ("failed", 7))
        self.assertEqual(self.select_existing.select(source, cancelled), ("none", None))
        workflow = (ROOT / ".github/workflows/yueops-master-validate.yml").read_text()
        branch = workflow.split("failed\\ [1-9]*)", 1)[1].split(";;", 1)[0]
        self.assertIn("exit 1", branch)
        self.assertNotIn("gh workflow run", branch)

