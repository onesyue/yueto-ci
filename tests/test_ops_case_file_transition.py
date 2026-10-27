"""The reviewed case-file successor admits exact environmental skip blobs."""
import copy
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("case_file_shards", ROOT / "scripts/pytest-shards.py")
assert SPEC is not None and SPEC.loader is not None
SHARDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARDS)

RUN_ID = "40474935568"
POLICY_REVISION = "aee5ae6e41e91d9af1e9c6b0717f2726f6d3f74c"
SOURCE_REVISION = "913b251b39e8b3966c5590b40120e934b70b24eb"
RELAY = "tests/test_relay4_tuning_20261025.py"
PRIOR_RELAY_BLOB = "8a9fb90e32d6225963d4a328a7ef388ad39428e1"


def review_document(record, successors):
    cases = []
    for nodeid in sorted([*record["additions"], *record["updates"]]):
        successor = successors[nodeid]
        before = (None if nodeid in record["additions"]
                  else record["updates"][nodeid]["before_blob"])
        cases.append({
            "nodeid": nodeid, "verdict": "approve", "basis": "environmental",
            "outcome": "skipped", "reason": successor["reason"],
            "before_blob": before, "after_blob": successor["module_blob"],
        })
    return {
        "kind": "independent-case-file-review", "reviewer": "independent",
        "run_id": RUN_ID, "source_revision": SOURCE_REVISION,
        "policy_revision": POLICY_REVISION, "cases": cases,
    }


class CaseFileTransition(unittest.TestCase):
    def setUp(self):
        self.raw = (ROOT / "ops-pytest-skip-baseline.json").read_bytes()
        self.sealed = json.loads(self.raw)
        self.record = self.sealed["reviewed_case_file_transition"]
        self.original, self.successors = SHARDS.reviewed_case_file_transition(self.sealed)
        self.blobs = {}
        for nodeid, case in self.successors.items():
            self.blobs[nodeid.split("::", 1)[0]] = case["module_blob"]

    def session(self, rows):
        body = {"execution_context": self.sealed["context"], "collection_skips": {},
                "junit_sha256": "b" * 64, "nonpassing_outcomes": rows}
        return {"reference": body | {"assignment_id": "reference"},
                "shards": [copy.deepcopy(body) | {"assignment_id": "ordinary-000"}]}

    def rows(self, cases):
        return [{"nodeid": nodeid, "outcome": case["outcome"], "when": "setup",
                 "reason": case["reason"]} for nodeid, case in cases.items()]

    def value(self, blobs):
        return {"skip_module_blobs": blobs, "skip_baseline_sha256": SHARDS.sha(self.raw),
                "common_inputs": self.sealed["common_inputs"]}

    def test_record_is_pinned_to_the_independent_review_and_historical_bytes(self):
        canon = (json.dumps(self.sealed, indent=2, ensure_ascii=False) + "\n").encode()
        self.assertEqual(canon, self.raw)
        self.assertEqual(SHARDS.sha(SHARDS.encoded(self.record)), SHARDS.CASE_FILE_TRANSITION_SHA256)
        restored = (json.dumps(self.original, indent=2, ensure_ascii=False) + "\n").encode()
        self.assertEqual(self.record["prior_baseline_sha256"], SHARDS.sha(restored))
        self.assertEqual(self.record["prior_baseline_sha256"],
                         "2daf46b92038f88071c97bffbf63aed1d7c022798fb4e261481366051a59563d")
        self.assertEqual(self.record["source_revision"], SOURCE_REVISION)
        self.assertNotIn("reviewed_case_file_transition", self.original)
        review = review_document(self.record, self.successors)
        self.assertEqual(self.record["independent_review_sha256"], SHARDS.sha(SHARDS.encoded(review)))
        self.assertEqual(self.record["independent_review_sha256"],
                         "0ee3de74be00b5c08ad7fd7d80cfb1c259c92700f62dac458e3c368ac562d52b")
        self.assertEqual((len(self.record["additions"]), len(self.record["updates"]),
                          len(self.successors)), (3, 31, 34))
        prior, site = SHARDS.reviewed_site_lock_transition(self.sealed)
        self.assertIsNotNone(site)
        self.assertNotIn("reviewed_case_file_transition", prior)
        historical, estate = SHARDS.reviewed_estate_input_transition(self.sealed)
        self.assertIsNotNone(estate)
        self.assertNotIn("reviewed_case_file_transition", historical)

    def test_updates_keep_the_admitted_skip_and_additions_are_new_cases(self):
        for nodeid, change in self.record["updates"].items():
            successor = self.successors[nodeid]
            self.assertEqual(set(change), {"before_blob", "after_blob"})
            self.assertNotEqual(change["before_blob"], change["after_blob"])
            self.assertEqual(successor, {
                "outcome": "skipped", "reason": successor["reason"],
                "module_blob": change["after_blob"],
            })
            self.assertTrue(successor["reason"])
        for nodeid, case in self.record["additions"].items():
            self.assertNotIn(nodeid, self.original["cases"])
            self.assertEqual(self.successors[nodeid], case)
            self.assertEqual(case["outcome"], "skipped")
        modules = {nodeid.split("::", 1)[0] for nodeid in self.successors}
        self.assertEqual(len(self.blobs), len(modules))
        for module, blob in self.blobs.items():
            self.assertTrue(all(case["module_blob"] == blob
                                for nodeid, case in self.successors.items()
                                if nodeid.startswith(module + "::")))

    def test_consumer_accepts_reviewed_blobs_and_the_previous_relay_blob(self):
        accepted = SHARDS.admit_skips(self.value(self.blobs), self.session(self.rows(self.successors)),
                                      {"obligations": {}})
        self.assertEqual(accepted["status"], "NO_NEW_SKIPS")
        self.assertIs(accepted["skips_are_passes"], False)
        self.assertEqual(accepted["disposition_counts"], {
            "HISTORICAL_UNEXECUTED": 68, "OWNER_CANCELED": 0,
            "SAME_RUN_NATIVE_REQUIRED": 0})
        relay_cases = {nodeid: case for nodeid, case in self.successors.items()
                       if nodeid.startswith(RELAY + "::")}
        accepted = SHARDS.admit_skips(self.value({RELAY: PRIOR_RELAY_BLOB}),
                                      self.session(self.rows(relay_cases)), {"obligations": {}})
        self.assertEqual(accepted["status"], "NO_NEW_SKIPS")
        self.assertEqual(accepted["disposition_counts"]["HISTORICAL_UNEXECUTED"], 20)

    def test_consumer_rejects_unknown_blob_reason_outcome_and_new_case(self):
        result = self.session(self.rows(self.successors))
        with self.assertRaisesRegex(ValueError, "new or changed case"):
            SHARDS.admit_skips(self.value(self.blobs | {RELAY: "f" * 40}), result, {})
        for field, replacement in (("reason", "Skipped: changed reason"), ("outcome", "xfailed"),
                                   ("nodeid", RELAY + "::test_unreviewed")):
            changed = copy.deepcopy(result)
            changed["shards"][0]["nonpassing_outcomes"][0][field] = replacement
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "new or changed case"):
                SHARDS.admit_skips(self.value(self.blobs), changed, {})
        stripped = copy.deepcopy(self.sealed)
        stripped.pop("reviewed_case_file_transition")
        with (patch.object(SHARDS, "skip_baseline", return_value=stripped),
              self.assertRaisesRegex(ValueError, "new or changed case")):
            SHARDS.admit_skips(self.value(self.blobs), result, {})

    def test_reviewed_module_must_be_a_regular_file_and_the_record_cannot_drift(self):
        modes = self.sealed["reviewed_shared_input_transition"]["common_input_modes"]
        files = {path: (modes[path], blob) for path, blob in self.sealed["common_inputs"].items()}
        SHARDS.admit_shared_inputs(self.sealed, self.sealed["common_inputs"],
                                   files | {RELAY: ("100644", self.blobs[RELAY])})
        for mode in ("100755", "120000"):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "module mode changed"):
                SHARDS.admit_shared_inputs(self.sealed, self.sealed["common_inputs"],
                                           files | {RELAY: (mode, self.blobs[RELAY])})
        for mutate in (
            lambda r: r.__setitem__("independent_review_sha256", "ab" * 32),
            lambda r: r.__setitem__("prior_baseline_sha256", "f" * 64),
            lambda r: r.__setitem__("source_revision", "e" * 40),
            lambda r: r.__setitem__("schema", 2),
            lambda r: r["updates"].__setitem__(RELAY + "::test_unreviewed",
                                               {"before_blob": "a" * 40, "after_blob": "b" * 40}),
            lambda r: r.__setitem__("extra", 1),
        ):
            changed = copy.deepcopy(self.sealed)
            mutate(changed["reviewed_case_file_transition"])
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                SHARDS.reviewed_case_file_transition(changed)


if __name__ == "__main__":
    unittest.main()
