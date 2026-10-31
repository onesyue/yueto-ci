"""The reviewed yueops packaging successor admits exactly four shared inputs on top of every seal."""
import copy
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ops_packaging_shards", ROOT / "scripts/pytest-shards.py")
assert SPEC is not None and SPEC.loader is not None
SHARDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARDS)
PATH = SHARDS.OPS_PACKAGING_INPUT
ADDED = SHARDS.OPS_PACKAGING_ADDED_INPUT
BOT = "tests/_bot_real_modules.py"
BOARD = "tests/_yueboard_internal_source.py"
PATHS = (PATH, ADDED, BOT, BOARD)
KEY = SHARDS.OPS_PACKAGING_KEY
EVIDENCE_FIELDS = (
    "independent_review_sha256", "source_freeze_sha256", "qualification_receipt_sha256",
)
SOURCE_AFTER = "6588794703ce04b3756ccb8c609ec81fadffe9e4"
BOARD_SOURCE = "22a82f65eb0bf7a250fd3149915b97ef09ce61d0"
EXPECTED = {
    PATH: {"before_blob": "7f598716706f7e2e197902599e7b12b5d0ccf086",
           "after_blob": "1baeb62063307eaad0c8a395790806e2ec4ca223",
           "mode": "100644", "source": SOURCE_AFTER},
    ADDED: {"before_blob": None,
            "after_blob": "c01d34addb780f1fc0bc06440588b751e8d725ca",
            "mode": "100644", "source": SOURCE_AFTER},
    BOT: {"before_blob": "18b533829a18f5b14b5fde545e448b6195176298",
          "after_blob": "34bff7be30793eb4724ae36f0121ddd0869b80db",
          "mode": "100644", "source": SOURCE_AFTER},
    BOARD: {"before_blob": "193e85fda9c87424111800184f5abd26e1bdb8d0",
            "after_blob": "9ea0442538334dc414ffc81d50ca2f17833b888c",
            "mode": "100644", "source": BOARD_SOURCE},
}


class OpsPackagingTransition(unittest.TestCase):
    def setUp(self):
        self.raw = (ROOT / "ops-pytest-skip-baseline.json").read_bytes()
        self.sealed = json.loads(self.raw)
        # Exercise the unchanged historical envelope beneath the new hook seal.
        self.sealed, _ = SHARDS.reviewed_collection_shuffle_transition(self.sealed)
        self.raw = SHARDS.baseline_bytes(self.sealed)
        self.record = self.sealed[KEY]
        self.changes = self.record["changes"]
        self.change = self.changes[PATH]
        below, _ = SHARDS.reviewed_ops_packaging_transition(self.sealed)
        self.below = below
        _, self.tornado = SHARDS.reviewed_tornado66_dependency_transition(below)
        self.estate = self.sealed["reviewed_estate_input_transition"]

    def test_sealed_record_is_exact_outermost_and_chained_on_tornado(self):
        self.assertEqual(list(self.sealed)[-1], KEY)
        prior, record = SHARDS.reviewed_ops_packaging_transition(self.sealed)
        self.assertEqual(record, self.record)
        self.assertNotIn(KEY, prior)
        self.assertEqual(list(prior)[-1], "reviewed_i10_skip_blob_successor_transition")
        self.assertEqual(SHARDS.sha(SHARDS.encoded(record)), SHARDS.OPS_PACKAGING_TRANSITION_SHA256)
        self.assertEqual(record["prior_baseline_sha256"], SHARDS.sha(
            (json.dumps(prior, indent=2, ensure_ascii=False) + "\n").encode()))
        self.assertEqual(record["source_before"], self.tornado["source_after"])
        self.assertEqual(record["source_before"], "3cbbdd4c9b4b208ea6845e3a6681b193cbbee286")
        self.assertEqual(record["source_after"], SOURCE_AFTER)
        self.assertEqual(set(self.changes), set(PATHS))
        self.assertEqual(self.changes, EXPECTED)
        # Each predecessor is the exact reviewed one underneath.
        self.assertEqual(self.change["before_blob"], self.tornado["changes"][PATH]["after_blob"])
        modes = prior["reviewed_shared_input_transition"]["common_input_modes"]
        for path in (BOT, BOARD):
            self.assertEqual(self.changes[path]["before_blob"], prior["common_inputs"][path])
            self.assertEqual(modes[path], "100644")
        self.assertNotIn(ADDED, prior["common_inputs"])
        self.assertNotIn(ADDED, modes)
        for field in EVIDENCE_FIELDS:
            self.assertRegex(record[field], r"^[0-9a-f]{64}$")
            self.assertNotEqual(record[field], "0" * 64)
        self.assertEqual(len({record[field] for field in EVIDENCE_FIELDS}), 3)
        # The file round-trips byte for byte, and every older peel still validates.
        self.assertEqual(self.raw, (json.dumps(self.sealed, indent=2, ensure_ascii=False) + "\n").encode())
        for peel in (SHARDS.reviewed_i10_skip_blob_successor_transition,
                     SHARDS.reviewed_tornado66_dependency_transition,
                     SHARDS.reviewed_bot_packaging_transition,
                     SHARDS.reviewed_estate_input_transition):
            historical, _ = peel(self.sealed)
            self.assertNotIn(KEY, historical)

    def test_damaged_records_are_refused(self):
        def damaged(mutate):
            baseline = copy.deepcopy(self.sealed)
            mutate(baseline[KEY])
            return baseline
        mutations = [
            lambda r: r.__setitem__("prior_baseline_sha256", "f" * 64),
            lambda r: r.__setitem__("source_before", "e" * 40),
            lambda r: r.__setitem__("source_after", r["source_before"]),
            lambda r: r.__setitem__("source_after", "bad"),
            lambda r: r.__setitem__("source_after", BOARD_SOURCE),
            lambda r: r.__setitem__("independent_review_sha256", "0" * 64),
            lambda r: r.__setitem__("source_freeze_sha256", "x"),
            lambda r: r.__setitem__("qualification_receipt_sha256", "A" * 64),
            lambda r: r.__setitem__("schema", True),
            lambda r: r.__setitem__("extra", 1),
            lambda r: r.pop("source_freeze_sha256"),
            lambda r: r["changes"].__setitem__("uv.lock", dict(r["changes"][PATH])),
            lambda r: r["changes"].__setitem__("tests/_other_helper.py", dict(r["changes"][ADDED])),
            lambda r: r["changes"].__setitem__("telegram-bot/yue/pyproject.toml",
                                               r["changes"].pop(PATH)),
            lambda r: r["changes"][ADDED].__setitem__("before_blob", "d" * 40),
            lambda r: r["changes"][BOT].__setitem__("before_blob", None),
            lambda r: r["changes"][BOARD].__setitem__("before_blob",
                                                      r["changes"][BOT]["before_blob"]),
            lambda r: r["changes"][PATH].__setitem__("source", "bad"),
            lambda r: r["changes"][PATH].__setitem__("source", BOARD_SOURCE),
            lambda r: r["changes"][BOARD].__setitem__("source", r["source_before"]),
        ]
        for path in PATHS:
            mutations += [
                lambda r, p=path: r["changes"].pop(p),
                lambda r, p=path: r["changes"][p].__setitem__("before_blob", "d" * 40),
                lambda r, p=path: r["changes"][p].__setitem__("after_blob",
                                                              r["changes"][p]["before_blob"]),
                lambda r, p=path: r["changes"][p].__setitem__("after_blob", "z" * 40),
                lambda r, p=path: r["changes"][p].__setitem__("mode", "100755"),
                lambda r, p=path: r["changes"][p].pop("source"),
                lambda r, p=path: r["changes"][p].__setitem__("extra", 1),
            ]
        for mutate in mutations:
            baseline = damaged(mutate)
            for consumer in (SHARDS.reviewed_ops_packaging_transition,
                             SHARDS.reviewed_i10_skip_blob_successor_transition,
                             SHARDS.reviewed_tornado66_dependency_transition,
                             SHARDS.reviewed_estate_input_transition):
                with self.subTest(mutate=mutate, consumer=consumer.__name__), \
                        self.assertRaises(ValueError):
                    consumer(baseline)
            # Re-pinning a malformed record still fails the structural checks.
            if mutate is not mutations[0]:
                with patch.object(SHARDS, "OPS_PACKAGING_TRANSITION_SHA256",
                                  SHARDS.sha(SHARDS.encoded(baseline[KEY]))), \
                        self.subTest(mutate=mutate, repinned=True), self.assertRaises(ValueError):
                    SHARDS.reviewed_ops_packaging_transition(baseline)
        for path in (PATH, BOT, BOARD):
            changed = copy.deepcopy(self.sealed)
            changed["common_inputs"][path] = self.changes[path]["after_blob"]
            with self.subTest(historical=path), self.assertRaisesRegex(
                    ValueError, "ops packaging transition changed historical baseline"):
                SHARDS.reviewed_ops_packaging_transition(changed)

    def _common(self):
        # A full shared-input view at the reviewed Tornado successor (before this seal).
        prior, _ = SHARDS.reviewed_tornado66_dependency_transition(self.below)
        common = dict(prior["common_inputs"])
        for name, row in prior.items():
            if name.startswith("reviewed_") and isinstance(row, dict):
                if "path" in row and "after_blob" in row:
                    common[row["path"]] = row["after_blob"]
                for path, change in row.get("changes", {}).items():
                    common[path] = change["after_blob"]
        for path, change in self.tornado["changes"].items():
            common[path] = change["after_blob"]
        common.update(SHARDS.NATIVE_INPUTS)
        self.assertNotIn(ADDED, common)
        return common

    def _successor(self, common):
        return common | {path: change["after_blob"] for path, change in self.changes.items()}

    def test_successor_blobs_only_as_a_complete_bundle_through_a_proven_estate_successor(self):
        tornado_common = self._common()
        successor = self._successor(tornado_common)
        later = "c" * 40
        proof = self.estate["source_after"]
        calls = []
        with patch.object(SHARDS, "_admit_existing_shared_inputs",
                          lambda b, c, f=None: calls.append((dict(c), f and dict(f)))):
            SHARDS.admit_shared_inputs(self.sealed, successor, source_revision=later,
                                       estate_successor_of=proof)
            # Every reviewed predecessor is re-admitted underneath: the successor
            # unwinds to exactly what the plain Tornado successor unwinds to.
            SHARDS.admit_shared_inputs(self.sealed, tornado_common, source_revision=later,
                                       estate_successor_of=proof)
            self.assertEqual(calls[-2][0], calls[-1][0])
            self.assertNotIn(ADDED, calls[-2][0])
            files = {p: ("100644", b) for p, b in successor.items()}
            plain = {p: ("100644", b) for p, b in tornado_common.items()}
            SHARDS.admit_shared_inputs(self.sealed, successor, files, source_revision=later,
                                       estate_successor_of=proof)
            SHARDS.admit_shared_inputs(self.sealed, tornado_common, plain, source_revision=later,
                                       estate_successor_of=proof)
            self.assertEqual(calls[-2], calls[-1])
            self.assertNotIn(ADDED, calls[-2][1])
            for source, prf in ((self.estate["source_after"], proof), (later, None),
                                (later, "e" * 40)):
                with self.subTest(source=source, proof=prf), self.assertRaises(ValueError):
                    SHARDS.admit_shared_inputs(self.sealed, successor, source_revision=source,
                                               estate_successor_of=prf)
            for path in PATHS:
                for mode in ("100755", "120000"):
                    with self.subTest(mode=mode, path=path), self.assertRaises(ValueError):
                        SHARDS.admit_shared_inputs(
                            self.sealed, successor,
                            files | {path: (mode, self.changes[path]["after_blob"])},
                            source_revision=later, estate_successor_of=proof)
                # Partial bundle: any one input left at (or removed to) its predecessor.
                partial = dict(successor)
                if self.changes[path]["before_blob"] is None:
                    partial.pop(path)
                else:
                    partial[path] = self.changes[path]["before_blob"]
                with self.subTest(partial=path), self.assertRaises(ValueError):
                    SHARDS.admit_shared_inputs(self.sealed, partial, source_revision=later,
                                               estate_successor_of=proof)
                with self.subTest(foreign=path), self.assertRaises(ValueError):
                    SHARDS.admit_shared_inputs(self.sealed, successor | {path: "f" * 40},
                                               source_revision=later, estate_successor_of=proof)
            # Partial Tornado bundle under the packaging successor is refused.
            for path, change in self.tornado["changes"].items():
                if path == PATH:
                    continue
                partial = successor | {path: change["before_blob"]}
                with self.subTest(tornado_partial=path), self.assertRaises(ValueError):
                    SHARDS.admit_shared_inputs(self.sealed, partial, source_revision=later,
                                               estate_successor_of=proof)
            # Without this seal the same successor blobs are refused as before.
            unsealed = copy.deepcopy(self.sealed)
            unsealed.pop(KEY)
            with self.assertRaises(ValueError):
                SHARDS.admit_shared_inputs(unsealed, successor, source_revision=later,
                                           estate_successor_of=proof)

    def test_added_helper_alone_is_refused(self):
        tornado_common = self._common()
        with patch.object(SHARDS, "_admit_existing_shared_inputs", lambda b, c, f=None: None):
            with self.assertRaises(ValueError):
                SHARDS.admit_shared_inputs(
                    self.sealed, tornado_common | {ADDED: self.changes[ADDED]["after_blob"]},
                    source_revision="c" * 40, estate_successor_of=self.estate["source_after"])

    def test_planner_requires_each_source_to_introduce_its_exact_transition(self):
        with tempfile.TemporaryDirectory() as tmp:
            def git(*args):
                return subprocess.run(["git", "-C", tmp, *args], check=True,
                                      capture_output=True, text=True).stdout.strip()
            def write(path, text):
                target = Path(tmp) / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text)
                git("add", path)
            git("init", "-q")
            git("config", "user.email", "fixture@example.invalid")
            git("config", "user.name", "fixture")
            git("config", "commit.gpgsign", "false")
            git("commit", "-q", "--allow-empty", "-m", "estate")
            estate = git("rev-parse", "HEAD")
            for path in (PATH, BOT, BOARD):
                write(path, f"before {path}\n")
            git("commit", "-q", "-m", "before")
            before = git("rev-parse", "HEAD")
            write(BOARD, f"after {BOARD}\n")
            git("commit", "-q", "-m", "board helper successor")
            board_source = git("rev-parse", "HEAD")
            for path in (PATH, ADDED, BOT):
                write(path, f"after {path}\n")
            git("commit", "-q", "-m", "packaging successor")
            after = git("rev-parse", "HEAD")
            git("commit", "-q", "--allow-empty", "-m", "later")
            later = git("rev-parse", "HEAD")
            record = copy.deepcopy(self.record)
            record.update(source_before=before, source_after=after)
            for path in PATHS:
                record["changes"][path].update(
                    after_blob=git("rev-parse", f"{after}:{path}"),
                    before_blob=None if path == ADDED else git("rev-parse", f"{before}:{path}"),
                    source=board_source if path == BOARD else after)
            git("checkout", "-q", "-b", "unrelated", estate)
            for path in PATHS:
                write(path, f"after {path}\n")
            git("commit", "-q", "-m", "same bytes, unrelated source")
            unrelated = git("rev-parse", "HEAD")
            none = lambda b, *a: (b, None)
            with (patch.object(SHARDS, "reviewed_ops_packaging_transition", return_value=({}, record)),
                  patch.object(SHARDS, "reviewed_tornado66_dependency_transition", none),
                  patch.object(SHARDS, "reviewed_hang_guard_input_transition", none),
                  patch.object(SHARDS, "reviewed_runtime_dependency_transition", none),
                  patch.object(SHARDS, "reviewed_audit_lock_transition", none),
                  patch.object(SHARDS, "reviewed_bot_packaging_transition", none),
                  patch.object(SHARDS, "reviewed_site_lock_transition", none),
                  patch.object(SHARDS, "reviewed_estate_input_transition",
                               return_value=({}, {"source_after": estate}))):
                for revision in (board_source, after, later):
                    self.assertEqual(SHARDS.estate_successor_proof({}, Path(tmp), revision), estate)
                with self.assertRaisesRegex(ValueError, "ops packaging successor"):
                    SHARDS.estate_successor_proof({}, Path(tmp), unrelated)
                damages = (
                    # A source that did not itself introduce the blob.
                    (BOARD, "source", after), (PATH, "source", later),
                    (PATH, "source", board_source),
                    # A source whose parent held a different predecessor.
                    (BOT, "before_blob", "d" * 40), (ADDED, "before_blob", "d" * 40),
                    # A source that is not an ancestor of the planned revision.
                    (PATH, "source", unrelated),
                )
                for path, field, value in damages:
                    damaged = copy.deepcopy(record)
                    damaged["changes"][path][field] = value
                    with patch.object(SHARDS, "reviewed_ops_packaging_transition",
                                      return_value=({}, damaged)), \
                            self.subTest(path=path, field=field), \
                            self.assertRaisesRegex(ValueError, "ops packaging successor"):
                        SHARDS.estate_successor_proof({}, Path(tmp), later)
                record["source_before"] = unrelated
                with self.assertRaisesRegex(ValueError, "ops packaging successor"):
                    SHARDS.estate_successor_proof({}, Path(tmp), later)


if __name__ == "__main__":
    unittest.main()
