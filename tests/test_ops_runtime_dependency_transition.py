"""The reviewed runtime dependency successor admits exactly three blobs, together, on top of every seal."""
import copy
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("runtime_shards", ROOT / "scripts/pytest-shards.py")
assert SPEC is not None and SPEC.loader is not None
SHARDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARDS)
KEY = "reviewed_runtime_dependency_transition"
PATHS = set(SHARDS.RUNTIME_DEPENDENCY_INPUTS)
LOCK = "uv.lock"


class RuntimeDependencyTransition(unittest.TestCase):
    def setUp(self):
        self.sealed = json.loads((ROOT / "ops-pytest-skip-baseline.json").read_text())
        self.record = self.sealed[KEY]
        self.lock = self.sealed["reviewed_audit_lock_transition"]
        self.estate = self.sealed["reviewed_estate_input_transition"]
        self.changes = self.record["changes"]

    def test_sealed_record_is_exact_and_chained_on_each_reviewing_seal(self):
        self.assertEqual(list(self.sealed)[-4:], [KEY, "reviewed_skip_blob_successor_transition", "reviewed_hang_guard_input_transition",
                         "reviewed_release_skip_blob_successor_transition"])
        prior, record = SHARDS.reviewed_runtime_dependency_transition(self.sealed)
        self.assertEqual(record, self.record)
        self.assertNotIn(KEY, prior)
        self.assertEqual(set(record["changes"]), PATHS)
        self.assertEqual(PATHS, {"pyproject.toml", "telegram-bot/yue/requirements.txt", LOCK})
        for path, key in SHARDS.RUNTIME_DEPENDENCY_INPUTS.items():
            self.assertEqual(self.changes[path]["before_blob"],
                             self.sealed[key]["changes"][path]["after_blob"])
            self.assertEqual(self.changes[path]["mode"], "100644")
        for peel, key in ((SHARDS.reviewed_audit_lock_transition, "reviewed_audit_lock_transition"),
                          (SHARDS.reviewed_bot_packaging_transition,
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
        one = next(iter(sorted(PATHS)))
        for mutate in (
            lambda r: r.__setitem__("prior_baseline_sha256", "f" * 64),
            lambda r: r.__setitem__("source_after", r["source_before"]),
            lambda r: r.__setitem__("source_after", self.lock["source_after"]),
            lambda r: r.__setitem__("source_before", "x"),
            lambda r: r.__setitem__("independent_review_sha256", "0" * 64),
            lambda r: r.__setitem__("qualification_receipt_sha256", "x"),
            lambda r: r.__setitem__("source_freeze_sha256", None),
            lambda r: r.__setitem__("schema", True),
            lambda r: r["changes"].__setitem__("frontend/package-lock.json",
                                               dict(self.changes[LOCK])),
            lambda r: r["changes"].pop(LOCK),
            lambda r: r["changes"].pop("pyproject.toml"),
            lambda r: r["changes"][LOCK].__setitem__("before_blob", "d" * 40),
            lambda r: r["changes"]["pyproject.toml"].__setitem__("before_blob", "d" * 40),
            lambda r: r["changes"]["telegram-bot/yue/requirements.txt"].__setitem__(
                "before_blob", "d" * 40),
            lambda r: r["changes"][one].__setitem__("after_blob",
                                                    self.changes[one]["before_blob"]),
            lambda r: r["changes"][one].__setitem__("mode", "100755"),
            lambda r: r["changes"][one].__setitem__("extra", 1),
            lambda r: r.__setitem__("extra", 1),
        ):
            for consumer in (SHARDS.reviewed_runtime_dependency_transition,
                             SHARDS.reviewed_audit_lock_transition,
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

    def test_successor_blobs_only_together_through_a_proven_estate_successor(self):
        estate_common = self._estate_common()
        runtime_common = estate_common | {p: c["after_blob"] for p, c in self.changes.items()}
        later = "c" * 40
        proof = self.estate["source_after"]
        calls = []
        original = SHARDS._admit_existing_shared_inputs
        try:
            SHARDS._admit_existing_shared_inputs = lambda b, c, f=None: calls.append(dict(c))
            SHARDS.admit_shared_inputs(self.sealed, runtime_common, source_revision=later,
                                       estate_successor_of=proof)
            # uv.lock is peeled twice: runtime -> audit lock after -> audit seal after.
            self.assertEqual(calls[-1][LOCK], self.lock["changes"][LOCK]["before_blob"])
            for path in PATHS - {LOCK}:
                self.assertEqual(calls[-1][path], self.changes[path]["before_blob"])
            for source, bad in ((self.estate["source_after"], None), (later, None),
                                (later, "e" * 40)):
                with self.subTest(source=source, proof=bad), self.assertRaises(ValueError):
                    SHARDS.admit_shared_inputs(self.sealed, runtime_common, source_revision=source,
                                               estate_successor_of=bad)
            # A partial move (any one or two of the three) is refused.
            for path in PATHS:
                partial = runtime_common | {path: self.changes[path]["before_blob"]}
                with self.subTest(partial=path), self.assertRaises(ValueError):
                    SHARDS.admit_shared_inputs(self.sealed, partial, source_revision=later,
                                               estate_successor_of=proof)
            for mode in ("100755", "120000"):
                files = {p: ("100644", b) for p, b in runtime_common.items()}
                files[LOCK] = (mode, self.changes[LOCK]["after_blob"])
                with self.subTest(mode=mode), self.assertRaises(ValueError):
                    SHARDS.admit_shared_inputs(self.sealed, runtime_common, files,
                                               source_revision=later, estate_successor_of=proof)
            files = {p: ("100644", b) for p, b in runtime_common.items()}
            SHARDS.admit_shared_inputs(self.sealed, runtime_common, files, source_revision=later,
                                       estate_successor_of=proof)
            self.assertEqual(calls[-1][LOCK], self.lock["changes"][LOCK]["before_blob"])
            unsealed = copy.deepcopy(self.sealed)
            unsealed.pop("reviewed_release_skip_blob_successor_transition")
            unsealed.pop("reviewed_hang_guard_input_transition")
            unsealed.pop("reviewed_skip_blob_successor_transition")
            unsealed.pop(KEY)
            calls.clear()
            SHARDS.admit_shared_inputs(unsealed, runtime_common, source_revision=later,
                                       estate_successor_of=proof)
            self.assertEqual(calls[-1][LOCK], self.changes[LOCK]["after_blob"])
        finally:
            SHARDS._admit_existing_shared_inputs = original
        with self.assertRaises(ValueError):
            SHARDS.admit_shared_inputs(unsealed, runtime_common, source_revision=later,
                                       estate_successor_of=proof)

    def test_successor_proof_requires_ancestry_from_the_reviewed_commit(self):
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
            runtime = dict(self.record, source_after="a" * 40)
            names = ("reviewed_runtime_dependency_transition", "reviewed_audit_lock_transition",
                     "reviewed_estate_input_transition", "reviewed_site_lock_transition",
                     "reviewed_bot_packaging_transition", "git")
            saved = {n: getattr(SHARDS, n) for n in names}
            git = SHARDS.git
            try:
                SHARDS.reviewed_runtime_dependency_transition = lambda b: (b, runtime)
                SHARDS.reviewed_audit_lock_transition = lambda b: (b, None)
                SHARDS.reviewed_estate_input_transition = lambda b: (b, {"source_after": estate})
                SHARDS.reviewed_site_lock_transition = lambda b, f=None: (b, None)
                SHARDS.reviewed_bot_packaging_transition = lambda b: (b, None)

                def fake_git(source, *args):
                    if args[0] == "rev-parse" and args[1].endswith(":" + LOCK):
                        return (self.changes[LOCK]["after_blob"] + "\n").encode()
                    return git(source, *args)
                SHARDS.git = fake_git
                run("commit", "-q", "--allow-empty", "-m", "runtime")
                reviewed = run("rev-parse", "HEAD")
                run("commit", "-q", "--allow-empty", "-m", "later")
                later = run("rev-parse", "HEAD")
                runtime["source_after"] = reviewed
                self.assertEqual(SHARDS.estate_successor_proof(self.sealed, tmp, later), estate)
                run("checkout", "-q", "-b", "side", estate)
                run("commit", "-q", "--allow-empty", "-m", "unrelated")
                unrelated = run("rev-parse", "HEAD")
                with self.assertRaisesRegex(ValueError, "runtime dependency successor"):
                    SHARDS.estate_successor_proof(self.sealed, tmp, unrelated)
            finally:
                for n, v in saved.items():
                    setattr(SHARDS, n, v)


if __name__ == "__main__":
    unittest.main()
