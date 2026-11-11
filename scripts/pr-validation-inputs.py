#!/usr/bin/env python3
"""Move exact Git objects between trusted fetch and credential-free PR workers."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE).decode().strip()


def identities():
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    pr = event["pull_request"]
    if (os.environ.get("GITHUB_EVENT_NAME") != "pull_request"
            or os.environ.get("GITHUB_REPOSITORY") != "onesyue/yueops"
            or event["repository"]["full_name"] != "onesyue/yueops"
            or any(pr[k]["repo"]["full_name"] != "onesyue/yueops" for k in ("head", "base"))):
        raise ValueError("only same-repository Ops pull requests are supported")
    source, base = pr["head"]["sha"], pr["base"]["sha"]
    board = json.loads((ROOT / "native-node-contract.json").read_text())["yueboard_contract_pin"]
    if not all(re.fullmatch(r"[0-9a-f]{40}", s) for s in (source, base, board)):
        raise ValueError("source, base and Board must be exact commits")
    return {"source": source, "base": base, "board": board}


def pack(output, source, board):
    ids = identities()
    output.mkdir(parents=True, exist_ok=False)
    for name, repo in (("source", source), ("board", board)):
        if git(repo, "rev-parse", "HEAD") != ids[name]:
            raise ValueError("fetched Git identity differs")
        if name == "source":
            subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", ids["base"], ids[name]], check=True)
            for reserved in (".ci-policy", ".ci-yueboard"):
                if git(repo, "ls-tree", ids[name], "--", reserved):
                    raise ValueError("candidate occupies trusted runtime directory")
        subprocess.run(["git", "-C", str(repo), "bundle", "create", str(output / f"{name}.bundle"), "--all", "HEAD"], check=True)
    files = {name: hashlib.sha256((output / name).read_bytes()).hexdigest()
             for name in ("source.bundle", "board.bundle")}
    (output / "manifest.json").write_text(json.dumps({"schema": 1, "identities": ids, "sha256": files}, sort_keys=True))


def restore(bundle, source, board):
    ids = identities()
    manifest = json.loads((bundle / "manifest.json").read_text())
    if manifest != {"schema": 1, "identities": ids, "sha256": {
            name: hashlib.sha256((bundle / name).read_bytes()).hexdigest()
            for name in ("source.bundle", "board.bundle")}}:
        raise ValueError("source artifact identity or digest differs")
    for name, destination in (("source", source), ("board", board)):
        # Worker policy checkout is the only pre-existing source entry.
        if (destination.exists() and any(destination.iterdir())
                and (name != "source" or {p.name for p in destination.iterdir()} != {".ci-policy"})):
            raise ValueError("nonempty restoration destination")
        destination.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", str(destination)], check=True)
        subprocess.run(["git", "-C", str(destination), "fetch", "--no-tags", str(bundle / f"{name}.bundle"), ids[name]], check=True, capture_output=True)
        if name == "source":
            for reserved in (".ci-policy", ".ci-yueboard"):
                if git(destination, "ls-tree", ids[name], "--", reserved):
                    raise ValueError("candidate occupies trusted runtime directory")
        subprocess.run(["git", "-C", str(destination), "checkout", "-q", "--detach", ids[name]], check=True)
        if git(destination, "rev-parse", "HEAD") != ids[name]:
            raise ValueError("restored checkout differs")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("identity", "pack", "restore"))
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--board", type=Path)
    args = parser.parse_args()
    if args.command == "identity":
        for key, value in identities().items():
            print(f"{key}={value}")
    elif args.command == "pack":
        pack(args.directory.absolute(), args.source, args.board)
    else:
        restore(args.directory.absolute(), args.source, args.board)


if __name__ == "__main__":
    main()
