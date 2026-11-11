"""Exercise the actual W12 immutable handoff and its workflow consumers."""

import copy
import importlib.util
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
        # Publication joins verified candidates with complete validation evidence.
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
        self.assertIn("name: candidate-${{ github.run_id }}-${{ github.run_attempt }}-${{ matrix.service }}", build)
        self.assertIn("candidate-artifact.py select", publish)
        self.assertIn("--family candidate", publish)
        self.assertIn("name: ${{ steps.candidate_artifact.outputs.name }}", publish)
        self.assertIn("CANDIDATE_BUILT_ATTEMPT: ${{ steps.candidate_artifact.outputs.built_attempt }}", publish)
        self.assertIn("actions: read", publish)
        evidence = workflow.split("\n  validation-evidence:\n", 1)[1].split("\n  build:\n", 1)[0]
        self.assertIn("--family admission", evidence)
        self.assertIn("YUETO_HANDOFF_ATTEMPT: ${{ steps.handoff.outputs.built_attempt }}", evidence)
        self.assertIn("ops-admission-${{ github.run_id }}-${{ steps.handoff.outputs.built_attempt }}", evidence)
        self.assertIn("ops-shard-${{ github.run_id }}-${{ steps.handoff.outputs.built_attempt }}-*", evidence)
        self.assertIn("actions: read", evidence)
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
            ("    needs: [build, plan, validate, validation-evidence]\n", "    needs: [build, plan]\n"),
            ("    needs: [build, plan, validate, validation-evidence]\n", "    needs: [build, plan, validate]\n"),
            ("    needs: [build, plan, validate, validation-evidence]\n", "    needs: [plan, validate, validation-evidence]\n"),
            ("candidate-receipt.py read", "candidate-receipt.py write"),
            ("CANDIDATE_DIGEST: ${{ steps.build.outputs.digest }}", "CANDIDATE_DIGEST: latest"),
            ("digest-mismatch: error", "digest-mismatch: warn"),
            ("bash scripts/freeze-build-plan.sh", "cat"),
            ("candidate-artifact.py select", "echo skipped"),
            ("steps.candidate_artifact.outputs.name", "candidate-${{ github.run_id }}-${{ github.run_attempt }}-${{ matrix.service }}"),
            ("steps.handoff.outputs.built_attempt", "github.run_attempt"),
        ):
            with self.subTest(old=old), self.assertRaises(AssertionError):
                self.assert_handoff(workflow.replace(old, new))


class LaterAttemptReceiptTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "candidate.json"
        self.env = dict(os.environ, CANDIDATE_SERVICE="yueops-web",
                        CANDIDATE_REPOSITORY="onesyue/yueops",
                        CANDIDATE_SOURCE_SHA="a" * 40, GITHUB_SHA="b" * 40,
                        GITHUB_RUN_ID="123", GITHUB_RUN_ATTEMPT="2",
                        CANDIDATE_DIGEST="sha256:" + "c" * 64)

    def cli(self, operation, env=None):
        return subprocess.run([sys.executable, str(RECEIPT), operation, str(self.path)],
                              env=env or self.env, text=True, capture_output=True, timeout=10)

    def test_later_attempt_reads_only_the_attempt_that_built_the_candidate(self):
        self.assertEqual(self.cli("write").returncode, 0)
        accepted = {
            "same": {**self.env, "CANDIDATE_BUILT_ATTEMPT": "2"},
            "later": {**self.env, "GITHUB_RUN_ATTEMPT": "4", "CANDIDATE_BUILT_ATTEMPT": "2"},
        }
        refused = {
            "wrong": {**self.env, "GITHUB_RUN_ATTEMPT": "4", "CANDIDATE_BUILT_ATTEMPT": "1"},
            "newer": {**self.env, "CANDIDATE_BUILT_ATTEMPT": "3"},
            "malformed": {**self.env, "CANDIDATE_BUILT_ATTEMPT": "0"},
            "unset": {**self.env, "GITHUB_RUN_ATTEMPT": "4"},
        }
        for name, env in accepted.items():
            with self.subTest(name=name):
                result = self.cli("read", env)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "digest=" + self.env["CANDIDATE_DIGEST"] + "\n")
        for name, env in refused.items():
            with self.subTest(name=name):
                result = self.cli("read", env)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")


class CandidateArtifactTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)

    def cli(self, payload, *args):
        path = Path(self.temporary.name) / "artifacts.json"
        path.write_text(json.dumps(payload))
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts/candidate-artifact.py"), "select",
             "--artifacts", str(path), *args],
            text=True, capture_output=True, timeout=10)

    def test_resume_reads_the_attempt_that_stored_the_artifact(self):
        artifacts = [
            {"name": "candidate-9-1-yueops-web", "expired": False},
            {"name": "candidate-9-2-yueops-web", "expired": False},
            {"name": "candidate-9-1-yue-bot", "expired": False},
            {"name": "notes", "expired": False},
        ]
        current = self.cli(artifacts, "--family", "candidate", "--run-id", "9",
                           "--run-attempt", "2", "--service", "yueops-web")
        self.assertEqual(current.returncode, 0, current.stderr)
        self.assertEqual(current.stdout, "built_attempt=2\nname=candidate-9-2-yueops-web\n")
        earlier = self.cli(
            [item for item in artifacts if item["name"] != "candidate-9-2-yueops-web"],
            "--family", "candidate", "--run-id", "9", "--run-attempt", "3",
            "--service", "yueops-web")
        self.assertEqual(earlier.returncode, 0, earlier.stderr)
        self.assertEqual(earlier.stdout, "built_attempt=1\nname=candidate-9-1-yueops-web\n")
        admission = self.cli(
            [{"name": "ops-admission-9-1", "expired": False},
             {"name": "ops-admission-9-4", "expired": False}],
            "--family", "admission", "--run-id", "9", "--run-attempt", "2")
        self.assertEqual(admission.returncode, 0, admission.stderr)
        self.assertEqual(admission.stdout, "built_attempt=1\nname=ops-admission-9-1\n")

    def test_missing_expired_foreign_and_duplicate_artifacts_emit_no_name(self):
        cases = {
            "empty": [],
            "expired": [{"name": "candidate-9-1-yueops-web", "expired": True}],
            "other service": [{"name": "candidate-9-1-yue-bot", "expired": False}],
            "future": [{"name": "candidate-9-3-yueops-web", "expired": False}],
            "duplicate": [{"name": "candidate-9-1-yueops-web", "expired": False},
                          {"name": "candidate-9-1-yueops-web", "expired": False}],
            "broken": ["candidate-9-1-yueops-web"],
            "newline ignored": [{"name": "candidate-9-1-yueops-web\nextra", "expired": False}],
        }
        for name, payload in cases.items():
            with self.subTest(name=name):
                result = self.cli(payload, "--family", "candidate", "--run-id", "9",
                                  "--run-attempt", "2", "--service", "yueops-web")
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertEqual(result.stdout, "")
                self.assertIn("handoff artifact refused", result.stderr)
        no_service = self.cli([], "--family", "candidate", "--run-id", "9", "--run-attempt", "2")
        self.assertNotEqual(no_service.returncode, 0)
        self.assertEqual(no_service.stdout, "")
        with_service = self.cli([], "--family", "admission", "--run-id", "9",
                                "--run-attempt", "2", "--service", "yueops-web")
        self.assertNotEqual(with_service.returncode, 0)
        self.assertEqual(with_service.stdout, "")


class HandoffAttemptIdentityTest(unittest.TestCase):
    def test_join_identity_uses_the_attempt_that_produced_the_admission(self):
        spec = importlib.util.spec_from_file_location(
            "handoff_pytest_shards", ROOT / "scripts/pytest-shards.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        head = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
        keys = ("GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT",
                "GITHUB_REPOSITORY", "YUETO_HANDOFF_ATTEMPT")
        previous = {key: os.environ.get(key) for key in keys}
        os.environ["GITHUB_SHA"] = head
        os.environ["GITHUB_RUN_ID"] = "431"
        os.environ["GITHUB_RUN_ATTEMPT"] = "2"
        os.environ["GITHUB_REPOSITORY"] = "onesyue/yueto-ci"
        os.environ.pop("YUETO_HANDOFF_ATTEMPT", None)
        try:
            self.assertEqual(module.workflow_identity()["run_attempt"], "2")
            os.environ["YUETO_HANDOFF_ATTEMPT"] = "2"
            self.assertEqual(module.workflow_identity()["run_attempt"], "2")
            os.environ["YUETO_HANDOFF_ATTEMPT"] = "1"
            self.assertEqual(module.workflow_identity()["run_attempt"], "1")
            os.environ["YUETO_HANDOFF_ATTEMPT"] = "3"
            with self.assertRaisesRegex(ValueError, "newer"):
                module.workflow_identity()
            os.environ["YUETO_HANDOFF_ATTEMPT"] = "0"
            with self.assertRaisesRegex(ValueError, "invalid handoff"):
                module.workflow_identity()
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
