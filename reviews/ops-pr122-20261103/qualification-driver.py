#!/usr/bin/env python3
"""Verify real source objects and admission using a disposable policy copy.

Usage: python3 qualification-driver.py /path/to/local/yueops
The source checkout is read-only; no Git objects or branches are created.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASE = 'c4f60c381e9eeb6c499bdf8313170e7f6f496c95'
HEAD = '047bbf81034093db226b81ccde9f6159a2c782aa'


def main():
    source = Path(sys.argv[1]).resolve()

    def git(*args):
        return subprocess.check_output(
            ['git', '-C', str(source), *args], text=True).strip()

    record = json.loads((ROOT / 'ops-shared-input-successors.json').read_text())[
        'reviewed_pr122_shared_input_transition']
    review = Path(__file__).resolve().parent
    freeze = json.loads((review / 'source-freeze.json').read_text())
    for field, filename in (
            ('source_freeze_sha256', 'source-freeze.json'),
            ('qualification_receipt_sha256', 'qualification.json'),
            ('independent_review_sha256', 'independent-review.md')):
        assert record[field] == hashlib.sha256((review / filename).read_bytes()).hexdigest()
    assert freeze['changes'] == record['changes']
    assert freeze['source_tree'] == git('rev-parse', record['source_after'] + '^{tree}')
    for field in ('source_before', 'source_after'):
        assert record[field] == freeze[field]
        git('cat-file', '-e', record[field] + '^{commit}')
        git('merge-base', '--is-ancestor', record[field], HEAD)
    for path, change in record['changes'].items():
        for field, blob in (('source_before', 'before_blob'), ('source_after', 'after_blob')):
            mode, kind, actual, _ = git('ls-tree', record[field], path).split()
            assert (mode, kind, actual) == (change['mode'], 'blob', change[blob])

    with tempfile.TemporaryDirectory() as tmp:
        policy = Path(tmp)
        shutil.copytree(ROOT / 'scripts', policy / 'scripts')
        for path in ROOT.glob('*.json'):
            shutil.copy2(path, policy / path.name)
        pin = policy / 'ops-first-native-successors.json'
        value = json.loads(pin.read_text())
        value['source_revision'] = HEAD
        pin.write_text(json.dumps(value, indent=2) + '\n')
        result = subprocess.run(
            [sys.executable, str(policy / 'scripts/admission-precheck.py'),
             '--repo', 'yueops', '--source', str(source), '--base', BASE, '--head', HEAD],
            capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout, end='')


if __name__ == '__main__':
    main()
