"""Resolve the Board context through root's existing signed-desired reader."""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import re
import sys


def desired_board(root: Path) -> str:
    path = root / "scripts/release-yaml.py"
    if not path.is_file():
        raise ValueError("set YUETO_ROOT to the root checkout containing scripts/release-yaml.py")
    spec = importlib.util.spec_from_file_location("ci_check_release_yaml", path)
    if spec is None or spec.loader is None:
        raise ValueError("root signed-desired reader is unavailable")
    # The root reader honors YUETO_ROOT at import time. Bind that authority to
    # --root even when the caller's environment names another checkout.
    previous_root = os.environ.get("YUETO_ROOT")
    os.environ["YUETO_ROOT"] = str(root.resolve())
    try:
        reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reader)
        record, snapshot = reader.verified_desired()
        revision = reader.desired_revision(record, "yueboard")
        reader.assert_desired_unchanged(snapshot)
        if not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
            raise ValueError("signed desired Board revision must be an exact commit SHA")
        return revision
    finally:
        if previous_root is None:
            os.environ.pop("YUETO_ROOT", None)
        else:
            os.environ["YUETO_ROOT"] = previous_root



def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(desired_board(args.root))
    except Exception as error:
        print(f"ci-check: signed Board desired unavailable: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
