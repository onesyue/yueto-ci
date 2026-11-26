"""Central credential and dependency-install policy.

Private source reads use ``secrets.YUETO_CI_PAT``. Workflows must not mint a
GitHub App installation token or reference ``YUETO_CI_APP_*``. GHCR login and
package API reads use the job ``GITHUB_TOKEN``. The job ``permissions`` block
is that scope.

Dependency lifecycle scripts never run in a credential-holding job:
every ``npm ci`` and ``pnpm install`` carries ``--ignore-scripts``.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
FORBIDDEN_APP = ("create-github-app-token", "YUETO_CI_APP_")


def _code(text: str) -> str:
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


def _workflows() -> dict[str, str]:
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(WORKFLOW_DIR.glob("*.y*ml"))
    }


class CredentialSwitchPolicyTest(unittest.TestCase):
    def test_workflows_forbid_github_app_credentials(self) -> None:
        workflows = _workflows()
        self.assertGreaterEqual(len(workflows), 8)
        for name, text in workflows.items():
            with self.subTest(workflow=name):
                for needle in FORBIDDEN_APP:
                    self.assertNotIn(needle, text)

    def test_private_source_reads_use_the_personal_access_token(self) -> None:
        workflows = _workflows()
        for name in (
            "alert-chain-deadman.yml",
            "board-visual-capture.yml",
            "build.yml",
            "client-core-matrix.yml",
            "hy2-probe.yml",
            "policy-ci.yml",
            "weekly-vuln-sbom.yml",
            "yueops-master-validate.yml",
        ):
            with self.subTest(workflow=name):
                self.assertIn("secrets.YUETO_CI_PAT", workflows[name])
        # GHCR jobs stay on the job token, not the PAT.
        self.assertNotIn("YUETO_CI_PAT", workflows["image-rescan.yml"])

    def test_retired_ghcr_pat_switch_stays_gone(self) -> None:
        for name, text in _workflows().items():
            with self.subTest(workflow=name):
                self.assertNotIn("YUETO_CI_GHCR_VIA_GITHUB_TOKEN", text)

    def test_promotion_uses_the_pat_for_the_head_recheck(self) -> None:
        workflow = (WORKFLOW_DIR / "build.yml").read_text(encoding="utf-8")
        promote = workflow.index(
            "- name: Authorize and promote verified default-branch digest"
        )
        self.assertLess(workflow.index("- name: Build & push"), promote)
        self.assertNotIn("Mint read-only promotion token", workflow)
        self.assertIn(
            "GH_API_TOKEN: ${{ secrets.YUETO_CI_PAT }}",
            workflow[promote : promote + 800],
        )

    def test_registry_calls_use_the_job_github_token(self) -> None:
        workflows = _workflows()
        build = workflows["build.yml"]
        # Toolchain image and own-package logins keep the job token; service
        # packages owned by other repositories are covered by
        # test_service_package_access_falls_back_to_the_source_pat.
        self.assertIn("username: ${{ github.actor }}", build)
        self.assertIn("password: ${{ github.token }}", build)
        rescan = workflows["image-rescan.yml"]
        self.assertIn("GH_API_TOKEN: ${{ github.token }}", rescan)
        self.assertIn("username: ${{ github.actor }}", rescan)
        self.assertIn("password: ${{ github.token }}", rescan)
        capture = workflows["board-visual-capture.yml"]
        self.assertIn("GHCR_USER: ${{ github.actor }}", capture)
        self.assertIn("GHCR_PASSWORD: ${{ github.token }}", capture)

    def test_service_package_access_falls_back_to_the_source_pat(self) -> None:
        # yueboard / yue-node packages refuse this repository's GITHUB_TOKEN
        # (403 push in 45836692565). Plan read, build push, publish, release-pr
        # and resume readback use the PAT unless the switch is set.
        build = _workflows()["build.yml"]
        gated_user = "${{ vars.YUETO_CI_GHCR_VIA_GITHUB_TOKEN == 'true' && github.actor || 'onesyue' }}"
        gated_pass = "${{ vars.YUETO_CI_GHCR_VIA_GITHUB_TOKEN == 'true' && github.token || secrets.YUETO_CI_PAT }}"
        plan = build[build.index("      - id: plan\n"):]
        plan = plan[: plan.index("        run: |")]
        self.assertIn("GHCR_USER: " + gated_user, plan)
        self.assertIn("GHCR_PASSWORD: " + gated_pass, plan)
        self.assertEqual(build.count("username: " + gated_user), 3)
        self.assertEqual(build.count("password: " + gated_pass), 3)
        self.assertEqual(build.count("GHCR_PASSWORD: " + gated_pass), 2)

    def test_ghcr_consumers_declare_the_package_scope_they_need(self) -> None:
        build = (WORKFLOW_DIR / "build.yml").read_text(encoding="utf-8")
        build_job = build[build.index("\n  build:\n") :]
        self.assertIn("      packages: write\n", build_job)
        for name in ("image-rescan.yml", "yueops-master-validate.yml"):
            text = (WORKFLOW_DIR / name).read_text(encoding="utf-8")
            with self.subTest(workflow=name):
                top = text.split("\npermissions:\n", 1)[1].split("\n\n", 1)[0]
                self.assertIn("packages: read", top)
                self.assertNotIn("packages: write", top)
                self.assertNotIn("contents: write", top)

    def test_readme_documents_pat_and_forbids_app_credentials(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("`YUETO_CI_PAT`", readme)
        self.assertIn("GITHUB_TOKEN", readme)
        for forbidden in (
            "YUETO_CI_APP_CLIENT_ID",
            "YUETO_CI_APP_PRIVATE_KEY",
            "create-github-app-token",
            "Delete the retired Actions secret after one green week",
        ):
            with self.subTest(anchor=forbidden):
                self.assertNotIn(forbidden, readme)


class DependencyLifecycleScriptPolicyTest(unittest.TestCase):
    INSTALL = re.compile(r"\b(?:npm(?: --prefix \S+)? ci|pnpm(?: --dir \S+)? install)\b[^\n]*")

    def test_every_locked_install_skips_lifecycle_scripts(self) -> None:
        found = []
        sources = _workflows() | {"board-validation.sh": (ROOT / "scripts/board-validation.sh").read_text()}
        self.assertIn('board-validation-output.py', sources['build.yml'])
        for name, text in sources.items():
            for match in self.INSTALL.finditer(_code(text)):
                command = match.group(0)
                found.append((name, command))
                with self.subTest(workflow=name, command=command):
                    self.assertIn("--ignore-scripts", command)
        ignored = [item for item in found if "--ignore-scripts" in item[1]]
        # One workspace install in board-validation.sh and one in board-visual-capture.yml.
        self.assertEqual(len(ignored), len(found))
        self.assertGreaterEqual(len(found), 2)
        self.assertIn(
            "pnpm install --frozen-lockfile --ignore-scripts",
            sources["board-validation.sh"],
        )

    def test_yueboard_npm_audit_gates_are_source_owned_and_fail_closed(self) -> None:
        workflow = (WORKFLOW_DIR / "build.yml").read_text(encoding="utf-8")
        freshness = workflow.split('\n  freshness:\n', 1)[1]
        self.assertIn('bash .ci-policy/scripts/board-frontend-audit.sh', freshness)
        step = (ROOT / 'scripts/board-frontend-audit.sh').read_text()
        self.assertIn('audit_gate="scripts/ci/pnpm-audit-gate.mjs"', step)
        guard = step.index('[ -f "$audit_gate" ] || {')
        call = step.index('node "$audit_gate" web web-admin')
        # `set -e`-free steps would let exit 2 (gate broken) through; the
        # call must be a bare command so any non-zero code fails the step.
        self.assertNotRegex(step[call:], r'node "\$audit_gate" web web-admin\s*(\|\||;\s*true)')
        self.assertIn("exit 1", step[guard:call])
        self.assertIn('node "$audit_gate" test/a11y test/e2e', step)
        self.assertNotIn("GHSA-", step)


if __name__ == "__main__":
    unittest.main()
