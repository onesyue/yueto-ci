"""Exact root collection-hook seal; the complete historical admission remains active."""
import copy
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('collection_shuffle_shards', ROOT / 'scripts/pytest-shards.py')
assert SPEC and SPEC.loader
SHARDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARDS)
KEY = SHARDS.COLLECTION_SHUFFLE_KEY
PATH = SHARDS.COLLECTION_SHUFFLE_INPUT
EVIDENCE = ROOT / 'reviews/ops-collection-shuffle-20261031'


class CollectionShuffleTransition(unittest.TestCase):
    def setUp(self):
        self.baseline = json.loads((ROOT / SHARDS.SKIP_BASELINE).read_text())
        self.baseline, _ = SHARDS.reviewed_npm_security_transition(self.baseline)
        self.record = self.baseline[KEY]
        self.prior, _ = SHARDS.reviewed_collection_shuffle_transition(self.baseline)
        freeze = json.loads((EVIDENCE / 'source-freeze.json').read_text())
        self.common = freeze['common_inputs']
        self.files = {p: (freeze['input_modes'][p], b) for p, b in self.common.items()}
        self.proof = self.prior['reviewed_estate_input_transition']['source_after']

    def test_seal_preserves_exact_old_baseline_and_binds_real_evidence(self):
        self.assertEqual(SHARDS.sha(SHARDS.baseline_bytes(self.prior)),
                         'd11a7572750c2e44d4781e92c2c0a910f40cae0e29b333aedd49132747842507')
        self.assertEqual(self.record['prior_baseline_sha256'], SHARDS.sha(SHARDS.baseline_bytes(self.prior)))
        self.assertEqual(SHARDS.sha(SHARDS.encoded(self.record)), SHARDS.COLLECTION_SHUFFLE_TRANSITION_SHA256)
        for field, filename in [('independent_review_sha256', 'independent-review.md'),
                                ('source_freeze_sha256', 'source-freeze.json'),
                                ('qualification_receipt_sha256', 'qualification.json')]:
            self.assertEqual(self.record[field], SHARDS.sha((EVIDENCE / filename).read_bytes()))
        self.assertEqual(self.record['changes'], {PATH: {
            'before_blob': None, 'after_blob': '05613fb260c40650ff94397493fe0bf8132d1e8e',
            'mode': '100644', 'source': 'f683e5391c723fd00da42b82d21cfd049a529e8c'}})
        receipt = json.loads((EVIDENCE / 'qualification.json').read_text())
        self.assertEqual(receipt['status'], 'PASS_COLLECTION_QUALIFICATION_ONLY')
        self.assertTrue(receipt['default_order_and_rng_unchanged'])
        self.assertTrue(receipt['shard_order_and_rng_unchanged'])
        self.assertTrue(receipt['seed_repeat_equal'] and receipt['seed_multisets_equal'])
        self.assertTrue(receipt['seed_global_rng_unchanged'] and receipt['complete_partition'])
        self.assertIn('NOT_RUN', receipt['full_execution_gate'])

    def test_current_shared_inputs_pass_full_old_admission_after_exact_peel(self):
        SHARDS.admit_shared_inputs(self.baseline, self.common, self.files,
                                   source_revision=self.record['source_after'], estate_successor_of=self.proof)
        # The same complete predecessor remains admissible without the new input.
        prior_common = {p: b for p, b in self.common.items() if p != PATH}
        prior_files = {p: b for p, b in self.files.items() if p != PATH}
        SHARDS.admit_shared_inputs(self.prior, prior_common, prior_files,
                                   source_revision=self.record['source_before'], estate_successor_of=self.proof)
        with self.assertRaises(ValueError):
            SHARDS.admit_shared_inputs(self.prior, self.common, self.files,
                                       source_revision=self.record['source_after'], estate_successor_of=self.proof)

    def test_wrong_blob_mode_proof_and_other_shared_changes_are_refused(self):
        for mutation in ('blob', 'execute', 'symlink', 'missing', 'proof', 'extra', 'historical'):
            common, files = dict(self.common), dict(self.files)
            proof = self.proof
            if mutation == 'blob': common[PATH] = 'a' * 40
            elif mutation == 'execute': files[PATH] = ('100755', common[PATH])
            elif mutation == 'symlink': files[PATH] = ('120000', common[PATH])
            elif mutation == 'missing': common.pop(PATH); files.pop(PATH)
            elif mutation == 'proof': proof = None
            elif mutation == 'extra': common['unreviewed/conftest.py'] = 'a' * 40
            else: common['pytest.ini'] = 'a' * 40
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                SHARDS.admit_shared_inputs(self.baseline, common, files,
                                           source_revision=self.record['source_after'], estate_successor_of=proof)

    def test_each_sealed_identity_and_historical_byte_remains_immutable(self):
        for field in ('schema', 'prior_baseline_sha256', 'source_before', 'source_after',
                      'independent_review_sha256', 'source_freeze_sha256', 'qualification_receipt_sha256'):
            damaged = copy.deepcopy(self.baseline)
            damaged[KEY][field] = True if field == 'schema' else '0' * 64
            with self.subTest(field=field), self.assertRaises(ValueError):
                SHARDS.reviewed_collection_shuffle_transition(damaged)
        for field in ('before_blob', 'after_blob', 'mode', 'source'):
            damaged = copy.deepcopy(self.baseline)
            damaged[KEY]['changes'][PATH][field] = 'foreign'
            with self.subTest(field=field), self.assertRaises(ValueError):
                SHARDS.reviewed_collection_shuffle_transition(damaged)
        damaged = copy.deepcopy(self.baseline)
        damaged['common_inputs']['pytest.ini'] = 'a' * 40
        with self.assertRaisesRegex(ValueError, 'changed historical baseline'):
            SHARDS.reviewed_collection_shuffle_transition(damaged)

    def test_real_git_proof_rejects_foreign_history_or_rewritten_hook(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            def git(*args):
                return subprocess.check_output(['git', '-C', str(source), *args], stderr=subprocess.DEVNULL).decode().strip()
            git('init', '-q')
            git('config', 'user.name', 'fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            git('config', 'commit.gpgsign', 'false')
            git('commit', '-q', '--allow-empty', '-m', 'before')
            before = git('rev-parse', 'HEAD')
            (source / PATH).write_text('reviewed hook\n')
            git('add', PATH); git('commit', '-q', '-m', 'introduce')
            introduced = git('rev-parse', 'HEAD')
            blob = git('rev-parse', 'HEAD:' + PATH)
            git('commit', '-q', '--allow-empty', '-m', 'qualified')
            after = git('rev-parse', 'HEAD')
            record = copy.deepcopy(self.record)
            record.update(source_before=before, source_after=after)
            record['changes'][PATH].update(source=introduced, after_blob=blob)
            with patch.object(SHARDS, 'reviewed_collection_shuffle_transition', return_value=({}, record)):
                SHARDS.estate_successor_proof({}, source, after)
                with self.assertRaisesRegex(ValueError, 'collection shuffle successor'):
                    SHARDS.estate_successor_proof({}, source, introduced)
                (source / PATH).write_text('unreviewed hook\n')
                git('add', PATH); git('commit', '-q', '-m', 'tamper')
                with self.assertRaisesRegex(ValueError, 'collection shuffle successor'):
                    SHARDS.estate_successor_proof({}, source, git('rev-parse', 'HEAD'))

    def test_real_git_descendant_deletion_cannot_reenter_historical_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            def git(*args):
                return subprocess.check_output(['git', '-C', str(source), *args],
                                               stderr=subprocess.DEVNULL).decode().strip()
            git('init', '-q')
            git('config', 'user.name', 'fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            git('config', 'commit.gpgsign', 'false')
            git('config', 'core.filemode', 'true')
            git('commit', '-q', '--allow-empty', '-m', 'historical source')
            before = git('rev-parse', 'HEAD')
            (source / PATH).write_text('reviewed hook\n')
            git('add', PATH); git('commit', '-q', '-m', 'introducer')
            introduced = git('rev-parse', 'HEAD')
            blob = git('rev-parse', 'HEAD:' + PATH)
            git('commit', '-q', '--allow-empty', '-m', 'qualified source')
            after = git('rev-parse', 'HEAD')
            git('commit', '-q', '--allow-empty', '-m', 'unchanged successor')
            unchanged = git('rev-parse', 'HEAD')
            record = copy.deepcopy(self.record)
            record.update(source_before=before, source_after=after)
            record['changes'][PATH].update(source=introduced, after_blob=blob)
            original_peel = SHARDS.reviewed_collection_shuffle_transition
            original_git = SHARDS.git

            def peel(value):
                prior, actual = original_peel(value)
                return prior, record if actual is not None else None

            def history(repo, *args):
                # The old estate is represented by this fixture's initial commit.
                # Hook introduction/qualification/successors use actual Git objects;
                # full old input admission still consumes the unmodified freeze.
                if args[:3] == ('merge-base', '--is-ancestor', self.proof):
                    args = (*args[:2], before, *args[3:])
                return original_git(repo, *args)

            def admit(revision):
                proof = SHARDS.estate_successor_proof(self.baseline, source, revision)
                common, files = dict(self.common), dict(self.files)
                hook = SHARDS.tree_inputs(source, revision).get(PATH)
                if hook is None:
                    common.pop(PATH); files.pop(PATH)
                else:
                    files[PATH] = hook
                    common[PATH] = hook[1]
                SHARDS.admit_shared_inputs(self.baseline, common, files,
                                           source_revision=revision, estate_successor_of=proof)

            with (patch.object(SHARDS, 'reviewed_collection_shuffle_transition', side_effect=peel),
                  patch.object(SHARDS, 'git', side_effect=history)):
                for revision in (before, after, unchanged):
                    with self.subTest(accepted=revision):
                        admit(revision)
                (source / PATH).chmod(0o755)
                git('update-index', '--chmod=+x', PATH)
                git('commit', '-q', '-m', 'unreviewed executable mode')
                with self.assertRaisesRegex(ValueError, 'mode or tree changed'):
                    admit(git('rev-parse', 'HEAD'))
                git('checkout', '-q', unchanged)
                git('rm', '-q', PATH)
                git('commit', '-q', '-m', 'delete qualified hook')
                with self.assertRaisesRegex(ValueError, 'collection shuffle successor'):
                    admit(git('rev-parse', 'HEAD'))
