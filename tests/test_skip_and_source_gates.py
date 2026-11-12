"""Promote-source admission uses real input fingerprints and fake remote evidence.

Every leg authorizing promotion must refuse when its source or provenance is
unknown. The workflow invokes the gate both before authorization and tag moves.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


GATE = load("promote_gate_under_test", "promote-source-gate.py")
PIN = "@sha256:" + "a" * 64
ENTRY = {"service": "svc", "group": "g", "repo": "onesyue/x", "ref": "master", "validation": "x",
         "context": ".", "dockerfile": "Dockerfile", "platforms": "linux/amd64"}
R_OLD, R_MID, R_HEAD, R_SIDE = "1" * 40, "2" * 40, "3" * 40, "4" * 40
BUILD_TEXT = "jobs:\n  plan:\n    x: 1\n  build:\n    steps: []\n"


def oid(body: bytes) -> str:
    return hashlib.sha1(body).hexdigest()


class FakeAPI:
    """Commits: R_OLD → R_MID (docs only) → R_HEAD (app change); R_SIDE diverges from R_OLD."""

    def __init__(self, fp, dockerfile: str = f"FROM python:3.13{PIN}\nCOPY app/ ./app/\n"):
        self.fp = fp
        self.blobs: dict[str, bytes] = {}
        base = {"Dockerfile": dockerfile.encode(), "app/main.py": b"v1\n", "docs/a.md": b"a\n"}
        self.trees = {
            R_OLD: dict(base),
            R_MID: {**base, "docs/a.md": b"b\n"},
            R_HEAD: {**base, "docs/a.md": b"b\n", "app/main.py": b"v2\n"},
            R_SIDE: {**base, "docs/side.md": b"s\n"},
        }
        self.order = [R_OLD, R_MID, R_HEAD]
        self.head = R_HEAD
        self.broken = False

    def entries(self, rev):
        if self.broken:
            raise self.fp.Unknown("API down")
        out = {}
        for path, body in self.trees[rev].items():
            self.blobs[oid(body)] = body
            out[path] = ("100644", "blob", oid(body))
        return out

    def blob(self, sha):
        return self.blobs[sha]

    def _get(self, path):
        if self.broken:
            raise self.fp.Unknown("API down")
        if path.startswith("branches/"):
            return {"commit": {"sha": self.head}}
        if path.startswith("compare/"):
            older, newer = path.removeprefix("compare/").split("...")
            if older == newer:
                return {"status": "identical"}
            if R_SIDE in (older, newer):
                return {"status": "diverged"}
            return {"status": "ahead" if self.order.index(older) < self.order.index(newer) else "behind"}
        raise AssertionError(path)


class PromoteSourceGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fp = GATE._fingerprint()
        self.api = FakeAPI(self.fp)

    def run_gate(self, source, latest=None, head=R_HEAD):
        self.api.head = head
        return GATE.gate(self.api, self.fp, entry=ENTRY, source=source, head=head, latest=latest)

    def test_source_equal_to_head_is_authorized(self) -> None:
        self.assertIn("== HEAD", self.run_gate(R_HEAD, latest=R_MID))

    def test_head_moved_by_an_input_neutral_commit_still_authorizes(self) -> None:
        # candidate R_OLD, HEAD R_MID (docs only): the old exact-HEAD gate refused this
        self.assertIn("inputs identical to HEAD", self.run_gate(R_OLD, latest=R_OLD, head=R_MID))

    def test_head_moved_by_an_input_change_is_refused(self) -> None:
        with self.assertRaises(GATE.Refused) as ctx:
            self.run_gate(R_MID, latest=R_OLD, head=R_HEAD)
        self.assertIn("app/main.py", str(ctx.exception))

    def test_a_source_off_the_default_branch_is_refused(self) -> None:
        with self.assertRaises(GATE.Refused):
            self.run_gate(R_SIDE, latest=None, head=R_HEAD)

    def test_an_old_candidate_cannot_overwrite_a_newer_promotion(self) -> None:
        """The negative case the design requires: :latest is already newer than the candidate."""
        with self.assertRaises(GATE.Refused) as ctx:
            self.run_gate(R_OLD, latest=R_MID, head=R_MID)
        self.assertIn("older candidate may not overwrite", str(ctx.exception))

    def test_first_promotion_has_no_latest_leg(self) -> None:
        self.assertIn("latest=none", self.run_gate(R_HEAD, latest=None))

    def test_unknown_inputs_never_authorize(self) -> None:
        self.api.trees[R_OLD]["Dockerfile"] = b"FROM python:3.13\nCOPY app/ ./app/\n"  # unpinned base
        self.api.trees[R_MID]["Dockerfile"] = b"FROM python:3.13\nCOPY app/ ./app/\n"
        with self.assertRaises(self.fp.Unknown):
            self.run_gate(R_OLD, latest=None, head=R_MID)

    def test_cli_rejects_malformed_arguments(self) -> None:
        self.assertEqual(GATE.main(["--repo", "evil/x", "--branch", "master", "--service", "svc",
                                    "--source", R_HEAD, "--latest-revision", "none"]), GATE.EXIT_USAGE)
        self.assertEqual(GATE.main(["--repo", "onesyue/x", "--branch", "master", "--service", "svc",
                                    "--source", "abc", "--latest-revision", "none"]), GATE.EXIT_USAGE)


class WorkflowWiringTest(unittest.TestCase):

    def test_promote_step_runs_the_gate_at_authorization_and_before_the_tags_move(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        start = workflow.index("- name: Authorize and promote verified default-branch digest")
        step = workflow[start:]
        self.assertIn("python3 .ci-policy/scripts/promote-source-gate.py", step)
        first = step.index("promote_source_gate || {")
        second = step.index("promote_source_gate || {", first + 1)
        create = step.index('"${promotion_tag_args[@]}"')
        self.assertLess(first, second)
        self.assertLess(second, create)
        self.assertIn("SERVICE_NAME: ${{ matrix.service }}", step)
        # the exact-HEAD equality is gone; the gate owns the decision
        self.assertNotIn('[ "$SOURCE_SHA" != "$default_head" ]', step)
        self.assertNotIn('[ "$SOURCE_SHA" = "$current_head" ]', step)
        # an unreadable :latest refuses, it never reads as "first promotion"
        self.assertIn("could not determine ${IMAGE}:latest state", step)


if __name__ == "__main__":
    unittest.main()
