"""The reviewed bot packaging successor admits exactly one pyproject blob on top of every seal."""
import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("bot_shards", ROOT / "scripts/pytest-shards.py")
assert SPEC is not None and SPEC.loader is not None
SHARDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARDS)
PATH = SHARDS.BOT_PACKAGING_INPUT
KEY = "reviewed_bot_packaging_transition"


class BotPackagingTransition(unittest.TestCase):
    def setUp(self):
        self.sealed = json.loads((ROOT / "ops-pytest-skip-baseline.json").read_text())
        self.record = self.sealed[KEY]
        self.estate = self.sealed["reviewed_estate_input_transition"]
        self.site = self.sealed["reviewed_site_lock_transition"]
        self.change = self.record["changes"][PATH]

    def test_sealed_record_is_exact_and_chained_on_the_estate_seal(self):
        # Only the audit lock seal may sit outside this one.
        self.assertEqual(list(self.sealed)[-4:], [KEY, "reviewed_audit_lock_transition",
                                                 "reviewed_runtime_dependency_transition",
                                                 "reviewed_skip_blob_successor_transition"])
        prior, record = SHARDS.reviewed_bot_packaging_transition(self.sealed)
        self.assertEqual(record, self.record)
        self.assertNotIn(KEY, prior)
        self.assertEqual(record["source_before"], self.estate["source_after"])
        self.assertEqual(set(record["changes"]), {PATH})
        self.assertEqual(self.change["before_blob"], self.estate["changes"][PATH]["after_blob"])
        # Every older peel still validates its own historical predecessor hash.
        for peel, key in ((SHARDS.reviewed_case_file_transition, "reviewed_case_file_transition"),
                          (SHARDS.reviewed_site_lock_transition, "reviewed_site_lock_transition"),
                          (SHARDS.reviewed_estate_input_transition, "reviewed_estate_input_transition")):
            historical, _ = peel(self.sealed)
            self.assertNotIn(KEY, historical)
            self.assertNotIn(key, historical)

    def test_damaged_records_are_refused(self):
        def damaged(mutate):
            baseline = copy.deepcopy(self.sealed)
            mutate(baseline[KEY])
            return baseline
        for mutate in (
            lambda r: r.__setitem__("prior_baseline_sha256", "f" * 64),
            lambda r: r.__setitem__("source_before", "e" * 40),
            lambda r: r.__setitem__("source_after", r["source_before"]),
            lambda r: r.__setitem__("independent_review_sha256", "0" * 64),
            lambda r: r.__setitem__("qualification_receipt_sha256", "x"),
            lambda r: r.__setitem__("schema", True),
            lambda r: r["changes"].__setitem__("qa/package.json", dict(self.change)),
            lambda r: r["changes"][PATH].__setitem__("before_blob", "d" * 40),
            lambda r: r["changes"][PATH].__setitem__("after_blob", self.change["before_blob"]),
            lambda r: r["changes"][PATH].__setitem__("mode", "100755"),
            lambda r: r.__setitem__("extra", 1),
        ):
            for consumer in (SHARDS.reviewed_bot_packaging_transition,
                             SHARDS.reviewed_case_file_transition,
                             SHARDS.reviewed_site_lock_transition,
                             SHARDS.reviewed_estate_input_transition):
                with self.subTest(mutate=mutate, consumer=consumer.__name__), \
                        self.assertRaises(ValueError):
                    consumer(damaged(mutate))

    def _estate_common(self):
        historical, _ = SHARDS.reviewed_estate_input_transition(self.sealed)
        common = dict(historical["common_inputs"])
        for path, change in self.estate["changes"].items():
            common[path] = change["after_blob"]
        return common

    def test_successor_blob_only_through_a_proven_estate_successor(self):
        estate_common = self._estate_common()
        bot_common = estate_common | {PATH: self.change["after_blob"]}
        both_common = bot_common | {
            SHARDS.SITE_LOCK_INPUT: self.site["changes"][SHARDS.SITE_LOCK_INPUT]["after_blob"]}
        later = "c" * 40
        calls = []
        original = SHARDS._admit_existing_shared_inputs
        try:
            SHARDS._admit_existing_shared_inputs = lambda b, c, f=None: calls.append(dict(c))
            for common in (bot_common, both_common):
                SHARDS.admit_shared_inputs(self.sealed, common, source_revision=later,
                                           estate_successor_of=self.estate["source_after"])
                self.assertEqual(calls[-1][PATH],
                                 self.estate["changes"][PATH]["before_blob"])
                for source, proof in ((self.estate["source_after"], None), (later, None),
                                      (later, "e" * 40)):
                    with self.subTest(source=source, proof=proof), self.assertRaises(ValueError):
                        SHARDS.admit_shared_inputs(self.sealed, common, source_revision=source,
                                                   estate_successor_of=proof)
            files = {PATH: ("100755", self.change["after_blob"])}
            with self.assertRaises(ValueError):
                SHARDS.admit_shared_inputs(self.sealed, bot_common, files, source_revision=later,
                                           estate_successor_of=self.estate["source_after"])
            # Without the bot seal the same successor blob is refused as before.
            unsealed = copy.deepcopy(self.sealed)
            unsealed.pop("reviewed_skip_blob_successor_transition")
            unsealed.pop("reviewed_runtime_dependency_transition")
            unsealed.pop("reviewed_audit_lock_transition")
            unsealed.pop(KEY)
            with self.assertRaises(ValueError):
                SHARDS.admit_shared_inputs(unsealed, bot_common, source_revision=later,
                                           estate_successor_of=self.estate["source_after"])
        finally:
            SHARDS._admit_existing_shared_inputs = original
        unknown = estate_common | {PATH: "f" * 40}
        with self.assertRaises(ValueError):
            SHARDS.admit_shared_inputs(self.sealed, unknown, source_revision=later,
                                       estate_successor_of=self.estate["source_after"])


if __name__ == "__main__":
    unittest.main()
