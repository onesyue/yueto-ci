"""Local lifecycle adapter; all source validation stays in shared executors."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


def capture(command: list[str], env: dict) -> str:
    return subprocess.check_output(command, text=True, env=env).strip()


def toolchain(contract: dict, env: dict) -> None:
    if capture(['go', 'env', 'GOVERSION'], env) != 'go' + contract['go']:
        raise ValueError('image Go compiler differs from workflow')
    if capture(['node', '--version'], env).split('.')[0] != 'v' + contract['node']:
        raise ValueError('image Node major differs from workflow')
    buf = shutil.which('buf', path=env.get('PATH'))
    if not buf or hashlib.sha256(Path(buf).read_bytes()).hexdigest() != contract['buf_sha256']:
        raise ValueError('image Buf checksum differs from workflow')
    if capture([buf, '--version'], env) != contract['buf']:
        raise ValueError('image Buf version differs from workflow')


def run(report: dict) -> int:
    job = Path(os.environ['CI_CHECK_JOB'])
    source = Path(os.environ['GITHUB_WORKSPACE'])
    policy = source / '.ci-policy'
    temp = Path(os.environ['RUNNER_TEMP'])
    role = os.environ['BOARD_ROLE']
    if role not in ('quality', 'race', 'postgres', 'migration', 'frontends', 'components', 'e2e'):
        raise ValueError('unsupported Board role')
    for key in ('GH_TOKEN', 'GITHUB_TOKEN', 'GH_ENTERPRISE_TOKEN', 'GITHUB_ENTERPRISE_TOKEN'):
        if os.environ.get(key):
            raise ValueError('source credential is not allowed: ' + key)
    contract = json.loads((job / 'contract.json').read_text())
    env = {key: os.environ[key] for key in ('PATH', 'HOME', 'LANG', 'LC_ALL', 'YUE_CI_PYTHON',
           'GITHUB_WORKSPACE', 'RUNNER_TEMP', 'TMPDIR', 'GITHUB_PATH') if key in os.environ}
    env |= {'TZ': 'UTC', 'CI': 'true', 'GOTOOLCHAIN': 'local', 'PROMOTE': 'false',
            'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1'}
    os.chdir(source)
    for path, expected in ((source, os.environ['CI_CHECK_SOURCE_SHA']), (policy, os.environ['CI_CHECK_POLICY_SHA'])):
        if capture(['git', '--no-replace-objects', '-C', str(path), 'rev-parse', 'HEAD'], env) != expected:
            raise ValueError('container checkout identity differs')
    toolchain(contract, env)

    def command(args: list[str], extra: dict | None = None) -> None:
        print('::board-local::' + role + ' ' + Path(args[1]).name, flush=True)
        subprocess.run(args, env=env | (extra or {}), check=True)

    def phase_environment(name: str) -> dict:
        return {key: value.replace('${{ github.workspace }}', str(source))
                for key, value in contract['environments'][name].items()}

    def backend(name: str, extra: dict | None = None, pg: bool = False) -> None:
        args = ['bash', str(policy / 'scripts/board-validation.sh'), name, str(source), str(policy), str(temp)]
        if pg:
            args += ['--database-adapter', 'loopback']
            if name != 'postgres-clean':
                args += ['--receipt', str(temp / ('yueboard-pg-' + role + '.json'))]
        command(args, extra)

    def frontend(phase: str, extra: dict | None = None) -> str:
        result = temp / ('frontend-' + phase + '.output')
        with result.open('x'):
            pass
        args = [env['YUE_CI_PYTHON'], str(policy / 'scripts/board-validation-output.py'), role,
                str(source), str(policy), str(temp), '--frontend-phase', phase]
        if role == 'e2e' and phase == 'test':
            args += ['--database-adapter', 'loopback']
        command(args, (extra or {}) | {'GITHUB_OUTPUT': str(result)})
        return result.read_text()

    pg_id = ''
    status = 0
    validation_started = False
    e2e_failed = False
    try:
        command(['bash', str(policy / 'scripts/board-validation-preflight.sh'), 'dependencies', str(source), str(policy)])
        # Cold isolated caches: no cache hit can bypass native checks.
        command(['bash', str(policy / 'scripts/board-validation-preflight.sh'), 'contract', str(source), str(policy)])
        if role in ('postgres', 'migration', 'e2e'):
            pg_id = capture(['docker', 'create', '--platform', 'linux/amd64',
                             '-e', 'POSTGRES_PASSWORD=ci', '-e', 'POSTGRES_DB=yueboard_test',
                             '-p', '127.0.0.1:5432:5432', *contract['postgres_health'],
                             contract['postgres_image']], env)
            if not re.fullmatch(r'[a-f0-9]{64}', pg_id):
                pg_id = ''
                raise ValueError('PostgreSQL create returned no exact identity')
            (temp / 'postgres-container.id').write_text(pg_id + '\n')
            subprocess.run(['docker', 'start', pg_id], env=env, check=True, timeout=120)
            healthy = False
            for _ in range(60):
                state = capture(['docker', 'inspect', '--format', '{{.State.Health.Status}}', pg_id], env)
                if state == 'healthy':
                    healthy = True
                    break
                if state != 'starting':
                    break
                time.sleep(1)
            if not healthy:
                raise ValueError('PostgreSQL service failed health check')
            if role in ('postgres', 'migration'):
                command(['bash', str(policy / 'scripts/board-postgres-diagnostics.sh')], {'PG_SERVICE': pg_id})
        validation_started = True
        if role in ('quality', 'race'):
            backend(role)
        elif role in ('postgres', 'migration'):
            backend(role, phase_environment(role), pg=True)
            if role == 'postgres':
                backend('postgres-clean', phase_environment('clean'), pg=True)
        else:
            layout = frontend('prepare')
            if layout not in ('layout=workspace\n', 'layout=legacy\n'):
                raise ValueError('invalid frontend layout output')
            if layout == 'layout=workspace\n':
                try:
                    frontend('lint' if role == 'frontends' else 'test', phase_environment('e2e') if role == 'e2e' else None)
                except subprocess.CalledProcessError:
                    e2e_failed = role == 'e2e'
                    raise
            if role == 'frontends':
                frontend('design')
    except subprocess.CalledProcessError as error:
        status = error.returncode if error.returncode > 0 else 128 - error.returncode
        print('ci-check: Board phase failed', file=sys.stderr)
    except (OSError, ValueError) as error:
        validation_started = False
        status = 2
        print(f'ci-check: Board infrastructure failure: {error}', file=sys.stderr)
    finally:
        # Shared executors reserve exit 2 for failed prerequisites/contracts.
        # A source command can also return 2; conservatively keep it incomplete.
        report['complete'] = validation_started and status != 2
        report['validation_exit_code'] = status if validation_started else None
        errors = []
        if e2e_failed:
            try:
                for name in ('playwright-report', 'test-results', '.state/server.log'):
                    artifact = source / 'test/e2e' / name
                    if artifact.exists():
                        # Reports cannot escape the source checkout via symlinks.
                        if not artifact.resolve().is_relative_to(source.resolve()) or artifact.is_symlink() or (artifact.is_dir() and any(p.is_symlink() for p in artifact.rglob('*'))):
                            raise ValueError('unsafe E2E report path')
                        dest = job / 'e2e-report' / name
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        if artifact.is_dir():
                            shutil.copytree(artifact, dest)
                        else:
                            shutil.copy2(artifact, dest)
            except (OSError, ValueError) as error:
                errors.append('E2E report retention failed: ' + str(error))
        if pg_id:
            try:
                with (temp / 'yueboard-postgres.log').open('w') as log:
                    subprocess.run(['docker', 'logs', pg_id], env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
            except (OSError, subprocess.SubprocessError) as error:
                errors.append('PostgreSQL log retention failed: ' + str(error))
            finally:
                try:
                    subprocess.run(['docker', 'rm', '--force', pg_id], env=env, check=True, timeout=120)
                except (OSError, subprocess.SubprocessError) as error:
                    errors.append('PostgreSQL cleanup failed: ' + str(error))
        if errors:
            report['infrastructure_errors'] = errors
            report['complete'] = False
            status = 2

    return status


def main() -> int:
    report = {'role': os.environ.get('BOARD_ROLE'), 'source': os.environ.get('CI_CHECK_SOURCE_SHA'),
              'policy': os.environ.get('CI_CHECK_POLICY_SHA'), 'complete': False}
    try:
        status = run(report)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'ci-check: Board infrastructure failure: {error}', file=sys.stderr)
        report['infrastructure_errors'] = [str(error)]
        report['complete'] = False
        status = 2
    report['exit_code'] = status
    (Path(os.environ['CI_CHECK_JOB']) / 'role-result.json').write_text(json.dumps(report) + '\n')
    return status


if __name__ == '__main__':
    raise SystemExit(main())
