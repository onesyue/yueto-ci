"""Credential-free root validation, using the root repository's native gate.

The signed source parser runs in an isolated networkless container. Only its
repository/revision data crosses back into trusted local snapshot creation.
Private source acquisition and local/hosted dispatch integration are separate.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from ci_check_local import execute_container, image_from_workflow
from source_evidence import verify_signed_commit

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = {'yueops', 'yueboard', 'yue-node'}
SHA = re.compile(r'[a-f0-9]{40}')


def references(value: object) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != COMPONENTS:
        raise ValueError('native desired must resolve exactly Ops, Board and Node')
    if any(not isinstance(v, str) or not SHA.fullmatch(v) for v in value.values()):
        raise ValueError('native desired revisions must be full commit SHAs')
    return value


def read_json(path: Path) -> object:
    if path.is_symlink() or not path.is_file():
        raise ValueError('missing or symbolic result: ' + str(path))
    return json.loads(path.read_text())


def isolated_command(workspace: Path, policy: Path, output: Path, mode: str) -> list[str]:
    return ['docker', 'create', '--platform', 'linux/amd64', '--network', 'none',
            '--user', 'runner', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--mount', f'type=bind,src={workspace},dst=/inputs,readonly',
            '--mount', f'type=bind,src={policy},dst=/policy,readonly',
            '--mount', f'type=bind,src={output},dst=/output',
            image_from_workflow(), 'python3', '-I', '/policy/scripts/ci_check_root_worker.py', mode]


def snapshot(source: Path, repo: str, revision: str, destination: Path) -> None:
    """Copy Git objects only, never ignored working files or credential config."""
    if repo not in COMPONENTS | {'yueto', 'yueto-ci'} or not SHA.fullmatch(revision):
        raise ValueError('unapproved snapshot input')
    env = {'PATH': os.environ.get('PATH', os.defpath), 'HOME': '/nonexistent',
           'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1',
           'GIT_TERMINAL_PROMPT': '0'}
    command = ['git', '--no-replace-objects', '-c', 'init.templateDir=']
    subprocess.run([*command, 'clone', '--quiet', '--no-hardlinks', '--dissociate',
                    '--no-checkout', str(source), str(destination)], env=env, check=True)
    subprocess.run([*command, '-C', str(destination), 'remote', 'set-url', 'origin',
                    f'https://github.com/onesyue/{repo}.git'], env=env, check=True)
    subprocess.run([*command, '-C', str(destination), 'checkout', '--quiet', '--detach', revision],
                   env=env, check=True)
    # The source clone is an object cache; never contact its configured remote.
    if subprocess.check_output([*command, '-C', str(destination), 'rev-parse', 'HEAD'], env=env, text=True).strip() != revision:
        raise ValueError('snapshot revision differs')
    # Docker's non-root user may have a different UID and the caller may use
    # umask 077. Only these owned object-only snapshots become world-readable.
    for path in (destination, *destination.rglob('*')):
        if path.is_symlink():
            continue
        if path.is_dir():
            path.chmod(0o755)
        else:
            mode = path.stat().st_mode
            path.chmod(mode | 0o444 | (0o111 if mode & 0o111 else 0))


def run(source: str, workspace: Path, output: Path) -> int:
    """Run against already acquired repositories; this entry has no fetch authority.

    Private repository acquisition/App scope is owned by the caller. Both local
    and hosted integration must call this same executor after auth cleanup.
    """
    if not SHA.fullmatch(source):
        raise ValueError('exact root source SHA required')
    if any(os.environ.get(key) for key in ('GH_TOKEN', 'GITHUB_TOKEN', 'GH_ENTERPRISE_TOKEN',
                                          'GITHUB_ENTERPRISE_TOKEN', 'GIT_ASKPASS', 'SSH_AUTH_SOCK')):
        raise ValueError('execution must follow credential cleanup')
    output.mkdir(parents=True, exist_ok=False)
    policy = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    if subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain', '--untracked-files=no'], text=True).strip():
        raise ValueError('commit policy edits before validation')
    identity = {'source': source, 'policy': policy}
    (output / 'result.json').write_text(json.dumps(identity | {'complete': False}) + '\n')
    with tempfile.TemporaryDirectory(prefix='root-validation-inputs-') as directory:
        snapshots = Path(directory)
        snapshots.chmod(0o755)
        snapshot(workspace, 'yueto', source, snapshots / 'yueto')
        # Central owner policy authenticates candidate code before its parser runs.
        verify_signed_commit(snapshots / 'yueto', source)
        snapshot(ROOT, 'yueto-ci', policy, snapshots / 'yueto-ci')
        parser = output / 'parser'
        parser.mkdir(mode=0o777)
        parser.chmod(0o777)
        code = execute_container(isolated_command(snapshots, snapshots / 'yueto-ci', parser, 'parse'),
                                 parser / 'parser.log', parser / 'container.json')
        if code:
            raise ValueError(f'isolated native desired parser failed ({code})')
        refs = references(read_json(parser / 'references.json'))
        for repo, revision in sorted(refs.items()):
            snapshot(workspace / repo, repo, revision, snapshots / repo)
        refs['yueto-ci'] = policy
        (snapshots / 'context.json').write_text(json.dumps(identity | {'refs': refs}) + '\n')
        (output / 'context.json').write_text(json.dumps(identity | {'refs': refs}) + '\n')
        job = output / 'execution'
        job.mkdir(mode=0o777)
        job.chmod(0o777)
        code = execute_container(isolated_command(snapshots, snapshots / 'yueto-ci', job, 'test'),
                                 job / 'execution.log', job / 'container.json')
        result = read_json(job / 'result.json')
        if (not isinstance(result, dict) or type(result.get('exit_code')) is not int
                or result.get('exit_code') != code or type(result.get('complete')) is not bool):
            raise ValueError('missing or inconsistent executor receipt')
        (output / 'result.json').write_text(json.dumps(result | identity) + '\n')
        print((job / 'execution.log').read_text(errors='replace'))
        return code if code else (0 if result['complete'] else 2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, type=Path)
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        return run(args.source, args.workspace.resolve(), args.output.resolve())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'root validation incomplete: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
