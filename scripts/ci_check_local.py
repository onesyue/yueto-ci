"""Run every admitted role in disposable instances of the workflow's image."""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import time
import json
import re
import subprocess
import sys
from pathlib import Path

from ci_check_failures import node_ids

ROOT = Path(__file__).resolve().parents[1]


def image_from_workflow() -> str:
    import yaml

    job = yaml.safe_load((ROOT / '.github/workflows/build.yml').read_text())['jobs']['validate']
    image = job['container']['image']
    digest = r"ghcr\.io/onesyue/yueops-ci-toolchain@sha256:[a-f0-9]{64}"
    if isinstance(image, str):
        if re.fullmatch(digest, image):
            return image
        match = re.fullmatch(
            r"\$\{\{ matrix.board_role != 'e2e' && '(" + digest + r")' \|\| '' \}\}", image)
        if match:
            return match[1]
    raise ValueError('workflow must declare one immutable validation toolchain image')



def execute_container(command: list[str], log: Path, receipt: Path) -> int:
    """Keep lifecycle calls separate; attaching before start can deadlock Desktop."""
    container = subprocess.check_output(command, text=True).strip()
    if not re.fullmatch(r'[a-f0-9]{64}', container):
        raise ValueError('Docker create returned no exact container identity')
    receipt.write_text(json.dumps({'container_id': container, 'command': command}, indent=2) + '\n')
    try:
        with log.open('w') as handle:
            try:
                subprocess.run(['docker', 'start', container], check=True, stdout=handle,
                               stderr=subprocess.STDOUT, timeout=120)
                status = subprocess.check_output(['docker', 'wait', container], text=True,
                                                 stderr=handle, timeout=7200).strip()
                return int(status)
            except subprocess.SubprocessError as error:
                handle.write(f'ci-check infrastructure failure: {error}\n')
                raise
            finally:
                subprocess.run(['docker', 'logs', container], stdout=handle,
                               stderr=subprocess.STDOUT, check=True, timeout=120)
    finally:
        # This exact ID was created by this call, and is retained in its receipt.
        subprocess.run(['docker', 'rm', '--force', container], stdout=subprocess.DEVNULL,
                       check=True, timeout=120)


def run(source: Path, board: Path, policy: Path, admission: Path, output: Path, base: str) -> int:
    value = json.loads(admission.read_text())
    if value.get('validation_only') is not True or value.get('mode') != 'sharded':
        raise ValueError('local replay requires the signed validation-only sharded plan')
    roles = [row['ops_role'] for row in value['validation_matrix'] if row['validation'] == 'yueops']
    if not roles or len(roles) != len(set(roles)) or 'native' not in roles:
        raise ValueError('missing or duplicate admitted role')
    if any(not re.fullmatch(r'[a-z0-9-]+', role) for role in roles):
        raise ValueError('invalid admitted role')
    image = image_from_workflow()
    available = subprocess.run(['docker', 'image', 'inspect', image], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, check=False)
    if available.returncode:
        subprocess.run(['docker', 'pull', '--platform', 'linux/amd64', image], check=True)
    output.mkdir(parents=True, exist_ok=True)
    evidence = output / 'evidence'
    evidence.mkdir()
    evidence.chmod(0o777)
    identity = value['identity']
    common = {
        'CI_CHECK_SOURCE': str(source), 'CI_CHECK_BOARD': str(board), 'CI_CHECK_POLICY': str(policy),
        'CI_CHECK_ADMISSION': str(admission), 'CI_CHECK_SOURCE_SHA': value['source_revision'],
        'CI_CHECK_BOARD_SHA': value['board_revision'], 'CI_CHECK_EVIDENCE': str(evidence),
        'CI_CHECK_ADMISSION_SHA': value['admission_sha256'], 'MIGRATION_BASE': base,
        'GITHUB_SHA': identity['policy_revision'], 'GITHUB_RUN_ID': identity['run_id'],
        'GITHUB_RUN_ATTEMPT': identity['run_attempt'], 'GITHUB_REPOSITORY': 'onesyue/yueto-ci',
        'RUNNER_OS': 'Linux', 'RUNNER_ARCH': 'X64', 'ImageVersion': 'yueops-ci-toolchain',
    }
    failed = False
    failures = []
    expected_roles = [*roles, 'join']
    statuses = {}
    owner = hashlib.sha256(str(output.resolve()).encode()).hexdigest()
    minimum_free = int(os.environ.get('CI_CHECK_MIN_FREE_BYTES', '0'))
    if minimum_free < 0:
        raise ValueError('minimum free disk space must not be negative')
    summary = output / 'execution.json'
    summary.write_text(json.dumps({'complete': False, 'roles': expected_roles, 'exit_codes': statuses}) + '\n')
    for role in expected_roles:
        free = shutil.disk_usage(output).free
        with (output / 'resources.jsonl').open('a') as handle:
            handle.write(json.dumps({'role': role, 'time': time.time(), 'free_bytes': free}) + '\n')
        if free < minimum_free:
            raise ValueError(f'infrastructure: free disk {free} below required {minimum_free} before {role}')
        job = output / role
        job.mkdir()
        job.chmod(0o777)
        env = common | {'OPS_ROLE': role, 'CI_CHECK_JOB': str(job),
                        'CI_CHECK_RESULT': 'failure' if failed else 'success'}
        command = ['docker', 'create', '--platform', 'linux/amd64',
                   '--privileged', '--user', 'runner', '--label', f'ci-check.owner={owner}',
                   '--cidfile', str(job / 'container.cid')]
        # The role has its own nested daemon. Never mount the shared host socket.
        # The same paths are visible to fixtures and their private Docker daemon.
        for path in (source, board, policy, admission):
            command += ['-v', f'{path}:{path}:ro']
        command += ['-v', f'{output}:{output}:rw']
        for key, val in env.items():
            command += ['-e', f'{key}={val}']
        command += [image, 'bash', str(policy / 'scripts/ci-check-container.sh')]
        print(f'ci-check: role {role}', file=sys.stderr, flush=True)
        log = job / 'role.log'
        status = execute_container(command, log, job / 'container.json')
        statuses[role] = status
        summary.write_text(json.dumps({'complete': False, 'roles': expected_roles, 'exit_codes': statuses}) + '\n')
        text = log.read_text(errors='replace')
        failures.extend(node_ids(text))
        if status:
            failed = True
            print(f'ci-check: {role} failed ({status}); {log}', file=sys.stderr)
            print('\n'.join(text.splitlines()[-12:]), file=sys.stderr)
    summary.write_text(json.dumps({'complete': True, 'roles': expected_roles, 'exit_codes': statuses}) + '\n')
    failures = list(dict.fromkeys(failures))
    (output / 'failures.txt').write_text(''.join(item + '\n' for item in failures))
    for item in failures:
        print(item)
    return 1 if failed or failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'board', 'policy', 'admission', 'output', 'base'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    try:
        return run(Path(args.source).resolve(), Path(args.board).resolve(), Path(args.policy).resolve(),
                   Path(args.admission).resolve(), Path(args.output).resolve(), args.base)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'ci-check: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
