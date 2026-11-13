"""Trusted preparation controls with real disposable Git objects, no live API."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('allocation_prepare', ROOT / 'scripts/prepare_board_allocation.py')
assert SPEC and SPEC.loader
PREP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREP)


class AllocationPreparation(unittest.TestCase):
    def test_metadata_pagination_and_closed_identity(self):
        rows = [{'number': n, 'state': 'open', 'head': {'sha': 'b' * 40}} for n in range(1, 101)]
        with patch.object(PREP, 'api', side_effect=[{'sha': 'a' * 40}, rows, []]) as api:
            master, pulls = PREP.remote_snapshot({})
        self.assertEqual(master, 'a' * 40)
        self.assertEqual(len(pulls), 100)
        self.assertIn('page=2', api.call_args_list[-1].args[0])
        for bad in ([{'number': True, 'state': 'open', 'head': {'sha': 'a' * 40}}],
                    [{'number': 1, 'state': 'closed', 'head': {'sha': 'a' * 40}}],
                    [{'number': 1, 'state': 'open', 'head': {'sha': 'main'}}], rows[:1] * 2, {}):
            with self.subTest(bad=bad), patch.object(PREP, 'api', side_effect=[{'sha': 'a' * 40}, bad]):
                with self.assertRaises(PREP.PreparationError):
                    PREP.remote_snapshot({})
        pages = [[{'number': p * 100 + n, 'state': 'open', 'head': {'sha': 'b' * 40}}
                  for n in range(1, 101)] for p in range(5)]
        with patch.object(PREP, 'api', side_effect=[{'sha': 'a' * 40}, *pages]):
            with self.assertRaisesRegex(PREP.PreparationError, '500'):
                PREP.remote_snapshot({})

    def test_errors_do_not_disclose_remote_stderr(self):
        secret = 'credential-sentinel-not-for-logs'
        error = subprocess.CalledProcessError(1, ['gh'], stderr=secret)
        with patch.object(PREP.subprocess, 'run', side_effect=error):
            with self.assertRaises(PREP.PreparationError) as caught:
                PREP.execute(['gh'], {})
        self.assertNotIn(secret, str(caught.exception))

    def fixture(self, directory):
        repo = directory / 'upstream'
        repo.mkdir()
        env = {'PATH': os.environ['PATH'], 'HOME': str(directory),
               'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull}
        def git(*args):
            return subprocess.check_output(['git', '-C', str(repo), '-c', 'user.name=Fixture',
                '-c', 'user.email=fixture@example.invalid', '-c', 'commit.gpgsign=false', *args],
                env=env, text=True, stderr=subprocess.DEVNULL).strip()
        git('init', '-q', '--initial-branch=master')
        migrations = repo / 'internal/platform/db/migrations'
        migrations.mkdir(parents=True)
        (migrations / '00001_initial.sql').write_text('SELECT 1;\n')
        git('add', '.')
        git('commit', '-qm', 'master fixture')
        master = git('rev-parse', 'HEAD')
        git('checkout', '-qb', 'candidate')
        (migrations / '00002_next.sql').write_text('SELECT 2;\n')
        git('add', '.')
        git('commit', '-qm', 'candidate fixture')
        candidate = git('rev-parse', 'HEAD')
        git('update-ref', 'refs/pull/7/head', candidate)
        return repo, master, candidate, git

    def invoke(self, directory, mode='valid'):
        upstream, master, candidate, fixture_git = self.fixture(directory)
        pulls = [{'number': 7, 'head_sha': candidate}]
        snapshots = [(master, pulls), (master, pulls)]
        if mode == 'fetch-race':
            fixture_git('update-ref', 'refs/pull/7/head', master)
        elif mode == 'enumeration-race':
            snapshots[1] = (master, [])
        elif mode == 'missing-object':
            candidate = 'c' * 40
        elif mode == 'empty-migrations':
            fixture_git('rm', '-qr', 'internal')
            fixture_git('commit', '-qm', 'empty fixture')
            candidate = fixture_git('rev-parse', 'HEAD')
        original = PREP.execute
        calls = []
        def execute(command, env, *, data=None):
            calls.append((command, env.copy()))
            self.assertNotIn('GIT_DIR', env)
            self.assertNotIn('GIT_CONFIG_COUNT', env)
            self.assertEqual(env['GIT_CONFIG_GLOBAL'], os.devnull)
            if mode == 'auth-persistence':
                (Path(env['HOME']) / 'unexpected-auth').write_text(env['GH_TOKEN'])
            if PREP.REMOTE in command:
                command = [str(upstream) if arg == PREP.REMOTE else arg for arg in command]
            return original(command, env, data=data)
        output = directory / 'prepared'
        with patch.dict(os.environ, {'GH_TOKEN': 'never-persist-this-token', 'GIT_DIR': '/bad',
                                     'GIT_CONFIG_COUNT': '999'}), \
                patch.object(PREP, 'remote_snapshot', side_effect=snapshots), \
                patch.object(PREP, 'execute', side_effect=execute):
            if mode == 'valid':
                receipt = PREP.prepare(candidate, output)
                self.assertEqual(receipt['candidate_sha'], candidate)
                self.assertEqual(receipt['master_sha'], master)
                self.assertEqual(receipt['open_pull_requests'], pulls)
                path = output / 'allocation-receipt.json'
                self.assertEqual(json.loads(path.read_text()), receipt)
                self.assertEqual(path.stat().st_mode & 0o222, 0)
                self.assertEqual(fixture_git('rev-parse', 'HEAD'), candidate)
                self.assertFalse((output / 'auth-home').exists())
                for file in output.rglob('*'):
                    if file.is_file():
                        self.assertNotIn(b'never-persist-this-token', file.read_bytes())
                config = (output / 'source/.git/config').read_text()
                self.assertNotIn('credential', config)
                self.assertNotIn('extraheader', config)
                self.assertTrue(all(command[0] == 'git' for command, _ in calls))
            else:
                with self.assertRaises((PREP.PreparationError, OSError)):
                    PREP.prepare(candidate, output)
                self.assertFalse((output / 'allocation-receipt.json').exists())
                self.assertFalse((output / 'auth-home').exists())

    def test_real_objects_receipt_and_no_persisted_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            self.invoke(Path(directory))

    def test_races_missing_objects_and_empty_tree_never_publish_receipt(self):
        for mode in ('fetch-race', 'enumeration-race', 'missing-object', 'empty-migrations', 'auth-persistence'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                self.invoke(Path(directory), mode)

    def test_missing_credential_and_bad_candidate_do_not_create_output(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            output = Path(directory) / 'prepared'
            for candidate in ('main', 'a' * 40):
                with self.assertRaises(PREP.PreparationError):
                    PREP.prepare(candidate, output)
                self.assertFalse(output.exists())

    def test_receipt_write_and_permission_failure_leave_no_completed_receipt(self):
        for phase in ('write', 'permission'):
            failure = (patch.object(PREP.json, 'dump', side_effect=OSError('disk failure'))
                       if phase == 'write' else patch.object(Path, 'chmod', side_effect=OSError('mode failure')))
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory, failure:
                self.invoke(Path(directory), 'receipt-failure')

    def test_tree_with_missing_blob_is_not_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, _, candidate, fixture_git = self.fixture(Path(directory))
            blob = fixture_git('rev-parse', candidate + ':internal/platform/db/migrations/00002_next.sql')
            (repo / '.git/objects' / blob[:2] / blob[2:]).unlink()
            env = {'PATH': os.environ['PATH'], 'HOME': directory, 'GIT_CONFIG_GLOBAL': os.devnull,
                   'GIT_CONFIG_NOSYSTEM': '1', 'GIT_NO_LAZY_FETCH': '1'}
            with self.assertRaisesRegex(PREP.PreparationError, 'missing prepared migration blob'):
                PREP.object_closure(repo, env, candidate)


if __name__ == '__main__':
    unittest.main()
