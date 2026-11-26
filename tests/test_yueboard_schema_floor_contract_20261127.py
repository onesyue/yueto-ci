"""Released schema floor is a minimum, derived from the reviewed board checkout."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from native_node_contract.yueboard import (  # noqa: E402
    check_yueboard_schema_floor,
    derive_released_schema_floor,
    schema_floor_from_git,
)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def _board_with_floors(*floors: str) -> tuple[Path, list[str]]:
    directory = tempfile.TemporaryDirectory()
    root = Path(directory.name)
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Fixture")
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "config", "commit.gpgsign", "false")
    revisions = []
    for floor in floors:
        (root / "schema-floor.txt").write_text(f"{floor}\n", encoding="utf-8")
        _git(root, "add", "schema-floor.txt")
        _git(root, "commit", "-qm", f"floor {floor}")
        revisions.append(
            subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
            ).strip()
        )
    # Keep the tree alive until the test class tears it down.
    return directory, revisions, root


class YueBoardSchemaFloorContract(unittest.TestCase):
    def test_candidate_may_match_or_raise_the_released_floor(self):
        contract = {"schema_floor": 10}
        check_yueboard_schema_floor("10", contract)
        check_yueboard_schema_floor("11", contract)
        check_yueboard_schema_floor(" 11\n", contract)

    def test_candidate_must_not_drop_below_the_released_floor(self):
        with self.assertRaisesRegex(RuntimeError, "below the native-node contract"):
            check_yueboard_schema_floor("9", {"schema_floor": 10})

    def test_candidate_floor_must_be_a_positive_integer(self):
        with self.assertRaisesRegex(RuntimeError, "not an integer"):
            check_yueboard_schema_floor("1.3.202", {"schema_floor": 10})
        with self.assertRaisesRegex(RuntimeError, "not an integer"):
            check_yueboard_schema_floor("0", {"schema_floor": 10})
        with self.assertRaisesRegex(RuntimeError, "not an integer"):
            check_yueboard_schema_floor("", {"schema_floor": 10})

    def test_released_floor_is_derived_from_the_reviewed_board_revision(self):
        holding, revisions, root = _board_with_floors("10", "11")
        self.addCleanup(holding.cleanup)
        released = schema_floor_from_git(root, revisions[0])
        self.assertEqual(released, 10)
        self.assertEqual(
            derive_released_schema_floor(root, promoted_ref=revisions[0]),
            10,
        )
        check_yueboard_schema_floor("10", board_root=root, promoted_ref=revisions[0])
        check_yueboard_schema_floor("11", board_root=root, promoted_ref=revisions[0])
        with self.assertRaisesRegex(RuntimeError, "below the native-node contract"):
            check_yueboard_schema_floor("9", board_root=root, promoted_ref=revisions[0])
        # A hand-written contract projection must not override the derived floor.
        with self.assertRaisesRegex(RuntimeError, "below the native-node contract"):
            check_yueboard_schema_floor(
                "9",
                {"schema_floor": 8},
                board_root=root,
                promoted_ref=revisions[0],
            )

    def test_promoted_ref_env_derives_the_floor_and_ignores_a_hand_written_projection(self):
        holding, revisions, root = _board_with_floors("10")
        self.addCleanup(holding.cleanup)
        previous = os.environ.get("PROMOTED_BOARD_REF")
        os.environ["PROMOTED_BOARD_REF"] = revisions[0]
        self.addCleanup(
            lambda: (
                os.environ.__setitem__("PROMOTED_BOARD_REF", previous)
                if previous is not None
                else os.environ.pop("PROMOTED_BOARD_REF", None)
            )
        )
        self.assertEqual(derive_released_schema_floor(root, contract={"schema_floor": 99}), 10)
        with self.assertRaisesRegex(RuntimeError, "below the native-node contract"):
            check_yueboard_schema_floor("9", {"schema_floor": 99}, board_root=root)


if __name__ == "__main__":
    unittest.main()
