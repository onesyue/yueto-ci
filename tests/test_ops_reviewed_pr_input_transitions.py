"""Exact PR shared-input successors peel outside every historical seal."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('pr_input_shards', ROOT / 'scripts/pytest-shards.py')
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
NAMES = tuple(M.REVIEWED_PR_INPUTS)
CURRENT_GENERATION = frozenset({'test_inputs_1105', 'ruff_retired_video', 'site_refresh_plans'})
EVIDENCE_DATES = {'ruff_retired_video': '20261106', 'test_inputs_1105': '20261105', 'site_refresh_plans': '20261110'}


def evidence(name):
    date = EVIDENCE_DATES.get(name, '20261103')
    directory = ROOT / ('reviews/ops-' + name.replace('_', '-') + '-' + date)
    return directory, json.loads((directory / 'source-freeze.json').read_text())


def check_review_and_qualification_bound_to_exact_source(name):
    record = M.reviewed_pr_input_transition(name)
    directory, freeze = evidence(name)
    for field, filename in [('independent_review_sha256', 'independent-review.md'),
                            ('source_freeze_sha256', 'source-freeze.json'),
                            ('qualification_receipt_sha256', 'qualification.json')]:
        assert record[field] == M.sha((directory / filename).read_bytes())
    assert record['changes'] == freeze['changes']
    assert record['source_before'] == freeze['source_before']
    assert record['source_after'] == freeze['source_after']
    assert 'VERDICT: APPROVE' in (directory / 'independent-review.md').read_text()
    q = json.loads((directory / 'qualification.json').read_text())
    assert q['source_revision'] == freeze['merge_revision']
    assert q['status'] == 'PASS_STATIC_SHARED_INPUT_QUALIFICATION_ONLY'
    assert 'NOT_RUN' in q['full_execution_gate']
    if name == 'deploy_ai_exit':
        assert q['exact_single_path_addition'] and q['scan_membership_equal']
        assert q['scan_lines'] >= q['minimum_lines'] == 2800
    elif name == 'ruff_retired_video':
        assert q['only_retired_ruff_exclude_removed'] and q['retired_tree_absent']
        assert q['parsed_other_configuration_equal']
    elif name == 'test_inputs_1105':
        assert q['test_only_inputs'] and q['collection_membership_equal']
        assert q['no_skip_or_import_side_effect_change']
    elif name == 'site_refresh_plans':
        assert q['only_refresh_plans_script_removed'] and q['lockfile_unchanged']
        assert q['no_dependency_or_pin_change']
    else:
        assert q['manifest_only_expected_devdependency_pins']
        assert q['importer_specifiers_match'] and q['all_snapshot_edges_resolve']
        assert q['all_packages_integrity_only']


def check_full_admission_exact_successor_and_predecessor_preserve_history(name):
    _, freeze = evidence(name)
    record = M.reviewed_pr_input_transition(name)
    # Seals frozen after the loadshed native successor see the current baseline.
    baseline = (M.skip_baseline() if name in CURRENT_GENERATION
                else M.reviewed_native_input_successor(M.skip_baseline())[0])
    historical = copy.deepcopy(baseline)
    pin = M.first_native_policy() | {'source_revision': freeze['merge_revision']}
    common = freeze['common_inputs']
    files = {p: (freeze['input_modes'][p], b) for p, b in common.items()}
    original_common, original_files = copy.deepcopy(common), copy.deepcopy(files)
    estate = baseline['reviewed_estate_input_transition']['source_after']
    with patch.object(M, 'first_native_policy', return_value=pin):
        M.admit_shared_inputs(baseline, common, files,
                             source_revision=pin['source_revision'], estate_successor_of=estate)
        before, before_files = M.admit_reviewed_pr_inputs(common, files, pin['source_revision'])
        for path, change in record['changes'].items():
            assert before[path] == change['before_blob']
            assert before_files[path] == (change['mode'], change['before_blob'])
        M.admit_shared_inputs(baseline, before, before_files,
                             source_revision=pin['source_revision'], estate_successor_of=estate)
        # The validators also re-admit without a Git tree in the signed envelope.
        M.admit_shared_inputs(baseline, common, source_revision=pin['source_revision'],
                             estate_successor_of=estate)
    assert baseline == historical
    assert common == original_common and files == original_files
    assert M.sha(M.historical_skip_baseline_bytes()) == record['prior_baseline_sha256']


def check_full_admission_rejects_partial_bundles_unknown_bytes_modes_and_wrong_pin(name, mutation):
    _, freeze = evidence(name)
    record = M.reviewed_pr_input_transition(name)
    for path, change in record['changes'].items():
        common = dict(freeze['common_inputs'])
        files = {p: (freeze['input_modes'][p], b) for p, b in common.items()}
        revision = freeze['merge_revision']
        if mutation == 'missing':
            common.pop(path)
            files.pop(path)
        elif mutation == 'blob':
            common[path] = 'f' * 40
            files[path] = ('100644', 'f' * 40)
        elif mutation in ('mode', 'symlink'):
            files[path] = ('100755' if mutation == 'mode' else '120000', common[path])
        elif mutation == 'tree':
            files[path] = ('100644', 'f' * 40)
        elif mutation == 'old':
            if len(record['changes']) == 1:
                continue  # The complete historical input remains valid.
            common[path] = change['before_blob']
            files[path] = ('100644', change['before_blob'])
        else:
            revision = 'f' * 40
        baseline = (M.skip_baseline() if name in CURRENT_GENERATION
                    else M.reviewed_native_input_successor(M.skip_baseline())[0])
        with patch.object(M, 'first_native_policy', return_value={
                **M.first_native_policy(), 'source_revision': freeze['merge_revision']}):
            with unittest.TestCase().assertRaises(ValueError):
                M.admit_shared_inputs(baseline, common, files, source_revision=revision,
                    estate_successor_of=baseline['reviewed_estate_input_transition']['source_after'])


def check_seal_tampering_fails_closed(name, field):
    policy = M.read_json(ROOT / M.REVIEWED_PR_INPUT_FILES.get(name, 'ops-shared-input-successors.json'))
    record = policy['reviewed_' + name + '_transition']
    record[field] = {} if field == 'changes' else 'unreviewed'
    with patch.object(M, 'read_json', return_value=policy), unittest.TestCase().assertRaises(ValueError):
        M.reviewed_pr_input_transition(name)


def check_real_git_ancestry_and_source_identity(tmp_path, name):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(tmp_path), *args],
                                       stderr=subprocess.DEVNULL, text=True).strip()
    git('init', '-q')
    git('config', 'user.name', 'fixture')
    git('config', 'user.email', 'fixture@example.invalid')
    git('config', 'commit.gpgsign', 'false')
    git('config', 'core.filemode', 'true')
    record = copy.deepcopy(M.reviewed_pr_input_transition(name))
    for path in record['changes']:
        p = tmp_path / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('before ' + path)
    git('add', '.')
    git('commit', '-qm', 'before')
    record['source_before'] = git('rev-parse', 'HEAD')
    for path, change in record['changes'].items():
        change['before_blob'] = git('rev-parse', 'HEAD:' + path)
        (tmp_path / path).write_text('after ' + path)
    git('add', '.')
    git('commit', '-qm', 'after')
    record['source_after'] = git('rev-parse', 'HEAD')
    for path, change in record['changes'].items():
        change.update(after_blob=git('rev-parse', 'HEAD:' + path), source=record['source_after'])
    git('commit', '-q', '--allow-empty', '-m', 'descendant')
    descendant = git('rev-parse', 'HEAD')
    with patch.object(M, 'REVIEWED_PR_INPUTS', {name: M.REVIEWED_PR_INPUTS[name]}), \
         patch.object(M, 'REVIEWED_PR_INPUT_ACTIVATION', {}), \
         patch.object(M, 'reviewed_pr_input_transition', return_value=record):
        for rev in (record['source_before'], record['source_after'], descendant):
            M.reviewed_pr_input_proof(tmp_path, rev)
        path = next(iter(record['changes']))
        (tmp_path / path).chmod(0o755)
        git('add', '.')
        git('commit', '-qm', 'changed mode')
        with unittest.TestCase().assertRaisesRegex(ValueError, 'blob or mode differs'):
            M.reviewed_pr_input_proof(tmp_path, git('rev-parse', 'HEAD'))
        # Same exact bytes copied to a branch without the reviewed source commit.
        git('checkout', '-q', '-f', record['source_before'])
        for path in record['changes']:
            (tmp_path / path).write_text('after ' + path)
        git('add', '.')
        git('commit', '-qm', 'unrelated copy')
        with unittest.TestCase().assertRaisesRegex(ValueError, 'source ancestry differs'):
            M.reviewed_pr_input_proof(tmp_path, git('rev-parse', 'HEAD'))


def check_activation_requires_exact_after_blob():
    record = M.reviewed_pr_input_transition('test_inputs_1105')
    assert M.REVIEWED_PR_INPUT_ACTIVATION['test_inputs_1105'] == frozenset(
        (p, c['after_blob']) for p, c in record['changes'].items())


def check_unrelated_historical_inputs_do_not_activate_new_seals():
    common = {'pytest.ini': 'a' * 40}
    files = {'pytest.ini': ('100644', 'a' * 40)}
    with patch.object(M, 'reviewed_pr_input_transition', side_effect=AssertionError('not applicable')), \
         patch.object(M, 'tree_inputs', return_value=files):
        assert M.admit_reviewed_pr_inputs(common, files, None) == (common, files)
        M.reviewed_pr_input_proof(Path('unused'), 'b' * 40)


def check_stacked_site_successors_peel_to_fixpoint():
    """A later successor must still peel its earlier predecessor (CI 42746203243)."""
    newer = M.reviewed_pr_input_transition('site_refresh_plans')
    older = M.reviewed_pr_input_transition('site_devdeps')
    pkg_after = newer['changes']['site/package.json']['after_blob']
    lock_after = older['changes']['site/pnpm-lock.yaml']['after_blob']
    common = {
        'site/package.json': pkg_after,
        'site/pnpm-lock.yaml': lock_after,
    }
    files = {path: ('100644', blob) for path, blob in common.items()}
    original = copy.deepcopy(common)
    with patch.object(M, 'holds_release_pin', return_value=True):
        before, before_files = M.admit_reviewed_pr_inputs(common, files, 'a' * 40,
                                                          pin_is_ancestor=True)
    pkg_before = older['changes']['site/package.json']['before_blob']
    lock_before = older['changes']['site/pnpm-lock.yaml']['before_blob']
    assert before['site/package.json'] == pkg_before
    assert before['site/pnpm-lock.yaml'] == lock_before
    assert before_files['site/package.json'] == ('100644', pkg_before)
    assert before_files['site/pnpm-lock.yaml'] == ('100644', lock_before)
    assert common == original


class ReviewedPrInputTransitions(unittest.TestCase):
    def test_review_artifacts(self):
        for name in NAMES:
            with self.subTest(name=name):
                check_review_and_qualification_bound_to_exact_source(name)

    def test_full_admission_preserves_history(self):
        for name in NAMES:
            with self.subTest(name=name):
                check_full_admission_exact_successor_and_predecessor_preserve_history(name)

    def test_partial_bundles_and_mutations_rejected(self):
        for name in NAMES:
            for mutation in ('missing', 'blob', 'mode', 'symlink', 'tree', 'old', 'pin'):
                with self.subTest(name=name, mutation=mutation):
                    check_full_admission_rejects_partial_bundles_unknown_bytes_modes_and_wrong_pin(name, mutation)

    def test_seal_tampering_rejected(self):
        for name in NAMES:
            for field in ('prior_baseline_sha256', 'source_before', 'source_after',
                          'independent_review_sha256', 'source_freeze_sha256',
                          'qualification_receipt_sha256', 'changes', 'schema'):
                with self.subTest(name=name, field=field):
                    check_seal_tampering_fails_closed(name, field)

    def test_real_git_ancestry(self):
        for name in NAMES:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                check_real_git_ancestry_and_source_identity(Path(directory), name)

    def test_activation_bound_to_record(self):
        check_activation_requires_exact_after_blob()

    def test_unrelated_historical_inputs(self):
        check_unrelated_historical_inputs_do_not_activate_new_seals()

    def test_stacked_site_successors_peel_to_fixpoint(self):
        check_stacked_site_successors_peel_to_fixpoint()
