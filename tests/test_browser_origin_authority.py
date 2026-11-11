"""The CI caller pins authority independently of generated source metadata."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import yaml
import test_credential_policy as credentials

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/build.yml'
AUTHORITY = 'd5f2b6b25477a2a3913bf7affef4bd6a822eec2a'
CONDITION = "matrix.validation == 'yueboard' || matrix.validation == 'yueops'"


def workflow():
    return yaml.safe_load(WORKFLOW.read_text())


class BrowserOriginAuthorityTest(unittest.TestCase):
    def assert_contract(self, data):
        self.assertEqual(data['env']['SECURITY_ORIGIN_AUTHORITY_REF'], AUTHORITY)
        triggers = data.get('on', data.get(True))
        self.assertNotIn('authority_ref', triggers['workflow_dispatch']['inputs'])
        steps = data['jobs']['validate']['steps']
        names = [s.get('name') for s in steps]
        checkout = steps[names.index('Checkout exact browser origin authority')]
        gate = steps[names.index('Require exact browser origin projections')]
        for step in (checkout, gate):
            self.assertEqual(step['if'], CONDITION)
            self.assertNotIn('continue-on-error', step)
        self.assertEqual(checkout['with']['repository'], 'onesyue/yueto')
        self.assertEqual(checkout['with']['ref'], '${{ env.SECURITY_ORIGIN_AUTHORITY_REF }}')
        self.assertEqual(checkout['with']['path'], '.ci-origin-authority')
        self.assertIs(checkout['with']['persist-credentials'], False)
        self.assertIs(checkout['with']['sparse-checkout-cone-mode'], False)
        self.assertEqual(checkout['with']['sparse-checkout'].splitlines(), ['/design/build-sources.mjs', '/design/sources/brand.json'])
        self.assertEqual(checkout['with']['token'], '${{ steps.source_token.outputs.token || secrets.YUETO_CI_PAT }}')
        self.assertEqual(gate['env'], {'ORIGIN_COMPONENT': '${{ matrix.validation }}'})
        self.assertLess(names.index('Set up Node'), names.index('Checkout exact browser origin authority'))
        self.assertLess(names.index('Checkout exact browser origin authority'), names.index('Require exact browser origin projections'))
        self.assertNotIn('permissions', data['jobs']['validate'])
        return gate['run']

    def test_reviewed_pin_checkout_scope_and_missing_gate_mutations(self):
        data = workflow()
        self.assert_contract(data)
        for mutation in ('branch', 'different-pin', 'persist', 'optional', 'partial-condition', 'missing-gate'):
            changed = copy.deepcopy(data)
            steps = changed['jobs']['validate']['steps']
            checkout = next(s for s in steps if s.get('name') == 'Checkout exact browser origin authority')
            gate = next(s for s in steps if s.get('name') == 'Require exact browser origin projections')
            if mutation == 'branch': checkout['with']['ref'] = 'master'
            elif mutation == 'different-pin': changed['env']['SECURITY_ORIGIN_AUTHORITY_REF'] = 'a' * 40
            elif mutation == 'persist': checkout['with']['persist-credentials'] = True
            elif mutation == 'optional': gate['continue-on-error'] = True
            elif mutation == 'partial-condition': gate['if'] = "matrix.validation == 'yueboard'"
            else: steps.remove(gate)
            with self.subTest(mutation=mutation), self.assertRaises((AssertionError, ValueError)):
                self.assert_contract(changed)

    def test_actual_shell_passes_pinned_authority_and_component_bytes_or_refuses(self):
        script = self.assert_contract(workflow())
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            calls = base / 'calls'
            node = base / 'node'
            node.write_text('#!' + sys.executable + '\n' + '''import json, os, sys
from pathlib import Path
Path(os.environ['CALLS']).write_text(json.dumps(sys.argv[1:]))
expected = ['.ci-origin-authority/design/build-sources.mjs', '--authority-ref='+os.environ['EXPECTED_AUTHORITY'], '--scope=security', '--repo='+os.environ['ORIGIN_COMPONENT']+'='+os.environ['GITHUB_WORKSPACE'], '--check']
if sys.argv[1:] != expected: sys.exit(71)
sys.exit(int(os.environ.get('CHECK_EXIT', '0')))
''')
            node.chmod(0o755)
            env = {**os.environ, 'PATH': str(base) + os.pathsep + os.environ['PATH'],
                   'CALLS': str(calls), 'GITHUB_WORKSPACE': str(base / 'component with spaces'),
                   'SECURITY_ORIGIN_AUTHORITY_REF': AUTHORITY, 'EXPECTED_AUTHORITY': AUTHORITY}
            def execute(body, component, **extra):
                calls.unlink(missing_ok=True)
                return subprocess.run(['bash', '-c', body], env={**env, 'ORIGIN_COMPONENT': component, **extra},
                                      capture_output=True, text=True, timeout=10)
            for component in ('yueboard', 'yueops'):
                result = execute(script, component)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(calls.read_text())[-1], '--check')
                self.assertEqual(execute(script, component, CHECK_EXIT='5').returncode, 5)
            self.assertNotEqual(execute(script, 'yuelink').returncode, 0)
            self.assertFalse(calls.exists())
            for old, new in [('--authority-ref="$SECURITY_ORIGIN_AUTHORITY_REF"', '--authority-ref=master'),
                             (' --check', ''), ('--repo="$ORIGIN_COMPONENT=$GITHUB_WORKSPACE"', '')]:
                with self.subTest(mutation=old):
                    self.assertIn(old, script)
                    self.assertNotEqual(execute(script.replace(old, new), 'yueboard').returncode, 0)

    def test_root_token_scope_cannot_leak_into_build_or_plan(self):
        texts = credentials._workflows()
        credentials.CredentialSwitchPolicyTest().test_every_app_token_is_switched_pinned_and_least_privilege()
        for job in ('plan', 'build', 'publish'):
            changed = dict(texts)
            prefix, tail = texts['build.yml'].split('\n  ' + job + ':\n', 1)
            changed['build.yml'] = prefix + '\n  ' + job + ':\n' + tail.replace(
                'repositories: yueboard,yue-node,yueops,yuelink,quic-go',
                'repositories: yueboard,yue-node,yueops,yuelink,quic-go,yueto', 1)
            with self.subTest(job=job), mock.patch.object(credentials, '_workflows', return_value=changed):
                with self.assertRaises(AssertionError):
                    credentials.CredentialSwitchPolicyTest().test_every_app_token_is_switched_pinned_and_least_privilege()
