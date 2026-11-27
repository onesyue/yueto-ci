"""Retired-host survivors follow the case-scope successor rule (2026-11-27).

#1192 (fixture include) and the 靠谱云 retirement both moved the retired-host
module blob; the hand-pinned successor blobs then rejected every surviving
skip although the cases themselves were unchanged.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from pytest_shards import skip_bindings as sb  # noqa: E402
from pytest_shards.config import RETIRED_HOST_MODULE  # noqa: E402

CASE = "test_native_policy"
NODE = f"{RETIRED_HOST_MODULE}::{CASE}[app.example]"
BASE = f'''import pytest

def helper():
    return "include a.conf"

@pytest.mark.parametrize("host", ["app.example"])
def {CASE}(host):
    assert helper()
'''


def blob(repo: Path, text: str) -> str:
    return subprocess.run(["git", "-C", str(repo), "hash-object", "-w", "--stdin"],
                          input=text.encode(), capture_output=True, check=True).stdout.decode().strip()


class RetiredHostCaseScope(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.sealed_blob = blob(self.repo, BASE)
        self.row = {"outcome": "skipped", "reason": "historical"}
        self.sealed = {NODE: {**self.row, "module_blob": self.sealed_blob}}
        self.retirement = {"surviving_ids": [NODE]}

    def tearDown(self):
        self.tmp.cleanup()

    def admitted(self, live_blob, row=None):
        return sb.retired_host_row_admitted(self.retirement, self.sealed, NODE, row or self.row,
                                            live_blob, self.repo)

    def test_edit_outside_the_case_keeps_the_survivor(self):
        live = blob(self.repo, BASE.replace('"include a.conf"', '"include a.conf b.conf"'))
        self.assertTrue(self.admitted(live))

    def test_edit_inside_the_case_is_refused(self):
        live = blob(self.repo, BASE.replace("assert helper()", "assert not helper()"))
        self.assertFalse(self.admitted(live))

    def test_changed_reason_is_refused(self):
        live = blob(self.repo, BASE + "\n# other\n")
        self.assertFalse(self.admitted(live, {"outcome": "skipped", "reason": "new"}))

    def test_non_survivor_is_refused(self):
        self.retirement = {"surviving_ids": []}
        live = blob(self.repo, BASE + "\n# other\n")
        self.assertFalse(self.admitted(live))


if __name__ == "__main__":
    unittest.main()
