"""Sequential dependency seals preserve history and reject partial bundles."""
import copy
import importlib.util
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('pr_shared_shards', ROOT / 'scripts/pytest-shards.py')
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def states():
    records = M.reviewed_pr_shared_input_transitions()
    inner = records[-1]
    before = {p: c['before_blob'] for p, c in inner['changes'].items()}
    result = [before]
    for record in reversed(records):
        result.append(result[-1] | {p: c['after_blob'] for p, c in record['changes'].items()})
    return result


def files(common):
    return {p: ('100644', b) for p, b in common.items()}


class PRSharedInputTransitions(unittest.TestCase):
    def test_evidence_and_sequential_predecessors(self):
        records = M.reviewed_pr_shared_input_transitions()
        assert tuple(r["source_after"] for r in records) == M.PR_SHARED_INPUT_SOURCE_REVISIONS
        assert {(p, c["after_blob"]) for r in records for p, c in r["changes"].items()} == M.PR_SHARED_INPUT_AFTER_BLOBS
        for number, record in zip((seal[0] for seal in M.PR_SHARED_INPUT_SEALS), records):
            review = ROOT / f'reviews/ops-pr{number}-20261103'
            for field, name in [('independent_review_sha256', 'independent-review.md'),
                                ('source_freeze_sha256', 'source-freeze.json'),
                                ('qualification_receipt_sha256', 'qualification.json')]:
                assert record[field] == M.sha((review / name).read_bytes())
            freeze = json.loads((review / 'source-freeze.json').read_text())
            assert record['changes'] == freeze['changes']
            assert record['source_after'] == freeze['source_after']
            assert record['source_before'] == freeze['source_before']
            qualification = json.loads((review / 'qualification.json').read_text())
            assert qualification['source_after'] == freeze['source_after']
            assert qualification['source_tree'] == freeze['source_tree']
        assert M.sha((ROOT / M.SKIP_BASELINE).read_bytes()) == '190f2ad9a50a78d0d8bfac1eb383f350e36586688510aa025e74435e6c28332d'


    def test_outermost_first_and_historical_inputs_unchanged(self):
        before, *successors = states()
        for common in (before, *successors):
            original = copy.deepcopy(common)
            c, f = M.admit_pr_shared_inputs(common, files(common), M.first_native_policy()['source_revision'])
            assert c == before and f == files(before)
            assert common == original
        assert M.admit_pr_shared_inputs(successors[-1], None, M.first_native_policy()['source_revision'])[0] == before


    def test_partial_bundle_mode_and_pin_refused(self):
        for stage in range(1, len(states())):
            for mutation in ("missing", "blob", "mode", "old", "pin"):
                with self.subTest(stage=stage, mutation=mutation):
                    before = states()[0]
                    common = dict(states()[stage])
                    path = 'pyproject.toml'
                    tree = files(common)
                    pin = M.first_native_policy()['source_revision']
                    if mutation == 'missing':
                        common.pop(path); tree.pop(path)
                    elif mutation == 'blob':
                        common[path] = 'f' * 40
                    elif mutation == 'mode':
                        tree[path] = ('100755', common[path])
                    elif mutation == 'old':
                        common[path] = before[path]
                    else:
                        pin = 'f' * 40
                    with self.assertRaises(ValueError):
                        M.admit_pr_shared_inputs(common, tree, pin)


    def test_pending_pr256_bundle_is_not_admitted(self):
        policy = json.loads((ROOT / 'ops-shared-input-successors.json').read_text())
        assert 'reviewed_pr256_shared_input_transition' not in policy
        review = ROOT / 'reviews/ops-pr256-20261103'
        assert json.loads((review / 'qualification.json').read_text())['status'] == 'PENDING_FINAL_HEAD_REVIEW'
        pending = json.loads((review / 'source-freeze.json').read_text())
        common = states()[-1] | {p: c['after_blob'] for p, c in pending['changes'].items()}
        with self.assertRaisesRegex(ValueError, 'bundle missing or changed'):
            M.admit_pr_shared_inputs(common, files(common), M.first_native_policy()['source_revision'])


    def test_seal_chain_tampering_refused(self):
        for mutation in ("record", "history", "delete", "extra"):
            with self.subTest(mutation=mutation):
                policy = json.loads((ROOT / 'ops-shared-input-successors.json').read_text())
                if mutation == 'record':
                    policy['reviewed_pr122_shared_input_transition']['source_after'] = 'f' * 40
                elif mutation == 'history':
                    policy['reviewed_miniapp_membership_transition']['reviewer'] = 'changed'
                elif mutation == 'delete':
                    del policy['reviewed_pr122_shared_input_transition']
                else:
                    policy['unreviewed'] = {}
                with patch.object(M, 'read_json', return_value=policy), self.assertRaises(ValueError):
                    M.reviewed_pr_shared_input_transitions()


    def test_real_git_ancestry_and_parent_trees(self):
        import tempfile
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        tmp_path = Path(temporary.name)
        def git(*args):
            return subprocess.check_output(['git', '-C', str(tmp_path), *args], stderr=subprocess.DEVNULL).decode().strip()
        git('init', '-q')
        git('config', 'user.name', 'fixture')
        git('config', 'user.email', 'fixture@example.invalid')
        git('config', 'commit.gpgsign', 'false')
        git('config', 'core.filemode', 'true')
        records = []
        for n in range(3):
            if n:
                git('commit', '-q', '--allow-empty', '-m', 'intermediate')
            (tmp_path / 'pyproject.toml').write_text(f'# stage {n}\n')
            (tmp_path / 'uv.lock').write_text(f'# lock {n}\n')
            git('add', '.')
            git('commit', '-qm', f'stage {n}')
            rev = git('rev-parse', 'HEAD')
            if n:
                records.insert(0, {'source_before': prev, 'source_after': rev, 'changes': {
                    p: {'before_blob': git('rev-parse', prev + ':' + p),
                        'after_blob': git('rev-parse', rev + ':' + p), 'mode': '100644', 'source': rev}
                    for p in ('pyproject.toml', 'uv.lock')}})
            prev = rev
        after_blobs = {(p, c['after_blob']) for r in records for p, c in r['changes'].items()}
        with patch.object(M, 'reviewed_pr_shared_input_transitions', return_value=records), \
             patch.object(M, 'PR_SHARED_INPUT_AFTER_BLOBS', after_blobs), \
             patch.object(M, 'PR_SHARED_INPUT_SOURCE_REVISIONS', tuple(r['source_after'] for r in records)):
            M.pr_shared_input_successor_proof(tmp_path, rev)
            # Same blobs on an unrelated root cannot borrow the merge's approval.
            unrelated = git('commit-tree', rev + '^{tree}', '-m', 'unrelated')
            with self.assertRaisesRegex(ValueError, 'ancestry'):
                M.pr_shared_input_successor_proof(tmp_path, unrelated)
            before = records[0]['source_before']
            records[0]['source_before'] = unrelated
            with self.assertRaisesRegex(ValueError, 'ancestry'):
                M.pr_shared_input_successor_proof(tmp_path, rev)
            records[0]['source_before'] = before
            for mutation in ('mode', 'delete', 'replace', 'revert_bundle'):
                git('checkout', '-q', '-f', rev)
                p = tmp_path / 'pyproject.toml'
                if mutation == 'revert_bundle':
                    for name in ('pyproject.toml', 'uv.lock'):
                        (tmp_path / name).write_text(git('show', records[-1]['source_before'] + ':' + name) + '\n')
                elif mutation == 'mode': p.chmod(0o755)
                elif mutation == 'delete': p.unlink()
                else: p.write_text('# unexpected\n')
                git('add', '.')
                git('commit', '-qm', mutation)
                with self.assertRaisesRegex(ValueError, 'blob or mode'):
                    M.pr_shared_input_successor_proof(tmp_path, git('rev-parse', 'HEAD'))


    def test_shared_input_source_objects_exist_when_source_available(self):
        source = ROOT / 'yueops-src'
        if not source.exists() or subprocess.run(
                ['git', '-C', str(source), 'rev-parse', '--git-dir'],
                capture_output=True).returncode:
            self.skipTest('yueops source checkout is unavailable')
        policy = json.loads((ROOT / 'ops-shared-input-successors.json').read_text())
        for name, record in policy.items():
            if not isinstance(record, dict):
                continue
            for field in ('source_before', 'source_after'):
                with self.subTest(record=name, field=field):
                    result = subprocess.run(
                        ['git', '-C', str(source), 'cat-file', '-e', record[field] + '^{commit}'],
                        capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
        record = M.reviewed_pr_shared_input_transitions()[0]
        review = ROOT / 'reviews/ops-pr122-20261103'
        freeze = json.loads((review / 'source-freeze.json').read_text())
        tree = subprocess.check_output(
            ['git', '-C', str(source), 'rev-parse', record['source_after'] + '^{tree}'],
            text=True).strip()
        self.assertEqual(tree, freeze['source_tree'])
