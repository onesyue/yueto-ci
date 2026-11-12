"""Native GitHub evidence replaces offline receipt and exemption artifacts."""
import copy
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('native_audit', ROOT / 'scripts/merge-hygiene-audit.py')
assert spec is not None and spec.loader is not None
AUDIT = importlib.util.module_from_spec(spec)
spec.loader.exec_module(AUDIT)


class NativeEvidence(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads((ROOT / 'tests/fixtures/merge-hygiene/approved.json').read_text())
        self.pr = self.fixture['pr'] | {'state': 'open', 'merged_at': None}
        self.refreshed = copy.deepcopy(self.pr)
        self.seen = []

    def api(self, endpoint):
        self.seen.append(endpoint)
        if endpoint.endswith('/pulls/203'):
            return self.pr if self.seen.count(endpoint) == 1 else self.refreshed
        if '/reviews?' in endpoint:
            return self.fixture['reviews']
        if '/check-runs?' in endpoint:
            return {'check_runs': self.fixture['checks']}
        if '/statuses?' in endpoint:
            return self.fixture['statuses']
        raise AssertionError('Unexpected legacy policy dependency: ' + endpoint)

    def premerge(self):
        with patch.object(AUDIT, 'api', side_effect=self.api):
            return AUDIT.premerge('onesyue', 'yueops', 203)

    def test_exact_head_approval_needs_no_local_artifact(self):
        with patch.object(Path, 'read_text', side_effect=AssertionError('no offline evidence')):
            row = self.premerge()
        self.assertEqual(row['findings'], [])
        self.assertEqual(set(row), {'repo', 'pr', 'url', 'head', 'merged_at', 'findings'})

    def test_missing_stale_and_malformed_review_commit_are_rejected(self):
        for value in (None, '', 'b' * 40, 'invalid'):
            with self.subTest(commit=value):
                self.fixture['reviews'][0]['commit_id'] = value
                self.assertIn('no_approving_review_at_merge', self.premerge()['findings'])
        self.fixture['reviews'][0].pop('commit_id')
        self.assertIn('no_approving_review_at_merge', self.premerge()['findings'])

    def test_new_review_replaces_stale_approval_only_for_current_commit(self):
        old = self.fixture['reviews'][0] | {'commit_id': 'b' * 40}
        self.fixture['reviews'] = [old]
        self.assertIn('no_approving_review_at_merge', self.premerge()['findings'])
        self.fixture['reviews'].append(old | {'id': 2, 'commit_id': self.pr['head']['sha'],
                                             'submitted_at': '2026-11-02T09:01:00Z'})
        self.assertEqual(self.premerge()['findings'], [])

    def test_head_or_base_movement_is_incomplete(self):
        for field in ('head', 'base'):
            with self.subTest(field=field):
                self.seen.clear()
                self.refreshed = copy.deepcopy(self.pr)
                self.refreshed[field]['sha'] = 'c' * 40
                with self.assertRaisesRegex(ValueError, 'changed'):
                    self.premerge()

    def test_retired_cli_exception_is_not_silently_accepted(self):
        with patch('sys.argv', ['audit', '--exceptions', 'offline.json']):
            with self.assertRaises(SystemExit) as error:
                AUDIT.main()
        self.assertEqual(error.exception.code, 2)

    def test_premerge_observes_checks_created_after_audit_started(self):
        original = copy.deepcopy(self.fixture)
        for kind in ('check', 'status'):
            with self.subTest(kind=kind):
                self.fixture = copy.deepcopy(original)
                self.seen.clear()
                current = AUDIT.timestamp('2026-11-02T10:00:00Z')
                def api(endpoint):
                    nonlocal current
                    if '/check-runs?' in endpoint:
                        current = AUDIT.timestamp('2026-11-02T10:02:00Z')
                        if kind == 'check':
                            self.fixture['checks'].append(self.fixture['checks'][0] | {
                                'id': 2, 'created_at': '2026-11-02T10:01:00Z',
                                'started_at': None, 'completed_at': None, 'status': 'queued'})
                        else:
                            self.fixture['statuses'].append(self.fixture['statuses'][0] | {
                                'id': 2, 'created_at': '2026-11-02T10:01:00Z', 'state': 'failure'})
                    return self.api(endpoint)
                with patch.object(AUDIT, 'api', side_effect=api), patch.object(
                        AUDIT, 'audit', return_value=[]), patch.object(
                        AUDIT, 'datetime', wraps=AUDIT.datetime) as clock, patch(
                        'sys.argv', ['audit', '--premerge', 'yueops', '203', '--format', 'json']), \
                        contextlib.redirect_stdout(io.StringIO()) as output:
                    clock.now.side_effect = lambda _zone: current
                    self.assertEqual(AUDIT.main(), 1)
                reasons = json.loads(output.getvalue())['findings'][0]['findings']
                expected = ('check_pending_at_merge:policy' if kind == 'check'
                            else 'status_nonpassing_at_merge:external-ci')
                self.assertIn(expected, reasons)

    def test_historical_window_is_explicit_without_activation_api(self):
        old = self.fixture['pr'] | {'merged_at': '2026-10-01T00:00:00Z',
                                    'updated_at': '2026-10-01T00:00:00Z'}
        def api(endpoint):
            self.assertIn('/pulls?state=closed', endpoint)
            return [old]
        with patch.object(AUDIT, 'api', side_effect=api):
            self.assertEqual(AUDIT.audit('onesyue', ['yueops'], AUDIT.timestamp('2026-11-01T00:00:00Z'),
                                         AUDIT.timestamp('2026-11-03T00:00:00Z')), [])
