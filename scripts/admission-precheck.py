#!/usr/bin/env python3
"""Read-only shared-input admission: 0 admitted, 1 rejected, 2 invalid invocation/input.

Run from the trusted yueto-ci checkout; --source is the local yueops checkout.
Only committed trees are examined. No checkout, source execution or network calls.
This is shared-input admission, not a substitute for full build validation.
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
    before = POLICY.tree_inputs(source, base)
    after = POLICY.tree_inputs(source, head)
    # Use the production discovery and validator, including mode, ancestry,
    # first-native pins and every cryptographically sealed predecessor.
    try:
        bound = POLICY.source_evidence.optional(source, head)
        if bound is not None:
            POLICY.source_evidence.validate_baseline(bound, {p: blob for p, (_, blob) in after.items()})
            return True, "owner-signed source inputs bound; runtime admission still required"
        common = POLICY.shared_inputs(source, head)
        baseline = POLICY.skip_baseline()
        successor = POLICY.estate_successor_proof(baseline, source, head)
        ancestor = POLICY.release_pin_is_ancestor(source, head)
        # Same proof the build planner passes; without it a tree that no longer
        # carries the retired template writer is rejected even when the build admits it.
        retired_at = POLICY.template_writer_retirement_proof(source, head)
        POLICY.admit_shared_inputs(baseline, common, after, source_revision=head,
                                   estate_successor_of=successor,
                                   template_writer_retired_at=retired_at,
                                   pin_is_ancestor=ancestor)
    except POLICY.EvidenceUnavailable:
        raise
    except ValueError as error:
        changed = sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p))
        # Discovery may itself reject a deletion/symlink. Derive diagnostic paths
        # from the same selector without executing source code.
        try:
            relevant = set(POLICY.shared_inputs(source, base))
        except ValueError:
            relevant = set(before)
        try:
            relevant.update(POLICY.shared_inputs(source, head))
        except ValueError:
            relevant.update(changed)
        paths = ", ".join(p for p in changed if p in relevant)
        prefix = (f"shared inputs changed ({paths}) without an applicable reviewed seal in reviews/; "
                  if paths else "shared-input tree lacks an applicable reviewed seal in reviews/; ")
        return False, prefix + str(error)
    return True, "shared-input tree accepted by the build admission policy"


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
