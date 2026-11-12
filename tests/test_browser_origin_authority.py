"""Validation reads the yueto root at run time and does not freeze its SHA."""
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
CONDITION = "matrix.validation == 'yueboard' || matrix.validation == 'yueops'"
CHECKOUT = 'Checkout the pinned yueto root'
GATE = 'Require exact browser origin projections'
RESOLVE = 'authority=$(git -C .ci-origin-authority rev-parse HEAD)'


def workflow():
    return yaml.safe_load(WORKFLOW.read_text())


class BrowserOriginAuthorityTest(unittest.TestCase):
    def assert_contract(self, data):
        self.assertNotIn('SECURITY_ORIGIN_AUTHORITY_REF', data.get('env', {}))
        triggers = data.get('on', data.get(True))
        self.assertNotIn('authority_ref', triggers['workflow_dispatch']['inputs'])
        steps = data['jobs']['validate']['steps']
        names = [s.get('name') for s in steps]
        checkout = steps[names.index(CHECKOUT)]
        gate = steps[names.index(GATE)]
        for step in (checkout, gate):
            self.assertEqual(step['if'], CONDITION)
            self.assertNotIn('continue-on-error', step)
        self.assertEqual(checkout['with']['repository'], 'onesyue/yueto')
        self.assertEqual(checkout['with']['ref'], 'master')
        self.assertNotIn('${{', checkout['with']['ref'])
        self.assertEqual(checkout['with']['path'], '.ci-origin-authority')
        self.assertIs(checkout['with']['persist-credentials'], False)
        self.assertIs(checkout['with']['sparse-checkout-cone-mode'], False)
        self.assertEqual(
            checkout['with']['sparse-checkout'].splitlines(),
            ['/design/build-sources.mjs', '/design/sources/brand.json'],
        )
        self.assertEqual(
            checkout['with']['token'],
            '${{ steps.source_token.outputs.token || secrets.YUETO_CI_PAT }}',
        )
        self.assertEqual(gate['env'], {'ORIGIN_COMPONENT': '${{ matrix.validation }}'})
        self.assertIn(RESOLVE, gate['run'])
        self.assertIn('--authority-ref="$authority"', gate['run'])
        self.assertNotRegex(gate['run'], r'--authority-ref="?[0-9a-f]{40}')
        self.assertLess(names.index('Set up Node'), names.index(CHECKOUT))
        self.assertLess(names.index(CHECKOUT), names.index(GATE))
        self.assertNotIn('permissions', data['jobs']['validate'])
        return gate['run']

    def test_runtime_root_checkout_rejects_a_frozen_sha(self):
        text = WORKFLOW.read_text()
        self.assertNotIn('de5477ffada2e6b1618bb798acd8f455b86102d7', text)
        data = workflow()
        self.assert_contract(data)
        for mutation in ('literal-sha', 'dispatch-ref', 'persist', 'optional', 'partial-condition', 'missing-gate', 'skip-resolve'):
            changed = copy.deepcopy(data)
            steps = changed['jobs']['validate']['steps']
            checkout = next(s for s in steps if s.get('name') == CHECKOUT)
            gate = next(s for s in steps if s.get('name') == GATE)
            if mutation == 'literal-sha':
                checkout['with']['ref'] = 'a' * 40
            elif mutation == 'dispatch-ref':
                checkout['with']['ref'] = '${{ inputs.ref }}'
            elif mutation == 'persist':
                checkout['with']['persist-credentials'] = True
            elif mutation == 'optional':
                gate['continue-on-error'] = True
            elif mutation == 'partial-condition':
                gate['if'] = "matrix.validation == 'yueboard'"
            elif mutation == 'skip-resolve':
                gate['run'] = gate['run'].replace(RESOLVE, 'authority=' + ('b' * 40))
            else:
                steps.remove(gate)
            with self.subTest(mutation=mutation), self.assertRaises((AssertionError, ValueError)):
                self.assert_contract(changed)

    def test_actual_shell_passes_resolved_head_or_refuses(self):
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
            git = base / 'git'
            git.write_text('#!' + sys.executable + '\n' + '''import os, sys
if sys.argv[1:] != ['-C', '.ci-origin-authority', 'rev-parse', 'HEAD']:
    sys.exit(9)
print(os.environ['EXPECTED_AUTHORITY'])
''')
            git.chmod(0o755)
            env = {**os.environ, 'PATH': str(base) + os.pathsep + os.environ['PATH'],
                   'CALLS': str(calls), 'GITHUB_WORKSPACE': str(base / 'component with spaces'),
                   'EXPECTED_AUTHORITY': 'c' * 40}

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
            for old, new in [(RESOLVE, 'authority=' + ('d' * 40)),
                             ('--authority-ref="$authority"', '--authority-ref=master'),
                             (' --check', ''),
                             ('--repo="$ORIGIN_COMPONENT=$GITHUB_WORKSPACE"', '')]:
                with self.subTest(mutation=old):
                    self.assertIn(old, script)
                    self.assertNotEqual(execute(script.replace(old, new, 1), 'yueboard').returncode, 0)

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
