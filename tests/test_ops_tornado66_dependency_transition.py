"""A Tornado security update admits one sealed three-file bundle, not a dependency exemption."""
import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("tornado66_shards", ROOT / "scripts/pytest-shards.py")
assert SPEC is not None and SPEC.loader is not None
SHARDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARDS)
KEY = "reviewed_tornado66_dependency_transition"
PATHS = {"pyproject.toml", "uv.lock", "telegram-bot/yue/requirements.txt"}
EVIDENCE_FIELDS = (
    "independent_review_sha256", "source_freeze_sha256", "qualification_receipt_sha256",
)
PRIOR_SHA256 = "f6277c02518d820b8d6e9630b6dd339f60afe89774ced9a363b686c4e4795afa"


class TornadoDependencyTransition(unittest.TestCase):
    def setUp(self):
        sealed = json.loads((ROOT / "ops-pytest-skip-baseline.json").read_text())
        self.prior, _ = SHARDS.reviewed_tornado66_dependency_transition(sealed)
        self.runtime = self.prior["reviewed_runtime_dependency_transition"]
        self.estate = self.prior["reviewed_estate_input_transition"]
        self.record = {
            "schema": 1,
            "prior_baseline_sha256": SHARDS.sha(
                (json.dumps(self.prior, indent=2, ensure_ascii=False) + "\n").encode()),
            "source_before": "a0a46ca02ae2d01aa19ac5ce82c749b05ab6c80a",
            "source_after": "b" * 40,
            # Synthetic test-only receipts; never copied into the production record.
            **{key: hashlib.sha256(("test-fixture:" + key).encode()).hexdigest()
               for key in EVIDENCE_FIELDS},
            "changes": {
                path: {"before_blob": self.runtime["changes"][path]["after_blob"],
                       "after_blob": hashlib.sha1(("test-fixture:" + path).encode()).hexdigest(),
                       "mode": "100644"} for path in sorted(PATHS)
            },
        }
        self.sealed = self.prior | {KEY: self.record}
        self.pin = patch.object(SHARDS, "TORNADO66_DEPENDENCY_TRANSITION_SHA256",
                                SHARDS.sha(SHARDS.encoded(self.record)))
        self.pin.start()
        self.addCleanup(self.pin.stop)
        self.common = dict(self.prior["common_inputs"])
        modes = self.prior["reviewed_shared_input_transition"]["common_input_modes"]
        self.files = {p: (modes[p], blob) for p, blob in self.common.items()}
        # Compose all reviewed shared-input successors in their original order.
        for name, row in self.prior.items():
            if not name.startswith("reviewed_") or not isinstance(row, dict):
                continue
            if "path" in row:
                self.common[row["path"]] = row["after_blob"]
                self.files[row["path"]] = (row.get("mode", "100644"), row["after_blob"])
            for path, change in row.get("changes", {}).items():
                self.common[path] = change["after_blob"]
                self.files[path] = (change["mode"], change["after_blob"])
        self.successor = self.common | {
            path: change["after_blob"] for path, change in self.record["changes"].items()}
        self.successor_files = self.files | {
            path: (change["mode"], change["after_blob"])
            for path, change in self.record["changes"].items()}

    def admit(self, common=None, files=None, source=None, proof=None, baseline=None):
        return SHARDS.admit_shared_inputs(
            self.sealed if baseline is None else baseline,
            self.successor if common is None else common,
            self.successor_files if files is None else files,
            source_revision=self.record["source_after"] if source is None else source,
            estate_successor_of=self.estate["source_after"] if proof is None else proof)

    def test_production_record_restores_the_exact_prior_bytes_below_native_inputs(self):
        # Unlike the other fixture controls, this requires the real reviewed seal.
        raw = (ROOT / "ops-pytest-skip-baseline.json").read_bytes()
        sealed = json.loads(raw)
        actual_pin = SHARDS.TORNADO66_DEPENDENCY_TRANSITION_SHA256
        # The fixture pin is local to this test class, so read the deployed constant
        # in a fresh module rather than accidentally accepting synthetic receipts.
        spec = importlib.util.spec_from_file_location("tornado66_production_pin",
                                                     ROOT / "scripts/pytest-shards.py")
        assert spec is not None and spec.loader is not None
        production = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(production)
        # The reviewed ops packaging successor is sealed above Tornado; peel it with the
        # production pins before walking the fixture-pinned chain.
        below_packaging, _ = production.reviewed_ops_packaging_transition(sealed)
        historical, _ = SHARDS.required_native_inputs(below_packaging)
        self.assertEqual(list(historical)[-1], KEY)
        self.assertIsInstance(production.TORNADO66_DEPENDENCY_TRANSITION_SHA256, str)
        self.assertNotEqual(actual_pin, production.TORNADO66_DEPENDENCY_TRANSITION_SHA256)
        prior, record = production.reviewed_tornado66_dependency_transition(sealed)
        self.assertEqual(record["prior_baseline_sha256"], PRIOR_SHA256)
        self.assertEqual(record["source_before"], "a0a46ca02ae2d01aa19ac5ce82c749b05ab6c80a")
        self.assertNotEqual(record["source_after"], self.record["source_after"])
        for field in EVIDENCE_FIELDS:
            self.assertNotEqual(record[field], self.record[field])
        self.assertEqual(set(record["changes"]), PATHS)
        restored = (json.dumps(prior, indent=2, ensure_ascii=False) + "\n").encode()
        self.assertEqual(SHARDS.sha(restored), PRIOR_SHA256)
        self.assertEqual(raw, (json.dumps(sealed, indent=2, ensure_ascii=False) + "\n").encode())

    def test_prior_baseline_and_historical_seals_are_unchanged(self):
        self.assertEqual(self.record["prior_baseline_sha256"], PRIOR_SHA256)
        prior, record = SHARDS.reviewed_tornado66_dependency_transition(self.sealed)
        self.assertEqual(prior, self.prior)
        self.assertEqual(record, self.record)
        for name in (
            "reviewed_release_skip_blob_successor_transition", "reviewed_hang_guard_input_transition",
            "reviewed_skip_blob_successor_transition", "reviewed_runtime_dependency_transition",
            "reviewed_audit_lock_transition", "reviewed_bot_packaging_transition",
            "reviewed_case_file_transition", "reviewed_site_lock_transition",
            "reviewed_estate_input_transition",
        ):
            with self.subTest(consumer=name):
                historical, _ = getattr(SHARDS, name)(self.sealed)
                self.assertNotIn(KEY, historical)
        self.admit()
        self.admit(common=self.common, files=self.files, source=self.record["source_before"])
        with self.assertRaises(ValueError):
            self.admit(baseline=self.prior)

    def test_bundle_refuses_missing_mixed_extra_mode_and_unproven_source(self):
        for path in sorted(PATHS):
            for mutation in ("missing", "mixed", "changed"):
                common = dict(self.successor)
                files = dict(self.successor_files)
                if mutation == "missing":
                    common.pop(path)
                    files.pop(path)
                else:
                    blob = self.record["changes"][path]["before_blob"] if mutation == "mixed" else "f" * 40
                    common[path] = blob
                    files[path] = ("100644", blob)
                with self.subTest(path=path, mutation=mutation), self.assertRaises(ValueError):
                    self.admit(common=common, files=files)
            for mode in ("100755", "120000"):
                files = self.successor_files | {path: (mode, self.successor[path])}
                with self.subTest(path=path, mode=mode), self.assertRaises(ValueError):
                    self.admit(files=files)
        with self.assertRaises(ValueError):
            self.admit(common=self.successor | {"tests/_unreviewed.py": "f" * 40})
        for source, proof in ((self.estate["source_after"], self.estate["source_after"]),
                              (self.record["source_after"], "f" * 40)):
            with self.subTest(source=source, proof=proof), self.assertRaises(ValueError):
                self.admit(source=source, proof=proof)
        with self.assertRaises(ValueError):
            SHARDS.admit_shared_inputs(self.sealed, self.successor, self.successor_files,
                                       source_revision=self.record["source_after"])

    def test_damaged_record_and_resealed_malformed_record_are_refused(self):
        mutations = [
            lambda r: r.__setitem__("schema", True),
            lambda r: r.__setitem__("extra", "not-reviewed"),
            lambda r: r.__setitem__("source_after", r["source_before"]),
            lambda r: r.__setitem__("source_before", "invalid"),
            lambda r: r.__setitem__("prior_baseline_sha256", "f" * 64),
            lambda r: r["changes"].pop("uv.lock"),
            lambda r: r["changes"].__setitem__("web/requirements.txt", dict(r["changes"]["uv.lock"])),
            lambda r: r["changes"]["uv.lock"].__setitem__("mode", "100755"),
            lambda r: r["changes"]["uv.lock"].__setitem__("before_blob", "f" * 40),
            lambda r: r["changes"]["uv.lock"].__setitem__("after_blob", r["changes"]["uv.lock"]["before_blob"]),
        ]
        for field in EVIDENCE_FIELDS:
            mutations.extend((lambda r, f=field: r.pop(f),
                              lambda r, f=field: r.__setitem__(f, "0" * 64)))
        for mutate in mutations:
            damaged = copy.deepcopy(self.sealed)
            mutate(damaged[KEY])
            for consumer in (SHARDS.reviewed_tornado66_dependency_transition,
                             SHARDS.reviewed_release_skip_blob_successor_transition,
                             SHARDS.reviewed_estate_input_transition):
                with self.subTest(consumer=consumer.__name__, mutate=mutate), self.assertRaises(ValueError):
                    consumer(damaged)
            # Shape and historical-chain checks still reject if only the pin is changed.
            with patch.object(SHARDS, "TORNADO66_DEPENDENCY_TRANSITION_SHA256",
                              SHARDS.sha(SHARDS.encoded(damaged[KEY]))), self.assertRaises(ValueError):
                SHARDS.reviewed_tornado66_dependency_transition(damaged)
        damaged = copy.deepcopy(self.sealed)
        damaged["cases"][next(iter(damaged["cases"]))]["reason"] = "changed history"
        with self.assertRaisesRegex(ValueError, "historical baseline"):
            SHARDS.reviewed_tornado66_dependency_transition(damaged)

    def test_real_expand_envelope_and_skip_consumer_reach_bundle_admission(self):
        # Source discovery is controlled; planner envelope and every admission consumer are real.
        policy = SHARDS.git(ROOT, "rev-parse", "HEAD").decode().strip()
        identity = {"policy_revision": policy, "run_id": "42", "run_attempt": "1"}
        board, source = "a" * 40, self.record["source_after"]
        planned = SHARDS.seal({
            "schema": 1, "kind": "ops-pytest-module-plan", "source_revision": source,
            "context": identity | {"board_revision": board, "runner_os": "Linux",
                                    "runner_arch": "X64", "runner_image": "test-fixture"},
            "pytest_ini_sha256": "a" * 64, "entry_sha256": "b" * 64,
            "recorder_sha256": "c" * 64, "modules": {"tests/test_control.py": "d" * 64},
            "assignments": [{"id": "ordinary-000", "modules": ["tests/test_control.py"]}],
        }, "plan_sha256")
        target = {"validation": "yueops", "repo": "onesyue/yueops", "ref": source}
        env = {"GITHUB_SHA": policy, "GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": "1",
               "GITHUB_REPOSITORY": "onesyue/yueto-ci", "RUNNER_OS": "Linux",
               "RUNNER_ARCH": "X64", "ImageVersion": "test-fixture"}
        session = {"execution_context": self.prior["context"], "collection_skips": {},
                   "junit_sha256": "b" * 64, "nonpassing_outcomes": []}
        result = {"reference": session | {"assignment_id": "reference"},
                  "shards": [session | {"assignment_id": "ordinary-000"}]}
        with tempfile.TemporaryDirectory() as directory:
            baseline_path = Path(directory) / "fixture-baseline.json"
            baseline_path.write_text(json.dumps(self.sealed, indent=2) + "\n")
            with (patch.object(SHARDS, "SKIP_BASELINE", str(baseline_path)),
                  patch.dict(os.environ, env), patch.object(SHARDS, "plan", return_value=planned),
                  patch.object(SHARDS, "serial_modules", return_value=[]),
                  patch.object(SHARDS, "shared_inputs", return_value=self.successor),
                  patch.object(SHARDS, "tree_inputs", return_value=self.successor_files | {
                      "tests/test_control.py": ("100644", "e" * 40)}),
                  patch.object(SHARDS, "estate_successor_proof", return_value=self.estate["source_after"])):
                value = SHARDS.expand({"matrix": [target], "validation_matrix": [target]},
                                      ROOT, board, "ubuntu-24.04", 3, 1)
                SHARDS.envelope(value)
                self.assertEqual(SHARDS.admit_skips(value, result, {})["status"], "NO_NEW_SKIPS")
                for field in ("uv.lock", "pyproject.toml", "telegram-bot/yue/requirements.txt"):
                    changed = copy.deepcopy(value)
                    changed["common_inputs"][field] = self.record["changes"][field]["before_blob"]
                    changed.pop("admission_sha256")
                    SHARDS.seal(changed, "admission_sha256")
                    with self.subTest(field=field), self.assertRaises(ValueError):
                        SHARDS.envelope(changed)
                    with self.subTest(field=field), self.assertRaises(ValueError):
                        SHARDS.admit_skips(changed, result, {})

    def test_planner_requires_real_source_before_and_after_ancestry(self):
        with tempfile.TemporaryDirectory() as tmp:
            def git(*args):
                return subprocess.run(["git", "-C", tmp, *args], check=True,
                                      capture_output=True, text=True).stdout.strip()
            git("init", "-q")
            git("config", "user.email", "fixture@example.invalid")
            git("config", "user.name", "fixture")
            git("config", "commit.gpgsign", "false")
            git("commit", "-q", "--allow-empty", "-m", "estate")
            estate = git("rev-parse", "HEAD")
            git("commit", "-q", "--allow-empty", "-m", "before")
            before = git("rev-parse", "HEAD")
            lock = Path(tmp) / "uv.lock"
            lock.write_text("reviewed Tornado fixture\n")
            git("add", "uv.lock")
            git("commit", "-q", "-m", "security successor")
            after = git("rev-parse", "HEAD")
            blob = git("rev-parse", "HEAD:uv.lock")
            git("commit", "-q", "--allow-empty", "-m", "later")
            later = git("rev-parse", "HEAD")
            git("checkout", "-q", "-b", "unrelated", estate)
            lock.write_text("reviewed Tornado fixture\n")
            git("add", "uv.lock")
            git("commit", "-q", "-m", "same bytes, unrelated source")
            unrelated = git("rev-parse", "HEAD")
            record = copy.deepcopy(self.record)
            record.update(source_before=before, source_after=after)
            record["changes"]["uv.lock"]["after_blob"] = blob
            none = lambda b, *a: (b, None)
            with (patch.object(SHARDS, "reviewed_tornado66_dependency_transition", return_value=({}, record)),
                  patch.object(SHARDS, "reviewed_hang_guard_input_transition", none),
                  patch.object(SHARDS, "reviewed_runtime_dependency_transition", none),
                  patch.object(SHARDS, "reviewed_audit_lock_transition", none),
                  patch.object(SHARDS, "reviewed_bot_packaging_transition", none),
                  patch.object(SHARDS, "reviewed_site_lock_transition", none),
                  patch.object(SHARDS, "reviewed_estate_input_transition", return_value=({}, {"source_after": estate}))):
                for revision in (after, later):
                    self.assertEqual(SHARDS.estate_successor_proof({}, Path(tmp), revision), estate)
                with self.assertRaisesRegex(ValueError, "Tornado dependency successor"):
                    SHARDS.estate_successor_proof({}, Path(tmp), unrelated)
                record["source_before"] = unrelated
                with self.assertRaisesRegex(ValueError, "Tornado dependency successor"):
                    SHARDS.estate_successor_proof({}, Path(tmp), later)


if __name__ == "__main__":
    unittest.main()
