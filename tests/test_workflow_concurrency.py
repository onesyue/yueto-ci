"""t1520u: no workflow may stack runs. Every workflow has one concurrency group;
PR/push-triggered checks supersede older runs of the same ref; publishing and
production workflows never interrupt a run in flight."""
from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / '.github' / 'workflows').glob('*.yml'))
# Publishing or production-side effects: a cancel mid-run could leave a half
# retagged image or a half-written report, so these queue instead.
NEVER_INTERRUPT = {'build.yml', 'ci-toolchain.yml', 'alert-chain-deadman.yml', 'board-visual-capture.yml',
                   'client-core-matrix.yml', 'hy2-probe.yml', 'image-rescan.yml', 'weekly-scan-deadman.yml',
                   'weekly-vuln-sbom.yml', 'yueops-master-validate.yml'}


def load(path: Path) -> dict:
    data = yaml.safe_load(path.read_text())
    data['on'] = data.pop(True, data.get('on'))
    return data


class WorkflowConcurrency(unittest.TestCase):
    def test_every_workflow_has_one_group(self):
        self.assertTrue(WORKFLOWS)
        for path in WORKFLOWS:
            with self.subTest(workflow=path.name):
                concurrency = load(path).get('concurrency')
                self.assertIsInstance(concurrency, dict, 'missing top-level concurrency')
                self.assertTrue(str(concurrency.get('group', '')).strip())

    def test_pr_checks_supersede_older_runs_of_the_same_ref(self):
        for path in WORKFLOWS:
            data = load(path)
            if path.name in NEVER_INTERRUPT or 'pull_request' not in (data['on'] or {}):
                continue
            with self.subTest(workflow=path.name):
                concurrency = data['concurrency']
                self.assertIn('github.ref', concurrency['group'])
                self.assertIn(concurrency['cancel-in-progress'],
                              (True, "${{ github.event_name != 'workflow_dispatch' }}"))

    def test_publishing_workflows_never_interrupt(self):
        for name in sorted(NEVER_INTERRUPT):
            with self.subTest(workflow=name):
                self.assertIs(load(ROOT / '.github' / 'workflows' / name)['concurrency']['cancel-in-progress'], False)


if __name__ == '__main__':
    unittest.main()
