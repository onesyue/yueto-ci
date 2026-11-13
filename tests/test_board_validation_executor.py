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

class PostgresExecutor(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.source, self.policy, self.temp, self.bin = [self.root / name for name in ('source', 'policy', 'temp', 'bin')]
        for directory in (self.source / 'scripts/ci', self.policy / 'scripts', self.temp, self.bin):
            directory.mkdir(parents=True)
        (self.source / 'go.mod').write_text('module fixture\n')
        (self.policy / 'scripts/install-board-quality-tools.sh').write_text('unused\n')
        (self.policy / 'scripts/pg_validation_address.py').write_text((ROOT / 'scripts/pg_validation_address.py').read_text())
        self.log = self.root / 'calls.jsonl'
        self.environment = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                                YUE_CI_PYTHON=sys.executable, CALL_LOG=str(self.log),
                                KEY_COUNT=str(self.root / 'key-count'),
                                YUEBOARD_ADMIN_DATABASE_URL='postgres://postgres:ci@postgres:5432/postgres',
                                CLEAN_PG_DSN='postgres://postgres:ci@postgres:5432/yueboard_clean_gate')
        for key in ('YUEBOARD_TOKEN_ENC_KEYS', 'YUEBOARD_TOKEN_BIDX_KEY'):
            self.environment.pop(key, None)
        phase = self.policy / 'scripts/validate-yueboard-postgres.py'
        phase.write_text('''import json, os, sys
from pathlib import Path
record = {'name': 'phase', 'args': sys.argv[1:], 'cwd': os.getcwd(),
          'clean_env': bool(os.getenv('CLEAN_PG_DSN') or os.getenv('YUEBOARD_ADMIN_DATABASE_URL')),
          'keys': bool(os.getenv('YUEBOARD_TOKEN_ENC_KEYS') or os.getenv('YUEBOARD_TOKEN_BIDX_KEY'))}
with open(os.environ['CALL_LOG'], 'a') as f: f.write(json.dumps(record) + '\\n')
if os.getenv('FAIL_STAGE') == 'phase': sys.exit(23)
Path(sys.argv[sys.argv.index('--receipt') + 1]).write_text('native fixture receipt')
''')
        stub = self.bin / 'stub'
        stub.write_text('#!' + sys.executable + '\n' + '''import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
stage = name
if name == 'openssl':
    count = Path(os.environ['KEY_COUNT'])
    number = int(count.read_text()) + 1 if count.exists() else 1
    count.write_text(str(number))
    stage += str(number)
with open(os.environ['CALL_LOG'], 'a') as f:
    f.write(json.dumps({'name': stage, 'args': sys.argv[1:],
        'keys_valid': os.getenv('YUEBOARD_TOKEN_ENC_KEYS') == '1:fixture-one-time-key'
         and os.getenv('YUEBOARD_TOKEN_BIDX_KEY') == 'fixture-one-time-key'}) + '\\n')
if os.getenv('FAIL_STAGE') == stage: sys.exit(23)
if name == 'openssl': print('fixture-one-time-key')
''')
        stub.chmod(0o755)
        for name in ('psql', 'openssl'):
            (self.bin / name).symlink_to(stub)
        (self.source / 'scripts/ci/clean-pg-gate.sh').symlink_to(stub)

    def execute(self, role, options, **extra):
        self.log.unlink(missing_ok=True)
        (self.root / 'key-count').unlink(missing_ok=True)
        result = subprocess.run(['bash', str(EXECUTOR), role, str(self.source), str(self.policy),
                                 str(self.temp), *options], env=self.environment | extra,
                                capture_output=True, text=True)
        rows = [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
        return result, rows

    def test_phase_argv_and_receipt_are_delegated_without_clean_environment(self):
        for role, phase in (('postgres', 'domain'), ('migration', 'remaining')):
            receipt = self.temp / (role + '.json')
            for failure in ('', 'phase'):
                receipt.unlink(missing_ok=True)
                result, rows = self.execute(role, ['--database-adapter', 'github-service', '--receipt', str(receipt)],
                                            YUEBOARD_ADMIN_DATABASE_URL='', CLEAN_PG_DSN='', FAIL_STAGE=failure)
                self.assertEqual(result.returncode, 23 if failure else 0, result.stderr)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0], {'name': 'phase', 'args': ['--phase', phase, '--database-adapter',
                    'github-service', '--receipt', str(receipt)], 'cwd': str(self.source),
                    'clean_env': False, 'keys': False})
                self.assertEqual(receipt.exists(), not failure)

    def test_clean_validates_then_creates_and_keeps_keys_out_of_output(self):
        result, rows = self.execute('postgres-clean', ['--database-adapter', 'github-service'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([r['name'] for r in rows], ['psql', 'openssl1', 'openssl2', 'clean-pg-gate.sh'])
        self.assertEqual(rows[0]['args'], ['-v', 'ON_ERROR_STOP=1', self.environment['YUEBOARD_ADMIN_DATABASE_URL'],
                                         '-c', 'CREATE DATABASE yueboard_clean_gate'])
        self.assertTrue(rows[-1]['keys_valid'])
        self.assertTrue(all(not row['keys_valid'] for row in rows[:-1]))
        self.assertNotIn('fixture-one-time-key', result.stdout + result.stderr)
        self.assertNotIn('YUEBOARD_TOKEN_ENC_KEYS', self.environment)
        self.assertFalse(list(self.temp.glob('*.json')))

    def test_each_clean_failure_stops_later_commands(self):
        sequence = ['psql', 'openssl1', 'openssl2', 'clean-pg-gate.sh']
        for index, stage in enumerate(sequence):
            with self.subTest(stage=stage):
                result, rows = self.execute('postgres-clean', ['--database-adapter', 'github-service'], FAIL_STAGE=stage)
                self.assertEqual(result.returncode, 23, result.stderr)
                self.assertEqual([r['name'] for r in rows], sequence[:index + 1])
                self.assertNotIn('fixture-one-time-key', result.stdout + result.stderr)

    def test_clean_bad_addresses_and_environment_stop_before_psql(self):
        changes = [
            {'YUEBOARD_ADMIN_DATABASE_URL': 'postgres://postgres:ci@postgres:5432/production'},
            {'CLEAN_PG_DSN': 'postgres://postgres:ci@postgres:5432/yueboard_test'},
            {'CLEAN_PG_DSN': 'postgres://postgres:ci@example.invalid:5432/yueboard_clean_gate'},
            {'CLEAN_PG_DSN': self.environment['CLEAN_PG_DSN'] + '?hostaddr=192.0.2.1'},
            {'YUEBOARD_ADMIN_DATABASE_URL': ''}, {'CLEAN_PG_DSN': ''},
            {'PGHOSTADDR': '192.0.2.1'}, {'PGSERVICE': 'untrusted'}, {'PGOPTIONS': '-csearch_path=other'},
        ]
        for change in changes:
            with self.subTest(change=change):
                result, rows = self.execute('postgres-clean', ['--database-adapter', 'github-service'], **change)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(rows, [])

    def test_argument_mismatch_is_refused_before_any_execution(self):
        for role, options in [
            ('quality', ['--database-adapter', 'loopback']), ('quality', ['--database-adapter', '']),
            ('postgres-clean', ['--database-adapter', 'github-service', '--receipt', '']), ('race', ['--receipt', str(self.temp / 'a')]),
            ('postgres', ['--database-adapter', 'github-service']),
            ('migration', ['--receipt', str(self.temp / 'a')]),
            ('postgres-clean', []),
            ('postgres-clean', ['--database-adapter', 'github-service', '--receipt', str(self.temp / 'a')]),
        ]:
            with self.subTest(role=role, options=options):
                result, rows = self.execute(role, options)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(rows, [])
        result, rows = self.execute('postgres-clean', ['--database-adapter', 'github-service'], YUE_CI_PYTHON='')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(rows, [])

    def test_pg_roles_reject_inherited_source_credentials(self):
        for role in ('postgres', 'migration', 'postgres-clean'):
            options = ['--database-adapter', 'github-service']
            if role != 'postgres-clean':
                options += ['--receipt', str(self.temp / 'receipt.json')]
            with self.subTest(role=role):
                result, rows = self.execute(role, options, GH_TOKEN='private-test-token')
                self.assertEqual(result.returncode, 2)
                self.assertEqual(rows, [])
                self.assertNotIn('private-test-token', result.stdout + result.stderr)

    def test_clean_loopback_uses_shared_rules(self):
        env = {'YUEBOARD_ADMIN_DATABASE_URL': 'postgres://postgres:ci@127.0.0.1:55434/postgres?sslmode=disable',
               'CLEAN_PG_DSN': 'postgres://postgres:ci@127.0.0.1:55434/yueboard_clean_gate?sslmode=disable'}
        result, rows = self.execute('postgres-clean', ['--database-adapter', 'loopback'], **env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(rows[-1]['name'], 'clean-pg-gate.sh')
        for uri in (env['CLEAN_PG_DSN'] + '&hostaddr=192.0.2.1',
                    env['CLEAN_PG_DSN'].replace('127.0.0.1:55434', 'localhost:5432,example.invalid:5432')):
            result, rows = self.execute('postgres-clean', ['--database-adapter', 'loopback'], **(env | {'CLEAN_PG_DSN': uri}))
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(rows, [])

    def test_clean_requires_same_connection_identity_before_psql(self):
        admin = 'postgres://postgres:ci@127.0.0.1:55434/postgres?sslmode=disable'
        clean = admin.replace('/postgres?', '/yueboard_clean_gate?')
        for changed in (clean.replace(':55434/', ':5432/'), clean.replace(':55434/', '/'),
                        clean.replace('@127.0.0.1', '@localhost'),
                        clean.replace('postgres:ci@', 'other:ci@'),
                        clean.replace('postgres:ci@', 'postgres:other@'),
                        clean.replace('sslmode=disable', 'sslmode=require'),
                        clean + '&application_name=other'):
            with self.subTest(changed=changed):
                result, rows = self.execute('postgres-clean', ['--database-adapter', 'loopback'],
                                            YUEBOARD_ADMIN_DATABASE_URL=admin, CLEAN_PG_DSN=changed)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('identity mismatch', result.stderr)
                self.assertNotIn(changed, result.stdout + result.stderr)
                self.assertEqual(rows, [])
        result, rows = self.execute('postgres-clean', ['--database-adapter', 'loopback'],
                                    YUEBOARD_ADMIN_DATABASE_URL=admin,
                                    CLEAN_PG_DSN=clean.replace('postgres:', 'postgresql:', 1))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(rows[-1]['name'], 'clean-pg-gate.sh')
