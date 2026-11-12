"""Promotion CLI rejects stale, diverged or unknown candidates without authorization output.

Native build signature and attestation controls remain in the build-policy and
SBOM suites. Retired poll-only verifier controls are removed with that helper.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
COMMIT = "b" * 40


def load_script(name):
    spec = importlib.util.spec_from_file_location(
        "sign_promote_gaps_" + name.replace("-", "_"),
        ROOT / "scripts" / f"{name}.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GATE = load_script("promote-source-gate")
FP = GATE._fingerprint()


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
