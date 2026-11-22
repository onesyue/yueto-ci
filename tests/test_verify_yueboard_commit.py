"""Computed YueBoard checks at the commit under build. The reviewed pin is not an input."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/verify-yueboard-commit.py"
PIN = "c" * 40


class VerifyYueBoardCommit(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "board"
        self.bin = self.root / "bin"
        self.log = self.root / "calls"
        self.source.mkdir()
        self.bin.mkdir()
        stub = self.bin / "stub"
        stub.write_text(
            "#!" + sys.executable + "\n"
            "import json, os, sys\n"
            "from pathlib import Path\n"
            "with open(os.environ['CALL_LOG'], 'a') as handle:\n"
            "    handle.write(json.dumps({'name': Path(sys.argv[0]).name, 'args': sys.argv[1:]}) + '\\n')\n"
            "raise SystemExit(0)\n"
        )
        stub.chmod(0o755)
        (self.bin / "buf").symlink_to(stub)
        (self.bin / "go").symlink_to(stub)
        self.write_tree(10, 10)
        self.baseline = self.commit("baseline")
        self.write_tree(11, 11)
        self.head = self.commit("candidate")
        (self.source / "native-node-contract.json").write_text(
            json.dumps({"yueboard_contract_pin": PIN}) + "\n"
        )

    def write_tree(self, floor, compat):
        (self.source / "go.mod").write_text("module fixture\n")
        (self.source / "schema-floor.txt").write_text(f"{floor}\n")
        (self.source / "schema-compat.txt").write_text(f"{compat}\n")
        proto = self.source / "proto/yuenode/v1"
        proto.mkdir(parents=True, exist_ok=True)
        (proto / "yuenode.proto").write_text('syntax = "proto3";\n')
        (self.source / "proto/breaking-baseline.binpb").write_bytes(b"baseline")
        gate = self.source / "scripts/ci/proto-gate.sh"
        gate.parent.mkdir(parents=True, exist_ok=True)
        gate.write_text("#!/usr/bin/env bash\nset -euo pipefail\necho TODAY-PROTO\nbuf lint\n")
        openapi = self.source / "contracts/openapi"
        openapi.mkdir(parents=True, exist_ok=True)
        (openapi / "yueboard-api.v1.json").write_text('{"openapi":"3.0.3"}\n')
        (self.source / "cmd/export-openapi").mkdir(parents=True, exist_ok=True)

    def commit(self, message):
        subprocess.run(["git", "-C", str(self.source), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(self.source), "add", "-A"], check=True)
        subprocess.run(
            [
                "git", "-C", str(self.source),
                "-c", "user.name=fixture",
                "-c", "user.email=fixture@example.invalid",
                "-c", "commit.gpgsign=false",
                "commit", "-qm", message,
            ],
            check=True,
        )
        return subprocess.check_output(
            ["git", "-C", str(self.source), "rev-parse", "HEAD"], text=True
        ).strip()

    def environment(self, **extra):
        env = dict(os.environ)
        env["PATH"] = str(self.bin) + os.pathsep + env.get("PATH", "")
        env["CALL_LOG"] = str(self.log)
        env.pop("YUEBOARD_BASELINE_REV", None)
        env.pop("YUEBOARD_RELEASE_LEDGER", None)
        env.update(extra)
        return env

    def run_check(self, **extra):
        self.log.unlink(missing_ok=True)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--source", str(self.source)],
            env=self.environment(**extra),
            capture_output=True,
            text=True,
            check=False,
        )
        rows = [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
        return result, rows

    def test_script_does_not_read_the_reviewed_pin(self):
        code = SCRIPT.read_text().split('"""', 2)[2]
        self.assertNotIn("yueboard_contract_pin", code)

    def test_commit_different_from_pin_passes_when_computed_checks_pass(self):
        self.assertNotEqual(self.head, PIN)
        result, rows = self.run_check(YUEBOARD_BASELINE_REV=self.baseline)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"schema floor 11 is monotonic against {self.baseline} floor 10", result.stdout)
        self.assertIn("buf breaking against previously promoted revision", result.stdout)
        self.assertIn("OpenAPI snapshot fresh", result.stdout)
        self.assertNotIn("TODAY-PROTO", result.stdout)
        self.assertEqual(rows[0]["name"], "buf")
        self.assertEqual(rows[0]["args"][0], "breaking")
        self.assertTrue(Path(rows[0]["args"][1]).resolve().is_relative_to(self.source.resolve()))
        self.assertTrue(rows[0]["args"][1].endswith("/proto"))
        self.assertIn("--against", rows[0]["args"])
        self.assertNotIn("lint", rows[0]["args"])
        self.assertEqual(rows[1]["args"], ["run", "./cmd/export-openapi", "--check"])

    def test_floor_regression_fails_before_proto(self):
        (self.source / "schema-floor.txt").write_text("9\n")
        (self.source / "schema-compat.txt").write_text("9\n")
        result, rows = self.run_check(YUEBOARD_BASELINE_REV=self.baseline)
        self.assertEqual(result.returncode, 1)
        self.assertIn("schema floor regression: 9 < previous promoted floor 10", result.stderr)
        self.assertEqual(rows, [])

    def test_missing_baseline_runs_todays_checks(self):
        result, rows = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("baseline-relative checks skipped", result.stderr)
        self.assertIn("today's checks still run", result.stderr)
        self.assertIn("TODAY-PROTO", result.stdout)
        self.assertIn("today proto check: scripts/ci/proto-gate.sh", result.stdout)
        self.assertIn("OpenAPI snapshot fresh", result.stdout)
        self.assertEqual([row["name"] for row in rows], ["buf", "go"])
        self.assertEqual(rows[0]["args"], ["lint"])
        self.assertNotIn("breaking", rows[0]["args"])

    def test_ledger_revision_is_the_baseline_and_a_bad_ledger_fails_closed(self):
        (self.source / "schema-floor.txt").write_text("9\n")
        (self.source / "schema-compat.txt").write_text("9\n")
        ledger = self.root / "release.yaml"
        ledger.write_text(
            "components:\n"
            "  yueboard:\n"
            f"    revision: {self.baseline}\n"
        )
        result, rows = self.run_check(YUEBOARD_RELEASE_LEDGER=str(ledger))
        self.assertEqual(result.returncode, 1)
        self.assertIn("schema floor regression: 9 < previous promoted floor 10", result.stderr)
        self.assertEqual(rows, [])

        desired = self.root / "desired.yaml"
        desired.write_text(
            "desired:\n"
            "  production:\n"
            "    yueboard:\n"
            f"      revision: {self.baseline}\n"
        )
        result, _rows = self.run_check(YUEBOARD_RELEASE_LEDGER=str(desired))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("schema floor regression", result.stderr)

        ledger.write_text("components:\n  other:\n    revision: not-a-revision\n")
        (self.source / "schema-floor.txt").write_text("11\n")
        (self.source / "schema-compat.txt").write_text("11\n")
        result, rows = self.run_check(YUEBOARD_RELEASE_LEDGER=str(ledger))
        self.assertEqual(result.returncode, 1)
        self.assertIn("release ledger has no yueboard revision", result.stderr)
        self.assertEqual(rows, [])

    def test_compat_above_floor_fails_without_a_baseline(self):
        (self.source / "schema-floor.txt").write_text("10\n")
        (self.source / "schema-compat.txt").write_text("11\n")
        result, rows = self.run_check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("schema-compat.txt 11 exceeds schema floor 10", result.stderr)
        self.assertEqual(rows, [])

    def test_explicit_baseline_must_be_forty_hex(self):
        result, rows = self.run_check(YUEBOARD_BASELINE_REV="main")
        self.assertEqual(result.returncode, 1)
        self.assertIn("YUEBOARD_BASELINE_REV must be an exact lowercase 40-hex commit", result.stderr)
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
