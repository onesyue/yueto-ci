"""Report-only weekly vulnerability and SBOM scan: catalog, pins, floor, workflow."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import unittest
import unittest.mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "weekly_vuln_scan", ROOT / "scripts" / "weekly-vuln-scan.py"
)
assert SPEC is not None and SPEC.loader is not None
SCAN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCAN)

CATALOG = ROOT / "policy" / "weekly-vuln-scan-targets.json"
WORKFLOW = ROOT / ".github" / "workflows" / "weekly-vuln-sbom.yml"
LINT_PINS = ROOT / "scripts" / "lint-tool-versions.sh"
SCANNER_PINS = ROOT / "scripts" / "scanner-tool-versions.sh"
REVISION = "a" * 40
GOVULNCHECK_ZIP = "396b780e8e9cf35cd5b0c481fed8e841cff89a21bf4f1b61556d1694f42fb572"
DART_SHA = "eb99aed266efbcb615c6ae21c12f52cfe935b9f208bccc5fea7f64c21e867229"
PIP_AUDIT_WHEEL = "99ef3f600a317c1945f1e89e227ef26e1c2d618429b8bd3fa6f4f7c440c4611a"
BASH = shutil.which("bash") or "/bin/bash"
FIRST_PARTY = (
    "yue-node",
    "yueboard",
    "yueops",
    "yueto",
    "yuelink",
    "yueto-ci",
    "yuelink-ci",
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def uncomment(text: str) -> str:
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


def named_steps(text: str) -> list[tuple[str, str]]:
    body = text.split("\n    steps:\n", 1)[1]
    parts = re.split(r"(?m)^      - name: ", body)
    steps = []
    for part in parts[1:]:
        name, _, rest = part.partition("\n")
        steps.append((name.strip(), rest))
    return steps


def write_repo(root: Path, name: str, files: dict[str, str]) -> Path:
    repo = root / name
    repo.mkdir(parents=True)
    for relative, content in files.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return repo


def complete_sources(root: Path) -> None:
    write_repo(root, "yue-node", {"go.mod": "module example.com/node\n"})
    write_repo(
        root,
        "yueboard",
        {"go.mod": "module example.com/board\n", "pnpm-lock.yaml": "lockfileVersion: '9.0'\n"},
    )
    write_repo(
        root,
        "yueops",
        {
            "uv.lock": "version = 1\n",
            "package-lock.json": "{}\n",
            "frontend/package-lock.json": "{}\n",
        },
    )
    write_repo(root, "yueto", {"README.md": "yueto\n"})
    write_repo(root, "yuelink", {"pubspec.yaml": "name: yuelink\n"})
    write_repo(
        root,
        "yueto-ci",
        {
            "requirements-audit.txt": (
                "demo==1.0.0 \\\n    --hash=sha256:" + ("ab" * 32) + "\n"
            )
        },
    )
    write_repo(root, "yuelink-ci", {"README.md": "yuelink-ci\n"})


class CatalogPolicyTest(unittest.TestCase):
    def test_reviewed_catalog_meets_the_scan_floor(self) -> None:
        catalog = SCAN.load_catalog(CATALOG)
        names = [entry["name"] for entry in catalog["repositories"]]
        self.assertEqual(names, list(FIRST_PARTY))
        self.assertTrue(catalog["report_only"])
        self.assertEqual(catalog["minimum_repositories"], 7)
        self.assertGreaterEqual(catalog["minimum_scanner_runs"], 10)
        self.assertEqual(
            set(catalog["required_kinds"]),
            {"govulncheck", "pip-audit", "npm-audit", "pnpm-audit", "dart-outdated", "syft"},
        )

    def test_catalog_command_prints_the_first_party_matrix(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/weekly-vuln-scan.py"), "catalog"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(
            [entry["repo"] for entry in payload["repositories"]], list(FIRST_PARTY)
        )

    def test_catalog_mutations_are_rejected(self) -> None:
        catalog = load_json(CATALOG)
        cases = {
            "schema": lambda data: data.__setitem__("schema_version", 2),
            "report_only": lambda data: data.__setitem__("report_only", False),
            "duplicate": lambda data: data["repositories"].append(data["repositories"][0]),
            "unknown": lambda data: data["repositories"][0].__setitem__(
                "scanners", ["govulncheck", "trivy"]
            ),
            "floor": lambda data: data.__setitem__("minimum_repositories", 8),
            "kinds": lambda data: data["repositories"][4].__setitem__("scanners", ["syft"]),
        }
        with tempfile.TemporaryDirectory() as tmp:
            for name, mutate in cases.items():
                with self.subTest(mutation=name):
                    data = json.loads(json.dumps(catalog))
                    mutate(data)
                    path = Path(tmp) / f"{name}.json"
                    path.write_text(json.dumps(data), encoding="utf-8")
                    with self.assertRaises(SCAN.ScanError):
                        SCAN.load_catalog(path)


class FindingCounterTest(unittest.TestCase):
    def test_govulncheck_counts_ndjson_finding_objects(self) -> None:
        payload = SCAN.parse_json_output(
            '{"config":{"protocol_version":"v1"}}\n'
            '{"finding":{"osv":"GO-2024-2687"}}\n'
            '{"progress":{"message":"done"}}\n'
        )
        self.assertEqual(SCAN.count_govulncheck(payload), 1)

    def test_empty_or_invalid_scanner_json_is_infrastructure_failure(self) -> None:
        with self.assertRaises(SCAN.ScanError):
            SCAN.parse_json_output("")
        with self.assertRaises(SCAN.ScanError):
            SCAN.parse_json_output("{not json}\n")

    def test_pip_and_npm_counts_follow_native_shapes(self) -> None:
        self.assertEqual(
            SCAN.count_pip_audit(
                {"dependencies": [{"name": "demo", "vulns": [{}, {}]}, {"name": "ok", "vulns": []}]}
            ),
            2,
        )
        self.assertEqual(
            SCAN.count_npm_audit({"vulnerabilities": {"left-pad": {}, "lodash": {}}}),
            2,
        )


class ReportOnlyScanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sources = self.root / "sources"
        self.output = self.root / "out"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.calls: list[list[str]] = []
        for name in (
            "govulncheck",
            "pip-audit",
            "uv",
            "npm",
            "corepack",
            "pnpm",
            "dart",
            "syft",
        ):
            path = self.bin / name
            path.write_text("#!/bin/sh\nexit 0\n")
            path.chmod(0o755)
        self.path = str(self.bin)
        self.patch = unittest.mock.patch.dict(os.environ, {"PATH": self.path})
        self.patch.start()
        self.addCleanup(self.patch.stop)
        complete_sources(self.sources)

    def args(self, catalog: Path | None = None) -> argparse.Namespace:
        return argparse.Namespace(
            catalog=str(catalog or CATALOG),
            scanner_pins=str(SCANNER_PINS),
            lint_pins=str(LINT_PINS),
            sources=str(self.sources),
            output=str(self.output),
        )

    def runner(self, *, findings: bool = True, empty_govuln: bool = False):
        def execute(argv, cwd=None, text=True, capture_output=True, timeout=600, check=False):
            argv = [str(part) for part in argv]
            self.calls.append(argv)
            name = argv[0]
            stdout = ""
            returncode = 0
            if name == "git" and "rev-parse" in argv:
                stdout = REVISION + "\n"
            elif name == "govulncheck":
                if empty_govuln:
                    stdout = ""
                elif findings:
                    stdout = '{"config":{}}\n{"finding":{"osv":"GO-2024-2687"}}\n'
                    returncode = 3
                else:
                    stdout = '{"config":{}}\n'
            elif name == "uv":
                dest = Path(argv[argv.index("--output-file") + 1])
                dest.write_text("demo==1.0.0\n", encoding="utf-8")
            elif name == "pip-audit":
                vulns = [{"id": "GHSA-xxxx"}] if findings else []
                stdout = json.dumps({"dependencies": [{"name": "demo", "vulns": vulns}]})
                returncode = 1 if findings else 0
            elif name in {"npm", "pnpm"} and "audit" in argv:
                stdout = json.dumps({"vulnerabilities": {"left-pad": {"severity": "high"}}})
                returncode = 1
            elif name == "corepack":
                stdout = ""
            elif name == "dart" and "outdated" in argv:
                stdout = json.dumps(
                    {
                        "packages": [
                            {
                                "package": "path",
                                "current": {"version": "1.0.0"},
                                "latest": {"version": "1.1.0"},
                            }
                        ]
                    }
                )
            elif name == "dart":
                stdout = ""
            elif name == "syft":
                output_flag = [item for item in argv if item.startswith("cyclonedx-json=")]
                dest = Path(output_flag[0].split("=", 1)[1])
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(
                    json.dumps({"bomFormat": "CycloneDX", "components": [{"name": "demo"}]}),
                    encoding="utf-8",
                )
            else:
                raise AssertionError(argv)
            return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr="")

        return execute

    def test_findings_are_recorded_and_do_not_fail_the_scan(self) -> None:
        rc = SCAN.cmd_scan(self.args(), runner=self.runner(findings=True))
        self.assertEqual(rc, 0)
        summary = load_json(self.output / "summary.json")
        self.assertTrue(summary["report_only"])
        self.assertFalse(summary["opens_pull_requests"])
        self.assertFalse(summary["blocks_builds"])
        self.assertEqual(summary["repositories"], 7)
        self.assertGreaterEqual(summary["scanner_runs"], 10)
        self.assertGreater(summary["findings_count"], 0)
        reports = load_json(self.output / "findings.json")
        self.assertEqual([row["name"] for row in reports], list(FIRST_PARTY))
        for name in FIRST_PARTY:
            sbom = self.output / "sbom" / f"{name}.cdx.json"
            self.assertGreater(sbom.stat().st_size, 2)
        self.assertIn("Report-only", (self.output / "SUMMARY.md").read_text())
        joined = [" ".join(call) for call in self.calls]
        self.assertTrue(any("npm audit --package-lock-only --json" == item for item in joined))
        self.assertTrue(any("dart pub get --enforce-lockfile" == item for item in joined))
        self.assertTrue(
            any(item.startswith("uv export --frozen --all-groups --no-emit-local") for item in joined)
        )
        hashed = [
            call
            for call in self.calls
            if call[:1] == ["pip-audit"] and "--require-hashes" in call
        ]
        self.assertTrue(hashed)

    def test_vendor_go_mod_is_not_a_scan_target(self) -> None:
        write_repo(
            self.sources,
            "extra-vendor",
            {"go.mod": "module example.com/root\n", "vendor/go.mod": "module example.com/vendored\n"},
        )
        rows = SCAN.run_govulncheck(self.sources / "extra-vendor", self.runner())
        self.assertEqual([row["target"] for row in rows], ["."])

    def test_missing_lockfile_is_infrastructure_failure(self) -> None:
        shutil.rmtree(self.sources / "yue-node")
        write_repo(self.sources, "yue-node", {"README.md": "no go\n"})
        with self.assertRaises(SCAN.ScanError) as raised:
            SCAN.cmd_scan(self.args(), runner=self.runner())
        self.assertIn("no go.mod", str(raised.exception))

    def test_missing_source_checkout_fails_closed(self) -> None:
        shutil.rmtree(self.sources / "yuelink")
        with self.assertRaises(SCAN.ScanError) as raised:
            SCAN.cmd_scan(self.args(), runner=self.runner())
        self.assertIn("source checkout is missing", str(raised.exception))

    def test_missing_scanner_binary_fails_closed(self) -> None:
        (self.bin / "govulncheck").unlink()
        with self.assertRaises(SCAN.ScanError) as raised:
            SCAN.cmd_scan(self.args(), runner=self.runner())
        self.assertIn("govulncheck is not on PATH", str(raised.exception))

    def test_empty_govulncheck_json_fails_closed(self) -> None:
        with self.assertRaises(SCAN.ScanError) as raised:
            SCAN.cmd_scan(self.args(), runner=self.runner(empty_govuln=True))
        self.assertIn("produced no JSON", str(raised.exception))

    def test_scan_floor_miss_fails_closed(self) -> None:
        catalog = load_json(CATALOG)
        catalog["minimum_scanner_runs"] = 999
        path = self.root / "high-floor.json"
        path.write_text(json.dumps(catalog), encoding="utf-8")
        with self.assertRaises(SCAN.ScanError) as raised:
            SCAN.cmd_scan(self.args(path), runner=self.runner(findings=False))
        self.assertIn("scan floor miss", str(raised.exception))

    def test_missing_govulncheck_zip_pin_fails_closed(self) -> None:
        pins = self.root / "lint-tool-versions.sh"
        pins.write_text(
            "\n".join(
                line
                for line in LINT_PINS.read_text(encoding="utf-8").splitlines()
                if "GOVULNCHECK_ZIP_SHA256" not in line
            )
            + "\n",
            encoding="utf-8",
        )
        args = self.args()
        args.lint_pins = str(pins)
        with self.assertRaises(SCAN.ScanError) as raised:
            SCAN.cmd_scan(args, runner=self.runner())
        self.assertIn("GOVULNCHECK_ZIP_SHA256", str(raised.exception))

    def test_main_returns_two_on_infrastructure_failure(self) -> None:
        shutil.rmtree(self.sources / "yue-node")
        stderr = io.StringIO()
        with unittest.mock.patch.object(sys, "stderr", stderr):
            rc = SCAN.main(
                [
                    "scan",
                    "--catalog",
                    str(CATALOG),
                    "--sources",
                    str(self.sources),
                    "--output",
                    str(self.output),
                ]
            )
        self.assertEqual(rc, 2)
        self.assertIn("weekly-vuln-scan:", stderr.getvalue())


class PinAuthorityTest(unittest.TestCase):
    def test_reviewed_pins_are_present_and_hashed(self) -> None:
        lint = LINT_PINS.read_text(encoding="utf-8")
        scanner = SCANNER_PINS.read_text(encoding="utf-8")
        workflow = WORKFLOW.read_text(encoding="utf-8")
        requirements = (ROOT / "requirements-audit.txt").read_text(encoding="utf-8")
        self.assertIn(f"readonly GOVULNCHECK_ZIP_SHA256='{GOVULNCHECK_ZIP}'", lint)
        self.assertIn("${GOVULNCHECK_ZIP_SHA256:-}", lint)
        self.assertIn(f"readonly DART_SDK_SHA256='{DART_SHA}'", scanner)
        self.assertIn("readonly PIP_AUDIT_VERSION='2.10.1'", scanner)
        self.assertIn("readonly NODE_VERSION='24.22.3'", scanner)
        self.assertIn("pip-audit==2.10.1", requirements)
        self.assertIn(PIP_AUDIT_WHEEL, requirements)
        self.assertIn("node-version: '24.22.3'", workflow)
        self.assertIn("--require-hashes --only-binary=:all:", workflow)
        self.assertIn("install-verified-govulncheck.sh", workflow)
        self.assertNotIn("anchore/sbom-action@", workflow)
        uv_pin = (ROOT / "images/yueops-ci-toolchain/uv.sha256").read_text().strip()
        self.assertRegex(uv_pin, r"^[0-9a-f]{64}$")
        self.assertIn("images/yueops-ci-toolchain/uv.sha256", (ROOT / "scripts/install-verified-uv.sh").read_text())


class WorkflowPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")
        self.code = uncomment(self.text)

    def test_report_only_hosted_shape(self) -> None:
        self.assertIn("cron: '17 3 * * 1'", self.text)
        self.assertIn("workflow_dispatch:", self.text)
        self.assertIn("permissions:\n  contents: read", self.code)
        self.assertIn("runs-on: ubuntu-24.04", self.code)
        self.assertIn("FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true", self.code)
        self.assertIn("cancel-in-progress: false", self.code)
        self.assertIn("timeout-minutes: 90", self.code)
        self.assertNotIn("continue-on-error", self.code)
        self.assertNotIn("ubuntu-latest", self.text)
        for forbidden in (
            "gh pr",
            "peter-evans",
            "issues: write",
            "pull-requests: write",
            "packages: write",
            "id-token: write",
            "contents: write",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.code)

    def test_every_action_is_sha_pinned_and_checkouts_drop_credentials(self) -> None:
        uses = re.findall(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", self.text, re.MULTILINE)
        self.assertGreaterEqual(len(uses), 8)
        for action in uses:
            self.assertRegex(action, r"^[^@]+@[0-9a-f]{40}$")
        self.assertEqual(self.code.count("persist-credentials: false"), 7)
        self.assertIn(
            "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a", self.code
        )
        self.assertIn("if-no-files-found: error", self.code)

    def test_token_is_not_on_the_scan_or_public_checkout(self) -> None:
        steps = dict(named_steps(self.text))
        scan = steps["Scan sources and write the SBOM plus findings"]
        self.assertNotIn("secrets.", scan)
        self.assertNotIn("source_token", scan)
        self.assertNotIn("YUETO_CI_PAT", scan)
        public = steps["Checkout yuelink-ci"]
        self.assertNotIn("token:", public)
        self.assertNotIn("YUETO_CI_PAT", public)
        self.assertIn("cp -a .ci-policy sources/yueto-ci", steps["Materialize the yueto-ci policy checkout"])
        private = steps["Checkout yueops"]
        self.assertIn(
            "token: ${{ steps.source_token.outputs.token || secrets.YUETO_CI_PAT }}",
            private,
        )


class VerifiedScannerInstallerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.scripts = self.base / "scripts"
        self.scripts.mkdir()
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.github_path = self.base / "github_path"
        self.github_path.touch()
        self.calls = self.base / "calls"
        self.artifact = self.base / "download.bin"
        for name in (
            "ci-retry.sh",
            "lint-tool-versions.sh",
            "scanner-tool-versions.sh",
            "install-verified-govulncheck.sh",
            "install-verified-dart.sh",
            "install-verified-uv.sh",
        ):
            shutil.copyfile(ROOT / "scripts" / name, self.scripts / name)
        pin_dir = self.base / "images" / "yueops-ci-toolchain"
        pin_dir.mkdir(parents=True)
        shutil.copyfile(ROOT / "images/yueops-ci-toolchain/uv.sha256", pin_dir / "uv.sha256")
        self.env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("GIT_", "GH_", "GITHUB_", "GOVULNCHECK_", "DART_", "UV_", "SCANNER_"))
        }
        self.env.update(
            PATH=f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}",
            RUNNER_TEMP=str(self.base),
            GITHUB_PATH=str(self.github_path),
            CALLS=str(self.calls),
            DOWNLOAD=str(self.artifact),
        )
        checksum = shutil.which("gsha256sum") or shutil.which("sha256sum")
        self.assertIsNotNone(checksum, "GNU checksum tool is required for installer fixtures")
        (self.bin / "sha256sum").symlink_to(str(checksum))
        (self.bin / "python3").symlink_to(sys.executable)
        self.shim("uname", 'case "$1" in -s) echo Linux ;; -m) echo x86_64 ;; esac\n')
        self.shim("sleep", ":\n")
        self.shim(
            "curl",
            textwrap.dedent(
                """
                printf 'curl %s\\n' "$*" >> "$CALLS"
                [ "${DOWNLOAD_FAIL:-0}" = 0 ] || exit 22
                while [ "$#" -gt 0 ]; do
                  if [ "$1" = --output ]; then cp "$DOWNLOAD" "$2"; exit; fi
                  shift
                done
                exit 64
                """
            ).lstrip(),
        )

    def shim(self, name: str, body: str) -> None:
        path = self.bin / name
        path.write_text("#!/bin/bash\nset -eu\n" + body)
        path.chmod(0o755)

    def replace_pin(self, path: Path, name: str, value: str) -> None:
        lines = [
            f"readonly {name}='{value}'" if line.startswith(f"readonly {name}=") else line
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def run_installer(self, name: str, **extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [BASH, str(self.scripts / name)],
            cwd=self.base,
            env=self.env | extra,
            text=True,
            capture_output=True,
            timeout=20,
        )

    def write_govulncheck_zip(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            version = "v1.8.0"
            archive.writestr(
                f"golang.org/x/vuln@{version}/go.mod",
                "module golang.org/x/vuln\n\ngo 1.22\n",
            )
            archive.writestr(
                f"golang.org/x/vuln@{version}/cmd/govulncheck/main.go",
                "package main\nfunc main() {}\n",
            )
        self.artifact.write_bytes(buffer.getvalue())
        self.replace_pin(
            self.scripts / "lint-tool-versions.sh",
            "GOVULNCHECK_ZIP_SHA256",
            hashlib.sha256(self.artifact.read_bytes()).hexdigest(),
        )
        self.shim(
            "go",
            textwrap.dedent(
                """
                printf 'go %s\\n' "$*" >> "$CALLS"
                [ "$1" = install ] || exit 97
                mkdir -p "${GOBIN:?}"
                printf '#!/bin/bash\\necho govulncheck version v1.8.0\\n' > "$GOBIN/govulncheck"
                chmod +x "$GOBIN/govulncheck"
                """
            ).lstrip(),
        )

    def write_dart_zip(self, version: str = "3.13.7") -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(
                "dart-sdk/bin/dart",
                f"#!/bin/bash\necho 'Dart SDK version: {version}'\n",
            )
        self.artifact.write_bytes(buffer.getvalue())
        self.replace_pin(
            self.scripts / "scanner-tool-versions.sh",
            "DART_SDK_SHA256",
            hashlib.sha256(self.artifact.read_bytes()).hexdigest(),
        )

    def write_uv_tar(self, version: str = "0.10.9") -> None:
        script = f"#!/bin/bash\necho uv {version}\n".encode()
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            info = tarfile.TarInfo("uv-x86_64-unknown-linux-gnu/uv")
            info.size = len(script)
            info.mode = 0o755
            archive.addfile(info, io.BytesIO(script))
        self.artifact.write_bytes(buffer.getvalue())
        (self.base / "images/yueops-ci-toolchain/uv.sha256").write_text(
            hashlib.sha256(self.artifact.read_bytes()).hexdigest() + "\n"
        )

    def test_govulncheck_zip_pin_is_load_bearing(self) -> None:
        self.write_govulncheck_zip()
        result = self.run_installer("install-verified-govulncheck.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("verified govulncheck v1.8.0", result.stdout)
        self.replace_pin(self.scripts / "lint-tool-versions.sh", "GOVULNCHECK_ZIP_SHA256", "0" * 64)
        self.github_path.write_text("")
        failed = self.run_installer("install-verified-govulncheck.sh")
        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual(self.github_path.read_text(), "")

    def test_dart_digest_mismatch_never_publishes_a_path(self) -> None:
        self.write_dart_zip()
        result = self.run_installer("install-verified-dart.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.replace_pin(self.scripts / "scanner-tool-versions.sh", "DART_SDK_SHA256", "0" * 64)
        self.github_path.write_text("")
        failed = self.run_installer("install-verified-dart.sh")
        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual(self.github_path.read_text(), "")

    def test_uv_digest_mismatch_never_publishes_a_path(self) -> None:
        self.write_uv_tar()
        result = self.run_installer("install-verified-uv.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        (self.base / "images/yueops-ci-toolchain/uv.sha256").write_text("0" * 64 + "\n")
        self.github_path.write_text("")
        failed = self.run_installer("install-verified-uv.sh")
        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual(self.github_path.read_text(), "")

    def test_environment_cannot_override_reviewed_govulncheck_digest(self) -> None:
        self.write_govulncheck_zip()
        result = self.run_installer(
            "install-verified-govulncheck.sh",
            GOVULNCHECK_ZIP_SHA256="0" * 64,
            GOVULNCHECK_VERSION="v0.0.1",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("verified govulncheck v1.8.0", result.stdout)

    def test_unreviewed_architecture_stops_before_download(self) -> None:
        self.shim("uname", 'case "$1" in -s) echo Linux ;; -m) echo aarch64 ;; esac\n')
        result = self.run_installer("install-verified-govulncheck.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.calls.exists())

    def test_download_failure_fails_closed(self) -> None:
        self.write_dart_zip()
        result = self.run_installer("install-verified-dart.sh", DOWNLOAD_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.github_path.read_text(), "")



if __name__ == "__main__":
    unittest.main()
