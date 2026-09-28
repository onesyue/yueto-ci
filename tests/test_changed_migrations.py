"""Real Git histories exercise the same selector used by public validation."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SELECTOR = ROOT / "scripts/changed-migrations.py"
SQL = "telegram-bot/yue/migrations/223_fixture.sql"


class ChangedMigrationsTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.repo = Path(temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.write("README", "baseline")
        self.base = self.commit()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], text=True).strip()

    def write(self, path, body):
        file = self.repo / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(body)

    def commit(self):
        self.git("add", "--all")  # Disposable fixture repository only.
        self.git("commit", "-qm", "fixture", "--no-verify")
        return self.git("rev-parse", "HEAD")

    def select(self, base=None):
        return subprocess.run([sys.executable, str(SELECTOR), "--repo", str(self.repo),
                               "--base", self.base if base is None else base],
                              capture_output=True, timeout=10)

    def test_whole_batch_with_final_non_sql_commit(self):
        self.write(SQL, "SELECT 1;\n")
        self.commit()
        self.write("README", "later non-SQL commit")
        self.commit()
        result = self.select()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, SQL.encode() + b"\0")
        self.assertEqual(self.select(self.git("rev-parse", "HEAD^")).stdout, b"")

    def test_invalid_missing_or_non_ancestor_base_fails_without_paths(self):
        self.git("checkout", "-qb", "side")
        self.write("side", "side")
        side = self.commit()
        self.git("checkout", "-q", "--detach", self.base)
        self.write("main", "main")
        self.commit()
        for base in ("", "HEAD^", self.base[:12], "f" * 40, side):
            with self.subTest(base=base):
                result = self.select(base)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b"")

    def test_deleted_renamed_and_missing_checkout_sql_are_not_green(self):
        self.write(SQL, "SELECT 1;\n")
        baseline = self.commit()
        (self.repo / SQL).unlink()
        result = self.select()
        self.assertNotEqual(result.returncode, 0)  # missing checkout file
        self.write(SQL + ".renamed.sql", "SELECT 1;\n")
        self.commit()
        result = self.select(baseline)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assertIn(b"deletion", result.stderr)

    def test_zero_changes_is_only_green_with_verified_base(self):
        result = self.select()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b"0 changed", result.stderr)

    def test_workflow_invokes_selector_before_reading_output(self):
        workflow = (ROOT / ".github/workflows/build.yml").read_text()
        sql = workflow.split("- name: Lint changed YueOps SQL migrations", 1)[1].split("\n  build:", 1)[0]
        self.assertIn('python3 .ci-policy/scripts/changed-migrations.py --base "$MIGRATION_BASE" > "$migration_list"', sql)
        self.assertIn("mapfile -d '' -t migrations <", sql)
        self.assertNotIn("HEAD^", sql)
        self.assertNotIn("git ls-tree", sql)
        self.assertIn('MIGRATION_BASE: ${{ github.event.inputs.migration_base', sql)
