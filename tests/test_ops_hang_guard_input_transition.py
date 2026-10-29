"""The reviewed hang-guard input seal admits exactly one new shared helper blob."""
import copy
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("hang_guard_shards", ROOT / "scripts/pytest-shards.py")
assert SPEC is not None and SPEC.loader is not None
SHARDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARDS)

KEY = "reviewed_hang_guard_input_transition"
PATH = "tests/_subprocess.py"
BLOB = "21c2cca9901c5cea683324a269d859bdd7b784d0"
SOURCE_BEFORE = "bc583a440c466c039e8ba0c4b448012700d339a3"
SOURCE_AFTER = "03db123be8bc722cacaa47776c94776f6e8623be"


class HangGuardInputTransition(unittest.TestCase):
    def setUp(self):
        self.raw = (ROOT / "ops-pytest-skip-baseline.json").read_bytes()
        self.sealed = json.loads(self.raw)
        self.record = self.sealed[KEY]
        self.original, record = SHARDS.reviewed_hang_guard_input_transition(self.sealed)
        self.assertEqual(record, self.record)
        self.assertNotIn("reviewed_release_skip_blob_successor_transition", self.original)
        estate = self.sealed["reviewed_estate_input_transition"]
        self.estate_after = estate["source_after"]
        modes = self.sealed["reviewed_shared_input_transition"]["common_input_modes"]
        # Representative estate successor: historical inputs at their sealed blobs,
        # the estate addition, and the reviewed helper.
        _, successors = SHARDS.reviewed_estate_input_transition(self.sealed)
        self.common = dict(self.sealed["common_inputs"])
        self.files = {p: (modes[p], b) for p, b in self.common.items()}

    def test_record_is_exact_pinned_and_under_the_release_seal(self):
        canon = (json.dumps(self.sealed, indent=2, ensure_ascii=False) + "\n").encode()
        self.assertEqual(canon, self.raw)
        # Only the release skip blob successor seal sits outside this one.
        self.assertEqual(list(self.sealed)[-2:],
                         [KEY, "reviewed_release_skip_blob_successor_transition"])
        restored = (json.dumps(self.original, indent=2, ensure_ascii=False) + "\n").encode()
        self.assertEqual(self.record["prior_baseline_sha256"], SHARDS.sha(restored))
        self.assertEqual((self.record["source_before"], self.record["source_after"]),
                         (SOURCE_BEFORE, SOURCE_AFTER))
        self.assertEqual(self.record["changes"],
                         {PATH: {"before_blob": None, "after_blob": BLOB, "mode": "100644"}})
        self.assertEqual(SHARDS.sha(SHARDS.encoded(self.record)),
                         SHARDS.HANG_GUARD_INPUT_TRANSITION_SHA256)
        # Every inner seal peels this record first and sees the historical bytes.
        for peel in (SHARDS.reviewed_skip_blob_successor_transition,
                     SHARDS.reviewed_runtime_dependency_transition,
                     SHARDS.reviewed_estate_input_transition):
            historical, _ = peel(self.sealed)
            self.assertNotIn(KEY, historical)

    def test_damaged_records_are_refused(self):
        for mutate in (
            lambda r: r.__setitem__("prior_baseline_sha256", "f" * 64),
            lambda r: r.__setitem__("source_after", r["source_before"]),
            lambda r: r.__setitem__("independent_review_sha256", "0" * 64),
            lambda r: r.__setitem__("source_freeze_sha256", "x"),
            lambda r: r.__setitem__("schema", True),
            lambda r: r.__setitem__("extra", 1),
            lambda r: r["changes"][PATH].__setitem__("after_blob", "e" * 40),
            lambda r: r["changes"][PATH].__setitem__("mode", "100755"),
            lambda r: r["changes"][PATH].__setitem__("before_blob", "e" * 40),
            lambda r: r["changes"].__setitem__("tests/_other.py", dict(r["changes"][PATH])),
        ):
            baseline = copy.deepcopy(self.sealed)
            baseline.pop("reviewed_release_skip_blob_successor_transition")  # outer seal
            mutate(baseline[KEY])
            for consumer in (SHARDS.reviewed_hang_guard_input_transition,
                             SHARDS.reviewed_skip_blob_successor_transition,
                             SHARDS.reviewed_estate_input_transition):
                with self.subTest(mutate=mutate, consumer=consumer.__name__), \
                        self.assertRaisesRegex(ValueError, "hang guard input"):
                    consumer(baseline)

    def test_helper_is_refused_outside_a_proven_estate_successor(self):
        common = self.common | {PATH: BLOB}
        files = self.files | {PATH: ("100644", BLOB)}
        # Without a proven estate successor the helper is refused.
        with self.assertRaisesRegex(ValueError, "hang guard input"):
            SHARDS.admit_shared_inputs(self.sealed, common, files,
                                       source_revision=self.estate_after,
                                       estate_successor_of=None)

    def test_successor_proof_refuses_helper_on_history_unrelated_to_the_fix(self):
        """The helper may only appear in a revision that descends from the reviewed fix."""
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
            helper = Path(tmp) / PATH
            helper.parent.mkdir(parents=True)
            helper.write_text("fix\n")
            run("add", PATH)
            run("commit", "-q", "-m", "reviewed fix adds the helper")
            fix = run("rev-parse", "HEAD")
            run("commit", "-q", "--allow-empty", "-m", "later")
            later = run("rev-parse", "HEAD")
            # Same estate ancestry, helper added on a side history that never saw the fix.
            run("checkout", "-q", "-b", "side", estate)
            helper.parent.mkdir(parents=True, exist_ok=True)
            helper.write_text("fix\n")
            run("add", PATH)
            run("commit", "-q", "-m", "unrelated helper")
            side = run("rev-parse", "HEAD")
            # A wholly unrelated history carrying the helper.
            run("checkout", "-q", "--orphan", "orphan")
            run("add", PATH)
            run("commit", "-q", "-m", "orphan helper")
            orphan = run("rev-parse", "HEAD")
            hang = dict(self.record, source_after=fix)
            none = lambda b, *a: (b, None)
            with (patch.object(SHARDS, "reviewed_hang_guard_input_transition", lambda b: (b, hang)),
                  patch.object(SHARDS, "reviewed_runtime_dependency_transition", none),
                  patch.object(SHARDS, "reviewed_audit_lock_transition", none),
                  patch.object(SHARDS, "reviewed_bot_packaging_transition", none),
                  patch.object(SHARDS, "reviewed_site_lock_transition", none),
                  patch.object(SHARDS, "reviewed_estate_input_transition",
                               lambda b: (b, {"source_after": estate}))):
                self.assertEqual(SHARDS.estate_successor_proof(self.sealed, tmp, later), estate)
                for unrelated in (side, orphan):
                    with self.subTest(unrelated=unrelated), \
                            self.assertRaisesRegex(ValueError,
                                                   "hang guard successor source revision differs"):
                        SHARDS.estate_successor_proof(self.sealed, tmp, unrelated)
                # Without the helper the estate rule alone still decides.
                run("checkout", "-q", "-b", "plain", estate)
                run("commit", "-q", "--allow-empty", "-m", "no helper")
                plain = run("rev-parse", "HEAD")
                self.assertEqual(SHARDS.estate_successor_proof(self.sealed, tmp, plain), estate)


if __name__ == "__main__":
    unittest.main()
