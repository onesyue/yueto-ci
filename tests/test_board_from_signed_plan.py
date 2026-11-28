"""Ops tests execute the Board commit the sealed admission names, never siblings.lock.

A Board promote must not need a yueto-ci lockstep pin bump: the plan job
computes the Board ref, seals it in the admission, and the test jobs check out
exactly that SHA after verifying the seal and the plan job's digest.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pytest_shards import cli  # noqa: E402

BOARD = "a" * 40
DIGEST = "b" * 64


def admission(**changes):
    value = {"schema": 1, "mode": "sharded", "board_revision": BOARD,
             "admission_sha256": DIGEST}
    value.update(changes)
    return value


class AdmittedBoardRevision(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.object(cli, "envelope", lambda value: value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_returns_the_sealed_board_commit(self) -> None:
        self.assertEqual(cli.admitted_board_revision(admission(), DIGEST), BOARD)
        self.assertEqual(cli.admitted_board_revision(admission(mode="legacy"), DIGEST), BOARD)

    def test_a_digest_the_plan_job_did_not_publish_is_refused(self) -> None:
        for expected in ("c" * 64, "", DIGEST[:-1], None):
            with self.subTest(expected=expected), self.assertRaisesRegex(
                    ValueError, "digest differs from the plan job"):
                cli.admitted_board_revision(admission(), expected)

    def test_no_ops_selection_or_inexact_board_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "no Ops validation"):
            cli.admitted_board_revision(admission(mode="none"), DIGEST)
        for board in ("main", "A" * 40, "a" * 39, None, 7):
            with self.subTest(board=board), self.assertRaisesRegex(ValueError, "exact Board"):
                cli.admitted_board_revision(admission(board_revision=board), DIGEST)

    def test_a_broken_seal_is_refused(self) -> None:
        def bad(_value):
            raise ValueError("admission envelope digest differs")

        with mock.patch.object(cli, "envelope", bad), self.assertRaisesRegex(
                ValueError, "envelope digest differs"):
            cli.admitted_board_revision(admission(), DIGEST)

    def test_real_envelope_rejects_a_tampered_admission(self) -> None:
        # No stub: a Board edit after sealing cannot pass the real digest check.
        mock.patch.stopall()
        tampered = admission(board_revision="c" * 40)
        with self.assertRaisesRegex(ValueError, "admission envelope digest differs"):
            cli.admitted_board_revision(tampered, DIGEST)

    def test_cli_prints_only_the_sha_and_fails_closed(self) -> None:
        import contextlib
        import io
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "admission.json"
            path.write_text(json.dumps(admission()))
            out, err = io.StringIO(), io.StringIO()
            args = type("A", (), {"admission": path, "expect_sha256": DIGEST})
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                self.assertEqual(cli.board_revision_command(args), 0)
            self.assertEqual(out.getvalue(), BOARD + "\n")
            args = type("A", (), {"admission": path, "expect_sha256": "d" * 64})
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                self.assertEqual(cli.board_revision_command(args), 1)
            self.assertEqual(out.getvalue(), "")
            self.assertIn("REJECTED", err.getvalue())


class WorkflowWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.steps = yaml.safe_load(
            (ROOT / ".github/workflows/build.yml").read_text())["jobs"]["validate"]["steps"]

    def named(self, name):
        return next(s for s in self.steps if s.get("name") == name)

    def index(self, name):
        return self.steps.index(self.named(name))

    def test_ops_board_is_the_admitted_sha_and_the_lock_is_yue_node_only(self) -> None:
        resolve = self.named("Resolve the YueBoard commit the signed Ops plan names")
        self.assertEqual(resolve["if"], "matrix.validation == 'yueops'")
        self.assertEqual(resolve["id"], "board")
        self.assertEqual(resolve["env"]["ADMISSION_SHA256"],
                         "${{ needs.plan.outputs.admission_sha256 }}")
        self.assertIn("pytest-shards.py", resolve["run"])
        self.assertIn("board-revision", resolve["run"])
        self.assertIn("ops-admission/ops-admission.json", resolve["run"])
        checkout = self.named("Checkout the YueBoard commit named by the signed Ops plan")
        self.assertEqual(checkout["if"], "matrix.validation == 'yueops'")
        self.assertEqual(checkout["with"]["repository"], "onesyue/yueboard")
        self.assertEqual(checkout["with"]["ref"], "${{ steps.board.outputs.board }}")
        self.assertEqual(checkout["with"]["path"], ".ci-yueboard")
        verify = self.named("Verify YueBoard checkout matches the signed Ops plan")
        self.assertIn("differs from the signed Ops plan", verify["run"])
        locked = self.named("Checkout the locked YueBoard sibling")
        self.assertEqual(locked["if"], "matrix.validation == 'yue-node'")
        self.assertEqual(self.named("Verify YueBoard checkout matches siblings.lock")["if"],
                         "matrix.validation == 'yue-node'")

    def test_admission_is_downloaded_and_resolved_before_the_checkout(self) -> None:
        download = self.named("Download exact Ops admission plan")
        self.assertEqual(download["if"], "matrix.validation == 'yueops'")
        order = [self.index("Download exact Ops admission plan"),
                 self.index("Resolve the YueBoard commit the signed Ops plan names"),
                 self.index("Checkout the YueBoard commit named by the signed Ops plan"),
                 self.index("Verify YueBoard checkout matches the signed Ops plan")]
        self.assertEqual(order, sorted(order))

    def test_no_step_runs_ops_against_the_lock_board(self) -> None:
        for step in self.steps:
            if "steps.siblings.outputs.yueboard" in yaml.safe_dump(step):
                self.assertEqual(step["if"], "matrix.validation == 'yue-node'", step["name"])


if __name__ == "__main__":
    unittest.main()
