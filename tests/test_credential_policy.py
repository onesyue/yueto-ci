"""Central credential and dependency-install policy.

Private source reads use a GitHub App installation token minted in the job.
Source tokens name their repositories and carry ``contents: read`` only.
The release-pr job is the exception: its token names yueto and can write
contents and pull requests. GHCR cannot accept an installation token, so
registry login and package API reads use the job ``GITHUB_TOKEN``. The job
``permissions`` block is that scope.

Dependency lifecycle scripts never run in a credential-holding job:
every ``npm ci`` and ``pnpm install`` carries ``--ignore-scripts``.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
APP_ACTION = (
    "actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1"
)
SOURCE_REPOS = {"yueboard", "yue-node", "yueops", "quic-go"}
WEEKLY_SOURCE_REPOS = {"yueops", "yueboard", "yue-node", "yueto", "yuelink"}


def _code(text: str) -> str:
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


def _workflows() -> dict[str, str]:
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(WORKFLOW_DIR.glob("*.y*ml"))
    }


def _mint_steps(text: str) -> list[str]:
    """Return every create-github-app-token step body (up to the next step)."""

    steps = re.split(r"(?m)^\s+- (?=name:|uses:|id:)", text)
    return [step for step in steps if "create-github-app-token@" in step]


def _jobs(text: str) -> dict[str, str]:
    parts = re.split(r"(?m)^  ([A-Za-z0-9_-]+):\s*$", text.split("\njobs:\n", 1)[1])
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


class CredentialSwitchPolicyTest(unittest.TestCase):
    def test_workflows_do_not_reference_the_personal_access_token(self) -> None:
        for name, text in _workflows().items():
            with self.subTest(workflow=name):
                self.assertNotIn("YUETO_CI_PAT", text)
                self.assertNotIn("YUETO_CI_GHCR_VIA_GITHUB_TOKEN", text)

    def test_every_app_token_is_pinned_and_least_privilege(self) -> None:
        steps = [
            (name, job, step)
            for name, text in _workflows().items()
            for job, body in _jobs(text).items()
            for step in _mint_steps(body)
        ]
        self.assertGreaterEqual(len(steps), 5)
        for name, job, step in steps:
            with self.subTest(workflow=name, step=step.splitlines()[0]):
                self.assertIn(APP_ACTION, step)
                self.assertNotIn("vars.YUETO_CI_APP_CLIENT_ID != ''", step)
                self.assertIn("client-id: ${{ vars.YUETO_CI_APP_CLIENT_ID }}", step)
                self.assertIn(
                    "private-key: ${{ secrets.YUETO_CI_APP_PRIVATE_KEY }}", step
                )
                self.assertIn("owner: onesyue", step)
                repos = re.search(r"repositories: ([A-Za-z0-9_.,-]+)", step)
                self.assertIsNotNone(repos, "token must name its repositories")
                assert repos is not None
                if name == "weekly-vuln-sbom.yml":
                    allowed = WEEKLY_SOURCE_REPOS
                elif name == "hy2-probe.yml" and job == "build":
                    allowed = {"hysteria", "quic-go"}
                    self.assertEqual(set(repos.group(1).split(",")), allowed)
                elif name == "client-core-matrix.yml":
                    allowed = {"yue-node", "mihomo"}
                    self.assertEqual(set(repos.group(1).split(",")), allowed)
                elif name == "build.yml" and job == "release-pr":
                    self.assertEqual(set(repos.group(1).split(",")), {"yueto"})
                    permissions = re.findall(r"permission-([a-z-]+): (\w+)", step)
                    self.assertEqual(len(permissions), 2, permissions)
                    self.assertEqual(
                        set(permissions),
                        {("contents", "write"), ("pull-requests", "write")},
                    )
                    continue
                else:
                    allowed = SOURCE_REPOS | (
                        {"yueto"} if name == "build.yml" and job == "validate" else set()
                    )
                self.assertLessEqual(set(repos.group(1).split(",")), allowed)
                permissions = re.findall(r"permission-([a-z-]+): (\w+)", step)
                self.assertEqual(len(permissions), 1, permissions)
                self.assertEqual(permissions[0], ("contents", "read"))

    def test_promotion_mints_a_fresh_token_right_before_the_head_recheck(self) -> None:
        workflow = (WORKFLOW_DIR / "build.yml").read_text(encoding="utf-8")
        mint = workflow.index("- name: Mint read-only promotion token (GitHub App)")
        promote = workflow.index(
            "- name: Authorize and promote verified default-branch digest"
        )
        self.assertLess(workflow.index("- name: Build & push"), mint)
        self.assertLess(mint, promote)
        self.assertIn(
            "GH_API_TOKEN: ${{ steps.promote_token.outputs.token }}",
            workflow[promote:],
        )

    def test_registry_calls_use_the_job_github_token(self) -> None:
        workflows = _workflows()
        build = workflows["build.yml"]
        self.assertIn("GHCR_USER: ${{ github.actor }}", build)
        self.assertIn("GHCR_PASSWORD: ${{ github.token }}", build)
        self.assertIn("username: ${{ github.actor }}", build)
        self.assertIn("password: ${{ github.token }}", build)
        rescan = workflows["image-rescan.yml"]
        self.assertIn("GH_API_TOKEN: ${{ github.token }}", rescan)
        self.assertIn("username: ${{ github.actor }}", rescan)
        self.assertIn("password: ${{ github.token }}", rescan)
        capture = workflows["board-visual-capture.yml"]
        self.assertIn("GHCR_USER: ${{ github.actor }}", capture)
        self.assertIn("GHCR_PASSWORD: ${{ github.token }}", capture)

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

    def test_readme_documents_the_cut_over(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for anchor in (
            "YUETO_CI_APP_CLIENT_ID",
            "YUETO_CI_APP_PRIVATE_KEY",
            "Manage Actions access",
            "Delete the retired Actions secret after one green week",
        ):
            with self.subTest(anchor=anchor):
                self.assertIn(anchor, readme)


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
