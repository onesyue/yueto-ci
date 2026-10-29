"""The reviewed skip blob successor moves only admitted skips to reviewed module blobs."""
import copy
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("skip_blob_shards", ROOT / "scripts/pytest-shards.py")
assert SPEC is not None and SPEC.loader is not None
SHARDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARDS)

KEY = "reviewed_skip_blob_successor_transition"
RUN_ID = "40552020790"
SOURCE_BEFORE = "bef6b202d896715df1801d94b163375b6d3b3c33"
SOURCE_AFTER = "ae6856f0bcc5579198c6e4b4c4d1ee4df107906e"
MODULES = {
    "tests/test_sshd_operator_native_20261009.py": (
        "eeb7b12d5594cfc951c26d3f039ced3fece2caef", "3f16a931133da90e3922da0aad1b1798af559448"),
    "tests/test_sshd_boundary_scope_native_20261008.py": (
        "d95bd432b2d28827153feae9d87db19262b9b64e", "31195dbde1b4d61e1985a4877097d76266ff24f2"),
    "tests/test_panel_subscribe_delivery_alert_20261012.py": (
        "9bb30b5940580d405ad0065b3a93e055c00c0285", "284a2914a0ce4aa2ffb89224fbe95cf1650f56ab"),
}
RECORD_SHA256 = "befa7b3d2cb2c5d3bbeb6e225f908087b1cd42c0bedbe290033a73b3fffe799d"
CASES_PER_MODULE = {
    "tests/test_sshd_operator_native_20261009.py": 6,
    "tests/test_sshd_boundary_scope_native_20261008.py": 8,
    "tests/test_panel_subscribe_delivery_alert_20261012.py": 1,
}
REVIEW_RECEIPT_SHA256 = "26750d5451ec06a463f03c9dc2ee78d8a5c0a8f94e6b6f67e54112000f83fd9f"


def review_document(record, historical):
    cases = []
    for nodeid in sorted(record["updates"]):
        change = record["updates"][nodeid]
        cases.append({
            "nodeid": nodeid, "verdict": "approve", "basis": "environmental",
            "outcome": "skipped", "reason": historical[nodeid]["reason"],
            "before_blob": change["before_blob"], "after_blob": change["after_blob"],
        })
    return {
        "kind": "independent-skip-blob-successor-review", "reviewer": "independent",
        "run_id": RUN_ID, "source_before": SOURCE_BEFORE, "source_after": SOURCE_AFTER,
        "review_receipt_sha256": REVIEW_RECEIPT_SHA256, "cases": cases,
    }


class SkipBlobSuccessorTransition(unittest.TestCase):
    def setUp(self):
        self.raw = (ROOT / "ops-pytest-skip-baseline.json").read_bytes()
        self.sealed = json.loads(self.raw)
        self.sealed, _ = SHARDS.reviewed_tornado66_dependency_transition(self.sealed)
        self.raw = (json.dumps(self.sealed, indent=2, ensure_ascii=False) + "\n").encode()
        self.record = self.sealed[KEY]
        self.original, record = SHARDS.reviewed_skip_blob_successor_transition(self.sealed)
        self.assertEqual(record, self.record)
        self.historical = self.original["cases"]
        self.after = {m: pair[1] for m, pair in MODULES.items()}
        self.before = {m: pair[0] for m, pair in MODULES.items()}

    def session(self, rows):
        body = {"execution_context": self.sealed["context"], "collection_skips": {},
                "junit_sha256": "b" * 64, "nonpassing_outcomes": rows}
        return {"reference": body | {"assignment_id": "reference"},
                "shards": [copy.deepcopy(body) | {"assignment_id": "ordinary-000"}]}

    def rows(self, nodeids):
        return [{"nodeid": n, "outcome": "skipped", "when": "setup",
                 "reason": self.historical[n]["reason"]} for n in sorted(nodeids)]

    def value(self, blobs):
        return {"skip_module_blobs": blobs, "skip_baseline_sha256": SHARDS.sha(self.raw),
                "common_inputs": self.sealed["common_inputs"]}

    def test_record_is_outermost_exact_and_pinned_to_the_review(self):
        canon = (json.dumps(self.sealed, indent=2, ensure_ascii=False) + "\n").encode()
        self.assertEqual(canon, self.raw)
        self.assertEqual(list(self.sealed)[-3:], [KEY, "reviewed_hang_guard_input_transition",
                         "reviewed_release_skip_blob_successor_transition"])
        restored = (json.dumps(self.original, indent=2, ensure_ascii=False) + "\n").encode()
        self.assertEqual(self.record["prior_baseline_sha256"], SHARDS.sha(restored))
        self.assertEqual((self.record["source_before"], self.record["source_after"]),
                         (SOURCE_BEFORE, SOURCE_AFTER))
        review = review_document(self.record, self.historical)
        self.assertEqual(self.record["independent_review_sha256"],
                         SHARDS.sha(SHARDS.encoded(review)))
        self.assertEqual(len(self.record["updates"]), 15)
        # The whole record, nodeids included, is pinned in the consumer and here.
        self.assertEqual(SHARDS.SKIP_BLOB_SUCCESSOR_TRANSITION_SHA256, RECORD_SHA256)
        self.assertEqual(SHARDS.sha(SHARDS.encoded(self.record)), RECORD_SHA256)
        per_module = {}
        for nodeid in self.record["updates"]:
            module = nodeid.split("::", 1)[0]
            per_module[module] = per_module.get(module, 0) + 1
        self.assertEqual(per_module, CASES_PER_MODULE)
        for nodeid, change in self.record["updates"].items():
            module = nodeid.split("::", 1)[0]
            self.assertEqual((change["before_blob"], change["after_blob"]), MODULES[module])
            self.assertEqual(self.historical[nodeid]["module_blob"], change["before_blob"])
            self.assertEqual(self.historical[nodeid]["outcome"], "skipped")
        # Every other seal peels the outer record first and sees the historical bytes.
        for peel in (SHARDS.reviewed_runtime_dependency_transition,
                     SHARDS.reviewed_audit_lock_transition,
                     SHARDS.reviewed_bot_packaging_transition,
                     SHARDS.reviewed_case_file_transition,
                     SHARDS.reviewed_site_lock_transition,
                     SHARDS.reviewed_estate_input_transition):
            historical, _ = peel(self.sealed)
            self.assertNotIn(KEY, historical)

    def test_consumer_admits_reviewed_blobs_and_still_admits_the_historical_blobs(self):
        result = self.session(self.rows(self.record["updates"]))
        for blobs in (self.after, self.before):
            with self.subTest(blobs=blobs):
                accepted = SHARDS.admit_skips(self.value(blobs), result, {"obligations": {}})
                self.assertEqual(accepted["status"], "NO_NEW_SKIPS")
                self.assertIs(accepted["skips_are_passes"], False)
                self.assertEqual(accepted["disposition_counts"]["HISTORICAL_UNEXECUTED"], 30)

    def test_consumer_refuses_other_blobs_reasons_outcomes_and_cases(self):
        result = self.session(self.rows(self.record["updates"]))
        module = next(iter(MODULES))
        with self.assertRaisesRegex(ValueError, "new or changed case"):
            SHARDS.admit_skips(self.value(self.after | {module: "f" * 40}), result, {})
        for field, replacement in (("reason", "Skipped: changed reason"), ("outcome", "xfailed"),
                                   ("nodeid", module + "::test_unreviewed")):
            changed = copy.deepcopy(result)
            changed["shards"][0]["nonpassing_outcomes"][0][field] = replacement
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "new or changed case"):
                SHARDS.admit_skips(self.value(self.after), changed, {})
        # Without the seal the reviewed successor blobs are refused exactly as in run 40552020790.
        stripped = copy.deepcopy(self.sealed)
        stripped.pop("reviewed_release_skip_blob_successor_transition")
        stripped.pop("reviewed_hang_guard_input_transition")
        stripped.pop(KEY)
        with (patch.object(SHARDS, "skip_baseline", return_value=stripped),
              self.assertRaisesRegex(ValueError, "new or changed case")):
            SHARDS.admit_skips(self.value(self.after), result, {})

    def test_damaged_records_are_refused(self):
        nodeid = sorted(self.record["updates"])[0]
        other = sorted(self.record["updates"])[-1]
        def damaged(mutate):
            baseline = copy.deepcopy(self.sealed)
            baseline.pop("reviewed_release_skip_blob_successor_transition")
            baseline.pop("reviewed_hang_guard_input_transition")  # outer seal over this one
            mutate(baseline[KEY])
            return baseline
        for mutate in (
            lambda r: r.__setitem__("prior_baseline_sha256", "f" * 64),
            lambda r: r.__setitem__("source_after", r["source_before"]),
            lambda r: r.__setitem__("source_before", "x"),
            lambda r: r.__setitem__("independent_review_sha256", "0" * 64),
            lambda r: r.__setitem__("independent_review_sha256", "x"),
            lambda r: r.__setitem__("schema", True),
            lambda r: r.__setitem__("extra", 1),
            lambda r: r.__setitem__("updates", {}),
            lambda r: r["updates"][nodeid].__setitem__("after_blob", r["updates"][nodeid]["before_blob"]),
            lambda r: r["updates"][nodeid].__setitem__("after_blob", "z" * 40),
            lambda r: r["updates"][nodeid].__setitem__("extra", 1),
            lambda r: r["updates"].__setitem__("../escape.py::test_x", dict(r["updates"][nodeid])),
            lambda r: r["updates"].__setitem__(nodeid.split("::")[0] + "::test_more",
                                               {"before_blob": r["updates"][nodeid]["before_blob"],
                                                "after_blob": "e" * 40}),
        ):
            for consumer in (SHARDS.reviewed_skip_blob_successor_transition,
                             SHARDS.reviewed_runtime_dependency_transition,
                             SHARDS.reviewed_case_file_transition,
                             SHARDS.reviewed_estate_input_transition):
                with self.subTest(mutate=mutate, consumer=consumer.__name__), \
                        self.assertRaisesRegex(ValueError, "skip blob successor"):
                    consumer(damaged(mutate))
            # Even with the record pin re-pointed at the damaged record, its shape is refused.
            baseline = damaged(mutate)
            repinned = SHARDS.sha(SHARDS.encoded(baseline[KEY]))
            with self.subTest(mutate=mutate, repinned=True), \
                    patch.object(SHARDS, "SKIP_BLOB_SUCCESSOR_TRANSITION_SHA256", repinned), \
                    self.assertRaises(ValueError) as refused:
                SHARDS.reviewed_skip_blob_successor_transition(baseline)
            self.assertNotIn("transition identity", str(refused.exception))
        self.assertNotEqual(nodeid, other)

    def test_swapped_nodeid_with_recomputed_review_is_refused_by_the_pin(self):
        baseline = copy.deepcopy(self.sealed)
        baseline.pop("reviewed_release_skip_blob_successor_transition")
        baseline.pop("reviewed_hang_guard_input_transition")  # outer seal over this one
        updates = baseline[KEY]["updates"]
        nodeid = sorted(n for n in updates if "panel_subscribe" in n)[0]
        swapped = nodeid.split("::")[0] + "::test_some_other_case"
        updates[swapped] = updates.pop(nodeid)
        historical = dict(self.historical)
        historical[swapped] = historical[nodeid]
        baseline[KEY]["independent_review_sha256"] = SHARDS.sha(
            SHARDS.encoded(review_document(baseline[KEY], historical)))
        with self.assertRaisesRegex(ValueError, "transition identity$"):
            SHARDS.reviewed_skip_blob_successor_transition(baseline)

    def test_update_must_succeed_an_admitted_skip(self):
        admitted = copy.deepcopy(self.historical)
        nodeid = sorted(self.record["updates"])[0]
        for mutate in (
            lambda a: a.pop(nodeid),
            lambda a: a[nodeid].__setitem__("module_blob", "d" * 40),
            lambda a: a[nodeid].__setitem__("outcome", "xfailed"),
            lambda a: a[nodeid].__setitem__("reason", ""),
        ):
            changed = copy.deepcopy(admitted)
            mutate(changed)
            with self.subTest(mutate=mutate), self.assertRaisesRegex(ValueError, "admitted skip"):
                SHARDS.skip_blob_successors(self.record, changed, {})
        with self.assertRaisesRegex(ValueError, "admitted skip"):
            SHARDS.skip_blob_successors(self.record, admitted, {nodeid: {}})
        self.assertEqual(SHARDS.skip_blob_successors(None, admitted, {}), {})


if __name__ == "__main__":
    unittest.main()
