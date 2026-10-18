"""Exercise the release gate with real Go discovery and real test processes."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'validate-yueboard-postgres.py'
SPEC = importlib.util.spec_from_file_location('postgres_gate', SCRIPT)
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


@contextlib.contextmanager
def working_directory(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class PostgresIntegrationExecutionTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(shutil.which('go'), 'real Go is required; these coverage tests must never skip')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'go.mod').write_text('module gate.example/board\n\ngo 1.23\n')
        (self.root / 'schema-floor.txt').write_text('130\n')
        self.environment = dict(os.environ)
        self.environment.pop('GOFLAGS', None)
        self.environment['GOWORK'] = 'off'
        self.environment.update({key: 'postgres://postgres:ci@127.0.0.1:5432/yueboard_test' for key in GATE.DSNS})
        self.environment.update(YUEBOARD_MIGRATION_TEST_ALLOW_RESET='YES_I_UNDERSTAND_THIS_DATABASE_IS_DISPOSABLE',
                                YUEBOARD_MIGRATION_TEST_PRODUCTION_SCALE='1')

    def package(self, path, body='t.Log("reached integration consumer")', *, extra=''):
        directory = self.root / path
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'base.go').write_text('package fixture\n')
        imports = 'import "testing"\n'
        if 'os.' in body + extra:
            imports = 'import ("testing"; "os")\n'
        (directory / 'consumer_test.go').write_text('//go:build integration\n\npackage fixture\n' + imports +
            'func TestConsumer(t *testing.T) {' + body + '}\n' + extra)
        return {'path': path, 'import_path': 'gate.example/board/' + path.removeprefix('./'),
                'tests': ['TestConsumer'], 'files': {}}

    def run_group(self, row):
        output = io.StringIO()
        with working_directory(self.root), mock.patch.dict(os.environ, self.environment, clear=True), contextlib.redirect_stdout(output):
            try:
                result = GATE.run_group([row['path']], [row])
                return result, output.getvalue(), None
            except RuntimeError as error:
                return None, output.getvalue(), str(error)

    def command(self, phase, receipt, environment=None):
        return subprocess.run([sys.executable, str(SCRIPT), '--phase', phase, '--receipt', str(receipt)],
            cwd=self.root, env=environment or self.environment, capture_output=True, text=True, timeout=90)

    def command_gate(self, body='go test -count=1 -tags integration -v ./cmd/yueboard'):
        script = self.root / GATE.COMMAND_GATE
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text('#!/usr/bin/env bash\nset -euo pipefail\n' + body + '\n')

    def test_real_domain_then_remaining_reaches_every_package_and_native_commands(self):
        for path in GATE.ORDER:
            self.package(path)
        self.command_gate()
        receipt = self.root / 'receipt.json'
        domain = self.command('domain', receipt)
        self.assertEqual(domain.returncode, 0, domain.stdout + domain.stderr)
        self.assertIn('=== RUN   TestConsumer', domain.stdout)
        remaining = self.command('remaining', receipt)
        self.assertEqual(remaining.returncode, 0, remaining.stdout + remaining.stderr)
        data = json.loads(receipt.read_text())
        self.assertEqual(sum((data[group]['packages'] for group in ('domain','commands','modules','migrations')), []), GATE.ORDER)
        self.assertEqual(sum(data[k]['top_level_passed'] for k in ('domain','commands','modules','migrations')), len(GATE.ORDER))
        self.assertNotIn('(cached)', domain.stdout + remaining.stdout)

    def test_missing_each_dsn_is_a_hard_execution_failure(self):
        for key in GATE.DSNS:
            with self.subTest(key=key):
                environment = dict(self.environment)
                del environment[key]
                result = self.command('domain', self.root / 'receipt.json', environment)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(key + ' is required', result.stderr)
                self.assertFalse((self.root / 'receipt.json').exists())

    def test_real_go_skip_without_traffic_dsn_cannot_be_a_green_package(self):
        row = self.package(GATE.DOMAIN[0], 'if os.Getenv("YUEBOARD_TRAFFIC_TEST_DATABASE_URL") == "" { t.Skip("traffic DSN missing") }')
        del self.environment['YUEBOARD_TRAFFIC_TEST_DATABASE_URL']
        unguarded = subprocess.run(['go', 'test', '-count=1', '-tags', 'integration', '-v', row['path']],
            cwd=self.root, env=self.environment, capture_output=True, text=True, timeout=45)
        self.assertEqual(unguarded.returncode, 0, unguarded.stderr)
        self.assertIn('--- SKIP: TestConsumer', unguarded.stdout)
        _, output, error = self.run_group(row)
        self.assertIn('traffic DSN missing', output)
        self.assertIn('skipped:', error)

    def test_real_subtest_skip_is_rejected_even_when_parent_passes(self):
        row = self.package(GATE.DOMAIN[0], 't.Run("missing", func(t *testing.T) {t.Skip("missing proof")})')
        _, output, error = self.run_group(row)
        self.assertIn('--- PASS: TestConsumer ', output)
        self.assertIn('--- SKIP: TestConsumer/missing', output)
        self.assertIn('skipped:', error)

    def test_testmain_exit_zero_is_not_execution(self):
        row = self.package(GATE.DOMAIN[0], extra='func TestMain(m *testing.M) { os.Exit(0) }\n')
        _, _, error = self.run_group(row)
        self.assertIn('integration tests not run and passed', error)

    def test_filter_matching_no_tests_is_not_execution(self):
        row = self.package(GATE.DOMAIN[0])
        row['tests'] = ['TestDoesNotExist']
        _, output, error = self.run_group(row)
        self.assertIn('no tests to run', output)
        self.assertIn('integration tests not run and passed', error)

    def test_real_failure_and_diagnostic_are_preserved(self):
        row = self.package(GATE.DOMAIN[0], 't.Fatal("actual consumer failed")')
        _, output, error = self.run_group(row)
        self.assertIn('actual consumer failed', output)
        self.assertIn('go test exited 1', error)

    def test_unit_pass_cannot_cover_missing_integration_execution(self):
        row = self.package(GATE.DOMAIN[0])
        (self.root / row['path'] / 'unit_test.go').write_text('package fixture\nimport "testing"\nfunc TestUnit(t *testing.T) {}\n')
        row['tests'].append('TestMissingIntegration')
        _, output, error = self.run_group(row)
        self.assertNotIn('=== RUN   TestUnit', output)
        self.assertIn('integration tests not run and passed', error)

    def test_unplanned_new_integration_package_requires_reviewed_order(self):
        for path in GATE.ORDER + ['./internal/modules/newly_added']:
            self.package(path)
        result = self.command('domain', self.root / 'receipt.json')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unplanned=['./internal/modules/newly_added']", result.stderr)

    def test_deleting_an_integration_package_is_not_historical_compatibility(self):
        for path in GATE.ORDER:
            if path != './internal/modules/user':
                self.package(path)
        result = self.command('domain', self.root / 'receipt.json')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing=['./internal/modules/user']", result.stderr)

    def test_explicit_older_floor_runs_only_its_actual_known_suites(self):
        (self.root / 'schema-floor.txt').write_text('129\n')
        for path in GATE.ORDER:
            if path not in GATE.HISTORICAL_ADDITIONS | set(GATE.COMMANDS) | set(GATE.FLOOR_ADDITIONS) | set(GATE.CAPABILITY_ADDITIONS):
                self.package(path)
        receipt = self.root / 'receipt.json'
        domain = self.command('domain', receipt)
        self.assertEqual(domain.returncode, 0, domain.stdout + domain.stderr)
        remaining = self.command('remaining', receipt)
        self.assertEqual(remaining.returncode, 0, remaining.stdout + remaining.stderr)
        self.assertIn('7 packages, no skipped tests', remaining.stdout)

    def test_current_floor_before_operator_cli_keeps_its_ten_packages(self):
        (self.root / 'schema-floor.txt').write_text('134\n')
        for path in GATE.ORDER:
            if path not in set(GATE.COMMANDS) | set(GATE.FLOOR_ADDITIONS) | set(GATE.CAPABILITY_ADDITIONS):
                self.package(path)
        receipt = self.root / 'receipt.json'
        self.assertEqual(self.command('domain', receipt).returncode, 0)
        result = self.command('remaining', receipt)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('10 packages, no skipped tests', result.stdout)

    def test_native_command_marker_cannot_hide_missing_integration_tests(self):
        for path in GATE.ORDER:
            if path not in GATE.COMMANDS:
                self.package(path)
        self.command_gate()
        result = self.command('domain', self.root / 'receipt.json')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing=['./cmd/yueboard']", result.stderr)

    def test_native_command_success_without_execution_is_rejected(self):
        self.package(GATE.COMMANDS[0])
        self.command_gate('true')
        with working_directory(self.root), mock.patch.dict(os.environ,self.environment,clear=True):
            with self.assertRaisesRegex(RuntimeError,'not run and passed'):
                GATE.run_commands([self.package(GATE.COMMANDS[0])])

    def test_traffic_cli_executes_after_privileged_native_gate(self):
        row = self.package(GATE.COMMANDS[0], extra='func TestTrafficLedgerCLIProcess(t *testing.T) { t.Log("traffic reached") }\n')
        row['tests'].append('TestTrafficLedgerCLIProcess')
        self.command_gate("go test -count=1 -tags integration -v -run '^TestConsumer$' ./cmd/yueboard")
        with working_directory(self.root), mock.patch.dict(os.environ, self.environment, clear=True):
            result = GATE.run_commands([row])
        self.assertEqual(result['top_level_passed'], 2)
        self.assertEqual(result['skipped'], 0)

    def test_traffic_cli_false_success_is_rejected(self):
        row = self.package(GATE.COMMANDS[0])
        row['tests'].append('TestTrafficLedgerCLIProcess')
        self.command_gate()
        with working_directory(self.root), mock.patch.dict(os.environ, self.environment, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'not run and passed'):
                GATE.run_commands([row])

    def test_native_command_skip_is_rejected(self):
        row = self.package(GATE.COMMANDS[0], 't.Skip("root issuer not reached")')
        self.command_gate()
        with working_directory(self.root), mock.patch.dict(os.environ,self.environment,clear=True):
            with self.assertRaisesRegex(RuntimeError,'not run and passed'):
                GATE.run_commands([row])

    def test_quota_cli_executes_and_missing_cutover_cannot_pass(self):
        names = ['TestQuotaRemindersCLIProcess', 'TestQuotaRemindersIndependentCutoverCLI']
        row = self.package(GATE.COMMANDS[0], extra='\n'.join(
            'func ' + name + '(t *testing.T) { t.Log("quota reached") }' for name in names))
        row['tests'].extend(names)
        self.command_gate("go test -count=1 -tags integration -v -run '^TestConsumer$' ./cmd/yueboard")
        with working_directory(self.root), mock.patch.dict(os.environ, self.environment, clear=True):
            result = GATE.run_commands([row])
            self.assertEqual(result['top_level_passed'], 3)
            self.assertEqual(result['skipped'], 0)
            self.package(GATE.COMMANDS[0], extra='func TestQuotaRemindersCLIProcess(t *testing.T) {}')
            with self.assertRaisesRegex(RuntimeError, 'TestQuotaRemindersIndependentCutoverCLI'):
                GATE.run_commands([row])

    def test_changed_source_cannot_reuse_earlier_domain_proof(self):
        for path in GATE.ORDER:
            self.package(path)
        receipt = self.root / 'receipt.json'
        domain = self.command('domain', receipt)
        self.assertEqual(domain.returncode, 0, domain.stdout + domain.stderr)
        self.package(GATE.MODULES[0], 't.Log("changed source")')
        remaining = self.command('remaining', receipt)
        self.assertNotEqual(remaining.returncode, 0)
        self.assertIn('missing or changed successful domain proof', remaining.stderr)

    def test_reset_scale_and_database_boundaries_fail_closed(self):
        for key, value, expected in (
            ('YUEBOARD_MIGRATION_TEST_ALLOW_RESET', '', 'reset acknowledgement'),
            ('YUEBOARD_MIGRATION_TEST_PRODUCTION_SCALE', '0', 'production-scale'),
            ('YUEBOARD_TRAFFIC_TEST_DATABASE_URL', 'postgres://postgres:ci@127.0.0.1:5432/production', 'disposable'),
            ('YUEBOARD_TRAFFIC_TEST_DATABASE_URL', 'postgres://postgres:ci@127.0.0.1:55434/yueboard_test', 'same disposable'),
        ):
            with self.subTest(key=key, value=value):
                environment = dict(self.environment, **{key: value})
                result = self.command('domain', self.root / 'receipt.json', environment)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)


    def test_current_floor_requires_statcron_and_subscribe_even_if_deleted(self):
        (self.root / 'schema-floor.txt').write_text('140\n')
        for path in GATE.ORDER:
            self.package(path)
        for path in GATE.FLOOR_ADDITIONS:
            with self.subTest(path=path):
                shutil.rmtree(self.root / path)
                result = self.command('domain', self.root / 'receipt.json')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("missing=['" + path + "']", result.stderr)
                self.package(path)

    def test_expiry_consumer_marker_requires_its_real_integration_package(self):
        (self.root / 'schema-floor.txt').write_text('140\n')
        for path in GATE.ORDER:
            if path not in GATE.CAPABILITY_ADDITIONS:
                self.package(path)
        marker = self.root / GATE.CAPABILITY_ADDITIONS['./internal/modules/remindmailcron']
        marker.parent.mkdir(parents=True)
        marker.write_text('package reminderrules\n')
        result = self.command('domain', self.root / 'receipt.json')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing=['./internal/modules/remindmailcron']", result.stderr)

    def test_pg_execution_does_not_run_unrelated_optional_unit_test(self):
        row = self.package('./internal/modules/subscribe')
        (self.root / row['path'] / 'unit_test.go').write_text(
            'package fixture\nimport "testing"\nfunc TestOptionalBinary(t *testing.T) {t.Skip("no optional binary")}\n')
        result, output, error = self.run_group(row)
        self.assertIsNone(error, output)
        self.assertEqual(result['top_level_passed'], 1)
        self.assertNotIn('TestOptionalBinary', output)

class PostgresWorkflowWiringTest(unittest.TestCase):
    def test_two_phase_real_consumer_wraps_existing_clean_lifecycle(self):
        workflow = (ROOT / '.github/workflows/build.yml').read_text()
        domain = workflow.index('- name: Validate YueBoard PostgreSQL integration')
        clean = workflow.index('- name: Validate YueBoard clean PostgreSQL lifecycle')
        remaining = workflow.index('- name: Validate YueBoard PostgreSQL module and migration integration')
        frontend = workflow.index('- name: Validate yueboard frontends')
        self.assertLess(domain, clean)
        self.assertLess(clean, remaining)
        phases = [(workflow[domain:clean], 'domain'), (workflow[remaining:frontend], 'remaining')]
        for block, phase in phases:
            with self.subTest(phase=phase):
                values = {line.strip().split(': ', 1)[0]: line.strip().split(': ', 1)[1]
                          for line in block.splitlines() if line.strip().startswith(tuple(key + ': ' for key in GATE.DSNS))}
                self.assertEqual(set(values), set(GATE.DSNS))
                self.assertEqual(len(set(values.values())), 1)
                self.assertIn('127.0.0.1:5432/yueboard_test', next(iter(values.values())))
                self.assertIn('127.0.0.1:55434/yueboard_test', next(iter(values.values())))
                self.assertIn('"$YUE_CI_PYTHON" .ci-policy/scripts/validate-yueboard-postgres.py', block)
                self.assertIn('--phase ' + phase, block)
                self.assertIn('github.run_id', block)
                self.assertIn('github.run_attempt', block)
                self.assertIn("YUEBOARD_MIGRATION_TEST_PRODUCTION_SCALE: '1'", block)
        lifecycle = workflow[clean:remaining]
        self.assertIn('CREATE DATABASE yueboard_clean_gate', lifecycle)
        self.assertIn('scripts/ci/clean-pg-gate.sh', lifecycle)
        self.assertNotIn('DROP DATABASE', lifecycle)


if __name__ == '__main__':
    unittest.main()
