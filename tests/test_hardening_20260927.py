"""2026-09-27 hardening of the public builder (C1, C2, C3, C5, C6).

Each group below executes the real artifact where it can (the plan step's
shell, the Trivy installer, the rescan planner) and checks the workflow text
only for the structural facts nothing else can observe (which step holds a
secret). Every structural check is paired with a mutation that proves it
would go red.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
BUILD = WORKFLOW_DIR / "build.yml"
RESCAN = WORKFLOW_DIR / "image-rescan.yml"
POLICY_CI = WORKFLOW_DIR / "policy-ci.yml"
TRIVY_INSTALLER = ROOT / "scripts" / "install-verified-trivy.sh"
RESCAN_PLANNER = ROOT / "scripts" / "plan-rescan-targets.py"
TRIVY_SHA256 = "2ae6fe3ee734b7fdf11335663e18c75ea12dccc76062f09f164a3b0f8be4371a"

JOB = r"(?ms)^  {name}:[ \t]*\n.*?(?=^  [A-Za-z0-9_-]+:[ \t]*$|\Z)"


def job(workflow: str, name: str) -> str:
    match = re.search(JOB.format(name=re.escape(name)), workflow)
    assert match, f"job {name} not found"
    return match.group(0)


def steps(job_text: str) -> list[str]:
    body = job_text.split("\n    steps:\n", 1)[1]
    return [s for s in re.split(r"(?m)(?=^      - )", body) if s.startswith("      - ")]


def step_named(job_text: str, name: str) -> str:
    found = [s for s in steps(job_text) if re.match(rf"      - name: {re.escape(name)}\n", s)]
    assert len(found) == 1, (name, len(found))
    return found[0]


# Anything that would hand a credential to a step's processes.
CREDENTIAL_MARKERS = (
    "secrets.",
    "steps.source_token",
    "github.token",
    "YUETO_FORK_READ_TOKEN",
    "GIT_CONFIG",
    "extraheader",
)
# Anything that executes third-party (dependency) code.
DEPENDENCY_CODE_MARKERS = ("go test", "make test", "make build", "go run ", "check-vulnerabilities.sh")


def credential_leaks(job_text: str) -> list[str]:
    """Steps that both run dependency code and carry a credential."""
    leaks = []
    for step in steps(job_text):
        if any(marker in step for marker in DEPENDENCY_CODE_MARKERS):
            if any(marker in step for marker in CREDENTIAL_MARKERS):
                leaks.append(step.splitlines()[0].strip())
    return leaks


class ForkTokenIsolationTest(unittest.TestCase):
    """C1: the private-fork PAT never reaches the step that runs `go test`."""

    def setUp(self) -> None:
        self.validate = job(BUILD.read_text(), "validate")

    def test_no_step_runs_dependency_code_with_a_credential(self) -> None:
        self.assertEqual(credential_leaks(self.validate), [])
        # Scan floor: the checker really looked at the Go test steps.
        runners = [s for s in steps(self.validate) if "go test" in s]
        self.assertGreaterEqual(len(runners), 3)

    def test_mutation_restoring_the_old_shape_is_caught(self) -> None:
        test_step = step_named(self.validate, "Validate yue-node")
        mutated_step = test_step.replace(
            "          NODE_PROFILE: ${{ matrix.node_profile }}\n",
            "          NODE_PROFILE: ${{ matrix.node_profile }}\n"
            "          YUETO_FORK_READ_TOKEN: ${{ steps.source_token.outputs.token || secrets.YUETO_CI_PAT }}\n",
            1,
        )
        self.assertNotEqual(mutated_step, test_step)
        mutated = self.validate.replace(test_step, mutated_step, 1)
        self.assertEqual(credential_leaks(mutated), ["- name: Validate yue-node"])

    def test_token_lives_only_in_the_tag_verification_step(self) -> None:
        holders = [
            s.splitlines()[0].strip()
            for s in steps(self.validate)
            if "YUETO_FORK_READ_TOKEN" in s
        ]
        self.assertEqual(holders, ["- name: Verify yue-node signed fork tags"])
        verify = step_named(self.validate, "Verify yue-node signed fork tags")
        self.assertIn("if: matrix.validation == 'yue-node'", verify)
        self.assertIn("make verify-fork-tags", verify)
        self.assertNotIn("export ", verify)
        for forbidden in DEPENDENCY_CODE_MARKERS + ("check-profile-deps", "scripts/test-"):
            self.assertNotIn(forbidden, verify)
        names = [s.splitlines()[0] for s in steps(self.validate)]
        self.assertLess(
            names.index("      - name: Verify yue-node signed fork tags"),
            names.index("      - name: Validate yue-node"),
        )

    def test_test_step_is_vendored_and_keeps_its_gates(self) -> None:
        test_step = step_named(self.validate, "Validate yue-node")
        self.assertIn("          GOFLAGS: -mod=vendor\n", test_step)
        self.assertIn("[ -f vendor/modules.txt ]", test_step)
        self.assertIn("make check-profile-deps", test_step)
        self.assertNotIn("verify-fork-tags", test_step)
        self.assertIn("bash scripts/test-check-vulnerabilities.sh", test_step)


def plan_script() -> str:
    plan = job(BUILD.read_text(), "plan")
    step = [s for s in steps(plan) if s.startswith("      - id: plan\n")]
    assert len(step) == 1
    body = step[0].split("        run: |\n", 1)[1]
    return textwrap.dedent(body)


class PlanPromotionGateTest(unittest.TestCase):
    """C3 + C2: execute the real plan step shell."""

    def run_plan(self, **overrides: str) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "out"
            output.touch()
            env = {
                "PATH": os.environ["PATH"],
                "GH_API_TOKEN": "",
                "SERVICE": "yue-node",
                "REF_OVERRIDE": "",
                "EVENT_NAME": "workflow_dispatch",
                "EVENT_ACTOR": "onesyue",
                "WORKFLOW_GIT_REF": "refs/heads/master",
                "MANUAL_PROMOTE": "false",
                "DISPATCH_PROMOTE": "false",
                "MANUAL_YUEBOARD_CONTRACT_REF": "",
                "DISPATCH_YUEBOARD_CONTRACT_REF": "",
                "GITHUB_OUTPUT": str(output),
                **overrides,
            }
            result = subprocess.run(
                ["bash", "-c", plan_script()], cwd=ROOT, env=env,
                text=True, capture_output=True, timeout=60,
            )
            result.outputs = output.read_text()  # type: ignore[attr-defined]
            return result

    def test_candidate_builds_still_accept_branch_refs(self) -> None:
        for ref in ("", "master"):
            result = self.run_plan(REF_OVERRIDE=ref)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("promote=false", result.outputs)

    def test_exact_sha_promotion_from_master_is_planned(self) -> None:
        sha = "a" * 40
        result = self.run_plan(REF_OVERRIDE=sha, MANUAL_PROMOTE="true")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("promote=true", result.outputs)
        matrix = json.loads(re.search(r"^matrix=(.*)$", result.outputs, re.M).group(1))
        self.assertEqual({entry["ref"] for entry in matrix}, {sha})
        validation = json.loads(
            re.search(r"^validation_matrix=(.*)$", result.outputs, re.M).group(1)
        )
        # validate and build judge the identical immutable commit.
        self.assertEqual({entry["ref"] for entry in validation}, {sha})

    def test_promotion_rejects_movable_refs(self) -> None:
        for ref in ("", "master", "refs/heads/master", "v1.2.3", "A" * 40):
            with self.subTest(ref=ref):
                result = self.run_plan(REF_OVERRIDE=ref, MANUAL_PROMOTE="true")
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("promote=true", result.outputs)

    def test_promotion_must_run_from_yueto_ci_master(self) -> None:
        for workflow_ref in ("refs/heads/main", "refs/heads/feature", "refs/tags/v1", ""):
            with self.subTest(workflow_ref=workflow_ref):
                result = self.run_plan(
                    REF_OVERRIDE="b" * 40, MANUAL_PROMOTE="true", WORKFLOW_GIT_REF=workflow_ref
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("only signing identity production accepts", result.stderr)
        # Candidate (non-promote) builds from a side branch still plan; their
        # signatures are simply never accepted by the production verifier.
        side = self.run_plan(REF_OVERRIDE="b" * 40, WORKFLOW_GIT_REF="refs/heads/feature")
        self.assertEqual(side.returncode, 0, side.stderr)

    def test_workflow_ref_is_wired_from_the_runtime(self) -> None:
        plan = job(BUILD.read_text(), "plan")
        self.assertIn("          WORKFLOW_GIT_REF: ${{ github.ref }}\n", plan)


def trivy_action_jobs() -> list[tuple[str, str, str]]:
    found = []
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        text = path.read_text().split("\njobs:\n", 1)[1]
        for block in re.split(r"(?m)(?=^  [A-Za-z0-9_-]+:\s*$)", text):
            if "aquasecurity/trivy-action@" in block:
                found.append((path.name, block.splitlines()[0].strip(), block))
    return found


class VerifiedTrivyWiringTest(unittest.TestCase):
    """C6: every Trivy execution uses the sha256-verified binary."""

    def test_every_trivy_action_skips_its_own_setup_after_verified_install(self) -> None:
        jobs = trivy_action_jobs()
        self.assertEqual(
            {(name, head) for name, head, _ in jobs},
            {("build.yml", "build:"), ("image-rescan.yml", "scan:")},
        )
        uses_count = 0
        for name, head, block in jobs:
            for step in steps(block):
                if "aquasecurity/trivy-action@" not in step:
                    continue
                uses_count += 1
                with self.subTest(workflow=name, step=step.splitlines()[0]):
                    self.assertIn("          skip-setup-trivy: true\n", step)
                    self.assertNotRegex(step, r"(?m)^\s+version:")
                    before = block[: block.index(step)]
                    self.assertRegex(
                        before,
                        r"- name: Install verified Trivy\n\s+run: bash (?:\.ci-policy/)?scripts/install-verified-trivy\.sh",
                    )
        self.assertEqual(uses_count, 3)

    def test_installer_pins_one_reviewed_artifact(self) -> None:
        source = TRIVY_INSTALLER.read_text()
        self.assertEqual(source.count(TRIVY_SHA256), 1)
        self.assertIn("readonly TRIVY_VERSION='0.74.0'", source)
        self.assertIn("--proto '=https' --proto-redir '=https'", source)
        self.assertIn("sha256sum --check --strict", source)
        self.assertNotIn("${TRIVY_SHA256", source)
        self.assertNotIn("${TRIVY_VERSION:-", source)


class VerifiedTrivyInstallerTest(unittest.TestCase):
    """Run the installer against a local fixture (only the digest is swapped)."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.artifact = self.base / "trivy.tar.gz"
        self.write_artifact("Version: 0.74.0")
        self.digest = hashlib.sha256(self.artifact.read_bytes()).hexdigest()
        self.github_path = self.base / "github_path"
        self.github_path.touch()
        self.env = {
            **os.environ,
            "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
            "RUNNER_TEMP": str(self.base),
            "GITHUB_PATH": str(self.github_path),
            "TEST_ARTIFACT": str(self.artifact),
            "TEST_DOWNLOADS": str(self.base / "downloads"),
            "TEST_EXECUTIONS": str(self.base / "executions"),
        }
        if os.uname().sysname == "Darwin" and shutil.which("gsha256sum"):
            (self.bin / "sha256sum").symlink_to(shutil.which("gsha256sum"))
        self.shim("uname", 'case "$1" in -s) echo Linux;; -m) echo x86_64;; esac\n')
        self.shim(
            "curl",
            'echo download >> "$TEST_DOWNLOADS"\n'
            '[ "${TEST_DOWNLOAD_FAIL:-0}" = 0 ] || exit 22\n'
            'while [ "$#" -gt 0 ]; do\n'
            '  if [ "$1" = --output ]; then cp "$TEST_ARTIFACT" "$2"; exit; fi\n'
            "  shift\n"
            "done\nexit 64\n",
        )
        # A different trivy already on the runner must be shadowed.
        self.shim("trivy", "echo 'Version: 0.1.0'\n")

    def write_artifact(self, version_line: str) -> None:
        script = (
            "#!/bin/sh\n"
            'echo executed >> "$TEST_EXECUTIONS"\n'
            f"echo '{version_line}'\n"
        ).encode()
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            info = tarfile.TarInfo("trivy")
            info.size = len(script)
            info.mode = 0o755
            archive.addfile(info, io.BytesIO(script))
        self.artifact.write_bytes(buffer.getvalue())

    def shim(self, name: str, body: str) -> None:
        path = self.bin / name
        path.write_text("#!/bin/sh\nset -eu\n" + body)
        path.chmod(0o755)

    def run_installer(self) -> subprocess.CompletedProcess:
        candidate = self.base / "installer.sh"
        candidate.write_text(TRIVY_INSTALLER.read_text().replace(TRIVY_SHA256, self.digest))
        return subprocess.run(
            ["bash", str(candidate)], env=self.env, text=True,
            capture_output=True, timeout=30,
        )

    def test_good_artifact_is_installed_first_on_path(self) -> None:
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        installed = Path(self.github_path.read_text().strip())
        self.assertTrue((installed / "trivy").is_file())
        resolved = subprocess.check_output(
            ["sh", "-c", "command -v trivy"],
            env={**self.env, "PATH": f"{installed}{os.pathsep}{self.env['PATH']}"},
            text=True,
        ).strip()
        self.assertEqual(resolved, str(installed / "trivy"))
        self.assertEqual(list(installed.parent.glob("*.tar.gz")), [])

    def test_wrong_digest_never_executes_or_publishes_a_path(self) -> None:
        self.write_artifact("Version: 0.74.0 tampered")
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.base / "executions").exists())
        self.assertEqual(self.github_path.read_text(), "")

    def test_download_failure_fails_closed(self) -> None:
        self.env["TEST_DOWNLOAD_FAIL"] = "1"
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.github_path.read_text(), "")

    def test_unexpected_version_is_rejected(self) -> None:
        self.write_artifact("Version: 0.74.01")
        self.digest = hashlib.sha256(self.artifact.read_bytes()).hexdigest()
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.github_path.read_text(), "")

    def test_unreviewed_architecture_stops_before_download(self) -> None:
        self.shim("uname", 'case "$1" in -s) echo Linux;; -m) echo aarch64;; esac\n')
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.base / "downloads").exists())

    def test_environment_cannot_override_reviewed_digest(self) -> None:
        self.env["TRIVY_SHA256"] = "0" * 64
        self.env["TRIVY_ARCHIVE_SHA256"] = "0" * 64
        self.env["TRIVY_VERSION"] = "0.1.0"
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("verified trivy 0.74.0", result.stdout)


def version(digest_char: str, tags: list[str], updated: str) -> dict:
    return {
        "name": "sha256:" + digest_char * 64,
        "updated_at": updated,
        "metadata": {"container": {"tags": tags}},
    }


def promoted(digest_char: str) -> str:
    return f"promoted-{'1' * 40}-{digest_char * 64}"


class RescanPlannerTest(unittest.TestCase):
    """C5: scan :latest plus the newest promoted digests; fail closed."""

    def run_planner(self, per_service: dict[str, list[dict]]) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as temp:
            services = json.loads((ROOT / "services.json").read_text())
            for service in services:
                versions = per_service.get(service["service"], per_service.get("*"))
                Path(temp, f"{service['service']}.json").write_text(json.dumps(versions))
            env = {k: v for k, v in os.environ.items() if k != "GITHUB_OUTPUT"}
            return subprocess.run(
                ["python3", str(RESCAN_PLANNER), "--versions-dir", temp],
                env=env, text=True, capture_output=True, timeout=30,
            )

    def healthy(self) -> list[dict]:
        return [
            version("c", ["sha256-" + "c" * 64], "2026-09-26T21:20:00Z"),  # signature artifact
            version("a", [promoted("a"), "latest", "sha-" + "1" * 40], "2026-09-26T21:19:00Z"),
            version("b", [promoted("b")], "2026-09-26T19:00:00Z"),
            version("d", [promoted("d")], "2026-09-26T18:00:00Z"),
            version("e", [promoted("e")], "2026-09-25T18:00:00Z"),
            version("f", ["candidate-1-1"], "2026-09-24T18:00:00Z"),
        ]

    def test_latest_and_newest_promoted_digests_are_scanned_per_platform(self) -> None:
        result = self.run_planner({"*": self.healthy()})
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = [line.split() for line in result.stdout.splitlines()]
        node = [(r[1], r[2], r[3][7:8]) for r in rows if r[0] == "yue-node"]
        self.assertEqual(
            node,
            [
                ("linux/amd64", "latest", "a"), ("linux/arm64", "latest", "a"),
                ("linux/amd64", "promoted-1", "b"), ("linux/arm64", "promoted-1", "b"),
                ("linux/amd64", "promoted-2", "d"), ("linux/arm64", "promoted-2", "d"),
            ],
        )
        # Depth bound: the fourth promoted digest is out; candidates never scan.
        self.assertNotIn("sha256:" + "e" * 64, result.stdout)
        self.assertNotIn("sha256:" + "f" * 64, result.stdout)

    def test_enumeration_problems_fail_closed(self) -> None:
        cases = {
            "no latest": [v for v in self.healthy() if "latest" not in v["metadata"]["container"]["tags"]]
            + [version("9", [promoted("9")], "2026-09-27T00:00:00Z")],
            "no promoted marker": [version("a", ["latest"], "2026-09-26T21:19:00Z")],
            "marker names another digest": [
                version("a", ["latest", promoted("b")], "2026-09-26T21:19:00Z")
            ],
            "malformed marker": [version("a", ["latest", "promoted-xyz"], "2026-09-26T21:19:00Z")],
            "empty": [],
        }
        for label, versions in cases.items():
            with self.subTest(case=label):
                result = self.run_planner({"*": versions})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("cannot plan the promoted-image rescan", result.stderr)

    def test_live_mode_without_a_token_fails_closed(self) -> None:
        env = {k: v for k, v in os.environ.items() if k not in {"GH_API_TOKEN", "GITHUB_OUTPUT"}}
        result = subprocess.run(
            ["python3", str(RESCAN_PLANNER)], env=env, text=True,
            capture_output=True, timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GH_API_TOKEN", result.stderr)


class RescanIncidentTest(unittest.TestCase):
    """C5: a failed or cancelled rescan opens one deduplicated YueOps incident."""

    def setUp(self) -> None:
        self.workflow = RESCAN.read_text()

    def test_incident_job_covers_every_non_success(self) -> None:
        incident = job(self.workflow, "incident")
        self.assertIn("    needs: [plan, scan]\n", incident)
        self.assertIn(
            "if: ${{ always() && (needs.plan.result != 'success' || needs.scan.result != 'success') }}",
            incident,
        )
        self.assertIn("repositories: yueops", incident)
        self.assertIn("permission-issues: write", incident)
        self.assertIn("--search \"in:title $title\"", incident)
        self.assertIn('gh issue comment "$existing"', incident)
        self.assertIn("gh issue create", incident)
        # The public repository's own token never gains write permission.
        self.assertNotRegex(self.workflow, r"(?m)^\s+(?:issues|contents|packages):\s*write\s*$")

    def test_scan_uses_the_planned_immutable_digest(self) -> None:
        scan = job(self.workflow, "scan")
        self.assertIn('"${IMAGE}@${DIGEST}"', scan)
        self.assertIn('[ "$digest" = "$DIGEST" ]', scan)
        self.assertNotIn(":latest", scan)


class RunnerAndActionRuntimeTest(unittest.TestCase):
    """GitHub moves `ubuntu-latest` to Ubuntu 26 on 2026-10-19 and removed
    Node20 on 2026-09-23: neither may change our builders underneath us."""

    def workflows(self) -> dict[str, str]:
        found = {p.name: p.read_text() for p in sorted(WORKFLOW_DIR.glob("*.yml"))}
        self.assertGreaterEqual(len(found), 5)
        return found

    @staticmethod
    def runner_violations(workflows: dict[str, str]) -> tuple[list[str], int]:
        bad, hosted = [], 0
        for name, text in workflows.items():
            if "ubuntu-latest" in text:
                bad.append(f"{name}: ubuntu-latest")
            for line in re.findall(r"(?m)^\s+runs-on:.*$", text):
                if "ubuntu" not in line:
                    continue
                hosted += 1
                if not re.search(r"ubuntu-24\.04", line) or re.search(r"ubuntu-(?!24\.04)\d", line):
                    bad.append(f"{name}: {line.strip()}")
        return bad, hosted

    def test_no_workflow_uses_the_moving_ubuntu_label(self) -> None:
        bad, hosted = self.runner_violations(self.workflows())
        self.assertEqual(bad, [])
        # Scan floor: plan/validate/build selectors, shadow, poll, rescan x3,
        # deadman, policy.
        self.assertGreaterEqual(hosted, 10)
        build = BUILD.read_text()
        # The signing job's hosted selector is the pinned image too.
        self.assertIn("'[\"ubuntu-24.04\"]')", job(build, "build"))

    def test_mutation_back_to_latest_is_caught(self) -> None:
        for mutated_label in ("ubuntu-latest", "ubuntu-26.04"):
            with self.subTest(label=mutated_label):
                workflows = self.workflows()
                workflows["build.yml"] = workflows["build.yml"].replace(
                    "'[\"ubuntu-24.04\"]'", f"'[\"{mutated_label}\"]'", 1
                )
                bad, _ = self.runner_violations(workflows)
                self.assertTrue(bad, mutated_label)

    def test_archived_node20_buf_setup_is_replaced_by_verified_buf_action(self) -> None:
        for name, text in self.workflows().items():
            with self.subTest(workflow=name):
                self.assertNotIn("bufbuild/buf-setup-action@", text)
        validate = job(BUILD.read_text(), "validate")
        step = step_named(validate, "Set up Buf for YueBoard protocol compatibility")
        self.assertIn(
            "uses: bufbuild/buf-action@85aebf73123b5c15fd5528aaecbf9129cddf7fa7 # v1.6.0", step
        )
        self.assertIn("          setup_only: true\n", step)
        self.assertIn("          version: '1.72.0'\n", step)
        self.assertIn(
            "          checksum: 8720830e26a733da55bb89bcd3cb44849c0965fc0c44fb5d691cccdc64dca5af\n",
            step,
        )
        # buf-action without setup_only would run its own lint/format/push.
        for forbidden in ("token:", "bot_username", "push:", "breaking:"):
            self.assertNotIn(f"          {forbidden}", step)


class PolicyCiRunsEveryTestFileTest(unittest.TestCase):
    # 2026-09-28: policy-ci switched from a per-file list to unittest discovery;
    # tests/test_policy_discovery_contract.py owns the reachability contract.
    # This keeps the original intent (this file itself must run) as a direct check.
    def test_every_policy_test_file_is_executed_by_policy_ci(self) -> None:
        policy = POLICY_CI.read_text()
        files = sorted(p.name for p in (ROOT / "tests").glob("test_*.py"))
        self.assertIn("test_hardening_20260927.py", files)
        self.assertIn("test_policy_discovery_contract.py", files)
        self.assertIn("python3 -m unittest discover -s tests -p 'test_*.py'", policy)


if __name__ == "__main__":
    unittest.main()
