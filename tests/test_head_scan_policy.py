"""Daily master-head image gate matches the ship Trivy policy."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import subprocess
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "head_scan_policy", ROOT / "scripts" / "head_scan_policy.py"
)
assert SPEC is not None and SPEC.loader is not None
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)

WORKFLOW = ROOT / ".github" / "workflows" / "weekly-vuln-sbom.yml"
BUILD = ROOT / ".github" / "workflows" / "build.yml"
SHA = "a" * 40
BUILT = "2026-11-26T01:02:03Z"
TOKEN = "present"
REF = "refs/heads/master"


def _uncomment(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def _report(severity: str, fixed: str | None, cve: str = "CVE-2026-1001") -> dict:
    item = {
        "VulnerabilityID": cve,
        "PkgName": "openssl",
        "InstalledVersion": "1.1.1",
        "Severity": severity,
    }
    if fixed is not None:
        item["FixedVersion"] = fixed
    return {"Results": [{"Vulnerabilities": [item]}]}


def _sources(root: Path, *, drop: str | None = None) -> None:
    files = {
        "yueops/services/yueops-web/Dockerfile": "FROM scratch\n",
        "yueops/services/checkin-api/Dockerfile": "FROM scratch\n",
        "yueops/services/yue-bot/Dockerfile": "FROM scratch\n",
        "yueboard/Dockerfile": "FROM scratch\n",
        "yue-node/Dockerfile": "FROM scratch\n",
    }
    if drop is not None:
        del files[drop]
        (root / drop).unlink(missing_ok=True)
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


class _Runner:
    def __init__(self, reports: dict[str, dict]) -> None:
        self.reports = reports
        self.docker: list[list[str]] = []
        self.trivy: list[list[str]] = []
        self.timeouts: list[int] = []

    def __call__(self, argv, **kwargs):
        if argv[:2] == ["git", "-C"] and "rev-parse" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout=SHA + "\n", stderr="")
        if argv[:2] == ["git", "-C"] and "show" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout=BUILT + "\n", stderr="")
        if argv[:2] == ["docker", "build"]:
            self.docker.append(list(argv))
            self.timeouts.append(kwargs["timeout"])
            self.assert_build(argv, kwargs.get("env") or {})
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        if argv[:2] == ["trivy", "image"]:
            self.trivy.append(list(argv))
            self.timeouts.append(kwargs["timeout"])
            output = Path(argv[argv.index("--output") + 1])
            service = argv[-1].removeprefix("headscan-").removesuffix(":local")
            output.write_text(json.dumps(self.reports.get(service, {"Results": []})), encoding="utf-8")
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        raise AssertionError(argv)

    @staticmethod
    def assert_build(argv: list[str], env: dict) -> None:
        if "buildx" in argv or any("ghcr.io" in item for item in argv):
            raise AssertionError(argv)
        if env.get("DOCKER_BUILDKIT") != "1":
            raise AssertionError(env.get("DOCKER_BUILDKIT"))


class ParityTest(unittest.TestCase):
    def test_build_and_scan_resolve_to_the_same_gate(self) -> None:
        build = BUILD.read_text(encoding="utf-8")
        scan = WORKFLOW.read_text(encoding="utf-8")
        self.assertIsNone(policy.parity_mismatch(build, scan))
        canonical = policy.canonical_action_flags()
        self.assertEqual(policy.flags_from_scan(scan), canonical)
        blocks = policy.block_flags(build)
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0], blocks[1])
        self.assertEqual(blocks[0], canonical)
        self.assertEqual(canonical["severity"], "HIGH,CRITICAL")
        self.assertEqual(canonical["trivyignores"], ".ci-policy/.trivyignore")
        self.assertEqual(canonical["ignore-unfixed"], "true")
        self.assertLess(
            scan.index(policy.VERIFIED_TRIVY),
            scan.index(policy.SCAN_COMMAND),
        )
        self.assertIn("head_scan_policy.py parity", scan)
        self.assertIn("head_scan_policy.py resolve-heads", scan)
        self.assertEqual(scan.count(policy.SCAN_COMMAND), 1)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(policy.main(["parity"]), 0)
        self.assertEqual(buf.getvalue().strip(), "head-scan parity ok")

    def test_severity_drift_in_one_workflow_fails_and_restores(self) -> None:
        build = BUILD.read_text(encoding="utf-8")
        scan = WORKFLOW.read_text(encoding="utf-8")
        mutated = scan.replace("--severity HIGH,CRITICAL", "--severity CRITICAL", 1)
        reason = policy.parity_mismatch(build, mutated)
        self.assertIsNotNone(reason)
        self.assertIn("severity", reason or "")
        self.assertIsNone(policy.parity_mismatch(build, scan))
        one_build = build.replace("severity: HIGH,CRITICAL", "severity: CRITICAL", 1)
        build_reason = policy.parity_mismatch(one_build, scan)
        self.assertIsNotNone(build_reason)
        self.assertIn("severity", build_reason or "")
        self.assertIsNone(policy.parity_mismatch(build, scan))


class WorkflowShapeTest(unittest.TestCase):
    def test_daily_job_stays_inside_the_weekly_workflow(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        code = _uncomment(text)
        document = yaml.safe_load(text)
        jobs = document["jobs"]
        self.assertLessEqual(len(jobs), 5)
        self.assertEqual(set(jobs), {"report", "head-scan"})
        self.assertEqual(jobs["head-scan"]["timeout-minutes"], 140)
        self.assertEqual(jobs["head-scan"]["timeout-minutes"], policy.HEAD_SCAN_JOB_TIMEOUT_MINUTES)
        self.assertEqual(jobs["report"]["timeout-minutes"], 90)
        self.assertIsInstance(jobs["head-scan"]["timeout-minutes"], int)
        self.assertIn("cron: '17 3 * * *'", text)
        self.assertIn("cron: '17 3 * * 1'", text)
        self.assertIn("17 3 * * 1", jobs["report"]["if"])
        self.assertIn("17 3 * * *", jobs["head-scan"]["if"])
        self.assertNotIn("ref: master", code)
        self.assertEqual(set(re.findall(r"secrets\.([A-Z0-9_]+)", text)), {"YUETO_CI_PAT"})
        self.assertNotIn("aquasecurity/trivy-action@", text)
        self.assertNotIn("buildx", code)
        self.assertNotIn("ghcr.io", code)
        self.assertNotIn("build-push-action", code)
        shipped = policy.load_shipped(ROOT / "services.json")
        self.assertEqual(set(shipped), set(policy.SHIPPED_SERVICES))


class GateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _gate(self, document: dict, image: str = "checkin-api") -> tuple[int, str, str]:
        path = Path(self.tmp.name) / "report.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = policy.main(["gate", "--image", image, "--report", str(path)])
        return rc, out.getvalue(), err.getvalue()

    def test_fixed_high_fails_with_one_line(self) -> None:
        rc, out, err = self._gate(_report("HIGH", "1.1.2"))
        self.assertEqual(rc, 1)
        self.assertEqual(err, "")
        self.assertEqual(out, "checkin-api: openssl, 1.1.1 → 1.1.2, CVE-2026-1001\n")

    def test_unfixed_high_passes(self) -> None:
        rc, out, _err = self._gate(_report("HIGH", ""))
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")
        rc, out, _err = self._gate(_report("HIGH", None))
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")

    def test_fixed_low_passes_and_fixed_critical_fails(self) -> None:
        rc, out, _err = self._gate(_report("LOW", "9.9.9"))
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")
        rc, out, _err = self._gate(_report("CRITICAL", "3.0.1", cve="CVE-2026-2002"))
        self.assertEqual(rc, 1)
        self.assertEqual(out, "checkin-api: openssl, 1.1.1 → 3.0.1, CVE-2026-2002\n")

    def test_two_fixed_highs_are_sorted_once(self) -> None:
        document = {
            "Results": [
                {
                    "Vulnerabilities": [
                        {
                            "VulnerabilityID": "CVE-2026-1002",
                            "PkgName": "zlib",
                            "InstalledVersion": "2",
                            "FixedVersion": "3",
                            "Severity": "HIGH",
                        },
                        {
                            "VulnerabilityID": "CVE-2026-1002",
                            "PkgName": "zlib",
                            "InstalledVersion": "2",
                            "FixedVersion": "3",
                            "Severity": "HIGH",
                        },
                        {
                            "VulnerabilityID": "CVE-2026-1001",
                            "PkgName": "openssl",
                            "InstalledVersion": "1",
                            "FixedVersion": "2",
                            "Severity": "HIGH",
                        },
                    ]
                }
            ]
        }
        rc, out, _err = self._gate(document)
        self.assertEqual(rc, 1)
        self.assertEqual(
            out,
            "checkin-api: openssl, 1 → 2, CVE-2026-1001\n"
            "checkin-api: zlib, 2 → 3, CVE-2026-1002\n",
        )


class ResolveHeadsTest(unittest.TestCase):
    def test_missing_token_is_a_named_error(self) -> None:
        with mock.patch.dict(os.environ, {"YUETO_CI_PAT": ""}):
            with self.assertRaises(policy.PolicyError) as caught:
                policy.resolve_heads(runner=lambda *_a, **_k: self.fail("network"))
        self.assertEqual(str(caught.exception), "head-scan: YUETO_CI_PAT is missing")

    def test_resolve_prints_shas_without_putting_the_token_on_argv(self) -> None:
        seen: list[list[str]] = []

        def runner(argv, **kwargs):
            seen.append(list(argv))
            self.assertNotIn(TOKEN, " ".join(argv))
            self.assertEqual(kwargs["env"]["GIT_CONFIG_VALUE_0"], f"AUTHORIZATION: bearer {TOKEN}")
            self.assertEqual(argv[0], "git")
            self.assertEqual(argv[1], "ls-remote")
            self.assertTrue(argv[2].startswith("https://github.com/onesyue/"))
            self.assertTrue(argv[2].endswith(".git"))
            self.assertEqual(argv[3], REF)
            return subprocess.CompletedProcess(argv, 0, stdout=f"{SHA}\t{REF}\n", stderr=TOKEN)

        with mock.patch.dict(os.environ, {"YUETO_CI_PAT": TOKEN}):
            text = policy.resolve_heads(runner=runner)
        self.assertNotIn(TOKEN, text)
        self.assertEqual(
            text,
            f"yueops={SHA}\nyueboard={SHA}\nyue_node={SHA}\n",
        )
        self.assertEqual(len(seen), 3)

    def test_ls_remote_failure_does_not_include_stderr(self) -> None:
        def runner(argv, **_kwargs):
            return subprocess.CompletedProcess(argv, 128, stdout="", stderr=TOKEN)

        with mock.patch.dict(os.environ, {"YUETO_CI_PAT": TOKEN}):
            with self.assertRaises(policy.PolicyError) as caught:
                policy.resolve_heads(runner=runner)
        self.assertEqual(str(caught.exception), "head-scan: ls-remote failed for yueops")
        self.assertNotIn(TOKEN, str(caught.exception))


class ScanHeadsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.sources = Path(self.tmp.name) / "sources"
        _sources(self.sources)

    def test_fixed_high_fails_on_the_local_amd64_build(self) -> None:
        runner = _Runner({"checkin-api": _report("HIGH", "1.1.2")})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = policy.scan_heads(
                self.sources,
                ROOT,
                policy.canonical_action_flags(),
                runner=runner,
            )
        self.assertEqual(rc, 1)
        self.assertEqual(out.getvalue(), "checkin-api: openssl, 1.1.1 → 1.1.2, CVE-2026-1001\n")
        self.assertEqual(len(runner.docker), 5)
        self.assertEqual(len(runner.trivy), 5)
        for argv in runner.docker:
            self.assertEqual(argv[:5], ["docker", "build", "--pull", "--platform", "linux/amd64"])
            self.assertNotIn("buildx", argv)
            self.assertTrue(any(item == f"VERSION={SHA}" for item in argv))
        node = next(argv for argv in runner.docker if "headscan-yue-node:local" in argv)
        self.assertIn("BUILD_PROFILE=auto", argv_build_args(node))
        web = next(argv for argv in runner.docker if "headscan-yueops-web:local" in argv)
        self.assertNotIn("BUILD_PROFILE=auto", argv_build_args(web))
        for argv in runner.trivy:
            self.assertEqual(argv[argv.index("--severity") + 1], "HIGH,CRITICAL")
            self.assertEqual(argv[argv.index("--ignore-unfixed") + 1], "--vuln-type")
            self.assertEqual(argv[argv.index("--vuln-type") + 1], "os,library")
            self.assertEqual(argv[argv.index("--scanners") + 1], "vuln")
            self.assertEqual(argv[argv.index("--format") + 1], "json")
            self.assertEqual(argv[argv.index("--exit-code") + 1], "0")
            self.assertEqual(argv[argv.index("--timeout") + 1], "15m")
            self.assertTrue(argv[argv.index("--ignorefile") + 1].endswith(".trivyignore"))
        self.assertIn(policy.HEAD_SCAN_BUILD_TIMEOUT_SECONDS, runner.timeouts)
        self.assertIn(policy.TRIVY_ACTION_TIMEOUT_SECONDS, runner.timeouts)

    def test_unfixed_only_passes(self) -> None:
        runner = _Runner({"yue-bot": _report("HIGH", "")})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = policy.scan_heads(
                self.sources,
                ROOT,
                policy.canonical_action_flags(),
                runner=runner,
            )
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue(), "")

    def test_missing_dockerfile_is_a_named_error(self) -> None:
        _sources(self.sources, drop="yueops/services/yueops-web/Dockerfile")
        with self.assertRaises(policy.PolicyError) as caught:
            policy.scan_heads(
                self.sources,
                ROOT,
                policy.canonical_action_flags(),
                runner=_Runner({}),
            )
        self.assertEqual(str(caught.exception), "head-scan: yueops-web dockerfile is missing")

    def test_declared_severity_drift_exits_nonzero(self) -> None:
        flags = policy.canonical_action_flags()
        argv = ["scan-heads", "--sources", str(self.sources)]
        flags["severity"] = "CRITICAL"
        for key in policy.ACTION_KEYS:
            argv.extend([f"--{key}", flags[key]])
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = policy.main(argv)
        self.assertEqual(rc, 2)
        self.assertIn("declared policy drifted", err.getvalue())
        self.assertIn("severity", err.getvalue())


def argv_build_args(argv: list[str]) -> list[str]:
    return [argv[index + 1] for index, item in enumerate(argv) if item == "--build-arg"]


if __name__ == "__main__":
    unittest.main()
