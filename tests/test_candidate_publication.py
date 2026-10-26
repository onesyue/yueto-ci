"""Exercise the actual W12 immutable handoff and its workflow consumers."""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "scripts/candidate-receipt.py"
WORKFLOW = ROOT / ".github/workflows/build.yml"


class CandidateReceiptTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "candidate.json"
        self.env = dict(os.environ, CANDIDATE_SERVICE="yue-node",
                        CANDIDATE_REPOSITORY="onesyue/yue-node",
                        CANDIDATE_SOURCE_SHA="a" * 40, GITHUB_SHA="b" * 40,
                        GITHUB_RUN_ID="123", GITHUB_RUN_ATTEMPT="2",
                        CANDIDATE_DIGEST="sha256:" + "c" * 64)

    def cli(self, operation, env=None):
        return subprocess.run([sys.executable, str(RECEIPT), operation, str(self.path)],
                              env=env or self.env, text=True, capture_output=True, timeout=10)

    def test_actual_producer_consumer_round_trip_and_no_overwrite(self):
        self.assertEqual(self.cli("write").returncode, 0)
        original = self.path.read_bytes()
        self.assertNotEqual(self.cli("write").returncode, 0)
        self.assertEqual(self.path.read_bytes(), original)
        result = self.cli("read")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "digest=" + self.env["CANDIDATE_DIGEST"] + "\n")

    def test_missing_malformed_and_cross_identity_receipts_emit_no_digest(self):
        self.assertNotEqual(self.cli("read").returncode, 0)
        self.assertEqual(self.cli("write").returncode, 0)
        valid = json.loads(self.path.read_text())
        mutations: dict[str, object] = {key: {**valid, key: value} for key, value in {
            "service": "yueboard", "repository": "onesyue/yueboard",
            "source_sha": "d" * 40, "workflow_sha": "e" * 40,
            "run_id": "124", "run_attempt": "1", "schema": 2,
            "image": "ghcr.io/other/yue-node", "digest": "latest",
            "extra": "unreviewed",
        }.items()}
        mutations["no digest"] = {k: v for k, v in valid.items() if k != "digest"}
        mutations["list"] = []
        for name, record in mutations.items():
            with self.subTest(name=name):
                self.path.write_text(json.dumps(record))
                result = self.cli("read")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
        self.path.write_text("{")
        self.assertNotEqual(self.cli("read").returncode, 0)

    def test_missing_identity_and_invalid_digest_cannot_create_receipt(self):
        for key in self.env.keys() & {
            "CANDIDATE_SERVICE", "CANDIDATE_REPOSITORY", "CANDIDATE_SOURCE_SHA",
            "GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "CANDIDATE_DIGEST",
        }:
            with self.subTest(key=key):
                env = {**self.env, key: ""}
                self.assertNotEqual(self.cli("write", env).returncode, 0)
                self.assertFalse(self.path.exists())


class FrozenPlanTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.calls = self.directory / "calls"
        curl = self.directory / "curl"
        curl.write_text('#!/bin/bash\nset -eu\nprintf "%s\\n" "${!#}" >> "$TEST_CALLS"\n'
                        '[ "${TEST_FAIL:-0}" = 0 ] || exit 22\n'
                        'printf \'%s\\n\' "$TEST_RESPONSE"\n')
        curl.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.directory) + os.pathsep + os.environ["PATH"],
                        GH_API_TOKEN="test-token", TEST_CALLS=str(self.calls),
                        TEST_RESPONSE=json.dumps({"sha": "a" * 40}))
        self.plan = {
            "matrix": [{"repo": "onesyue/yue-node", "ref": "feature/frozen", "service": "yue-node"},
                       {"repo": "onesyue/yueboard", "ref": "b" * 40, "service": "yueboard"}],
            "validation_matrix": [{"repo": "onesyue/yue-node", "ref": "feature/frozen", "validation": "node"},
                                  {"repo": "onesyue/yuelink", "ref": "master", "validation": "link"}],
            "has_builds": True,
        }

    def cli(self, plan=None, **env):
        return subprocess.run(["bash", str(ROOT / "scripts/freeze-build-plan.sh")],
                              input=json.dumps(self.plan if plan is None else plan),
                              env={**self.env, **env}, text=True, capture_output=True, timeout=10)

    def test_resolves_once_and_preserves_every_build_and_validation_obligation(self):
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = copy.deepcopy(self.plan)
        expected["matrix"][0]["ref"] = "a" * 40
        for row in expected["validation_matrix"]:
            row["ref"] = "a" * 40
        self.assertEqual(json.loads(result.stdout), expected)
        self.assertEqual(self.calls.read_text().splitlines(), [
            "https://api.github.com/repos/onesyue/yue-node/commits/feature%2Ffrozen",
            "https://api.github.com/repos/onesyue/yuelink/commits/master",
        ])
        self.calls.unlink()
        repeated = self.cli(expected)
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertEqual(json.loads(repeated.stdout), expected)
        self.assertFalse(self.calls.exists())

    def test_failed_lookup_or_invalid_identity_never_outputs_a_plan(self):
        for env in ({"TEST_FAIL": "1"}, {"TEST_RESPONSE": '{}'},
                    {"TEST_RESPONSE": '{"sha":"master"}'}, {"TEST_RESPONSE": '{'}):
            with self.subTest(env=env):
                result = self.cli(**env)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
        for field, value in (("repo", "other/repo"), ("ref", "")):
            plan = copy.deepcopy(self.plan)
            plan["matrix"][0][field] = value
            result = self.cli(plan)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")

    def test_source_only_plan_keeps_build_matrix_empty(self):
        plan = {"matrix": [], "validation_matrix": self.plan["validation_matrix"], "has_builds": False}
        result = self.cli(plan)
        self.assertEqual(result.returncode, 0, result.stderr)
        frozen = json.loads(result.stdout)
        self.assertEqual(frozen["matrix"], [])
        self.assertFalse(frozen["has_builds"])


class PublicationWiringTest(unittest.TestCase):
    def assert_handoff(self, workflow):
        build, publish = workflow.split("\n  build:\n", 1)[1].split("\n  publish:\n", 1)
        self.assertTrue(build.startswith("    needs: [plan]\n"))
        self.assertTrue(publish.startswith("    needs: [build, plan, validate, validation-evidence]\n"))
        self.assertIn("if: needs.plan.outputs.has_builds == 'true'", publish)
        self.assertNotIn("always()", publish)
        self.assertNotIn("continue-on-error", build + publish)
        self.assertNotIn("built-${SOURCE_SHA}", build)
        self.assertNotIn('promotion_tag_args=', build)
        self.assertLess(build.index("Generate signed GitHub build provenance"),
                        build.index("Record verified candidate digest"))
        self.assertIn("CANDIDATE_DIGEST: ${{ steps.build.outputs.digest }}", build)
        for job in (build, publish):
            self.assertIn("CANDIDATE_SOURCE_SHA: ${{ matrix.ref }}", job)
            self.assertIn('[ "$(git rev-parse HEAD)" = "$CANDIDATE_SOURCE_SHA" ]', job)
            self.assertIn("name: candidate-${{ github.run_id }}-${{ github.run_attempt }}-${{ matrix.service }}", job)
        self.assertIn("overwrite: false", build)
        self.assertIn("digest-mismatch: error", publish)
        self.assertIn('candidate-receipt.py read', publish)
        self.assertNotIn("CANDIDATE_TAG", publish)
        self.assertNotIn('imagetools inspect "$CANDIDATE_TAG"', publish)
        self.assertLess(publish.index("Resolve verified candidate digest"),
                        publish.index("Mark this source revision as built"))
        self.assertIn("DIGEST: ${{ steps.build.outputs.digest }}", publish)
        self.assertIn('bash scripts/freeze-build-plan.sh', workflow)
        self.assertLess(workflow.index('bash scripts/freeze-build-plan.sh'),
                        workflow.index('echo "matrix=$matrix"'))

    def test_actual_workflow_consumes_frozen_plan_and_candidate(self):
        self.assert_handoff(WORKFLOW.read_text())

    def test_mutations_cannot_bypass_join_or_immutable_handoff(self):
        workflow = WORKFLOW.read_text()
        for old, new in (
            ("needs: [build, plan, validate, validation-evidence]", "needs: [build, plan]"),
            ("candidate-receipt.py read", "candidate-receipt.py write"),
            ("CANDIDATE_DIGEST: ${{ steps.build.outputs.digest }}", "CANDIDATE_DIGEST: latest"),
            ("digest-mismatch: error", "digest-mismatch: warn"),
            ("bash scripts/freeze-build-plan.sh", "cat"),
        ):
            with self.subTest(old=old), self.assertRaises(AssertionError):
                self.assert_handoff(workflow.replace(old, new))
