"""Execute central disposable-service diagnostic steps and reject wiring drift."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
SETUP = 'Configure YueBoard PostgreSQL lock diagnostics'
COLLECT = 'Collect YueBoard PostgreSQL failure diagnostics'
ROLES = "matrix.validation == 'yueboard' && (matrix.board_role == 'postgres' || matrix.board_role == 'migration')"
ENTRIES = ['Validate YueBoard PostgreSQL integration',
           'Validate YueBoard clean PostgreSQL lifecycle',
           'Validate YueBoard PostgreSQL module and migration integration']


def validate(steps):
    names = [step.get('name') for step in steps]
    setup, collect = (steps[names.index(name)] for name in (SETUP, COLLECT))
    assert setup['if'] == ROLES
    assert collect['if'] == 'failure() && ' + ROLES
    assert not setup.get('continue-on-error') and not collect.get('continue-on-error')
    for entry in ENTRIES:
        assert names.index(SETUP) < names.index(entry) < names.index(COLLECT)
    for step in (setup, collect):
        assert step['env']['PG_SERVICE'] == '${{ job.services.postgres.id }}'
    return setup, collect


class LockDiagnostics(unittest.TestCase):
    def setUp(self):
        self.steps = yaml.safe_load((ROOT / '.github/workflows/build.yml').read_text())['jobs']['validate']['steps']
        self.setup, self.collect = validate(self.steps)

    def execute(self, step, mode='ok'):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docker = root / 'docker'
            docker.write_text('''#!/usr/bin/env python3
import os, sys
from pathlib import Path
args = sys.argv[1:]
with (Path(os.environ['RUNNER_TEMP']) / 'calls').open('a') as f:
    f.write(repr(args) + '\\n')
if args[0] == 'logs':
    print('deadlock detected\\nProcess 123: query one\\nProcess 456: query two')
    sys.exit(17 if os.environ['MODE'] == 'logs_fail' else 0)
assert args[:2] == ['exec', 'exact-service-id']
assert '-X' in args and 'ON_ERROR_STOP=1' in args
sql = args[-1]
if os.environ['MODE'] == 'sql_fail': sys.exit(19)
values = {'SELECT pg_reload_conf()': 't', 'SHOW log_lock_waits': 'on',
          'SHOW deadlock_timeout': '200ms',
          'SHOW log_line_prefix': '%m [%p] %q%u@%d app=%a xid=%x '}
if sql in values:
    print('wrong' if os.environ['MODE'] == sql else values[sql])
else: assert sql.startswith('ALTER SYSTEM SET ')
''')
            docker.chmod(0o755)
            sleep = root / 'sleep'
            sleep.write_text('#!/bin/sh\nexit 0\n'); sleep.chmod(0o755)
            result = subprocess.run(['bash', '-c', step['run']], text=True, capture_output=True,
                timeout=15, env={**os.environ, 'PATH': str(root) + ':' + os.environ['PATH'],
                                'PG_SERVICE': 'exact-service-id', 'RUNNER_TEMP': str(root), 'MODE': mode})
            return result, (root / 'calls').read_text()

    def test_setup_effective_and_dependency_failures(self):
        result, calls = self.execute(self.setup)
        self.assertEqual(result.returncode, 0, result.stderr)
        for setting in ('log_lock_waits = on', "deadlock_timeout = '200ms'", "log_line_prefix = '%m [%p]"):
            self.assertIn(setting, calls)
        for failure in ('sql_fail', 'SELECT pg_reload_conf()', 'SHOW log_lock_waits',
                        'SHOW deadlock_timeout', 'SHOW log_line_prefix'):
            with self.subTest(failure=failure):
                self.assertNotEqual(self.execute(self.setup, failure)[0].returncode, 0)

    def test_complete_both_pid_report_and_collection_failure(self):
        result, _ = self.execute(self.collect)
        self.assertEqual(result.returncode, 0)
        self.assertIn('Process 123: query one', result.stdout)
        self.assertIn('Process 456: query two', result.stdout)
        self.assertEqual(self.execute(self.collect, 'logs_fail')[0].returncode, 17)

    def test_workflow_mutations_fail(self):
        import copy
        for mutation in ('late', 'early', 'condition', 'continue', 'service'):
            steps = copy.deepcopy(self.steps)
            setup = next(s for s in steps if s.get('name') == SETUP)
            collect = next(s for s in steps if s.get('name') == COLLECT)
            if mutation == 'late': steps.remove(setup); steps.append(setup)
            if mutation == 'early': steps.remove(collect); steps.insert(0, collect)
            if mutation == 'condition': collect['if'] = ROLES
            if mutation == 'continue': setup['continue-on-error'] = True
            if mutation == 'service': setup['env']['PG_SERVICE'] = 'unrelated'
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError): validate(steps)
