from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"
SERVICES = ROOT / "services.json"
README = ROOT / "README.md"
NATIVE_CONTRACT = ROOT / "native-node-contract.json"
NATIVE_VALIDATOR = ROOT / "scripts" / "validate-native-node-contract.py"


class BuildPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.services = json.loads(SERVICES.read_text(encoding="utf-8"))
        cls.readme = README.read_text(encoding="utf-8")
        cls.native_contract = json.loads(
            NATIVE_CONTRACT.read_text(encoding="utf-8")
        )
        cls.native_validator = NATIVE_VALIDATOR.read_text(encoding="utf-8")

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

    def test_self_hosted_fallback_is_manual_and_opt_in(self) -> None:
        runner_input = re.search(
            r"(?ms)^\s{6}runner:\n(?P<body>(?:^\s{8}.+\n)+)",
            self.workflow,
        )
        self.assertIsNotNone(runner_input)
        assert runner_input is not None
        self.assertIn("type: choice", runner_input.group("body"))
        self.assertIn("default: ubuntu-latest", runner_input.group("body"))
        self.assertIn("- yue-local-release", runner_input.group("body"))
        selector = (
            "github.event_name == 'workflow_dispatch' && "
            "github.event.inputs.runner || 'ubuntu-latest'"
        )
        self.assertEqual(self.workflow.count(selector), 3)
        self.assertIn("'127.0.0.1:55434:5432' || '5432:5432'", self.workflow)
        self.assertEqual(self.workflow.count("127.0.0.1:55434"), 3)

    def test_build_yml_is_the_single_real_promotion_workflow(self) -> None:
        workflow_files = sorted(
            path.name for path in WORKFLOW_DIR.glob("*.y*ml")
        )
        self.assertEqual(workflow_files, ["build.yml"])
        self.assertIn(
            "Authorize and promote verified default-branch digest",
            self.workflow,
        )
        self.assertNotIn("promote.yml", self.readme)

    def test_runner_dependencies_are_bootstrapped_and_preflighted(self) -> None:
        required = (
            "Preflight planning dependencies",
            "Install native yue-node test toolchain",
            '"${apt[@]}" install -y --no-install-recommends build-essential',
            "Preflight validation dependencies",
            'yue-node) tools+=(gcc go jq make)',
            'yueboard) tools+=(go node corepack)',
            'yueops) tools+=(jq node npm uv)',
            "Preflight build and promotion dependencies",
            'docker buildx version >/dev/null',
            "CGO_ENABLED: '1'",
            'Go race validation requires CGO_ENABLED=1',
        )
        for invariant in required:
            with self.subTest(invariant=invariant):
                self.assertIn(invariant, self.workflow)
        self.assertIn("python-version: '3.13'", self.workflow)
        self.assertIn(
            "Set up Python on GitHub-hosted runner",
            self.workflow,
        )
        self.assertIn(
            "github.event_name != 'workflow_dispatch' || "
            "github.event.inputs.runner != 'yue-local-release'",
            self.workflow,
        )
        self.assertIn(
            "Validate system Python on self-hosted runner",
            self.workflow,
        )
        self.assertIn("system_python=/usr/bin/python3", self.workflow)
        self.assertIn("sys.version_info[:2] != (3, 13)", self.workflow)
        self.assertIn('UV_PYTHON_DOWNLOADS: never', self.workflow)
        self.assertIn(
            'uv venv --python "$YUE_CI_PYTHON" .venv',
            self.workflow,
        )
        hosted_setup = self.workflow.index(
            "Set up Python on GitHub-hosted runner"
        )
        system_check = self.workflow.index(
            "Validate system Python on self-hosted runner"
        )
        hosted_selection = self.workflow.index(
            "Select Python on GitHub-hosted runner"
        )
        policy_validation = self.workflow.index(
            "Validate native-node cross-repository contract"
        )
        self.assertLess(hosted_setup, policy_validation)
        self.assertLess(hosted_selection, policy_validation)
        self.assertLess(system_check, policy_validation)
        self.assertIn(
            '"$YUE_CI_PYTHON" .ci-policy/scripts/validate-native-node-contract.py',
            self.workflow,
        )
        self.assertIn(
            "short commit refs are not reproducible; pass the exact 40-hex source SHA",
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
        pin = re.search(
            r"(?m)^  YUEBOARD_CONTRACT_PIN: ([0-9a-f]+)$",
            self.workflow,
        )
        self.assertIsNotNone(pin)
        assert pin is not None
        self.assertRegex(pin.group(1), r"^[0-9a-f]{40}$")
        self.assertIn("yueboard_contract_ref:", self.workflow)
        self.assertIn(
            "ref: ${{ needs.plan.outputs.yueboard_contract_ref }}",
            self.workflow,
        )
        self.assertIn(
            '[[ "$yueboard_contract_ref" =~ ^[0-9a-f]{40}$ ]]',
            self.workflow,
        )
        self.assertIn(
            "repository_dispatch may not override the pinned YueBoard contract",
            self.workflow,
        )
        self.assertIn(
            "promotion must use the reviewed pinned YueBoard contract",
            self.workflow,
        )
        self.assertIn(
            'echo "yueboard_contract_ref=$yueboard_contract_ref" >> "$GITHUB_OUTPUT"',
            self.workflow,
        )
        self.assertIn(
            "YUEBOARD_REPO_PATH: ${{ github.workspace }}/.ci-yueboard",
            self.workflow,
        )

    def test_native_node_contract_is_central_and_blocks_all_three_repositories(self) -> None:
        self.assertEqual(self.native_contract["version"], 2)
        self.assertEqual(self.native_contract["schema_floor"], 38)
        self.assertEqual(
            self.native_contract["layout"],
            {
                "node-1": {
                    "inventory_type": "hy2",
                    "kernel": "hysteria",
                    "artifact": "/usr/local/bin/yue-node-hy2",
                },
                "node-2": {
                    "inventory_type": "reality",
                    "kernel": "xray",
                    "artifact": "/usr/local/bin/yue-node-vless",
                },
            },
        )
        self.assertIn(
            "Checkout immutable central native-node policy",
            self.workflow,
        )
        self.assertIn("ref: ${{ github.sha }}", self.workflow)
        self.assertIn(
            "Validate native-node cross-repository contract",
            self.workflow,
        )
        self.assertIn("--kind '${{ matrix.validation }}'", self.workflow)
        self.assertIn("BUILD_PROFILE=auto", self.workflow)
        for kind in ("yue-node", "yueops", "yueboard"):
            self.assertIn(f'"{kind}"', self.native_validator)
        for rpc in (
            "/yuenode.v1.NodeControlPlane/GetConfig",
            "/yuenode.v1.NodeControlPlane/ReportMachineStatus",
        ):
            self.assertIn(rpc, json.dumps(self.native_contract))
        for rpc in (
            "/yuenode.v1.NodeControlPlane/Report",
            "/yuenode.v1.NodeControlPlane/ListMachineNodes",
        ):
            self.assertIn(rpc, self.native_contract["control"]["retired_rpcs"])
        self.assertIn("validate_yueboard", self.native_validator)

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
