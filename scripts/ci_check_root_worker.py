"""Container-side root native parser/executor; no credential or network mounts."""
from __future__ import annotations

import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


def environment() -> dict[str, str]:
    return {'PATH': os.defpath + ':/usr/local/bin:/usr/local/go/bin', 'HOME': '/tmp/root-home',
            'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'TZ': 'UTC',
            'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
            'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'}


def parse(inputs: Path, policy: Path, output: Path) -> None:
    root = inputs / 'yueto'
    os.environ.clear()
    os.environ.update(environment() | {'YUETO_ROOT': str(root),
        'YUETO_RELEASE_SIGNER_KEYRING': str(policy / 'policy/yueops-owner.gpg')})
    native = runpy.run_path(str(root / 'scripts/release-yaml.py'))
    record, snapshot = native['verified_desired']()
    refs = {repo: native['desired_revision'](record, repo, root)
            for repo in ('yueops', 'yueboard', 'yue-node')}
    native['assert_desired_unchanged'](snapshot)
    (output / 'references.json').write_text(json.dumps(refs) + '\n')


def junit_complete(path: Path) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    root = ET.parse(path).getroot()
    cases = list(root.iter('testcase'))
    # Missing dependencies often surface as collection skips; neither skips nor
    # xfail are complete coverage. Native nonzero exits remain authoritative.
    return bool(cases) and not any(case.find('skipped') is not None for case in cases)


def execute(inputs: Path, output: Path) -> int:
    result: dict = {'complete': False, 'exit_code': 2, 'phases': {}}
    try:
        env = environment()
        Path(env['HOME']).mkdir(exist_ok=True)
        for tool in ('git', 'bash', 'shellcheck'):
            if not shutil.which(tool, path=env['PATH']):
                raise ValueError('missing validation tool: ' + tool)
        subprocess.run([sys.executable, '-I', '-c', 'import pytest'], env=env, check=True)
        context = json.loads((inputs / 'context.json').read_text())
        with tempfile.TemporaryDirectory(prefix='root-validation-') as directory:
            workspace = Path(directory)
            # Only disposable copies are writable: the native gate creates its
            # own detached worktrees and never mutates prepared checkouts.
            for repo in ('yueto', *context['refs']):
                shutil.copytree(inputs / repo, workspace / repo, symlinks=True)
            root = workspace / 'yueto'
            paths = subprocess.check_output(['git', '-C', str(root), 'ls-files', '-z', '*.sh'], env=env).split(b'\0')
            shells = [os.fsdecode(path) for path in paths if path]
            if not shells:
                raise ValueError('empty tracked shell collection')
            for phase, command in (('bash-n', ['bash', '-n', '--']), ('shellcheck', ['shellcheck', '--'])):
                for path in shells:
                    status = subprocess.run([*command, path], cwd=root, env=env).returncode
                    if status:
                        result['phases'][phase] = status
                        result['exit_code'] = status
                        return status
                result['phases'][phase] = 0
            command = ['bash', 'scripts/gate-root-selftests.sh', '--ops-repo', str(workspace / 'yueops'),
                       '--ops-sha', context['refs']['yueops'], '--python', sys.executable,
                       '--workspace', str(workspace), '--junit', str(output / 'junit.xml')]
            for repo, revision in sorted(context['refs'].items()):
                command += ['--with', f'{repo}={revision}']
            status = subprocess.run(command, cwd=root, env=env).returncode
            result['phases']['native-selftests'] = status
            result['validation_exit_code'] = status
            complete = junit_complete(output / 'junit.xml')
            result['complete'] = complete and status in (0, 1)
            result['exit_code'] = status if result['complete'] else 2
            return result['exit_code']
    except (OSError, ValueError, subprocess.SubprocessError, ET.ParseError) as error:
        print(f'root validation incomplete: {error}', file=sys.stderr)
        return 2
    finally:
        (output / 'result.json').write_text(json.dumps(result) + '\n')


if __name__ == '__main__':
    if sys.argv[1:] == ['parse']:
        parse(Path('/inputs'), Path('/policy'), Path('/output'))
    elif sys.argv[1:] == ['test']:
        raise SystemExit(execute(Path('/inputs'), Path('/output')))
    else:
        raise SystemExit('expected parse or test')
