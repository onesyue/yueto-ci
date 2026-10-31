"""G succeeds one release-sealed ordinary skip; hosted admissions remain unchanged."""
import copy
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("i10_shards", ROOT / "scripts/pytest-shards.py")
SHARDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARDS)
KEY = "reviewed_i10_skip_blob_successor_transition"
MODULE = "tests/test_entry_diagnostics_signed_closure_20261008.py"
NODE = MODULE + "::test_real_linux_signed_fixture_when_explicitly_requested"
BEFORE = "3b3443dcf3a8fa9bce9cfa57da51969e2ab7ea1a"
AFTER = "74403b075bb053e563ad5fc5a3a1461c6be49e60"


class I10SkipBlobSuccessorTransition(unittest.TestCase):
    def setUp(self):
        self.baseline = json.loads((ROOT / SHARDS.SKIP_BASELINE).read_bytes())
        self.baseline, _ = SHARDS.reviewed_ops_packaging_transition(self.baseline)
        self.prior, self.record = SHARDS.reviewed_i10_skip_blob_successor_transition(self.baseline)
        self.value = {
            "skip_module_blobs": {MODULE: AFTER},
            "skip_baseline_sha256": SHARDS.sha(SHARDS.baseline_bytes(self.baseline)),
            "common_inputs": self.baseline["common_inputs"] | SHARDS.NATIVE_INPUTS,
        }
        row = {"nodeid": NODE, "outcome": "skipped", "when": "setup",
               "reason": self.baseline["cases"][NODE]["reason"]}
        body = {"execution_context": self.baseline["context"], "collection_skips": {},
                "junit_sha256": "b" * 64, "nonpassing_outcomes": [row]}
        self.result = {"reference": body | {"assignment_id": "reference"},
                       "shards": [copy.deepcopy(body) | {"assignment_id": "ordinary-000"}]}

    def admit(self, value=None, result=None):
        return SHARDS.admit_skips(value or self.value, result or self.result, {"obligations": {}})

    def test_exact_outer_seal_and_source_review(self):
        self.assertEqual(list(self.baseline)[-1], KEY)
        self.assertEqual(self.record["prior_baseline_sha256"],
                         SHARDS.sha(SHARDS.baseline_bytes(self.prior)))
        self.assertEqual(self.record["updates"], {NODE: {"before_blob": BEFORE, "after_blob": AFTER}})
        self.assertEqual(self.record["source_before"], "e18f0ec8ccd21bacc8e249238ed89a8774ba8347")
        self.assertEqual(self.record["source_after"], "5277e42a459bd1d530e4eea97f4056af7f3d529f")
        self.assertEqual(self.record["independent_review_sha256"], SHARDS.sha(
            (ROOT / "reviews/ops-i10-skip-blob-5277e42a.md").read_bytes()))
        self.assertEqual(SHARDS.sha(SHARDS.encoded(self.record)),
                         SHARDS.I10_SKIP_BLOB_SUCCESSOR_TRANSITION_SHA256)
        self.assertNotIn(NODE, self.prior["reviewed_hosted"]["cases"])
        self.assertEqual(self.prior["reviewed_release_skip_blob_successor_transition"]
                         ["updates"][NODE]["after_blob"], BEFORE)
        for consumer in (SHARDS.reviewed_retired_host_transition, SHARDS.required_native_inputs,
                         SHARDS.reviewed_tornado66_dependency_transition,
                         SHARDS.reviewed_release_skip_blob_successor_transition,
                         SHARDS.reviewed_estate_input_transition):
            self.assertEqual(consumer(self.baseline), consumer(self.prior))

    def test_red_before_green_after_and_historical_blobs(self):
        with patch.object(SHARDS, "skip_baseline", return_value=self.prior):
            with self.assertRaisesRegex(ValueError, "new or changed case skip/xfail: " + NODE):
                self.admit()
        for blob in (AFTER, BEFORE, self.prior["cases"][NODE]["module_blob"]):
            with self.subTest(blob=blob):
                accepted = self.admit(self.value | {"skip_module_blobs": {MODULE: blob}})
                self.assertEqual(accepted["status"], "NO_NEW_SKIPS")
                self.assertIs(accepted["skips_are_passes"], False)
                self.assertEqual(accepted["disposition_counts"]["HISTORICAL_UNEXECUTED"], 2)

    def test_unknown_blob_reason_outcome_and_new_case_rejected(self):
        with self.assertRaisesRegex(ValueError, "new or changed case"):
            self.admit(self.value | {"skip_module_blobs": {MODULE: "f" * 40}})
        for field, value in (("reason", "Skipped: other reason"), ("outcome", "xfailed"),
                             ("nodeid", MODULE + "::test_new")):
            changed = copy.deepcopy(self.result)
            changed["shards"][0]["nonpassing_outcomes"][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "new or changed case"):
                self.admit(result=changed)

    def test_other_hosted_case_retains_blob_variant_context_and_native_gates(self):
        node, case = next(iter(self.baseline["reviewed_hosted"]["cases"].items()))
        module = node.split("::")[0]
        row = {"nodeid": node, "outcome": case["outcome"], **case["variants"][0]}
        result = copy.deepcopy(self.result)
        for session in (result["reference"], *result["shards"]):
            session["nonpassing_outcomes"] = [dict(row)]
        value = self.value | {"skip_module_blobs": {module: case["module_blob"]},
                              "ops_plan": {"context": self.baseline["reviewed_hosted"]["runner"]}}
        native = {"obligations": {case.get("native_target"): {"passed": [node]}}}
        self.assertEqual(SHARDS.admit_skips(value, result, native)["status"], "NO_NEW_SKIPS")
        for field, replacement in (("reason", "Skipped: changed"), ("outcome", "xfailed"),
                                   ("when", "unreviewed-phase")):
            changed = copy.deepcopy(result)
            changed["shards"][0]["nonpassing_outcomes"][0][field] = replacement
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "new or changed case"):
                SHARDS.admit_skips(value, changed, native)
        for blob in (AFTER, "f" * 40):
            with self.assertRaisesRegex(ValueError, "new or changed case"):
                SHARDS.admit_skips(value | {"skip_module_blobs": {module: blob}}, result, native)
        with self.assertRaisesRegex(ValueError, "new or changed case"):
            SHARDS.admit_skips(value | {"ops_plan": {"context": {}}}, result, native)
        if case["disposition"] == "SAME_RUN_NATIVE_REQUIRED":
            with self.assertRaisesRegex(ValueError, "missing exact same-run native"):
                SHARDS.admit_skips(value, result, {"obligations": {}})

    def test_predecessor_must_be_ordinary_admitted_skip(self):
        historical = self.prior["cases"][NODE] | {"module_blob": BEFORE}
        for changed in ({}, {NODE: historical | {"module_blob": "d" * 40}},
                        {NODE: historical | {"outcome": "xfailed"}},
                        {NODE: historical | {"reason": ""}}):
            with self.assertRaisesRegex(ValueError, "admitted skip"):
                SHARDS.skip_blob_successors(self.record, changed, {})
        with self.assertRaisesRegex(ValueError, "admitted skip"):
            SHARDS.skip_blob_successors(self.record, {NODE: historical}, {NODE: historical})

    def test_record_mutations_and_historical_changes_rejected(self):
        mutations = (
            lambda r: r.update(prior_baseline_sha256="f" * 64),
            lambda r: r.update(source_after=r["source_before"]),
            lambda r: r.update(source_before="bad"),
            lambda r: r.update(independent_review_sha256="0" * 64),
            lambda r: r.update(schema=True),
            lambda r: r.update(extra=True),
            lambda r: r.update(updates={}),
            lambda r: r["updates"][NODE].update(after_blob=BEFORE),
            lambda r: r["updates"][NODE].update(after_blob="z" * 40),
            lambda r: r["updates"][NODE].update(extra=True),
        )
        for mutate in mutations:
            changed = copy.deepcopy(self.baseline)
            mutate(changed[KEY])
            for consumer in (SHARDS.reviewed_i10_skip_blob_successor_transition,
                             SHARDS.reviewed_estate_input_transition):
                with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                    consumer(changed)
            with patch.object(SHARDS, "I10_SKIP_BLOB_SUCCESSOR_TRANSITION_SHA256",
                              SHARDS.sha(SHARDS.encoded(changed[KEY]))), self.assertRaises(ValueError):
                SHARDS.reviewed_i10_skip_blob_successor_transition(changed)
        changed = copy.deepcopy(self.baseline)
        changed["cases"][NODE]["reason"] = "changed"
        with self.assertRaisesRegex(ValueError, "historical baseline"):
            SHARDS.reviewed_i10_skip_blob_successor_transition(changed)
        changed = copy.deepcopy(self.baseline)
        changed[KEY]["updates"][MODULE + "::test_new"] = changed[KEY]["updates"].pop(NODE)
        with self.assertRaisesRegex(ValueError, "transition identity"):
            SHARDS.reviewed_i10_skip_blob_successor_transition(changed)


if __name__ == "__main__":
    unittest.main()
