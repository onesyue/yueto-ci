"""Bind credential-free execution to independently prepared, owned clones."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


def git(path: Path, *args: str) -> str:
    return subprocess.check_output(['git', '--no-replace-objects', '-C', str(path), *args],
                                   text=True).strip()


def validate(output: Path, checkouts: Path, identities: dict) -> dict:
    if checkouts.is_symlink() or checkouts.parent.resolve() != output.resolve() or not re.fullmatch(r'checkouts\.[A-Za-z0-9]+', checkouts.name):
        raise ValueError('prepared checkouts are not an owned output child')
    branches = {}
    for name, repo in [('source', 'yueops'), ('board', 'yueboard'), ('policy', 'yueto-ci')]:
        path = checkouts / name
        if path.is_symlink() or not (path / '.git').is_dir() or (path / '.git').is_symlink():
            raise ValueError('prepared checkout must be an independent clone')
        if git(path, 'rev-parse', 'HEAD') != identities[name] or git(path, 'status', '--porcelain', '--untracked-files=no'):
            raise ValueError('prepared checkout differs or is dirty')
        if git(path, 'config', '--local', '--get', 'remote.origin.url') != f'https://github.com/onesyue/{repo}.git':
            raise ValueError('prepared origin differs')
        keys = git(path, 'config', '--local', '--name-only', '--list').splitlines()
        if any(key.lower().startswith(('credential.', 'include.', 'includeif.')) or key.lower().endswith('.extraheader') for key in keys):
            raise ValueError('prepared checkout contains credential configuration')
        branches[name] = git(path, 'rev-parse', 'refs/remotes/origin/master')
    return branches


def prepare(receipt: Path, checkouts: Path, identities: dict) -> None:
    branches = validate(receipt.parent, checkouts, identities)
    value = {'schema': 1, 'checkouts': str(checkouts.resolve()), 'identities': identities,
             'default_branches': branches}
    marker = checkouts / '.ci-check-owned.json'
    with marker.open('x') as handle:
        json.dump(value, handle, sort_keys=True)
    with receipt.open('x') as handle:
        json.dump(value, handle, sort_keys=True)


def claim(receipt: Path, output: Path, identities: dict) -> Path:
    if receipt.is_symlink() or receipt.parent.resolve() != output.resolve():
        raise ValueError('prepared receipt must belong to the output directory')
    value = json.loads(receipt.read_text())
    if value.get('schema') != 1 or value.get('identities') != identities:
        raise ValueError('prepared input identities differ')
    checkouts = Path(value['checkouts'])
    branches = validate(output, checkouts, identities)
    marker = checkouts / '.ci-check-owned.json'
    if marker.is_symlink() or json.loads(marker.read_text()) != value or branches != value['default_branches']:
        raise ValueError('prepared ownership or default branch evidence differs')
    # Single consumer. A repeated invocation cannot remove another live replay.
    with (checkouts / '.claimed').open('x') as handle:
        handle.write('claimed\n')
    return checkouts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('prepare', 'claim'))
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True)
    for key in ('source', 'board', 'policy', 'base'):
        parser.add_argument('--' + key, required=True)
    args = parser.parse_args()
    identities = {key: getattr(args, key) for key in ('source', 'board', 'policy', 'base')}
    try:
        if not all(re.fullmatch(r'[0-9a-f]{40}', value) for value in identities.values()):
            raise ValueError('prepared identities must be exact commits')
        if args.operation == 'prepare':
            prepare(args.receipt, args.directory, identities)
        else:
            print(claim(args.receipt, args.directory, identities))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'ci-check: preparation rejected: {error}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
