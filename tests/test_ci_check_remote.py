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
                REMOTE.dispatch('branch', 'a' * 40, 'c' * 40, 'd' * 40, Path(directory))

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
                REMOTE.dispatch('branch', policy, source, 'd' * 40, Path(directory))
            self.assertTrue((Path(directory) / 'dispatch.json').exists())
        self.assertTrue(any('--log' in args for args in calls))
        self.assertFalse(any('--log-failed' in args for args in calls))


if __name__ == '__main__':
    unittest.main()
