"""Lock the reviewed HY2 probe signing and hash admission path.

Existing build-policy tests already forbid publication and require pinned
source SHAs. They do not fail if signed-tag verification, VALIDSIG binding,
vcs identity, or the artifact checksum sidecar is removed. This module covers
those failure paths offline and never dispatches the workflow.
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/hy2-probe.yml"
HYSTERIA_SHA = "c7c91bb398460031aeda898297a5ef4743c4c583"
QUIC_SHA = "6e04cc5812b7d1041bd0382c953149076e1a5def"
VALIDSIG = (
    r"grep -Eq '^\[GNUPG:\] VALIDSIG CEF96E9A4ECB741C78329CA3FE2659E6AC769954 "
    r".* D9D3C6E59E7465BD07C2177142239A996FDA9F55$' "
    r'"$RUNNER_TEMP/tag-status"'
)

ADMISSION_MARKERS = (
    "on:\n  workflow_dispatch:\n",
    "permissions:\n  contents: read\n",
    "if: github.repository == 'onesyue/yueto-ci' && github.ref == 'refs/heads/master'",
    "repositories: hysteria,quic-go",
    "permission-contents: read",
    f"repository: onesyue/hysteria\n          ref: {HYSTERIA_SHA}\n",
    f"repository: onesyue/quic-go\n          ref: {QUIC_SHA}\n",
    "gpg --batch --import policy/policy/yueops-owner.gpg",
    "hysteria:core/v2.14.0-yue.1 hysteria:extras/v2.14.0-yue.1 quic-go:v0.65.1-yue.1",
    'test "$(git -C "$repo" rev-parse "$tag^{}")" = "$(git -C "$repo" rev-parse HEAD)"',
    'git -C "$repo" verify-tag --raw "$tag"',
    VALIDSIG,
    "go build -mod=readonly -trimpath -buildvcs=true",
    rf"grep -Fx $'\tbuild\tvcs.revision={HYSTERIA_SHA}' buildinfo.txt",
    r"grep -Fx $'\tbuild\tvcs.modified=false' buildinfo.txt",
    r"grep -Fx $'\t=>\tgithub.com/onesyue/quic-go\tv0.65.1-yue.1\th1:PakWfZivnEvnlMLIinntBoQ7vYoFd8cvv1iX5gVtX54=' buildinfo.txt",
    "sha256sum hysteria-probe > SHA256SUMS",
    f"name: hy2-probe-{HYSTERIA_SHA}",
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
            rf"grep -Fx $'\tbuild\tvcs.revision={HYSTERIA_SHA}' buildinfo.txt",
            r"grep -Fx $'\tbuild\tvcs.modified=false' buildinfo.txt",
            "sha256sum hysteria-probe > SHA256SUMS",
        ):
            with self.subTest(marker=marker):
                self.assertTrue(admission_issues(self.workflow.replace(marker, "", 1)))


if __name__ == "__main__":
    unittest.main()
