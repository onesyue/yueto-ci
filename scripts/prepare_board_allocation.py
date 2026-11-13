"""Trusted Board allocation preparation; never executes candidate source code.

The caller owns an already authorized read-only credential and must revoke it
before source execution. This tool does not mint tokens or enable a workflow.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

REPOSITORY = 'onesyue/yueboard'
REMOTE = 'https://github.com/' + REPOSITORY + '.git'
SHA = re.compile(r'[0-9a-f]{40}')


class PreparationError(ValueError):
    pass


def revision(value: object) -> str:
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise PreparationError('invalid exact commit identity')
    return value


def execute(command: list[str], env: dict[str, str], *, data: str | None = None) -> str:
    try:
        result = subprocess.run(command, input=data, text=True, capture_output=True,
                                env=env, timeout=300, check=True)
    except (OSError, subprocess.SubprocessError):
        # Remote stderr can contain attacker-controlled text or credential data.
        raise PreparationError('trusted preparation command failed') from None
    return result.stdout


def api(endpoint: str, env: dict[str, str]) -> object:
    raw = execute(['gh', 'api', '--hostname', 'github.com',
                   '-H', 'Accept: application/vnd.github+json', endpoint], env)
    try:
        return json.loads(raw)
    except ValueError:
        raise PreparationError('invalid GitHub metadata response') from None


def remote_snapshot(env: dict[str, str]) -> tuple[str, list[dict]]:
    master = api(f'repos/{REPOSITORY}/commits/master', env)
    if not isinstance(master, dict):
        raise PreparationError('missing master metadata')
    master_sha = revision(master.get('sha'))
    pulls: list[dict] = []
    seen: set[int] = set()
    for page in range(1, 6):
        rows = api(f'repos/{REPOSITORY}/pulls?state=open&sort=created&direction=asc&per_page=100&page={page}', env)
        if not isinstance(rows, list) or len(rows) > 100:
            raise PreparationError('invalid pull request enumeration')
        for row in rows:
            if not isinstance(row, dict) or type(row.get('number')) is not int or row['number'] <= 0:
                raise PreparationError('invalid pull request number')
            if row['number'] in seen or row.get('state') != 'open' or not isinstance(row.get('head'), dict):
                raise PreparationError('duplicate or inconsistent pull request metadata')
            seen.add(row['number'])
            pulls.append({'number': row['number'], 'head_sha': revision(row['head'].get('sha'))})
        if len(pulls) >= 500:
            raise PreparationError('open pull request list reached 500; completeness refused')
        if len(rows) < 100:
            return master_sha, sorted(pulls, key=lambda row: row['number'])
    raise PreparationError('incomplete pull request enumeration')


def git(root: Path, env: dict[str, str], *args: str, data: str | None = None) -> str:
    return execute(['git', '--no-replace-objects', '-c', 'init.templateDir=',
                    '-c', 'credential.helper=', '-c', 'credential.helper=!gh auth git-credential',
                    '-c', 'credential.useHttpPath=true', '-C', str(root), *args], env, data=data)


def object_closure(root: Path, env: dict[str, str], sha: str) -> None:
    if git(root, env, 'cat-file', '-t', sha).strip() != 'commit':
        raise PreparationError('prepared identity is not a commit')
    tree = git(root, env, 'ls-tree', '-rz', sha, '--', 'internal/platform/db/migrations/')
    blobs = []
    for entry in tree.split('\0'):
        if not entry:
            continue
        meta, separator, path = entry.partition('\t')
        fields = meta.split()
        if not separator or len(fields) != 3 or fields[1] != 'blob':
            raise PreparationError('invalid prepared migration tree')
        if path.endswith('.sql'):
            if fields[0] not in ('100644', '100755'):
                raise PreparationError('migration SQL is not a regular file')
            blobs.append(revision(fields[2]))
    if not blobs:
        raise PreparationError('empty prepared migration tree')
    expected = set(blobs)
    checked = git(root, env, 'cat-file', '--batch-check=%(objectname) %(objecttype)',
                  data='\n'.join(sorted(expected)) + '\n').splitlines()
    if len(checked) != len(expected) or set(checked) != {blob + ' blob' for blob in expected}:
        raise PreparationError('missing prepared migration blob')


def prepare(candidate: str, output: Path) -> dict:
    candidate = revision(candidate)
    token = os.environ.get('GH_TOKEN', '')
    if not token or '\n' in token or '\r' in token:
        raise PreparationError('an authorized read-only preparation credential is required')
    output.mkdir(parents=True, exist_ok=False)
    home = output / 'auth-home'
    home.mkdir(mode=0o700)
    source = output / 'source'
    source.mkdir()
    # No workstation selectors, helpers, URLs, headers or cached gh login are
    # inherited. The token exists only in the trusted preparation process tree.
    env = {'PATH': os.environ.get('PATH', os.defpath), 'HOME': str(home),
           'GH_CONFIG_DIR': str(home), 'GH_TOKEN': token, 'GH_PROMPT_DISABLED': '1',
           'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
           'GIT_TERMINAL_PROMPT': '0', 'GIT_NO_LAZY_FETCH': '1', 'LC_ALL': 'C'}
    try:
        master, pulls = remote_snapshot(env)
        git(source, env, 'init', '--quiet')
        refs = [('refs/heads/master', master, 'refs/prepared/master'),
                (candidate, candidate, 'refs/prepared/candidate')]
        refs += [(f'refs/pull/{row["number"]}/head', row['head_sha'],
                  f'refs/prepared/pull-{row["number"]}') for row in pulls]
        git(source, env, 'fetch', '--quiet', '--atomic', '--no-tags', '--no-recurse-submodules',
            REMOTE, *[f'{remote}:{local}' for remote, _, local in refs])
        for _, expected, local in refs:
            if git(source, env, 'rev-parse', '--verify', local).strip() != expected:
                raise PreparationError('pull or master changed during object preparation')
        for sha in {expected for _, expected, _ in refs}:
            object_closure(source, env, sha)
        if remote_snapshot(env) != (master, pulls):
            raise PreparationError('open pull request set or master changed during preparation')
        git(source, env, 'checkout', '--quiet', '--detach', candidate)
        if git(source, env, 'rev-parse', '--verify', 'HEAD').strip() != candidate:
            raise PreparationError('candidate checkout identity differs')
        receipt = {'schema_version': 1, 'repository': REPOSITORY, 'candidate_sha': candidate,
                   'master_sha': master, 'open_pull_requests': pulls}
        # No token is written to files. Any unexpected auth-home writes indicate
        # preparation violated its contract, so withhold the success receipt.
        if list(home.iterdir()):
            raise PreparationError('unexpected credential persistence during preparation')
        home.rmdir()
        pending = output / '.allocation-receipt.pending'
        with pending.open('x') as handle:
            json.dump(receipt, handle, sort_keys=True)
            handle.write('\n')
        pending.chmod(0o444)
        pending.rename(output / 'allocation-receipt.json')
        return receipt
    finally:
        # Do not claim credential revocation: that is the trusted caller's
        # required boundary before invoking any candidate process.
        env.pop('GH_TOKEN', None)
        if home.exists():
            # Only the freshly created auth directory is removed, including on
            # command failure. Cleanup failure propagates; source may not run.
            shutil.rmtree(home)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        receipt = prepare(args.candidate, args.output.resolve())
    except (OSError, PreparationError):
        print('Board allocation preparation failed; no source execution authorized', file=sys.stderr)
        return 2
    print(f'Prepared exact Board allocation objects for {len(receipt["open_pull_requests"])} open PRs; credential cleanup still required')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
