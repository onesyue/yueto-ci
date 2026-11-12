"""Bound a complete credential-free ci-check --local execution on a hosted VM."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
SECRET_ENV = ('GH_TOKEN', 'GITHUB_TOKEN', 'GH_ENTERPRISE_TOKEN', 'GITHUB_ENTERPRISE_TOKEN')
EXECUTION_SECONDS = 330 * 60
INITIAL_FREE = 8 * 1024**3
ROLE_FREE = 2 * 1024**3


def clean_environment(output: Path, base: str) -> dict:
    if any(os.environ.get(key) for key in SECRET_ENV):
        raise ValueError('credential environment must end before hosted execution')
    # The host planner executes the signed source's --describe-ci-selection.
    # Do not inherit either credentials or the preparation Git/gh configuration.
    env = {key: os.environ[key] for key in ('PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL', 'RUNNER_TRACKING_ID') if key in os.environ}
    return env | {'TZ': 'UTC', 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1',
                  'GH_CONFIG_DIR': str(output / 'unauthenticated-gh'),
                  'CI_CHECK_OUTPUT': str(output), 'CI_CHECK_MIGRATION_BASE': base,
                  'CI_CHECK_MIN_FREE_BYTES': str(ROLE_FREE)}


def cleanup_containers(output: Path) -> None:
    owner = hashlib.sha256(str((output / 'local').resolve()).encode()).hexdigest()
    seen = set()
    errors = []
    for receipt in sorted((output / 'local').glob('*/container.*')):
        if receipt.name not in ('container.json', 'container.cid'):
            continue
        try:
            if receipt.is_symlink():
                raise ValueError('container receipt is not an owned regular file')
            container = (receipt.read_text().strip() if receipt.name == 'container.cid'
                         else json.loads(receipt.read_text())['container_id'])
            if not isinstance(container, str) or not re.fullmatch(r'[a-f0-9]{64}', container):
                raise ValueError('invalid recorded container identity')
            if container in seen:
                continue
            seen.add(container)
            inspected = subprocess.run(['docker', 'inspect', '--format',
                                         '{{index .Config.Labels "ci-check.owner"}}', container],
                                        text=True, capture_output=True, timeout=30, check=False)
            if inspected.returncode:
                if 'No such object' in inspected.stderr or 'No such container' in inspected.stderr:
                    continue
                raise ValueError('cannot verify recorded container ownership')
            if inspected.stdout.strip() != owner:
                raise ValueError('refusing to remove an unowned container')
            try:
                with (output / f'timeout-container-{container}.log').open('w') as log:
                    subprocess.run(['docker', 'logs', container], stdout=log, stderr=subprocess.STDOUT,
                                   check=True, timeout=60)
            finally:
                subprocess.run(['docker', 'rm', '--force', container], check=True,
                               stdout=subprocess.DEVNULL, timeout=60)
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
            errors.append(f'{receipt.parent.name}/{receipt.name}: {error}')
    if errors:
        raise ValueError('; '.join(errors))


def stop_session(process: subprocess.Popen | None, session_id: int) -> None:
    """Stop only the recorded session created with start_new_session=True."""
    if process is not None and session_id != process.pid:
        raise ValueError('process session ownership differs')
    try:
        os.killpg(session_id, signal.SIGTERM)
    except ProcessLookupError:
        if process is not None:
            process.wait(timeout=10)
        return
    if process is not None:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
    else:
        time.sleep(0.5)
    # Reaping the leader does not prove descendants have stopped. Always send
    # KILL to this same owned group, even when the leader exited after TERM.
    try:
        os.killpg(session_id, signal.SIGKILL)
    except ProcessLookupError:
        pass
    if process is not None:
        process.wait(timeout=10)
    deadline = time.monotonic() + 5
    while True:
        try:
            os.killpg(session_id, 0)
        except ProcessLookupError:
            return
        if time.monotonic() >= deadline:
            raise ValueError('owned process group still exists after bounded termination')
        time.sleep(0.05)


def process_identity(pid: int) -> dict:
    if sys.platform == 'linux':
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        return {'group': int(fields[2]), 'session': int(fields[3]), 'start': fields[19]}
    start = subprocess.check_output(['ps', '-o', 'lstart=', '-p', str(pid)], text=True).strip()
    return {'group': os.getpgid(pid), 'session': os.getsid(pid), 'start': start}


def recover_session(output: Path) -> None:
    path = output / 'controller-session.json'
    if not path.exists():
        return
    if path.is_symlink():
        raise ValueError('controller session receipt must be a regular file')
    record = json.loads(path.read_text())
    pid = record['pid']
    if (type(pid) is not int or pid <= 1 or record['output'] != str(output.resolve())
            or record['identity']['group'] != pid or record['identity']['session'] != pid):
        raise ValueError('controller session ownership differs')
    try:
        current = process_identity(pid)
    except (ProcessLookupError, FileNotFoundError, subprocess.CalledProcessError):
        try:
            os.killpg(pid, 0)
        except ProcessLookupError:
            return
        # If the leader is gone, an inherited random marker authenticates a
        # surviving member of its Linux session before any group signal.
        proven = False
        if sys.platform == 'linux':
            for child in Path('/proc').glob('[0-9]*/stat'):
                try:
                    identity = process_identity(int(child.parent.name))
                    if identity['group'] == pid and identity['session'] == pid:
                        marker = b'CI_CHECK_SESSION_OWNER=' + record['owner'].encode() + b'\0'
                        proven |= marker in (child.parent / 'environ').read_bytes()
                except (OSError, ValueError):
                    continue
        if not proven:
            raise ValueError('cannot authenticate surviving controller session')
    else:
        if current != record['identity']:
            raise ValueError('recorded controller PID has been reused')
    stop_session(None, pid)


def sample_resources(output: Path) -> int:
    free = shutil.disk_usage(output).free
    with (output / 'host-resources.jsonl').open('a') as resources:
        resources.write(json.dumps({'time': time.time(), 'free_bytes': free}) + '\n')
    return free


def completed(output: Path) -> bool:
    summary = json.loads((output / 'local/execution.json').read_text())
    admission = json.loads((output / 'admission.json').read_text())
    expected = [row['ops_role'] for row in admission['validation_matrix'] if row['validation'] == 'yueops'] + ['join']
    return (admission.get('validation_only') is True and admission.get('mode') == 'sharded'
            and 'native' in expected and len(expected) == len(set(expected))
            and summary.get('complete') is True and summary.get('roles') == expected
            and set(summary.get('exit_codes', {})) == set(expected)
            and all(type(code) is int for code in summary['exit_codes'].values()))


def policy_revision() -> str:
    return subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'],
                                   text=True, timeout=15).strip()


def run(source: str, board: str, base: str, output: Path, *, timeout_seconds: int = EXECUTION_SECONDS) -> int:
    output.mkdir(parents=True, exist_ok=True)
    # Exclusive ownership prevents a duplicate invocation cleaning a live replay.
    try:
        with (output / '.hosted-owner').open('x') as handle:
            handle.write(str(os.getpid()) + '\n')
    except FileExistsError:
        print('hosted replay output is already owned', file=sys.stderr)
        return 2
    started = time.time()
    receipt = {'schema': 1, 'status': 'INFRASTRUCTURE_FAILED', 'complete': False,
               'source_revision': source, 'board_revision': board, 'migration_base': base,
               'started_at': started, 'timeout_seconds': timeout_seconds,
               'workflow_run_id': os.environ.get('GITHUB_RUN_ID'),
               'workflow_run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT')}
    code = 2
    process = None
    session_id = None
    try:
        if not all(re.fullmatch(r'[0-9a-f]{40}', value) for value in (source, board, base)):
            raise ValueError('hosted replay inputs must be exact commit SHAs')
        env = clean_environment(output, base)
        receipt['policy_revision'] = policy_revision()
        receipt['initial_free_bytes'] = shutil.disk_usage(output).free
        if receipt['initial_free_bytes'] < INITIAL_FREE:
            raise ValueError('insufficient disk: hosted replay requires 8 GiB free before execution')
        with (output / 'hosted.log').open('w') as log:
            owner = uuid.uuid4().hex
            command = ['bash', str(ROOT / 'scripts/ci-check.sh'), 'yueops', source,
                       '--local', '--board-ref', board, '--prepared', str(output / 'prepared.json')]
            # No source code starts until its recoverable session identity is
            # durable. If the controller dies early, pipe EOF exits this gate.
            process = subprocess.Popen(
                ['bash', '-c', 'read -r permit; [ "$permit" = proceed ] || exit 2; exec "$@"',
                 'ci-check-gate', *command], stdin=subprocess.PIPE,
                env=env | {'CI_CHECK_SESSION_OWNER': owner}, stdout=log,
                stderr=subprocess.STDOUT, start_new_session=True)
            session_id = process.pid
            receipt['controller_session_id'] = session_id
            session = {'pid': session_id, 'identity': process_identity(session_id),
                       'owner': owner, 'output': str(output.resolve())}
            temporary = output / 'controller-session.json.tmp'
            temporary.write_text(json.dumps(session) + '\n')
            temporary.replace(output / 'controller-session.json')
            if process.stdin is None:
                raise ValueError('source execution gate has no controller pipe')
            process.stdin.write(b'proceed\n')
            process.stdin.close()
            deadline = time.monotonic() + timeout_seconds
            while True:
                free = sample_resources(output)
                if free < ROLE_FREE:
                    raise ValueError('disk space budget exhausted during execution')
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError('execution time budget exhausted; full role coverage is unproven')
                try:
                    result = process.wait(timeout=min(5, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
        receipt['cli_exit_code'] = result
        receipt['complete'] = completed(output)
        if result == 0 and receipt['complete']:
            summary = json.loads((output / 'local/execution.json').read_text())
            if any(summary['exit_codes'].values()):
                raise ValueError('successful CLI contradicts failing role receipts')
        if receipt['complete'] and result in (0, 1):
            code = result
            receipt['status'] = 'VALIDATION_PASSED' if result == 0 else 'VALIDATION_FAILED'
        else:
            raise ValueError('CLI did not complete every admitted role and join')
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        receipt['problem'] = str(error)
    finally:
        if process is not None and session_id is not None:
            try:
                stop_session(process, session_id)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                receipt['session_cleanup_problem'] = str(error)
                receipt['status'] = 'INFRASTRUCTURE_FAILED'
                code = 2
        try:
            cleanup_containers(output)
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
            receipt['cleanup_problem'] = str(error)
            receipt['status'] = 'INFRASTRUCTURE_FAILED'
            code = 2
        receipt['elapsed_seconds'] = time.time() - started
        receipt['exit_code'] = code
        (output / 'hosted-result.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return code


def finalize(output: Path) -> int:
    """An independent always-step recovers evidence if the controller was killed."""
    output.mkdir(parents=True, exist_ok=True)
    path = output / 'hosted-result.json'
    value = (json.loads(path.read_text()) if path.exists() else
             {'schema': 1, 'status': 'INFRASTRUCTURE_FAILED', 'complete': False,
              'exit_code': 2, 'problem': 'controller did not produce a terminal receipt'})
    for cleanup in (recover_session, cleanup_containers):
        try:
            cleanup(output)
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
            value.update(status='INFRASTRUCTURE_FAILED', exit_code=2)
            value.setdefault('cleanup_problems', []).append(str(error))
    path.write_text(json.dumps(value, indent=2) + '\n')
    return 2 if value['status'] == 'INFRASTRUCTURE_FAILED' else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'board', 'base'):
        parser.add_argument('--' + name)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cleanup-only', action='store_true')
    args = parser.parse_args()
    if args.cleanup_only:
        return finalize(args.output.resolve())
    if not all((args.source, args.board, args.base)):
        parser.error('execution requires --source, --board and --base')
    return run(args.source, args.board, args.base, args.output.resolve())


if __name__ == '__main__':
    raise SystemExit(main())
