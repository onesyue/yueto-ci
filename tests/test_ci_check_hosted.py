"""Hosted execution cannot turn partial runs or credential leakage into success."""
import importlib.util
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import types
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('hosted', ROOT / 'scripts/ci_check_hosted.py')
HOSTED = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HOSTED)


class HostedExecution(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'scripts').mkdir()
        self.output = self.root / 'output'
        self.output.mkdir()
        self.cli = self.root / 'scripts/ci-check.sh'
        self.env = patch.dict(os.environ, {key: '' for key in HOSTED.SECRET_ENV})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.resources = types.SimpleNamespace(free=20 * 1024**3)

    def execute(self, body, timeout_seconds=5):
        self.cli.write_text('#!/bin/bash\nset -eu\n' + body)
        with patch.object(HOSTED, 'ROOT', self.root), \
                patch.object(HOSTED, 'cleanup_containers') as cleanup, \
                patch.object(HOSTED.shutil, 'disk_usage', return_value=self.resources), \
                patch.object(HOSTED, 'policy_revision', return_value='d' * 40):
            code = HOSTED.run('a' * 40, 'b' * 40, 'c' * 40, self.output, timeout_seconds=timeout_seconds)
        self.assertEqual(cleanup.call_count, 1)
        return code, json.loads((self.output / 'hosted-result.json').read_text())

    def full_receipt(self, code):
        admission = {'validation_only': True, 'mode': 'sharded',
                     'validation_matrix': [{'validation': 'yueops', 'ops_role': 'native'}]}
        summary = {'complete': True, 'roles': ['native', 'join'], 'exit_codes': {'native': code, 'join': code}}
        (self.output / 'admission.json').write_text(json.dumps(admission))
        (self.output / 'local').mkdir()
        (self.output / 'local/execution.json').write_text(json.dumps(summary))

    def test_real_child_has_no_credential_and_all_roles_required(self):
        self.full_receipt(0)
        code, receipt = self.execute('test -z "${GH_TOKEN:-}"\ntest "$GIT_CONFIG_GLOBAL" = /dev/null\nexit 0\n')
        self.assertEqual(code, 0)
        self.assertEqual(receipt['status'], 'VALIDATION_PASSED')
        self.assertTrue(receipt['complete'])

    def test_success_exit_without_complete_role_receipts_is_infrastructure_failure(self):
        code, receipt = self.execute('exit 0\n')
        self.assertEqual(code, 2)
        self.assertEqual(receipt['status'], 'INFRASTRUCTURE_FAILED')
        self.assertFalse(receipt['complete'])

    def test_complete_product_failure_is_retained_as_failure(self):
        self.full_receipt(1)
        code, receipt = self.execute('exit 1\n')
        self.assertEqual(code, 1)
        self.assertEqual(receipt['status'], 'VALIDATION_FAILED')
        self.assertTrue(receipt['complete'])

    def test_success_exit_cannot_contradict_role_failure(self):
        self.full_receipt(1)
        code, receipt = self.execute('exit 0\n')
        self.assertEqual(code, 2)
        self.assertIn('contradicts', receipt['problem'])

    def test_real_timeout_terminates_child_and_keeps_incomplete_receipt(self):
        started = time.monotonic()
        code, receipt = self.execute('echo started\nsleep 60\n', timeout_seconds=0.1)
        self.assertEqual(code, 2)
        self.assertLess(time.monotonic() - started, 5)
        self.assertIn('time budget', receipt['problem'])
        self.assertIn('started', (self.output / 'hosted.log').read_text())

    def test_low_disk_and_credentials_refuse_before_source_execution(self):
        self.resources.free = 1
        code, receipt = self.execute('echo must-not-run\n')
        self.assertEqual(code, 2)
        self.assertIn('insufficient disk', receipt['problem'])
        self.assertFalse((self.output / 'hosted.log').exists())
        with patch.dict(os.environ, GH_TOKEN='fixture-secret'):
            with self.assertRaisesRegex(ValueError, 'credential'):
                HOSTED.clean_environment(self.output, 'a' * 40)

    def test_duplicate_invocation_does_not_clean_an_existing_execution(self):
        (self.output / '.hosted-owner').write_text('owned')
        with patch.object(HOSTED, 'cleanup_containers') as cleanup:
            self.assertEqual(HOSTED.run('a' * 40, 'b' * 40, 'c' * 40, self.output), 2)
            cleanup.assert_not_called()
        self.assertFalse((self.output / 'hosted-result.json').exists())

    def test_cleanup_rechecks_recorded_exact_identity_before_removal(self):
        job = self.output / 'local/native'
        job.mkdir(parents=True)
        container = 'a' * 64
        (job / 'container.json').write_text(json.dumps({'container_id': container}))
        (job / 'container.cid').write_text(container + '\n')
        with patch.object(HOSTED.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'foreign-owner', '')) as run:
            with self.assertRaisesRegex(ValueError, 'unowned'):
                HOSTED.cleanup_containers(self.output)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0][-1], container)
            self.assertEqual(run.call_args.args[0][:2], ['docker', 'inspect'])
        owner = HOSTED.hashlib.sha256(str((self.output / 'local').resolve()).encode()).hexdigest()
        with patch.object(HOSTED.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, owner, '')) as run:
            HOSTED.cleanup_containers(self.output)
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual([cmd[1] for cmd in commands], ['inspect', 'logs', 'rm'])
            self.assertTrue(all(cmd[-1] == container for cmd in commands))

    def test_cleanup_continues_after_corrupt_receipt_and_log_failure(self):
        for name, body in [('bad', '{'), ('first', json.dumps({'container_id': 'a' * 64})),
                           ('second', json.dumps({'container_id': 'b' * 64}))]:
            job = self.output / 'local' / name
            job.mkdir(parents=True)
            (job / 'container.json').write_text(body)
        owner = HOSTED.hashlib.sha256(str((self.output / 'local').resolve()).encode()).hexdigest()
        calls = []
        def command(args, **kwargs):
            calls.append(args)
            if args[1] == 'logs' and args[-1] == 'a' * 64:
                raise OSError('fixture log failure')
            return subprocess.CompletedProcess(args, 0, owner, '')
        with patch.object(HOSTED.subprocess, 'run', side_effect=command):
            with self.assertRaisesRegex(ValueError, 'fixture log failure'):
                HOSTED.cleanup_containers(self.output)
        self.assertEqual({args[-1] for args in calls if args[1] == 'rm'}, {'a' * 64, 'b' * 64})

    def test_sampling_error_stops_descendant_even_when_leader_exits_on_term(self):
        child_pid = self.output / 'stubborn-child.pid'
        heartbeat = self.output / 'heartbeat'
        child = self.root / 'stubborn-child.sh'
        child.write_text('#!/bin/bash\ntrap "" TERM\necho $$ > "$CI_CHECK_OUTPUT/stubborn-child.pid"\n'
                         'while :; do echo alive >> "$CI_CHECK_OUTPUT/heartbeat"; sleep 0.05; done\n')
        def failed_sample(output):
            deadline = time.monotonic() + 5
            while not child_pid.exists():
                if time.monotonic() >= deadline:
                    raise AssertionError('controlled descendant did not start')
                time.sleep(0.01)
            raise OSError('sampler write failed')
        real_kill = os.killpg
        signals = []
        def kill(group, sig):
            signals.append(sig)
            return real_kill(group, sig)
        body = f'trap "exit 0" TERM\nbash {str(child)!r} &\nwait\n'
        with patch.object(HOSTED, 'sample_resources', side_effect=failed_sample), \
                patch.object(HOSTED.os, 'killpg', side_effect=kill):
            code, receipt = self.execute(body)
        self.assertEqual(code, 2)
        self.assertIn('sampler write failed', receipt['problem'])
        self.assertIn(HOSTED.signal.SIGKILL, signals)
        before = heartbeat.read_bytes() if heartbeat.exists() else b''
        time.sleep(0.1)
        self.assertEqual(heartbeat.read_bytes() if heartbeat.exists() else b'', before)

    def test_session_receipt_failure_never_releases_source_execution_gate(self):
        marker = self.output / 'source-executed'
        with patch.object(HOSTED, 'process_identity', side_effect=OSError('session recording unavailable')):
            code, receipt = self.execute(f'echo forbidden > {str(marker)!r}\n')
        self.assertEqual(code, 2)
        self.assertIn('session recording unavailable', receipt['problem'])
        self.assertFalse(marker.exists())

    def test_recovery_refuses_reused_process_identity(self):
        pid = 123456
        record = {'pid': pid, 'output': str(self.output.resolve()), 'owner': 'fixture',
                  'identity': {'group': pid, 'session': pid, 'start': 'old'}}
        (self.output / 'controller-session.json').write_text(json.dumps(record))
        with patch.object(HOSTED, 'process_identity', return_value=record['identity'] | {'start': 'new'}), \
                patch.object(HOSTED.os, 'killpg') as kill:
            with self.assertRaisesRegex(ValueError, 'reused'):
                HOSTED.recover_session(self.output)
            kill.assert_not_called()

    def test_always_cleanup_produces_infra_receipt_after_controller_death(self):
        with patch.object(HOSTED, 'cleanup_containers') as cleanup:
            self.assertEqual(HOSTED.finalize(self.output), 2)
            cleanup.assert_called_once_with(self.output)
        receipt = json.loads((self.output / 'hosted-result.json').read_text())
        self.assertFalse(receipt['complete'])
        self.assertEqual(receipt['status'], 'INFRASTRUCTURE_FAILED')

    def test_disk_exhaustion_during_execution_terminates_child_as_infra(self):
        class Budget:
            calls = 0
            @property
            def free(self):
                self.calls += 1
                return 20 * 1024**3 if self.calls == 1 else 1024
        self.resources = Budget()
        code, receipt = self.execute('sleep 60\n')
        self.assertEqual(code, 2)
        self.assertIn('disk space budget', receipt['problem'])
        self.assertFalse(receipt['complete'])


class ManualWorkflow(unittest.TestCase):
    def setUp(self):
        self.workflow = yaml.safe_load((ROOT / '.github/workflows/policy-ci.yml').read_text())
        self.job = self.workflow['jobs']['local-replay']

    def test_manual_only_read_only_complete_runner_has_reserved_upload_time(self):
        self.assertEqual(set(self.workflow['jobs']), {'policy', 'local-replay'})
        trigger = self.workflow.get('on', self.workflow.get(True))
        inputs = trigger['workflow_dispatch']['inputs']
        self.assertEqual(set(inputs), {'source_ref', 'board_ref', 'migration_base'})
        self.assertTrue(all(item['required'] for item in inputs.values()))
        self.assertEqual(self.job['if'], "github.event_name == 'workflow_dispatch'")
        self.assertEqual(self.job['timeout-minutes'], 360)
        self.assertEqual(HOSTED.EXECUTION_SECONDS, 330 * 60)
        self.assertEqual(self.job['permissions'], {'contents': 'read'})
        self.assertFalse(self.job['concurrency']['cancel-in-progress'])
        steps = self.job['steps']
        self.assertFalse(steps[0]['with']['persist-credentials'])
        self.assertEqual([step['uses'] for step in steps if 'uses' in step], [
            'actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1',
            'actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97',
            'actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1',
            'actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a',
        ])
        mint = next(step for step in steps if step.get('id') == 'source_token')
        self.assertEqual(mint['if'], "vars.YUETO_CI_APP_CLIENT_ID != ''")
        self.assertEqual(mint['with']['repositories'], 'yueops,yueboard')
        self.assertEqual(mint['with']['permission-contents'], 'read')
        execution = next(step for step in steps if step.get('name', '').startswith('Execute every'))
        self.assertNotIn('env', execution)
        self.assertIn('ci_check_hosted.py', execution['run'])
        upload = steps[-1]
        self.assertEqual(upload['if'], 'always()')
        self.assertEqual(upload['with']['if-no-files-found'], 'error')
        prefix = '${{ runner.temp }}/ci-check-replay/'
        allowed = {'controller-session.json', 'hosted-result.json', 'hosted.log', 'host-resources.jsonl', 'preparation.log',
                   'preparation-status.json', 'prepared.json', 'admission.json', 'planner.log',
                   'docker-info.txt', 'disk-before.txt', 'timeout-container-*.log',
                   'local/execution.json', 'local/resources.jsonl', 'local/failures.txt',
                   'local/*/role.log', 'local/*/container.json', 'local/*/container.cid',
                   'local/*/temp/docker-daemon.log', 'local/evidence/**'}
        selected = set()
        for path in upload['with']['path'].splitlines():
            self.assertTrue(path.startswith(prefix))
            selected.add(path[len(prefix):])
        self.assertLessEqual(selected, allowed)
        self.assertLessEqual({'hosted-result.json', 'admission.json', 'prepared.json',
                             'local/evidence/**', 'local/*/role.log'}, selected)
        self.assertIn('/local/execution.json', upload['with']['path'])
        cleanup = steps[-2]
        self.assertEqual(cleanup['if'], 'always()')
        self.assertIn('--cleanup-only', cleanup['run'])

    def test_manual_boundary_mutations_are_rejected(self):
        original = copy.deepcopy(self.workflow)
        for mutation in ('event', 'permissions', 'token_env', 'publication_action', 'raw_archive'):
            with self.subTest(mutation=mutation):
                self.workflow = copy.deepcopy(original)
                self.job = self.workflow['jobs']['local-replay']
                if mutation == 'event':
                    self.job['if'] = "github.event_name == 'pull_request'"
                elif mutation == 'permissions':
                    self.job['permissions']['packages'] = 'write'
                elif mutation == 'token_env':
                    next(step for step in self.job['steps'] if step.get('name', '').startswith('Execute every'))['env'] = {'GH_TOKEN': 'leaked'}
                elif mutation == 'publication_action':
                    self.job['steps'].insert(-1, {'uses': 'docker/build-push-action@' + 'a' * 40})
                else:
                    self.job['steps'][-1]['with']['path'] = '${{ runner.temp }}/ci-check-replay/**'
                with self.assertRaises(AssertionError):
                    self.test_manual_only_read_only_complete_runner_has_reserved_upload_time()

    def test_credential_selection_and_step_scope_are_fail_closed(self):
        steps = self.job['steps']
        prepare = next(step for step in steps if step.get('name', '').startswith('Prepare exact'))
        self.assertEqual(prepare['env']['GH_TOKEN'],
                         "${{ vars.YUETO_CI_APP_CLIENT_ID == '' && secrets.YUETO_CI_PAT || steps.source_token.outputs.token }}")
        self.assertEqual(prepare['env']['REPLAY_APP_CLIENT_ID'], '${{ vars.YUETO_CI_APP_CLIENT_ID }}')
        mint = next(step for step in steps if step.get('id') == 'source_token')
        self.assertNotIn('continue-on-error', mint)
        self.assertNotIn('if', prepare)  # Default success() blocks after mint failure.
        for step in steps[steps.index(prepare) + 1:]:
            self.assertNotIn('secrets.', str(step))
            self.assertNotIn('source_token.outputs.token', str(step))
        self.assertNotIn('GH_TOKEN', self.job['env'])

    def test_real_preparation_shell_cleans_both_credentials_and_revokes_only_app(self):
        preparation = next(step for step in self.job['steps'] if step.get('name', '').startswith('Prepare exact'))
        cases = [
            ('app', 'fixture-secret', 0, 0, 0, 0),
            ('app', 'fixture-secret', 17, 0, 0, 17),
            ('app', 'fixture-secret', 0, 1, 0, 2),
            ('app', 'fixture-secret', 0, 0, 1, 2),
            ('', 'fixture-secret', 0, 0, 0, 0),
            ('', 'fixture-secret', 17, 0, 0, 17),
            ('', 'fixture-secret', 0, 0, 1, 2),
            ('', 'fixture-secret', 0, 0, 3, 2),
            ('', '', 0, 0, 0, 2),
            ('app', '', 0, 0, 0, 2),
        ]
        for app, token, clone_code, revoke_code, remove_code, expected in cases:
            with self.subTest(app=bool(app), token=bool(token), clone=clone_code, revoke=revoke_code, remove=remove_code), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                binpath = root / 'bin'
                binpath.mkdir()
                output = root / 'output'
                output.mkdir()
                calls = root / 'calls'
                (binpath / 'gh').write_text('#!/bin/bash\nset -eu\necho "gh $*" >> "$CALLS"\n'
                                          'if [ "$1" = api ]; then exit "$REVOKE_CODE"; fi\n'
                                          'mkdir -p "$GH_CONFIG_DIR"\n'
                                          'printf config > "$GIT_CONFIG_GLOBAL"\n')
                (binpath / 'bash').write_text('#!/bin/bash\nset -eu\n'
                                            '[ "$GH_TOKEN" = fixture-secret ]\n'
                                            '[ "${!#}" = --prepare-only ]\n'
                                            'echo prepare >> "$CALLS"\nexit "$CLONE_CODE"\n')
                (binpath / 'rm').write_text('#!/bin/bash\n'
                                          'if [ "$REMOVE_CODE" = 3 ]; then exit 0; fi\n'
                                          'if [ "$REMOVE_CODE" != 0 ]; then exit "$REMOVE_CODE"; fi\n'
                                          'exec /bin/rm "$@"\n')
                for path in binpath.iterdir():
                    path.chmod(0o755)
                env = os.environ | {'PATH': str(binpath) + os.pathsep + os.environ['PATH'],
                                    'RUNNER_TEMP': str(root), 'CI_CHECK_OUTPUT': str(output),
                                    'CALLS': str(calls), 'CLONE_CODE': str(clone_code), 'REVOKE_CODE': str(revoke_code),
                                    'REMOVE_CODE': str(remove_code), 'REPLAY_APP_CLIENT_ID': app,
                                    'GH_TOKEN': token, 'SOURCE_REF': 'a' * 40, 'BOARD_REF': 'b' * 40}
                result = subprocess.run(['/bin/bash', '-c', preparation['run']], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, expected, result.stderr)
                expected_calls = []
                if token:
                    expected_calls = ['gh auth setup-git --hostname github.com', 'prepare']
                    if app:
                        expected_calls.append('gh api --method DELETE /installation/token')
                self.assertEqual(calls.read_text().splitlines() if calls.exists() else [], expected_calls)
                self.assertEqual(bool(list(root.glob('ci-check-auth.*'))), bool(remove_code))
                receipt = (output / 'preparation-status.json').read_text()
                self.assertEqual(json.loads(receipt)['exit_code'], expected)
                self.assertNotIn('fixture-secret', receipt + result.stdout + result.stderr)
                log = output / 'preparation.log'
                if log.exists():
                    self.assertNotIn('fixture-secret', log.read_text())
