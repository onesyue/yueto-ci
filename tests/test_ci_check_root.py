"""Root executor boundary controls; real Git, Bash, ShellCheck and pytest."""
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
CONTROLLER = importlib.import_module('ci_check_root')
WORKER = importlib.import_module('ci_check_root_worker')


class RootExecutor(unittest.TestCase):
    def test_isolation_no_credentials_no_network_no_socket(self):
        command = CONTROLLER.isolated_command(Path('/source'), Path('/policy'), Path('/output'), 'parse')
        self.assertEqual(command[command.index('--network') + 1], 'none')
        self.assertEqual(command[command.index('--user') + 1], 'runner')
        self.assertIn('no-new-privileges', command)
        self.assertIn('ALL', command)
        self.assertNotIn('--privileged', command)
        self.assertNotIn('-e', command)
        self.assertNotIn('docker.sock', ' '.join(command))
        self.assertEqual(command.count('--mount'), 3)
        self.assertIn('type=bind,src=/source,dst=/inputs,readonly', command)
        with patch.dict(os.environ, {'GH_TOKEN': 'secret', 'GIT_ASKPASS': '/auth/askpass'}):
            env = WORKER.environment()
        self.assertNotIn('GH_TOKEN', env)
        self.assertNotIn('GIT_ASKPASS', env)
        self.assertEqual(env['GIT_CONFIG_GLOBAL'], '/dev/null')

    def test_reference_output_closed_schema(self):
        good = {repo: 'a' * 40 for repo in CONTROLLER.COMPONENTS}
        self.assertEqual(CONTROLLER.references(good), good)
        for value in ({}, good | {'other': 'a' * 40}, good | {'yueops': 'main'},
                      good | {'yueops': ['a' * 40]}, ['yueops'], good | {'../../auth': 'a' * 40}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                CONTROLLER.references(value)

    def test_credentials_rejected_before_snapshot_or_container(self):
        for key in ('GH_TOKEN', 'GITHUB_TOKEN', 'GH_ENTERPRISE_TOKEN', 'GITHUB_ENTERPRISE_TOKEN',
                    'GIT_ASKPASS', 'SSH_AUTH_SOCK'):
            with self.subTest(key=key), patch.dict(os.environ, {key: 'secret'}), \
                    patch.object(CONTROLLER, 'snapshot') as snapshot, self.assertRaises(ValueError):
                CONTROLLER.run('a' * 40, Path('/unused'), Path('/unused'))
            snapshot.assert_not_called()

    def test_unsigned_source_stops_before_native_parser(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'output'
            with patch.dict(os.environ, {'PATH': os.environ['PATH']}, clear=True), \
                    patch.object(CONTROLLER, 'snapshot'), \
                    patch.object(CONTROLLER.subprocess, 'check_output', side_effect=['a' * 40, '']), \
                    patch.object(CONTROLLER, 'verify_signed_commit', side_effect=ValueError('unsigned')), \
                    patch.object(CONTROLLER, 'execute_container') as container:
                with self.assertRaisesRegex(ValueError, 'unsigned'):
                    CONTROLLER.run('a' * 40, Path(directory), output)
                container.assert_not_called()
                self.assertFalse(json.loads((output / 'result.json').read_text())['complete'])

    def test_snapshot_excludes_ignored_auth_and_uses_exact_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            source.mkdir()
            subprocess.run(['git', 'init', '-q', str(source)], check=True)
            (source / '.gitignore').write_text('auth\n')
            (source / 'tracked').write_text('one')
            (source / 'executable').write_text('#!/bin/sh\nexit 0\n')
            (source / 'executable').chmod(0o755)
            subprocess.run(['git', '-C', str(source), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(source), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@invalid',
                            '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture'], check=True)
            sha = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
            (source / 'auth').write_text('secret')
            (source / 'tracked').write_text('dirty')
            subprocess.run(['git', '-C', str(source), 'config', 'http.https://github.com/.extraheader', 'secret'], check=True)
            mask = os.umask(0o077)
            try:
                CONTROLLER.snapshot(source, 'yueto', sha, root / 'snapshot')
            finally:
                os.umask(mask)
            self.assertEqual((root / 'snapshot').stat().st_mode & 0o777, 0o755)
            self.assertEqual((root / 'snapshot/.git/config').stat().st_mode & 0o444, 0o444)
            self.assertEqual((root / 'snapshot/executable').stat().st_mode & 0o111, 0o111)
            self.assertEqual((root / 'snapshot/tracked').stat().st_mode & 0o111, 0)
            self.assertEqual((root / 'snapshot/tracked').read_text(), 'one')
            self.assertFalse((root / 'snapshot/auth').exists())
            config = (root / 'snapshot/.git/config').read_text()
            self.assertNotIn('secret', config)
            self.assertIn('https://github.com/onesyue/yueto.git', config)

    def test_native_parser_uses_verified_snapshot_and_trusted_keyring(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'out'
            output.mkdir()
            (root / 'yueto/scripts').mkdir(parents=True)
            (root / 'yueto/scripts/release-yaml.py').write_text('''
import os
assert os.environ['YUETO_RELEASE_SIGNER_KEYRING'].endswith('/policy/yueops-owner.gpg')
assert 'GH_TOKEN' not in os.environ
verified = False
def verified_desired():
    global verified
    verified = True
    return {}, ('bytes', 'signature')
def desired_revision(record, repo, root):
    assert verified
    return 'a' * 40
def assert_desired_unchanged(snapshot):
    assert snapshot == ('bytes', 'signature')
''')
            with patch.dict(os.environ, {'GH_TOKEN': 'secret'}):
                WORKER.parse(root, root, output)
            self.assertEqual(set(json.loads((output / 'references.json').read_text())), CONTROLLER.COMPONENTS)

    def fixture(self, root, test='def test_ok():\n    assert True\n', shell='#!/bin/bash\nprintf "ok\\n"\n'):
        inputs, output = root / 'inputs', root / 'output'
        inputs.mkdir()
        output.mkdir()
        refs = {repo: 'a' * 40 for repo in (*sorted(CONTROLLER.COMPONENTS), 'yueto-ci')}
        (inputs / 'context.json').write_text(json.dumps({'refs': refs}))
        for repo in ('yueto', *refs):
            (inputs / repo).mkdir()
        source = inputs / 'yueto'
        (source / 'scripts').mkdir()
        (source / '.claude/hooks').mkdir(parents=True)
        (source / 'scripts/test-one.py').write_text(test)
        (source / 'scripts/check.sh').write_text(shell)
        (source / 'scripts/gate-root-selftests.sh').write_text('''#!/bin/bash
set -euo pipefail
py='' junit='' ops='' ws=''
while (( $# )); do
  case "$1" in
    --python) py=$2 ;;
    --junit) junit=$2 ;;
    --ops-repo) ops=$2 ;;
    --workspace) ws=$2 ;;
    --ops-sha|--with) : ;;
    *) exit 91 ;;
  esac
  shift 2
done
[ -d "$ops" ] && [ -d "$ws/yueto-ci" ]
"$py" -m pytest -q -p no:cacheprovider --junitxml="$junit" scripts/test-*.py .claude/hooks
''')
        subprocess.run(['git', 'init', '-q', str(source)], check=True)
        subprocess.run(['git', '-C', str(source), 'add', '.'], check=True)
        return inputs, output

    def run_fixture(self, test='def test_ok():\n    assert True\n', shell='#!/bin/bash\nprintf "ok\\n"\n'):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs, output = self.fixture(root, test, shell)
            env = WORKER.environment() | {'PATH': os.environ['PATH'], 'HOME': str(root / 'home')}
            with patch.object(WORKER, 'environment', return_value=env):
                code = WORKER.execute(inputs, output)
            return code, json.loads((output / 'result.json').read_text())

    def test_real_native_entry_success_and_failure(self):
        for test, code, complete in (
                ('def test_ok():\n    assert True\n', 0, True),
                ('def test_bad():\n    assert False\n', 1, True),
                ('import pytest\n@pytest.mark.skip(reason="dependency")\ndef test_skip(): pass\n', 2, False),
                ('import missing_root_dependency\n', 2, False),
                ('# no tests\n', 2, False)):
            with self.subTest(test=test):
                actual, result = self.run_fixture(test)
                self.assertEqual(actual, code)
                self.assertEqual(result['complete'], complete)
                self.assertEqual(result['exit_code'], code)
                self.assertEqual(result['phases']['bash-n'], 0)
                self.assertEqual(result['phases']['shellcheck'], 0)

    def test_real_shell_failures_stop_native_gate(self):
        for shell, phase in (('#!/bin/bash\nif\n', 'bash-n'),
                             ('#!/bin/bash\necho $unquoted\n', 'shellcheck')):
            with self.subTest(phase=phase):
                code, result = self.run_fixture(shell=shell)
                self.assertNotEqual(code, 0)
                self.assertNotIn('native-selftests', result['phases'])
                self.assertNotEqual(result['phases'][phase], 0)
                self.assertFalse(result['complete'])

    def test_missing_tool_and_symbolic_report_are_incomplete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs, output = self.fixture(root)
            with patch.object(WORKER.shutil, 'which', return_value=None):
                self.assertEqual(WORKER.execute(inputs, output), 2)
            self.assertFalse(json.loads((output / 'result.json').read_text())['complete'])
            (root / 'real.xml').write_text('<testsuite><testcase name="a"/></testsuite>')
            (root / 'link.xml').symlink_to(root / 'real.xml')
            self.assertFalse(WORKER.junit_complete(root / 'link.xml'))
            with self.assertRaises(ValueError):
                CONTROLLER.read_json(root / 'link.xml')


if __name__ == '__main__':
    unittest.main()
