"""Execute the real Board role shell with controlled tools and real Git history."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
EXECUTOR = ROOT / 'scripts/board-validation.sh'


class BoardExecutor(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.source = self.root / 'source with spaces'
        self.policy = self.root / 'policy with spaces'
        self.temp = self.root / 'temp with spaces'
        self.bin = self.root / 'bin'
        for path in (self.source, self.policy / 'scripts', self.temp, self.bin, self.source / 'scripts/ci'):
            path.mkdir(parents=True, exist_ok=True)
        self.log = self.root / 'calls.jsonl'
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                        CALL_LOG=str(self.log), EXPECT_SOURCE=str(self.source))
        self.env.pop('YUEBOARD_CONTRACT_BASELINE', None)
        self.stub = self.bin / 'stub'
        self.stub.write_text('#!' + sys.executable + '\n' + '''import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
key = name + ' ' + ' '.join(args)
assert os.getcwd() == os.environ['EXPECT_SOURCE']
with open(os.environ['CALL_LOG'], 'a') as f:
    f.write(json.dumps({'name': name, 'args': args, 'baseline': os.getenv('YUEBOARD_CONTRACT_BASELINE'), 'cgo': os.getenv('CGO_ENABLED'), 'path': os.getenv('PATH')}) + '\\n')
if os.getenv('FAIL_COMMAND') == key:
    sys.exit(19)
if key == 'go env CGO_ENABLED':
    print(os.getenv('GO_CGO_RESULT', '1'))
if name == 'gofmt' and os.getenv('UNFORMATTED'):
    print('main.go')
''')
        self.stub.chmod(0o755)
        for name in ('go', 'gofmt', 'make', 'govulncheck', 'golangci-lint'):
            (self.bin / name).symlink_to(self.stub)
        for name in ('check-server-error-logging.sh', 'proto-gate.sh'):
            (self.source / 'scripts/ci' / name).symlink_to(self.stub)
        # The production executor invokes this source-owned installer with bash.
        installer = self.policy / 'scripts/install-board-quality-tools.sh'
        installer.write_text('#!/bin/bash\nexec "' + str(self.bin / 'installer') + '" "$@"\n')
        (self.bin / 'installer').symlink_to(self.stub)
        (self.source / 'go.mod').write_text('module fixture\n')
        (self.source / 'main.go').write_text('package fixture\n')
        (self.source / 'internal/gen').mkdir(parents=True)
        (self.source / 'internal/gen/generated.go').write_text('package gen\n')
        (self.source / 'noderpc/gen').mkdir(parents=True)
        (self.source / 'noderpc/gen/generated.go').write_text('package gen\n')
        self.git('init', '-q')
        self.git('add', '.')
        self.git('-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid',
                 '-c', 'commit.gpgsign=false', 'commit', '-qm', 'first')
        self.first = self.git('rev-parse', 'HEAD').stdout.strip()
        self.git('-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid',
                 '-c', 'commit.gpgsign=false', 'commit', '--allow-empty', '-qm', 'second')
        self.git('update-ref', 'refs/remotes/origin/master', 'HEAD')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.source), *args],
                              check=True, capture_output=True, text=True)

    def execute(self, role='quality', **env):
        self.log.unlink(missing_ok=True)
        result = subprocess.run(['bash', str(EXECUTOR), role, str(self.source), str(self.policy), str(self.temp)],
                                env=self.env | env, capture_output=True, text=True)
        rows = [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
        return result, rows

    def quality_commands(self):
        return ['go build ./...', 'gofmt -l main.go', 'make check-generated', 'go vet ./...',
                'check-server-error-logging.sh ', 'installer ' + str(self.temp / 'board-quality-tools'),
                'govulncheck ./...', 'golangci-lint run --timeout=6m ./...', 'go test ./...', 'proto-gate.sh ']

    def keys(self, rows):
        return [row['name'] + ' ' + ' '.join(row['args']) for row in rows]

    def test_quality_sequence_baseline_cgo_and_generated_exclusions(self):
        result, rows = self.execute()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.keys(rows), self.quality_commands())
        self.assertTrue(all(row['baseline'] == self.first and row['cgo'] == '1' for row in rows[:-1]))
        self.assertIsNone(rows[-1]['baseline'])
        self.assertEqual(rows[-1]['cgo'], self.env.get('CGO_ENABLED'))
        self.assertEqual(rows[-1]['path'], self.env['PATH'])

    def test_every_quality_failure_stops_later_commands(self):
        expected = self.quality_commands()
        for index, command in enumerate(expected):
            with self.subTest(command=command):
                result, rows = self.execute(FAIL_COMMAND=command)
                self.assertEqual(result.returncode, 19, result.stderr)
                self.assertEqual(self.keys(rows), expected[:index + 1])

    def test_explicit_and_branch_baselines_preserved(self):
        result, rows = self.execute(YUEBOARD_CONTRACT_BASELINE='reviewed-baseline')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(all(row['baseline'] == 'reviewed-baseline' for row in rows))
        self.git('update-ref', 'refs/remotes/origin/master', self.first)
        result, rows = self.execute()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(all(row['baseline'] is None for row in rows))

    def test_no_parent_does_not_invent_baseline(self):
        self.git('checkout', '--detach', self.first)
        self.git('update-ref', 'refs/remotes/origin/master', self.first)
        result, rows = self.execute()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(all(row['baseline'] is None for row in rows))

    def test_empty_or_unformatted_sources_stop_before_generated_gate(self):
        result, rows = self.execute(UNFORMATTED='1')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.keys(rows), self.quality_commands()[:2])
        self.git('rm', 'main.go')
        result, rows = self.execute()
        self.assertEqual(result.returncode, 1)
        self.assertIn('no lintable Go files', result.stdout + result.stderr)
        self.assertEqual(self.keys(rows), ['go build ./...'])

    def test_race_cgo_and_failure_propagation(self):
        result, rows = self.execute('race')
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = ['go env CGO_ENABLED', 'go test -race ./...']
        self.assertEqual(self.keys(rows), expected)
        self.assertTrue(all(row['cgo'] == '1' for row in rows))
        result, rows = self.execute('race', GO_CGO_RESULT='0')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.keys(rows), expected[:1])
        for command in expected:
            result, rows = self.execute('race', FAIL_COMMAND=command)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(self.keys(rows), expected[:expected.index(command) + 1])

    def test_invalid_role_or_missing_directories_fail_before_execution(self):
        args = ['quality', str(self.source), str(self.policy), str(self.temp)]
        for index in range(4):
            bad = args.copy()
            bad[index] = 'unknown' if index == 0 else str(self.root / 'missing')
            with self.subTest(index=index):
                result = subprocess.run(['bash', str(EXECUTOR), *bad], env=self.env,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse(self.log.exists())

    def test_inherited_tokens_refused_without_source_execution_or_disclosure(self):
        for role in ('quality', 'race'):
            for secret in ('GH_TOKEN', 'GITHUB_TOKEN', 'GH_ENTERPRISE_TOKEN', 'GITHUB_ENTERPRISE_TOKEN'):
                with self.subTest(role=role, secret=secret):
                    token = 'fixture-token-must-never-be-printed'
                    result, rows = self.execute(role, **{secret: token})
                    self.assertEqual(result.returncode, 2)
                    self.assertIn(secret, result.stderr)
                    self.assertNotIn(token, result.stdout + result.stderr)
                    self.assertEqual(rows, [])

    def test_protocol_receives_original_environment_after_quality_subshell(self):
        result, rows = self.execute(CGO_ENABLED='original-cgo', YUEBOARD_CONTRACT_BASELINE='original-baseline')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(all(row['cgo'] == '1' for row in rows[:-1]))
        self.assertEqual(rows[-1]['name'], 'proto-gate.sh')
        self.assertEqual(rows[-1]['cgo'], 'original-cgo')
        self.assertEqual(rows[-1]['baseline'], 'original-baseline')
        self.assertEqual(rows[-1]['path'], self.env['PATH'])
        self.assertTrue(rows[-2]['path'].startswith(str(self.temp / 'board-quality-tools') + os.pathsep))
