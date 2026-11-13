"""Board-only local adapter over the native planner and shared role executors."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import subprocess
import sys

from ci_check_local import execute_container, image_from_workflow
from ci_check_failures import failure_ids

STEPS = {
    'postgres': 'Validate YueBoard PostgreSQL integration',
    'migration': 'Validate YueBoard PostgreSQL module and migration integration',
    'clean': 'Validate YueBoard clean PostgreSQL lifecycle',
    'e2e': 'Validate YueBoard end-to-end suite',
}


def planner_environment() -> dict:
    # Preparation may use clone credentials; no host planner inherits them.
    return {key: os.environ[key] for key in ('PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR') if key in os.environ} | {
        'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1', 'TZ': 'UTC'}


def git(path: Path, *args: str) -> str:
    return subprocess.check_output(['git', '--no-replace-objects', '-C', str(path), *args], text=True, env=planner_environment()).strip()


def checkout(path: Path, repo: str, sha: str) -> None:
    if not re.fullmatch(r'[a-f0-9]{40}', sha):
        raise ValueError('exact checkout revision required')
    if path.is_symlink() or not (path / '.git').is_dir() or (path / '.git').is_symlink():
        raise ValueError('independent checkout required')
    if git(path, 'rev-parse', 'HEAD') != sha or git(path, 'status', '--porcelain'):
        raise ValueError('checkout identity or cleanliness differs')
    if git(path, 'config', '--local', '--get', 'remote.origin.url') != f'https://github.com/onesyue/{repo}.git':
        raise ValueError('checkout origin differs')
    git(path, 'rev-parse', '--verify', 'refs/remotes/origin/master^{commit}')
    keys = git(path, 'config', '--local', '--name-only', '--list').splitlines()
    if any(k.lower().startswith(('credential.', 'include.', 'includeif.')) or k.lower().endswith('.extraheader') for k in keys):
        raise ValueError('checkout contains credential configuration')


def workflow_contract(policy: Path) -> dict:
    # Metadata only: never evaluate workflow expressions or execute a run block.
    import yaml
    job = yaml.safe_load((policy / '.github/workflows/build.yml').read_text())['jobs']['validate']
    steps = job['steps']

    def step(name: str) -> dict:
        selected = [s for s in steps if s.get('name') == name]
        if len(selected) != 1:
            raise ValueError('workflow step missing or duplicated: ' + name)
        return selected[0]

    def env_value(value: str) -> str:
        if not isinstance(value, str):
            raise ValueError('workflow environment must be strings')
        if value == '${{ github.workspace }}/test/fixtures':
            return value
        if '${{' not in value:
            return value
        match = re.fullmatch(r"\$\{\{ github.event_name == 'workflow_dispatch' && github.event.inputs.runner == 'yue-local-release' && '([^']+)' \|\| '([^']+)' \}\}", value)
        if not match or match[1] != match[2] or not match[1].startswith('postgres://postgres:ci@postgres:5432/'):
            raise ValueError('unsupported workflow environment expression')
        return match[1].replace('@postgres:5432/', '@127.0.0.1:5432/', 1)

    service = job['services']['postgres']
    if not re.fullmatch(r'postgres:18@sha256:[a-f0-9]{64}', service['image']):
        raise ValueError('immutable PostgreSQL 18 service required')
    if service['env'] != {'POSTGRES_PASSWORD': 'ci', 'POSTGRES_DB': 'yueboard_test'}:
        raise ValueError('unexpected disposable service identity')
    health = shlex.split(service['options'])
    if len(health) != 8 or health[::2] != ['--health-cmd', '--health-interval', '--health-timeout', '--health-retries'] or health[1] != 'pg_isready -U postgres' or any(not re.fullmatch(r'[1-9][0-9]*s', v) for v in (health[3], health[5])) or not re.fullmatch(r'[1-9][0-9]*', health[7]):
        raise ValueError('unsupported PostgreSQL health contract')
    environments = {}
    for role, name in STEPS.items():
        raw = step(name)['env']
        if any(not re.fullmatch(r'(?:YUEBOARD_[A-Z0-9_]+|CLEAN_PG_DSN)', key) for key in raw):
            raise ValueError('unexpected workflow phase environment key')
        environments[role] = {k: env_value(v) for k, v in raw.items()}
    go = step('Set up YueBoard Go')['with']['go-version']
    node = step('Set up Node')['with']['node-version']
    buf = step('Set up Buf for YueBoard protocol compatibility')['with']
    if not re.fullmatch(r'\d+\.\d+\.\d+', go) or not re.fullmatch(r'\d+', node):
        raise ValueError('unsupported compiler version contract')
    if not re.fullmatch(r'\d+\.\d+\.\d+', buf['version']) or not re.fullmatch(r'[a-f0-9]{64}', buf['checksum']):
        raise ValueError('unsupported Buf identity')
    return {'postgres_image': service['image'], 'postgres_health': health, 'environments': environments,
            'go': go, 'node': node, 'buf': buf['version'], 'buf_sha256': buf['checksum']}


def plan(policy: Path, source_sha: str, output: Path) -> list[str]:
    native = subprocess.check_output(['bash', str(policy / 'scripts/plan-build-targets.sh'), 'yueboard', source_sha], text=True, env=planner_environment())
    pin = json.loads((policy / 'native-node-contract.json').read_text())['yueboard_contract_pin']
    authorized = subprocess.check_output(['bash', str(policy / 'scripts/authorize-yueboard-build-plan.sh'), pin, source_sha, 'false'], input=native, text=True, env=planner_environment())
    value = json.loads(authorized)
    rows = value['validation_matrix']
    roles = [row['board_role'] for row in rows]
    if len(roles) != 7 or len(set(roles)) != 7 or any(
            row['repo'] != 'onesyue/yueboard' or row['validation'] != 'yueboard' or row['ref'] != source_sha
            or not re.fullmatch(r'[a-z0-9]+', row['board_role']) for row in rows):
        raise ValueError('native Board role matrix identity differs')
    # Even an exact reviewed pin is never build-authorized by this CLI.
    value['matrix'] = []
    value['has_builds'] = False
    (output / 'targets.json').write_text(json.dumps(value, indent=2) + '\n')
    return roles


def run(source: Path, policy: Path, source_sha: str, policy_sha: str, output: Path) -> int:
    checkout(source, 'yueboard', source_sha)
    checkout(policy, 'yueto-ci', policy_sha)
    output.mkdir(parents=True, exist_ok=True)
    roles = plan(policy, source_sha, output)
    contract = workflow_contract(policy)
    image = image_from_workflow()
    summary = output / 'execution.json'
    statuses: dict[str, int] = {}
    summary.write_text(json.dumps({'complete': False, 'roles': roles, 'exit_codes': statuses}) + '\n')
    if subprocess.run(['docker', 'image', 'inspect', image], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        subprocess.run(['docker', 'pull', '--platform', 'linux/amd64', image], check=True)
    owner = hashlib.sha256(str(output.resolve()).encode()).hexdigest()
    failures = []
    outcomes = {}
    minimum = int(os.environ.get('CI_CHECK_MIN_FREE_BYTES', '0'))
    if minimum < 0:
        raise ValueError('negative free space threshold')
    for role in roles:
        if shutil.disk_usage(output).free < minimum:
            raise ValueError('infrastructure: insufficient free space before ' + role)
        job = output / role
        job.mkdir()
        job.chmod(0o777)
        (job / 'contract.json').write_text(json.dumps(contract))
        env = {'CI_CHECK_SOURCE': str(source), 'CI_CHECK_POLICY': str(policy), 'CI_CHECK_JOB': str(job),
               'CI_CHECK_SOURCE_SHA': source_sha, 'CI_CHECK_POLICY_SHA': policy_sha, 'BOARD_ROLE': role}
        command = ['docker', 'create', '--platform', 'linux/amd64', '--privileged', '--user', 'runner',
                   '--label', f'ci-check.owner={owner}', '--cidfile', str(job / 'container.cid')]
        for path in (source, policy):
            command += ['-v', f'{path}:{path}:ro']
        command += ['-v', f'{job}:{job}:rw']
        for key, value in env.items():
            command += ['-e', f'{key}={value}']
        command += [image, 'bash', str(policy / 'scripts/ci-check-board-container.sh')]
        log = job / 'role.log'
        statuses[role] = execute_container(command, log, job / 'container.json')
        if not log.is_file() or not log.stat().st_size:
            raise ValueError('role log missing or empty: ' + role)
        result = json.loads((job / 'role-result.json').read_text())
        expected = {'role': role, 'source': source_sha, 'policy': policy_sha}
        if any(result.get(k) != v for k, v in expected.items()) or result.get('exit_code') != statuses[role] or type(result.get('complete')) is not bool:
            raise ValueError('role lifecycle receipt differs')
        outcomes[role] = result
        failures.extend(failure_ids(log.read_text(errors='replace'), 'yueboard'))
        summary.write_text(json.dumps({'complete': False, 'roles': roles, 'exit_codes': statuses}) + '\n')
    complete = len(outcomes) == len(roles) and all(row['complete'] for row in outcomes.values())
    summary.write_text(json.dumps({'complete': complete, 'roles': roles, 'exit_codes': statuses, 'outcomes': outcomes}) + '\n')
    unique_failures = list(dict.fromkeys(failures))
    (output / 'failures.txt').write_text(''.join(s + '\n' for s in unique_failures))
    for diagnostic in unique_failures:
        print(diagnostic)
    return 2 if not complete else int(any(statuses.values()) or bool(failures))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'policy', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('source-sha', 'policy-sha'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    try:
        return run(args.source.resolve(), args.policy.resolve(), args.source_sha, args.policy_sha, args.output.resolve())
    except (OSError, ValueError, KeyError, ImportError, subprocess.SubprocessError) as error:
        print(f'ci-check: Board infrastructure failure: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
