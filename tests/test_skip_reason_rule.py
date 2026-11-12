"""A skip is admitted by its reason. The dated review chain is not an allow-list."""
import copy
import importlib.util
import inspect
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "skip_reason_shards", ROOT / "scripts/pytest-shards.py")
SHARDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARDS)

MODULE = "tests/test_relay_coordinator_delivery_closure_20260905.py"
AFTER = "3c9f5d4f5b68b458b5c7f95a4bf029828bc0c404"

RELAY_SKIPS = (
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_busy_provider_service_is_not_killed_or_republished', 'Skipped: real root installer'),
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_effective_unit_override_cannot_enable_writer[entrypoint]', 'Skipped: real root installer'),
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_effective_unit_override_cannot_enable_writer[timeout]', 'Skipped: real root installer'),
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_existing_private_closure_is_restored_as_a_pair_with_its_unit', 'Skipped: real root installer'),
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_extra_importable_runtime_bytes_fail_before_import_or_service_start[scripts/lib/__init__.py]', 'Skipped: real root installer'),
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_extra_importable_runtime_bytes_fail_before_import_or_service_start[scripts/lib/__pycache__/ssh_auth.pyc]', 'Skipped: real root installer'),
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_extra_importable_runtime_bytes_fail_before_import_or_service_start[yueops/__pycache__/fleet_inventory_env.pyc]', 'Skipped: real root installer'),
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_extra_importable_runtime_bytes_fail_before_import_or_service_start[yueops/unreviewed.py]', 'Skipped: real root installer'),
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_identity_change_during_wait_is_not_admitted_as_address_refresh', 'Skipped: real root installer'),
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_missing_transitive_input_fails_before_any_mutation[scripts/converge-blackholed-pool-member-rotation.py]', 'Skipped: real root installer'),
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_missing_transitive_input_fails_before_any_mutation[scripts/lib/fleet-inventory-env.sh]', 'Skipped: real root installer'),
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_missing_transitive_input_fails_before_any_mutation[scripts/lib/moonvm_rotate.py]', 'Skipped: real root installer'),
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_missing_transitive_input_fails_before_any_mutation[scripts/lib/owned_dns.py]', 'Skipped: real root installer'),
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_missing_transitive_input_fails_before_any_mutation[scripts/lib/relay_peers.py]', 'Skipped: real root installer'),
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_missing_transitive_input_fails_before_any_mutation[scripts/lib/ssh_auth.py]', 'Skipped: real root installer'),
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_missing_transitive_input_fails_before_any_mutation[scripts/lib/ssh_kr_proxy.py]', 'Skipped: real root installer'),
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_missing_transitive_input_fails_before_any_mutation[yueops/__init__.py]', 'Skipped: real root installer'),
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_missing_transitive_input_fails_before_any_mutation[yueops/fleet_inventory_env.py]', 'Skipped: real root installer'),
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_naturally_completed_rotation_refreshes_addresses_before_delivery', 'Skipped: real root installer'),
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_old_flat_closure_is_untouched_and_new_directories_are_removed_on_rollback', 'Skipped: real root installer and predecessor filesystem'),
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_private_inventory_bridge_and_loader_ignore_external_package', 'Skipped: real root installer and isolated interpreter'),
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_rollback_refuses_changed_published_dependency', 'Skipped: real root installer'),
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_apply_imports_complete_private_closure_and_rollback_preserves_evolved_lease[False-False]', 'Skipped: real GNU owner/mode and root installer, Linux root image'),
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_apply_imports_complete_private_closure_and_rollback_preserves_evolved_lease[False-True]', 'Skipped: real GNU owner/mode and root installer, Linux root image'),
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_apply_imports_complete_private_closure_and_rollback_preserves_evolved_lease[True-False]', 'Skipped: real GNU owner/mode and root installer, Linux root image'),
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_apply_imports_complete_private_closure_and_rollback_preserves_evolved_lease[True-True]', 'Skipped: real GNU owner/mode and root installer, Linux root image'),
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_install_held_lease_keeps_timer_and_expiry_preflight', 'Skipped: real GNU owner/mode and root installer, Linux root image'),
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_missing_transitive_input_fails_before_any_mutation[scripts/lib/retired_entry_quarantine.py]', 'Skipped: real root installer'),
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_missing_transitive_input_fails_before_any_mutation[scripts/v4-relay-multi-a-peers.json]', 'Skipped: real root installer'),
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_read_relays_does_not_depend_on_inherited_bytecode_environment[mutation-without-B]', 'Skipped: real root installer and GNU filesystem tools'),
    ('tests/test_relay_coordinator_delivery_closure_20260905.py::test_read_relays_does_not_depend_on_inherited_bytecode_environment[protected]', 'Skipped: real root installer and GNU filesystem tools'),
)


class SkipReasonRule(unittest.TestCase):
    def setUp(self):
        self.baseline = json.loads((ROOT / "ops-pytest-skip-baseline.json").read_text())
        self.rows = [{"nodeid": nodeid, "outcome": "skipped", "when": "setup", "reason": reason}
                     for nodeid, reason in RELAY_SKIPS]
        session = {"execution_context": self.baseline["context"], "collection_skips": {},
                   "junit_sha256": "b" * 64, "nonpassing_outcomes": self.rows}
        self.result = {"reference": session | {"assignment_id": "reference"},
                       "shards": [copy.deepcopy(session) | {"assignment_id": "ordinary-000"}]}
        self.value = {
            "skip_module_blobs": {MODULE: AFTER},
            "skip_baseline_sha256": SHARDS.sha((ROOT / SHARDS.SKIP_BASELINE).read_bytes()),
            "common_inputs": self.baseline["common_inputs"] | SHARDS.NATIVE_INPUTS,
        }

    def test_relay_run_43024038775_is_admitted(self):
        self.assertEqual(len(RELAY_SKIPS), 31)
        self.assertTrue(all(reason.strip() for _, reason in RELAY_SKIPS))
        verdict = SHARDS.admit_skips(self.value, self.result, {"obligations": {}})
        self.assertEqual(verdict["status"], "NO_NEW_SKIPS")
        self.assertIs(verdict["skips_are_passes"], False)
        accounted = sum(verdict["disposition_counts"].values()) + len(verdict.get("reported_skips", ()))
        self.assertGreaterEqual(accounted, 31)
        self.assertEqual(list((ROOT / "reviews").glob("ops-ordinary-skip-evidence-*.json")), [])

    def test_reasonless_skip_fails_and_a_new_reason_is_reported(self):
        blank = copy.deepcopy(self.result)
        for session in (blank["reference"], *blank["shards"]):
            session["nonpassing_outcomes"][0]["reason"] = ""
        with self.assertRaisesRegex(ValueError, "skip has no reason"):
            SHARDS.admit_skips(self.value, blank, {"obligations": {}})
        missing = copy.deepcopy(self.result)
        for session in (missing["reference"], *missing["shards"]):
            del session["nonpassing_outcomes"][0]["reason"]
        with self.assertRaisesRegex(ValueError, "skip has no reason"):
            SHARDS.admit_skips(self.value, missing, {"obligations": {}})
        fresh = copy.deepcopy(self.result)
        nodeid = MODULE + "::test_brand_new_reason"
        row = {"nodeid": nodeid, "outcome": "skipped", "when": "setup",
               "reason": "Skipped: brand new case"}
        for session in (fresh["reference"], *fresh["shards"]):
            session["nonpassing_outcomes"] = [row]
        verdict = SHARDS.admit_skips(self.value, fresh, {"obligations": {}})
        self.assertEqual(verdict["status"], "NO_NEW_SKIPS")
        self.assertIn(nodeid, verdict["reported_skips"])
        self.assertIs(verdict["skips_are_passes"], False)

    def test_collection_skip_follows_the_same_reason_rule(self):
        module = "tests/test_new_collection_skip.py"
        reasoned = copy.deepcopy(self.result)
        for session in (reasoned["reference"], *reasoned["shards"]):
            session["nonpassing_outcomes"] = []
            session["collection_skips"] = {module: "Skipped: new missing dependency"}
        verdict = SHARDS.admit_skips(
            self.value | {"skip_module_blobs": {MODULE: AFTER, module: "d" * 40}},
            reasoned, {"obligations": {}})
        self.assertIn(module, verdict["reported_skips"])
        blank = copy.deepcopy(reasoned)
        for session in (blank["reference"], *blank["shards"]):
            session["collection_skips"] = {module: "   "}
        with self.assertRaisesRegex(ValueError, "skip has no reason"):
            SHARDS.admit_skips(self.value, blank, {"obligations": {}})

    def test_allow_list_message_is_not_the_gate(self):
        source = inspect.getsource(SHARDS.admit_skips)
        self.assertNotIn("new or changed case skip", source)
        self.assertNotIn("new or changed collection skip", source)
        self.assertIn("skip has no reason", source)
        self.assertNotIn("ORDINARY_SKIP_EVIDENCE", inspect.getsource(SHARDS))


if __name__ == "__main__":
    unittest.main()
