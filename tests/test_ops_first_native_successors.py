"""Exact first-release successors preserve historical and native obligations."""

import copy
import importlib.util
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("first_native_shards", ROOT / "scripts/pytest-shards.py")
assert SPEC and SPEC.loader
SHARDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARDS)
BOARD = "tests/test_board139_schema_acl_native_20261018.py"
BACKUP = "tests/test_critical_key_restore_gate_mutations_20260903.py"


class FirstNativeSuccessors(unittest.TestCase):
    def setUp(self):
        self.raw = (ROOT / "ops-pytest-skip-baseline.json").read_bytes()
        self.baseline = json.loads(self.raw)
        self.board_value = {"skip_module_blobs": {BOARD: "2d510c6a2e765ae7eb0379ab7671ba64d6770ef4"}}
        self.backup_value = {"skip_module_blobs": {BACKUP: "a609746c0f11d0965861bbecd25044c659c5eabe"}}
        self.previous = sorted(k for k in self.baseline["reviewed_hosted"]["cases"] if k.startswith(BOARD + "::"))
        self.added = BOARD + "::test_actual_bootstrap_and_audit_stay_strict_around_orders_archive"
        self.native = {"obligations": {BOARD: {"passed": self.previous + [self.added]}}}

    def test_board_successor_requires_seven_calls_without_editing_historical_baseline(self):
        result = SHARDS.reviewed_board139_native_successor(self.baseline, self.board_value, self.native)
        rows = {k: v for k, v in result["reviewed_hosted"]["cases"].items() if k.startswith(BOARD + "::")}
        self.assertEqual(set(rows), set(self.previous + [self.added]))
        self.assertTrue(all(row["disposition"] == "SAME_RUN_NATIVE_REQUIRED" for row in rows.values()))
        self.assertEqual(self.baseline, json.loads(self.raw))
        self.assertEqual((ROOT / "ops-pytest-skip-baseline.json").read_bytes(), self.raw)

    def test_board_missing_extra_or_duplicate_native_call_is_rejected(self):
        for calls in (self.previous, self.previous + [self.added, BOARD + "::unreviewed"],
                      self.previous + [self.added, self.added]):
            with self.subTest(calls=calls), self.assertRaisesRegex(ValueError, "seven exact"):
                SHARDS.reviewed_board139_native_successor(self.baseline, self.board_value,
                                                          {"obligations": {BOARD: {"passed": calls}}})

    def test_board_historical_reason_blob_disposition_or_identity_cannot_change(self):
        for field, replacement in (("module_blob", "f" * 40), ("outcome", "passed"),
                                   ("disposition", "HISTORICAL_UNEXECUTED"), ("variants", [])):
            altered = copy.deepcopy(self.baseline)
            altered["reviewed_hosted"]["cases"][self.previous[0]][field] = replacement
            with self.subTest(field=field), self.assertRaises(ValueError):
                SHARDS.reviewed_board139_native_successor(altered, self.board_value, self.native)
        altered = copy.deepcopy(self.baseline)
        del altered["reviewed_hosted"]["cases"][self.previous[0]]
        with self.assertRaises(ValueError):
            SHARDS.reviewed_board139_native_successor(altered, self.board_value, self.native)

    def test_unknown_board_blob_receives_no_inheritance(self):
        self.assertIs(SHARDS.reviewed_board139_native_successor(
            self.baseline, {"skip_module_blobs": {BOARD: "f" * 40}}, self.native), self.baseline)

    def test_renewal_blob_requires_the_twenty_two_native_calls(self):
        renewal = "0509528f81cd39c6e308e130650670a874b1b3df"
        names = (
            "test_actual_renewal_audit_rejects_extra_callers[PUBLIC-function-exchange_points_renewal(bigint, bigint, text)-]",
            "test_actual_renewal_audit_rejects_extra_callers[PUBLIC-function-renewal_credit_month(timestamp with time zone)-]",
            "test_actual_renewal_audit_rejects_extra_callers[PUBLIC-function-renewal_credit_state(bigint)-yueboard_runtime:EXECUTE:false]",
            "test_actual_renewal_audit_rejects_extra_callers[PUBLIC-function-reserve_order_renewal_credit()-]",
            "test_actual_renewal_audit_rejects_extra_callers[PUBLIC-sequence-renewal_credit_exchanges_id_seq-]",
            "test_actual_renewal_audit_rejects_extra_callers[app_yue_bot-function-exchange_points_renewal(bigint, bigint, text)-]",
            "test_actual_renewal_audit_rejects_extra_callers[app_yue_bot-function-renewal_credit_month(timestamp with time zone)-]",
            "test_actual_renewal_audit_rejects_extra_callers[app_yue_bot-function-renewal_credit_state(bigint)-yueboard_runtime:EXECUTE:false]",
            "test_actual_renewal_audit_rejects_extra_callers[app_yue_bot-function-reserve_order_renewal_credit()-]",
            "test_actual_renewal_audit_rejects_extra_callers[app_yue_bot-sequence-renewal_credit_exchanges_id_seq-]",
            "test_actual_renewal_exact_acl_matches_reviewed_floor[function-exchange_points_renewal(bigint, bigint, text)-]",
            "test_actual_renewal_exact_acl_matches_reviewed_floor[function-renewal_credit_month(timestamp with time zone)-]",
            "test_actual_renewal_exact_acl_matches_reviewed_floor[function-renewal_credit_state(bigint)-yueboard_runtime:EXECUTE:false]",
            "test_actual_renewal_exact_acl_matches_reviewed_floor[function-reserve_order_renewal_credit()-]",
            "test_actual_renewal_exact_acl_matches_reviewed_floor[sequence-renewal_credit_exchanges_id_seq-]",
        )
        calls = self.previous + [self.added] + [BOARD + "::" + name for name in names]
        value = {"skip_module_blobs": {BOARD: renewal}}
        result = SHARDS.reviewed_board139_native_successor(
            self.baseline, value, {"obligations": {BOARD: {"passed": calls}}})
        rows = {k: v for k, v in result["reviewed_hosted"]["cases"].items() if k.startswith(BOARD + "::")}
        self.assertEqual(set(rows), set(calls))
        self.assertEqual(len(rows), 22)
        self.assertTrue(all(row["module_blob"] == renewal and row["outcome"] == "skipped"
                            and row["disposition"] == "SAME_RUN_NATIVE_REQUIRED" for row in rows.values()))
        self.assertEqual((ROOT / "ops-pytest-skip-baseline.json").read_bytes(), self.raw)
        for dropped in (calls[:-1], calls + [BOARD + "::unreviewed"]):
            with self.subTest(count=len(dropped)), self.assertRaisesRegex(ValueError, "twenty-two exact"):
                SHARDS.reviewed_board139_native_successor(
                    self.baseline, value, {"obligations": {BOARD: {"passed": dropped}}})

    def test_canceled_backup_keeps_exact_23_skips_unexecuted(self):
        result = SHARDS.reviewed_canceled_backup_blob_successor(self.baseline, self.backup_value)
        before = {k: v for k, v in self.baseline["cases"].items() if k.startswith(BACKUP + "::")}
        after = {k: v for k, v in result["cases"].items() if k.startswith(BACKUP + "::")}
        self.assertEqual(len(after), 23)
        self.assertEqual(after, {k: v | {"module_blob": self.backup_value["skip_module_blobs"][BACKUP]}
                                 for k, v in before.items()})
        self.assertTrue(all(row["outcome"] == "skipped" for row in after.values()))
        self.assertFalse(any(k.startswith(BACKUP + "::") for k in result["reviewed_hosted"]["cases"]))
        self.assertEqual(self.baseline, json.loads(self.raw))

    def test_backup_missing_changed_or_new_reason_cannot_be_grandfathered(self):
        original = next(k for k in self.baseline["cases"] if k.startswith(BACKUP + "::"))
        for mutation in ("missing", "reason", "outcome", "extra"):
            altered = copy.deepcopy(self.baseline)
            if mutation == "missing":
                del altered["cases"][original]
            elif mutation == "extra":
                altered["cases"][BACKUP + "::new"] = altered["cases"][original]
            else:
                altered["cases"][original][mutation] = "changed"
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, "historical case"):
                SHARDS.reviewed_canceled_backup_blob_successor(altered, self.backup_value)


class ExactFirstNativePolicy(unittest.TestCase):
    def setUp(self):
        self.policy = SHARDS.first_native_policy()
        self.baseline = SHARDS.skip_baseline()
        self.value = {"source_revision": self.policy["source_revision"],
                      "skip_module_blobs": self.policy["module_blobs"]}
        self.native = {"obligations": {m: {"passed": [n for n in self.policy["cases"]
                                                       if n.startswith(m + "::")]}
                                       for m in self.policy["module_blobs"]}}

    def test_remaining_obligations_require_actual_same_run_case_calls(self):
        result = SHARDS.reviewed_first_native_successor(self.baseline, self.value, self.native)
        for name in self.policy["cases"]:
            self.assertEqual(result["reviewed_hosted"]["cases"][name]["disposition"],
                             "SAME_RUN_NATIVE_REQUIRED")
        for name in self.policy["cases"]:
            native = copy.deepcopy(self.native)
            native["obligations"][name.split("::")[0]]["passed"].remove(name)
            with self.subTest(case=name), self.assertRaisesRegex(ValueError, "same-run call"):
                SHARDS.reviewed_first_native_successor(self.baseline, self.value, native)

    def test_missing_or_changed_module_blob_refuses_inheritance(self):
        for module in self.policy["module_blobs"]:
            for replacement in (None, "f" * 40):
                value = copy.deepcopy(self.value)
                value["skip_module_blobs"][module] = replacement
                with self.subTest(module=module, replacement=replacement), self.assertRaises(ValueError):
                    SHARDS.reviewed_first_native_successor(self.baseline, value, self.native)
        value = self.value | {"source_revision": "f" * 40}
        self.assertIs(SHARDS.reviewed_first_native_successor(self.baseline, value, self.native), self.baseline)

    def test_descendant_with_the_same_native_blobs_keeps_the_binding(self):
        value = self.value | {"source_revision": "a" * 40, "pin_is_ancestor": True}
        result = SHARDS.reviewed_first_native_successor(self.baseline, value, self.native)
        for name in self.policy["cases"]:
            self.assertEqual(result["reviewed_hosted"]["cases"][name]["disposition"],
                             "SAME_RUN_NATIVE_REQUIRED")

    def test_helper_admits_only_reviewed_mode_blob_source_and_retains_other_inputs(self):
        item = self.policy["shared_input"]
        path, blob, revision = item["path"], item["blob"], self.policy["source_revision"]
        common = {path: blob, "other.py": "a" * 40}
        files = {p: ("100644", b) for p, b in common.items()}
        remaining, tree = SHARDS.admit_first_native_helper(common, files, revision)
        self.assertEqual(remaining, {"other.py": "a" * 40})
        self.assertEqual(tree, {"other.py": ("100644", "a" * 40)})
        self.assertIn(path, common)
        for changed, modes, source in (
            ({}, files, revision), (common | {path: "f" * 40}, files, revision),
            (common, files | {path: ("100755", blob)}, revision),
            (common, files | {path: ("120000", blob)}, revision),
            (common, files, "f" * 40),
        ):
            with self.subTest(changed=changed, source=source), self.assertRaises(ValueError):
                SHARDS.admit_first_native_helper(changed, modes, source)


    def test_descendant_keeps_the_exact_helper_blob(self):
        item = self.policy["shared_input"]
        path, blob = item["path"], item["blob"]
        common = {path: blob, "other.py": "a" * 40}
        files = {name: ("100644", value) for name, value in common.items()}
        later = "b" * 40
        remaining, tree = SHARDS.admit_first_native_helper(
            common, files, later, pin_is_ancestor=True)
        self.assertEqual(remaining, {"other.py": "a" * 40})
        self.assertEqual(tree, {"other.py": ("100644", "a" * 40)})
        with self.assertRaises(ValueError):
            SHARDS.admit_first_native_helper(
                common | {path: "f" * 40}, files, later, pin_is_ancestor=True)

    def test_release_pin_ancestry_follows_yueops_history(self):
        source = ROOT.parent / "yueops"
        if not (source / ".git").exists():
            self.skipTest("yueops sibling checkout is not available")
        pin = SHARDS.release_pin()
        self.assertTrue(SHARDS.release_pin_is_ancestor(source, pin))
        parent = SHARDS.git(source, "rev-parse", pin + "^").decode().strip()
        self.assertFalse(SHARDS.release_pin_is_ancestor(source, parent))
        self.assertFalse(SHARDS.holds_release_pin(parent, pin_is_ancestor=False))
        self.assertTrue(SHARDS.holds_release_pin(parent, pin_is_ancestor=True))

    def test_descendant_ruff_bundle_uses_release_pin_ancestry(self):
        source = ROOT.parent / "yueops"
        if not (source / ".git").exists():
            self.skipTest("yueops sibling checkout is not available")
        revision = SHARDS.git(source, "rev-parse", "HEAD").decode().strip()
        self.assertNotEqual(revision, SHARDS.release_pin())
        self.assertTrue(SHARDS.release_pin_is_ancestor(source, revision))
        SHARDS.pr_shared_input_successor_proof(source, revision)
        with mock.patch.object(SHARDS, "release_pin_is_ancestor", return_value=False):
            with self.assertRaisesRegex(ValueError, "ruff_retired_video"):
                SHARDS.pr_shared_input_successor_proof(source, revision)
    def test_policy_has_no_historical_backup_or_disposition_downgrade(self):
        retired = {
            "tests/test_protocol_liveness_results_install.py",
            "tests/test_protocol_liveness_results_pull.py",
            "tests/test_install_operator_host_source.py",
        }
        self.assertEqual(len(self.policy["cases"]), 4)
        self.assertEqual(set(self.policy["module_blobs"]), {
            "tests/test_frozen_manifest_reader_20261015.py",
            "tests/test_panel_subscribe_delivery_alert_20261012.py",
            "tests/test_status_tls_installer_20261027.py",
        })
        self.assertTrue(retired.isdisjoint(SHARDS.NATIVE_TARGETS))
        self.assertFalse(any(name.split("::", 1)[0] in retired for name in self.policy["cases"]))
        for name, row in self.policy["cases"].items():
            self.assertFalse(name.startswith(BACKUP + "::"))
            self.assertEqual(set(row), {"outcome", "variants"})
            self.assertEqual(row["outcome"], "skipped")
            self.assertTrue(row["variants"])

    def test_ordinary_skip_evidence_is_exact_and_does_not_inherit_a_new_blob(self):
        evidence = ROOT / "reviews/ops-ordinary-skip-evidence-20261107.json"
        baseline_bytes = (ROOT / "ops-pytest-skip-baseline.json").read_bytes()
        raw = evidence.read_bytes()
        self.assertEqual(SHARDS.sha(raw), SHARDS.ORDINARY_SKIP_EVIDENCE_SHA256)
        record = json.loads(raw)
        sealed = SHARDS.skip_baseline()
        _, blob_record = SHARDS.reviewed_skip_blob_successor_transition(sealed)
        _, release_blob = SHARDS.reviewed_release_skip_blob_successor_transition(sealed)
        _, case_successors = SHARDS.reviewed_case_file_transition(sealed)
        baseline, _estate = SHARDS.reviewed_estate_input_transition(sealed)
        baseline, preservation = SHARDS.reviewed_relay_preservation_module_transition(baseline)
        baseline, meter = SHARDS.reviewed_relay_meter_module_transition(baseline)
        baseline, metrics = SHARDS.reviewed_relay_metrics_module_transition(baseline)
        baseline, relay = SHARDS.reviewed_relay_skip_module_transition(baseline)
        baseline, extra = SHARDS.reviewed_current_skip_transition(baseline)
        _, successors = SHARDS.reviewed_skip_module_transition(baseline)
        successors = dict(successors)
        successors.update(extra)
        admitted = {nodeid: dict(case) for nodeid, case in baseline["cases"].items()}
        for mapping in (successors, relay, metrics, meter, preservation, case_successors):
            admitted.update(mapping)
        hosted = baseline.get("reviewed_hosted", {}).get("cases", {})
        admitted.update(SHARDS.skip_blob_successors(blob_record, admitted, hosted))
        admitted.update(SHARDS.skip_blob_successors(release_blob, admitted, hosted))
        blobs = {}
        for nodeid, change in record["updates"].items():
            blobs[nodeid.split("::", 1)[0]] = change["after_blob"]
        for nodeid, case in record["additions"].items():
            blobs[nodeid.split("::", 1)[0]] = case["module_blob"]
        got = SHARDS.ordinary_skip_evidence_successors(admitted, {"skip_module_blobs": blobs})
        self.assertEqual(set(got), set(record["updates"]) | set(record["additions"]))
        self.assertEqual(len(got), 306)
        sample = next(iter(record["updates"]))
        module = sample.split("::", 1)[0]
        narrowed = dict(blobs)
        narrowed[module] = "f" * 40
        self.assertNotIn(sample, SHARDS.ordinary_skip_evidence_successors(
            admitted, {"skip_module_blobs": narrowed}))
        broken = dict(admitted)
        broken[sample] = dict(admitted[sample], module_blob="e" * 40)
        with self.assertRaisesRegex(ValueError, "does not succeed"):
            SHARDS.ordinary_skip_evidence_successors(broken, {"skip_module_blobs": blobs})
        rollback = ("tests/test_agent_rollback_payload_20261013.py::"
                    "test_real_linux_signed_payload_roots_and_native_consumer_rejections")
        rollback_module, rollback_after = rollback.split("::", 1)[0], record["updates"][rollback]["after_blob"]
        predecessor, _ = SHARDS.reviewed_estate_input_transition(SHARDS.skip_baseline())
        earlier = {nodeid: dict(case) for nodeid, case in predecessor["cases"].items()}
        self.assertNotEqual(earlier[rollback]["module_blob"], record["updates"][rollback]["before_blob"])
        self.assertNotIn(rollback, SHARDS.ordinary_skip_evidence_successors(
            earlier, {"skip_module_blobs": {rollback_module: "f" * 40}}))
        with self.assertRaisesRegex(ValueError, "does not succeed"):
            SHARDS.ordinary_skip_evidence_successors(
                earlier, {"skip_module_blobs": {rollback_module: rollback_after}})
        self.assertIn(rollback, got)
        self.assertEqual(got[rollback]["module_blob"], rollback_after)
        self.assertEqual(got[rollback]["reason"], admitted[rollback]["reason"])
        with tempfile.TemporaryDirectory() as directory:
            isolated = Path(directory)
            with mock.patch.object(SHARDS, "ROOT", isolated):
                self.assertIsNone(SHARDS.ordinary_skip_evidence_file())
                self.assertEqual(SHARDS.ordinary_skip_evidence_successors(admitted, {
                    "skip_module_blobs": blobs}), {})
            reviews = isolated / "reviews"
            reviews.mkdir()
            (reviews / SHARDS.ORDINARY_SKIP_EVIDENCE.name).symlink_to(evidence)
            with mock.patch.object(SHARDS, "ROOT", isolated):
                self.assertIsNone(SHARDS.ordinary_skip_evidence_file())
                self.assertEqual(SHARDS.ordinary_skip_evidence_successors(admitted, {
                    "skip_module_blobs": blobs}), {})
        self.assertEqual((ROOT / "ops-pytest-skip-baseline.json").read_bytes(), baseline_bytes)


class Successors20261110(unittest.TestCase):
    def test_status_tls_blob_is_the_reviewed_la_retirement_blob(self):
        policy = json.loads((ROOT / "ops-first-native-successors.json").read_text())
        self.assertEqual(policy["module_blobs"]["tests/test_status_tls_installer_20261027.py"],
                         "88a1065c4fae3cb7b05a6531eccced3da13768bb")
        self.assertEqual(len(policy["module_blobs"]), 3)
        self.assertEqual(len(policy["cases"]), 4)

    def test_second_retired_host_successor_is_exact(self):
        sealed = SHARDS.skip_baseline()
        _, retirement = SHARDS.reviewed_retired_host_transition(sealed)
        cases = sealed["cases"]
        survivors = retirement["surviving_ids"]
        second = SHARDS.RETIRED_HOST_SECOND_IDS
        self.assertTrue(second <= set(survivors))
        keep = next(n for n in survivors if n not in second)
        row = {"outcome": cases[keep]["outcome"], "reason": cases[keep]["reason"]}
        new_blob = SHARDS.RETIRED_HOST_SECOND_AFTER_BLOB
        self.assertTrue(SHARDS.retired_host_case_admitted(retirement, cases, keep, row, new_blob))
        self.assertTrue(SHARDS.retired_host_case_admitted(
            retirement, cases, keep, row, SHARDS.RETIRED_HOST_AFTER_BLOB))
        for nodeid in second:
            self.assertFalse(SHARDS.retired_host_case_admitted(retirement, cases, nodeid, row, new_blob))
        self.assertFalse(SHARDS.retired_host_case_admitted(retirement, cases, keep, row, "f" * 40))
        self.assertFalse(SHARDS.retired_host_case_admitted(
            retirement, cases, keep, dict(row, reason="other"), new_blob))
        self.assertFalse(SHARDS.retired_host_case_admitted(
            retirement, cases, keep, dict(row, outcome="failed"), new_blob))
        removed = next(iter(SHARDS.RETIRED_HOST_IDS))
        self.assertFalse(SHARDS.retired_host_case_admitted(retirement, cases, removed, row, new_blob))

    def test_20261110_evidence_is_pinned_and_admits_only_its_after_blob(self):
        raw = (ROOT / SHARDS.ORDINARY_SKIP_EVIDENCE_20261110).read_bytes()
        self.assertEqual(SHARDS.sha(raw), SHARDS.ORDINARY_SKIP_EVIDENCE_20261110_SHA256)
        record = json.loads(raw)
        self.assertEqual((len(record["updates"]), len(record["additions"])), (102, 32))
        self.assertEqual(record["evidence_run"], "42817758699")
        for case in record["additions"].values():
            self.assertEqual(case["outcome"], "skipped")
            self.assertTrue(case["reason"].startswith("Skipped: "))
        updated = {n.split("::", 1)[0] for n in record["updates"]}
        only_added = {n: c for n, c in record["additions"].items() if n.split("::", 1)[0] not in updated}
        self.assertTrue(only_added)
        blobs = {n.split("::", 1)[0]: c["module_blob"] for n, c in only_added.items()}
        admitted = {}
        got = SHARDS._ordinary_skip_evidence_record(
            ROOT / SHARDS.ORDINARY_SKIP_EVIDENCE_20261110, SHARDS.ORDINARY_SKIP_EVIDENCE_20261110_SHA256,
            admitted, {"skip_module_blobs": blobs})
        self.assertEqual(set(got), set(only_added))
        moved = {m: "f" * 40 for m in blobs}
        self.assertEqual(SHARDS._ordinary_skip_evidence_record(
            ROOT / SHARDS.ORDINARY_SKIP_EVIDENCE_20261110, SHARDS.ORDINARY_SKIP_EVIDENCE_20261110_SHA256,
            admitted, {"skip_module_blobs": moved}), {})
        with self.assertRaisesRegex(ValueError, "unreviewed ordinary skip evidence"):
            SHARDS._ordinary_skip_evidence_record(
                ROOT / SHARDS.ORDINARY_SKIP_EVIDENCE_20261110, "0" * 64, admitted, {"skip_module_blobs": blobs})

    def test_20261110b_drill_evidence_moves_only_admitted_skips(self):
        raw = (ROOT / SHARDS.ORDINARY_SKIP_EVIDENCE_20261110B).read_bytes()
        self.assertEqual(SHARDS.sha(raw), SHARDS.ORDINARY_SKIP_EVIDENCE_20261110B_SHA256)
        record = json.loads(raw)
        self.assertEqual((len(record["updates"]), len(record["additions"])), (7, 0))
        module = "tests/test_yueops_pg_restore_drill_20260924.py"
        self.assertEqual({n.split("::", 1)[0] for n in record["updates"]}, {module})
        before = "2f57ec05cab6f9af631f66650feaaf76a7770222"
        after = "3cca4792fbd3319411901ad3588a879e7b52193f"
        admitted = {n: {"outcome": "skipped", "reason": "Skipped: docker", "module_blob": before}
                    for n in record["updates"]}
        path = ROOT / SHARDS.ORDINARY_SKIP_EVIDENCE_20261110B
        digest = SHARDS.ORDINARY_SKIP_EVIDENCE_20261110B_SHA256
        got = SHARDS._ordinary_skip_evidence_record(path, digest, admitted, {"skip_module_blobs": {module: after}})
        self.assertEqual(set(got), set(record["updates"]))
        self.assertTrue(all(c["module_blob"] == after and c["reason"] == "Skipped: docker" for c in got.values()))
        self.assertEqual(SHARDS._ordinary_skip_evidence_record(
            path, digest, admitted, {"skip_module_blobs": {module: before}}), {})
        wrong = {n: dict(c, module_blob="e" * 40) for n, c in admitted.items()}
        with self.assertRaisesRegex(ValueError, "does not succeed an admitted skip"):
            SHARDS._ordinary_skip_evidence_record(path, digest, wrong, {"skip_module_blobs": {module: after}})
        with self.assertRaisesRegex(ValueError, "does not succeed an admitted skip"):
            SHARDS._ordinary_skip_evidence_record(path, digest, {}, {"skip_module_blobs": {module: after}})


    def test_20261111_cdn_vless_evidence_moves_only_the_admitted_skip(self):
        raw = (ROOT / SHARDS.ORDINARY_SKIP_EVIDENCE_20261111).read_bytes()
        self.assertEqual(SHARDS.sha(raw), SHARDS.ORDINARY_SKIP_EVIDENCE_20261111_SHA256)
        record = json.loads(raw)
        self.assertEqual((len(record["updates"]), len(record["additions"])), (1, 0))
        module = "tests/test_cdn_vless_autohide_20261006.py"
        self.assertEqual({n.split("::", 1)[0] for n in record["updates"]}, {module})
        before = "cbfe9f4b0931c1b12d63f433a4ba854004e617c4"
        after = "57146f4b40337b548cf38783f5930378880f4cda"
        baseline = json.loads((ROOT / SHARDS.SKIP_BASELINE).read_bytes())
        # Evidence files are checked against the admitted set, not chained:
        # before_blob must be the blob the baseline admits (run 42878457376).
        for nodeid in record["updates"]:
            self.assertEqual(baseline["cases"][nodeid]["module_blob"], before)
        reason = "Skipped: set XRAY_PROBE_TEST_BIN to run the native VLESS transport regression"
        admitted = {n: {"outcome": "skipped", "reason": reason, "module_blob": before}
                    for n in record["updates"]}
        path = ROOT / SHARDS.ORDINARY_SKIP_EVIDENCE_20261111
        digest = SHARDS.ORDINARY_SKIP_EVIDENCE_20261111_SHA256
        got = SHARDS._ordinary_skip_evidence_record(path, digest, admitted, {"skip_module_blobs": {module: after}})
        self.assertEqual(set(got), set(record["updates"]))
        self.assertTrue(all(c["module_blob"] == after and c["reason"] == reason for c in got.values()))
        self.assertEqual(SHARDS._ordinary_skip_evidence_record(
            path, digest, admitted, {"skip_module_blobs": {module: before}}), {})
        with self.assertRaisesRegex(ValueError, "does not succeed an admitted skip"):
            SHARDS._ordinary_skip_evidence_record(path, digest, {}, {"skip_module_blobs": {module: after}})

    def test_20261111b_cdn_vless_evidence_moves_only_the_admitted_skip(self):
        raw = (ROOT / SHARDS.ORDINARY_SKIP_EVIDENCE_20261111B).read_bytes()
        self.assertEqual(SHARDS.sha(raw), SHARDS.ORDINARY_SKIP_EVIDENCE_20261111B_SHA256)
        record = json.loads(raw)
        self.assertEqual((len(record["updates"]), len(record["additions"])), (1, 0))
        module = "tests/test_cdn_vless_autohide_20261006.py"
        self.assertEqual({n.split("::", 1)[0] for n in record["updates"]}, {module})
        before = "cbfe9f4b0931c1b12d63f433a4ba854004e617c4"
        after = "b6509a58e8596c13e6e3050031720a32239a1186"
        baseline = json.loads((ROOT / SHARDS.SKIP_BASELINE).read_bytes())
        # Evidence files are checked against the admitted set, not chained:
        # before_blob must be the blob the baseline admits (run 42878457376).
        for nodeid in record["updates"]:
            self.assertEqual(baseline["cases"][nodeid]["module_blob"], before)
        reason = "Skipped: set XRAY_PROBE_TEST_BIN to run the native VLESS transport regression"
        admitted = {n: {"outcome": "skipped", "reason": reason, "module_blob": before}
                    for n in record["updates"]}
        path = ROOT / SHARDS.ORDINARY_SKIP_EVIDENCE_20261111B
        digest = SHARDS.ORDINARY_SKIP_EVIDENCE_20261111B_SHA256
        got = SHARDS._ordinary_skip_evidence_record(path, digest, admitted, {"skip_module_blobs": {module: after}})
        self.assertEqual(set(got), set(record["updates"]))
        self.assertTrue(all(c["module_blob"] == after and c["reason"] == reason for c in got.values()))
        self.assertEqual(SHARDS._ordinary_skip_evidence_record(
            path, digest, admitted, {"skip_module_blobs": {module: before}}), {})
        with self.assertRaisesRegex(ValueError, "does not succeed an admitted skip"):
            SHARDS._ordinary_skip_evidence_record(path, digest, {}, {"skip_module_blobs": {module: after}})

    def test_20261111c_cdn_vless_evidence_moves_only_the_admitted_skip(self):
        raw = (ROOT / SHARDS.ORDINARY_SKIP_EVIDENCE_20261111C).read_bytes()
        self.assertEqual(SHARDS.sha(raw), SHARDS.ORDINARY_SKIP_EVIDENCE_20261111C_SHA256)
        record = json.loads(raw)
        self.assertEqual((len(record["updates"]), len(record["additions"])), (1, 0))
        module = "tests/test_cdn_vless_autohide_20261006.py"
        self.assertEqual({n.split("::", 1)[0] for n in record["updates"]}, {module})
        before = "cbfe9f4b0931c1b12d63f433a4ba854004e617c4"
        after = "8919984185a50b7f92cb27dfa883c1f8f72c1635"
        baseline = json.loads((ROOT / SHARDS.SKIP_BASELINE).read_bytes())
        for nodeid in record["updates"]:
            self.assertEqual(baseline["cases"][nodeid]["module_blob"], before)
        reason = "Skipped: set XRAY_PROBE_TEST_BIN to run the native VLESS transport regression"
        admitted = {n: {"outcome": "skipped", "reason": reason, "module_blob": before}
                    for n in record["updates"]}
        path = ROOT / SHARDS.ORDINARY_SKIP_EVIDENCE_20261111C
        digest = SHARDS.ORDINARY_SKIP_EVIDENCE_20261111C_SHA256
        got = SHARDS._ordinary_skip_evidence_record(path, digest, admitted, {"skip_module_blobs": {module: after}})
        self.assertEqual(set(got), set(record["updates"]))
        self.assertTrue(all(c["module_blob"] == after and c["reason"] == reason for c in got.values()))
        self.assertEqual(SHARDS._ordinary_skip_evidence_record(
            path, digest, admitted, {"skip_module_blobs": {module: before}}), {})
        with self.assertRaisesRegex(ValueError, "does not succeed an admitted skip"):
            SHARDS._ordinary_skip_evidence_record(path, digest, {}, {"skip_module_blobs": {module: after}})

    def test_20261111d_selective_deploy_evidence_moves_only_the_admitted_skip(self):
        raw = (ROOT / SHARDS.ORDINARY_SKIP_EVIDENCE_20261111D).read_bytes()
        self.assertEqual(SHARDS.sha(raw), SHARDS.ORDINARY_SKIP_EVIDENCE_20261111D_SHA256)
        record = json.loads(raw)
        self.assertEqual((len(record["updates"]), len(record["additions"])), (1, 0))
        module = "tests/test_ops_selective_deploy_20261009.py"
        before = "03118c494df39551571140bfc371e814bcb7f400"
        after = "c0037189784255c6881365f66d3d1db258f07aac"
        baseline = json.loads((ROOT / SHARDS.SKIP_BASELINE).read_bytes())
        for nodeid in record["updates"]:
            self.assertEqual(baseline["cases"][nodeid]["module_blob"], before)
            reason = baseline["cases"][nodeid]["reason"]
        admitted = {n: {"outcome": "skipped", "reason": reason, "module_blob": before}
                    for n in record["updates"]}
        path = ROOT / SHARDS.ORDINARY_SKIP_EVIDENCE_20261111D
        digest = SHARDS.ORDINARY_SKIP_EVIDENCE_20261111D_SHA256
        got = SHARDS._ordinary_skip_evidence_record(path, digest, admitted, {"skip_module_blobs": {module: after}})
        self.assertEqual(set(got), set(record["updates"]))
        self.assertTrue(all(c["module_blob"] == after and c["reason"] == reason for c in got.values()))
        with self.assertRaisesRegex(ValueError, "does not succeed an admitted skip"):
            SHARDS._ordinary_skip_evidence_record(path, digest, {}, {"skip_module_blobs": {module: after}})

if __name__ == "__main__":
    unittest.main()


class RestoreDrillBlobSuccessor(unittest.TestCase):
    def test_moves_only_the_seven_owner_canceled_cases(self):
        baseline = json.loads((ROOT / SHARDS.SKIP_BASELINE).read_bytes())
        module = "tests/test_yueops_pg_restore_drill_20260924.py"
        after = "3cca4792fbd3319411901ad3588a879e7b52193f"
        moved = SHARDS.reviewed_restore_drill_blob_successor(baseline, {"skip_module_blobs": {module: after}})
        rows = {k: v for k, v in moved["reviewed_hosted"]["cases"].items() if k.startswith(module + "::")}
        self.assertEqual(len(rows), 7)
        self.assertTrue(all(v["module_blob"] == after and v["disposition"] == "OWNER_CANCELED" for v in rows.values()))
        for k, v in rows.items():
            self.assertEqual(v["variants"], baseline["reviewed_hosted"]["cases"][k]["variants"])
        other = {k: v for k, v in moved["reviewed_hosted"]["cases"].items() if not k.startswith(module + "::")}
        self.assertEqual(other, {k: v for k, v in baseline["reviewed_hosted"]["cases"].items() if not k.startswith(module + "::")})
        self.assertIs(SHARDS.reviewed_restore_drill_blob_successor(baseline, {"skip_module_blobs": {module: "0" * 40}}), baseline)
        tampered = json.loads(json.dumps(baseline))
        key = next(iter(rows))
        tampered["reviewed_hosted"]["cases"][key]["disposition"] = "SAME_RUN_NATIVE_REQUIRED"
        with self.assertRaisesRegex(ValueError, "restore-drill reviewed case"):
            SHARDS.reviewed_restore_drill_blob_successor(tampered, {"skip_module_blobs": {module: after}})
