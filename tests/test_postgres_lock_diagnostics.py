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
    assert setup['run'] == 'bash .ci-policy/scripts/board-postgres-diagnostics.sh'
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
            # The failed-reload cases can invoke Docker 60 times in one test.
            docker.write_text(r'''#!/usr/bin/env bash
set -eu
printf '%s\n' "$@" >> "$RUNNER_TEMP/calls"
if [[ "$1" == logs ]]; then
    printf '%s\n' 'deadlock detected' 'Process 123: query one' 'Process 456: query two'
    [[ "$MODE" != logs_fail ]] || exit 17
    exit 0
fi
[[ "$1" == exec && "$2" == exact-service-id ]]
ignore_psqlrc=false
stop_on_error=false
for arg in "$@"; do
    case "$arg" in
        -X) ignore_psqlrc=true ;;
        ON_ERROR_STOP=1) stop_on_error=true ;;
    esac
done
[[ "$ignore_psqlrc" == true && "$stop_on_error" == true ]]
sql=${!#}
[[ "$MODE" != sql_fail ]] || exit 19
case "$sql" in
    'SELECT pg_reload_conf()') value=t ;;
    'SHOW log_lock_waits') value=on ;;
    'SHOW deadlock_timeout') value=200ms ;;
    'SHOW log_line_prefix') value='%m [%p] %q%u@%d app=%a xid=%x ' ;;
    'ALTER SYSTEM SET '*) exit 0 ;;
    *) exit 1 ;;
esac
if [[ "$MODE" == "$sql" ]]; then
    value=wrong
fi
printf '%s\n' "$value"
''')
            docker.chmod(0o755)
            sleep = root / 'sleep'
            sleep.write_text('#!/bin/sh\nexit 0\n'); sleep.chmod(0o755)
            script = str(ROOT / 'scripts/board-postgres-diagnostics.sh')
            body = step['run'].replace('.ci-policy/scripts/board-postgres-diagnostics.sh', script)
            result = subprocess.run(['bash', '-c', body], text=True, capture_output=True,
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
