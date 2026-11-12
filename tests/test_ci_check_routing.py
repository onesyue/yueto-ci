"""The public CLI routes repositories before resolving Ops-only context."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RepositoryRouting(unittest.TestCase):
    def test_board_node_remote_without_ops_context(self):
        for repo in ('yueboard', 'yue-node'):
            with self.subTest(repo=repo), tempfile.TemporaryDirectory() as directory:
                temp = Path(directory)
                scripts = temp / 'scripts'
                scripts.mkdir()
                (scripts / 'ci-check.sh').write_text((ROOT / 'scripts/ci-check.sh').read_text())
                # Stub only the final remote boundary. Resolving Ops context would
                # attempt the absent ci_check_board.py and fail this real shell run.
                (scripts / 'ci_check_remote.py').write_text(
                    'import json, sys\nprint(json.dumps(sys.argv[1:]))\n')
                subprocess.run(['git', 'init', '-q', '-b', 'fixture', str(temp)], check=True)
                subprocess.run(['git', '-C', str(temp), 'add', 'scripts'], check=True)
                subprocess.run(['git', '-C', str(temp), '-c', 'user.name=fixture', '-c',
                                'user.email=fixture@example.invalid', '-c', 'commit.gpgsign=false',
                                'commit', '-qm', 'fixture'], check=True)
                env = dict(os.environ, CI_CHECK_OUTPUT=str(temp / 'output'), YUETO_ROOT=str(temp / 'absent'))
                env.pop('CI_CHECK_MIGRATION_BASE', None)
                result = subprocess.run(['bash', str(scripts / 'ci-check.sh'), repo, 'c'*40],
                                        env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                args = json.loads(result.stdout)
                fields = dict(zip(args[::2], args[1::2]))
                self.assertEqual(fields['--repo'], repo)
                self.assertEqual(fields['--source'], 'c'*40)
                self.assertEqual(fields['--base'], '')
                self.assertEqual(fields['--board'], '')
                self.assertEqual(fields['--branch'], 'fixture')

    def test_unsupported_local_and_ops_options_rejected_before_network(self):
        for repo in ('yueboard', 'yue-node'):
            for options in (['--local'], ['--board-ref', 'b'*40], ['--prepare-only'], ['--prepared', 'receipt']):
                with self.subTest(repo=repo, options=options):
                    result = subprocess.run(['bash', str(ROOT / 'scripts/ci-check.sh'), repo, 'c'*40, *options],
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn('local validation is not implemented' if '--local' in options else
                                  'options apply only to yueops', result.stderr)

    def test_non_ops_migration_base_rejected(self):
        result = subprocess.run(
            ['bash', str(ROOT / 'scripts/ci-check.sh'), 'yueboard', 'c'*40],
            env=dict(os.environ, CI_CHECK_MIGRATION_BASE='d'*40), capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('options apply only to yueops', result.stderr)
