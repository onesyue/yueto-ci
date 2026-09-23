"""Central credential and dependency-install policy (2026-09-23, L9).

Two families live here because both are about "what may execute or read while
this public repository's jobs hold private-repository credentials":

1. The classic, all-repo ``YUETO_CI_PAT`` is being replaced without downtime.
   Every use must be a *fallback* behind an explicit switch:
     * source reads   -> a GitHub App installation token minted per job by
       ``actions/create-github-app-token`` when ``vars.YUETO_CI_APP_CLIENT_ID``
       is set, scoped to named repositories and ``contents: read`` only
       (the deadman incident writer is the single ``issues: write`` exception,
       scoped to ``yueops``);
     * GHCR           -> this repository's own ``GITHUB_TOKEN`` when
       ``vars.YUETO_CI_GHCR_VIA_GITHUB_TOKEN == 'true'`` (GitHub Apps cannot
       authenticate to GHCR).
   A bare ``secrets.YUETO_CI_PAT`` anywhere would make deleting the PAT an
   outage, which is exactly what the switch exists to avoid.

2. Dependency lifecycle scripts never run in a credential-holding job:
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
PAT_FALLBACKS = (
    re.compile(
        r"\$\{\{ steps\.[a-z_]+\.outputs\.token \|\| secrets\.YUETO_CI_PAT \}\}"
    ),
    re.compile(
        r"\$\{\{ vars\.YUETO_CI_GHCR_VIA_GITHUB_TOKEN == 'true' && github\.token"
        r" \|\| secrets\.YUETO_CI_PAT \}\}"
    ),
    re.compile(
        r"\$\{\{ vars\.YUETO_CI_APP_CLIENT_ID != '' && github\.token"
        r" \|\| secrets\.YUETO_CI_PAT \}\}"
    ),
)
SOURCE_REPOS = {"yueboard", "yue-node", "yueops", "yuelink", "quic-go"}


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


class CredentialSwitchPolicyTest(unittest.TestCase):
    def test_pat_is_only_ever_a_switch_fallback(self) -> None:
        uses = 0
        for name, text in _workflows().items():
            for line in _code(text).splitlines():
                if "secrets.YUETO_CI_PAT" not in line:
                    continue
                uses += 1
                with self.subTest(workflow=name, line=line.strip()):
                    self.assertTrue(
                        any(pattern.search(line) for pattern in PAT_FALLBACKS),
                        "YUETO_CI_PAT must only appear as the fallback of a switch",
                    )
        # Scan floor: plan, validate x3, build checkout, GHCR, promote,
        # poll x3, rescan, deadman x2.  A refactor that stops finding them
        # must not read as "no bare PAT left".
        self.assertGreaterEqual(uses, 13)

    def test_every_app_token_is_switched_pinned_and_least_privilege(self) -> None:
        steps = [
            (name, step)
            for name, text in _workflows().items()
            for step in _mint_steps(text)
        ]
        self.assertGreaterEqual(len(steps), 7)
        for name, step in steps:
            with self.subTest(workflow=name, step=step.splitlines()[0]):
                self.assertIn(APP_ACTION, step)
                self.assertIn("vars.YUETO_CI_APP_CLIENT_ID != ''", step)
                self.assertIn("client-id: ${{ vars.YUETO_CI_APP_CLIENT_ID }}", step)
                self.assertIn(
                    "private-key: ${{ secrets.YUETO_CI_APP_PRIVATE_KEY }}", step
                )
                self.assertIn("owner: onesyue", step)
                repos = re.search(r"repositories: ([A-Za-z0-9_.,-]+)", step)
                self.assertIsNotNone(repos, "token must name its repositories")
                self.assertLessEqual(set(repos.group(1).split(",")), SOURCE_REPOS)
                permissions = re.findall(r"permission-([a-z-]+): (\w+)", step)
                self.assertEqual(len(permissions), 1, permissions)
                self.assertIn(
                    permissions[0], {("contents", "read"), ("issues", "write")}
                )
                if permissions[0] == ("issues", "write"):
                    self.assertEqual(name, "alert-chain-deadman.yml")
                    self.assertEqual(repos.group(1), "yueops")

    def test_promotion_mints_a_fresh_token_right_before_the_head_recheck(self) -> None:
        workflow = (WORKFLOW_DIR / "build.yml").read_text(encoding="utf-8")
        mint = workflow.index("- name: Mint read-only promotion token (GitHub App)")
        promote = workflow.index(
            "- name: Authorize and promote verified default-branch digest"
        )
        self.assertLess(workflow.index("- name: Build & push"), mint)
        self.assertLess(mint, promote)
        self.assertIn(
            "GH_API_TOKEN: ${{ steps.promote_token.outputs.token || secrets.YUETO_CI_PAT }}",
            workflow[promote:],
        )

    def test_ghcr_consumers_declare_the_package_scope_they_need(self) -> None:
        build = (WORKFLOW_DIR / "build.yml").read_text(encoding="utf-8")
        build_job = build[build.index("\n  build:\n") :]
        self.assertIn("      packages: write\n", build_job)
        for name in ("poll-sources.yml", "image-rescan.yml"):
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
            "YUETO_CI_GHCR_VIA_GITHUB_TOKEN",
            "Manage Actions access",
        ):
            with self.subTest(anchor=anchor):
                self.assertIn(anchor, readme)


class DependencyLifecycleScriptPolicyTest(unittest.TestCase):
    INSTALL = re.compile(r"\b(?:npm(?: --prefix \S+)? ci|pnpm(?: --dir \S+)? install)\b[^\n]*")

    def test_every_locked_install_skips_lifecycle_scripts(self) -> None:
        found = 0
        for name, text in _workflows().items():
            for match in self.INSTALL.finditer(_code(text)):
                found += 1
                with self.subTest(workflow=name, command=match.group(0)):
                    self.assertIn("--ignore-scripts", match.group(0))
        # yueops miniapp + frontend, yueboard web + web-admin.
        self.assertGreaterEqual(found, 4)

    def test_yueboard_npm_audit_gates_are_source_owned_and_fail_closed(self) -> None:
        workflow = (WORKFLOW_DIR / "build.yml").read_text(encoding="utf-8")
        start = workflow.index("- name: Validate yueboard frontends")
        end = workflow.index("- name: Validate YueBoard responsive and design contracts")
        step = workflow[start:end]
        self.assertIn("for app in web web-admin; do", step)
        self.assertIn('audit_gate="$app/scripts/npm-audit-gate.mjs"', step)
        guard = step.index('[ -f "$audit_gate" ] || {')
        call = step.index('(cd "$app" && node scripts/npm-audit-gate.mjs)')
        self.assertIn("exit 1", step[guard:call])
        # The audit must judge the tree that was actually installed and built.
        self.assertLess(step.index("pnpm --dir web-admin build"), guard)
        self.assertNotIn("GHSA-", step)


if __name__ == "__main__":
    unittest.main()
