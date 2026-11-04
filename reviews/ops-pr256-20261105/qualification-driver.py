#!/usr/bin/env python3
"""Run the real expand CLI with the on-disk policy and diagnose a refusal."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
HEAD = '72bf60474359d831f0cee70a6246ebf50952ea26'


def main():
    source = Path(sys.argv[1]).resolve()
    spec = importlib.util.spec_from_file_location('qualification_shards', ROOT / 'scripts/pytest-shards.py')
    assert spec is not None and spec.loader is not None
    policy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(policy)
    review = Path(__file__).resolve().parent
    os.environ.update({'GITHUB_SHA': policy.git(ROOT, 'rev-parse', 'HEAD').decode().strip(),
                       'GITHUB_REPOSITORY': 'onesyue/yueto-ci', 'GITHUB_RUN_ID': '1',
                       'GITHUB_RUN_ATTEMPT': '1', 'RUNNER_OS': 'Linux',
                       'RUNNER_ARCH': 'X64', 'ImageVersion': 'local-admission-simulation'})
    record = policy.reviewed_pr_shared_input_transitions()[0]
    freeze = json.loads((review / 'source-freeze.json').read_text())
    for field, name in [('source_freeze_sha256', 'source-freeze.json'),
                        ('independent_review_sha256', 'independent-review.md'),
                        ('qualification_receipt_sha256', 'qualification.json')]:
        assert record[field] == policy.sha((review / name).read_bytes())
    assert policy.git(source, 'rev-parse', record['source_after'] + '^{tree}').decode().strip() == freeze['source_tree']
    policy.pr_shared_input_successor_proof(source, HEAD)
    with tempfile.TemporaryDirectory(prefix='seal256-') as tmp:
        checkout = Path(tmp) / 'source'
        subprocess.run(['git', 'clone', '--quiet', '--shared', '--no-checkout', str(source), str(checkout)], check=True)
        subprocess.run(['git', '-C', str(checkout), 'checkout', '--quiet', '--detach', HEAD], check=True)
        board = policy.read_json(ROOT / 'native-node-contract.json')['yueboard_contract_pin']
        row = {'repo': 'onesyue/yueops', 'ref': HEAD, 'validation': 'yueops'}
        targets = {'matrix': [row], 'validation_matrix': [row]}
        target_file = Path(tmp) / 'targets.json'
        target_file.write_text(json.dumps(targets))
        command = [sys.executable, str(ROOT / 'scripts/pytest-shards.py'), 'expand',
                   '--targets', str(target_file), '--source', str(checkout), '--board', board,
                   '--runner', 'ubuntu-24.04', '--capacity', '20', '--shards', '16']
        result = subprocess.run(command, capture_output=True, text=True)
        (review / 'current-policy-admission.log').write_text(result.stdout + result.stderr)
        diagnosis = {}
        def trace(frame, event, arg):
            if event == 'exception' and frame.f_code.co_name == '_admit_existing_shared_inputs':
                if str(arg[1]) == 'shared collection/dependency input modes changed':
                    values = frame.f_locals
                    expected = values['modes']
                    actual = {p: values['files'].get(p, (None, None))[0] for p in values['common']}
                    diagnosis['effective_mode_differences'] = {
                        p: {'baseline': expected.get(p), 'effective': actual.get(p)}
                        for p in sorted(expected.keys() | actual.keys()) if expected.get(p) != actual.get(p)}
            return trace
        if result.returncode:
            sys.settrace(trace)
            try:
                policy.expand(targets, checkout, board, 'ubuntu-24.04', 20, 16)
            except ValueError as error:
                diagnosis['reason'] = str(error)
            finally:
                sys.settrace(None)
        receipt = {'source_revision': HEAD, 'runner': 'ubuntu-24.04',
                   'status': 'ADMITTED' if result.returncode == 0 else 'REJECTED',
                   'cli_exit_code': result.returncode, 'policy_override': False,
                   'execution': 'Local CLI admission; not Linux runtime tests', **diagnosis}
        (review / 'admission-results.json').write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps(receipt, indent=2))
        return result.returncode


if __name__ == '__main__':
    sys.exit(main())
