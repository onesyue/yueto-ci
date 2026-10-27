"""The reviewed static-site lock successor admits exactly one blob on top of the estate seal."""
import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("site_shards", ROOT / "scripts/pytest-shards.py")
assert SPEC is not None and SPEC.loader is not None
SHARDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARDS)
PATH = SHARDS.SITE_LOCK_INPUT


class SiteLockTransition(unittest.TestCase):
    def setUp(self):
        self.sealed = json.loads((ROOT / "ops-pytest-skip-baseline.json").read_text())
        self.record = self.sealed["reviewed_site_lock_transition"]
        self.estate = self.sealed["reviewed_estate_input_transition"]
        self.change = self.record["changes"][PATH]

    def test_sealed_record_is_exact_and_chained_on_the_estate_seal(self):
        prior, record = SHARDS.reviewed_site_lock_transition(self.sealed)
        self.assertEqual(record, self.record)
        self.assertNotIn("reviewed_site_lock_transition", prior)
        self.assertEqual(record["source_before"], self.estate["source_after"])
        self.assertEqual(set(record["changes"]), {PATH})
        self.assertEqual(self.change["before_blob"], prior["common_inputs"][PATH])
        # The estate peel still validates its own historical predecessor hash.
        historical, estate = SHARDS.reviewed_estate_input_transition(self.sealed)
        self.assertEqual(estate, self.estate)
        self.assertNotIn("reviewed_site_lock_transition", historical)

    def test_damaged_records_are_refused(self):
        def damaged(mutate):
            baseline = copy.deepcopy(self.sealed)
            mutate(baseline["reviewed_site_lock_transition"])
            return baseline
        for mutate in (
            lambda r: r.__setitem__("prior_baseline_sha256", "f" * 64),
            lambda r: r.__setitem__("source_before", "e" * 40),
            lambda r: r.__setitem__("independent_review_sha256", "0" * 64),
            lambda r: r["changes"].__setitem__("site/package.json", dict(self.change)),
            lambda r: r["changes"][PATH].__setitem__("before_blob", "d" * 40),
            lambda r: r["changes"][PATH].__setitem__("mode", "100755"),
            lambda r: r.__setitem__("extra", 1),
        ):
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                SHARDS.reviewed_site_lock_transition(damaged(mutate))
            with self.subTest(consumer="estate"), self.assertRaises(ValueError):
                SHARDS.reviewed_estate_input_transition(damaged(mutate))

    def test_successor_blob_only_through_a_proven_estate_successor(self):
        historical, _ = SHARDS.reviewed_estate_input_transition(self.sealed)
        common = dict(historical["common_inputs"])
        for path, change in self.estate["changes"].items():
            common[path] = change["after_blob"]
        estate_common = dict(common)
        # The admission below goes through the real historical chain; the
        # reviewed site successor must not let anything but its exact blob in.
        site_common = estate_common | {PATH: self.change["after_blob"]}
        later = "c" * 40
        calls = []
        original = SHARDS._admit_existing_shared_inputs
        try:
            SHARDS._admit_existing_shared_inputs = lambda b, c, f=None: calls.append(dict(c))
            SHARDS.admit_shared_inputs(self.sealed, site_common, source_revision=later,
                                       estate_successor_of=self.estate["source_after"])
            self.assertEqual(calls[-1][PATH], self.change["before_blob"])
            for source, proof in ((self.estate["source_after"], None), (later, None),
                                  (later, "e" * 40)):
                with self.subTest(source=source, proof=proof), self.assertRaises(ValueError):
                    SHARDS.admit_shared_inputs(self.sealed, site_common, source_revision=source,
                                               estate_successor_of=proof)
            files = {PATH: ("100755", self.change["after_blob"])}
            with self.assertRaises(ValueError):
                SHARDS.admit_shared_inputs(self.sealed, site_common, files, source_revision=later,
                                           estate_successor_of=self.estate["source_after"])
        finally:
            SHARDS._admit_existing_shared_inputs = original
        unknown = estate_common | {PATH: "f" * 40}
        with self.assertRaises(ValueError):
            SHARDS.admit_shared_inputs(self.sealed, unknown, source_revision=later,
                                       estate_successor_of=self.estate["source_after"])


if __name__ == "__main__":
    unittest.main()
