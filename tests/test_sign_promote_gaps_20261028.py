"""Exercise uncovered provenance and promotion rejection paths without credentials.

Coverage audit: test_skip_and_source_gates.py already covers a failed verifier,
ambiguous builders, changed inputs and an old candidate. This file adds payload
identity failures, verifier execution failures and CLI refusal/no-output checks.
The gh boundary is mocked: these tests do not validate cryptography or certificate
expiry themselves. release.yaml signer policy and ship --from-promoted live in
the workspace root repository, outside this builder's test scope.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
DIGEST = "d" * 64
COMMIT = "b" * 40
IMAGE = f"ghcr.io/onesyue/yue-node@sha256:{DIGEST}"
BUILDER = "https://github.com/onesyue/yueto-ci/.github/workflows/build.yml@refs/heads/master"


def load_script(name):
    spec = importlib.util.spec_from_file_location(
        "sign_promote_gaps_" + name.replace("-", "_"),
        ROOT / "scripts" / f"{name}.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SKIP = load_script("poll-skip-decision")
GATE = load_script("promote-source-gate")
FP = SKIP._fingerprint()


def verified_payload(*, builder=BUILDER, digest=DIGEST, commit=COMMIT):
    return [{"verificationResult": {"statement": {
        "subject": [{"name": "ghcr.io/onesyue/yue-node", "digest": {"sha256": digest}}],
        "predicate": {
            "runDetails": {"builder": {"id": builder}},
            "buildDefinition": {"resolvedDependencies": [{"digest": {"gitCommit": commit}}]},
        },
    }}}]


class ProvenanceRejectionGapsTest(unittest.TestCase):
    def verify(self, payload):
        result = subprocess.CompletedProcess([], 0, stdout=json.dumps(payload), stderr="")
        with patch.object(SKIP.subprocess, "run", return_value=result):
            return SKIP.verified_builder(IMAGE, "fixture-gh", FP)

    def test_valid_control_pins_verifier_policy_and_uses_workflow_token(self):
        result = subprocess.CompletedProcess([], 0, stdout=json.dumps(verified_payload()), stderr="")
        with patch.dict(os.environ, {
            "GH_TOKEN": "fixture-source-read-token",
            "GITHUB_TOKEN": "fixture-attestation-read-token",
        }, clear=True), patch.object(SKIP.subprocess, "run", return_value=result) as run:
            self.assertEqual(SKIP.verified_builder(IMAGE, "fixture-gh", FP), COMMIT)
            run.assert_called_once()
            self.assertEqual(run.call_args.args[0], [
                "fixture-gh", "attestation", "verify", f"oci://{IMAGE}",
                "--repo", "onesyue/yueto-ci",
                "--signer-workflow", "github.com/onesyue/yueto-ci/.github/workflows/build.yml",
                "--cert-oidc-issuer", "https://token.actions.githubusercontent.com",
                "--predicate-type", "https://slsa.dev/provenance/v1", "--format", "json",
            ])
            self.assertEqual(run.call_args.kwargs["env"]["GH_TOKEN"], "fixture-attestation-read-token")
            self.assertEqual(os.environ["GH_TOKEN"], "fixture-source-read-token")

    def test_wrong_signer_workflow_or_branch_is_refused(self):
        for builder in (
            BUILDER.replace("onesyue/yueto-ci", "other/yueto-ci"),
            BUILDER.replace("build.yml", "other.yml"),
            BUILDER.replace("refs/heads/master", "refs/pull/42/merge"),
        ):
            with self.subTest(builder=builder), self.assertRaisesRegex(FP.Unknown, "names 0 builder commits"):
                self.verify(verified_payload(builder=builder))

    def test_attestation_for_another_digest_cannot_be_replayed(self):
        with self.assertRaisesRegex(FP.Unknown, "names 0 builder commits"):
            self.verify(verified_payload(digest="e" * 64))

    def test_missing_verified_statement_never_counts_as_provenance(self):
        for payload in ({}, [], [{}], [{"verificationResult": None}]):
            with self.subTest(payload=payload), self.assertRaisesRegex(FP.Unknown, "names 0 builder commits"):
                self.verify(payload)

    def test_non_commit_builder_dependency_is_refused(self):
        for commit in ("", "master", "b" * 39, "B" * 40):
            with self.subTest(commit=commit), self.assertRaisesRegex(FP.Unknown, "names 0 builder commits"):
                self.verify(verified_payload(commit=commit))

    def test_non_json_verifier_output_is_refused(self):
        result = subprocess.CompletedProcess([], 0, stdout="verification unavailable", stderr="")
        with patch.object(SKIP.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(FP.Unknown, "output is not JSON"):
                SKIP.verified_builder(IMAGE, "fixture-gh", FP)

    def test_unavailable_or_timed_out_verifier_is_refused(self):
        for error in (OSError("fixture executable missing"), subprocess.TimeoutExpired("fixture-gh", 180)):
            with self.subTest(error=type(error).__name__):
                with patch.object(SKIP.subprocess, "run", side_effect=error):
                    with self.assertRaisesRegex(FP.Unknown, "verify did not run"):
                        SKIP.verified_builder(IMAGE, "fixture-gh", FP)

    def test_verifier_denial_cannot_publish_a_migration_baseline_or_skip(self):
        # An expired credential/certificate is rejected by gh, not parsed here.
        # Even plausible stdout from that failed command must not authorize reuse.
        result = subprocess.CompletedProcess(
            [], 1, stdout=json.dumps(verified_payload()), stderr="fixture: expired credential",
        )
        fp = Mock(Unknown=FP.Unknown)
        fp.ghcr_latest.return_value = ("sha256:" + DIGEST, "a" * 40)
        api = Mock()
        bases = {}
        with patch.object(SKIP.subprocess, "run", return_value=result):
            verdict, reason = SKIP.decide(
                "yue-node", COMMIT, {"repo": "onesyue/yue-node"}, fp=fp, api=api,
                ci_token="fixture", ghcr_user="fixture", ghcr_password="fixture",
                gh="fixture-gh", current_workflow="", migration_bases=bases,
            )
        self.assertEqual(verdict, "build")
        self.assertIn("does not verify (rc=1)", reason)
        self.assertEqual(bases, {})
        api._get.assert_not_called()
        fp.workflow_at.assert_not_called()


class PromotionCLIRejectionGapsTest(unittest.TestCase):
    def run_cli(self, relation):
        # Source == HEAD avoids input comparison; the latest-to-source leg alone
        # must reject a stale/diverged candidate or an unmeasurable relationship.
        api = Mock()
        api._get.side_effect = [{"commit": {"sha": COMMIT}}, {"status": relation}]
        entry = {"service": "yue-node", "repo": "onesyue/yue-node"}
        fp = SimpleNamespace(
            Unknown=FP.Unknown, load_services=lambda: {"yue-node": entry},
            GitHubTree=Mock(return_value=api),
        )
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(GATE, "_fingerprint", return_value=fp):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                rc = GATE.main([
                    "--repo", "onesyue/yue-node", "--branch", "master", "--service", "yue-node",
                    "--source", COMMIT, "--latest-revision", "c" * 40,
                ])
        self.assertEqual(api._get.call_args.args, (f"compare/{'c' * 40}...{COMMIT}",))
        self.assertEqual(stdout.getvalue(), "", "refusal must not emit promotion authorization")
        return rc, stderr.getvalue()

    def test_replayed_or_diverged_candidate_has_refusal_exit_status(self):
        for relation in ("behind", "diverged"):
            with self.subTest(relation=relation):
                rc, error = self.run_cli(relation)
                self.assertEqual(rc, 1)
                self.assertIn("older candidate may not overwrite", error)

    def test_unknown_latest_ancestry_has_unmeasurable_exit_status(self):
        for relation in (None, "unavailable"):
            with self.subTest(relation=relation):
                rc, error = self.run_cli(relation)
                self.assertEqual(rc, 75)
                self.assertIn("unmeasured never authorizes", error)
