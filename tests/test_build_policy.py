from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"
POLICY_WORKFLOW = ROOT / ".github" / "workflows" / "policy-ci.yml"
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
        cls.policy_workflow = POLICY_WORKFLOW.read_text(encoding="utf-8")
        cls.services = json.loads(SERVICES.read_text(encoding="utf-8"))
        cls.validation_targets = json.loads(
            VALIDATION_TARGETS.read_text(encoding="utf-8")
        )
        cls.readme = README.read_text(encoding="utf-8")
        cls.native_contract = json.loads(NATIVE_CONTRACT.read_text(encoding="utf-8"))
        cls.native_validator = NATIVE_VALIDATOR.read_text(encoding="utf-8")
        cls.target_planner = TARGET_PLANNER.read_text(encoding="utf-8")

    def test_all_actions_are_pinned_to_full_commit_sha(self) -> None:
        action_sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(WORKFLOW_DIR.glob("*.y*ml"))
        )
        uses = re.findall(
            r"^\s*(?:-\s*)?uses:\s*([^\s#]+)",
            action_sources + "\n" + self.readme,
            re.MULTILINE,
        )
        self.assertTrue(uses)
        for action in uses:
            with self.subTest(action=action):
                self.assertRegex(action, r"^[^@]+@[0-9a-f]{40}$")

    def test_release_go_toolchain_is_an_exact_security_patch(self) -> None:
        setup = re.search(
            r"(?ms)^      - name: Set up Go\n(?P<body>.*?)(?=^      - name:)",
            self.workflow,
        )
        self.assertIsNotNone(setup)
        assert setup is not None
        body = setup.group("body")
        self.assertIn("go-version: '1.26.7'", body)
        self.assertNotIn("go-version-file:", body)
        self.assertIn(
            "cache: ${{ github.event_name != 'workflow_dispatch' || "
            "github.event.inputs.runner != 'yue-local-release' }}",
            body,
        )

    def test_local_release_never_exports_the_remote_build_cache(self) -> None:
        compute = re.search(
            r"(?ms)^      - name: Compute tags\n(?P<body>.*?)(?=^      - name:)",
            self.workflow,
        )
        build = re.search(
            r"(?ms)^      - name: Build & push\n(?P<body>.*?)(?=^      - )",
            self.workflow,
        )
        self.assertIsNotNone(compute)
        self.assertIsNotNone(build)
        assert compute is not None and build is not None
        self.assertIn(
            "RUNNER_KIND: ${{ github.event.inputs.runner || 'ubuntu-latest' }}",
            compute.group("body"),
        )
        self.assertIn(
            '"$RUNNER_KIND" != "yue-local-release"', compute.group("body")
        )
        self.assertNotIn(
            '"${{ github.event.inputs.runner }}"', compute.group("body")
        )
        self.assertIn(
            'echo "cache_to=type=gha,mode=max,scope=${{ matrix.service }}"',
            compute.group("body"),
        )
        self.assertIn(
            "cache-to: ${{ steps.meta.outputs.cache_to }}",
            build.group("body"),
        )
        self.assertNotIn("cache-to: type=gha", build.group("body"))

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
            "fromJSON(github.event_name == 'workflow_dispatch' && "
            "github.event.inputs.runner == 'yue-local-release' && "
            "'[\"self-hosted\",\"Linux\",\"X64\",\"yue-local-release\"]' || "
            "'[\"ubuntu-latest\"]')"
        )
        self.assertEqual(self.workflow.count(selector), 3)
        self.assertIn(
            "`self-hosted`、`Linux`、`X64` 标签并添加唯一自定义\n"
            "  标签 `yue-local-release`",
            self.readme,
        )
        self.assertIn("本仓保持 public 时不得注册常驻 self-hosted runner", self.readme)
        self.assertIn("`--ephemeral --disableupdate` runner", self.readme)
        self.assertIn("'127.0.0.1:55434:5432' || '5432:5432'", self.workflow)
        self.assertEqual(self.workflow.count("127.0.0.1:55434"), 3)

    def test_source_poller_is_unconditional(self) -> None:
        """poller 不许有路径过滤——「每个提交都被中央验证」靠的就是这一点。

        它接替的是三个源仓里那个 `trigger-build.yml`，那个是**按路径过滤**的
        （只有碰了 `scripts/**` / `services/**` 之类才派发）。而且它 428 次运行
        零成功，从来没派发过。改成拉取式之后判据是「HEAD 变没变」，与改了哪些
        文件无关，所以「policy-only 的改动继承了一份早先验过的镜像」这种形态
        结构上不可能再发生——前提是这里永远不要给它加回路径过滤。

        yueops 侧原本断言那份路径过滤的测试
        （test_npm_audit_waiver_scope_20260730）已指向这一条。
        """
        poll = (WORKFLOW_DIR / "poll-sources.yml").read_text(encoding="utf-8")
        trigger = poll.split("jobs:", 1)[0]
        self.assertIn("schedule:", trigger)
        self.assertIn("workflow_dispatch:", trigger)
        self.assertNotIn("paths:", trigger)
        self.assertNotIn("paths-ignore:", trigger)
        # 拉取式的判据只能是 HEAD 与产物，不能是 push 事件本身。
        self.assertNotIn("on:\n  push:", poll)

    def test_source_poller_probes_every_image_in_a_group(self) -> None:
        """「已构建」必须以 group 内每个镜像都有 built- 标签为准。

        只探「代表镜像」时，一次部分失败的构建（代表推上去了、其余没有）会让
        缺的镜像永远不被补——下一轮 poll 看到代表标签即跳过，且无任何重试。
        同时组表必须从 services.json 派生而不是手写：手写表时代的注释声称有
        测试钉住对应关系，那条测试从未存在过，这条就是补上的那条。
        """
        poll = (WORKFLOW_DIR / "poll-sources.yml").read_text(encoding="utf-8")
        poll_code = "\n".join(
            line for line in poll.splitlines() if not line.lstrip().startswith("#")
        )
        # 组表从 services.json 派生（group_by 才能把一仓多镜像折成一组）。
        self.assertIn("services.json", poll_code)
        self.assertIn("group_by(.group)", poll_code)
        # 探测的是全部 probes，不是单个代表。
        self.assertIn("probes: map(.service)", poll_code)
        self.assertIn('jq -r \'.probes[]\'', poll_code)
        # 手写代表镜像的形态不许回来。
        self.assertNotIn('"probe":', poll_code)

    def test_built_markers_use_exact_source_identity_and_registry_errors_fail_closed(
        self,
    ) -> None:
        poll = (WORKFLOW_DIR / "poll-sources.yml").read_text(encoding="utf-8")
        poll_code = "\n".join(
            line for line in poll.splitlines() if not line.lstrip().startswith("#")
        )
        self.assertIn('marker_ref="${image}:built-${sha}"', poll_code)
        self.assertIn('legacy_ref="${image}:built-${short}"', poll_code)
        self.assertIn('if [ "$legacy_rev" = "$sha" ]', poll_code)
        self.assertIn('"org.opencontainers.image.revision"', poll_code)
        self.assertNotIn("no such manifest|denied", poll_code)

        marker_start = self.workflow.index("- name: Mark this source revision as built")
        promotion_start = self.workflow.index(
            "- name: Authorize and promote verified default-branch digest"
        )
        marker_step = self.workflow[marker_start:promotion_start]
        self.assertIn("SOURCE_SHA: ${{ steps.meta.outputs.source_sha }}", marker_step)
        self.assertIn('built-${SOURCE_SHA}', marker_step)
        self.assertNotIn("SHA_SHORT", marker_step)

    def assert_promotion_uses_current_verified_digest(self, step: str) -> None:
        final_create = step[step.rindex("docker buildx imagetools create") :]
        self.assertNotIn("promotion_digest", step)
        self.assertIn(
            'promotion_tag_args=(--tag "${IMAGE}:latest")',
            step,
        )
        self.assertIn(
            'promotion_tag_args=(\n'
            '              --tag "${IMAGE}:${SHA_TAG}"\n'
            '              --tag "${IMAGE}:latest"',
            step,
        )
        self.assertIn('"${promotion_tag_args[@]}"', final_create)
        self.assertIn('"${IMAGE}@${DIGEST}"', final_create)
        self.assertNotIn('"${IMAGE}@${existing}"', final_create)
        self.assertNotIn('--tag "${IMAGE}:${SHA_TAG}"', final_create)

    def test_promotion_preserves_sha_tag_and_uses_current_verified_digest(self) -> None:
        start = self.workflow.index(
            "- name: Authorize and promote verified default-branch digest"
        )
        step = self.workflow[start:]
        self.assertIn("SHA_TAG: sha-${{ steps.meta.outputs.source_sha }}", step)
        self.assertIn("build did not return a valid immutable digest", step)
        self.assertIn("could not determine immutable tag state", step)
        self.assertIn("invalid manifest digest", step)
        self.assertIn('sha_tag_error="$(mktemp "${RUNNER_TEMP}/', step)
        self.assertIn("denied|unauthorized|forbidden|authentication", step)
        self.assertIn("cosign verify \\", step)
        self.assertIn("cosign verify-attestation \\", step)
        self.assertIn("保留 immutable tag", step)
        self.assert_promotion_uses_current_verified_digest(step)
        for gate in (
            "- name: Build & push",
            "- name: Block fixed HIGH/CRITICAL vulnerabilities (linux/amd64)",
            "- name: Validate complete platform SBOM set",
            "- name: Sign & attest image (Sigstore keyless)",
            "- name: Generate signed GitHub build provenance",
        ):
            with self.subTest(gate=gate):
                self.assertLess(self.workflow.index(gate), start)
        same_source = step[
            step.index('if [ -n "$existing_rev" ]') : step.index(
                "# Narrow the unavoidable network check/use interval"
            )
        ]
        self.assertNotIn("exit 0", same_source)

    def test_policy_rejects_old_digest_promotion_mutation(self) -> None:
        start = self.workflow.index(
            "- name: Authorize and promote verified default-branch digest"
        )
        step = self.workflow[start:]
        mutated = step.replace(
            '"${IMAGE}@${DIGEST}"',
            '"${IMAGE}@${existing}"',
            1,
        )
        self.assertNotEqual(mutated, step)
        with self.assertRaises(AssertionError):
            self.assert_promotion_uses_current_verified_digest(mutated)

    def test_build_job_permissions_are_minimal_and_explicit(self) -> None:
        build_start = self.workflow.index("  build:\n")
        strategy_start = self.workflow.index("    strategy:\n", build_start)
        build_header = self.workflow[build_start:strategy_start]
        permission_lines = re.findall(
            r"(?m)^      ([a-z-]+): (read|write)$",
            build_header,
        )
        self.assertEqual(
            permission_lines,
            [
                ("contents", "read"),
                ("packages", "write"),
                ("id-token", "write"),
                ("attestations", "write"),
            ],
        )

    def assert_sbom_gate_binds_distinct_architectures(self, workflow: str) -> None:
        verifier = (ROOT / "scripts/verify-sbom-attestations.py").read_text(
            encoding="utf-8"
        )
        self.assertEqual(workflow.count("EXPECTED_ARCHITECTURES:"), 3)
        self.assertEqual(
            workflow.count(".ci-policy/scripts/verify-sbom-attestations.py"), 2
        )
        self.assertIn('== [$arch]', workflow)
        self.assertIn(
            'prop.get("name") == "syft:metadata:architecture"', verifier
        )
        self.assertIn('subject[0] != {"name": image', verifier)
        self.assertIn("--digest \"$DIGEST\"", workflow)
        self.assertIn("--digest \"$existing\"", workflow)
        self.assertNotIn("EXPECTED_SBOMS", workflow)
        self.assertNotIn('length >= ${EXPECTED_SBOMS}', workflow)

    def test_sbom_gate_binds_distinct_platforms_and_subject_digest(self) -> None:
        self.assert_sbom_gate_binds_distinct_architectures(self.workflow)

    def test_sbom_count_only_regression_is_rejected(self) -> None:
        mutated = self.workflow.replace(
            "python3 .ci-policy/scripts/verify-sbom-attestations.py",
            'jq -s -e "length >= 2"',
            1,
        )
        self.assertNotEqual(mutated, self.workflow)
        with self.assertRaises(AssertionError):
            self.assert_sbom_gate_binds_distinct_architectures(mutated)

    def test_only_build_yml_can_build_or_promote_products(self) -> None:
        workflow_files = sorted(path.name for path in WORKFLOW_DIR.glob("*.y*ml"))
        self.assertEqual(
            workflow_files,
            [
                "alert-chain-deadman.yml",
                "build.yml",
                "policy-ci.yml",
                "poll-sources.yml",
            ],
        )

        # poll-sources.yml 只允许**请求**构建，永远不许自己构建或 promote。
        # 它是定时跑的、无人看着的，所以「它只能做安全的那半」必须由门禁钉住，
        # 而不是靠写它的人当时的自觉。
        poll = (WORKFLOW_DIR / "poll-sources.yml").read_text(encoding="utf-8")
        # 「不许做」的几条只能看**可执行内容**：注释里解释「为什么这里不签名」
        # 本身是有价值的，不该被自己的门禁判违规。
        poll_code = "\n".join(
            line for line in poll.splitlines() if not line.lstrip().startswith("#")
        )
        self.assertIn("-f promote=false", poll_code)
        self.assertNotIn("promote=true", poll_code)
        self.assertNotIn("build-push-action", poll_code)
        self.assertNotIn("imagetools create", poll_code)
        self.assertNotIn("cosign", poll_code)
        self.assertIn("permissions:\n  contents: read", poll)
        # 漏跑一轮只是晚 20 分钟；两轮叠在一起会对同一个 commit 派两次构建。
        self.assertIn("concurrency:", poll)

        # The public dead-man receiver is operational control, never another
        # unattended product delivery path.
        deadman = (WORKFLOW_DIR / "alert-chain-deadman.yml").read_text(
            encoding="utf-8"
        )
        deadman_code = "\n".join(
            line
            for line in deadman.splitlines()
            if not line.lstrip().startswith("#")
        )
        self.assertNotIn("build-push-action", deadman_code)
        self.assertNotIn("imagetools create", deadman_code)
        self.assertNotIn("cosign", deadman_code)
        self.assertNotIn("promote=true", deadman_code)
        self.assertIn("permissions:\n  contents: read", deadman)

        self.assertIn(
            "Authorize and promote verified default-branch digest",
            self.workflow,
        )
        self.assertNotIn("promote.yml", self.readme)

        self.assertIn("push:", self.policy_workflow)
        self.assertIn("pull_request:", self.policy_workflow)
        self.assertIn("permissions:\n  contents: read", self.policy_workflow)
        policy_lower = self.policy_workflow.casefold()
        for forbidden in (
            "repository_dispatch",
            "workflow_dispatch",
            "packages: write",
            "id-token: write",
            "actions: write",
            "docker",
            "cosign",
            "promote",
            "repository-dispatch",
            "secrets.",
            "ghcr.io",
            "buildx",
            "trivy",
            "push-to-registry",
            "client-payload",
            "event-type",
            "actionlint_flags",
            "-ignore",
            "shellcheck_opts",
            "sc2129",
            "sc2086",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, policy_lower)
        self.assertNotRegex(
            self.policy_workflow,
            r"(?m)^\s+[A-Za-z-]+:\s*write\s*$",
        )

    def test_policy_ci_runs_pinned_fail_closed_policy_tooling(self) -> None:
        required = (
            "python3 tests/test_build_policy.py -v",
            "python3 -m compileall -q scripts tests",
            'bash -n "$script"',
            "actionlint .github/workflows/*.yml",
            "ACTIONLINT_VERSION: '1.7.12'",
            "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8",
            "sha256sum --check --strict",
            "https://github.com/rhysd/actionlint/releases/download/",
            "--proto '=https' --tlsv1.2",
            "persist-credentials: false",
        )
        for invariant in required:
            with self.subTest(invariant=invariant):
                self.assertIn(invariant, self.policy_workflow)
        uses = re.findall(
            r"^\s*(?:-\s*)?uses:\s*([^\s#]+)",
            self.policy_workflow,
            re.MULTILINE,
        )
        self.assertEqual(
            uses,
            [
                "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803",
                "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1",
            ],
        )
        for action in uses:
            with self.subTest(action=action):
                self.assertRegex(action, r"^[^@]+@[0-9a-f]{40}$")

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
            "for tool in bash curl docker envsubst git jq",
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
        self.assertIn(
            'requirements_file="${RUNNER_TEMP}/ci-requirements.txt"',
            self.workflow,
        )
        self.assertNotIn("/tmp/ci-requirements.txt", self.workflow)
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

    def test_privileged_builder_images_are_immutable(self) -> None:
        qemu_image = (
            "docker.io/tonistiigi/binfmt:latest@sha256:"
            "400a4873b838d1b89194d982c45e5fb3cda4593fbfd7e08a02e76b03b21166f0"
        )
        buildkit_image = (
            "moby/buildkit:buildx-stable-1@sha256:"
            "2f5adac4ecd194d9f8c10b7b5d7bceb5186853db1b26e5abd3a657af0b7e26ec"
        )
        self.assertIn(f"image: {qemu_image}", self.workflow)
        self.assertIn(f"driver-opts: image={buildkit_image}", self.workflow)
        self.assertNotRegex(
            self.workflow,
            r"(?m)^\s+image:\s+(?:docker\.io/)?tonistiigi/binfmt:[^@\s]+\s*$",
        )
        self.assertNotRegex(
            self.workflow,
            r"(?m)^\s+driver-opts:\s+image=moby/buildkit:[^@\s]+\s*$",
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
            "scripts/npm-audit-gate.py",
            'corepack install --global "$web_pm"',
            '[ "$web_pm" = "$admin_pm" ]',
            "squawk/releases/download/v2.60.0/squawk-linux-x64",
            "708d77899e2b43e0d21cb811023dbbcfb3b8220b0c0b7e71c6e73568be7716e5",
            'test "$("$squawk_bin" --version)" = \'squawk 2.60.0\'',
            "aquasecurity/trivy-action@",
            "sigstore/cosign-installer@",
            # >= v3.1.3: GHSA-fx35-mq7g-6g98 (2026-08-06, High 7.4) — a legacy
            # JSON bundle with a bare public key in `cert` made verify-blob*
            # skip CheckCertificatePolicy and print "Verified OK" while
            # ignoring --certificate-identity. Image verify/verify-attestation
            # (what this pipeline uses) are unaffected; pinned forward anyway
            # because the whole chain rests on cosign really checking identity.
            "cosign-release: v3.1.3",
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
        self.assertNotIn("npm install --global squawk", self.workflow)

    def test_yueops_reports_are_unique_runner_temp_files(self) -> None:
        backend_start = self.workflow.index("- name: Validate yueops backend")
        frontend_start = self.workflow.index("- name: Validate yueops frontend")
        backend_step = self.workflow[backend_start:frontend_start]

        self.assertIn(
            'security_report=$(mktemp "${RUNNER_TEMP:?}/security-scan.',
            backend_step,
        )
        self.assertIn(
            'python_lock_audit=$(mktemp "${RUNNER_TEMP:?}/python-lock-audit.',
            backend_step,
        )
        self.assertIn("trap cleanup_reports EXIT", backend_step)
        self.assertNotIn("/tmp/security-scan.json", backend_step)
        self.assertNotIn("/tmp/python-lock-audit.txt", backend_step)

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
        install_start = self.workflow.index("- name: Install yueops dependencies")
        backend_start = self.workflow.index("- name: Validate yueops backend")
        miniapp_start = self.workflow.index("- name: Validate Yue mini app")
        migration_start = self.workflow.index(
            "- name: Lint changed YueOps SQL migrations"
        )
        install_step = self.workflow[install_start:backend_start]
        miniapp_step = self.workflow[miniapp_start:migration_start]

        locked_install = "npm --prefix telegram-bot/yue/miniapp ci"
        self.assertIn(locked_install, install_step)
        self.assertLess(
            self.workflow.index(locked_install),
            self.workflow.index(".venv/bin/python -m pytest -q"),
        )
        self.assertIn("working-directory: telegram-bot/yue/miniapp", miniapp_step)
        self.assertIn("npm run lint", miniapp_step)
        self.assertIn("npm run build", miniapp_step)
        self.assertLess(
            miniapp_step.index("npm run lint"), miniapp_step.index("npm run build")
        )

    def test_yueops_tests_do_not_override_the_isolated_database_fixture(self) -> None:
        self.assertNotIn("DATABASE_URL: ''", self.workflow)

    def test_yue_node_and_yueops_use_a_pinned_yueboard_contract(self) -> None:
        self.assertIn(
            "Checkout pinned YueBoard canonical contract",
            self.workflow,
        )
        checkout_start = self.workflow.index(
            "- name: Checkout pinned YueBoard canonical contract"
        )
        checkout_end = self.workflow.index(
            "- name: Checkout immutable central native-node policy"
        )
        checkout_step = self.workflow[checkout_start:checkout_end]
        self.assertIn(
            "if: matrix.validation == 'yue-node' || matrix.validation == 'yueops'",
            checkout_step,
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
            'echo "yueboard_contract_ref=$yueboard_contract_ref"',
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
        validation_start = self.workflow.index(
            "- name: Validate native-node cross-repository contract"
        )
        self.assertLess(checkout_start, validation_start)
        validation_step = self.workflow[
            validation_start : self.workflow.index(
                "- name: Validate yue-node", validation_start
            )
        ]
        self.assertIn("matrix.validation == 'yue-node'", validation_step)
        self.assertIn("matrix.validation == 'yueops'", validation_step)
        self.assertIn("validate_canonical_proto_mirror", self.native_validator)
        self.assertIn(
            "yue-node validation requires the separately checked-out",
            self.native_validator,
        )
        self.assertIn(
            "pinned YueBoard contract schema floor does not match central policy",
            self.native_validator,
        )
        self.assertIn(
            'for source_dir in (root / "cmd", root / "internal")',
            self.native_validator,
        )
        self.assertNotIn(
            'for path in root.rglob("*.go")',
            self.native_validator,
        )

    def test_native_node_contract_is_central_and_blocks_all_product_repositories(
        self,
    ) -> None:
        self.assertEqual(self.native_contract["version"], 6)
        # 58 is the binary-required floor: the pinned YueBoard tree's irreversible
        # hot-path-index and runtime-role migration. The floor-57 authority
        # retirement ceremony has also landed, so neither the old decoupled-at-55
        # value nor the superseded floor 57 is deployable. Keep the
        # central policy, pinned YueBoard tree and YueOps MIN_SCHEMA_FLOOR on
        # this exact reviewed value; the cross-repository validator checks the
        # latter two as well.
        self.assertIsInstance(self.native_contract["schema_floor"], int)
        self.assertEqual(self.native_contract["schema_floor"], 70)
        self.assertEqual(
            self.native_contract["yueboard_contract_pin"],
            "013fdd2bef77cf998306fb9cdc41585c688fc66d",
        )
        self.assertEqual(
            self.native_contract["presence"],
            {
                "required_capabilities": [
                    "presence_v2",
                ],
                "release_a_rollout_capabilities": [
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
                "count_basis": "client_declared_hwid_or_network_projection",
                "count_equation": "max_online_identities_and_network_lines",
                "legacy_shared_online_max": 1,
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
                "account_subscription_api": "/api/v1/user/getSubscribe",
                "account_subscription_prefix": "/s/",
                "third_party_import": "account_subscription",
                "portal_installation_authority": "retired",
                "synthetic_install_identity": "retired",
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

    def test_floor57_portal_installation_retirement_is_pinned_fail_closed(self) -> None:
        for required in (
            "internal/modules/subscribe/install_beacon_inject.go",
            "internal/modules/subscribe/presence_beacon.go",
            "00056_drop_portal_handoff_enrollment_receipts.sql",
            "00057_drop_retired_device_subscription_authorities.sql",
            "current_setting('yueboard.retirement_nonce', true), 57, false",
            "current_setting('yueboard.retirement_nonce', true), 57, true",
            '"/d/{authority}"',
            "RecordInstallBeacon",
            "MintInstallToken",
            "install_token",
            "TestRuntimeHasNoSyntheticInstallOrPerDeviceAuthoritySurface",
            "web/src/lib/subscription-client.ts",
            "the portal does not recommend clients without a proven managed profile",
            '"shadowrocket"',
            '"小火箭"',
        ):
            with self.subTest(required=required):
                self.assertIn(required, self.native_validator)

        self.assertNotIn("web/src/lib/device-subscription.ts", self.native_validator)
        self.assertIn("forbid_paths(", self.native_validator)
        self.assertIn("forbid_casefold(", self.native_validator)
        self.assertIn('root / "internal/modules"', self.native_validator)
        self.assertIn('root / "web/src"', self.native_validator)

    def test_retired_path_and_client_name_guards_reject_regressions(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "native_node_contract_validator", NATIVE_VALIDATOR
        )
        self.assertIsNotNone(spec)
        assert spec is not None and spec.loader is not None
        validator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(validator)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            retired = root / "internal/modules/subscribe/install_beacon_inject.go"
            retired.parent.mkdir(parents=True)
            retired.write_text("package subscribe\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "retired contract paths"):
                validator.forbid_paths(
                    root,
                    ["internal/modules/subscribe/install_beacon_inject.go"],
                    "test Portal runtime",
                )

        for spelling in ("Shadowrocket", "SHADOWROCKET", "小火箭"):
            with self.subTest(spelling=spelling):
                with self.assertRaisesRegex(RuntimeError, "retired contract fragments"):
                    validator.forbid_casefold(
                        f"recommend {spelling}",
                        ["shadowrocket", "小火箭"],
                        "test client catalogue",
                    )

    def test_yue_node_proto_gate_compares_real_canonical_bytes_and_hashes(
        self,
    ) -> None:
        spec = importlib.util.spec_from_file_location(
            "native_node_proto_validator", NATIVE_VALIDATOR
        )
        self.assertIsNotNone(spec)
        assert spec is not None and spec.loader is not None
        validator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(validator)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            node = temp / "yue-node"
            yueboard = temp / "yueboard"
            node_proto = node / "proto/yuenode/v1/yuenode.proto"
            canonical_proto = yueboard / "proto/yuenode/v1/yuenode.proto"
            digest = node / "proto/CANONICAL.sha256"
            node_proto.parent.mkdir(parents=True)
            canonical_proto.parent.mkdir(parents=True)

            canonical = b'syntax = "proto3";\n// canonical bytes\n'
            canonical_hash = hashlib.sha256(canonical).hexdigest()
            node_proto.write_bytes(canonical)
            canonical_proto.write_bytes(canonical)
            digest.write_text(
                f"{canonical_hash}  yuenode/v1/yuenode.proto\n",
                encoding="utf-8",
            )
            validator.validate_canonical_proto_mirror(node, yueboard)

            # This is the old blind spot: mirror + local digest drift together
            # and remain repository-internally self-consistent. The separately
            # checked-out canonical bytes must still make the central gate red.
            drifted = canonical + b"// independently edited mirror\n"
            node_proto.write_bytes(drifted)
            digest.write_text(
                f"{hashlib.sha256(drifted).hexdigest()}  yuenode/v1/yuenode.proto\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "differs byte-for-byte"):
                validator.validate_canonical_proto_mirror(node, yueboard)

            # Equal bytes with a stale/forged pin are independently rejected;
            # a successful gate proves bytes plus all three SHA-256 values.
            node_proto.write_bytes(canonical)
            digest.write_text(
                f"{'0' * 64}  yuenode/v1/yuenode.proto\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(
                RuntimeError, "does not pin the checked-out canonical bytes"
            ):
                validator.validate_canonical_proto_mirror(node, yueboard)

            missing_canonical = subprocess.run(
                [
                    "python3",
                    str(NATIVE_VALIDATOR),
                    "--kind",
                    "yue-node",
                    "--source",
                    str(node),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(missing_canonical.returncode, 1)
            self.assertIn(
                "requires the separately checked-out YueBoard canonical source",
                missing_canonical.stderr,
            )

    def test_transition_advertisement_and_serving_proof_capabilities_are_distinct(
        self,
    ) -> None:
        transition = 'presence["release_a_rollout_capabilities"]'
        serving = 'presence["required_capabilities"]'
        self.assertEqual(self.native_validator.count(transition), 1)
        self.assertGreaterEqual(self.native_validator.count(serving), 1)
        self.assertIn(
            "post process lacks the exact serving capabilities",
            self.native_validator,
        )
        self.assertNotIn(
            "post process lacks the exact credential capabilities",
            self.native_validator,
        )

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
