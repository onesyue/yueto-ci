"""Validation dispatch cannot consume another run or suppress missing logs."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
SPEC = importlib.util.spec_from_file_location('ci_remote', ROOT / 'scripts/ci_check_remote.py')
assert SPEC is not None and SPEC.loader is not None
REMOTE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REMOTE)


class DispatchBinding(unittest.TestCase):
    def row(self, id=2, title='expected', policy='a' * 40):
        return dict(databaseId=id, displayTitle=title, headSha=policy,
                    event='workflow_dispatch', status='completed', conclusion='success')

    def test_requires_new_unique_run_with_exact_title_and_policy(self):
        expected = self.row()
        rows = [self.row(id=1), self.row(id=3, title='other'), expected]
        self.assertEqual(REMOTE.select_run(rows, {1}, 'expected', 'a' * 40), expected)
        self.assertIsNone(REMOTE.select_run(rows, {1, 2}, 'expected', 'a' * 40))
        with self.assertRaisesRegex(ValueError, 'multiple'):
            REMOTE.select_run([expected, self.row(id=4)], set(), 'expected', 'a' * 40)
        with self.assertRaisesRegex(ValueError, 'revision differs'):
            REMOTE.select_run([self.row(policy='b' * 40)], set(), 'expected', 'a' * 40)

    def test_dirty_remote_head_refused_before_dispatch(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(REMOTE, 'gh', return_value='b' * 40):
            with self.assertRaisesRegex(ValueError, 'push the exact'):
                REMOTE.dispatch('branch', 'a' * 40, 'c' * 40, 'd' * 40, Path(directory), board='b' * 40)

    def test_complete_logs_failure_is_not_hidden(self):
        policy, source, nonce = 'a' * 40, 'c' * 40, 'e' * 32
        title = f'Build & publish images yueops {source} [nonce:{nonce}]'
        row = self.row(title=title)
        calls = []

        def gh(*args):
            calls.append(args)
            if args[0] == 'api':
                return policy
            if args[:2] == ('workflow', 'run'):
                self.assertIn('nonce=' + nonce, args)
                self.assertIn('yueboard_contract_ref=' + 'b' * 40, args)
                self.assertIn('validation_only=true', args)
                self.assertIn('promote=false', args)
                return ''
            if '--log' in args:
                raise OSError('log unavailable')
            return json.dumps(row)

        with tempfile.TemporaryDirectory() as directory, \
                patch.object(REMOTE, 'gh', side_effect=gh), \
                patch.object(REMOTE, 'runs', side_effect=[[], [row]]), \
                patch.object(REMOTE.uuid, 'uuid4') as uid, \
                patch.object(REMOTE.subprocess, 'run'):
            uid.return_value.hex = nonce
            with self.assertRaisesRegex(OSError, 'log unavailable'):
                REMOTE.dispatch('branch', policy, source, 'd' * 40, Path(directory), board='b' * 40)
            self.assertTrue((Path(directory) / 'dispatch.json').exists())
            self.assertEqual(json.loads((Path(directory) / 'result.json').read_text()), row)
        self.assertTrue(any('--log' in args for args in calls))
        self.assertFalse(any('--log-failed' in args for args in calls))

    def test_repo_inputs_fail_closed_before_network(self):
        for repo, policy, source, base, board in [
            ('unknown', 'a'*40, 'c'*40, '', ''),
            ('yueboard', 'a'*7, 'c'*40, '', ''),
            ('yue-node', 'a'*40, 'c'*7, '', ''),
            ('yueboard', 'a'*40, 'c'*40, 'd'*40, ''),
            ('yue-node', 'a'*40, 'c'*40, '', 'b'*40),
            ('yueops', 'a'*40, 'c'*40, '', 'b'*40),
        ]:
            with self.subTest(repo=repo, base=base, board=board), patch.object(REMOTE, 'gh') as gh:
                with self.assertRaises(ValueError):
                    REMOTE.dispatch('branch', policy, source, base, Path('.'), board=board, repo=repo)
                gh.assert_not_called()

    def test_board_node_dispatch_binding_diagnostics_and_terminal_evidence(self):
        for repo in ('yueboard', 'yue-node'):
            for conclusion, log, expected in [
                ('success', 'all checks passed\n', 0),
                ('failure', 'unrecognized tool failed\n', 1),
                ('cancelled', '', 1),
                ('success', '2026-11-13T00:00:00Z --- FAIL: TestBoundary (0.01s)\n', 1),
                ('failure', '2026-11-13T00:00:00Z internal/a.go:12:3: omit redundant nil check (S1009)\n', 1),
            ]:
                with self.subTest(repo=repo, conclusion=conclusion, log=log):
                    policy, source, nonce = 'a'*40, 'c'*40, 'e'*32
                    row = self.row(title=f'Build & publish images {repo} {source} [nonce:{nonce}]')
                    final = row | {'conclusion': conclusion}
                    def gh(*args):
                        if args[0] == 'api':
                            return policy
                        if args[:2] == ('workflow', 'run'):
                            for field in (f'service={repo}', f'ref={source}', 'validation_only=true', 'promote=false'):
                                self.assertIn(field, args)
                            self.assertFalse(any(x.startswith(('migration_base=', 'yueboard_contract_ref=')) for x in args))
                            return ''
                        return log if '--log' in args else json.dumps(final)
                    with tempfile.TemporaryDirectory() as directory, \
                            patch.object(REMOTE, 'gh', side_effect=gh), \
                            patch.object(REMOTE, 'runs', side_effect=[[], [row]]), \
                            patch.object(REMOTE.uuid, 'uuid4') as uid, \
                            patch.object(REMOTE.subprocess, 'run'):
                        uid.return_value.hex = nonce
                        output = Path(directory)
                        self.assertEqual(REMOTE.dispatch('branch', policy, source, '', output, repo=repo), expected)
                        self.assertEqual((output / 'remote.log').read_text(), log)
                        self.assertEqual(json.loads((output / 'result.json').read_text()), final)
                        self.assertEqual(json.loads((output / 'dispatch.json').read_text())['repository'], repo)
                        if 'S1009' in log:
                            self.assertIn('S1009', (output / 'failures.txt').read_text())

    def test_changed_terminal_identity_is_rejected_and_retained(self):
        for field, value in [('headSha', 'b'*40), ('displayTitle', 'other'), ('event', 'push'), ('status', 'in_progress')]:
            row = self.row(title=f'Build & publish images yueboard {"c"*40} [nonce:nonce]')
            final = row | {field: value}
            def gh(*args):
                if args[0] == 'api':
                    return 'a'*40
                return '' if args[0] == 'workflow' else json.dumps(final)
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory, \
                    patch.object(REMOTE, 'gh', side_effect=gh), \
                    patch.object(REMOTE, 'runs', side_effect=[[], [row]]), \
                    patch.object(REMOTE.uuid, 'uuid4') as uid, \
                    patch.object(REMOTE.subprocess, 'run'):
                uid.return_value.hex = 'nonce'
                with self.assertRaises(ValueError):
                    REMOTE.dispatch('branch', 'a'*40, 'c'*40, '', Path(directory), repo='yueboard')
                self.assertEqual(json.loads((Path(directory) / 'result.json').read_text()), final)


if __name__ == '__main__':
    unittest.main()
