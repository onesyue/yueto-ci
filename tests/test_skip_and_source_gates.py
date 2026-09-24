"""P3 build skip (design §3 step 8) and the P2 #11 promote source gate (step 9), 2026-09-24.

Both tools are driven with a fake GitHub API (trees, blobs, compare, branches) over the
real input-fingerprint implementation, and a fake ``gh`` for verified provenance.  Every
leg that authorizes a skip or a promotion is broken on its own and must refuse; every
"cannot measure" must build / refuse, never skip / authorize.  The workflow wiring is
pinned too: poll-sources still only requests ``promote=false`` builds, and the promote
step runs the gate twice — once at authorization and once immediately before the tags move.
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
POLL = ROOT / ".github" / "workflows" / "poll-sources.yml"


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


SKIP = load("poll_skip_under_test", "poll-skip-decision.py")
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


class FakeFP:
    """The real fingerprint module with ghcr_latest / workflow_at replaced (no network)."""

    def __init__(self, real, *, latest=(("sha256:" + "d" * 64), R_OLD), old_workflow=BUILD_TEXT,
                 latest_error=False):
        self._real = real
        self._latest, self._old_workflow, self._latest_error = latest, old_workflow, latest_error
        self.Unknown = real.Unknown

    def __getattr__(self, name):
        return getattr(self._real, name)

    def ghcr_latest(self, service, user, password):
        if self._latest_error:
            raise self.Unknown("GHCR down")
        return self._latest

    def workflow_at(self, commit, token):
        return self._old_workflow, {"svc": dict(ENTRY)}


class PollSkipDecisionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.real = SKIP._fingerprint()
        self.tmp = Path(tempfile.mkdtemp(prefix="poll-skip-"))
        self.gh = self.tmp / "gh"
        self.set_gh(ok=True)

    def set_gh(self, *, ok: bool, builders=("b" * 40,)) -> None:
        payload = [{"verificationResult": {"statement": {
            "subject": [{"digest": {"sha256": "d" * 64}}],
            "predicate": {"runDetails": {"builder": {"id": SKIP.BUILDER_PREFIX + "refs/heads/master"}},
                          "buildDefinition": {"resolvedDependencies": [{"digest": {"gitCommit": b}}]}}}}}
            for b in builders]
        # a failed verification that still prints a plausible statement must not count
        self.gh.write_text(f"#!{sys.executable}\nimport sys\n"
                           + "print(" + repr(json.dumps(payload)) + ")\n" + ("" if ok else "sys.exit(1)\n"))
        self.gh.chmod(0o755)

    def decide(self, *, head=R_MID, api=None, fp=None, workflow=BUILD_TEXT):
        fp = fp or FakeFP(self.real)
        api = api or FakeAPI(self.real)
        return SKIP.decide("svc", head, dict(ENTRY), fp=fp, api=api, ci_token="t", ghcr_user="u",
                           ghcr_password="p", gh=str(self.gh), current_workflow=workflow)

    def test_unchanged_inputs_with_verified_provenance_are_skipped(self) -> None:
        verdict, reason = self.decide(head=R_MID)
        self.assertEqual(verdict, "skip", reason)
        self.assertIn("provenance verified", reason)

    def test_changed_inputs_build(self) -> None:
        verdict, reason = self.decide(head=R_HEAD)
        self.assertEqual(verdict, "build")
        self.assertIn("app/main.py", reason)

    def test_unverified_or_ambiguous_provenance_builds(self) -> None:
        self.set_gh(ok=False)
        self.assertEqual(self.decide()[0], "build")
        self.set_gh(ok=True, builders=("b" * 40, "c" * 40))
        self.assertEqual(self.decide()[0], "build")

    def test_recipe_change_builds(self) -> None:
        verdict, reason = self.decide(workflow=BUILD_TEXT.replace("steps: []", "steps: [x]"))
        self.assertEqual(verdict, "build")
        self.assertIn("recipe", reason)

    def test_promoted_revision_not_on_the_branch_builds(self) -> None:
        fp = FakeFP(self.real, latest=("sha256:" + "d" * 64, R_SIDE))
        verdict, reason = self.decide(fp=fp)
        self.assertEqual(verdict, "build")
        self.assertIn("not an ancestor", reason)

    def test_floating_frontend_vetoes_a_skip(self) -> None:
        api = FakeAPI(self.real, dockerfile=f"# syntax=docker/dockerfile:1\nFROM python:3.13{PIN}\nCOPY app/ ./app/\n")
        verdict, reason = self.decide(api=api)
        self.assertEqual(verdict, "build")
        self.assertIn("floating", reason)

    def test_anything_unmeasurable_builds(self) -> None:
        self.assertEqual(self.decide(fp=FakeFP(self.real, latest_error=True))[0], "build")
        api = FakeAPI(self.real)
        api.broken = True
        self.assertEqual(self.decide(api=api)[0], "build")


class WorkflowWiringTest(unittest.TestCase):
    def test_poll_sources_asks_the_decision_and_still_only_requests_builds(self) -> None:
        poll = POLL.read_text(encoding="utf-8")
        code = "\n".join(line for line in poll.splitlines() if not line.lstrip().startswith("#"))
        self.assertIn("python3 scripts/poll-skip-decision.py", code)
        self.assertIn("-f promote=false", code)
        self.assertNotIn("promote=true", code)
        self.assertNotIn("imagetools create", code)
        self.assertIn("attestations: read", poll.split("jobs:", 1)[0])
        # a crashed / malformed decision falls back to building every missing image
        self.assertIn('build=("${missing[@]}")', code)
        self.assertIn("P3 skip decision unavailable", code)
        # skipping never writes a built- marker for the unbuilt HEAD
        self.assertNotIn("built-${sha}\" \"", code)

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
