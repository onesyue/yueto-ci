"""Execute the shared dispatch planner and enforce its no-publication boundary."""
from __future__ import annotations

import itertools
import json
from pathlib import Path
import subprocess
import unittest

import yaml

import test_hardening_20260927 as hardening

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/build.yml'


class ValidationOnlyTest(unittest.TestCase):
    run_plan = hardening.PlanPromotionGateTest.run_plan

    def test_exact_candidate_preserves_complete_registered_validation(self):
        for service, count in [('yueboard', 7), ('yue-node', 2), ('yueops', 1), ('yuelink', 1)]:
            with self.subTest(service=service):
                result = self.run_plan(SERVICE=service, REF_OVERRIDE='b' * 40, VALIDATION_ONLY='true')
                self.assertEqual(result.returncode, 0, result.stderr)
                plan = getattr(result, 'target_plan')
                expected = subprocess.run(
                    ['bash', 'scripts/plan-build-targets.sh', service, 'b' * 40],
                    cwd=ROOT, capture_output=True, text=True, check=True,
                )
                self.assertEqual(plan['validation_matrix'], json.loads(expected.stdout)['validation_matrix'])
                self.assertEqual(len(plan['validation_matrix']), count)
                self.assertEqual(plan['matrix'], [])
                self.assertIs(plan['has_builds'], False)
                self.assertIn('has_builds=false', getattr(result, 'outputs'))
                self.assertIn('promote=false', getattr(result, 'outputs'))

    def test_invalid_modes_fail_before_emitting_any_plan(self):
        cases = [dict(REF_OVERRIDE=value) for value in ('', 'master', 'a' * 12, 'A' * 40, 'a' * 41)]
        cases += [dict(MANUAL_PROMOTE='true'), dict(EVENT_NAME='repository_dispatch'),
                  dict(SERVICE='all'), dict(VALIDATION_ONLY='maybe'),
                  dict(SERVICE='yueops', MIGRATION_BASE=''), dict(SERVICE='unknown')]
        for case in cases:
            with self.subTest(case=case):
                result = self.run_plan(False, **{'REF_OVERRIDE': 'b' * 40, 'VALIDATION_ONLY': 'true', **case})
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(getattr(result, 'outputs'), '')
                self.assertIsNone(getattr(result, 'target_plan'))

    def assert_read_only_graph(self, text):
        workflow = yaml.safe_load(text)
        jobs = workflow['jobs']
        # PyYAML's YAML 1.1 loader represents the workflow key `on` as True.
        trigger = workflow.get('on', workflow.get(True))
        mode = trigger['workflow_dispatch']['inputs']['validation_only']
        self.assertEqual(mode['type'], 'boolean')
        self.assertIs(mode['default'], False)
        plan = next(step for step in jobs['plan']['steps'] if step.get('id') == 'plan')
        self.assertEqual(plan['env']['VALIDATION_ONLY'], "${{ inputs.validation_only && 'true' || 'false' }}")
        # The boolean input, rather than a possibly absent plan output, also
        # protects abort jobs when planning itself fails.
        for name in ('build', 'publish', 'abort-on-build-failure', 'abort-on-validate-failure'):
            expression = jobs[name]['if']
            self.assertIn('!inputs.validation_only', expression)
            for validation_only, has_builds, failed in itertools.product((False, True), repeat=3):
                condition = expression.replace('!inputs.validation_only', str(not validation_only).lower())
                condition = condition.replace("needs.plan.outputs.has_builds == 'true'", str(has_builds).lower())
                condition = condition.replace('failure()', str(failed).lower())
                condition = condition.replace("needs.plan.outputs.resume != 'true'", 'true')
                condition = condition.replace("needs.plan.outputs.resume == 'true'", 'false')
                condition = condition.replace('always()', 'true')
                for dependency in ('plan', 'build', 'validate', 'validation-evidence'):
                    condition = condition.replace("needs." + dependency + ".result == 'success'", 'true')
                    condition = condition.replace("needs." + dependency + ".result == 'skipped'", 'false')
                status = subprocess.run(['bash', '-c', condition], capture_output=True, check=False).returncode
                expected = not validation_only and (failed if name.startswith('abort-') else has_builds)
                self.assertEqual(status == 0, expected)
        self.assertEqual(workflow['permissions'], {'contents': 'read'})
        for name in ('plan', 'validate', 'validation-evidence'):
            self.assertTrue(all(value == 'read' for value in jobs[name].get('permissions', {}).values()))
            self.assertNotIn('concurrency', jobs[name])
        self.assertIn("inputs.validation_only && 'validate-only' || 'build'", workflow['concurrency']['group'])
        self.assertEqual(jobs['validate']['strategy']['matrix']['include'], '${{ fromJSON(needs.plan.outputs.validation_matrix) }}')
        self.assertEqual(jobs['validation-evidence']['needs'], ['plan', 'validate'])
        self.assertIn("always() && needs.plan.result == 'success'", jobs['validation-evidence']['if'])
        plan_steps = str(jobs['plan']['steps'])
        self.assertIn('scripts/pytest-shards.py expand', plan_steps)
        self.assertIn('scripts/pytest-shards.py join', str(jobs['validation-evidence']['steps']))

    def test_read_only_graph_and_missing_boundary_mutations(self):
        text = WORKFLOW.read_text()
        self.assert_read_only_graph(text)
        for name in ('build', 'publish', 'abort-on-build-failure', 'abort-on-validate-failure'):
            prefix, body = text.split('\n  ' + name + ':\n', 1)
            changed = prefix + '\n  ' + name + ':\n' + body.replace(' && !inputs.validation_only', '', 1)
            with self.subTest(name=name), self.assertRaises(AssertionError):
                self.assert_read_only_graph(changed)
