"""Third retired-host transition: the 靠谱云.com panel mirror (2026-11-28).

yueops #1240 retired brand_literals.PANEL_MIRROR_ALTERNATE_HOST and deleted
its vhost. Validation 46037413506 then refused
test_native_unchanged_panel_site_url_bearer_and_default444, whose apex probe
lost the retired host. With exactly RETIRED_HOST_THIRD_AFTER_BLOB every other
sealed survivor is admitted with its sealed outcome and reason, and the
second and third retired ids stay absent.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pytest_shards import skip_bindings as sb  # noqa: E402
from pytest_shards import skip_report  # noqa: E402
from pytest_shards.config import (  # noqa: E402
    RETIRED_HOST_AFTER_BLOB,
    RETIRED_HOST_KEY,
    RETIRED_HOST_MODULE,
    RETIRED_HOST_SECOND_AFTER_BLOB,
    RETIRED_HOST_THIRD_AFTER_BLOB,
)
from pytest_shards.skip_baseline import retired_host_case_admitted  # noqa: E402
from pytest_shards.support import (  # noqa: E402
    RETIRED_HOST_SECOND_IDS,
    RETIRED_HOST_THIRD_IDS,
    _brand,
)

DEFAULT444 = RETIRED_HOST_MODULE + "::test_native_unchanged_panel_site_url_bearer_and_default444"


class RetiredHostThirdTransition(unittest.TestCase):
    def setUp(self):
        baseline = json.loads((ROOT / "ops-pytest-skip-baseline.json").read_text(encoding="utf-8"))
        self.retirement = baseline[RETIRED_HOST_KEY]
        self.sealed = baseline["cases"]
        self.survivors = list(self.retirement["surviving_ids"])

    def row(self, nodeid):
        sealed = self.sealed[nodeid]
        return {"outcome": sealed["outcome"], "reason": sealed["reason"]}

    def test_third_ids_are_the_alternate_panel_cases(self):
        self.assertEqual(len(RETIRED_HOST_THIRD_IDS), 3)
        self.assertTrue(all(n.endswith("[" + _brand.PANEL_MIRROR_ALTERNATE_HOST + "]")
                            for n in RETIRED_HOST_THIRD_IDS))
        self.assertTrue(RETIRED_HOST_THIRD_IDS <= set(self.survivors))
        self.assertFalse(RETIRED_HOST_THIRD_IDS & RETIRED_HOST_SECOND_IDS)
        self.assertEqual(RETIRED_HOST_THIRD_AFTER_BLOB, "2e7ad9e66349f16a144e43082d9cdcc9f2190cfc")

    def test_third_blob_admits_survivors_and_keeps_both_absences(self):
        self.assertIn(DEFAULT444, self.survivors)
        for nodeid in self.survivors:
            expected = nodeid not in RETIRED_HOST_SECOND_IDS | RETIRED_HOST_THIRD_IDS
            with self.subTest(nodeid=nodeid):
                self.assertEqual(self.sealed[nodeid]["module_blob"], RETIRED_HOST_AFTER_BLOB)
                self.assertEqual(retired_host_case_admitted(
                    self.retirement, self.sealed, nodeid, self.row(nodeid),
                    RETIRED_HOST_THIRD_AFTER_BLOB), expected)
                self.assertEqual(sb.retired_host_row_admitted(
                    self.retirement, self.sealed, nodeid, self.row(nodeid),
                    RETIRED_HOST_THIRD_AFTER_BLOB, None), expected)

    def test_second_blob_is_unchanged_and_third_ids_never_return_elsewhere(self):
        for nodeid in RETIRED_HOST_THIRD_IDS:
            self.assertTrue(retired_host_case_admitted(
                self.retirement, self.sealed, nodeid, self.row(nodeid),
                RETIRED_HOST_SECOND_AFTER_BLOB))
            self.assertFalse(sb.retired_host_row_admitted(
                self.retirement, self.sealed, nodeid, self.row(nodeid), "f" * 40, None))

    def test_changed_reason_is_refused(self):
        row = {"outcome": "skipped", "reason": "different"}
        self.assertFalse(retired_host_case_admitted(
            self.retirement, self.sealed, DEFAULT444, row, RETIRED_HOST_THIRD_AFTER_BLOB))

    def test_report_view_matches(self):
        bound = {"retirement": self.retirement, "sealed_baseline": {"cases": self.sealed}}
        for nodeid in self.survivors:
            expected = nodeid not in RETIRED_HOST_SECOND_IDS | RETIRED_HOST_THIRD_IDS
            with self.subTest(nodeid=nodeid):
                self.assertEqual(skip_report._retired_blob_admitted(
                    bound, nodeid, RETIRED_HOST_THIRD_AFTER_BLOB), expected)


if __name__ == "__main__":
    unittest.main()
