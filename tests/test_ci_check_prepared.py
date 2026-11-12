"""Real Git controls for the clone-only / credential-free phase boundary."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('prepared', ROOT / 'scripts/ci_check_prepared.py')
PREPARED = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREPARED)


class PreparedClones(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        self.checkouts = self.output / 'checkouts.abc123'
        self.checkouts.mkdir()
        self.env = os.environ | {'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1',
                                 'GIT_AUTHOR_NAME': 'Fixture', 'GIT_AUTHOR_EMAIL': 'f@example.invalid',
                                 'GIT_COMMITTER_NAME': 'Fixture', 'GIT_COMMITTER_EMAIL': 'f@example.invalid'}
        self.identities = {'base': 'b' * 40}
        for name, repo in [('source', 'yueops'), ('board', 'yueboard'), ('policy', 'yueto-ci')]:
            path = self.checkouts / name
            path.mkdir()
            self.git(path, 'init', '-q', '-b', 'master')
            (path / 'file').write_text('fixture')
            self.git(path, 'add', '.')
            self.git(path, '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture')
            self.identities[name] = self.git(path, 'rev-parse', 'HEAD')
            self.git(path, 'remote', 'add', 'origin', f'https://github.com/onesyue/{repo}.git')
            self.git(path, 'update-ref', 'refs/remotes/origin/master', self.identities[name])
        self.receipt = self.output / 'prepared.json'
        with patch.dict(os.environ, self.env, clear=True):
            PREPARED.prepare(self.receipt, self.checkouts, self.identities)

    def git(self, path, *args):
        return subprocess.check_output(['git', '-C', str(path), *args], env=self.env,
                                       stderr=subprocess.PIPE, text=True).strip()

    def claim(self, identities=None):
        with patch.dict(os.environ, self.env, clear=True):
            return PREPARED.claim(self.receipt, self.output, identities or self.identities)

    def test_exact_clean_clones_have_only_one_consumer(self):
        self.assertEqual(self.claim(), self.checkouts.resolve())
        with self.assertRaises(FileExistsError):
            self.claim()
        self.assertTrue((self.checkouts / 'source/file').is_file())

    def test_wrong_identity_dirty_checkout_and_credential_config_reject(self):
        with self.assertRaisesRegex(ValueError, 'identities'):
            self.claim(self.identities | {'board': 'a' * 40})
        target = self.checkouts / 'board/file'
        target.write_text('dirty')
        with self.assertRaisesRegex(ValueError, 'dirty'):
            self.claim()
        self.git(self.checkouts / 'board', 'checkout', '--', 'file')
        self.git(self.checkouts / 'source', 'config', 'http.https://github.com/.extraheader', 'fixture')
        with self.assertRaisesRegex(ValueError, 'credential'):
            self.claim()

    def test_foreign_path_or_modified_branch_authority_cannot_be_claimed(self):
        value = json.loads(self.receipt.read_text())
        self.receipt.write_text(json.dumps(value | {'checkouts': str(self.output.parent)}))
        with self.assertRaisesRegex(ValueError, 'owned output'):
            self.claim()
        self.receipt.write_text(json.dumps(value))
        path = self.checkouts / 'source'
        (path / 'file').write_text('new default branch')
        self.git(path, 'add', 'file')
        self.git(path, '-c', 'commit.gpgsign=false', 'commit', '-qm', 'new')
        self.git(path, 'update-ref', 'refs/remotes/origin/master', 'HEAD')
        self.git(path, 'checkout', '--detach', self.identities['source'])
        with self.assertRaisesRegex(ValueError, 'default branch'):
            self.claim()

    def test_real_cli_prepare_does_not_execute_planner_and_consume_has_no_token(self):
        policy = self.checkouts / 'policy'
        scripts = policy / 'scripts'
        scripts.mkdir()
        for name in ('ci-check.sh', 'ci_check_prepared.py'):
            shutil.copyfile(ROOT / 'scripts' / name, scripts / name)
        sentinel = self.output / 'planner-ran'
        (scripts / 'pytest-shards.py').write_text(
            'import os,pathlib\nassert not os.environ.get("GH_TOKEN")\n'
            f'pathlib.Path({str(sentinel)!r}).write_text("credential-free")\nprint("{{}}")\n')
        (scripts / 'ci_check_local.py').write_text('import os\nassert not os.environ.get("GH_TOKEN")\n')
        self.git(policy, 'add', 'scripts')
        self.git(policy, '-c', 'commit.gpgsign=false', 'commit', '-qm', 'controlled CLI consumers')
        config = self.output / 'gitconfig'
        for name, repo in [('source', 'yueops'), ('board', 'yueboard'), ('policy', 'yueto-ci')]:
            subprocess.run(['git', 'config', '--file', str(config),
                            f'url.{(self.checkouts / name).as_uri()}.insteadOf',
                            f'https://github.com/onesyue/{repo}.git'], check=True)
        output = self.output / 'execution'
        binpath = self.output / 'bin'
        binpath.mkdir()
        docker = binpath / 'docker'
        docker.write_text('#!/bin/sh\nexit 99\n')
        docker.chmod(0o755)
        env = self.env | {'GH_TOKEN': 'fixture-token', 'GIT_CONFIG_GLOBAL': str(config),
                          'CI_CHECK_OUTPUT': str(output), 'CI_CHECK_MIGRATION_BASE': self.identities['source'],
                          'YUEOPS_CHECKOUT': str(self.checkouts / 'source'),
                          'YUEBOARD_CHECKOUT': str(self.checkouts / 'board'),
                          'PATH': str(binpath) + os.pathsep + self.env['PATH']}
        args = ['bash', str(scripts / 'ci-check.sh'), 'yueops', self.identities['source'],
                '--local', '--board-ref', self.identities['board']]
        prepared = subprocess.run([*args, '--prepare-only'], env=env, capture_output=True, text=True)
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        self.assertFalse(sentinel.exists())
        consumed_args = [*args, '--prepared', str(output / 'prepared.json')]
        refused = subprocess.run(consumed_args, env=env, capture_output=True, text=True)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn('credential environment', refused.stderr)
        self.assertFalse(sentinel.exists())
        del env['GH_TOKEN']
        env['GIT_CONFIG_GLOBAL'] = '/dev/null'
        consumed = subprocess.run(consumed_args, env=env, capture_output=True, text=True)
        self.assertEqual(consumed.returncode, 0, consumed.stderr)
        self.assertEqual(sentinel.read_text(), 'credential-free')
        self.assertEqual(list(output.glob('checkouts.*')), [])
