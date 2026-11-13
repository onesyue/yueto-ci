#!/usr/bin/env python3
"""Thin workflow adapter: preserve phase status and whitelist optional outputs."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile


def read_result(path: Path, role: str, phase: str, status: int) -> str:
    allowed = {'layout=workspace\n', 'layout=legacy\n'} if phase == 'prepare' else (
        {'visual=compared\n'} if (role, phase) == ('e2e', 'test') else set())
    if not path.exists() and not path.is_symlink():
        if allowed and status == 0:
            raise ValueError('successful phase did not produce its required result')
        return ''
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError('phase result must be a regular file')
        data = handle.read(257)
    result = data.decode('ascii')
    if result not in allowed:
        raise ValueError('invalid phase result')
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('role', choices=('frontends', 'components', 'e2e'))
    parser.add_argument('source', type=Path)
    parser.add_argument('policy', type=Path)
    parser.add_argument('temp', type=Path)
    parser.add_argument('--frontend-phase', required=True, choices=('prepare', 'lint', 'test', 'design'))
    parser.add_argument('--database-adapter', choices=('loopback', 'github-service'))
    args = parser.parse_args()
    status = 2
    try:
        with tempfile.TemporaryDirectory(prefix='board-frontend.', dir=args.temp.resolve()) as directory:
            result = Path(directory) / 'result'
            command = ['bash', str(args.policy.resolve() / 'scripts/board-validation.sh'), args.role,
                       str(args.source.resolve()), str(args.policy.resolve()), str(args.temp.resolve()),
                       '--frontend-phase', args.frontend_phase, '--result', str(result)]
            if args.database_adapter:
                command += ['--database-adapter', args.database_adapter]
            environment = dict(os.environ)
            # Source stdout is never parsed and cannot write workflow outputs.
            environment.pop('GITHUB_OUTPUT', None)
            status = subprocess.run(command, env=environment, check=False).returncode
            status = status if status >= 0 else 128 - status
            value = read_result(result, args.role, args.frontend_phase, status)
            if value and os.environ.get('GITHUB_OUTPUT'):
                with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
                    output.write(value)
    except (OSError, ValueError) as error:
        print(f'board-validation-output: {error}', file=sys.stderr)
        return status or 2
    return status


if __name__ == '__main__':
    raise SystemExit(main())
