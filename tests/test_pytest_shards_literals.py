"""Reviewed pin literals stay in the shard config, and the count only falls."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pytest_shards.config import (  # noqa: E402
    RESTORE_DRILL_AFTER_BLOB,
    RESTORE_DRILL_BEFORE_BLOB,
)
from pytest_shards.literal_ratchet import current_counts, load_baseline, violations
from pytest_shards.skip_bindings import reviewed_restore_drill_blob_successor
import inspect


class PinLiteralRatchet(unittest.TestCase):
    def test_named_restore_drill_blobs_are_the_binding(self):
        self.assertEqual(len(RESTORE_DRILL_BEFORE_BLOB), 40)
        self.assertEqual(len(RESTORE_DRILL_AFTER_BLOB), 40)
        self.assertNotEqual(RESTORE_DRILL_BEFORE_BLOB, RESTORE_DRILL_AFTER_BLOB)
        source = inspect.getsource(reviewed_restore_drill_blob_successor)
        self.assertIn("RESTORE_DRILL_BEFORE_BLOB", source)
        self.assertIn("RESTORE_DRILL_AFTER_BLOB", source)
        self.assertNotIn(RESTORE_DRILL_BEFORE_BLOB, source)

    def test_pin_literals_outside_config_do_not_grow(self):
        baseline = load_baseline()
        counts = current_counts()
        self.assertEqual(violations(baseline, counts), [])
        self.assertEqual(counts["scripts/pytest_shards/skip_bindings.py"], 0)
        self.assertLessEqual(
            counts["scripts/pytest_shards/skip_bindings.py"],
            baseline["scripts/pytest_shards/skip_bindings.py"])


if __name__ == "__main__":
    unittest.main()
