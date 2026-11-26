"""Replay the public Node validation plan in a disposable source checkout."""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

_CI_LIB = str(Path(__file__).resolve().parent / "lib")
if _CI_LIB not in sys.path:
    sys.path.insert(0, _CI_LIB)
from ci_constants import GITHUB_HTTPS_ORIGIN

POLICY = Path(__file__).resolve().parents[1]


def profiles(source_sha: str, env: dict[str, str]) -> list[str]:
    raw = subprocess.check_output(
        ['bash', POLICY / 'scripts/plan-build-targets.sh', 'yue-node-validation', source_sha],
        env=env, text=True)
    rows = json.loads(raw)['validation_matrix']
    selected = [row['node_profile'] for row in rows]
    if sorted(selected) != ['hy2', 'vless'] or any(
        row['ref'] != source_sha or row['repo'] != 'onesyue/yue-node'
        or row['validation'] != 'yue-node' for row in rows
    ):
        raise ValueError('unexpected yue-node validation matrix')
    return selected


def run(source: Path, sha: str, board: Path, output: Path, home: str) -> int:
    env = {'PATH': os.environ['PATH'], 'HOME': home, 'TZ': 'UTC',
           'YUE_CI_PYTHON': sys.executable, 'GIT_TERMINAL_PROMPT': '0',
           'CGO_ENABLED': '1', 'GOFLAGS': '-mod=vendor', 'GOWORK': 'off'}
    selected = profiles(sha, env)
    linux = platform.system() == 'Linux'
    if not linux:
        print('SKIP-PLATFORM dependencies', flush=True)
        for profile in selected:
            print('SKIP-PLATFORM', profile, flush=True)

    def role(name, command, role_env=env):
        with (output / (name + '.log')).open('w') as log:
            code = subprocess.run(command, cwd=source, env=role_env, stdout=log,
                                  stderr=subprocess.STDOUT).returncode
        print('PASS' if code == 0 else 'FAIL', name, 'rc=' + str(code), flush=True)
        return code

    preflight = ['bash', POLICY / 'scripts/node-validation-preflight.sh']
    paths = [source, POLICY, board]
    if linux and role('dependencies', [*preflight, 'dependencies', *paths]):
        return 2
    if role('contract', [*preflight, 'contract', *paths]):
        return 1

    for tool in ('make', 'awk', 'git', 'gpg', 'mktemp', 'go'):
        if not shutil.which(tool, path=env['PATH']):
            print('MISSING-TOOL verify-fork-tags', tool, file=sys.stderr)
            return 2
    # Git may consult the caller's HTTPS credential helper only for the fork
    # verification. The preflight and profile children have a disposable HOME.
    fork_env = dict(env, HOME=os.environ['HOME'], GIT_ALLOW_PROTOCOL='https')
    token = os.environ.get('YUETO_FORK_READ_TOKEN')
    if token:
        auth = base64.b64encode(('x-access-token:' + token).encode()).decode()
        fork_env.update(GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='http.' + GITHUB_HTTPS_ORIGIN + '/.extraheader',
                        GIT_CONFIG_VALUE_0='AUTHORIZATION: basic ' + auth)
    if role('verify-fork-tags', ['make', 'verify-fork-tags'], fork_env):
        return 1
    if not linux:
        return 3
    failed = False
    for profile in selected:
        if role(profile, ['bash', POLICY / 'scripts/node-validation.sh', profile, source]):
            failed = True
    return int(failed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('sha')
    parser.add_argument('board', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    try:
        with tempfile.TemporaryDirectory(prefix='node-home-', dir=args.source.parent) as home:
            return run(args.source, args.sha, args.board, args.output, home)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        print(f'ci-check: node prerequisites: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
