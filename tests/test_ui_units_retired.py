"""AX03-A (负责人, 2026-10-30): frontends ship inside their backend images.

The four scratch UI units (ui-console, ui-miniapp, ui-site, ui-board-web) were
never built from master (no services/ui-*/Dockerfile), so registering them made
build/poll/image-rescan chase images that do not exist (rescan 404). They are
retired: no ui-* entry may come back into services.json or
validation-targets.json without a new decision. scripts/ui_static_units.py is
inert with zero units and is removed with the K6 script retirement.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def _names(path: str) -> set[str]:
    return {entry["service"] for entry in json.loads((ROOT / path).read_text())}


class UiUnitsRetiredTest(unittest.TestCase):
    def test_no_ui_units_are_registered(self) -> None:
        for path in ("services.json", "validation-targets.json"):
            with self.subTest(path=path):
                self.assertEqual({n for n in _names(path) if n.startswith("ui-")}, set())

    def test_static_unit_helper_sees_no_units(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "ui_static_units_retired", ROOT / "scripts" / "ui_static_units.py")
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        self.assertEqual(module.ui_services(), [])
        self.assertEqual(module.ui_targets(), [])


if __name__ == "__main__":
    unittest.main()
