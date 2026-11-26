import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts.derive_contract_facts import MIGRATION_DIRECTORY, board_contract_ref, migration_head


class CandidateMigrationFacts(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.board = Path(directory.name)
        self.migrations = self.board / MIGRATION_DIRECTORY
        self.migrations.mkdir(parents=True)
        self.git("init", "--quiet")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.test")

    def git(self, *args):
        return subprocess.check_output(
            ["git", "-C", str(self.board), *args], text=True,
            env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull},
        ).strip()

    def commit(self):
        self.git("add", "--", MIGRATION_DIRECTORY)
        self.git("commit", "--quiet", "-m", "Board fixture")
        return self.git("rev-parse", "HEAD")

    def test_head_follows_the_named_commit(self):
        (self.migrations / "00161_first.sql").write_text("SELECT 1;\n")
        old = self.commit()
        (self.migrations / "00162_next.sql").write_text("SELECT 2;\n")
        (self.migrations / "99999_link.sql").symlink_to("00161_first.sql")
        nested = self.migrations / "88888_directory.sql"
        nested.mkdir()
        (nested / "99999_nested.sql").touch()
        new = self.commit()
        (self.migrations / "99999_uncommitted.sql").touch()

        self.assertEqual(board_contract_ref(self.board, old), old)
        self.assertEqual(migration_head(self.board, old), 161)
        self.assertEqual(migration_head(self.board, new), 162)

    def test_requires_an_exact_commit_and_a_migration_file(self):
        (self.migrations / "README.md").touch()
        commit = self.commit()
        for ref in ("master", "HEAD", commit[:12], commit + "\n"):
            with self.subTest(ref=ref), self.assertRaisesRegex(ValueError, "board_contract_ref_invalid"):
                migration_head(self.board, ref)
        for ref in ("f" * 40, self.git("rev-parse", "HEAD^{tree}")):
            with self.subTest(ref=ref), self.assertRaisesRegex(ValueError, "board_commit_missing"):
                migration_head(self.board, ref)
        with self.assertRaisesRegex(ValueError, "board_migration_head_missing"):
            migration_head(self.board, commit)
