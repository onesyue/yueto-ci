"""Native protocol helper admission is bound to exactly one reviewed path, blob, mode and the signed release pin."""
import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('protocol_shards', ROOT / 'scripts/pytest-shards.py')
assert SPEC is not None and SPEC.loader is not None
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
REVIEW = ROOT / 'reviews/ops-native-protocol-helper-20261106'


class NativeProtocolHelper(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((REVIEW / 'helper-policy.json').read_text())
        self.freeze = json.loads((REVIEW / 'source-freeze.json').read_text())
        self.common = self.freeze['common_inputs']
        self.files = {p: (self.freeze['input_modes'][p], b) for p, b in self.common.items()}
        self.path = self.policy['shared_input']['path']
        self.revision = M.first_native_policy()['source_revision']

    def admit(self, common, files):
        baseline = M.skip_baseline()
        return M.admit_shared_inputs(
            baseline, common, files, source_revision=self.revision,
            estate_successor_of=baseline['reviewed_estate_input_transition']['source_after'])

    def test_exact_helper_full_chain_and_inputs_unchanged(self):
        original = copy.deepcopy((self.common, self.files))
        self.admit(self.common, self.files)
        self.assertEqual((self.common, self.files), original)
        common, files = M.admit_native_protocol_helper(self.common, self.files, self.revision)
        self.assertEqual(common, {p: b for p, b in self.common.items() if p != self.path})
        self.assertEqual(files, {p: v for p, v in self.files.items() if p != self.path})

    def test_changed_blob_mode_tree_and_revision_rejected(self):
        blob = self.common[self.path]
        for mode, tree_blob, common_blob, revision in (
            ('100644', 'f' * 40, 'f' * 40, self.revision),
            ('100755', blob, blob, self.revision),
            ('120000', blob, blob, self.revision),
            ('100644', 'f' * 40, blob, self.revision),
            ('100644', blob, blob, 'f' * 40),
        ):
            with self.subTest(mode=mode, blob=tree_blob, revision=revision), self.assertRaises(ValueError):
                M.admit_native_protocol_helper(
                    self.common | {self.path: common_blob},
                    self.files | {self.path: (mode, tree_blob)}, revision)

    def test_other_new_helpers_reach_unchanged_mode_rejection(self):
        for path in ('tests/other_helper.py', 'tests/native_protocol_fixture_extra.py',
                     'tests/nested/native_protocol_fixture.py'):
            with self.subTest(path=path), self.assertRaisesRegex(
                    ValueError, 'shared collection/dependency input modes changed'):
                self.admit(self.common | {path: self.common[self.path]},
                           self.files | {path: self.files[self.path]})

    def test_absent_helper_keeps_historical_inputs_unchanged(self):
        common, files = {'tests/old.py': 'a' * 40}, {'tests/old.py': ('100644', 'a' * 40)}
        self.assertEqual(M.admit_native_protocol_helper(common, files, self.revision),
                         (common, files))

    def test_evidence_identity(self):
        for field, filename in [('independent_review_sha256', 'independent-review.md'),
                                ('qualification_receipt_sha256', 'qualification.json'),
                                ('source_freeze_sha256', 'source-freeze.json')]:
            self.assertEqual(self.policy[field], M.sha((REVIEW / filename).read_bytes()))
        self.assertIn('VERDICT: APPROVE', (REVIEW / 'independent-review.md').read_text())

    def test_real_git_ancestry_blob_and_mode(self):
        import subprocess
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.check_output(['git', '-C', directory, *args],
                                               stderr=subprocess.DEVNULL, text=True).strip()
            git('init', '-q')
            git('config', 'user.name', 'fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            git('config', 'commit.gpgsign', 'false')
            git('config', 'core.filemode', 'true')
            git('commit', '-q', '--allow-empty', '-m', 'before')
            before = git('rev-parse', 'HEAD')
            path = root / self.path
            path.parent.mkdir(parents=True)
            path.write_text('fixture\n')
            git('add', self.path)
            git('commit', '-qm', 'introduce fixture')
            policy = copy.deepcopy(self.policy)
            policy['source_revision'] = git('rev-parse', 'HEAD')
            policy['shared_input']['blob'] = git('rev-parse', 'HEAD:' + self.path)
            with patch.object(M, 'native_protocol_helper_policy', return_value=policy):
                M.native_protocol_helper_proof(root, policy['source_revision'])
                git('commit', '-q', '--allow-empty', '-m', 'descendant')
                M.native_protocol_helper_proof(root, git('rev-parse', 'HEAD'))
                for mode in (0o755, 0o644):
                    path.chmod(mode)
                    if mode == 0o644:
                        path.write_text('changed\n')
                    git('add', self.path)
                    git('commit', '-qm', 'mutation')
                    with self.assertRaisesRegex(ValueError, 'blob or mode differs'):
                        M.native_protocol_helper_proof(root, git('rev-parse', 'HEAD'))
                git('checkout', '-q', '-f', before)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('fixture\n')
                git('add', self.path)
                git('commit', '-qm', 'unrelated copy')
                with self.assertRaisesRegex(ValueError, 'ancestry differs'):
                    M.native_protocol_helper_proof(root, git('rev-parse', 'HEAD'))
