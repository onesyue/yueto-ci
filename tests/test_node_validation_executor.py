"""Execute the shared Node profile shell with offline argv-recording tools."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
EXECUTOR = ROOT / 'scripts/node-validation.sh'
TAGS = 'with_quic with_utls with_wireguard with_clash_api'


class NodeExecutorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.source = self.home / 'source with spaces'
        self.source.mkdir()
        (self.source / 'go.mod').write_text('module fixture\n')
        (self.source / 'vendor').mkdir()
        (self.source / 'vendor/modules.txt').write_text('# fixture\n')
        (self.source / 'scripts').mkdir()
        self.bin = self.home / 'bin'
        self.bin.mkdir()
        self.log = self.home / 'commands.jsonl'
        tool = '''#!PYTHON
import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
record = {'name': name, 'args': args, 'cwd': os.getcwd(),
          'profile': os.environ.get('NODE_PROFILE'), 'goflags': os.environ.get('GOFLAGS'),
          'cgo': os.environ.get('CGO_ENABLED'), 'build_profile': os.environ.get('BUILD_PROFILE')}
with open(os.environ['COMMAND_LOG'], 'a') as stream:
    stream.write(json.dumps(record) + '\\n')
key = ' '.join([name] + args)
if key == os.environ.get('FAIL_AT'):
    sys.exit(37)
if name == 'go' and args == ['env', 'CGO_ENABLED']:
    print(os.environ.get('CGO_ENABLED', '0'))
'''.replace('PYTHON', sys.executable, 1)
        for name in ('go', 'make', 'test-vulnerabilities', 'scan-vulnerabilities'):
            target = self.bin / name
            target.write_text(tool)
            target.chmod(0o755)
        for script, name in [('test-check-vulnerabilities.sh', 'test-vulnerabilities'),
                             ('check-vulnerabilities.sh', 'scan-vulnerabilities')]:
            (self.source / 'scripts' / script).write_text(f'#!/bin/bash\nexec {name}\n')
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(('GIT_', 'GH_', 'GITHUB_', 'YUETO_', 'GO', 'BUILD_PROFILE'))}
        self.env.update(PATH=f'{self.bin}:/usr/bin:/bin', COMMAND_LOG=str(self.log),
                        CGO_ENABLED='1', GOFLAGS='-mod=vendor')

    def run_profile(self, profile: str = 'hy2', **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(['bash', str(EXECUTOR), profile, str(self.source)],
                              cwd=self.home, env=self.env | env, text=True,
                              capture_output=True, timeout=15)

    def records(self) -> list[dict]:
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def expected(self, profile: str) -> list[tuple[str, list[str]]]:
        race = ['test', '-race', '-count=1', '-timeout', '30m', '-tags', f'{TAGS} yue_profile_{profile}']
        subset = ['./internal/kernel/hysteria/compatobfs/'] if profile == 'hy2' else [
            '-run', 'Splice|VendoredVisionReality', './internal/kernel/xray/']
        return [('go', ['env', 'CGO_ENABLED']), ('make', ['check-profile-deps']),
                ('test-vulnerabilities', []), ('go', race + ['./...']), ('go', race + subset)] + (
                    [('make', ['build']), ('scan-vulnerabilities', [])] if profile == 'vless' else [])

    def test_profiles_exact_commands_environment_and_default_bundle(self) -> None:
        for profile in ('hy2', 'vless'):
            with self.subTest(profile=profile):
                self.log.unlink(missing_ok=True)
                result = self.run_profile(profile)
                self.assertEqual(result.returncode, 0, result.stderr)
                records = self.records()
                self.assertEqual([(r['name'], r['args']) for r in records], self.expected(profile))
                for record in records:
                    self.assertEqual(record['cwd'], str(self.source.resolve()))
                    self.assertEqual(record['profile'], profile)
                    self.assertEqual(record['goflags'], '-mod=vendor')
                    self.assertEqual(record['cgo'], '1')
                    self.assertIsNone(record['build_profile'])

    def test_every_command_failure_stops_before_later_source_code(self) -> None:
        for profile in ('hy2', 'vless'):
            expected = self.expected(profile)
            for index, (name, args) in enumerate(expected):
                with self.subTest(profile=profile, failure=(name, args)):
                    self.log.unlink(missing_ok=True)
                    result = self.run_profile(profile, FAIL_AT=' '.join([name] + args))
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual([(r['name'], r['args']) for r in self.records()], expected[:index + 1])
                    if index:
                        self.assertEqual(result.returncode, 37)

    def test_invalid_profiles_and_credentials_do_not_execute_tools(self) -> None:
        for profile in ('', 'auto', 'hy2;true'):
            self.assertNotEqual(self.run_profile(profile).returncode, 0)
            self.assertEqual(self.records(), [])
        for variable in ('GH_TOKEN', 'GITHUB_TOKEN', 'GH_ENTERPRISE_TOKEN', 'GITHUB_ENTERPRISE_TOKEN',
                         'YUETO_FORK_READ_TOKEN', 'GIT_CONFIG_COUNT', 'GIT_CONFIG_PARAMETERS',
                         'GIT_CONFIG_GLOBAL', 'GIT_CONFIG_KEY_0', 'GIT_CONFIG_VALUE_0'):
            with self.subTest(variable=variable):
                result = self.run_profile(**{variable: 'fixture-not-a-secret'})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(variable, result.stderr)
                self.assertNotIn('fixture-not-a-secret', result.stderr)
                self.assertEqual(self.records(), [])
        self.assertNotEqual(self.run_profile(GOFLAGS='-mod=mod').returncode, 0)
        self.assertEqual(self.records(), [])

    def test_required_source_vendor_and_cgo(self) -> None:
        (self.source / 'go.mod').unlink()
        self.assertNotEqual(self.run_profile().returncode, 0)
        self.assertEqual(self.records(), [])
        (self.source / 'go.mod').touch()
        (self.source / 'vendor/modules.txt').unlink()
        self.assertNotEqual(self.run_profile().returncode, 0)
        self.assertEqual(len(self.records()), 1)
        self.log.unlink()
        (self.source / 'vendor/modules.txt').touch()
        self.assertNotEqual(self.run_profile(CGO_ENABLED='0').returncode, 0)
        self.assertEqual(len(self.records()), 1)

    def test_real_workflow_step_invokes_executor(self) -> None:
        workflow = (ROOT / '.github/workflows/build.yml').read_text()
        node = workflow.split('      - name: Validate yue-node\n', 1)[1].split('      - name:', 1)[0]
        body = node.split('        run: |\n', 1)[1]
        import textwrap
        policy = self.source / '.ci-policy'
        policy.symlink_to(ROOT, target_is_directory=True)
        result = subprocess.run(['bash', '-euo', 'pipefail', '-c', textwrap.dedent(body)],
                                cwd=self.source, env=self.env | {'NODE_PROFILE': 'vless',
                                'GITHUB_WORKSPACE': str(self.source)}, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([(r['name'], r['args']) for r in self.records()], self.expected('vless'))


if __name__ == '__main__':
    unittest.main()
