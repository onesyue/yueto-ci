"""Report-only interop matrix CLI.

`run --report-only` writes the matrix and exits 0 when the report is written.
Pin mismatches, missing binaries, and a report that cannot be written exit non-zero.
`--strict` is for tests; a failing cell exits non-zero and an unsupported cell does not.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.request import urlopen

from client_matrix.catalog import CLIENTS, is_commit_ref
from client_matrix.live import FetchError, LiveDialer, resolve_client
from client_matrix.material import generate_material
from client_matrix.runner import build_report, execute, plans, strict_exit, write_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="client_matrix")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("catalog")
    fetch = commands.add_parser("fetch")
    fetch.add_argument("--cache", required=True)
    fetch.add_argument("--source-client", action="append", default=[])
    run = commands.add_parser("run")
    run.add_argument("--report-only", action="store_true")
    run.add_argument("--strict", action="store_true")
    run.add_argument("--yue-node-ref", required=True)
    run.add_argument("--node-hy2", required=True)
    run.add_argument("--node-vless", required=True)
    run.add_argument("--source-client", action="append", default=[])
    run.add_argument("--cache", required=True)
    run.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.command == "catalog":
        return _catalog()
    if args.command == "fetch":
        return _fetch(args.cache, args.source_client)
    return _run(args)


def _catalog() -> int:
    pins = [
        {
            "client_id": pin.client_id,
            "version": pin.version,
            "repository": pin.repository,
            "commit": pin.commit,
            "sha256": pin.sha256,
            "archive": pin.archive,
        }
        for pin in CLIENTS
    ]
    json.dump(pins, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _fetch(cache: str, source_clients: list[str]) -> int:
    try:
        _resolve_all(Path(cache), _source_map(source_clients))
    except (FetchError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


def _run(args: argparse.Namespace) -> int:
    if args.report_only == args.strict:
        print("choose exactly one of --report-only or --strict", file=sys.stderr)
        return 2
    if not is_commit_ref(args.yue_node_ref):
        print("yue-node ref must be 40 lowercase hex characters", file=sys.stderr)
        return 2
    node_bins = {"hy2": Path(args.node_hy2), "vless": Path(args.node_vless)}
    for path in node_bins.values():
        if not path.is_file():
            print("missing node binary", file=sys.stderr)
            return 2
    cache = Path(args.cache)
    try:
        sources = _source_map(args.source_client)
        client_bins = _resolve_all(cache, sources)
    except (FetchError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    dialer = LiveDialer(
        node_bins=node_bins,
        client_bins=client_bins,
        material=generate_material(),
        work=cache / "work",
    )
    try:
        results = execute(plans(), dialer.dial)
    finally:
        dialer.close()
    report = build_report(args.yue_node_ref, args.report_only, results)
    try:
        write_report(Path(args.output), report)
    except OSError as exc:
        print(f"report write failed: {exc}", file=sys.stderr)
        return 2
    if args.report_only:
        return 0
    return strict_exit(results)


def _resolve_all(cache: Path, sources: dict[str, str]) -> dict[str, Path]:
    resolved: dict[str, Path] = {}
    for pin in CLIENTS:
        resolved[pin.client_id] = resolve_client(
            pin.client_id,
            cache,
            sources.get(pin.client_id, ""),
            urlopen,
        )
    return resolved


def _source_map(items: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for item in items:
        client_id, separator, path = item.partition("=")
        if separator != "=" or client_id == "" or path == "":
            raise ValueError("source client must be client=path")
        found[client_id] = path
    return found


if __name__ == "__main__":
    sys.exit(main())
