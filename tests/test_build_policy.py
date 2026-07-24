from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"
SERVICES = ROOT / "services.json"
README = ROOT / "README.md"


class BuildPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.services = json.loads(SERVICES.read_text(encoding="utf-8"))
        cls.readme = README.read_text(encoding="utf-8")

    def test_all_actions_are_pinned_to_full_commit_sha(self) -> None:
        uses = re.findall(
            r"^\s*(?:-\s*)?uses:\s*([^\s#]+)",
            self.workflow + "\n" + self.readme,
            re.MULTILINE,
        )
        self.assertTrue(uses)
        for action in uses:
            with self.subTest(action=action):
                self.assertRegex(action, r"^[^@]+@[0-9a-f]{40}$")

    def test_manual_build_is_candidate_only_by_default(self) -> None:
        promote_input = re.search(
            r"(?ms)^\s{6}promote:\n(?P<body>(?:^\s{8}.+\n)+)",
            self.workflow,
        )
        self.assertIsNotNone(promote_input)
        assert promote_input is not None
        self.assertIn("type: boolean", promote_input.group("body"))
        self.assertIn("default: false", promote_input.group("body"))
        self.assertIn("promote=$promote", self.workflow)
        self.assertIn(
            "if: needs.plan.outputs.promote == 'true'",
            self.workflow,
        )

    def test_promotion_is_bound_to_trusted_exact_default_head(self) -> None:
        required = (
            'EVENT_ACTOR" = "onesyue"',
            r"^onesyue/[A-Za-z0-9._-]+$",
            r"^[0-9a-f]{40}$",
            "repository_dispatch ref did not resolve to its exact source SHA",
            "https://api.github.com/repos/${SOURCE_REPO}",
            "branches/${default_branch}",
            "source default branch moved during promotion authorization",
            "Authorize and promote verified default-branch digest",
        )
        for invariant in required:
            with self.subTest(invariant=invariant):
                self.assertIn(invariant, self.workflow)

    def test_source_and_image_security_gates_are_present(self) -> None:
        required = (
            "scripts/check-vulnerabilities.sh",
            "golang.org/x/vuln/cmd/govulncheck@v1.6.0",
            "scripts/security_scan.sh --json",
            "pip-audit",
            "working-directory: frontend",
            "working-directory: telegram-bot/yue/miniapp",
            "npm audit --registry=https://registry.npmjs.org",
            'corepack install --global "$web_pm"',
            '[ "$web_pm" = "$admin_pm" ]',
            "squawk-cli@2.60.0",
            "aquasecurity/trivy-action@",
            "sigstore/cosign-installer@",
            "cosign-release: v3.1.2",
            "retrying with fresh OIDC token",
            'keyless_cosign sign "${IMAGE}@${DIGEST}"',
            "keyless_cosign attest",
            "FATAL: cosign ${command} failed after bounded retries",
            "FATAL: cosign verification failed after bounded retries",
            "actions/attest-build-provenance@",
        )
        for gate in required:
            with self.subTest(gate=gate):
                self.assertIn(gate, self.workflow)

    def test_yueops_tests_do_not_override_the_isolated_database_fixture(self) -> None:
        self.assertNotIn("DATABASE_URL: ''", self.workflow)

    def test_yueops_acl_validation_uses_a_pinned_yueboard_contract(self) -> None:
        self.assertIn(
            "Checkout YueBoard contract for YueOps ACL validation",
            self.workflow,
        )
        self.assertIn(
            "ref: 60eca1b13d15ec5444bd93a329eba822b37c2a77",
            self.workflow,
        )
        self.assertIn(
            "YUEBOARD_REPO_PATH: ${{ github.workspace }}/.ci-yueboard",
            self.workflow,
        )

    def test_service_matrix_is_closed_and_complete(self) -> None:
        expected_keys = {
            "service",
            "group",
            "repo",
            "ref",
            "validation",
            "context",
            "dockerfile",
            "platforms",
        }
        names = set()
        for service in self.services:
            self.assertEqual(set(service), expected_keys)
            self.assertRegex(service["repo"], r"^onesyue/[A-Za-z0-9._-]+$")
            self.assertIn(service["ref"], {"main", "master"})
            self.assertNotIn(service["service"], names)
            names.add(service["service"])
        self.assertEqual(
            names,
            {"yue-node", "yueops-web", "checkin-api", "yue-bot", "yueboard"},
        )


if __name__ == "__main__":
    unittest.main()
