#!/usr/bin/env python3
"""Read-only frozen source contract; this does not attest test execution."""
import argparse
import importlib.util
import json
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("first_native_consumer", Path(__file__).with_name("pytest-shards.py"))
assert SPEC and SPEC.loader
CONSUMER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONSUMER)


def check(source):
    policy = CONSUMER.first_native_policy()
    revision = policy["source_revision"]
    files = CONSUMER.tree_inputs(source, revision)
    for path, blob in policy["module_blobs"].items():
        CONSUMER.require(files.get(path) == ("100644", blob), "native module mode or blob changed: " + path)
    baseline = CONSUMER.skip_baseline()
    common = CONSUMER.shared_inputs(source, revision)
    predecessor = CONSUMER.estate_successor_proof(baseline, source, revision)
    CONSUMER.admit_shared_inputs(baseline, common, files, source_revision=revision,
                                estate_successor_of=predecessor)
    return {"status": "FROZEN_SOURCE_CONTRACT_VALID", "source_revision": revision,
            "modules": len(policy["module_blobs"]), "native_case_obligations": len(policy["cases"]),
            "execution_evaluated": False, "release_acceptance": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = check(args.source)
    except (ValueError, OSError) as exc:
        parser.exit(1, str(exc) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
