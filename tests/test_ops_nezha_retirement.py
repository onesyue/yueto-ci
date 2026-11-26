"""Owner-retired Nezha skips leave the active baseline without rewriting history."""
import sys
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from pytest_shards.config import (
    NEZHA_PRIOR_BASELINE_SHA256,
    NEZHA_RETIRED_MODULE,
    NEZHA_RETIREMENT_KEY,
    SKIP_BASELINE,
)
from pytest_shards import skip_baseline as skip_baseline_mod
from pytest_shards import skip_bindings as skip_bindings_mod
from pytest_shards import transitions_native
from pytest_shards.skip_baseline import skip_baseline
from pytest_shards.skip_bindings import admit_skips
from pytest_shards.support import baseline_bytes, sha
from pytest_shards.transitions_native import (
    historical_skip_baseline_bytes,
    required_native_inputs,
    restore_nezha_history,
    reviewed_native_input_successor,
)



class NezhaRetirement(unittest.TestCase):
    def setUp(self):
        self.baseline = skip_baseline()
        self.prior = restore_nezha_history(self.baseline)
        self.removed = [n for n in self.prior["cases"]
                        if n.startswith(NEZHA_RETIRED_MODULE + "::")]

    def test_exact_deletion_preserves_format_order_and_historical_hashes(self):
        raw = (ROOT / SKIP_BASELINE).read_bytes()
        self.assertEqual(raw, baseline_bytes(self.baseline))
        self.assertNotIn(NEZHA_RETIRED_MODULE.encode(), raw)
        self.assertEqual(len(self.baseline["cases"]), 1000)
        self.assertEqual(len(self.removed), 2)
        expected = copy.deepcopy(self.prior)
        for nodeid in self.removed:
            del expected["cases"][nodeid]
        expected[NEZHA_RETIREMENT_KEY] = self.baseline[NEZHA_RETIREMENT_KEY]
        predecessor, _ = reviewed_native_input_successor(self.baseline)
        self.assertEqual(baseline_bytes(expected), baseline_bytes(predecessor))
        self.assertEqual(sha(baseline_bytes(self.prior)), NEZHA_PRIOR_BASELINE_SHA256)
        self.assertEqual(historical_skip_baseline_bytes(), baseline_bytes(self.prior))
        # The returned history is independent of the active case mapping.
        self.assertTrue(set(self.removed).isdisjoint(self.baseline["cases"]))

    def test_missing_or_altered_retirement_record_is_rejected(self):
        for field, value in ((None, None), ("schema", True), ("removed_case_count", 1),
                             ("prior_baseline_sha256", "f" * 64)):
            changed = copy.deepcopy(self.baseline)
            if field is None:
                del changed[NEZHA_RETIREMENT_KEY]
            else:
                changed[NEZHA_RETIREMENT_KEY][field] = value
            with self.subTest(field=field), patch.object(skip_baseline_mod, "read_json", return_value=changed):
                with self.assertRaises(ValueError):
                    skip_baseline()

    def test_extra_deletion_or_restored_case_is_rejected(self):
        for mutation in ("extra-deletion", "changed-case", *self.removed):
            changed = copy.deepcopy(self.baseline)
            unrelated = next(iter(changed["cases"]))
            if mutation == "extra-deletion":
                del changed["cases"][unrelated]
            elif mutation == "changed-case":
                changed["cases"][unrelated]["reason"] = "unreviewed reason"
            else:
                changed["cases"][mutation] = self.prior["cases"][mutation]
            with self.subTest(mutation=mutation), patch.object(skip_baseline_mod, "read_json", return_value=changed):
                with self.assertRaises(ValueError):
                    skip_baseline()

    def admit(self, baseline, nodeid):
        case = self.prior["cases"][nodeid]
        module = nodeid.split("::", 1)[0]
        body = {"execution_context": baseline["context"], "collection_skips": {},
                "junit_sha256": "a" * 64, "nonpassing_outcomes": [
                    {"nodeid": nodeid, "outcome": case["outcome"], "reason": case["reason"]}]}
        result = {"reference": body | {"assignment_id": "reference"},
                  "shards": [body | {"assignment_id": "ordinary-000"}]}
        historical, inputs = required_native_inputs(baseline)
        value = {"skip_module_blobs": {module: case["module_blob"]},
                 "skip_baseline_sha256": sha(baseline_bytes(baseline)),
                 "common_inputs": historical["common_inputs"] | inputs}
        with patch.object(skip_bindings_mod, "skip_baseline", return_value=baseline):
            return admit_skips(value, result, {})

    def test_retired_skips_fail_admission_and_unrelated_skips_still_work(self):
        for nodeid in self.removed:
            self.assertEqual(self.admit(self.prior, nodeid)["status"], "NO_NEW_SKIPS")
            with self.subTest(nodeid=nodeid), self.assertRaisesRegex(ValueError, "retired Nezha test"):
                self.admit(self.baseline, nodeid)
        unrelated = next(iter(self.baseline["cases"]))
        result = self.admit(self.baseline, unrelated)
        self.assertEqual(result["disposition_counts"]["HISTORICAL_UNEXECUTED"], 2)
        self.assertFalse(result["skips_are_passes"])

    def test_sidecar_history_rejects_changed_or_missing_baseline(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(transitions_native, "ROOT", root):
                with self.assertRaises(FileNotFoundError):
                    historical_skip_baseline_bytes()
                changed = copy.deepcopy(self.baseline)
                changed["events_sha256"] = "f" * 64
                (root / SKIP_BASELINE).write_bytes(baseline_bytes(changed))
                with self.assertRaisesRegex(ValueError, "changed historical baseline"):
                    historical_skip_baseline_bytes()
                (root / SKIP_BASELINE).write_bytes(baseline_bytes(self.prior))
                self.assertEqual(historical_skip_baseline_bytes(), baseline_bytes(self.prior))
