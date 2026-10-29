"""D removes only retired Mini IDs, preserving every historical seal below F."""
import copy
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("retired_host_shards", ROOT / "scripts/pytest-shards.py")
assert SPEC is not None and SPEC.loader is not None
SHARDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARDS)
KEY = SHARDS.RETIRED_HOST_KEY
MODULE = SHARDS.RETIRED_HOST_MODULE


class RetiredHostTransition(unittest.TestCase):
    def setUp(self):
        self.raw = (ROOT / SHARDS.SKIP_BASELINE).read_bytes()
        self.baseline = json.loads(self.raw)
        self.prior, self.record = SHARDS.reviewed_retired_host_transition(self.baseline)
        self.survivor = self.record["surviving_ids"][0]

    def test_exact_predecessor_and_existing_seals(self):
        self.assertEqual(SHARDS.sha(SHARDS.baseline_bytes(self.prior)),
                         "927f711ddbdd4aa14012ccb687183e969610922e0c9b17b55eef06545ec86e91")
        self.assertEqual(len(self.record["removed"]), 3)
        self.assertEqual(len(self.record["surviving_ids"]), 12)
        self.assertEqual(set(self.prior["cases"]) - set(self.baseline["cases"]),
                         SHARDS.RETIRED_HOST_IDS)
        self.assertEqual(self.baseline["required_native_inputs"], self.prior["required_native_inputs"])
        for name in (
            "required_native_inputs", "reviewed_tornado66_dependency_transition",
            "reviewed_release_skip_blob_successor_transition", "reviewed_hang_guard_input_transition",
            "reviewed_skip_blob_successor_transition", "reviewed_runtime_dependency_transition",
            "reviewed_audit_lock_transition", "reviewed_bot_packaging_transition",
            "reviewed_case_file_transition", "reviewed_site_lock_transition",
            "reviewed_estate_input_transition",
        ):
            with self.subTest(consumer=name):
                self.assertEqual(getattr(SHARDS, name)(self.baseline),
                                 getattr(SHARDS, name)(self.prior))
        self.assertEqual(self.raw, SHARDS.baseline_bytes(self.baseline))

    def reject(self, mutate):
        changed = copy.deepcopy(self.baseline)
        mutate(changed)
        with self.assertRaises(ValueError):
            SHARDS.reviewed_estate_input_transition(changed)
        with patch.object(SHARDS, "read_json", return_value=changed), self.assertRaises(ValueError):
            SHARDS.skip_baseline()

    def test_wrong_predecessor_digest_rejected(self):
        self.reject(lambda b: b[KEY].update(prior_baseline_sha256="f" * 64))

    def test_extra_removed_id_rejected(self):
        self.reject(lambda b: b["cases"].pop(self.survivor))
        self.reject(lambda b: b["reviewed_current_skip_transition"]["updates"].pop(self.survivor))

    def test_missing_removed_id_rejected(self):
        nodeid = sorted(SHARDS.RETIRED_HOST_IDS)[0]
        self.reject(lambda b: b["cases"].update({nodeid: self.prior["cases"][nodeid]}))
        self.reject(lambda b: b["reviewed_current_skip_transition"]["updates"].update({
            nodeid: self.prior["reviewed_current_skip_transition"]["updates"][nodeid]}))

    def test_unrelated_mutation_rejected(self):
        self.reject(lambda b: b.update(events_sha256="f" * 64))
        self.reject(lambda b: b["cases"][self.survivor].update(reason="different reason"))
        self.reject(lambda b: b["required_native_inputs"]["inputs"].update({"extra.py": "f" * 40}))

    def test_wrong_blob_rejected(self):
        self.reject(lambda b: b["cases"][self.survivor].update(module_blob="f" * 40))
        self.reject(lambda b: b["reviewed_current_skip_transition"]["updates"][
            self.survivor].update(after_blob="f" * 40))
        self.reject(lambda b: b[KEY].update(after_blob="f" * 40))

    def test_retirement_layer_stripped_rejected(self):
        self.reject(lambda b: b.pop(KEY))

    def admit(self, nodeids, blob):
        rows = [{"nodeid": n, "outcome": "skipped", "when": "setup",
                 "reason": self.prior["cases"][n]["reason"]} for n in nodeids]
        body = {"execution_context": self.baseline["context"], "collection_skips": {},
                "junit_sha256": "b" * 64, "nonpassing_outcomes": rows}
        result = {"reference": body | {"assignment_id": "reference"},
                  "shards": [body | {"assignment_id": "ordinary-000"}]}
        historical, inputs = SHARDS.required_native_inputs(self.baseline)
        value = {"skip_module_blobs": {MODULE: blob}, "skip_baseline_sha256": SHARDS.sha(self.raw),
                 "common_inputs": historical["common_inputs"] | inputs}
        with patch.object(SHARDS, "skip_baseline", return_value=self.baseline):
            return SHARDS.admit_skips(value, result, {})

    def test_hosted_matching_accepts_all_survivors_only_at_new_blob(self):
        admitted = self.admit(self.record["surviving_ids"], SHARDS.RETIRED_HOST_AFTER_BLOB)
        self.assertEqual(admitted["disposition_counts"]["HISTORICAL_UNEXECUTED"], 24)
        self.assertFalse(admitted["skips_are_passes"])
        for blob in (SHARDS.RETIRED_HOST_BEFORE_BLOB, self.record["historical_blob"], "f" * 40):
            with self.subTest(blob=blob), self.assertRaisesRegex(ValueError, "retired host case"):
                self.admit([self.survivor], blob)
        for nodeid in SHARDS.RETIRED_HOST_IDS:
            for blob in (SHARDS.RETIRED_HOST_AFTER_BLOB, SHARDS.RETIRED_HOST_BEFORE_BLOB,
                         self.record["historical_blob"]):
                with self.subTest(nodeid=nodeid, blob=blob), self.assertRaisesRegex(
                        ValueError, "retired host case"):
                    self.admit([nodeid], blob)

    def test_generator_reproducible_and_rejects_wrong_inputs(self):
        files = {MODULE: ("100644", SHARDS.RETIRED_HOST_AFTER_BLOB)}
        with tempfile.TemporaryDirectory() as tmp:
            predecessor = Path(tmp) / "prior.json"
            predecessor.write_bytes(SHARDS.baseline_bytes(self.prior))
            with patch.object(SHARDS, "tree_inputs", return_value=files):
                for _ in range(2):
                    generated = SHARDS.generate_retired_host_baseline(predecessor, Path(tmp), "a" * 40)
                    self.assertEqual(SHARDS.baseline_bytes(generated), self.raw)
            for entry in (("120000", SHARDS.RETIRED_HOST_AFTER_BLOB),
                          ("100644", SHARDS.RETIRED_HOST_BEFORE_BLOB)):
                with patch.object(SHARDS, "tree_inputs", return_value={MODULE: entry}), self.assertRaises(
                        ValueError):
                    SHARDS.generate_retired_host_baseline(predecessor, Path(tmp), "a" * 40)
            predecessor.write_bytes(self.raw)
            completed = subprocess.run([
                "python3", str(ROOT / "scripts/pytest-shards.py"), "generate-retired-host-baseline",
                "--predecessor", str(predecessor), "--source", tmp, "--revision", "a" * 40,
            ], capture_output=True, text=True, check=False)
            self.assertEqual(completed.returncode, 1)
            self.assertEqual(completed.stdout, "")
            self.assertIn("exact F predecessor", completed.stderr)
