"""Owner-retired Nezha skips leave the active baseline without rewriting history."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("nezha_shards", ROOT / "scripts/pytest-shards.py")
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class NezhaRetirement(unittest.TestCase):
    def setUp(self):
        self.baseline = M.skip_baseline()
        self.prior = M.restore_nezha_history(self.baseline)
        self.removed = [n for n in self.prior["cases"]
                        if n.startswith(M.NEZHA_RETIRED_MODULE + "::")]

    def test_exact_deletion_preserves_format_order_and_historical_hashes(self):
        raw = (ROOT / M.SKIP_BASELINE).read_bytes()
        self.assertEqual(raw, M.baseline_bytes(self.baseline))
        self.assertNotIn(M.NEZHA_RETIRED_MODULE.encode(), raw)
        self.assertEqual(len(self.baseline["cases"]), 1000)
        self.assertEqual(len(self.removed), 2)
        expected = copy.deepcopy(self.prior)
        for nodeid in self.removed:
            del expected["cases"][nodeid]
        expected[M.NEZHA_RETIREMENT_KEY] = self.baseline[M.NEZHA_RETIREMENT_KEY]
        predecessor, _ = M.reviewed_native_input_successor(self.baseline)
        self.assertEqual(M.baseline_bytes(expected), M.baseline_bytes(predecessor))
        self.assertEqual(M.sha(M.baseline_bytes(self.prior)), M.NEZHA_PRIOR_BASELINE_SHA256)
        self.assertEqual(M.historical_skip_baseline_bytes(), M.baseline_bytes(self.prior))
        # The returned history is independent of the active case mapping.
        self.assertTrue(set(self.removed).isdisjoint(self.baseline["cases"]))

    def test_missing_or_altered_retirement_record_is_rejected(self):
        for field, value in ((None, None), ("schema", True), ("removed_case_count", 1),
                             ("prior_baseline_sha256", "f" * 64)):
            changed = copy.deepcopy(self.baseline)
            if field is None:
                del changed[M.NEZHA_RETIREMENT_KEY]
            else:
                changed[M.NEZHA_RETIREMENT_KEY][field] = value
            with self.subTest(field=field), patch.object(M, "read_json", return_value=changed):
                with self.assertRaises(ValueError):
                    M.skip_baseline()

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
            with self.subTest(mutation=mutation), patch.object(M, "read_json", return_value=changed):
                with self.assertRaises(ValueError):
                    M.skip_baseline()

    def admit(self, baseline, nodeid):
        case = self.prior["cases"][nodeid]
        module = nodeid.split("::", 1)[0]
        body = {"execution_context": baseline["context"], "collection_skips": {},
                "junit_sha256": "a" * 64, "nonpassing_outcomes": [
                    {"nodeid": nodeid, "outcome": case["outcome"], "reason": case["reason"]}]}
        result = {"reference": body | {"assignment_id": "reference"},
                  "shards": [body | {"assignment_id": "ordinary-000"}]}
        historical, inputs = M.required_native_inputs(baseline)
        value = {"skip_module_blobs": {module: case["module_blob"]},
                 "skip_baseline_sha256": M.sha(M.baseline_bytes(baseline)),
                 "common_inputs": historical["common_inputs"] | inputs}
        with patch.object(M, "skip_baseline", return_value=baseline):
            return M.admit_skips(value, result, {})

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
            with patch.object(M, "ROOT", root):
                with self.assertRaises(FileNotFoundError):
                    M.historical_skip_baseline_bytes()
                changed = copy.deepcopy(self.baseline)
                changed["events_sha256"] = "f" * 64
                (root / M.SKIP_BASELINE).write_bytes(M.baseline_bytes(changed))
                with self.assertRaisesRegex(ValueError, "changed historical baseline"):
                    M.historical_skip_baseline_bytes()
                (root / M.SKIP_BASELINE).write_bytes(M.baseline_bytes(self.prior))
                self.assertEqual(M.historical_skip_baseline_bytes(), M.baseline_bytes(self.prior))
