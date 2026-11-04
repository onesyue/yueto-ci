"""P015 admission is bound to exactly one reviewed path, blob, mode and source."""
import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('p015_shards', ROOT / 'scripts/pytest-shards.py')
assert SPEC is not None and SPEC.loader is not None
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
REVIEW = ROOT / 'reviews/ops-p015-20261105'


class P015OfflineHelper(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((REVIEW / 'helper-policy.json').read_text())
        self.freeze = json.loads((REVIEW / 'source-freeze.json').read_text())
        self.common = self.freeze['common_inputs']
        self.files = {p: (self.freeze['input_modes'][p], b) for p, b in self.common.items()}
        self.path = self.policy['shared_input']['path']
        self.revision = self.policy['source_revision']

    def admit(self, common, files):
        baseline = M.skip_baseline()
        return M.admit_shared_inputs(
            baseline, common, files, source_revision=self.revision,
            estate_successor_of=baseline['reviewed_estate_input_transition']['source_after'])

    def test_exact_helper_full_chain_and_inputs_unchanged(self):
        original = copy.deepcopy((self.common, self.files))
        self.admit(self.common, self.files)
        self.assertEqual((self.common, self.files), original)
        common, files = M.admit_p015_offline_helper(self.common, self.files, self.revision)
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
                M.admit_p015_offline_helper(
                    self.common | {self.path: common_blob},
                    self.files | {self.path: (mode, tree_blob)}, revision)

    def test_other_new_helpers_reach_unchanged_mode_rejection(self):
        for path in ('tests/other_helper.py', 'tests/p015_offline_plugin_extra.py',
                     'tests/nested/p015_offline_plugin.py'):
            with self.subTest(path=path), self.assertRaisesRegex(
                    ValueError, 'shared collection/dependency input modes changed'):
                self.admit(self.common | {path: self.common[self.path]},
                           self.files | {path: self.files[self.path]})

    def test_absent_helper_keeps_historical_inputs_unchanged(self):
        common, files = {'tests/old.py': 'a' * 40}, {'tests/old.py': ('100644', 'a' * 40)}
        self.assertEqual(M.admit_p015_offline_helper(common, files, self.revision),
                         (common, files))
