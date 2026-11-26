"""Released native-node schema floor is a minimum, not an exact pin."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from native_node_contract.yueboard import check_yueboard_schema_floor  # noqa: E402


def test_candidate_may_match_or_raise_the_released_floor():
    contract = {"schema_floor": 166}
    check_yueboard_schema_floor("166", contract)
    check_yueboard_schema_floor("167", contract)
    check_yueboard_schema_floor(" 167\n", contract)


def test_candidate_must_not_drop_below_the_released_floor():
    with pytest.raises(RuntimeError, match="below the native-node contract"):
        check_yueboard_schema_floor("165", {"schema_floor": 166})


def test_candidate_floor_must_be_a_positive_integer():
    with pytest.raises(RuntimeError, match="not an integer"):
        check_yueboard_schema_floor("1.3.202", {"schema_floor": 166})
    with pytest.raises(RuntimeError, match="not an integer"):
        check_yueboard_schema_floor("0", {"schema_floor": 166})
    with pytest.raises(RuntimeError, match="not an integer"):
        check_yueboard_schema_floor("", {"schema_floor": 166})
