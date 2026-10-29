"""The reviewed release skip blob successor moves only admitted skips to reviewed module blobs."""
import copy
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("release_skip_blob_shards",
                                              ROOT / "scripts/pytest-shards.py")
assert SPEC is not None and SPEC.loader is not None
SHARDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARDS)

KEY = "reviewed_release_skip_blob_successor_transition"
RUN_ID = "40578720805"
SOURCE_BEFORE = "8ffdedad24dcb23ca0c33a05ea0ea889cbdab0fe"
SOURCE_AFTER = "d9c302e126c039e90b5f34c82b796582b1e367e8"
# module: (admitted before blob, reviewed after blob, reviewed cases)
MODULES = {
    "tests/test_agent_rollback_payload_20261013.py": (
        "4e63ad7e168512c3317749dbbed031b6276376d9", "7bbe1bae33d206b38634888ad2a4734e5a1754ef", 1),
    "tests/test_boot_container_reconcile_lock.py": (
        "56cd97b4a04eb17fac54841ce65358fea87be0a7", "aa63d4180d06a939df28a8fba2f45109a0d0bc7f", 12),
    "tests/test_cadvisor_persistent_owner.py": (
        "1b546609f02b20df89363f493e13c71b1dbaae3a", "1ca96a2971e121affc89220d09d3228aa4e0a772", 7),
    "tests/test_cert_renew_log_dir_20260815.py": (
        "78743dca4a3211d62b5059f84b6bf6fe2a43bfd2", "b545a93d93baf5591cec4e609ec9c07812218b34", 1),
    "tests/test_cleanup_hostpatch_guard.py": (
        "700443e48165fe0132b6ed8e91df5a0186030d00", "f536ee76a01e4f7d4c395ea018ecf688dfe2517f", 107),
    "tests/test_entry_diagnostics_signed_closure_20261008.py": (
        "1a88653d038cb780b4eefd6a8b28718e801d1b5e", "3b3443dcf3a8fa9bce9cfa57da51969e2ab7ea1a", 1),
    "tests/test_host_diagnostic_tools.py": (
        "545ebff82f64aa4ad1d6b7b056a6f9817fc29c3f", "9b069353a1cdb89639f7c856d90f6922dd1f6bde", 6),
    "tests/test_host_runtime_converger_owns_sentinel_20261005.py": (
        "d527ab3c0417d44a38683318724634c7b673f8bd", "a0edcebe36745ab381fb58b405aeae62a83616b6", 1),
    "tests/test_independent_subscription_origin_20261012.py": (
        "9a9d2b964e7c351ba52256711e2dbbfc4d81513e", "b5d647222f714528474fe9ff9749a9d1c174ebf2", 42),
    "tests/test_node_resource_consumers.py": (
        "cfed1a776576b7e62a75a124043ac3fe566a2bc8", "ba7b0a20dcb051274bd38a9d1d6d658a22400446", 16),
    "tests/test_node_systemd_legacy_interlock_20261018.py": (
        "256fd472b326ad176f9d5d6fd546b802b6bf11f1", "757f66662b0ee4e430e20eb9a0e2d9eeeaf69ad7", 12),
    "tests/test_node_systemd_runtime_20261018.py": (
        "271eaabce8df0c769a33ff78789c30fd02ca023e", "c0175bae787b314890bbf46c2ef25dc58547e82c", 13),
    "tests/test_panel_backend_bootstrap_20261019.py": (
        "5b3f95b91a67c7c8ff8d438fd5c7d906a0406462", "5d6095b1b51cf75c756d5d405834703a84080802", 2),
    "tests/test_relay_buffer_transaction_20261013.py": (
        "db3609c2bba5128d1d1be952a30cbe7a44ed1dd0", "f08bbb7f773c4ba65c8c793533a0a69e0c7063df", 27),
    "tests/test_relay_coordinator_delivery_closure_20260905.py": (
        "a954d431f4e9b2327b3f952f2b7ac4d1b5c3cf30", "89a5553d408705adb39c7f703a4f3b0325b49171", 23),
    "tests/test_relay_nginx_output_order_20261009.py": (
        "201bcd8cba4eeccca55c221e898cd3f9a06714cc", "09a3fe42fb73422c5d1ab49549721c1c9ddd497d", 3),
    "tests/test_schema_contract_receipt_20261020.py": (
        "24ebf12305f69861acd22225575edccc0d40ba45", "8bbe33fd3e70bfe899d9ed1005e9c9437935243e", 30),
}
RECORD_SHA256 = "efa7c2e8c9944feeccbcf0bf1111b3b4b67f8b15c94e1b6d41879654136d274b"
REVIEW_RECEIPT_SHA256 = "bea31a6cb5c97a5de4bcc46febf9ec3430683082ecc38a8d93b2f7f5e38ce469"


def admitted_cases(sealed):
    """Every admitted skip the release seal may succeed, exactly as admit_skips composes it."""
    _, blob_record = SHARDS.reviewed_skip_blob_successor_transition(sealed)
    _, case_successors = SHARDS.reviewed_case_file_transition(sealed)
    baseline, _ = SHARDS.reviewed_estate_input_transition(sealed)
    baseline, preservation = SHARDS.reviewed_relay_preservation_module_transition(baseline)
    baseline, meter = SHARDS.reviewed_relay_meter_module_transition(baseline)
    baseline, metrics = SHARDS.reviewed_relay_metrics_module_transition(baseline)
    baseline, relay = SHARDS.reviewed_relay_skip_module_transition(baseline)
    baseline, extra = SHARDS.reviewed_current_skip_transition(baseline)
    _, successors = SHARDS.reviewed_skip_module_transition(baseline)
    successors.update(extra)
    admitted = {n: dict(c) for n, c in baseline["cases"].items()}
    for mapping in (successors, relay, metrics, meter, preservation, case_successors):
        admitted.update(mapping)
    hosted = baseline.get("reviewed_hosted", {}).get("cases", {})
    admitted.update(SHARDS.skip_blob_successors(blob_record, admitted, hosted))
    return admitted, hosted


def review_document(record, admitted):
    cases = []
    for nodeid in sorted(record["updates"]):
        change = record["updates"][nodeid]
        cases.append({
            "nodeid": nodeid, "verdict": "approve", "basis": "environmental",
            "outcome": "skipped", "reason": admitted[nodeid]["reason"],
            "before_blob": change["before_blob"], "after_blob": change["after_blob"],
        })
    return {
        "kind": "independent-skip-blob-successor-review", "reviewer": "independent",
        "run_id": RUN_ID, "source_before": SOURCE_BEFORE, "source_after": SOURCE_AFTER,
        "review_receipt_sha256": REVIEW_RECEIPT_SHA256, "cases": cases,
    }


class ReleaseSkipBlobSuccessorTransition(unittest.TestCase):
    def setUp(self):
        self.raw = (ROOT / "ops-pytest-skip-baseline.json").read_bytes()
        self.sealed = json.loads(self.raw)
        self.sealed, _ = SHARDS.reviewed_tornado66_dependency_transition(self.sealed)
        self.raw = (json.dumps(self.sealed, indent=2, ensure_ascii=False) + "\n").encode()
        self.record = self.sealed[KEY]
        self.original, record = SHARDS.reviewed_release_skip_blob_successor_transition(self.sealed)
        self.assertEqual(record, self.record)
        self.admitted, self.hosted = admitted_cases(self.sealed)
        self.after = {m: v[1] for m, v in MODULES.items()}
        self.before = {m: v[0] for m, v in MODULES.items()}

    def session(self, rows):
        body = {"execution_context": self.sealed["context"], "collection_skips": {},
                "junit_sha256": "b" * 64, "nonpassing_outcomes": rows}
        return {"reference": body | {"assignment_id": "reference"},
                "shards": [copy.deepcopy(body) | {"assignment_id": "ordinary-000"}]}

    def rows(self, nodeids):
        return [{"nodeid": n, "outcome": "skipped", "when": "setup",
                 "reason": self.admitted[n]["reason"]} for n in sorted(nodeids)]

    def value(self, blobs):
        return {"skip_module_blobs": blobs, "skip_baseline_sha256": SHARDS.sha(self.raw),
                "common_inputs": self.sealed["common_inputs"]}

    def test_record_is_outermost_exact_and_pinned_to_the_review(self):
        canon = (json.dumps(self.sealed, indent=2, ensure_ascii=False) + "\n").encode()
        self.assertEqual(canon, self.raw)
        self.assertEqual(list(self.sealed)[-1], KEY)
        restored = (json.dumps(self.original, indent=2, ensure_ascii=False) + "\n").encode()
        self.assertEqual(self.record["prior_baseline_sha256"], SHARDS.sha(restored))
        self.assertEqual((self.record["source_before"], self.record["source_after"]),
                         (SOURCE_BEFORE, SOURCE_AFTER))
        review = review_document(self.record, self.admitted)
        self.assertEqual(self.record["independent_review_sha256"],
                         SHARDS.sha(SHARDS.encoded(review)))
        self.assertEqual(len(self.record["updates"]), 304)
        self.assertEqual(SHARDS.RELEASE_SKIP_BLOB_SUCCESSOR_TRANSITION_SHA256, RECORD_SHA256)
        self.assertEqual(SHARDS.sha(SHARDS.encoded(self.record)), RECORD_SHA256)
        per_module = {}
        for nodeid, change in self.record["updates"].items():
            module = nodeid.split("::", 1)[0]
            per_module[module] = per_module.get(module, 0) + 1
            self.assertEqual((change["before_blob"], change["after_blob"]), MODULES[module][:2])
            self.assertNotIn(nodeid, self.hosted)
            self.assertEqual(self.admitted[nodeid]["module_blob"], change["before_blob"])
            self.assertEqual(self.admitted[nodeid]["outcome"], "skipped")
        self.assertEqual(per_module, {m: v[2] for m, v in MODULES.items()})
        # No update overlaps the first skip blob successor seal.
        first = self.sealed["reviewed_skip_blob_successor_transition"]["updates"]
        self.assertFalse(set(first) & set(self.record["updates"]))
        # Every other seal peels this record first and sees the historical bytes.
        for peel in (SHARDS.reviewed_hang_guard_input_transition,
                     SHARDS.reviewed_skip_blob_successor_transition,
                     SHARDS.reviewed_runtime_dependency_transition,
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
                self.assertEqual(accepted["disposition_counts"]["HISTORICAL_UNEXECUTED"], 608)

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
        # Without the seal the reviewed successor blobs are refused exactly as before.
        stripped = copy.deepcopy(self.sealed)
        stripped.pop(KEY)
        with (patch.object(SHARDS, "skip_baseline", return_value=stripped),
              self.assertRaisesRegex(ValueError, "new or changed case")):
            SHARDS.admit_skips(self.value(self.after), result, {})

    def test_damaged_records_are_refused(self):
        nodeid = sorted(self.record["updates"])[0]
        def damaged(mutate):
            baseline = copy.deepcopy(self.sealed)
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
            for consumer in (SHARDS.reviewed_release_skip_blob_successor_transition,
                             SHARDS.reviewed_hang_guard_input_transition,
                             SHARDS.reviewed_skip_blob_successor_transition,
                             SHARDS.reviewed_runtime_dependency_transition,
                             SHARDS.reviewed_case_file_transition,
                             SHARDS.reviewed_estate_input_transition):
                with self.subTest(mutate=mutate, consumer=consumer.__name__), \
                        self.assertRaisesRegex(ValueError, "release skip blob successor"):
                    consumer(damaged(mutate))
            # Even with the record pin re-pointed at the damaged record, its shape is refused.
            baseline = damaged(mutate)
            repinned = SHARDS.sha(SHARDS.encoded(baseline[KEY]))
            with self.subTest(mutate=mutate, repinned=True), \
                    patch.object(SHARDS, "RELEASE_SKIP_BLOB_SUCCESSOR_TRANSITION_SHA256", repinned), \
                    self.assertRaises(ValueError) as refused:
                SHARDS.reviewed_release_skip_blob_successor_transition(baseline)
            self.assertNotIn("transition identity", str(refused.exception))

    def test_swapped_nodeid_with_recomputed_review_is_refused_by_the_pin(self):
        baseline = copy.deepcopy(self.sealed)
        updates = baseline[KEY]["updates"]
        nodeid = sorted(updates)[0]
        swapped = nodeid.split("::")[0] + "::test_some_other_case"
        updates[swapped] = updates.pop(nodeid)
        admitted = dict(self.admitted)
        admitted[swapped] = admitted[nodeid]
        baseline[KEY]["independent_review_sha256"] = SHARDS.sha(
            SHARDS.encoded(review_document(baseline[KEY], admitted)))
        with self.assertRaisesRegex(ValueError, "transition identity$"):
            SHARDS.reviewed_release_skip_blob_successor_transition(baseline)

    def test_update_must_succeed_an_admitted_skip(self):
        nodeid = sorted(self.record["updates"])[0]
        for mutate in (
            lambda a: a.pop(nodeid),
            lambda a: a[nodeid].__setitem__("module_blob", "d" * 40),
            lambda a: a[nodeid].__setitem__("outcome", "xfailed"),
            lambda a: a[nodeid].__setitem__("reason", ""),
        ):
            changed = copy.deepcopy(self.admitted)
            mutate(changed)
            with self.subTest(mutate=mutate), self.assertRaisesRegex(ValueError, "admitted skip"):
                SHARDS.skip_blob_successors(self.record, changed, {})
        with self.assertRaisesRegex(ValueError, "admitted skip"):
            SHARDS.skip_blob_successors(self.record, self.admitted, {nodeid: {}})


if __name__ == "__main__":
    unittest.main()
