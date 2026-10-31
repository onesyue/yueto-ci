"""Exact first-release successors preserve historical and native obligations."""

import copy
import importlib.util
import json
import unittest
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

    def test_all_52_obligations_require_actual_same_run_case_calls(self):
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

    def test_policy_has_no_historical_backup_or_disposition_downgrade(self):
        self.assertEqual(len(self.policy["cases"]), 52)
        for name, row in self.policy["cases"].items():
            self.assertFalse(name.startswith(BACKUP + "::"))
            self.assertEqual(set(row), {"outcome", "variants"})
            self.assertEqual(row["outcome"], "skipped")
            self.assertTrue(row["variants"])


if __name__ == "__main__":
    unittest.main()
