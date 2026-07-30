from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"
SERVICES = ROOT / "services.json"
VALIDATION_TARGETS = ROOT / "validation-targets.json"
README = ROOT / "README.md"
NATIVE_CONTRACT = ROOT / "native-node-contract.json"
NATIVE_VALIDATOR = ROOT / "scripts" / "validate-native-node-contract.py"
TARGET_PLANNER = ROOT / "scripts" / "plan-build-targets.sh"


class BuildPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.services = json.loads(SERVICES.read_text(encoding="utf-8"))
        cls.validation_targets = json.loads(
            VALIDATION_TARGETS.read_text(encoding="utf-8")
        )
        cls.readme = README.read_text(encoding="utf-8")
        cls.native_contract = json.loads(NATIVE_CONTRACT.read_text(encoding="utf-8"))
        cls.native_validator = NATIVE_VALIDATOR.read_text(encoding="utf-8")
        cls.target_planner = TARGET_PLANNER.read_text(encoding="utf-8")

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
        workflow_files = sorted(path.name for path in WORKFLOW_DIR.glob("*.y*ml"))
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
            "yue-node) tools+=(docker gcc go jq make)",
            "yueboard) tools+=(docker go node corepack)",
            "yueops) tools+=(docker jq node npm uv)",
            "Preflight build and promotion dependencies",
            "docker buildx version >/dev/null",
            "CGO_ENABLED: '1'",
            "Go race validation requires CGO_ENABLED=1",
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
        self.assertIn("UV_PYTHON_DOWNLOADS: never", self.workflow)
        self.assertIn(
            'uv venv --python "$YUE_CI_PYTHON" .venv',
            self.workflow,
        )
        hosted_setup = self.workflow.index("Set up Python on GitHub-hosted runner")
        system_check = self.workflow.index(
            "Validate system Python on self-hosted runner"
        )
        hosted_selection = self.workflow.index("Select Python on GitHub-hosted runner")
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
        self.assertIn("make build", self.workflow)
        self.assertNotIn("go build ./...", self.workflow)

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
            "scripts/npm-audit-gate.py",
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

    def test_yueops_npm_audit_policy_is_owned_by_the_checked_out_source(self) -> None:
        frontend_start = self.workflow.index("- name: Validate yueops frontend")
        miniapp_start = self.workflow.index("- name: Validate Yue mini app")
        migration_start = self.workflow.index(
            "- name: Lint changed YueOps SQL migrations"
        )
        frontend_step = self.workflow[frontend_start:miniapp_start]
        miniapp_step = self.workflow[miniapp_start:migration_start]

        expected_gate = 'audit_gate="$GITHUB_WORKSPACE/scripts/npm-audit-gate.py"'
        self.assertIn(expected_gate, frontend_step)
        self.assertIn(expected_gate, miniapp_step)
        self.assertEqual(self.workflow.count(expected_gate), 2)

        # A source checkout that omitted its reviewed policy must stop the
        # release.  The central builder must never grow an independent
        # advisory-ID allowlist that can drift from the product topology.
        missing_gate_guard = '[ -f "$audit_gate" ] || {'
        self.assertIn(missing_gate_guard, frontend_step)
        self.assertIn(missing_gate_guard, miniapp_step)
        frontend_call = (
            '"$YUE_CI_PYTHON" "$audit_gate" "$GITHUB_WORKSPACE/frontend"'
        )
        self.assertIn(frontend_call, frontend_step)
        self.assertIn(
            '"$GITHUB_WORKSPACE/telegram-bot/yue/miniapp"',
            miniapp_step,
        )
        self.assertIn(
            "exit 1",
            frontend_step[
                frontend_step.index(missing_gate_guard) : frontend_step.index(
                    frontend_call
                )
            ],
        )
        self.assertIn(
            "exit 1",
            miniapp_step[
                miniapp_step.index(missing_gate_guard) : miniapp_step.index(
                    '"$YUE_CI_PYTHON" "$audit_gate"'
                )
            ],
        )
        self.assertNotIn("GHSA-", frontend_step + miniapp_step)
        self.assertNotIn("npm audit --", frontend_step + miniapp_step)

    def test_central_release_runs_the_miniapp_source_linter(self) -> None:
        miniapp_start = self.workflow.index("- name: Validate Yue mini app")
        migration_start = self.workflow.index(
            "- name: Lint changed YueOps SQL migrations"
        )
        miniapp_step = self.workflow[miniapp_start:migration_start]

        self.assertIn("working-directory: telegram-bot/yue/miniapp", miniapp_step)
        self.assertIn("npm ci", miniapp_step)
        self.assertIn("npm run lint", miniapp_step)
        self.assertIn("npm run build", miniapp_step)
        self.assertLess(miniapp_step.index("npm ci"), miniapp_step.index("npm run lint"))
        self.assertLess(
            miniapp_step.index("npm run lint"), miniapp_step.index("npm run build")
        )

    def test_yueops_tests_do_not_override_the_isolated_database_fixture(self) -> None:
        self.assertNotIn("DATABASE_URL: ''", self.workflow)

    def test_yueops_acl_validation_uses_a_pinned_yueboard_contract(self) -> None:
        self.assertIn(
            "Checkout YueBoard contract for YueOps ACL validation",
            self.workflow,
        )
        pin = self.native_contract["yueboard_contract_pin"]
        self.assertRegex(pin, r"^[0-9a-f]{40}$")
        self.assertIn(".yueboard_contract_pin", self.workflow)
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
            'yueboard_contract_ref" != "$yueboard_contract_pin',
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
        self.assertIn(
            "--yueboard-contract-source .ci-yueboard",
            self.workflow,
        )
        self.assertIn(
            "pinned YueBoard contract schema floor does not match central policy",
            self.native_validator,
        )

    def test_native_node_contract_is_central_and_blocks_all_product_repositories(
        self,
    ) -> None:
        self.assertEqual(self.native_contract["version"], 4)
        self.assertEqual(self.native_contract["schema_floor"], 46)
        self.assertEqual(
            self.native_contract["presence"],
            {
                "required_capabilities": [
                    "credential_limit_v1",
                    "presence_v2",
                ],
                "report_rpc": "/yuenode.v1.NodeControlPlane/ReportDevices",
                "rollout_proof_endpoint": "/api/v1/internal/yueops/nodes/rollout",
                "process_lease_seconds": 240,
                "rollout_order": [
                    "yueboard_control_plane_locked",
                    "yue_node_fleet",
                    "credential_consumers",
                ],
            },
        )
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
        self.assertEqual(
            self.native_contract["device_identity"],
            {
                "count_basis": "authenticated_credential",
                "count_equation": "online_device_rows_plus_shared_online_bit",
                "legacy_shared_online_max": 1,
                "synthetic_credential_id_floor": 1_000_000_000,
                "diagnostic_only": [
                    "ip",
                    "connection",
                    "protocol",
                    "node",
                    "user_agent",
                ],
                "devices_endpoint": "/api/v1/user/devices",
                "overview_endpoint": "/api/v1/user/overview",
                "reset_endpoint": "/api/v1/user/devices/reset-all",
                "reset_identity_field": "applied_user_ids",
                "device_subscription_prefix": "/d/",
                "legacy_subscription_prefix": "/s/",
                "third_party_enrollment": "target_device_local_stable_id",
                "presence_sources": ["memory", "database_projection"],
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
        for kind in ("yue-node", "yueops", "yueboard", "yuelink"):
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

    def test_yuelink_is_a_remote_validation_only_target(self) -> None:
        self.assertEqual(
            self.validation_targets,
            [
                {
                    "service": "yuelink",
                    "group": "yuelink",
                    "repo": "onesyue/yuelink",
                    "ref": "master",
                    "validation": "yuelink",
                }
            ],
        )
        self.assertNotIn("yuelink", {service["service"] for service in self.services})
        self.assertIn("scripts/plan-build-targets.sh", self.workflow)
        self.assertIn("validation-targets.json", self.target_planner)
        self.assertIn(
            "validation-only targets cannot be promoted as container images",
            self.workflow,
        )
        self.assertIn("has_builds: ${{ steps.plan.outputs.has_builds }}", self.workflow)
        self.assertIn(
            "if: needs.plan.outputs.has_builds == 'true'",
            self.workflow,
        )
        self.assertIn("yuelink) ;;", self.workflow)
        self.assertIn(
            "matrix.validation == 'yueboard' || matrix.validation == 'yuelink'",
            self.workflow,
        )
        self.assertIn(
            "-f service=yuelink -f ref=<40-hex-yuelink-sha>",
            self.readme,
        )

        exact_ref = "a" * 40
        result = subprocess.run(
            ["bash", str(TARGET_PLANNER), "yuelink", exact_ref],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        plan = json.loads(result.stdout)
        self.assertEqual(plan["matrix"], [])
        self.assertFalse(plan["has_builds"])
        self.assertEqual(
            plan["validation_matrix"],
            [
                {
                    "repo": "onesyue/yuelink",
                    "ref": exact_ref,
                    "validation": "yuelink",
                }
            ],
        )

    def test_all_plan_validates_yuelink_without_building_it(self) -> None:
        result = subprocess.run(
            ["bash", str(TARGET_PLANNER), "all"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        plan = json.loads(result.stdout)
        self.assertTrue(plan["has_builds"])
        self.assertEqual(
            {entry["service"] for entry in plan["matrix"]},
            {"yue-node", "yueops-web", "checkin-api", "yue-bot", "yueboard"},
        )
        self.assertNotIn("yuelink", {entry["service"] for entry in plan["matrix"]})
        self.assertEqual(
            {entry["validation"] for entry in plan["validation_matrix"]},
            {"yue-node", "yueops", "yueboard", "yuelink"},
        )

    def test_target_planner_fails_closed_for_unknown_target(self) -> None:
        result = subprocess.run(
            ["bash", str(TARGET_PLANNER), "not-a-product"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("unknown build service or validation target", result.stderr)

    def test_validation_only_registry_is_closed(self) -> None:
        expected_keys = {"service", "group", "repo", "ref", "validation"}
        names = set()
        for target in self.validation_targets:
            self.assertEqual(set(target), expected_keys)
            self.assertRegex(target["repo"], r"^onesyue/[A-Za-z0-9._-]+$")
            self.assertIn(target["ref"], {"main", "master"})
            self.assertNotIn(target["service"], names)
            names.add(target["service"])
        self.assertEqual(names, {"yuelink"})

    def test_native_validator_rejects_stale_pinned_yueboard_floor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            yueops = temp / "yueops"
            yueboard = temp / "yueboard"
            yueops.mkdir()
            yueboard.mkdir()
            (yueboard / "schema-floor.txt").write_text("42\n", encoding="utf-8")
            result = subprocess.run(
                [
                    "python3",
                    str(NATIVE_VALIDATOR),
                    "--kind",
                    "yueops",
                    "--source",
                    str(yueops),
                    "--yueboard-contract-source",
                    str(yueboard),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "pinned YueBoard contract schema floor does not match central policy",
            result.stderr,
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
