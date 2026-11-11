"""Private PR validation uses the same worker, exact objects and real caller identity."""
import copy
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'scripts' / f'{name}.py')
    assert spec is not None and spec.loader is not None
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


GEN = module('generate-pr-validation')
INPUTS = module('pr-validation-inputs')
TIMING = module('pytest-timing')
SHARDS = module('pytest-shards')


class PrivatePRValidation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.source = 'a' * 40
        self.base = 'b' * 40
        self.policy = 'c' * 40
        self.merge = 'd' * 40
        self.event = {'repository': {'full_name': 'onesyue/yueops'}, 'pull_request': {
            'head': {'sha': self.source, 'repo': {'full_name': 'onesyue/yueops'}},
            'base': {'sha': self.base, 'repo': {'full_name': 'onesyue/yueops'}}}}
        self.event_path = self.path / 'event.json'
        self.event_path.write_text(json.dumps(self.event))
        self.env = {'GITHUB_EVENT_PATH': str(self.event_path), 'GITHUB_EVENT_NAME': 'pull_request',
                    'GITHUB_REPOSITORY': 'onesyue/yueops', 'GITHUB_SHA': self.merge,
                    'YUE_CI_PR_POLICY': self.policy}

    def test_real_caller_and_policy_are_distinct_and_required(self):
        value = TIMING.pr_workflow_identity(self.policy, self.env)
        self.assertEqual(value, {'workflow_repository': 'onesyue/yueops',
                                'workflow_revision': self.merge, 'pull_request_head': self.source})
        for change in ({'GITHUB_EVENT_NAME': 'pull_request_target'}, {'GITHUB_REPOSITORY': 'onesyue/yueto-ci'},
                       {'YUE_CI_PR_POLICY': 'f' * 40}, {'GITHUB_SHA': 'master'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                TIMING.pr_workflow_identity(self.policy, self.env | change)
        self.assertEqual(TIMING.pr_workflow_identity(self.policy, {}), {})

    def test_fork_or_unknown_dependency_context_rejected(self):
        for field in ('head', 'base'):
            event = copy.deepcopy(self.event)
            event['pull_request'][field]['repo']['full_name'] = 'elsewhere/yueops'
            self.event_path.write_text(json.dumps(event))
            with self.subTest(field=field), patch.dict(os.environ, self.env), self.assertRaises(ValueError):
                INPUTS.identities()

    def test_derived_worker_retains_all_canonical_runtime_steps(self):
        build = yaml.safe_load((ROOT / '.github/workflows/build.yml').read_text())
        generated = GEN.derive(build, self.policy)
        worker = generated['jobs']['validate']
        copied = worker['steps'][3:]
        expected = [s for s in build['jobs']['validate']['steps'][5:]
                    if s.get('name') != 'Verify yue-node signed fork tags']
        self.assertEqual(len(copied), len(expected))
        for actual, original in zip(copied, expected):
            if original.get('name') == 'Lint changed YueOps SQL migrations':
                original = copy.deepcopy(original)
                original['env']['MIGRATION_BASE'] = '${{ github.event.pull_request.base.sha }}'
            self.assertEqual(actual, original)
        self.assertFalse(worker['strategy']['fail-fast'])
        self.assertEqual(generated['permissions'], {'contents': 'read'})
        self.assertNotIn('inputs', generated['on']['workflow_call'])
        self.assertEqual(set(generated['jobs']), {'fetch', 'plan', 'yueops-pg18-toolchain',
                                                'validate', 'validation-evidence', 'complete'})
        for name, job in generated['jobs'].items():
            if name != 'fetch':
                self.assertNotIn('secrets.', json.dumps(job))
        self.assertIn("job[\"result\"] != \"success\"", generated['jobs']['complete']['steps'][0]['run'])
        self.assertEqual(generated['jobs']['validation-evidence']['steps'][3:],
                         build['jobs']['validation-evidence']['steps'][3:])

    def test_generated_workflow_and_frozen_policy_have_no_drift(self):
        pin = json.loads((ROOT / 'pr-validation-policy.json').read_text())['policy_revision']
        self.assertEqual((ROOT / '.github/workflows/ops-pr-validation.yml').read_text(), GEN.render(pin))
        # A future canonical planner, worker, trust anchor or baseline change
        # requires a reviewed policy-pin update, not a silently stale PR gate.
        result = subprocess.run(['git', '-C', str(ROOT), 'diff', '--exit-code', pin, '--',
                                 'scripts', 'policy', 'reviews', ':(top,glob)*.json',
                                 ':!pr-validation-policy.json', '.github/workflows/build.yml'],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, 'frozen PR policy differs from canonical validation inputs: ' + result.stderr)

    def test_actual_shallow_checkout_fetches_fixed_object_and_still_rejects_drift(self):
        # file:// forces Git's real depth-limited transport, not local object sharing.
        checkout = self.path / 'shallow'
        origin = self.path / 'detached-origin'
        pin = json.loads((ROOT / 'pr-validation-policy.json').read_text())['policy_revision']
        subprocess.run(['git', 'clone', '--quiet', '--depth=1', ROOT.as_uri(), str(origin)], check=True)
        subprocess.run(['git', '-C', str(origin), 'fetch', '--quiet', '--no-tags', '--depth=1',
                        'origin', f'{pin}:refs/ci/frozen-pr-policy'], check=True)
        subprocess.run(['git', '-C', str(origin), 'checkout', '--quiet', '--detach'], check=True)
        subprocess.run(['git', 'clone', '--quiet', '--depth=1', origin.as_uri(), str(checkout)], check=True)
        self.assertEqual(subprocess.check_output(['git', '-C', str(checkout), 'rev-parse',
                                                '--is-shallow-repository'], text=True).strip(), 'true')
        compare = ['git', '-C', str(checkout), 'diff', '--exit-code', pin, '--', 'scripts']
        missing = subprocess.run(compare, capture_output=True, text=True, check=False)
        self.assertEqual(missing.returncode, 128)
        self.assertIn(pin, missing.stderr)
        policy = yaml.safe_load((ROOT / '.github/workflows/policy-ci.yml').read_text())
        command = next(s['run'] for s in policy['jobs']['policy']['steps']
                       if s.get('name') == 'Fetch fixed PR policy object for drift verification')
        fetched = subprocess.run(['bash', '-c', command], cwd=checkout, capture_output=True, text=True, check=False)
        self.assertEqual(fetched.returncode, 0, fetched.stderr)
        self.assertEqual(subprocess.run(compare, capture_output=True, check=False).returncode, 0)
        with (checkout / 'scripts/pytest-shards.py').open('a') as stream:
            stream.write('\n# deliberate tracked policy drift\n')
        self.assertEqual(subprocess.run(compare, capture_output=True, check=False).returncode, 1)

    def test_pr_boundary_requires_bound_source_evidence(self):
        build = yaml.safe_load((ROOT / '.github/workflows/build.yml').read_text())
        generated = GEN.derive(build, self.policy)
        command = next(s['run'] for s in generated['jobs']['plan']['steps']
                       if s.get('id') == 'ops_plan').splitlines()[-1]
        for value, accepted in (({}, False), ({'source_evidence': {'status': 'BOUND_SOURCE_EVIDENCE',
                                                                 'admission': False}}, True)):
            (self.path / 'ops-admission.json').write_text(json.dumps(value))
            result = subprocess.run(['bash', '-c', command], env=dict(os.environ, RUNNER_TEMP=str(self.path)),
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode == 0, accepted, result.stderr)

    def test_new_worker_credential_is_rejected_by_generator(self):
        build = yaml.safe_load((ROOT / '.github/workflows/build.yml').read_text())
        build['jobs']['validate']['steps'].append({'name': 'unsafe', 'env': {'TOKEN': '${{ secrets.PUBLISH }}'}, 'run': 'true'})
        with self.assertRaisesRegex(ValueError, 'credential'):
            GEN.derive(build, self.policy)

    def test_git_bundle_roundtrip_has_no_credential_configuration_and_binds_event(self):
        repos = {}
        for name in ('source', 'board'):
            repo = self.path / name
            repo.mkdir()
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            (repo / 'payload').write_text(name)
            subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(repo), '-c', 'user.name=Fixture', '-c', 'user.email=f@example.invalid',
                            '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture'], check=True)
            repos[name] = repo
        ids = {name: INPUTS.git(repo, 'rev-parse', 'HEAD') for name, repo in repos.items()}
        ids['base'] = ids['source']
        bundle = self.path / 'bundle'
        with patch.object(INPUTS, 'identities', return_value=ids):
            INPUTS.pack(bundle, repos['source'], repos['board'])
            INPUTS.restore(bundle, self.path / 'restored', self.path / 'restored-board')
            self.assertEqual((self.path / 'restored/payload').read_text(), 'source')
            self.assertNotIn('credential', (self.path / 'restored/.git/config').read_text())
            (bundle / 'source.bundle').write_bytes((bundle / 'source.bundle').read_bytes() + b'bad')
            with self.assertRaisesRegex(ValueError, 'digest'):
                INPUTS.restore(bundle, self.path / 'bad', self.path / 'bad-board')
        with patch.object(INPUTS, 'identities', return_value=ids | {'source': 'e' * 40}), \
                self.assertRaisesRegex(ValueError, 'identity or digest'):
            INPUTS.restore(bundle, self.path / 'wrong', self.path / 'wrong-board')

    @unittest.skipUnless(os.name == 'posix' and os.uname().sysname == 'Linux', 'real full-role fixture requires Linux')
    def test_real_private_caller_full_role_join(self):
        from test_ops_shard_workflow import OpsShardWorkflow
        workflow = OpsShardWorkflow()
        workflow.setUp()
        self.addCleanup(workflow.doCleanups)
        event = copy.deepcopy(self.event)
        event['pull_request']['head']['sha'] = workflow.source_sha
        self.event_path.write_text(json.dumps(event))
        policy = workflow.env['GITHUB_SHA']
        workflow.env.update(self.env | {'YUE_CI_PR_POLICY': policy})
        workflow.admission = workflow.call(workflow.consumer.expand, workflow.targets,
                                           workflow.source, workflow.board_sha, 'ubuntu-24.04', 4, 4)
        self.assertEqual(workflow.admission['identity']['workflow_revision'], self.merge)
        self.assertEqual(workflow.admission['identity']['policy_revision'], policy)
        result = workflow.full_bundle()
        self.assertEqual(result['status'], 'VALIDATION_MATRIX_COMPLETE')
        altered = copy.deepcopy(workflow.admission)
        altered['identity']['pull_request_head'] = 'f' * 40
        altered.pop('admission_sha256')
        workflow.consumer.seal(altered, 'admission_sha256')
        with self.assertRaises(ValueError):
            workflow.call(workflow.consumer.envelope, altered)
