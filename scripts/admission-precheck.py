#!/usr/bin/env python3
"""Read-only admission: 0 admitted, 1 rejected, 2 invalid invocation/input.

Run from the trusted yueto-ci checkout; --source is the local yueops checkout.
A head commit is admitted when it is on the default branch and signed by
policy/yueops-owner-signers.json. No checkout, source execution or network.
"""
import argparse
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

from admission_diagnostics import rejection

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("admission_policy", ROOT / "scripts/pytest-shards.py")
POLICY = importlib.util.module_from_spec(spec)
spec.loader.exec_module(POLICY)


def precheck(source, base, head):
    for revision in (base, head):
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError("--base and --head must be full commit SHAs")
        POLICY.git(source, "cat-file", "-e", revision + "^{commit}")
    after = POLICY.tree_inputs(source, head)
    # Admit a signed commit on the default branch. A new helper or conftest
    # is not a separate seal.
    try:
        bound = POLICY.source_evidence.optional(source, head)
        if bound is not None:
            POLICY.source_evidence.validate_baseline(bound, {p: blob for p, (_, blob) in after.items()})
            return True, "owner-signed source inputs bound; runtime admission still required"
        POLICY.admit_signed_default_branch(source, head)
    except POLICY.EvidenceUnavailable:
        raise
    except ValueError as error:
        return False, "source SHA is not a signed commit on the default branch: " + str(error)
    return True, "signed default-branch commit admitted"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", choices=["yueops"], required=True)
    parser.add_argument("--source", type=Path, default=ROOT.parent / "yueops")
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    args = parser.parse_args()
    try:
        accepted, reason = precheck(args.source, args.base, args.head)
    except (ValueError, OSError, subprocess.CalledProcessError, KeyError, TypeError):
        print("ADMISSION_ERROR: invalid commits, missing local history or unreadable policy", file=sys.stderr)
        return 2
    if not accepted:
        rejection(reason)
        return 1
    print("ADMISSION_ACCEPTED: " + reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
