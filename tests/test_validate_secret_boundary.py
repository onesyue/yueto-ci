"""Validate executes product code without a secret, and publish runs yueto-ci code."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")

JOB_HEADER = re.compile(r"^  ([A-Za-z0-9_-]+):\n", re.M)
STEP_HEADER = re.compile(r"^      - name: (.+)$", re.M)
# Credential setup may see a read token. Steps that execute product tests must not.
CREDENTIAL_STEPS = {
    "Verify yue-node signed fork tags",
    "Fetch the default branch for admission",
    "Fetch the default branch for evidence admission",
}
PRODUCT_STEP = re.compile(
    r"^(Validate|Run|Lint|Record|Require|Classify|Select|Set up|Keep|Download|Upload|Retain|Use the runner|Mint |Checkout )",
)
SCRIPT_RUN = re.compile(
    r"(?:^|[;&|`(])\s*(?:bash|sh|python3)\s+(\S+)", re.M)


def _job(workflow, name):
    matches = list(JOB_HEADER.finditer(workflow))
    for index, match in enumerate(matches):
        if match.group(1) != name:
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(workflow)
        return workflow[start:end]
    raise AssertionError(f"missing job {name}")


def _steps(job):
    headers = list(STEP_HEADER.finditer(job))
    steps = []
    for index, match in enumerate(headers):
        start = match.start()
        end = headers[index + 1].start() if index + 1 < len(headers) else len(job)
        steps.append((match.group(1).strip(), job[start:end]))
    return steps


def secret_findings(workflow):
    """Return reasons a validate job would expose a secret to product code."""
    findings = []
    permissions = re.search(r"^permissions:\n(?:  .+\n)+", workflow, re.M)
    if permissions is None or permissions.group(0).strip() != "permissions:\n  contents: read":
        findings.append("workflow permissions are not contents: read only")
    for name in ("validate", "validation-evidence"):
        job = _job(workflow, name)
        if re.search(r"^    permissions:\n", job, re.M):
            findings.append(f"{name} overrides workflow permissions")
        for step_name, body in _steps(job):
            if "secrets." not in body:
                continue
            if step_name in CREDENTIAL_STEPS:
                continue
            if "uses: actions/checkout@" in body and "persist-credentials: false" in body:
                continue
            if "uses: actions/create-github-app-token@" in body:
                continue
            findings.append(f"{name} step {step_name} references a secret")
    return findings


def _uncommented(script):
    return "\n".join(
        line.split("#", 1)[0] for line in script.splitlines())


def publish_script_findings(workflow):
    """Publish may run yueto-ci programs only. Product scripts stay out of it."""
    findings = []
    job = _job(workflow, "publish")
    for step_name, body in _steps(job):
        if "\n        run:" not in body and not body.lstrip().startswith("run:"):
            continue
        script = _uncommented(body.split("run:", 1)[1])
        for match in SCRIPT_RUN.finditer(script):
            target = match.group(1)
            if ".ci-policy/" in target:
                continue
            findings.append(f"publish step {step_name} runs {target}")
    return findings


class ValidateSecretBoundary(unittest.TestCase):
    def test_validate_jobs_do_not_hand_secrets_to_product_code(self):
        self.assertEqual(secret_findings(WORKFLOW), [])

    def test_a_secret_in_a_product_step_is_rejected(self):
        mutated = WORKFLOW.replace(
            "      - name: Validate yue-node\n",
            "      - name: Validate yue-node\n"
            "        env:\n"
            "          LEAKED: ${{ secrets.YUETO_CI_PAT }}\n",
            1)
        self.assertNotEqual(mutated, WORKFLOW)
        findings = secret_findings(mutated)
        self.assertTrue(any("Validate yue-node" in item for item in findings), findings)

    def test_publish_runs_yueto_ci_code_only(self):
        self.assertEqual(publish_script_findings(WORKFLOW), [])

    def test_publish_rejects_a_product_script(self):
        job = _job(WORKFLOW, "publish")
        mutated_job = job.replace(
            "bash .ci-policy/scripts/install-cosign.sh",
            "bash scripts/install-cosign.sh",
            1)
        mutated = WORKFLOW.replace(job, mutated_job, 1)
        self.assertNotEqual(mutated, WORKFLOW)
        findings = publish_script_findings(mutated)
        self.assertTrue(findings, findings)
