"""The reviewed audit lock successor admits exactly one uv.lock blob on top of every seal."""
import copy
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("lock_shards", ROOT / "scripts/pytest-shards.py")
assert SPEC is not None and SPEC.loader is not None
SHARDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARDS)
PATH = SHARDS.AUDIT_LOCK_INPUT
KEY = "reviewed_audit_lock_transition"


class AuditLockTransition(unittest.TestCase):
    def setUp(self):
        self.sealed = json.loads((ROOT / "ops-pytest-skip-baseline.json").read_text())
        self.record = self.sealed[KEY]
        self.audit = self.sealed["reviewed_audit_dependency_transition"]
        self.estate = self.sealed["reviewed_estate_input_transition"]
        self.bot = self.sealed["reviewed_bot_packaging_transition"]
        self.change = self.record["changes"][PATH]

    def test_sealed_record_is_exact_and_chained_on_the_audit_seal(self):
        self.assertEqual(list(self.sealed)[-5:], [KEY, "reviewed_runtime_dependency_transition",
                                                 "reviewed_skip_blob_successor_transition", "reviewed_hang_guard_input_transition",
                         "reviewed_release_skip_blob_successor_transition"])
        prior, record = SHARDS.reviewed_audit_lock_transition(self.sealed)
        self.assertEqual(record, self.record)
        self.assertNotIn(KEY, prior)
        self.assertEqual(set(record["changes"]), {PATH})
        self.assertEqual(self.change["before_blob"], self.audit["changes"][PATH]["after_blob"])
        self.assertEqual(self.change["mode"], "100644")
        # Every older peel still validates its own historical predecessor hash.
        for peel, key in ((SHARDS.reviewed_bot_packaging_transition,
                           "reviewed_bot_packaging_transition"),
                          (SHARDS.reviewed_case_file_transition, "reviewed_case_file_transition"),
                          (SHARDS.reviewed_site_lock_transition, "reviewed_site_lock_transition"),
                          (SHARDS.reviewed_estate_input_transition,
                           "reviewed_estate_input_transition")):
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
            lambda r: r.__setitem__("source_after", r["source_before"]),
            lambda r: r.__setitem__("source_after", self.bot["source_after"]),
            lambda r: r.__setitem__("source_before", "x"),
            lambda r: r.__setitem__("independent_review_sha256", "0" * 64),
            lambda r: r.__setitem__("qualification_receipt_sha256", "x"),
            lambda r: r.__setitem__("source_freeze_sha256", None),
            lambda r: r.__setitem__("schema", True),
            lambda r: r["changes"].__setitem__("pyproject.toml", dict(self.change)),
            lambda r: r["changes"].pop(PATH),
            lambda r: r["changes"][PATH].__setitem__("before_blob", "d" * 40),
            lambda r: r["changes"][PATH].__setitem__("after_blob", self.change["before_blob"]),
            lambda r: r["changes"][PATH].__setitem__("mode", "100755"),
            lambda r: r["changes"][PATH].__setitem__("extra", 1),
            lambda r: r.__setitem__("extra", 1),
        ):
            for consumer in (SHARDS.reviewed_audit_lock_transition,
                             SHARDS.reviewed_bot_packaging_transition,
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
        lock_common = estate_common | {PATH: self.change["after_blob"]}
        both_common = lock_common | {
            SHARDS.BOT_PACKAGING_INPUT:
                self.bot["changes"][SHARDS.BOT_PACKAGING_INPUT]["after_blob"]}
        later = "c" * 40
        calls = []
        original = SHARDS._admit_existing_shared_inputs
        try:
            SHARDS._admit_existing_shared_inputs = lambda b, c, f=None: calls.append(dict(c))
            for common in (lock_common, both_common):
                SHARDS.admit_shared_inputs(self.sealed, common, source_revision=later,
                                           estate_successor_of=self.estate["source_after"])
                # The audit seal's exact after-blob is what the historical chain re-admits.
                self.assertEqual(calls[-1][PATH], self.change["before_blob"])
                for source, proof in ((self.estate["source_after"], None), (later, None),
                                      (later, "e" * 40)):
                    with self.subTest(source=source, proof=proof), self.assertRaises(ValueError):
                        SHARDS.admit_shared_inputs(self.sealed, common, source_revision=source,
                                                   estate_successor_of=proof)
            for mode in ("100755", "120000"):
                files = {PATH: (mode, self.change["after_blob"])}
                with self.subTest(mode=mode), self.assertRaises(ValueError):
                    SHARDS.admit_shared_inputs(self.sealed, lock_common, files,
                                               source_revision=later,
                                               estate_successor_of=self.estate["source_after"])
            files = {path: ("100644", blob) for path, blob in lock_common.items()}
            SHARDS.admit_shared_inputs(self.sealed, lock_common, files, source_revision=later,
                                       estate_successor_of=self.estate["source_after"])
            self.assertEqual(calls[-1][PATH], self.change["before_blob"])
            # Without the lock seal the same successor blob is refused as before.
            unsealed = copy.deepcopy(self.sealed)
            unsealed.pop("reviewed_release_skip_blob_successor_transition")
            unsealed.pop("reviewed_hang_guard_input_transition")
            unsealed.pop("reviewed_skip_blob_successor_transition")
            unsealed.pop("reviewed_runtime_dependency_transition")
            unsealed.pop(KEY)
            calls.clear()
            SHARDS.admit_shared_inputs(unsealed, lock_common, source_revision=later,
                                       estate_successor_of=self.estate["source_after"])
            self.assertEqual(calls[-1][PATH], self.change["after_blob"])
        finally:
            SHARDS._admit_existing_shared_inputs = original
        with self.assertRaises(ValueError):
            SHARDS.admit_shared_inputs(unsealed, lock_common, source_revision=later,
                                       estate_successor_of=self.estate["source_after"])
        unknown = estate_common | {PATH: "f" * 40}
        with self.assertRaises(ValueError):
            SHARDS.admit_shared_inputs(self.sealed, unknown, source_revision=later,
                                       estate_successor_of=self.estate["source_after"])

    def test_successor_proof_requires_ancestry_from_the_reviewed_lock_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            def run(*args):
                return subprocess.run(["git", "-C", tmp, *args], check=True,
                                      capture_output=True, text=True).stdout.strip()
            run("init", "-q")
            run("config", "user.email", "t@example.invalid")
            run("config", "user.name", "t")
            run("config", "commit.gpgsign", "false")
            run("commit", "-q", "--allow-empty", "-m", "estate")
            estate = run("rev-parse", "HEAD")
            blob = self.change["after_blob"]
            sealed = copy.deepcopy(self.sealed)
            sealed["reviewed_estate_input_transition"]["source_after"] = estate
            # Rewriting the inner seal invalidates the outer hashes, so exercise the
            # ancestry rule with a patched peel instead of a forged record.
            lock = dict(self.record, source_after="a" * 40)
            orig_lock = SHARDS.reviewed_audit_lock_transition
            orig_estate = SHARDS.reviewed_estate_input_transition
            orig_site = SHARDS.reviewed_site_lock_transition
            orig_bot = SHARDS.reviewed_bot_packaging_transition
            orig_runtime = SHARDS.reviewed_runtime_dependency_transition
            orig_hang = SHARDS.reviewed_hang_guard_input_transition
            git = SHARDS.git
            try:
                SHARDS.reviewed_hang_guard_input_transition = lambda b: (b, None)
                SHARDS.reviewed_runtime_dependency_transition = lambda b: (b, None)
                SHARDS.reviewed_audit_lock_transition = lambda b: (b, lock)
                SHARDS.reviewed_estate_input_transition = lambda b: (b, {"source_after": estate})
                SHARDS.reviewed_site_lock_transition = lambda b, f=None: (b, None)
                SHARDS.reviewed_bot_packaging_transition = lambda b: (b, None)

                def fake_git(source, *args):
                    if args[0] == "rev-parse" and args[1].endswith(":" + PATH):
                        return (blob + "\n").encode()
                    return git(source, *args)
                SHARDS.git = fake_git
                run("commit", "-q", "--allow-empty", "-m", "lock")
                reviewed = run("rev-parse", "HEAD")
                run("commit", "-q", "--allow-empty", "-m", "later")
                later = run("rev-parse", "HEAD")
                lock["source_after"] = reviewed
                self.assertEqual(SHARDS.estate_successor_proof(sealed, tmp, later), estate)
                run("checkout", "-q", "-b", "side", estate)
                run("commit", "-q", "--allow-empty", "-m", "unrelated")
                unrelated = run("rev-parse", "HEAD")
                with self.assertRaisesRegex(ValueError, "audit lock successor"):
                    SHARDS.estate_successor_proof(sealed, tmp, unrelated)
            finally:
                SHARDS.reviewed_audit_lock_transition = orig_lock
                SHARDS.reviewed_estate_input_transition = orig_estate
                SHARDS.reviewed_site_lock_transition = orig_site
                SHARDS.reviewed_bot_packaging_transition = orig_bot
                SHARDS.reviewed_runtime_dependency_transition = orig_runtime
                SHARDS.reviewed_hang_guard_input_transition = orig_hang
                SHARDS.git = git


if __name__ == "__main__":
    unittest.main()
