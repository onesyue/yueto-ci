#!/usr/bin/env python3
"""Recreate deterministic merge objects in a disposable clone and check admission.

Usage: python3 qualification-driver.py /path/to/local/yueops
No source branch or policy pin is changed. No source code is executed.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASE = 'c56159246c31ede8e24b40b8626b6a3c6b0b0137'
HEADS = {122: '56a7e0412e9bd1d297ba4a5dd3d363147fac463c',
         256: '0d8c8f47432db7f2b11a8dd2bfc5081350929e76',
         260: 'e4703455a8d551e498118186fcbe47ca5768efb9'}


def main():
    env = dict(os.environ, GIT_AUTHOR_NAME='Local qualification',
               GIT_AUTHOR_EMAIL='qualification@example.invalid',
               GIT_COMMITTER_NAME='Local qualification',
               GIT_COMMITTER_EMAIL='qualification@example.invalid',
               GIT_AUTHOR_DATE='2026-11-03T00:00:00Z',
               GIT_COMMITTER_DATE='2026-11-03T00:00:00Z')
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        source = tmp / 'source'
        subprocess.run(['git', 'clone', '-q', '--shared', '--no-checkout', sys.argv[1], str(source)], check=True)
        def git(*args):
            return subprocess.check_output(['git', '-C', str(source), *args], env=env, text=True).strip()
        revs = {'master': BASE}
        before = BASE
        for n in (122, 256, 260):
            if n == 260:
                before = BASE
            tree = git('merge-tree', '--write-tree', before, HEADS[n])
            after = git('commit-tree', tree, '-p', before, '-p', HEADS[n], '-m', f'Local qualification merge #{n}')
            if n != 260:
                freeze = json.loads((ROOT / f'reviews/ops-pr{n}-20261103/source-freeze.json').read_text())
                assert after == freeze['source_after'] and tree == freeze['source_tree']
                for p, c in freeze['changes'].items():
                    assert git('rev-parse', before + ':' + p) == c['before_blob']
                    assert git('rev-parse', after + ':' + p) == c['after_blob']
                    assert git('ls-tree', after, p).split()[0] == c['mode']
            revs[str(n)] = after
            before = after
        policy = tmp / 'policy'
        policy.mkdir()
        shutil.copytree(ROOT / 'scripts', policy / 'scripts')
        for p in ROOT.glob('*.json'):
            shutil.copy2(p, policy / p.name)
        pin = policy / 'ops-first-native-successors.json'
        value = json.loads(pin.read_text())
        results = {}
        for n, rev in revs.items():
            value['source_revision'] = rev
            pin.write_text(json.dumps(value, indent=2) + '\n')
            result = subprocess.run([sys.executable, str(policy / 'scripts/admission-precheck.py'),
                                     '--repo', 'yueops', '--source', str(source),
                                     '--base', BASE, '--head', rev], capture_output=True, text=True)
            expected = 1 if n == '260' else 0
            assert result.returncode == expected, result.stdout + result.stderr
            results[n] = {'head': rev, 'exit': result.returncode,
                          'status': 'ADMISSION_REJECTED' if expected else 'ADMISSION_ACCEPTED'}
        print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
