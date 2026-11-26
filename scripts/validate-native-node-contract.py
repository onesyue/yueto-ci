#!/usr/bin/env python3
"""Validate each source repository against the central native-node ABI."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import runpy
import sys


POLICY_ROOT = Path(__file__).resolve().parents[1]


def resolve_yueboard_contract_ref(explicit: str) -> str:
    revision = explicit
    if not explicit:
        # Use the same digest and revision reader as the image fingerprint check.
        registry = runpy.run_path(str(POLICY_ROOT / "scripts/input-fingerprint.py"))
        try:
            _, revision = registry["ghcr_latest"](
                "yueboard", os.environ["GHCR_USER"], os.environ["GHCR_PASSWORD"]
            )
        except (KeyError, registry["Unknown"]) as exc:
            raise ValueError("cannot resolve promoted YueBoard revision") from exc
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("YueBoard contract ref must be an exact 40-hex commit SHA")
    return revision


def resolve_ref_cli() -> int:
    parser = argparse.ArgumentParser(description="Select the YueBoard wire contract revision")
    parser.add_argument("--explicit", default="")
    args = parser.parse_args(sys.argv[2:])
    try:
        print(resolve_yueboard_contract_ref(args.explicit))
    except ValueError as exc:
        parser.exit(1, f"{exc}\n")
    return 0


def _bind_contract_api() -> None:
    """Load validators from the package beside this entry script."""
    script_dir = str(Path(__file__).resolve().parent)
    if script_dir not in sys.path:
        sys.path.append(script_dir)
    from native_node_contract.fragments import (
        forbid,
        forbid_casefold,
        forbid_paths,
        read,
        require,
        validate_managed_subscription_catalogue,
    )
    from native_node_contract.node import validate_node
    from native_node_contract.proto import validate_canonical_proto_mirror
    from native_node_contract.yueboard import validate_yueboard
    from native_node_contract.yuelink import validate_yuelink
    from native_node_contract.yueops import (
        validate_board_schema_input,
        validate_widget_identity_artifact,
        validate_widget_projection,
        validate_yueops,
    )

    globals().update(
        forbid=forbid,
        forbid_casefold=forbid_casefold,
        forbid_paths=forbid_paths,
        read=read,
        require=require,
        validate_board_schema_input=validate_board_schema_input,
        validate_canonical_proto_mirror=validate_canonical_proto_mirror,
        validate_managed_subscription_catalogue=validate_managed_subscription_catalogue,
        validate_node=validate_node,
        validate_widget_identity_artifact=validate_widget_identity_artifact,
        validate_widget_projection=validate_widget_projection,
        validate_yueboard=validate_yueboard,
        validate_yuelink=validate_yuelink,
        validate_yueops=validate_yueops,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--kind", choices=("yue-node", "yueops", "yueboard", "yuelink"), required=True
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--yueboard-contract-source", type=Path)
    args = parser.parse_args()
    contract = json.loads(read(POLICY_ROOT / "native-node-contract.json"))
    source = args.source.resolve()
    try:
        if args.kind == "yue-node":
            if args.yueboard_contract_source is None:
                raise RuntimeError(
                    "yue-node validation requires the separately checked-out "
                    "YueBoard canonical source"
                )
            validate_canonical_proto_mirror(
                source, args.yueboard_contract_source.resolve()
            )
            validate_node(source, contract)
        elif args.kind == "yueops":
            contract_source = (
                args.yueboard_contract_source.resolve()
                if args.yueboard_contract_source is not None
                else None
            )
            validate_yueops(source, contract, contract_source)
        elif args.kind == "yueboard":
            validate_yueboard(source, contract)
        else:
            validate_yuelink(source, contract)
    except RuntimeError as exc:
        print(f"native node contract failed: {exc}", file=sys.stderr)
        return 1
    print(f"native node contract v{contract['version']} verified for {args.kind}")
    return 0


if __name__ == "__main__" and sys.argv[1:2] == ["resolve-yueboard-ref"]:
    raise SystemExit(resolve_ref_cli())
_bind_contract_api()
if __name__ == "__main__":
    raise SystemExit(main())
