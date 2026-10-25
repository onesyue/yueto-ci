#!/usr/bin/env python3
"""The reference collect must overlap independent parts and keep their order."""
import importlib.util
import threading
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "ops_shards_parallel", ROOT / "scripts" / "pytest-shards.py")
SHARDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARDS)


class ReferenceCollectParallelTest(unittest.TestCase):
    def test_bounded_map_overlaps_and_preserves_order(self):
        started = []
        release = threading.Event()

        def work(name):
            started.append(name)
            if len(started) < 2:
                self.assertTrue(release.wait(2), "the second part never started")
            else:
                release.set()
            time.sleep(0.05)
            return name

        began = time.monotonic()
        self.assertEqual(SHARDS.map_bounded([lambda: work("a"), lambda: work("b")], 2), ["a", "b"])
        self.assertLess(time.monotonic() - began, 0.2)
        self.assertEqual(SHARDS.map_bounded([lambda: "only"], 4), ["only"])
        with self.assertRaises(ValueError):
            SHARDS.map_bounded([], 0)


if __name__ == "__main__":
    unittest.main()
