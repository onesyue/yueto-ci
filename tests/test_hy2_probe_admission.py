"""Lock the reviewed HY2 probe signing and hash admission path.

Existing build-policy tests already forbid publication and require pinned
source SHAs. They do not fail if signed-tag verification, VALIDSIG binding,
vcs identity, or the artifact checksum sidecar is removed. This module covers
those failure paths offline and never dispatches the workflow.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/hy2-probe.yml"
HYSTERIA_SHA = "c7c91bb398460031aeda898297a5ef4743c4c583"
SUCCESSOR_SHA = "ea5418dc7468ccee899adc4680891d962ec2ccf2"
QUIC_SHA = "6e04cc5812b7d1041bd0382c953149076e1a5def"
VALIDSIG = (
    r"grep -Eq '^\[GNUPG:\] VALIDSIG CEF96E9A4ECB741C78329CA3FE2659E6AC769954 "
    r".* D9D3C6E59E7465BD07C2177142239A996FDA9F55$' "
    r'"$RUNNER_TEMP/tag-status"'
)

BUILD_REVISION_CHECK = r"""grep -Fx $'\tbuild\tvcs.revision='"$HYSTERIA_REVISION" buildinfo.txt"""

ADMISSION_MARKERS = (
    "on:\n  workflow_dispatch:\n",
    "permissions:\n  contents: read\n",
    "if: github.repository == 'onesyue/yueto-ci' && github.ref == 'refs/heads/master'",
    f"repository: onesyue/hysteria\n          ref: {HYSTERIA_SHA}\n          token: ${{{{ secrets.YUETO_CI_PAT }}}}\n",
    f"repository: onesyue/quic-go\n          ref: {QUIC_SHA}\n          token: ${{{{ secrets.YUETO_CI_PAT }}}}\n",
    "gpg --batch --import policy/policy/yueops-owner.gpg",
    'HYSTERIA_VERSION: ${{ steps.reviewed.outputs.version }}',
    'HYSTERIA_REVISION: ${{ steps.reviewed.outputs.revision }}',
    'git -C hysteria checkout --detach "$HYSTERIA_REVISION"',
    '"hysteria:core/$HYSTERIA_VERSION" "hysteria:extras/$HYSTERIA_VERSION" quic-go:v0.65.1-yue.1',
    'test "$(git -C "$repo" rev-parse "$tag^{}")" = "$(git -C "$repo" rev-parse HEAD)"',
    'git -C "$repo" verify-tag --raw "$tag"',
    VALIDSIG,
    "go build -mod=readonly -trimpath -buildvcs=true",
    BUILD_REVISION_CHECK,
    r"grep -Fx $'\tbuild\tvcs.modified=false' buildinfo.txt",
    r"grep -Fx $'\t=>\tgithub.com/onesyue/quic-go\tv0.65.1-yue.1\th1:PakWfZivnEvnlMLIinntBoQ7vYoFd8cvv1iX5gVtX54=' buildinfo.txt",
    "sha256sum hysteria-probe > SHA256SUMS",
    "name: hy2-probe-${{ steps.reviewed.outputs.revision }}",
)

FORBIDDEN_MARKERS = (
    "packages: write",
    "id-token: write",
    "contents: write",
    "build-push-action",
    "docker push",
    "imagetools create",
    "gh release",
    "continue-on-error: true",
)


def admission_issues(workflow: str) -> list[str]:
    issues: list[str] = []
    for marker in ADMISSION_MARKERS:
        if marker not in workflow:
            issues.append(f"missing {marker!r}")
    for marker in FORBIDDEN_MARKERS:
        if marker in workflow:
            issues.append(f"forbidden {marker!r}")
    on_block = workflow.split("\npermissions:", 1)[0]
    for trigger in ("push:", "pull_request:", "schedule:", "workflow_call:", "workflow_run:"):
        if trigger in on_block:
            issues.append(f"auto-build trigger present: {trigger}")
    return issues


class Hy2ProbeAdmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_dispatch_only_allows_the_two_reviewed_module_versions(self) -> None:
        workflow = yaml.load(self.workflow, Loader=yaml.BaseLoader)
        field = workflow["on"]["workflow_dispatch"]["inputs"]["probe_version"]
        self.assertEqual(field["type"], "choice")
        self.assertEqual(field["default"], "v2.14.0-yue.1")
        self.assertEqual(field["options"], ["v2.14.0-yue.1", "v2.14.0-yue.2"])
        steps = workflow["jobs"]["build"]["steps"]
        selector = next(step for step in steps if step.get("id") == "reviewed")
        self.assertEqual(selector["env"], {"REQUESTED_VERSION": "${{ inputs.probe_version }}"})
        self.assertEqual(self.workflow.count("inputs.probe_version"), 1)
        hysteria = next(
            i for i, step in enumerate(steps)
            if step.get("with", {}).get("repository") == "onesyue/hysteria"
        )
        quic = next(
            i for i, step in enumerate(steps)
            if step.get("with", {}).get("repository") == "onesyue/quic-go"
        )
        self.assertLess(steps.index(selector), hysteria)
        self.assertLess(hysteria, quic)
        self.assertNotIn("create-github-app-token", self.workflow)
        self.assertNotIn("YUETO_CI_APP_", self.workflow)
        cases = {
            "": ("v2.14.0-yue.1", HYSTERIA_SHA),
            "v2.14.0-yue.1": ("v2.14.0-yue.1", HYSTERIA_SHA),
            "v2.14.0-yue.2": ("v2.14.0-yue.2", SUCCESSOR_SHA),
            "master": None,
            SUCCESSOR_SHA: None,
            "v2.14.0-yue.3": None,
            "v2.14.0-yue.2\nrevision=other": None,
        }
        for requested, expected in cases.items():
            with self.subTest(version=requested), tempfile.TemporaryDirectory() as temp:
                output = Path(temp) / "output"
                result = subprocess.run(
                    ["bash", "-c", selector["run"]],
                    env={**os.environ, "REQUESTED_VERSION": requested, "GITHUB_OUTPUT": str(output)},
                    capture_output=True, text=True, timeout=10,
                )
                if expected is None:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(output.exists())
                else:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    version, revision = expected
                    self.assertEqual(output.read_text(), f"version={version}\nrevision={revision}\n")

    def test_build_revision_cannot_be_swapped_between_artifacts(self) -> None:
        self.assertIn(BUILD_REVISION_CHECK, self.workflow)
        for expected, wrong in [(HYSTERIA_SHA, SUCCESSOR_SHA), (SUCCESSOR_SHA, HYSTERIA_SHA)]:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temp:
                for actual in (expected, wrong):
                    Path(temp, "buildinfo.txt").write_text(f"\tbuild\tvcs.revision={actual}\n")
                    result = subprocess.run(
                        ["bash", "-c", BUILD_REVISION_CHECK], cwd=temp,
                        env={**os.environ, "HYSTERIA_REVISION": expected}, capture_output=True, timeout=10,
                    )
                    self.assertEqual(result.returncode == 0, actual == expected)

    def test_signed_tag_and_hash_admission_markers_are_present(self) -> None:
        self.assertEqual(admission_issues(self.workflow), [])

    def test_dropping_any_admission_marker_is_rejected(self) -> None:
        for marker in ADMISSION_MARKERS:
            with self.subTest(marker=marker):
                mutated = self.workflow.replace(marker, "", 1)
                self.assertNotEqual(mutated, self.workflow)
                self.assertTrue(admission_issues(mutated))

    def test_unsigned_or_wrong_signer_path_cannot_stay_hidden(self) -> None:
        for marker in (
            'git -C "$repo" verify-tag --raw "$tag"',
            VALIDSIG,
            'test "$(git -C "$repo" rev-parse "$tag^{}")" = "$(git -C "$repo" rev-parse HEAD)"',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.workflow)
                self.assertTrue(admission_issues(self.workflow.replace(marker, "true", 1)))

    def test_buildinfo_and_checksum_sidecars_are_required(self) -> None:
        for marker in (
            BUILD_REVISION_CHECK,
            r"grep -Fx $'\tbuild\tvcs.modified=false' buildinfo.txt",
            "sha256sum hysteria-probe > SHA256SUMS",
        ):
            with self.subTest(marker=marker):
                self.assertTrue(admission_issues(self.workflow.replace(marker, "", 1)))


if __name__ == "__main__":
    unittest.main()
