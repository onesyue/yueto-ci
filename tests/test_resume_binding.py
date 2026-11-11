"""Exact API objects, real Git/Docker inputs and signed evidence resume controls."""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('resume_binding', ROOT / 'scripts/resume-binding.py')
assert SPEC is not None and SPEC.loader is not None
B = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B)


class Authority(B.GitHub):
    def __init__(self):
        self.responses = {}
        self.archives = {}
        self.certificates = {}
        self.counter = 100

    def get(self, path):
        return copy.deepcopy(self.responses[path])

    def raw(self, path):
        return self.archives[path]

    def provenance(self, candidate):
        B.verify_provenance(self.certificates[candidate['service']], candidate)

    def add_artifact(self, run, policy, name, documents):
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            for filename, value in documents.items():
                archive.writestr(filename, json.dumps(value, sort_keys=True))
        raw = output.getvalue()
        self.counter += 1
        item = {'id': self.counter, 'name': name, 'expired': False, 'digest': 'sha256:' + B.sha(raw),
                'workflow_run': {'id': int(run), 'head_sha': policy}}
        self.archives[f'actions/artifacts/{self.counter}/zip'] = raw
        page = self.responses.setdefault(f'actions/runs/{run}/artifacts?per_page=100&page=1',
                                         {'total_count': 0, 'artifacts': []})
        page['artifacts'].append(item)
        page['total_count'] += 1
        return item

    def policy_object(self, policy, path, raw):
        self.responses[f'contents/{path}?ref={policy}'] = {
            'encoding': 'base64', 'content': base64.b64encode(raw).decode(),
            'sha': hashlib.sha1(f'blob {len(raw)}\0'.encode() + raw).hexdigest()}

    def run(self, run, attempt, policy, names, conclusion='failure'):
        self.responses[f'actions/runs/{run}/attempts/{attempt}'] = {
            'id': int(run), 'run_attempt': int(attempt), 'event': 'workflow_dispatch',
            'head_branch': 'master', 'path': '.github/workflows/build.yml', 'head_sha': policy,
            'status': 'completed', 'conclusion': conclusion}
        jobs = [{'id': n + 1, 'run_id': int(run), 'run_attempt': int(attempt), 'head_sha': policy,
                 'name': name, 'status': 'completed', 'conclusion': 'success'} for n, name in enumerate(names)]
        self.responses[f'actions/runs/{run}/attempts/{attempt}/jobs?per_page=100&page=1'] = {
            'total_count': len(jobs), 'jobs': jobs}


class ResumeBinding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from test_source_evidence import SourceEvidence
        cls.Owner = SourceEvidence
        cls.Owner.setUpClass()
        cls.addClassCleanup(cls.Owner.doClassCleanups)

    def setUp(self):
        from test_ops_shard_workflow import OpsShardWorkflow
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.owner = self.Owner()
        self.owner.setUp()
        self.addCleanup(self.owner.doCleanups)
        self.workflow = OpsShardWorkflow()
        self.workflow.setUp()
        self.addCleanup(self.workflow.doCleanups)
        self.source = self.workflow.source
        (self.source / 'app.py').write_text('value = 1\n')
        fp = B.load('input-fingerprint')
        self.entries = fp.load_services()
        for service in B.OPS:
            target = self.source / self.entries[service]['dockerfile']
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('FROM scratch\nCOPY app.py /app.py\n')
        self.workflow.fixture.git(self.source, 'add', 'app.py', *[self.entries[s]['dockerfile'] for s in B.OPS])
        self.workflow.fixture.commit(self.source)
        self.old_source = self.workflow.fixture.git(self.source, 'rev-parse', 'HEAD').stdout.strip()
        self.workflow.baseline['context'] = {'platform': 'linux', 'uid': 1001}
        self.workflow.baseline['reviewed_hosted'] = {'schema': 1, 'context': {'platform': 'linux', 'uid': 1001},
                                                   'runner': {'runner_os': 'Linux', 'runner_arch': 'X64'}, 'cases': {}}
        (self.workflow.policy / 'ops-pytest-skip-baseline.json').write_text(json.dumps(self.workflow.baseline))
        self.workflow.fixture.git(self.workflow.policy, 'add', 'ops-pytest-skip-baseline.json')
        self.workflow.fixture.commit(self.workflow.policy)
        self.exported = self.workflow.consumer.export_source_baseline(self.source, self.old_source)['baseline']
        self.exported['context'] = {'platform': 'linux', 'uid': 1001}
        self.evidence = B.load('source_evidence')
        self.evidence.ROOT = self.owner.policy.parent
        original_load = B.load
        self.addCleanup(patch.stopall)
        patcher = patch.object(B, 'load', side_effect=lambda name: self.evidence if name == 'source_evidence' else original_load(name))
        patcher.start()
        self.new_source = self.enroll()
        shutil.copytree(self.owner.policy, self.workflow.policy / 'policy')
        self.workflow.fixture.git(self.workflow.policy, 'add', 'policy')
        self.workflow.fixture.commit(self.workflow.policy)
        self.policy = self.workflow.fixture.git(self.workflow.policy, 'rev-parse', 'HEAD').stdout.strip()
        self.args = argparse.Namespace(source=self.source, build_run_id='101', build_attempt='2', build_source=self.old_source,
                                       evidence_source=self.new_source, policy_sha=self.policy, service='yueops',
                                       board=self.workflow.board_sha, migration_base='b' * 40,
                                       binding=None, candidate=None, run_id='202', attempt='1')
        self.old_policy = 'a' * 40
        self.api = Authority()
        self.api.run('101', '2', self.old_policy, ['plan', *[f'candidate-{s}' for s in sorted(B.OPS)]])
        self.api.policy_object(self.old_policy, 'services.json', (ROOT / 'services.json').read_bytes())
        self.api.policy_object(self.old_policy, '.github/workflows/build.yml', (ROOT / '.github/workflows/build.yml').read_bytes())
        self.candidates = {}
        for index, service in enumerate(sorted(B.OPS), 1):
            candidate = {'schema': 1, 'service': service, 'repository': 'onesyue/yueops', 'source_sha': self.old_source,
                         'workflow_sha': self.old_policy, 'run_id': '101', 'run_attempt': '2',
                         'image': f'ghcr.io/onesyue/{service}', 'digest': 'sha256:' + str(index) * 64}
            self.candidates[service] = candidate
            context = B.build_context(candidate, self.source, self.args.board, self.args.migration_base)
            self.api.add_artifact('101', self.old_policy, f'candidate-101-2-{service}',
                                  {'candidate.json': candidate, 'candidate-context.json': context})
            self.api.certificates[service] = [{'verificationResult': {
                'signature': {'certificate': {
                    'buildSignerURI': 'https://github.com/onesyue/yueto-ci/.github/workflows/build.yml@refs/heads/master',
                    'sourceRepositoryRef': 'refs/heads/master', 'buildSignerDigest': self.old_policy,
                    'runInvocationURI': 'https://github.com/onesyue/yueto-ci/actions/runs/101/attempts/2'}},
                'statement': {'subject': [{'digest': {'sha256': candidate['digest'][7:]}}]}}}]

    def enroll(self):
        code = self.workflow.fixture.git(self.source, 'rev-parse', 'HEAD').stdout.strip()
        tree = {path: value for path, value in self.evidence.tree_inputs(self.source, code).items()
                if path not in self.evidence.EVIDENCE_PATHS}
        digest = self.evidence.digest(self.evidence.canonical(tree))
        values = {self.evidence.INPUTS: {'schema': 1, 'inputs': tree, 'inputs_sha256': digest},
                  self.evidence.BASELINE: self.exported | {'inputs_sha256': digest}}
        for name, value in values.items():
            target = self.source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(value))
        subprocess.run(['git', '-C', str(self.source), 'add', *values], check=True, capture_output=True)
        assert self.owner.gpg is not None
        subprocess.run(['git', '-C', str(self.source), '-c', 'user.name=Fixture', '-c', 'user.email=f@example.invalid',
                        '-c', 'gpg.program=' + self.owner.gpg, '-c', 'user.signingkey=' + self.owner.fingerprint,
                        'commit', '-S', '-qm', 'enrolled evidence'], env=self.owner.env, check=True, capture_output=True)
        return subprocess.check_output(['git', '-C', str(self.source), 'rev-parse', 'HEAD']).decode().strip()

    def test_real_signed_evidence_reuses_only_equivalent_original_inputs(self):
        value = B.inspect(self.args, self.api)
        self.assertEqual(value['original_build']['source_revision'], self.old_source)
        self.assertEqual(value['validation']['source_revision'], self.new_source)
        self.assertIsNone(value['validation']['run_id'])
        self.assertEqual(set(value['services']), B.OPS)
        self.assertEqual(B.check_binding(value), value)
        with patch.dict(os.environ, GITHUB_RUN_ID='202', GITHUB_RUN_ATTEMPT='1', GITHUB_SHA=self.policy):
            prepared = B.prepare(self.args, self.api)
        self.assertEqual(prepared['request_sha256'], value['binding_sha256'])
        self.assertEqual(prepared['validation']['run_id'], '202')
        self.assertEqual(prepared['original_build']['run_id'], '101')

    def test_wrong_run_attempt_service_context_and_provenance_refused(self):
        for change in ({'build_source': 'f' * 40}, {'build_attempt': '3'}, {'service': 'yueboard'},
                       {'board': 'c' * 40}, {'migration_base': 'd' * 40}):
            with self.subTest(change=change), self.assertRaises((ValueError, KeyError)):
                B.inspect(argparse.Namespace(**(vars(self.args) | change)), self.api)
        self.api.certificates['yue-bot'][0]['verificationResult']['signature']['certificate']['runInvocationURI'] = \
            'https://github.com/onesyue/yueto-ci/actions/runs/101/attempts/1'
        with self.assertRaisesRegex(ValueError, 'provenance'):
            B.inspect(self.args, self.api)

    def test_artifact_expiry_duplicate_digest_and_context_loss_are_rejected(self):
        path = 'actions/runs/101/artifacts?per_page=100&page=1'
        original = copy.deepcopy(self.api.responses[path])
        for mutation in ('expired', 'duplicate', 'digest', 'missing-context'):
            self.api.responses[path] = copy.deepcopy(original)
            page = self.api.responses[path]
            item = page['artifacts'][0]
            if mutation == 'expired':
                item['expired'] = True
            elif mutation == 'duplicate':
                page['artifacts'].append(item | {'id': 999})
                page['total_count'] += 1
            elif mutation == 'digest':
                item['digest'] = 'sha256:' + '0' * 64
            else:
                service = min(B.OPS)
                page['artifacts'] = []
                page['total_count'] = 0
                self.api.add_artifact('101', self.old_policy, f'candidate-101-2-{service}',
                                      {'candidate.json': self.candidates[service]})
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                B.inspect(self.args, self.api)

    def test_real_docker_input_change_is_not_hidden_by_signed_evidence(self):
        (self.source / 'app.py').write_text('value = 2\n')
        self.workflow.fixture.git(self.source, 'add', 'app.py')
        self.workflow.fixture.commit(self.source)
        self.args.evidence_source = self.enroll()
        with self.assertRaisesRegex(ValueError, 'inputs or recipe'):
            B.inspect(self.args, self.api)

    def test_future_copy_of_evidence_is_not_unconditionally_excluded(self):
        fp = B.load('input-fingerprint')
        entry = self.entries['yueops-web']
        old = fp.compute(B.exact_source(fp, self.source), self.old_source, entry)
        self.assertEqual(fp.compare(old, fp.compute(B.exact_source(fp, self.source), self.new_source, entry)), 'unchanged')
        dockerfile = self.source / entry['dockerfile']
        dockerfile.write_text('FROM scratch\nCOPY app.py /app.py\nCOPY ci/evidence /evidence\n')
        self.workflow.fixture.git(self.source, 'add', entry['dockerfile'])
        self.workflow.fixture.commit(self.source)
        start = self.enroll()
        (self.source / self.evidence.BASELINE).write_text((self.source / self.evidence.BASELINE).read_text() + '\n')
        self.workflow.fixture.git(self.source, 'add', self.evidence.BASELINE)
        self.workflow.fixture.commit(self.source)
        finish = self.workflow.fixture.git(self.source, 'rev-parse', 'HEAD').stdout.strip()
        self.assertEqual(fp.compare(fp.compute(B.exact_source(fp, self.source), start, entry),
                                    fp.compute(B.exact_source(fp, self.source), finish, entry)), 'changed')

    def test_isolated_archive_cli_uses_authoritative_api_and_no_policy_git_directory(self):
        archive = self.directory / 'exported-policy'
        shutil.copytree(ROOT / 'scripts', archive / 'scripts')
        shutil.copytree(self.owner.policy, archive / 'policy')
        shutil.copyfile(ROOT / 'services.json', archive / 'services.json')
        (archive / '.github/workflows').mkdir(parents=True)
        shutil.copyfile(ROOT / '.github/workflows/build.yml', archive / '.github/workflows/build.yml')
        self.assertFalse((archive / '.git').exists())
        fixture = self.directory / 'authority.json'
        data = {'responses': self.api.responses, 'archives': {k: base64.b64encode(v).decode() for k, v in self.api.archives.items()},
                'certificates': self.api.certificates}
        fixture.write_text(json.dumps(data))
        binary = self.directory / 'bin'
        binary.mkdir()
        gh = binary / 'gh'
        gh.write_text('#!' + sys.executable + '\n' + """import base64,json,os,sys
from pathlib import Path
value=json.loads(Path(os.environ['RESUME_API_FIXTURE']).read_text())
args=sys.argv[1:]
if args[:4]==['api','--method','GET',args[-1]]:
    path=args[-1].removeprefix('repos/onesyue/yueto-ci/')
    if path in value['archives']:
        sys.stdout.buffer.write(base64.b64decode(value['archives'][path]))
    else:
        print(json.dumps(value['responses'][path]))
elif args[:2]==['attestation','verify']:
    assert '--bundle-from-oci' in args
    service=args[2].split('/')[-1].split('@')[0]
    print(json.dumps(value['certificates'][service]))
else:
    raise SystemExit('unexpected side effect requested')
""")
        gh.chmod(0o755)
        argv = [sys.executable, '-I', str(archive / 'scripts/resume-binding.py'), 'inspect', '--source', str(self.source),
                '--build-run-id', '101', '--build-attempt', '2', '--build-source', self.old_source,
                '--evidence-source', self.new_source, '--policy-sha', self.policy, '--service', 'yueops',
                '--board', self.args.board, '--migration-base', self.args.migration_base]
        env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ['PATH'], RESUME_API_FIXTURE=str(fixture))
        result = subprocess.run(argv, env=env, text=True, capture_output=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), B.inspect(self.args, self.api))
        data['responses']['actions/runs/101/attempts/2']['head_branch'] = 'candidate'
        fixture.write_text(json.dumps(data))
        result = subprocess.run(argv, env=env, text=True, capture_output=True, timeout=30, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')

    def test_actual_dispatch_planner_rejects_partial_or_incompatible_resume(self):
        from test_hardening_20260927 import PlanPromotionGateTest
        planner = PlanPromotionGateTest()
        valid: dict[str, Any] = {'SERVICE': 'yueops', 'REF_OVERRIDE': 'b' * 40, 'MANUAL_PROMOTE': 'true',
                 'RESUME_BUILD_RUN_ID': '101', 'RESUME_BUILD_ATTEMPT': '2',
                 'RESUME_BUILD_SOURCE': 'a' * 40, 'RESUME_RUNNER': 'ubuntu-24.04'}
        result = planner.run_plan(**valid)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('resume=true', cast(Any, result).outputs)
        for changes in ({'RESUME_BUILD_ATTEMPT': ''}, {'RESUME_BUILD_SOURCE': 'master'},
                        {'SERVICE': 'yueboard'}, {'REF_OVERRIDE': 'master'},
                        {'RESUME_RUNNER': 'yue-local-release'}, {'MANUAL_PROMOTE': 'false'},
                        {'VALIDATION_ONLY': 'true'}, {'EVENT_NAME': 'repository_dispatch'}):
            with self.subTest(changes=changes):
                result = planner.run_plan(False, **(valid | changes))
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(cast(Any, result).outputs, '')

    def test_workflow_resume_cannot_build_and_requires_complete_validation(self):
        workflow = yaml.safe_load((ROOT / '.github/workflows/build.yml').read_text())
        jobs = workflow['jobs']
        self.assertEqual(json.loads((ROOT / 'resume-protocol.json').read_text()), {
            'schema': 1, 'protocol': 'ops-resume-publication-v1',
            'dispatch_inputs': ['resume_build_run_id', 'resume_build_attempt', 'resume_build_source'],
            'inspect_entry': 'scripts/resume-binding.py',
        })
        self.assertIn("needs.plan.outputs.resume != 'true'", jobs['build']['if'])
        for gate in ('needs.plan.result', 'needs.validate.result', 'needs.validation-evidence.result'):
            self.assertIn(gate + " == 'success'", jobs['publish']['if'])
        self.assertIn("needs.build.result == 'skipped'", jobs['publish']['if'])
        plan = next(s for s in jobs['plan']['steps'] if s.get('id') == 'plan')
        for field in ('RESUME_BUILD_RUN_ID', 'RESUME_BUILD_ATTEMPT', 'RESUME_BUILD_SOURCE'):
            self.assertIn(field, plan['env'])
        prepare = next(s for s in jobs['plan']['steps'] if s.get('id') == 'resume')
        self.assertIn('resume-binding.py prepare', prepare['run'])
        self.assertIn('--evidence-source "$EVIDENCE_SOURCE"', prepare['run'])
        self.assertIn('map(.ref = $source)', prepare['run'])
        login = next(s for s in jobs['plan']['steps'] if s.get('name') == 'Authenticate read-only original OCI proof retrieval')
        self.assertEqual(login['if'], "steps.plan.outputs.resume == 'true'")
        self.assertEqual(login['with']['password'], '${{ github.token }}')
        self.assertEqual(jobs['plan']['permissions']['packages'], 'read')

    @unittest.skipUnless(os.name == 'posix' and os.uname().sysname == 'Linux', 'actual native protocol join requires Linux')
    def test_actual_new_signed_full_join_and_authoritative_publication(self):
        w = self.workflow
        w.source_sha = self.new_source
        w.prefix = 'ops-shard-202-1-'
        w.env.update(GITHUB_SHA=self.policy, GITHUB_RUN_ID='202', GITHUB_RUN_ATTEMPT='1')
        for row in w.targets['matrix'] + w.targets['validation_matrix']:
            row['ref'] = self.new_source
        w.admission = w.call(w.consumer.expand, w.targets, w.source, w.board_sha, 'ubuntu-24.04', 4, 4)
        def join(result='success', expected=None):
            return w.call(w.consumer.join, w.admission, w.artifacts, result,
                          expected or w.admission['admission_sha256'], w.source)
        with patch.object(w, 'join', side_effect=join):
            verdict = w.full_bundle()
        self.assertEqual(verdict['status'], 'VALIDATION_MATRIX_COMPLETE')
        request = B.inspect(self.args, self.api)
        with patch.dict(os.environ, GITHUB_SHA=self.policy, GITHUB_RUN_ID='202', GITHUB_RUN_ATTEMPT='1'):
            binding = B.prepare(self.args, self.api)
        roles = w.consumer.role_order(w.admission['ops_plan'])
        names = ['plan', 'validation-evidence', *[f'validate-yueops-{r}' for r in roles], *sorted(B.OPS)]
        self.api.run('202', '1', self.policy, names, conclusion='success')
        self.api.add_artifact('202', self.policy, 'resume-binding-202-1', {'resume-binding.json': binding})
        self.api.add_artifact('202', self.policy, 'ops-admission-202-1', {'ops-admission.json': w.admission})
        self.api.add_artifact('202', self.policy, 'ops-validation-evidence-202-1', {'ops-validation-evidence-202-1.json': verdict})
        proof = B.validation_proof(self.api, binding, self.source)
        binding_path = self.directory / 'binding.json'
        binding_path.write_text(json.dumps(binding))
        real_load = B.load
        fingerprint = real_load('input-fingerprint')
        for service, row in request['services'].items():
            candidate_path = self.directory / (service + '.json')
            candidate_path.write_text(json.dumps(row['candidate']))
            publisher = argparse.Namespace(source=self.source, binding=binding_path, candidate=candidate_path, service=service)
            with patch.dict(os.environ, GITHUB_SHA=self.policy, GITHUB_RUN_ID='202', GITHUB_RUN_ATTEMPT='1',
                            GHCR_USER='fixture', GHCR_PASSWORD='fixture'), \
                 patch.object(fingerprint, 'ghcr_latest', return_value=(row['digest'], self.old_source)), \
                 patch.object(B, 'load', side_effect=lambda name: fingerprint if name == 'input-fingerprint' else real_load(name)):
                publication = B.publication(publisher, self.api)
            self.assertEqual(publication['source_revision'], self.old_source)
            self.assertEqual(publication['validation']['source_revision'], self.new_source)
            self.assertEqual(publication['verdict_sha256'], proof['verdict_sha256'])
            self.api.add_artifact('202', self.policy, f'resume-publication-202-1-{service}', {'resume-publication.json': publication})
        self.args.binding = self.directory / 'request.json'
        self.args.binding.write_text(json.dumps(request))
        result = B.verify_publication(self.args, self.api)
        self.assertEqual(result['publication']['run_id'], '202')
        self.assertEqual(result['original_build']['run_id'], '101')
        self.assertTrue(all(row['source_revision'] == self.old_source for row in result['services'].values()))
        jobs = self.api.responses['actions/runs/202/attempts/1/jobs?per_page=100&page=1']['jobs']
        next(j for j in jobs if j['name'] == 'validate-yueops-native')['conclusion'] = 'skipped'
        with self.assertRaisesRegex(ValueError, 'did not succeed'):
            B.verify_publication(self.args, self.api)
