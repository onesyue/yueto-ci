"""Exact npm security successor admission retains the complete prior baseline."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('security_shards', ROOT / 'scripts/pytest-shards.py')
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
EVIDENCE = ROOT / 'reviews/ops-npm-security-20261031'


class SecurityTransition(unittest.TestCase):
    def setUp(self):
        self.baseline = json.loads((ROOT / M.SKIP_BASELINE).read_text())
        self.prior, self.record = M.reviewed_npm_security_transition(self.baseline)
        self.freeze = json.loads((EVIDENCE / 'source-freeze.json').read_text())
        self.common = self.freeze['common_inputs']
        self.files = {p: (self.freeze['input_modes'][p], b) for p, b in self.common.items()}
        self.proof = self.prior['reviewed_estate_input_transition']['source_after']

    def test_evidence_and_historical_baseline_are_exact(self):
        self.assertEqual(M.sha(M.baseline_bytes(self.prior)), self.record['prior_baseline_sha256'])
        for field, name in [('source_freeze_sha256','source-freeze.json'),
                            ('independent_review_sha256','independent-review.md'),
                            ('qualification_receipt_sha256','qualification.json')]:
            self.assertEqual(self.record[field], M.sha((EVIDENCE/name).read_bytes()))
        self.assertEqual(set(self.record['changes']), M.SECURITY_INPUT_PATHS)
        q = json.loads((EVIDENCE/'qualification.json').read_text())
        self.assertTrue(q['ordered_nodeids_equal'] and q['partition_no_loss_or_overlap'])
        self.assertGreater(q['count'], 28000)
        self.assertIn('NOT_RUN',q['full_execution_gate'])

    def test_current_and_historical_admit_and_mutations_fail(self):
        M.admit_shared_inputs(self.baseline,self.common,self.files,
            source_revision=self.freeze['source_revision'],estate_successor_of=self.proof)
        before, files = dict(self.common), dict(self.files)
        for p, c in self.record['changes'].items():
            before[p]=c['before_blob'];files[p]=(c['mode'],c['before_blob'])
        M.admit_shared_inputs(self.baseline,before,files,
            source_revision=self.record['source_before'],estate_successor_of=self.proof)
        for path in self.record['changes']:
            for mutation in ('missing','blob','mode','old'):
                common,files=dict(self.common),dict(self.files)
                if mutation=='missing':common.pop(path);files.pop(path)
                if mutation=='blob':common[path]='f'*40
                if mutation=='mode':files[path]=('100755',common[path])
                if mutation=='old':common[path]=self.record['changes'][path]['before_blob']
                with self.subTest(path=path,mutation=mutation),self.assertRaises(ValueError):
                    M.admit_shared_inputs(self.baseline,common,files,
                        source_revision=self.freeze['source_revision'],estate_successor_of=self.proof)
        for mutation in ('seal','baseline'):
            b=copy.deepcopy(self.baseline)
            if mutation=='seal':b[M.SECURITY_INPUT_KEY]['source_after']='f'*40
            else:b['common_inputs']['unexpected']='f'*40
            with self.assertRaises(ValueError):M.reviewed_npm_security_transition(b)

    def test_real_git_descendant_deletion_replacement_and_mode_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)
            def git(*args):return subprocess.check_output(['git','-C',str(source),*args],stderr=subprocess.DEVNULL).decode().strip()
            git('init','-q');git('config','user.name','fixture');git('config','user.email','fixture@example.invalid');git('config','commit.gpgsign','false');git('config','core.filemode','true')
            record=copy.deepcopy(self.record)
            for path in record['changes']:
                p=source/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('before '+path)
            git('add','.');git('commit','-qm','before');before=git('rev-parse','HEAD')
            for path in record['changes']:
                record['changes'][path]['before_blob']=git('rev-parse','HEAD:'+path)
                (source/path).write_text('after '+path)
            git('add','.');git('commit','-qm','qualified');after=git('rev-parse','HEAD')
            for path in record['changes']:
                record['changes'][path].update(after_blob=git('rev-parse','HEAD:'+path),source=after)
            record.update(source_before=before,source_after=after)
            git('commit','-q','--allow-empty','-m','unchanged');unchanged=git('rev-parse','HEAD')
            peel=M.reviewed_npm_security_transition
            def fixture_peel(value):
                prior,r=peel(value)
                return prior,record if r is not None else None
            # Isolate only this transition's real ancestry proof. Prior admission
            # is exercised unchanged above; this fixture has no historical estate.
            with patch.object(M,'reviewed_npm_security_transition',side_effect=fixture_peel), \
                 patch.object(M,'reviewed_collection_shuffle_transition',return_value=({},None)), \
                 patch.object(M,'reviewed_estate_input_transition',return_value=({},None)):
                for rev in (before,after,unchanged):M.estate_successor_proof(self.baseline,source,rev)
                path=next(iter(record['changes']))
                for mutation in ('delete','replace','mode','revert'):
                    git('checkout','-q','-f',unchanged)
                    if mutation=='delete':git('rm','-q',path)
                    elif mutation=='mode':(source/path).chmod(0o755);git('add',path)
                    else:(source/path).write_text(('before ' if mutation=='revert' else 'foreign ')+path);git('add',path)
                    git('commit','-qm',mutation)
                    with self.subTest(mutation=mutation),self.assertRaisesRegex(ValueError,'npm security successor'):
                        M.estate_successor_proof(self.baseline,source,git('rev-parse','HEAD'))
