"""Exercise the release gate with real Go discovery and real test processes."""
from __future__ import annotations

import ast
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'validate-yueboard-postgres.py'
sys.path.insert(0, str(SCRIPT.parent))
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

    def offline_dependency(self):
        """Serve a real module from disk with a fresh module cache, without network access."""
        proxy = self.root / 'proxy'
        version = proxy / 'gate.example/dependency/@v'
        version.mkdir(parents=True)
        module = 'module gate.example/dependency\n\ngo 1.23\n'
        (version / 'v1.0.0.mod').write_text(module)
        (version / 'v1.0.0.info').write_text('{"Version":"v1.0.0","Time":"2020-01-01T00:00:00Z"}')
        with zipfile.ZipFile(version / 'v1.0.0.zip', 'w') as archive:
            archive.writestr('gate.example/dependency@v1.0.0/go.mod', module)
            archive.writestr('gate.example/dependency@v1.0.0/value.go', 'package dependency\nconst Value = 1\n')
        with (self.root / 'go.mod').open('a') as module_file:
            module_file.write('\nrequire gate.example/dependency v1.0.0\n')
        self.environment.update(
            GOPROXY=proxy.as_uri(), GOSUMDB='off', GOPRIVATE='', GONOPROXY='', GONOSUMDB='',
            GOVCS='*:off', GOTOOLCHAIN='local', GOTELEMETRY='off', GOFLAGS='-mod=mod',
            GOMODCACHE=str(self.root / 'module-cache'), GOPATH=str(self.root / 'gopath'))
        row = self.package(GATE.DOMAIN[0])
        directory = self.root / row['path']
        (directory / 'dependency.go').write_text(
            'package fixture\nimport "gate.example/dependency"\nvar value = dependency.Value\n')
        return row

    def group_process(self, row):
        # Capture the Python parent's stderr too: Go's inherited diagnostics must remain visible.
        driver = ('import json, runpy, sys; from pathlib import Path; '
                  'sys.path.insert(0, str(Path(sys.argv[1]).parent)); '
                  'gate = runpy.run_path(sys.argv[1]); '
                  'row = json.loads(sys.argv[2]); gate["run_group"]([row["path"]], [row])')
        return subprocess.run([sys.executable, '-c', driver, str(SCRIPT), json.dumps(row)],
                              cwd=self.root, env=self.environment, capture_output=True, text=True, timeout=90,
                              check=False)

    def test_cold_and_warm_module_cache_keep_download_diagnostics_out_of_json(self):
        row = self.offline_dependency()
        notice = 'go: downloading gate.example/dependency v1.0.0'
        for cache in ('cold', 'warm'):
            with self.subTest(cache=cache):
                result = self.group_process(row)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertNotIn(notice, result.stdout)
                if cache == 'cold':
                    self.assertIn(notice, result.stderr)
                else:
                    self.assertNotIn(notice, result.stderr)
                receipt = json.loads(result.stdout.split('Integration execution: ', 1)[1])
                self.assertEqual(receipt, {'packages': [row['path']], 'top_level_passed': 1,
                                           'subtests_passed': 0, 'skipped': 0})

    def test_cold_cache_still_rejects_failure_skip_missing_test_and_build_failure(self):
        row = self.offline_dependency()
        cases = [
            ('failure', 't.Fatal("intentional failure")', ['TestConsumer'],
             ['failed: ' + row['import_path'] + '/TestConsumer', 'go test exited 1']),
            ('skip', 't.Skip("intentional skip")', ['TestConsumer'], ['skipped:']),
            ('missing', 't.Log("consumer")', ['TestAbsent'], ['integration tests not run and passed']),
            ('build', 'undefinedFixture()', ['TestConsumer'],
             ['go test exited 1', 'no successful package completion']),
        ]
        for label, body, tests, diagnostics in cases:
            with self.subTest(control=label):
                self.environment['GOMODCACHE'] = str(self.root / ('module-cache-' + label))
                selected = self.package(row['path'], body)
                selected['tests'] = tests
                result = self.group_process(selected)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('go: downloading gate.example/dependency v1.0.0', result.stderr)
                self.assertNotIn('Integration execution:', result.stdout)
                for diagnostic in diagnostics:
                    self.assertIn(diagnostic, result.stderr)
                if label == 'build':
                    self.assertIn('undefinedFixture', result.stdout + result.stderr)

    def test_non_json_stdout_rejected_despite_complete_success_events(self):
        row = self.package(GATE.DOMAIN[0])
        events = [{'Package': row['import_path'], 'Action': action, **fields}
                  for action, fields in [('run', {'Test': 'TestConsumer'}),
                                         ('pass', {'Test': 'TestConsumer'}), ('pass', {})]]
        stream = 'unexpected stdout\n' + ''.join(json.dumps(event) + '\n' for event in events)
        process = mock.Mock(stdout=io.StringIO(stream))
        process.wait.return_value = 0
        with mock.patch.object(GATE.subprocess, 'Popen', return_value=process):
            result, output, error = self.run_group(row)
        self.assertIsNone(result)
        self.assertEqual(error, 'non-JSON Go test output')
        self.assertIn('unexpected stdout', output)
        process.wait.assert_called_once_with()

    def run_workflow_role(self, workflow, role):
        """Execute the real phase scripts in an isolated runner receipt directory."""
        job = workflow.split('\n  validate:\n', 1)[1].split('\n  validation-evidence:', 1)[0]
        blocks = re.findall(r'^      - name: .*?(?=^      - name: |\Z)', job, re.M | re.S)
        selected = [block for block in blocks if block.splitlines()[0].strip() in {
            '- name: Validate YueBoard PostgreSQL integration',
            '- name: Validate YueBoard PostgreSQL module and migration integration',
        }]
        policy = self.root / '.ci-policy'
        if not policy.exists():
            policy.symlink_to(ROOT, target_is_directory=True)
        phases = []
        with tempfile.TemporaryDirectory(dir=self.root, prefix=role + '-') as runner_temp:
            for block in selected:
                condition = re.search(r'^        if: (.+)$', block, re.M)
                assert condition is not None
                expression = condition[1].replace('matrix.validation', repr('yueboard')).replace(
                    'matrix.board_role', repr(role)).replace('&&', ' and ').replace('||', ' or ')
                tree = ast.parse(expression, mode='eval')
                allowed = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.Compare, ast.Eq, ast.Constant)
                if any(not isinstance(node, allowed) for node in ast.walk(tree)):
                    raise RuntimeError('unsupported role condition: ' + condition[1])
                if not eval(compile(tree, '<workflow role>', 'eval'), {'__builtins__': {}}, {}):
                    continue
                environment = dict(self.environment, RUNNER_TEMP=runner_temp, YUE_CI_PYTHON=sys.executable,
                                   GITHUB_WORKSPACE=str(self.root))
                # Exercise the actual workflow address contract, not a loopback substitute.
                for key in GATE.DSNS:
                    match = re.search(r'^          ' + key + r": (.+)$", block, re.M)
                    assert match is not None
                    uris = re.findall(r"'(postgres(?:ql)?://[^']+)'", match[1])
                    if not uris or len(set(uris)) != 1:
                        raise RuntimeError('ambiguous workflow disposable DSN')
                    environment[key] = uris[0]
                environment.pop('YUEBOARD_MIGRATION_TEST_ALLOW_RESET', None)
                reset = re.search(r'^          YUEBOARD_MIGRATION_TEST_ALLOW_RESET: (.+)$', block, re.M)
                if reset:
                    environment['YUEBOARD_MIGRATION_TEST_ALLOW_RESET'] = reset[1]
                run = textwrap.dedent(block.split('        run: |\n', 1)[1])
                step_roles = re.findall(r'board-validation\.sh (postgres|migration)\s', run)
                step_phases = [{'postgres': 'domain', 'migration': 'remaining'}[item] for item in step_roles]
                if 'domain' in step_phases and reset:
                    raise RuntimeError('domain inherited reset acknowledgement')
                run = run.replace('${{ github.run_id }}', '123').replace('${{ github.run_attempt }}', '1')
                result = subprocess.run(['bash', '-c', run], cwd=self.root, env=environment,
                                        capture_output=True, text=True, timeout=90)
                if result.returncode:
                    raise RuntimeError(result.stdout + result.stderr)
                phases.extend(step_phases)
            expected = {'postgres': ['domain'], 'migration': ['remaining']}.get(role, [])
            if phases != expected:
                raise RuntimeError(f'{role}: expected local phases {expected}, executed {phases}')
        return phases

    def test_each_planned_role_executes_its_own_phase(self):
        for path in GATE.ORDER:
            self.package(path)
        self.command_gate()
        workflow = (ROOT / '.github/workflows/build.yml').read_text()
        plan = subprocess.run(['bash', str(ROOT / 'scripts/plan-build-targets.sh'), 'yueboard', 'c' * 40],
                              cwd=ROOT, check=True, capture_output=True, text=True)
        roles = [row['board_role'] for row in json.loads(plan.stdout)['validation_matrix']]
        self.assertEqual(roles, ['quality', 'race', 'postgres', 'migration', 'e2e', 'components', 'frontends'])
        for role in roles:
            with self.subTest(role=role):
                self.run_workflow_role(workflow, role)

    def test_repeating_domain_on_the_migration_role_is_rejected(self):
        for path in GATE.ORDER:
            self.package(path)
        self.command_gate()
        original = (ROOT / '.github/workflows/build.yml').read_text()
        workflow = original.replace(
            "- name: Validate YueBoard PostgreSQL integration\n"
            "        if: matrix.validation == 'yueboard' && matrix.board_role == 'postgres'",
            "- name: Validate YueBoard PostgreSQL integration\n"
            "        if: matrix.validation == 'yueboard' && (matrix.board_role == 'postgres' || matrix.board_role == 'migration')",
            1)
        self.assertNotEqual(workflow, original)
        with self.assertRaisesRegex(RuntimeError, r"migration: expected local phases \['remaining'\], executed \['domain', 'remaining'\]"):
            self.run_workflow_role(workflow, 'migration')

    def test_remaining_without_domain_receipt_does_not_claim_domain_packages(self):
        for path in GATE.ORDER:
            self.package(path)
        self.command_gate()
        receipt = self.root / 'receipt.json'
        remaining = self.command('remaining', receipt)
        self.assertEqual(remaining.returncode, 0, remaining.stdout + remaining.stderr)
        data = json.loads(receipt.read_text())
        self.assertNotIn('domain', data)
        executed = sum((data[group]['packages'] for group in ('commands', 'modules', 'migrations')), [])
        self.assertEqual(executed, [path for path in GATE.ORDER if path not in GATE.DOMAIN])

    def test_moving_domain_into_reset_step_loses_postgres_and_reset_isolation(self):
        workflow = (ROOT / '.github/workflows/build.yml').read_text()
        command = ('bash .ci-policy/scripts/board-validation.sh postgres \\\n'
                   '            "$GITHUB_WORKSPACE" "$GITHUB_WORKSPACE/.ci-policy" "$RUNNER_TEMP" \\\n'
                   '            --database-adapter github-service --receipt "$RUNNER_TEMP/yueboard-pg-${{ github.run_id }}-${{ github.run_attempt }}.json"')
        self.assertIn(command, workflow)
        workflow = workflow.replace(command, 'echo "domain runs in migration"', 1)
        remaining = '          bash .ci-policy/scripts/board-validation.sh migration'
        workflow = workflow.replace(remaining, '          ' + command + '\n' + remaining, 1)
        for role, diagnostic in [('postgres', 'expected local phases'), ('migration', 'domain inherited reset')]:
            with self.subTest(role=role), self.assertRaisesRegex(RuntimeError, diagnostic):
                self.run_workflow_role(workflow, role)

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
            if path not in GATE.HISTORICAL_ADDITIONS | set(GATE.COMMANDS) | set(GATE.FLOOR_ADDITIONS) | set(GATE.CAPABILITY_ADDITIONS) | set(GATE.SOURCE_CAPABILITY_ADDITIONS):
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
            if path not in set(GATE.COMMANDS) | set(GATE.FLOOR_ADDITIONS) | set(GATE.CAPABILITY_ADDITIONS) | set(GATE.SOURCE_CAPABILITY_ADDITIONS):
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
                phase = 'remaining' if key == 'YUEBOARD_MIGRATION_TEST_ALLOW_RESET' else 'domain'
                result = self.command(phase, self.root / 'receipt.json', environment)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)


    def test_current_floor_requires_statcron_and_subscribe_even_if_deleted(self):
        (self.root / 'schema-floor.txt').write_text('140\n')
        for path in GATE.ORDER:
            self.package(path)
        for path, minimum in GATE.FLOOR_ADDITIONS.items():
            if minimum > 140:
                continue
            with self.subTest(path=path):
                shutil.rmtree(self.root / path)
                result = self.command('domain', self.root / 'receipt.json')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("missing=['" + path + "']", result.stderr)
                self.package(path)

    def test_email_coupon_worker_requires_its_receipt_consumer(self):
        (self.root / 'schema-floor.txt').write_text('151\n')
        email = './internal/platform/emailcoupon'
        for path in GATE.ORDER:
            if path != email:
                self.package(path)
        marker = self.root / GATE.CAPABILITY_ADDITIONS[email]
        marker.parent.mkdir(parents=True)
        marker.write_text('package emailcoupon\n')
        result = self.command('domain', self.root / 'receipt.json')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing=['" + email + "']", result.stderr)

    def test_floor_151_without_email_coupon_source_is_not_missing(self):
        (self.root / 'schema-floor.txt').write_text('151\n')
        email = './internal/platform/emailcoupon'
        for path in GATE.ORDER:
            if path != email:
                self.package(path)
        result = self.command('domain', self.root / 'receipt.json')
        self.assertNotIn('integration package plan mismatch', result.stderr)

    def test_email_coupon_suite_runs_before_user_reset(self):
        email = './internal/platform/emailcoupon'
        for path in GATE.ORDER:
            body = 't.Log("reached integration consumer")'
            if path == email:
                body = 'if err := os.WriteFile(os.Getenv("COUPON_ORDER_MARKER"), []byte("ready"), 0600); err != nil { t.Fatal(err) }'
            elif path == './internal/modules/user':
                body = 'if _, err := os.Stat(os.Getenv("COUPON_ORDER_MARKER")); err != nil { t.Fatal("email coupon consumer must execute before user reset") }'
            self.package(path, body)
        self.command_gate()
        self.environment['COUPON_ORDER_MARKER'] = str(self.root / 'email-coupon-reached')
        receipt = self.root / 'receipt.json'
        domain = self.command('domain', receipt)
        self.assertEqual(domain.returncode, 0, domain.stdout + domain.stderr)
        remaining = self.command('remaining', receipt)
        self.assertEqual(remaining.returncode, 0, remaining.stdout + remaining.stderr)

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

    def test_abuse_retry_writer_requires_its_real_integration_suite(self):
        (self.root / 'schema-floor.txt').write_text('144\n')
        abuse_package = './internal/modules/usagepolicy'
        for path in GATE.ORDER:
            if path != abuse_package:
                self.package(path)
        self.command_gate()
        source, marker = GATE.SOURCE_CAPABILITY_ADDITIONS[abuse_package]
        source = self.root / source
        source.parent.mkdir(parents=True)
        source.write_text('package fixture\nconst pendingIntent = "' + marker + '"\n')
        result = self.command('domain', self.root / 'receipt.json')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing=['./internal/modules/usagepolicy']", result.stderr)
        self.package(abuse_package)
        receipt = self.root / 'recovered.json'
        domain = self.command('domain', receipt)
        self.assertEqual(domain.returncode, 0, domain.stdout + domain.stderr)
        remaining = self.command('remaining', receipt)
        self.assertEqual(remaining.returncode, 0, remaining.stdout + remaining.stderr)
        self.assertIn(abuse_package, json.loads(receipt.read_text())['modules']['packages'])

    def test_floor_144_before_abuse_retry_writer_keeps_its_actual_suites(self):
        (self.root / 'schema-floor.txt').write_text('144\n')
        abuse_package = './internal/modules/usagepolicy'
        for path in GATE.ORDER:
            if path != abuse_package:
                self.package(path)
        self.command_gate()
        source, _ = GATE.SOURCE_CAPABILITY_ADDITIONS[abuse_package]
        source = self.root / source
        source.parent.mkdir(parents=True)
        source.write_text('package fixture\nconst previousWriter = true\n')
        receipt = self.root / 'receipt.json'
        domain = self.command('domain', receipt)
        self.assertEqual(domain.returncode, 0, domain.stdout + domain.stderr)
        remaining = self.command('remaining', receipt)
        self.assertEqual(remaining.returncode, 0, remaining.stdout + remaining.stderr)
        executed = sum((json.loads(receipt.read_text())[group]['packages']
                        for group in ('domain', 'commands', 'modules', 'migrations')), [])
        self.assertEqual(executed, [path for path in GATE.ORDER if path != abuse_package])

    def test_template_cas_writer_requires_its_real_integration_suite(self):
        (self.root / 'schema-floor.txt').write_text('153\n')
        abuse_package = './internal/modules/admin'
        for path in GATE.ORDER:
            if path != abuse_package:
                self.package(path)
        self.command_gate()
        source, marker = GATE.SOURCE_CAPABILITY_ADDITIONS[abuse_package]
        source = self.root / source
        source.parent.mkdir(parents=True)
        source.write_text('package fixture\nconst pendingIntent = "' + marker + '"\n')
        result = self.command('domain', self.root / 'receipt.json')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing=['./internal/modules/admin']", result.stderr)
        self.package(abuse_package)
        receipt = self.root / 'recovered.json'
        domain = self.command('domain', receipt)
        self.assertEqual(domain.returncode, 0, domain.stdout + domain.stderr)
        remaining = self.command('remaining', receipt)
        self.assertEqual(remaining.returncode, 0, remaining.stdout + remaining.stderr)
        self.assertIn(abuse_package, json.loads(receipt.read_text())['modules']['packages'])

    def test_pre_cas_source_keeps_its_actual_suites(self):
        (self.root / 'schema-floor.txt').write_text('153\n')
        abuse_package = './internal/modules/admin'
        for path in GATE.ORDER:
            if path != abuse_package:
                self.package(path)
        self.command_gate()
        source, _ = GATE.SOURCE_CAPABILITY_ADDITIONS[abuse_package]
        source = self.root / source
        source.parent.mkdir(parents=True)
        source.write_text('package fixture\nconst previousWriter = true\n')
        receipt = self.root / 'receipt.json'
        domain = self.command('domain', receipt)
        self.assertEqual(domain.returncode, 0, domain.stdout + domain.stderr)
        remaining = self.command('remaining', receipt)
        self.assertEqual(remaining.returncode, 0, remaining.stdout + remaining.stderr)
        executed = sum((json.loads(receipt.read_text())[group]['packages']
                        for group in ('domain', 'commands', 'modules', 'migrations')), [])
        self.assertEqual(executed, [path for path in GATE.ORDER if path != abuse_package])

    def test_pg_execution_does_not_run_unrelated_optional_unit_test(self):
        row = self.package('./internal/modules/subscribe')
        (self.root / row['path'] / 'unit_test.go').write_text(
            'package fixture\nimport "testing"\nfunc TestOptionalBinary(t *testing.T) {t.Skip("no optional binary")}\n')
        result, output, error = self.run_group(row)
        self.assertIsNone(error, output)
        self.assertEqual(result['top_level_passed'], 1)
        self.assertNotIn('TestOptionalBinary', output)

class PostgresAddressContractTest(unittest.TestCase):
    def environment(self, uri):
        return {**{key: uri for key in GATE.DSNS},
                'YUEBOARD_MIGRATION_TEST_PRODUCTION_SCALE': '1',
                'YUEBOARD_MIGRATION_TEST_ALLOW_RESET': 'YES_I_UNDERSTAND_THIS_DATABASE_IS_DISPOSABLE'}

    def validate(self, uri, adapter='loopback', **extra):
        with mock.patch.dict(os.environ, self.environment(uri) | extra, clear=True):
            GATE.check_environment('remaining', adapter)

    def test_explicit_service_adapter_accepts_only_canonical_uris(self):
        for scheme in ('postgres', 'postgresql'):
            uri = f'{scheme}://postgres:ci@postgres:5432/yueboard_test'
            self.validate(uri, 'github-service')
            with self.assertRaisesRegex(RuntimeError, 'loopback disposable'):
                self.validate(uri, GITHUB_ACTIONS='true')
        with self.assertRaisesRegex(RuntimeError, 'unsupported database adapter'):
            self.validate('postgres://postgres:ci@postgres:5432/yueboard_test', 'automatic')

    def test_service_rejects_noncanonical_identity_and_redirects(self):
        canonical = 'postgres://postgres:ci@postgres:5432/yueboard_test'
        cases = [canonical.replace('postgres:5432', host) for host in
                 ('127.0.0.1:5432', 'example.invalid:5432', 'postgres:55434',
                  'postgres', 'postgres,example.invalid:5432', '%70ostgres:5432')]
        cases += [canonical.replace('postgres:ci@', credentials) for credentials in
                  ('postgres:wrong@', 'other:ci@', 'postgres@', '', '%70ostgres:ci@')]
        cases += [canonical.replace('/yueboard_test', '/production'),
                  canonical.replace('/yueboard_test', '/%79ueboard_test'),
                  canonical + '/', canonical + '#fragment', canonical + '?sslmode=disable',
                  canonical + '?hostaddr=192.0.2.1', canonical + '?service=production',
                  canonical + '?options=-csearch_path=other', canonical + '\n',
                  canonical.replace('@postgres', '@post\tgres')]
        for uri in cases:
            with self.subTest(uri=uri), self.assertRaisesRegex(RuntimeError, 'canonical github-service'):
                self.validate(uri, 'github-service', GITHUB_ACTIONS='true')

    def test_loopback_keeps_sslmode_and_rejects_encoded_redirect_keys(self):
        base = 'postgres://postgres:ci@127.0.0.1:55434/yueboard_test'
        self.validate(base + '?sslmode=disable&connect_timeout=5&application_name=integration')
        for key in ('host', 'hostaddr', 'port', 'dbname', 'database', 'user', 'password',
                    'passfile', 'service', 'servicefile', 'options', 'target_session_attrs',
                    'search_path', 'role', 'session_authorization', '%68ostaddr', 'HOSTADDR'):
            with self.subTest(key=key), self.assertRaisesRegex(RuntimeError, 'redirect option'):
                self.validate(base + '?sslmode=disable&' + key + '=untrusted')
        for uri in (base + '#other', base + '\n', base.replace('@127', '@\t127')):
            with self.subTest(uri=uri), self.assertRaises(RuntimeError):
                self.validate(uri)

    def test_loopback_requires_single_literal_hostspec_and_valid_port(self):
        for hostspec in ('localhost', '127.0.0.1', 'localhost:55434', '127.0.0.1:5432'):
            # Encoded userinfo does not change the address authority.
            self.validate(f'postgres://post%67res:c%40i@{hostspec}/yueboard_test?sslmode=disable')
        for hostspec in ('localhost:5432,example.invalid:5432',
                         '127.0.0.1:5432,localhost:55434', 'localhost,example.invalid',
                         '%6cocalhost:5432', 'localhost:%35%34%33%32',
                         'localhost:5432%2cexample.invalid:5432',
                         'localhost:', 'localhost:abc', 'localhost:-1',
                         'localhost:0', 'localhost:65536', 'localhost:5432:5433',
                         'localhost:5432@other.invalid', 'localhost.:5432'):
            with self.subTest(hostspec=hostspec), self.assertRaises(RuntimeError):
                self.validate(f'postgres://postgres:ci@{hostspec}/yueboard_test')

    def test_environment_redirects_rejected_without_value_disclosure(self):
        # Explicit inventory protects against dropping an entry from the production guard.
        keys = ('PGHOST', 'PGHOSTADDR', 'PGPORT', 'PGDATABASE', 'PGUSER', 'PGPASSWORD',
                'PGPASSFILE', 'PGSERVICE', 'PGSERVICEFILE', 'PGSYSCONFDIR', 'PGOPTIONS',
                'PGTARGETSESSIONATTRS')
        for adapter, uri in [('loopback', 'postgres://postgres:ci@localhost:5432/yueboard_test'),
                             ('github-service', 'postgres://postgres:ci@postgres:5432/yueboard_test')]:
            for key in keys:
                with self.subTest(adapter=adapter, key=key):
                    with self.assertRaises(RuntimeError) as error:
                        self.validate(uri, adapter, **{key: 'private-value-never-print'})
                    self.assertIn(key, str(error.exception))
                    self.assertNotIn('private-value-never-print', str(error.exception))
                    self.validate(uri, adapter, **{key: ''})

    def test_service_retains_identity_scale_and_reset_requirements(self):
        uri = 'postgres://postgres:ci@postgres:5432/yueboard_test'
        for key in GATE.DSNS:
            with self.subTest(missing=key), self.assertRaisesRegex(RuntimeError, 'required'):
                self.validate(uri, 'github-service', **{key: ''})
        with self.assertRaisesRegex(RuntimeError, 'same disposable'):
            self.validate(uri, 'github-service', YUEBOARD_TEMPLATE_TEST_DATABASE_URL=uri.replace('postgres:', 'postgresql:', 1))
        for key in ('YUEBOARD_MIGRATION_TEST_PRODUCTION_SCALE', 'YUEBOARD_MIGRATION_TEST_ALLOW_RESET'):
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                self.validate(uri, 'github-service', **{key: ''})

    def test_actual_cli_rejects_before_source_discovery(self):
        service = 'postgres://postgres:ci@postgres:5432/yueboard_test'
        loopback = service.replace('@postgres:', '@127.0.0.1:')
        cases = [([], service, {}), (['--database-adapter', 'unknown'], loopback, {}),
                 (['--database-adapter', 'github-service'], service + '?hostaddr=192.0.2.1', {}),
                 ([], loopback + '?%68ostaddr=192.0.2.1', {}),
                 (['--database-adapter', 'github-service'], service, {'PGSERVICE': 'untrusted'}),
                 ([], loopback, {'PGOPTIONS': '-csearch_path=untrusted'}),
                 ([], loopback.replace('127.0.0.1:5432', 'localhost:5432,example.invalid:5432'), {}),
                 ([], loopback.replace('127.0.0.1:5432', 'localhost:%35%34%33%32'), {}),
                 ([], loopback.replace('127.0.0.1:5432', '%6cocalhost:5432'), {})]
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / 'receipt.json'
            for args, uri, extra in cases:
                with self.subTest(args=args, uri=uri, extra=extra):
                    env = self.environment(uri) | extra | {'PATH': '', 'GITHUB_ACTIONS': 'true'}
                    result = subprocess.run([sys.executable, str(SCRIPT), '--phase', 'remaining',
                                             '--receipt', str(receipt), *args], cwd=directory,
                                            env=env, capture_output=True, text=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn('No such file', result.stderr)  # No attempt to execute go.
                    self.assertNotIn('Integration discovery', result.stdout)
                    self.assertFalse(receipt.exists())


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
                self.assertIn('@postgres:5432/yueboard_test', next(iter(values.values())))
                self.assertNotIn('127.0.0.1', next(iter(values.values())))
                self.assertIn('board-validation.sh ' + {'domain': 'postgres', 'remaining': 'migration'}[phase], block)
                self.assertIn('--database-adapter github-service', block)
                self.assertNotIn('YUEBOARD_ADMIN_DATABASE_URL:', block)
                self.assertNotIn('CLEAN_PG_DSN:', block)
                self.assertIn('github.run_id', block)
                self.assertIn('github.run_attempt', block)
                self.assertIn("YUEBOARD_MIGRATION_TEST_PRODUCTION_SCALE: '1'", block)
        lifecycle = workflow[clean:remaining]
        self.assertIn('board-validation.sh postgres-clean', lifecycle)
        executor = (ROOT / 'scripts/board-validation.sh').read_text()
        self.assertIn('CREATE DATABASE yueboard_clean_gate', executor)
        self.assertIn('scripts/ci/clean-pg-gate.sh', executor)
        self.assertNotIn('DROP DATABASE', lifecycle)
        for key in GATE.DSNS:
            self.assertNotIn(key + ':', lifecycle)
        self.assertNotIn('--receipt', lifecycle)


if __name__ == '__main__':
    unittest.main()
