"""Real temporary signing keys exercise Git object admission, never owner keys."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import source_evidence as E

SPEC = importlib.util.spec_from_file_location("source_admission_policy",
                                             E.ROOT / "scripts/pytest-shards.py")
P = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(P)


class SourceEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.home = Path(cls.temporary.name) / "gpg"
        cls.home.mkdir(mode=0o700)
        cls.env = dict(os.environ, GNUPGHOME=str(cls.home))
        cls.gpg = shutil.which("gpg")
        # No skip for missing cryptographic tooling: this module is a required gate.
        subprocess.run([cls.gpg, "--batch", "--pinentry-mode", "loopback", "--passphrase", "",
                        "--quick-generate-key", "Fixture <fixture@example.invalid>",
                        "ed25519", "sign", "0"], env=cls.env, check=True, capture_output=True)
        listing = subprocess.check_output([cls.gpg, "--with-colons", "--list-keys"], env=cls.env)
        cls.fingerprint = next(line.split(b":")[9].decode() for line in listing.splitlines()
                               if line.startswith(b"fpr:"))
        cls.policy = Path(cls.temporary.name) / "policy"
        cls.policy.mkdir()
        key = subprocess.check_output([cls.gpg, "--export", cls.fingerprint], env=cls.env)
        (cls.policy / "yueops-owner.gpg").write_bytes(key)
        cls.authority = {"schema": 1, "signer": cls.fingerprint, "primary": cls.fingerprint,
                         "keyring_sha256": E.digest(key)}
        (cls.policy / "yueops-owner-signers.json").write_text(json.dumps(cls.authority))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.signingkey", self.fingerprint)
        self.git("config", "gpg.program", self.gpg)
        (self.repo / "app.py").write_text("raise Exception('must never execute')\n")
        self.git("add", "app.py")
        self.git("commit", "-qm", "initial", "--no-gpg-sign")
        tree = E.tree_inputs(self.repo, self.git("rev-parse", "HEAD"))
        self.inputs = {"schema": 1, "inputs": tree, "inputs_sha256": E.digest(E.canonical(tree))}
        self.baseline = {"schema": 1, "status": "HISTORICAL_SKIPS_NOT_PASSES", "cases": {},
                         "collection_skips": {}, "context": {"platform": "linux", "uid": 1001},
                         "inputs_sha256": self.inputs["inputs_sha256"]}
        for path, value in ((E.INPUTS, self.inputs), (E.BASELINE, self.baseline)):
            target = self.repo / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(value))
        self.head = self.commit()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], env=self.env,
                                       stderr=subprocess.PIPE).decode().strip()

    def commit(self, signed=True):
        self.git("add", ".")
        self.git("commit", "-qm", "fixture", "-S" if signed else "--no-gpg-sign")
        return self.git("rev-parse", "HEAD")

    def load(self, head=None):
        return E._load(self.repo, head or self.head, self.policy)

    def test_actual_skip_blob_cli_accepts_signed_source_and_rejects_unregistered_case(self):
        with tempfile.TemporaryDirectory() as directory:
            public = Path(directory)
            (public / "scripts").mkdir()
            for name in ("pytest-shards.py", "source_evidence.py"):
                shutil.copyfile(E.ROOT / "scripts" / name, public / "scripts" / name)
            shutil.copytree(self.policy, public / "policy")

            def command(head):
                return subprocess.run([
                    sys.executable, str(public / "scripts/pytest-shards.py"),
                    "skip-blob-precheck", "--ops-checkout", str(self.repo),
                    "--ops-rev", head,
                ], capture_output=True, text=True, check=False, env=self.env)

            accepted = command(self.head)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertEqual(accepted.stdout.strip(), "skip-blob-precheck ok")
            # A correctly signed but unregistered approval is still rejected.
            baseline = self.baseline | {"cases": {"tests/test_missing.py::test_case": {
                "outcome": "skipped", "reason": "Skipped: unregistered", "when": "setup",
                "module_blob": "a" * 40, "disposition": "HISTORICAL_UNEXECUTED",
            }}}
            (self.repo / E.BASELINE).write_text(json.dumps(baseline))
            rejected = command(self.commit())
            self.assertNotEqual(rejected.returncode, 0)
            self.assertNotIn("skip-blob-precheck ok", rejected.stdout)

    def test_signed_exact_tree_bound_not_admitted(self):
        result = self.load()
        self.assertEqual(result["source_revision"], self.head)
        self.assertFalse(result["admission"])
        self.assertEqual(set(result["evidence"]), E.EVIDENCE_PATHS)

    def test_dirty_evidence_and_source_never_read(self):
        (self.repo / E.INPUTS).write_text("invalid")
        (self.repo / "app.py").write_text("changed")
        self.assertEqual(self.load()["source_revision"], self.head)

    def test_unsigned_commit_rejected(self):
        (self.repo / E.BASELINE).write_text(json.dumps(self.baseline) + "\n")
        with self.assertRaisesRegex(E.Rejected, "OpenPGP"):
            self.load(self.commit(signed=False))

    def test_authorized_signature_cannot_approve_wrong_blob(self):
        (self.repo / "app.py").write_text("changed")
        with self.assertRaisesRegex(E.Rejected, "manifest mismatch"):
            self.load(self.commit())

    def test_missing_or_symlink_evidence_rejected(self):
        for symlink in (False, True):
            with self.subTest(symlink=symlink):
                target = self.repo / E.BASELINE
                if target.exists():
                    target.unlink()
                if symlink:
                    target.symlink_to("shared-inputs.json")
                with self.assertRaisesRegex(E.Rejected, "nonregular evidence"):
                    self.load(self.commit())

    def test_untrusted_primary_or_signer_rejected(self):
        for field in ("signer", "primary"):
            with self.subTest(field=field):
                policy = self.repo / "test-policy"
                policy.mkdir(exist_ok=True)
                shutil.copyfile(self.policy / "yueops-owner.gpg", policy / "yueops-owner.gpg")
                (policy / "yueops-owner-signers.json").write_text(
                    json.dumps(self.authority | {field: "F" * 40}))
                with self.assertRaisesRegex(E.Rejected, "unauthorized"):
                    E._load(self.repo, self.head, policy)

    def test_injected_git_environment_cannot_redirect_source(self):
        with patch.dict(os.environ, {"GIT_DIR": "/nonexistent", "GIT_CONFIG_COUNT": "1",
                                    "GIT_CONFIG_KEY_0": "core.hooksPath",
                                    "GIT_CONFIG_VALUE_0": "/nonexistent"}):
            self.assertEqual(self.load()["source_revision"], self.head)

    def test_candidate_keyring_cannot_replace_public_authority(self):
        shutil.copytree(self.policy, self.repo / "policy")
        # A candidate-supplied valid fixture authority is not the public authority.
        with self.assertRaisesRegex(E.Rejected, "unauthorized"):
            E.load(self.repo, self.head)
        self.assertEqual(self.load()["source_revision"], self.head)

    def test_refs_and_missing_objects_rejected(self):
        for ref in ("HEAD", "f" * 40):
            with self.subTest(ref=ref), self.assertRaises(E.Rejected):
                self.load(ref)

    def test_duplicate_json_keys_and_mismatched_baseline_rejected(self):
        (self.repo / E.BASELINE).write_text('{"schema":1,"schema":1}')
        with self.assertRaisesRegex(E.Rejected, "JSON"):
            self.load(self.commit())
        (self.repo / E.BASELINE).write_text(json.dumps(self.baseline | {"inputs_sha256": "0" * 64}))
        with self.assertRaisesRegex(E.Rejected, "skip baseline"):
            self.load(self.commit())

    def corrupt_object(self, oid, kind, raw):
        target = self.repo / ".git" / "objects" / oid[:2] / oid[2:]
        target.chmod(0o600)
        target.write_bytes(zlib.compress(kind.encode() + b" " + str(len(raw)).encode()
                                        + b"\0" + raw))

    def test_corrupted_evidence_blob_under_original_oid_rejected(self):
        oid = self.git("rev-parse", self.head + ":" + E.BASELINE)
        forged = json.dumps(self.baseline | {"cases": {"forged": {}}}).encode()
        self.corrupt_object(oid, "blob", forged)
        with self.assertRaisesRegex(E.Rejected, "object identity mismatch"):
            self.load()

    def test_corrupted_nested_tree_under_original_oid_rejected(self):
        oid = self.git("rev-parse", self.head + ":ci/evidence")
        raw = subprocess.check_output(["git", "-C", str(self.repo), "cat-file", "tree", oid])
        self.corrupt_object(oid, "tree", raw.replace(b"shared-inputs.json", b"forged-inputs.json"))
        with self.assertRaisesRegex(E.Rejected, "object identity mismatch"):
            self.load()

    def test_join_requires_reverified_exact_source_before_acceptance(self):
        bound = self.load()
        value = {"source_revision": self.head, "source_evidence": bound}
        with self.assertRaisesRegex(ValueError, "source checkout required"):
            P.verify_source_evidence(value, None)
        with patch.object(P.source_evidence, "ROOT", self.policy.parent):
            P.verify_source_evidence(value, self.repo)
            value["source_evidence"] = bound | {"inputs_sha256": "0" * 64}
            with self.assertRaisesRegex(ValueError, "differs from original"):
                P.verify_source_evidence(value, self.repo)

    def test_real_signed_source_planner_envelope_and_missing_roles(self):
        (self.repo / "tests").mkdir()
        (self.repo / "scripts").mkdir()
        for name in ("a", "serial"):
            (self.repo / f"tests/test_{name}.py").write_text("def test_ok(): pass\n")
        (self.repo / "pytest.ini").write_text(
            "[pytest]\ntestpaths=tests\npython_files=test_*.py\npython_functions=test_*\nasyncio_mode=auto\n")
        (self.repo / "scripts/run-pytest-parallel.sh").write_text(
            "#!/bin/sh\nprintf '%s\\n' '{\"schema\":1,\"serial_modules\":[\"tests/test_serial.py\"]}'\n")
        code = self.commit()
        inputs = {path: value for path, value in E.tree_inputs(self.repo, code).items()
                  if path not in E.EVIDENCE_PATHS}
        digest = E.digest(E.canonical(inputs))
        (self.repo / E.INPUTS).write_text(json.dumps(
            {"schema": 1, "inputs": inputs, "inputs_sha256": digest}))
        (self.repo / E.BASELINE).write_text(json.dumps(self.baseline | {"inputs_sha256": digest}))
        head = self.commit()
        public = subprocess.check_output(["git", "-C", str(E.ROOT), "rev-parse", "HEAD"]).decode().strip()
        env = {"GITHUB_SHA": public, "GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": "1",
               "GITHUB_REPOSITORY": "onesyue/yueto-ci", "RUNNER_OS": "Linux", "RUNNER_ARCH": "X64",
               "ImageVersion": "fixture"}
        ops = {"repo": "onesyue/yueops", "ref": head, "validation": "yueops"}
        with patch.dict(os.environ, env), patch.object(P.source_evidence, "ROOT", self.policy.parent):
            value = P.expand({"validation_matrix": [ops], "matrix": [ops]}, self.repo, "b" * 40,
                             "ubuntu-24.04", 2, 1)
            self.assertEqual(P.envelope(value), value)
            # Re-seal both layers: rejection must enforce the public approval
            # scope, not merely notice a stale digest after candidate mutation.
            for field, wrong in (("runner_arch", "ARM64"), ("runner_os", "Windows")):
                changed = json.loads(json.dumps(value))
                changed["ops_plan"]["context"][field] = wrong
                changed["ops_plan"].pop("plan_sha256")
                P.seal(changed["ops_plan"], "plan_sha256")
                changed.pop("admission_sha256")
                P.seal(changed, "admission_sha256")
                with self.subTest(field=field), self.assertRaisesRegex(
                        ValueError, "runner differs from reviewed hosted scope"):
                    P.envelope(changed)
            P.verify_source_evidence(value, self.repo)
            with self.assertRaisesRegex(ValueError, "missing evidence"):
                P.join(value, self.repo / "absent", "success", value["admission_sha256"], self.repo)
            with self.assertRaisesRegex(ValueError, "did not succeed"):
                P.join(value, self.repo / "absent", "skipped", value["admission_sha256"], self.repo)

    def skip_fixture(self):
        module = "tests/test_fixture.py"
        nodeid = module + "::test_sample"
        blob = "a" * 40
        case = {"outcome": "skipped", "reason": "Skipped: fixture", "when": "setup",
                "module_blob": blob, "disposition": "HISTORICAL_UNEXECUTED"}
        bound = self.load()
        bound["baseline"]["cases"] = {nodeid: case}
        row = {"nodeid": nodeid, "outcome": case["outcome"], "reason": case["reason"], "when": "setup"}
        reference = {"assignment_id": "reference", "execution_context": self.baseline["context"],
                     "junit_sha256": "b" * 64, "collection_skips": {}, "nonpassing_outcomes": []}
        shard = reference | {"assignment_id": "ordinary-000", "nonpassing_outcomes": [row]}
        return bound, {module: blob}, {"reference": reference, "shards": [shard]}, nodeid

    def test_source_skip_exact_outcome_platform_blob_and_native_obligation(self):
        bound, blobs, result, nodeid = self.skip_fixture()
        native = {"obligations": {}}
        self.assertFalse(E.admit_skips(bound, blobs, result, native, set())["skips_are_passes"])
        for field, wrong in (("reason", "different"), ("when", "call"), ("outcome", "xfail")):
            row = result["shards"][0]["nonpassing_outcomes"][0]
            with self.subTest(field=field), patch.dict(row, {field: wrong}), self.assertRaises(E.Rejected):
                E.admit_skips(bound, blobs, result, native, set())
        with self.assertRaisesRegex(E.Rejected, "stale skip"):
            E.admit_skips(bound, {next(iter(blobs)): "f" * 40}, result, native, set())
        with self.assertRaisesRegex(E.Rejected, "cannot waive native"):
            E.admit_skips(bound, blobs, result, native, set(blobs))
        case = bound["baseline"]["cases"][nodeid]
        case.update(disposition="SAME_RUN_NATIVE_REQUIRED", native_target=next(iter(blobs)))
        with self.assertRaisesRegex(E.Rejected, "missing same-run"):
            E.admit_skips(bound, blobs, result, native, set(blobs))
        native["obligations"][next(iter(blobs))] = {"passed": [nodeid]}
        self.assertEqual(E.admit_skips(bound, blobs, result, native, set(blobs))[
            "disposition_counts"]["SAME_RUN_NATIVE_REQUIRED"], 1)

    def test_missing_junit_unregistered_skip_and_wrong_platform_rejected(self):
        for mutation in ("junit", "unknown", "platform"):
            bound, blobs, result, _ = self.skip_fixture()
            if mutation == "junit":
                result["shards"][0]["junit_sha256"] = ""
            elif mutation == "unknown":
                bound["baseline"]["cases"] = {}
            else:
                result["shards"][0]["execution_context"] = {"platform": "darwin", "uid": 1001}
            with self.subTest(mutation=mutation), self.assertRaises(E.Rejected):
                E.admit_skips(bound, blobs, result, {"obligations": {}}, set())

    @unittest.skipUnless(sys.platform == "linux", "source-owned hosted admission requires Linux")
    def test_migrated_nonempty_baseline_actual_signed_full_role_join(self):
        # The existing fixture runs real pytest ordinary/reference/serial and
        # actual native-protocol fixture programs. Only the signing certificate
        # is a fixture trust injection; no loader or join function is mocked.
        from test_ops_shard_workflow import OpsShardWorkflow
        workflow = OpsShardWorkflow()
        workflow.setUp()
        self.addCleanup(workflow.doCleanups)
        # Carry the real public runner scope into this generated historical
        # fixture; source-owned admission must not invent a broader approval.
        workflow.baseline["reviewed_hosted"] = {
            "schema": 1, "context": workflow.baseline["context"], "cases": {},
            "runner": P.skip_baseline()["reviewed_hosted"]["runner"],
        }
        (workflow.policy / "ops-pytest-skip-baseline.json").write_text(json.dumps(workflow.baseline))
        workflow.fixture.git(workflow.policy, "add", "ops-pytest-skip-baseline.json")
        workflow.fixture.commit(workflow.policy)
        migration = workflow.consumer.export_source_baseline(workflow.source, workflow.source_sha)
        self.assertTrue(migration["baseline"]["cases"])
        self.assertFalse(migration["unmatched"])
        for path, value in ((E.BASELINE, migration["baseline"]), (E.INPUTS, migration["shared_inputs"])):
            target = workflow.source / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(value))
        command = ["git", "-C", str(workflow.source)]
        subprocess.run([*command, "add", E.BASELINE, E.INPUTS], check=True, capture_output=True)
        subprocess.run([*command, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                        "-c", "gpg.program=" + self.gpg, "-c",
                        "user.signingkey=" + self.fingerprint, "commit", "-S", "-qm", "fixture enrollment"],
                       env=self.env, check=True, capture_output=True)
        workflow.source_sha = subprocess.check_output([*command, "rev-parse", "HEAD"]).decode().strip()
        nested = workflow.policy / "policy"
        # ShardPrimitives already wrote the shard signer here. Replace it with
        # this test's fixture authority; copytree refuses an existing directory.
        if nested.exists():
            shutil.rmtree(nested)
        shutil.copytree(self.policy, nested)
        workflow.rebind_board_signer(self.gpg, self.fingerprint, self.env)
        workflow.fixture.git(workflow.policy, "add", "policy")
        workflow.fixture.commit(workflow.policy)
        workflow.env["GITHUB_SHA"] = workflow.fixture.git(
            workflow.policy, "rev-parse", "HEAD").stdout.strip()
        for row in workflow.targets["matrix"] + workflow.targets["validation_matrix"]:
            row["ref"] = workflow.source_sha
        workflow.admission = workflow.call(workflow.consumer.expand, workflow.targets,
                                            workflow.source, workflow.board_sha, "ubuntu-24.04", 4, 4)
        self.assertIn("source_evidence", workflow.admission)

        def join(result="success", expected=None):
            return workflow.call(workflow.consumer.join, workflow.admission, workflow.artifacts, result,
                                 expected or workflow.admission["admission_sha256"], workflow.source)

        with patch.object(workflow, "join", side_effect=join):
            result = workflow.full_bundle()
            self.assertEqual(result["status"], "VALIDATION_MATRIX_COMPLETE")
            self.assertGreater(sum(result["skip_admission"]["disposition_counts"].values()), 0)
            (workflow.artifacts / (workflow.prefix + "native") / "native.json").unlink()
            with self.assertRaises((ValueError, OSError)):
                join()

    def test_real_public_native_history_projection_preserves_phase_and_requires_passed(self):
        # Use the real public-approved records and real successor/export logic;
        # only the private checkout's tree/ancestry is a discovery fixture.
        modules = {"tests/test_node_systemd_pilot_20261018.py",
                   "tests/test_schema_contract_receipt_20261020.py"}
        approved = {n: case for n, case in P.skip_baseline()["cases"].items()
                    if n.split("::", 1)[0] in modules}
        files = {n.split("::", 1)[0]: {"mode": "100644", "kind": "blob",
                                      "git_blob": case["module_blob"]}
                 for n, case in approved.items()}
        with patch.object(P.source_evidence, "tree_inputs", return_value=files):
            exported = P.export_source_baseline(self.repo, "a" * 40)
        baseline = exported["baseline"]
        expected_count = sum(P.NATIVE_TARGETS[module][0] for module in modules)
        self.assertEqual(sum(n.split("::", 1)[0] in modules for n in baseline["cases"]), expected_count)
        outcomes, obligations = [], {}
        for nodeid, variants in baseline["cases"].items():
            if nodeid.split("::", 1)[0] not in modules:
                continue
            original = approved[nodeid]
            for row in variants:
                self.assertEqual({key: row[key] for key in original}, original)
                self.assertEqual(row["disposition"], "SAME_RUN_NATIVE_REQUIRED")
                self.assertEqual(row["native_target"], nodeid.split("::", 1)[0])
            row = variants[0]
            outcomes.append({"nodeid": nodeid, **{key: row[key] for key in ("outcome", "reason", "when")}})
            obligations.setdefault(row["native_target"], {"passed": []})["passed"].append(nodeid)
        reference = {"assignment_id": "reference", "execution_context": baseline["context"],
                     "junit_sha256": "a" * 64, "collection_skips": {}, "nonpassing_outcomes": []}
        result = {"reference": reference, "shards": [reference | {
            "assignment_id": "ordinary-000", "nonpassing_outcomes": outcomes}]}
        bound = {"baseline": baseline, "source_revision": "a" * 40,
                 "evidence": {E.BASELINE: {"sha256": "b" * 64}}}
        blobs = {module: row["git_blob"] for module, row in files.items()}
        native = {"obligations": obligations}
        admitted = E.admit_skips(bound, blobs, result, native, modules)
        self.assertEqual(admitted["disposition_counts"]["SAME_RUN_NATIVE_REQUIRED"], expected_count)
        next(iter(obligations.values()))["passed"].pop()
        with self.assertRaisesRegex(E.Rejected, "missing same-run"):
            E.admit_skips(bound, blobs, result, native, modules)


if __name__ == "__main__":
    unittest.main()
