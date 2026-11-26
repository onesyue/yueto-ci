#!/usr/bin/env python3
"""Report unbounded test and build steps, including the CI validation executors."""

import argparse
import re
import sys
from pathlib import Path

import yaml

BUILD_WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/build.yml"
BUILD_ACTION = "docker/build-push-action@"
TEST_OR_BUILD = re.compile(
    r"\b(?:go\s+(?:test|build)|pytest(?=[\s;&|]|$)|unittest\s+discover|flutter\s+(?:test|build)"
    r"|node\s+--test|(?:npm|pnpm|yarn|bun|make|cargo|docker(?:\s+buildx)?)"
    r"\s+(?:run\s+)?(?:test|build)(?:[:.-][\w.-]+)?|playwright\s+test)\b"
)
EXECUTOR = re.compile(
    r"\b(?:board-validation(?:-output)?\.(?:sh|py)|node-validation\.sh"
    r"|ops-validation-(?:notices|selection|backend|obligations|frontend|miniapp|node)\.sh"
    r"|ops-service-owned\.sh|ui_static_units\.py[\"']?\s+validate|yueops-ci-toolchain-selfcheck)\b"
)
TIMEOUT = re.compile(r"\$\{\{\s*fromJSON\(env\.([A-Z][A-Z0-9_]*_STEP_TIMEOUT_MINUTES)\)\s*\}\}")


def runs_tests_or_builds(step):
    commands = "\n".join(line for line in step.get("run", "").splitlines()
                         if not line.lstrip().startswith("#"))
    return (step.get("uses", "").startswith(BUILD_ACTION)
            or TEST_OR_BUILD.search(commands) or EXECUTOR.search(commands))


def timeout_errors(workflow):
    errors = []
    checked = 0
    for job_name, job in workflow["jobs"].items():
        for step in job.get("steps", []):
            if not runs_tests_or_builds(step):
                continue
            checked += 1
            label = f"{job_name} / {step.get('name') or step.get('id') or step.get('run') or step['uses']}"
            match = TIMEOUT.fullmatch(str(step.get("timeout-minutes", "")))
            if not match:
                errors.append(f"{label}: timeout-minutes must reference a named step timeout")
                continue
            variable = match[1]
            value = workflow.get("env", {}).get(variable)
            if not re.fullmatch(r"[1-9][0-9]*", str(value)):
                errors.append(f"{label}: workflow env {variable} must be positive whole minutes")
    if not checked:
        errors.append("no test or build steps found")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workflow", nargs="?", type=Path, default=BUILD_WORKFLOW)
    args = parser.parse_args()
    with args.workflow.open() as source:
        workflow = yaml.safe_load(source)
    errors = timeout_errors(workflow)
    for error in errors:
        print(error, file=sys.stderr)
    return int(bool(errors))


if __name__ == "__main__":
    sys.exit(main())
