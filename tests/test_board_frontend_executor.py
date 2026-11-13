"""Run the real frontend executor/adapter with controlled commands, never browsers/DB."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXECUTOR = ROOT / 'scripts/board-validation.sh'
ADAPTER = ROOT / 'scripts/board-validation-output.py'
SPEC = importlib.util.spec_from_file_location('board_output', ADAPTER)
assert SPEC and SPEC.loader
OUTPUT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OUTPUT)
PG_SPEC = importlib.util.spec_from_file_location('pg_address', ROOT / 'scripts/pg_validation_address.py')
assert PG_SPEC and PG_SPEC.loader
PG = importlib.util.module_from_spec(PG_SPEC)
PG_SPEC.loader.exec_module(PG)


class FrontendExecutor(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.source = self.root / 'source with spaces'
        self.policy = self.root / 'policy with spaces'
        self.temp = self.root / 'temporary files'
        self.bin = self.root / 'bin'
        for path in (self.source, self.policy / 'scripts', self.temp, self.bin,
                     self.source / 'scripts/ci', self.source / 'web', self.source / 'web-admin',
                     self.source / 'test/e2e/specs/__screenshots__', self.source / 'test/a11y'):
            path.mkdir(parents=True, exist_ok=True)
        for file in ('board-validation.sh', 'pg_validation_address.py', 'install-board-quality-tools.sh'):
            shutil.copy(ROOT / 'scripts' / file, self.policy / 'scripts')
        for file in ('go.mod', 'pnpm-workspace.yaml', 'scripts/ci/pnpm-audit-gate.mjs', 'test/e2e/playwright.config.ts',
                     'test/e2e/specs/__screenshots__/fixture-linux.png'):
            (self.source / file).touch()
        self.log = self.root / 'calls'
        (self.source / 'test/a11y/a11y-smoke.mjs').touch()
        self.output = self.root / 'github-output'
        self.env = os.environ | {'PATH': str(self.bin) + os.pathsep + os.environ['PATH'],
                                 'CALL_LOG': str(self.log), 'YUE_CI_PYTHON': sys.executable,
                                 'GITHUB_OUTPUT': str(self.output)}
        for key in ('GH_TOKEN', 'GITHUB_TOKEN', 'GH_ENTERPRISE_TOKEN', 'GITHUB_ENTERPRISE_TOKEN',
                    'YUEBOARD_ADMIN_DATABASE_URL', 'YUEBOARD_E2E_DATABASE_URL', 'YUEBOARD_E2E_ALLOW_RESET',
                    'PGHOST', 'PGHOSTADDR', 'PGPORT', 'PGDATABASE', 'PGUSER', 'PGPASSWORD', 'PGPASSFILE',
                    'PGSERVICE', 'PGSERVICEFILE', 'PGSYSCONFDIR', 'PGOPTIONS', 'PGTARGETSESSIONATTRS',
                    'YUEBOARD_A11Y_SKIP'):
            self.env.pop(key, None)
        stub = self.bin / 'stub'
        stub.write_text('#!' + sys.executable + '\n' + '''import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
key = name + ' ' + ' '.join(args)
rows = pathlib.Path(os.environ['CALL_LOG'])
index = len(rows.read_text().splitlines()) if rows.exists() else 0
with rows.open('a') as f:
 f.write(json.dumps({'key': key, 'cwd': os.getcwd(), 'db': bool(os.getenv('YUEBOARD_ADMIN_DATABASE_URL')),
                     'reset': bool(os.getenv('YUEBOARD_E2E_ALLOW_RESET')), 'output': bool(os.getenv('GITHUB_OUTPUT'))}) + '\\n')
if str(index) == os.getenv('FAIL_INDEX') or key == os.getenv('FAIL_COMMAND'): sys.exit(int(os.getenv('FAIL_STATUS', '19')))
if name == 'node' and args and args[0] == '-p' and 'test/a11y' in args[1] and os.getenv('A11Y_NO_PM'):
 print(''); sys.exit(0)
if name == 'node' and args and args[0] == '-p':
 print('' if os.getenv('MISSING_PM') else ('pnpm@other' if os.getenv('DIVERGED_PM') and 'web-admin' in args[1] else 'pnpm@fixture'))
if name == 'node' and args and args[0] == '-e' and os.getenv('MISSING_SCRIPT'): sys.exit(1)
if os.getenv('FORGE_OUTPUT'): print('layout=evil\\nvisual=bootstrapped')
''')
        stub.chmod(0o755)
        for name in ('node', 'pnpm', 'corepack', 'psql'):
            (self.bin / name).symlink_to(stub)
        (self.bin / 'id').write_text('#!/bin/sh\necho "${TEST_UID:-1001}"\n')
        (self.bin / 'sudo').write_text('#!/bin/sh\nexit "${TEST_SUDO:-1}"\n')
        for name in ('id', 'sudo'):
            (self.bin / name).chmod(0o755)

    def run_phase(self, role='frontends', phase='prepare', **extra):
        direct = extra.pop('direct', False)
        self.log.unlink(missing_ok=True)
        self.output.unlink(missing_ok=True)
        env = self.env | extra
        args = [role, str(self.source), str(self.policy), str(self.temp), '--frontend-phase', phase]
        if role == 'e2e' and phase == 'test':
            args += ['--database-adapter', 'github-service']
            for key, value in {'YUEBOARD_ADMIN_DATABASE_URL': 'postgres://postgres:ci@postgres:5432/postgres',
                               'YUEBOARD_E2E_DATABASE_URL': 'postgres://postgres:ci@postgres:5432/yueboard_e2e?sslmode=disable',
                               'YUEBOARD_E2E_ALLOW_RESET': 'YES_I_UNDERSTAND_THIS_DATABASE_IS_DISPOSABLE'}.items():
                env.setdefault(key, value)
        if direct:
            directory = Path(tempfile.mkdtemp(prefix='board-frontend.', dir=self.temp))
            args += ['--result', str(directory / 'result')]
            env.pop('GITHUB_OUTPUT', None)
            command = ['bash', str(EXECUTOR), *args]
        else:
            command = [sys.executable, str(ADAPTER), *args]
        completed = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
        rows = [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
        output = self.output.read_text() if self.output.exists() else ''
        return completed, rows, output

    def test_prepare_both_layouts_build_both_apps_audit_and_output(self):
        for layout in ('workspace', 'legacy'):
            if layout == 'legacy': (self.source / 'pnpm-workspace.yaml').unlink()
            for role in ('frontends', 'components', 'e2e'):
                with self.subTest(layout=layout, role=role):
                    result, rows, output = self.run_phase(role)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(output, f'layout={layout}\n')
                    keys = [row['key'] for row in rows]
                    self.assertEqual(keys[0], 'corepack enable')
                    self.assertEqual(keys[-1], 'node scripts/ci/pnpm-audit-gate.mjs web web-admin')
                    self.assertEqual(keys.count('node scripts/verify-dist.mjs dist'), 2)
                    self.assertTrue(all('--frozen-lockfile --ignore-scripts' in key for key in keys if ' install' in key and key.startswith('pnpm')))
                    if layout == 'workspace':
                        self.assertIn('pnpm --filter yueboard-web --filter yueboard-web-admin run build', keys)
                    else:
                        self.assertIn('pnpm --dir web build', keys)
                        self.assertIn('pnpm --dir web-admin build', keys)
                    self.assertTrue(all(not row['db'] and not row['reset'] and not row['output'] for row in rows))
        self.assertEqual(list(self.temp.iterdir()), [])

    def test_all_phase_commands_fail_closed_and_preserve_markers(self):
        for role, phase in [('frontends', 'prepare'), ('frontends', 'lint'), ('frontends', 'design'),
                            ('components', 'test'), ('e2e', 'test')]:
            good, expected, _ = self.run_phase(role, phase)
            self.assertEqual(good.returncode, 0, good.stderr)
            for index in range(len(expected)):
                with self.subTest(role=role, phase=phase, index=index):
                    result, rows, output = self.run_phase(role, phase, FAIL_INDEX=str(index))
                    # Missing-script wrappers intentionally map node failure to 1.
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual([r['key'] for r in rows], [r['key'] for r in expected[:index + 1]])
                    if phase == 'prepare' and index == len(expected) - 1:
                        self.assertEqual(output, 'layout=workspace\n')
                    if role == 'e2e' and index == len(expected) - 1:
                        self.assertEqual(output, 'visual=compared\n')

    def test_accessibility_reaches_source_gate_and_cannot_skip(self):
        for extra, with_deps in (({}, False), ({'TEST_SUDO': '0'}, True), ({'TEST_UID': '0'}, True)):
            with self.subTest(extra=extra):
                result, rows, output = self.run_phase(phase='design', **extra)
                self.assertEqual(result.returncode, 0, result.stderr)
                keys = [row['key'] for row in rows]
                self.assertEqual(keys[-3], 'node scripts/ci/pnpm-audit-gate.mjs test/a11y')
                self.assertEqual(keys[-2], 'pnpm --dir test/a11y exec playwright-core install ' + ('--with-deps ' if with_deps else '') + 'chromium')
                self.assertEqual(keys[-1], 'node test/a11y/a11y-smoke.mjs')
                self.assertEqual(output, '')
                self.assertTrue(all(not row['db'] and not row['reset'] for row in rows))
        for status in (1, 2, 3):
            result, _, output = self.run_phase(phase='design', FAIL_COMMAND='node test/a11y/a11y-smoke.mjs', FAIL_STATUS=str(status))
            self.assertEqual(result.returncode, status)
            self.assertEqual(output, '')
        result, rows, _ = self.run_phase(phase='design', YUEBOARD_A11Y_SKIP='1')
        self.assertEqual(result.returncode, 2)
        self.assertFalse(any('playwright-core' in row['key'] for row in rows))
        (self.source / 'test/a11y/a11y-smoke.mjs').unlink()
        result, rows, _ = self.run_phase(phase='design')
        self.assertEqual(result.returncode, 2)
        self.assertFalse(any('playwright-core' in row['key'] for row in rows))

    def test_layout_missing_entries_and_source_audit_fail_closed(self):
        for extra in ({'MISSING_PM': '1'},):
            result, _, output = self.run_phase(**extra)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output, '')
        audit = self.source / 'scripts/ci/pnpm-audit-gate.mjs'
        audit.unlink()
        result, _, output = self.run_phase()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output, 'layout=workspace\n')
        audit.touch()
        for role, phase in [('frontends', 'lint'), ('components', 'test')]:
            result, rows, _ = self.run_phase(role, phase, MISSING_SCRIPT='1')
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(any(row['key'].startswith('pnpm ') for row in rows))
        (self.source / 'pnpm-workspace.yaml').unlink()
        result, rows, _ = self.run_phase(DIVERGED_PM='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(row['key'].startswith('pnpm ') for row in rows))
        result, rows, _ = self.run_phase('frontends', 'design')
        self.assertEqual(result.returncode, 0, result.stderr)
        keys = [row['key'] for row in rows]
        self.assertEqual(keys[:3], ['node scripts/ci/verify-responsive.mjs',
                                    'node scripts/ci/verify-design-tokens.mjs',
                                    'node scripts/ci/verify-page-consistency.mjs'])
        self.assertEqual(keys[-1], 'node test/a11y/a11y-smoke.mjs')
        result, _, _ = self.run_phase('frontends', 'design', A11Y_NO_PM='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        install = 'pnpm --dir test/a11y install --frozen-lockfile --ignore-scripts'
        browser = 'pnpm --dir test/a11y exec playwright-core install chromium'
        self.assertLess(keys.index(install), keys.index(browser))
        result, rows, _ = self.run_phase('frontends', 'design', FAIL_COMMAND=install)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any('playwright-core' in row['key'] for row in rows))
        result, rows, _ = self.run_phase('frontends', 'design', MISSING_PM='1')
        self.assertEqual(result.returncode, 2)
        self.assertFalse(any('playwright-core' in row['key'] for row in rows))
        for role, phase in [('frontends', 'lint'), ('components', 'test'), ('e2e', 'test')]:
            result, rows, _ = self.run_phase(role, phase)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(rows, [])

    def test_browser_install_privilege_paths_and_no_snapshot_updates(self):
        for role in ('components', 'e2e'):
            for uid, sudo, deps in [('0', '1', True), ('1001', '0', True), ('1001', '1', False)]:
                result, rows, _ = self.run_phase(role, 'test', TEST_UID=uid, TEST_SUDO=sudo)
                self.assertEqual(result.returncode, 0, result.stderr)
                install = next(row['key'] for row in rows if 'playwright install' in row['key'])
                self.assertEqual('--with-deps' in install, deps)
                if role == 'e2e':
                    self.assertEqual(rows[-1]['key'], 'pnpm --dir test/e2e test --update-snapshots=none')

    def test_visual_missing_large_find_and_comparison_failure_controls(self):
        shots = self.source / 'test/e2e/specs/__screenshots__'
        for path in shots.iterdir(): path.unlink()
        for scenario in ('empty', 'darwin-only', 'missing', 'large'):
            if scenario == 'darwin-only': (shots / 'fixture-darwin.png').touch()
            if scenario == 'missing': shutil.rmtree(shots)
            if scenario == 'large':
                shots.mkdir()
                for index in range(6000): (shots / f'{index}-linux.png').touch()
            result, rows, output = self.run_phase('e2e', 'test')
            self.assertEqual(result.returncode == 0, scenario == 'large', result.stderr)
            self.assertEqual(output, 'visual=compared\n' if scenario == 'large' else '')
            self.assertEqual(any('test --update-snapshots' in row['key'] for row in rows), scenario == 'large')
        result, _, output = self.run_phase('e2e', 'test', FAIL_COMMAND='pnpm --dir test/e2e test --update-snapshots=none')
        self.assertEqual(result.returncode, 19)
        self.assertEqual(output, 'visual=compared\n')
        (self.bin / 'find').write_text('#!/bin/sh\nexit 7\n')
        (self.bin / 'find').chmod(0o755)
        result, rows, output = self.run_phase('e2e', 'test')
        self.assertEqual(result.returncode, 7)
        self.assertEqual(output, '')
        self.assertFalse(any('test --update-snapshots' in row['key'] for row in rows))

    def test_credentials_db_scope_and_redirects_refuse_before_tools(self):
        for role, phase in [('frontends', 'prepare'), ('frontends', 'lint'), ('frontends', 'design'),
                            ('components', 'test'), ('e2e', 'test')]:
            for token in ('GH_TOKEN', 'GITHUB_TOKEN', 'GH_ENTERPRISE_TOKEN', 'GITHUB_ENTERPRISE_TOKEN'):
                result, rows, _ = self.run_phase(role, phase, **{token: 'secret-never-log'})
                self.assertEqual(result.returncode, 2)
                self.assertEqual(rows, [])
                self.assertNotIn('secret-never-log', result.stdout + result.stderr)
        for key in ('YUEBOARD_ADMIN_DATABASE_URL', 'YUEBOARD_E2E_DATABASE_URL', 'YUEBOARD_E2E_ALLOW_RESET'):
            result, rows, _ = self.run_phase(**{key: 'forbidden'})
            self.assertEqual(result.returncode, 2)
            self.assertEqual(rows, [])
        for key, value in [('PGHOSTADDR', '192.0.2.1'), ('PGOPTIONS', '-csearch_path=other'),
                           ('YUEBOARD_E2E_ALLOW_RESET', ''), ('YUEBOARD_ADMIN_DATABASE_URL', 'postgres://postgres:ci@postgres:5432/production'),
                           ('YUEBOARD_E2E_DATABASE_URL', 'postgres://postgres:ci@postgres:5432/yueboard_e2e?hostaddr=192.0.2.1'),
                           ('YUEBOARD_E2E_DATABASE_URL', 'postgres://postgres:ci@other:5432/yueboard_e2e?sslmode=disable')]:
            result, rows, _ = self.run_phase('e2e', 'test', **{key: value})
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(rows, [])

    def test_executor_without_github_output_and_stdout_spoofing(self):
        result, _, output = self.run_phase(direct=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, '')
        result, _, output = self.run_phase(FORGE_OUTPUT='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('visual=bootstrapped', result.stdout)
        self.assertEqual(output, 'layout=workspace\n')

    def test_output_whitelist_refuses_missing_duplicate_unknown_and_symlink(self):
        path = self.temp / 'result'
        with self.assertRaisesRegex(ValueError, 'required'):
            OUTPUT.read_result(path, 'frontends', 'prepare', 0)
        self.assertEqual(OUTPUT.read_result(path, 'frontends', 'prepare', 19), '')
        for value in ('layout=workspace\nlayout=workspace\n', 'layout=unknown\n', 'visual=bootstrapped\n', 'SECRET=bad\n'):
            path.write_text(value)
            with self.assertRaises(ValueError): OUTPUT.read_result(path, 'frontends', 'prepare', 0)
        path.unlink()
        path.symlink_to(self.source / 'go.mod')
        with self.assertRaises(OSError): OUTPUT.read_result(path, 'frontends', 'prepare', 19)

    def test_workflow_boundaries_and_report_paths_stay_exact(self):
        workflow = yaml.safe_load((ROOT / '.github/workflows/build.yml').read_text())
        steps = workflow['jobs']['validate']['steps']
        e2e = next(step for step in steps if step.get('id') == 'board_e2e')
        prepare = next(step for step in steps if step.get('id') == 'board_frontend')
        self.assertNotIn('env', prepare)
        self.assertEqual(set(e2e['env']), {'YUEBOARD_ADMIN_DATABASE_URL', 'YUEBOARD_E2E_DATABASE_URL', 'YUEBOARD_E2E_ALLOW_RESET'})
        self.assertIn("steps.board_frontend.outputs.layout == 'workspace'", e2e['if'])
        report = next(step for step in steps if step.get('name') == 'Upload YueBoard E2E report')
        self.assertEqual(report['if'], "failure() && matrix.validation == 'yueboard' && matrix.board_role == 'e2e' && steps.board_e2e.outcome == 'failure'")
        self.assertEqual(report['with']['path'].splitlines(), ['test/e2e/playwright-report/', 'test/e2e/test-results/', 'test/e2e/.state/server.log'])
        self.assertEqual(report['with']['retention-days'], 7)
        self.assertEqual(report['with']['if-no-files-found'], 'ignore')
        for step in steps:
            if 'board-validation-output.py' in step.get('run', ''):
                self.assertNotIn('pnpm ', step['run'])
                self.assertNotIn('psql ', step['run'])
                self.assertNotIn('node ', step['run'])

    def test_adapter_preserves_failure_even_when_result_is_invalid(self):
        script = self.policy / 'scripts/board-validation.sh'
        for code in (0, 19):
            script.write_text('#!/bin/bash\nwhile [ "$1" != --result ]; do shift; done\n'
                              'printf "layout=evil\\n" > "$2"\nexit ' + str(code) + '\n')
            result, _, output = self.run_phase()
            self.assertEqual(result.returncode, code or 2)
            self.assertEqual(output, '')
            self.assertIn('invalid phase result', result.stderr)
        self.assertEqual(list(self.temp.iterdir()), [])

    def test_existing_or_foreign_result_is_refused_before_source_execution(self):
        directory = Path(tempfile.mkdtemp(prefix='board-frontend.', dir=self.temp))
        result = directory / 'result'
        result.write_text('layout=legacy\n')
        args = ['bash', str(EXECUTOR), 'frontends', str(self.source), str(self.policy), str(self.temp),
                '--frontend-phase', 'prepare', '--result']
        for path in (result, self.root / 'foreign-result'):
            process = subprocess.run([*args, str(path)], env=self.env, capture_output=True, text=True)
            self.assertEqual(process.returncode, 2)
            self.assertFalse(self.log.exists())
        self.assertEqual(result.read_text(), 'layout=legacy\n')

    def test_e2e_address_scope_and_exact_ssl_difference(self):
        from unittest.mock import patch
        admin = 'postgres://fixture:password@127.0.0.1:55434/postgres'
        target = 'postgresql://fixture:password@127.0.0.1:55434/yueboard_e2e?sslmode=disable'
        clean_env = {key: '' for key in PG.REDIRECT_ENV}
        clean_env |= {'YUEBOARD_ADMIN_DATABASE_URL': admin, 'YUEBOARD_E2E_DATABASE_URL': target,
                      'YUEBOARD_E2E_ALLOW_RESET': 'YES_I_UNDERSTAND_THIS_DATABASE_IS_DISPOSABLE'}
        for uri in (admin, admin + '?sslmode=disable'):
            with patch.dict(os.environ, clean_env | {'YUEBOARD_ADMIN_DATABASE_URL': uri}):
                PG.check_e2e_environment('loopback')
        for changed in (target.replace(':55434/', ':55435/'), target.replace('fixture:password', 'other:password'),
                        target.replace('fixture:password', 'fixture:other'), target.replace('127.0.0.1', 'localhost'),
                        target.replace('sslmode=disable', 'sslmode=require'), target.replace('?sslmode=disable', ''),
                        target + '&application_name=other', target + '&%68ostaddr=192.0.2.1',
                        target.replace('/yueboard_e2e?', '/production?'), target + '#fragment',
                        target.replace('127.0.0.1:55434', '127.0.0.1:55434,example.invalid:5432')):
            with self.subTest(uri=changed), patch.dict(os.environ, clean_env | {'YUEBOARD_E2E_DATABASE_URL': changed}):
                with self.assertRaises(RuntimeError): PG.check_e2e_environment('loopback')

    def test_legacy_prepare_each_failure_stops_and_audit_status_two_is_red(self):
        (self.source / 'pnpm-workspace.yaml').unlink()
        good, expected, _ = self.run_phase()
        self.assertEqual(good.returncode, 0, good.stderr)
        for index in range(len(expected)):
            result, rows, _ = self.run_phase(FAIL_INDEX=str(index))
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual([r['key'] for r in rows], [r['key'] for r in expected[:index + 1]])
        for code in (1, 2):
            result, _, output = self.run_phase(FAIL_COMMAND='node scripts/ci/pnpm-audit-gate.mjs web web-admin', FAIL_STATUS=str(code))
            self.assertEqual(result.returncode, code)
            self.assertEqual(output, 'layout=legacy\n')

    def test_missing_e2e_suite_fails_before_any_database_command(self):
        (self.source / 'test/e2e/playwright.config.ts').unlink()
        result, rows, output = self.run_phase('e2e', 'test')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(rows, [])
        self.assertEqual(output, '')
