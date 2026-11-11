#!/usr/bin/env python3
"""Derive the private PR worker from the canonical ship validation jobs."""
import argparse
import copy
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHECKOUT = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
UPLOAD = "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
DOWNLOAD = "actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333"
BUNDLE = "ops-pr-source-${{ github.run_id }}-${{ github.run_attempt }}"


def checkout(pin, path=None):
    options = {"repository": "onesyue/yueto-ci", "ref": pin, "persist-credentials": False}
    if path:
        options["path"] = path
    return {"name": "Checkout fixed public policy", "uses": CHECKOUT, "with": options}


def bundle_download():
    return {"name": "Download trusted source objects", "uses": DOWNLOAD, "with": {
        "name": BUNDLE, "path": "${{ runner.temp }}/ops-pr-inputs", "digest-mismatch": "error"}}


def restore(policy, source, board):
    return {"name": "Restore exact source and Board without credentials", "run":
            f'python3 {policy}/scripts/pr-validation-inputs.py restore '
            f'--directory "$RUNNER_TEMP/ops-pr-inputs" --source {source} --board {board}'}


def derive(build, pin):
    if not re.fullmatch(r"[0-9a-f]{40}", pin):
        raise ValueError("policy must be an immutable reviewed commit")
    original = build["jobs"]
    fetch = {
        "runs-on": "ubuntu-24.04", "timeout-minutes": 10,
        "steps": [checkout(pin, ".policy"), {
            "name": "Bind exact same-repository PR and fixed Board", "id": "identity",
            "run": 'python3 .policy/scripts/pr-validation-inputs.py identity >> "$GITHUB_OUTPUT"',
        }, {
            "name": "Fetch Ops objects using only caller read permission", "uses": CHECKOUT,
            "with": {"repository": "onesyue/yueops", "ref": "${{ steps.identity.outputs.source }}",
                     "path": ".source", "fetch-depth": 0, "persist-credentials": False},
        }, {
            "name": "Fetch pinned Board with dedicated read-only identity", "uses": CHECKOUT,
            "with": {"repository": "onesyue/yueboard", "ref": "${{ steps.identity.outputs.board }}",
                     "path": ".board", "fetch-depth": 0, "persist-credentials": False,
                     "token": "${{ secrets.YUEBOARD_SOURCE_READ_TOKEN }}"},
        }, {
            "name": "Pack Git objects without credential configuration",
            "run": 'python3 .policy/scripts/pr-validation-inputs.py pack --directory "$RUNNER_TEMP/ops-pr-inputs" --source .source --board .board',
        }, {"name": "Retain private caller source objects", "uses": UPLOAD, "with": {
            "name": BUNDLE, "path": "${{ runner.temp }}/ops-pr-inputs", "if-no-files-found": "error",
            "retention-days": 1, "overwrite": False}}],
    }
    plan = {
        "needs": "fetch", "runs-on": "ubuntu-24.04", "timeout-minutes": 10,
        "env": {"YUE_CI_PR_POLICY": pin},
        "outputs": copy.deepcopy(original["plan"]["outputs"]),
        "steps": [checkout(pin), bundle_download(), restore(".", ".ops-shard-source", ".board-source"), {
            "id": "plan", "name": "Use canonical frozen single-repository target planner",
            "env": {"SOURCE_REVISION": "${{ github.event.pull_request.head.sha }}"},
            "run": '''set -euo pipefail
python3 scripts/pr-validation-inputs.py identity > "$RUNNER_TEMP/pr-identities"
bash scripts/plan-build-targets.sh yueops "$SOURCE_REVISION" | bash scripts/freeze-build-plan.sh | jq '.matrix=[] | .has_builds=false' > "$RUNNER_TEMP/build-target-plan.json"
board=$(sed -n 's/^board=//p' "$RUNNER_TEMP/pr-identities")
{
  echo "ops_source=$SOURCE_REVISION"
  echo "yueboard_contract_ref=$board"
  echo 'has_builds=false'
  echo 'promote=false'
  echo 'matrix=[]'
} >> "$GITHUB_OUTPUT"
''',
        }],
    }
    ops_plan = copy.deepcopy(next(s for s in original["plan"]["steps"] if s.get("id") == "ops_plan"))
    ops_plan["env"]["OPS_RUNNER"] = "ubuntu-24.04"
    # Do not expose arbitrary roles or capacity through reusable inputs.
    ops_plan["env"].update(OPS_SHARDS="16", OPS_CAPACITY="20")
    ops_plan["run"] += """jq -e '.source_evidence.status == "BOUND_SOURCE_EVIDENCE" and .source_evidence.admission == false' "$RUNNER_TEMP/ops-admission.json" >/dev/null
"""
    plan["steps"].append(ops_plan)
    plan["steps"].append(copy.deepcopy(original["plan"]["steps"][-1]))
    toolchain = copy.deepcopy(original["yueops-pg18-toolchain"])
    toolchain["runs-on"] = "ubuntu-24.04"
    toolchain["steps"][0] = checkout(pin)
    worker = copy.deepcopy(original["validate"])
    worker["runs-on"] = "ubuntu-24.04"
    worker["if"] = "always() && needs.plan.result == 'success' && needs.yueops-pg18-toolchain.result == 'success'"
    worker["env"]["YUE_CI_PR_POLICY"] = pin
    worker["services"]["postgres"]["ports"] = ["5432:5432"]
    removed = {"Mint read-only source token (GitHub App)", "Checkout source repo",
               "Checkout pinned YueBoard canonical contract", "Checkout immutable central native-node policy",
               "Checkout UI static unit policy"}
    fork_step = next(s for s in original["validate"]["steps"]
                     if s.get("name") == "Verify yue-node signed fork tags")
    if fork_step.get("if") != "matrix.validation == 'yue-node'":
        raise ValueError("non-Ops credential step scope changed")
    removed.add("Verify yue-node signed fork tags")
    worker["steps"] = [checkout(pin, ".ci-policy"), bundle_download(), restore(".ci-policy", ".", ".ci-yueboard")] + [
        copy.deepcopy(s) for s in original["validate"]["steps"] if s.get("name") not in removed]
    for step in worker["steps"]:
        if step.get("name") == "Lint changed YueOps SQL migrations":
            step["env"]["MIGRATION_BASE"] = "${{ github.event.pull_request.base.sha }}"
    join = copy.deepcopy(original["validation-evidence"])
    join["runs-on"] = "ubuntu-24.04"
    join["env"] = {"YUE_CI_PR_POLICY": pin}
    join["steps"] = [checkout(pin), bundle_download(), restore(".", ".admission-source", ".board-source")] + copy.deepcopy(original["validation-evidence"]["steps"][3:])
    final = {
        "name": "Ops admission and evidence", "needs": ["fetch", "plan", "yueops-pg18-toolchain", "validate", "validation-evidence"],
        "if": "always()", "runs-on": "ubuntu-24.04", "timeout-minutes": 2,
        "steps": [{"name": "Require every selected job and complete canonical join", "env": {"RESULTS": "${{ toJSON(needs) }}"},
                   "run": '''python3 - <<'PYCODE'
import json, os
needs = json.loads(os.environ["RESULTS"])
if not needs or any(job["result"] != "success" for job in needs.values()):
    raise SystemExit("complete PR admission/evidence failed or skipped")
PYCODE
'''}],
    }
    workflow = {"name": "Ops full PR validation", "on": {"workflow_call": {"secrets": {
        "YUEBOARD_SOURCE_READ_TOKEN": {"required": True, "description": "Dedicated contents:read identity for pinned Board only; never a publish token"}}}},
        "permissions": {"contents": "read"}, "jobs": {
            "fetch": fetch, "plan": plan, "yueops-pg18-toolchain": toolchain,
            "validate": worker, "validation-evidence": join, "complete": final}}
    # No hidden source token can survive a canonical worker evolution.
    for name, job in workflow["jobs"].items():
        if name != "fetch" and "secrets." in json.dumps(job):
            raise ValueError("credential entered a validation consumer")
    return workflow


class Dumper(yaml.SafeDumper):
    pass


def scalar(dumper, value):
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="|" if "\n" in value else None)


Dumper.add_representer(str, scalar)


def render(pin):
    build = yaml.safe_load((ROOT / ".github/workflows/build.yml").read_text())
    return "# Generated by scripts/generate-pr-validation.py; edit canonical build.yml or generator.\n" + yaml.dump(derive(build, pin), Dumper=Dumper, sort_keys=False, width=120)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    pin = json.loads((ROOT / "pr-validation-policy.json").read_text())["policy_revision"]
    path = ROOT / ".github/workflows/ops-pr-validation.yml"
    expected = render(pin)
    if args.check:
        if not path.is_file() or path.read_text() != expected:
            raise SystemExit("derived PR validation workflow drifted")
    else:
        path.write_text(expected)


if __name__ == "__main__":
    main()
