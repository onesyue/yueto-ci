"""Board local lifecycle negative controls; never contacts Docker or databases."""
import copy
import contextlib
import io
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
LOCAL = importlib.import_module('ci_check_board_local')
ROLE = importlib.import_module('ci_check_board_role')


class BoardLocal(unittest.TestCase):
    def test_native_planner_and_workflow_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            sha = json.loads((ROOT / 'native-node-contract.json').read_text())['yueboard_contract_pin']
            roles = LOCAL.plan(ROOT, sha, output)
            expected = json.loads(subprocess.check_output(['bash', str(ROOT / 'scripts/plan-build-targets.sh'), 'yueboard', sha]))
            self.assertEqual(roles, [r['board_role'] for r in expected['validation_matrix']])
            result = json.loads((output / 'targets.json').read_text())
            self.assertEqual(result['matrix'], [])
            self.assertFalse(result['has_builds'])
            contract = LOCAL.workflow_contract(ROOT)
            self.assertIn('@127.0.0.1:5432/', contract['environments']['postgres']['YUEBOARD_TEST_DATABASE_URL'])
            self.assertNotIn('YUEBOARD_MIGRATION_TEST_ALLOW_RESET', contract['environments']['postgres'])
            self.assertIn('YUEBOARD_MIGRATION_TEST_ALLOW_RESET', contract['environments']['migration'])
            self.assertEqual(set(contract['environments']['clean']), {'YUEBOARD_ADMIN_DATABASE_URL', 'CLEAN_PG_DSN'})

    def test_unknown_metadata_and_missing_steps_fail(self):
        workflow = yaml.safe_load((ROOT / '.github/workflows/build.yml').read_text())
        for mutation in ('expression', 'missing', 'secret', 'image', 'health'):
            value = copy.deepcopy(workflow)
            job = value['jobs']['validate']
            step = next(s for s in job['steps'] if s.get('name') == LOCAL.STEPS['postgres'])
            if mutation == 'expression': step['env']['YUEBOARD_TEST_DATABASE_URL'] = '${{ secrets.DATABASE }}'
            if mutation == 'missing': job['steps'].remove(step)
            if mutation == 'secret': step['env']['GITHUB_TOKEN'] = 'literal'
            if mutation == 'image': job['services']['postgres']['image'] = 'postgres:latest'
            if mutation == 'health': job['services']['postgres']['options'] += ' --privileged'
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / '.github/workflows').mkdir(parents=True)
                (root / '.github/workflows/build.yml').write_text(yaml.safe_dump(value))
                with self.assertRaises(ValueError): LOCAL.workflow_contract(root)

    def test_planner_never_inherits_preparation_credentials(self):
        with patch.dict(os.environ, {'GH_TOKEN': 'secret', 'GITHUB_TOKEN': 'secret', 'GIT_CONFIG_COUNT': '1',
                                     'GIT_CONFIG_KEY_0': 'credential.helper', 'PGOPTIONS': 'redirect'}):
            env = LOCAL.planner_environment()
            self.assertNotIn('GH_TOKEN', env)
            self.assertNotIn('GIT_CONFIG_COUNT', env)
            self.assertNotIn('PGOPTIONS', env)
            self.assertEqual(env['GIT_CONFIG_GLOBAL'], '/dev/null')
            with tempfile.TemporaryDirectory() as directory:
                # Real native planner and authorizer run with the sanitized env.
                self.assertEqual(len(LOCAL.plan(ROOT, 'a'*40, Path(directory))), 7)

    def test_planner_rejects_role_identity_mutations(self):
        raw = json.loads(subprocess.check_output(['bash', str(ROOT / 'scripts/plan-build-targets.sh'), 'yueboard', 'a'*40]))
        for mutation in ('missing', 'duplicate', 'repo', 'ref', 'role'):
            value = copy.deepcopy(raw)
            if mutation == 'missing': value['validation_matrix'].pop()
            if mutation == 'duplicate': value['validation_matrix'][0] = value['validation_matrix'][1]
            if mutation == 'repo': value['validation_matrix'][0]['repo'] = 'onesyue/yueops'
            if mutation == 'ref': value['validation_matrix'][0]['ref'] = 'b'*40
            if mutation == 'role': value['validation_matrix'][0]['board_role'] = '../escape'
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory, patch.object(LOCAL.subprocess, 'check_output', return_value=json.dumps(value)):
                with self.assertRaises(ValueError): LOCAL.plan(ROOT, 'a'*40, Path(directory))

    def test_outer_records_all_roles_but_infrastructure_is_incomplete(self):
        for mode in ('pass', 'source-fail', 'infra', 'missing-log', 'missing-result', 'wrong-result'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source, policy, output = root/'source', root/'policy', root/'output'
                source.mkdir(); policy.mkdir()
                roles = ['quality', 'race', 'postgres', 'migration', 'frontends', 'components', 'e2e']
                commands = []
                stdout = io.StringIO()
                diagnostic = 'internal/platform/entrysalt/delivery.go:168:3: redundant nil check (S1009)'
                def execute(command, log, receipt):
                    commands.append(command)
                    role = log.parent.name
                    if mode != 'missing-log': log.write_text(diagnostic + '\n' + diagnostic + '\n' if mode == 'source-fail' and role == 'quality' else 'role executed\n')
                    code = 17 if mode == 'source-fail' and role == 'quality' else 2 if mode == 'infra' else 0
                    if mode != 'missing-result':
                        (log.parent/'role-result.json').write_text(json.dumps({'role': 'other' if mode == 'wrong-result' else role,
                            'source': 'a'*40, 'policy': 'b'*40, 'complete': mode != 'infra', 'exit_code': code}))
                    return code
                with contextlib.redirect_stdout(stdout), patch.object(LOCAL, 'checkout'), patch.object(LOCAL, 'plan', return_value=roles), patch.object(LOCAL, 'workflow_contract', return_value={}), patch.object(LOCAL, 'execute_container', side_effect=execute), patch.object(LOCAL.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)):
                    if mode.startswith('missing') or mode == 'wrong-result':
                        with self.assertRaises((OSError, ValueError)): LOCAL.run(source, policy, 'a'*40, 'b'*40, output)
                    else:
                        code = LOCAL.run(source, policy, 'a'*40, 'b'*40, output)
                        self.assertEqual(code, 2 if mode == 'infra' else 1 if mode == 'source-fail' else 0)
                        self.assertEqual(len(commands), 7)
                        state = json.loads((output/'execution.json').read_text())
                        self.assertEqual(state['complete'], mode != 'infra')
                        expected_failures = diagnostic + '\n' if mode == 'source-fail' else ''
                        self.assertEqual(stdout.getvalue(), expected_failures)
                        self.assertEqual((output/'failures.txt').read_text(), expected_failures)
                for command in commands:
                    text = ' '.join(command)
                    self.assertNotIn('/var/run/docker.sock', text)
                    self.assertNotIn('GH_TOKEN', text)
                    mounts = [command[i+1] for i, item in enumerate(command) if item == '-v']
                    self.assertEqual(len(mounts), 3)
                    self.assertTrue(mounts[0].endswith(':ro') and mounts[1].endswith(':ro'))
                    self.assertNotIn(f'{output}:{output}:rw', mounts)


class BoardRole(unittest.TestCase):
    def fixture(self, role, mode='ok', layout='workspace'):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        job = Path(directory.name)
        source = job/'source'; source.mkdir()
        temp = job/'temp'; temp.mkdir()
        (source/'.ci-policy').mkdir()
        (job/'contract.json').write_text(json.dumps(LOCAL.workflow_contract(ROOT)))
        env = {'CI_CHECK_JOB': str(job), 'GITHUB_WORKSPACE': str(source), 'RUNNER_TEMP': str(temp),
               'CI_CHECK_SOURCE_SHA': 'a'*40, 'CI_CHECK_POLICY_SHA': 'b'*40, 'BOARD_ROLE': role,
               'YUE_CI_PYTHON': sys.executable, 'PATH': os.environ['PATH'], 'HOME': str(job)}
        calls = []
        pg = 'f'*64
        def capture(command, env):
            calls.append((command, env))
            if command[0] == 'git': return 'b'*40 if '.ci-policy' in command[3] else 'a'*40
            if command[:2] == ['docker', 'create']: return 'bad-id' if mode == 'bad-id' else pg
            if command[:2] == ['docker', 'inspect']: return 'unhealthy' if mode == 'health' else 'healthy'
            raise AssertionError(command)
        def run(command, env, **kwargs):
            calls.append((command, env))
            if mode == 'diagnostic' and 'board-postgres-diagnostics.sh' in command[1]: raise subprocess.CalledProcessError(19, command)
            if mode == 'start' and command[:2] == ['docker', 'start']: raise subprocess.CalledProcessError(23, command)
            if mode == 'logs' and command[:2] == ['docker', 'logs']: raise subprocess.CalledProcessError(29, command)
            if mode == 'rm' and command[:2] == ['docker', 'rm']: raise subprocess.CalledProcessError(31, command)
            if mode == 'executor-infra' and any(name in command[1] for name in ('board-validation.sh', 'board-validation-output.py')):
                raise subprocess.CalledProcessError(2, command)
            if 'board-validation-output.py' in command[1]:
                phase = command[command.index('--frontend-phase')+1]
                if phase == 'prepare': Path(env['GITHUB_OUTPUT']).write_text('layout='+layout+'\n')
                if mode in ('source', 'report') and phase == 'test':
                    artifact = source/'test/e2e/test-results'; artifact.mkdir(parents=True)
                    if mode == 'report': (artifact/'escape').symlink_to(job/'contract.json')
                    raise subprocess.CalledProcessError(17, command)
            if mode == 'source' and 'board-validation.sh' in command[1]: raise subprocess.CalledProcessError(17, command)
            return subprocess.CompletedProcess(command, 0)
        previous = Path.cwd()
        try:
            with patch.dict(os.environ, env, clear=True), patch.object(ROLE, 'capture', side_effect=capture), patch.object(ROLE, 'toolchain', side_effect=ValueError('missing Buf') if mode=='tool' else None), patch.object(ROLE.subprocess, 'run', side_effect=run):
                status = ROLE.main()
        finally:
            os.chdir(previous)
        return status, calls, json.loads((job/'role-result.json').read_text()), job

    def test_all_roles_reach_shared_engine_and_distinct_phase_environments(self):
        for role in ('quality', 'race', 'postgres', 'migration', 'frontends', 'components', 'e2e'):
            with self.subTest(role=role):
                status, calls, receipt, _ = self.fixture(role)
                self.assertEqual(status, 0)
                self.assertTrue(receipt['complete'])
                engines = [(c,e) for c,e in calls if 'board-validation.sh' in c[1]]
                if role == 'postgres':
                    self.assertEqual([c[2] for c,e in engines], ['postgres', 'postgres-clean'])
                    self.assertNotIn('CLEAN_PG_DSN', engines[0][1])
                    self.assertNotIn('YUEBOARD_MIGRATION_TEST_ALLOW_RESET', engines[0][1])
                    self.assertNotIn('YUEBOARD_TEST_DATABASE_URL', engines[1][1])
                    self.assertNotIn('--receipt', engines[1][0])
                if role == 'migration': self.assertIn('YUEBOARD_MIGRATION_TEST_ALLOW_RESET', engines[0][1])
                for command, env in calls:
                    self.assertNotIn('GH_TOKEN', env)
                    self.assertNotIn('PGOPTIONS', env)
                    self.assertNotIn('YUEBOARD_TOKEN_ENC_KEYS', env)
                    if command[:2] == ['docker', 'rm']: self.assertEqual(command, ['docker', 'rm', '--force', 'f'*64])

    def test_infrastructure_never_counts_complete_and_owned_pg_is_cleaned(self):
        for mode in ('tool', 'bad-id', 'start', 'health', 'diagnostic', 'logs', 'rm'):
            with self.subTest(mode=mode):
                status, calls, receipt, _ = self.fixture('postgres', mode)
                self.assertNotEqual(status, 0)
                self.assertFalse(receipt['complete'])
                if mode not in ('tool', 'bad-id'):
                    self.assertIn(['docker', 'rm', '--force', 'f'*64], [c for c,e in calls])
                if mode in ('tool', 'bad-id', 'start', 'health', 'diagnostic'):
                    self.assertFalse(any('board-validation.sh' in c[1] for c,e in calls))

    def test_source_failure_preserved_and_e2e_report_failure_cannot_skip_cleanup(self):
        for role in ('quality', 'postgres', 'e2e'):
            status, calls, receipt, job = self.fixture(role, 'source')
            self.assertEqual(status, 17)
            self.assertTrue(receipt['complete'])
            if role == 'e2e': self.assertTrue((job/'e2e-report/test-results').is_dir())
        status, calls, receipt, _ = self.fixture('e2e', 'report')
        self.assertEqual(status, 2)
        self.assertFalse(receipt['complete'])
        self.assertEqual(receipt['validation_exit_code'], 17)
        self.assertIn(['docker', 'rm', '--force', 'f'*64], [c for c,e in calls])

    def test_executor_infrastructure_exit_is_incomplete(self):
        for role in ('quality', 'postgres', 'frontends', 'e2e'):
            with self.subTest(role=role):
                status, calls, receipt, _ = self.fixture(role, 'executor-infra')
                self.assertEqual(status, 2)
                self.assertFalse(receipt['complete'])
                self.assertEqual(receipt['validation_exit_code'], 2)
                if role in ('postgres', 'e2e'):
                    self.assertIn(['docker', 'rm', '--force', 'f'*64], [c for c,e in calls])

    def test_legacy_retains_original_phase_conditions(self):
        for role in ('frontends', 'components', 'e2e'):
            status, calls, receipt, job = self.fixture(role, layout='legacy')
            self.assertEqual(status, 0)
            phases = [c[c.index('--frontend-phase')+1] for c,e in calls if '--frontend-phase' in c]
            self.assertEqual(phases, ['prepare', 'design'] if role == 'frontends' else ['prepare'])
            self.assertFalse((job/'e2e-report').exists())

    def test_toolchain_checks_workflow_versions_and_buf_bytes(self):
        contract = LOCAL.workflow_contract(ROOT)
        with tempfile.TemporaryDirectory() as directory:
            buf = Path(directory)/'buf'; buf.write_bytes(b'fixture')
            contract['buf_sha256'] = hashlib.sha256(buf.read_bytes()).hexdigest()
            for mode in ('ok', 'go', 'node', 'buf-version', 'buf-bytes'):
                def capture(command, env):
                    if command[0] == 'go': return 'bad' if mode=='go' else 'go'+contract['go']
                    if command[0] == 'node': return 'v0.1' if mode=='node' else 'v'+contract['node']+'.1'
                    return 'bad' if mode=='buf-version' else contract['buf']
                expected = dict(contract)
                if mode == 'buf-bytes': expected['buf_sha256'] = '0'*64
                with patch.object(ROLE, 'capture', side_effect=capture), patch.object(ROLE.shutil, 'which', return_value=str(buf)):
                    if mode=='ok': ROLE.toolchain(expected, {})
                    else:
                        with self.assertRaises(ValueError): ROLE.toolchain(expected, {})


class BoardBoundary(unittest.TestCase):
    def test_real_checkout_identity_and_credential_rejections(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()
            git('init', '-q')
            (root/'source').write_text('fixture')
            git('add', 'source')
            git('-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid',
                '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture')
            sha = git('rev-parse', 'HEAD')
            git('remote', 'add', 'origin', 'https://github.com/onesyue/yueboard.git')
            git('update-ref', 'refs/remotes/origin/master', sha)
            LOCAL.checkout(root, 'yueboard', sha)
            with self.assertRaises(ValueError): LOCAL.checkout(root, 'yueboard', 'f'*40)
            with self.assertRaises(ValueError): LOCAL.checkout(root, 'yueops', sha)
            (root/'source').write_text('dirty')
            with self.assertRaises(ValueError): LOCAL.checkout(root, 'yueboard', sha)
            git('checkout', '--', 'source')
            for key in ('credential.helper', 'http.https://github.com/.extraheader', 'include.path'):
                git('config', '--local', key, '/nonexistent-fixture')
                with self.assertRaises(ValueError): LOCAL.checkout(root, 'yueboard', sha)
                git('config', '--local', '--unset-all', key)
            git('update-ref', '-d', 'refs/remotes/origin/master')
            with self.assertRaises(subprocess.CalledProcessError): LOCAL.checkout(root, 'yueboard', sha)

    def test_real_cli_routes_only_board_and_preserves_failure_cleanup(self):
        for status in (0, 23):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); binpath = root/'bin'; binpath.mkdir()
                log = root/'calls'
                for tool in ('git', 'docker', 'python3'):
                    program = binpath/tool
                    program.write_text('#!' + sys.executable + '\n' + '''import json, os, sys
from pathlib import Path
name=Path(sys.argv[0]).name; args=sys.argv[1:]
with open(os.environ['FIXTURE_LOG'],'a') as f: f.write(json.dumps([name,args])+'\\n')
if name=='git':
 if args[0]=='clone': Path(args[-1]).mkdir(parents=True)
 elif 'rev-parse' in args: print('b'*40)
elif name=='python3':
 assert args[0].endswith('/scripts/ci_check_board_local.py'), args
 sys.exit(int(os.environ['FIXTURE_EXIT']))
''')
                    program.chmod(0o755)
                env = dict(os.environ, PATH=str(binpath)+os.pathsep+os.environ['PATH'],
                           FIXTURE_LOG=str(log), FIXTURE_EXIT=str(status), CI_CHECK_OUTPUT=str(root/'output'))
                env.pop('CI_CHECK_MIGRATION_BASE', None)
                result = subprocess.run(['bash', str(ROOT/'scripts/ci-check.sh'), 'yueboard', 'a'*40, '--local'],
                                        env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, status, result.stderr)
                calls = [json.loads(line) for line in log.read_text().splitlines()]
                clones = [args for name,args in calls if name=='git' and args[0]=='clone']
                self.assertEqual(len(clones), 2)
                self.assertFalse(any('yueops' in ' '.join(args) for name,args in calls))
                args = next(args for name,args in calls if name=='python3')
                self.assertEqual(args[args.index('--source-sha')+1], 'a'*40)
                self.assertEqual(args[args.index('--policy-sha')+1], 'b'*40)
                self.assertEqual(list((root/'output').glob('checkouts.*')), [])

    def test_real_private_daemon_shell_stops_only_owned_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sudo = root/'sudo'
            sudo.write_text('#!' + sys.executable + '\n' + '''import os, signal, sys, time
from pathlib import Path
with open(os.environ['FIXTURE_LOG'],'a') as f: f.write(' '.join(sys.argv[1:])+'\\n')
if sys.argv[1]=='dockerd': time.sleep(30)
else:
 assert sys.argv[1:3]==['kill','-TERM']
 os.kill(int(sys.argv[3]), signal.SIGTERM)
''')
            sudo.chmod(0o755)
            timeout = root/'timeout'; timeout.write_text('#!/bin/sh\nexit 0\n'); timeout.chmod(0o755)
            env = dict(os.environ, PATH=str(root)+os.pathsep+os.environ['PATH'], RUNNER_TEMP=str(root), FIXTURE_LOG=str(root/'calls'))
            body = 'set -euo pipefail\nsource "$1"\ntrap ci_check_daemon_stop EXIT\nci_check_daemon_start\nprintf "%s\\n" "$daemon_pid" > "$RUNNER_TEMP/owned-pid"\n'
            result = subprocess.run(['bash', '-c', body, '--', str(ROOT/'scripts/ci-check-private-daemon.sh')], env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            pid = int((root/'owned-pid').read_text())
            self.assertIn('kill -TERM '+str(pid), (root/'calls').read_text())
            with self.assertRaises(ProcessLookupError): os.kill(pid, 0)
