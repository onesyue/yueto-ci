"""Local replay runs admitted roles, retains failures, and reaches the evidence join."""
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
SPEC = importlib.util.spec_from_file_location('ci_local', ROOT / 'scripts/ci_check_local.py')
assert SPEC is not None and SPEC.loader is not None
LOCAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LOCAL)


class LocalReplay(unittest.TestCase):
    def test_conditional_image_rejects_mutable_or_other_role_expressions(self):
        import yaml

        original = yaml.safe_load((ROOT / '.github/workflows/build.yml').read_text())
        image = original['jobs']['validate']['container']['image']
        for value in [image.replace("!= 'e2e'", "== 'e2e'"),
                      image.replace("!= 'e2e'", "!= 'quality'"),
                      "${{ inputs.image }}", "ghcr.io/onesyue/yueops-ci-toolchain:latest", ""]:
            original['jobs']['validate']['container']['image'] = value
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / '.github/workflows').mkdir(parents=True)
                (root / '.github/workflows/build.yml').write_text(yaml.safe_dump(original))
                with patch.object(LOCAL, 'ROOT', root), self.assertRaises(ValueError):
                    LOCAL.image_from_workflow()

    def test_existing_output_is_preserved_when_clone_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing = root / 'source'
            existing.mkdir()
            sentinel = existing / 'sentinel'
            sentinel.write_text('unrelated checkout')
            binpath = root / 'bin'
            binpath.mkdir()
            git = binpath / 'git'
            git.write_text("#!/bin/bash\n"
                           "if [ \"$1\" = clone ]; then for last in \"$@\"; do :; done; "
                           "mkdir -p \"$last\"; touch \"$last/partial\"; exit 23; fi\n"
                           "case \"${3:-}\" in status) exit 0;; rev-parse) printf '%040d\\n' 1;; *) exit 99;; esac\n")
            git.chmod(0o755)
            docker = binpath / 'docker'
            docker.write_text('#!/bin/sh\nexit 99\n')
            docker.chmod(0o755)
            env = os.environ | {'PATH': str(binpath) + os.pathsep + os.environ['PATH'],
                                'CI_CHECK_OUTPUT': str(root), 'CI_CHECK_MIGRATION_BASE': 'a' * 40,
                                'YUEOPS_CHECKOUT': str(root / 'fixture')}
            result = subprocess.run(['bash', str(ROOT / 'scripts/ci-check.sh'), 'yueops', 'b' * 40, '--local', '--board-ref', 'c' * 40],
                                    env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 23, result.stderr)
            self.assertEqual(sentinel.read_text(), 'unrelated checkout')
            self.assertEqual(list(root.glob('checkouts.*')), [])

    def test_local_object_cache_does_not_supply_default_branch_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote, seed, stale, dest = [root / name for name in ('yueops.git', 'seed', 'stale', 'dest')]
            env = os.environ | {'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1',
                                'GIT_AUTHOR_NAME': 'Fixture', 'GIT_AUTHOR_EMAIL': 'test@example.invalid',
                                'GIT_COMMITTER_NAME': 'Fixture', 'GIT_COMMITTER_EMAIL': 'test@example.invalid'}

            def git(*args):
                return subprocess.check_output(['git', *map(str, args)], env=env, text=True, stderr=subprocess.DEVNULL).strip()

            git('init', '--bare', '-b', 'master', remote)
            git('init', '-b', 'master', seed)
            (seed / 'file').write_text('first')
            git('-C', seed, 'add', 'file')
            git('-C', seed, '-c', 'commit.gpgsign=false', 'commit', '-qm', 'first')
            first = git('-C', seed, 'rev-parse', 'HEAD')
            git('-C', seed, 'push', remote, 'master')
            git('clone', remote, stale)
            (seed / 'file').write_text('second')
            git('-C', seed, '-c', 'commit.gpgsign=false', 'commit', '-am', 'second', '-q')
            latest = git('-C', seed, 'rev-parse', 'HEAD')
            git('-C', seed, 'push', remote, 'master')
            env |= {'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': f'url.{root.as_uri()}/.insteadOf',
                    'GIT_CONFIG_VALUE_0': 'https://github.com/onesyue/'}
            script = (ROOT / 'scripts/ci-check.sh').read_text()
            body = script.split('clone_at() {\n', 1)[1].split('\n}\n', 1)[0]
            command = 'set -euo pipefail\nclone_at() {\n' + body + '\n}\nclone_at \"$@\"'
            subprocess.run(['bash', '-c', command, '--', 'yueops', first, str(dest), str(stale)],
                           env=env, capture_output=True, text=True, check=True)
            self.assertEqual(git('-C', dest, 'rev-parse', 'HEAD'), first)
            self.assertEqual(git('-C', dest, 'rev-parse', 'origin/master'), latest)

    def test_container_start_failure_keeps_logs_and_removes_only_its_own_id(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            container = 'f' * 64
            calls = []

            def run(command, **kwargs):
                calls.append(command)
                if command[1] == 'start':
                    raise subprocess.TimeoutExpired(command, 120)
                if command[1] == 'logs':
                    kwargs['stdout'].write('daemon startup diagnostic\n')
                return subprocess.CompletedProcess(command, 0)

            with patch.object(LOCAL.subprocess, 'check_output', return_value=container), \
                    patch.object(LOCAL.subprocess, 'run', side_effect=run):
                with self.assertRaises(subprocess.TimeoutExpired):
                    LOCAL.execute_container(['docker', 'create', 'fixture'], root / 'log', root / 'receipt')
            self.assertEqual(calls[-1], ['docker', 'rm', '--force', container])
            self.assertIn('daemon startup diagnostic', (root / 'log').read_text())
            self.assertEqual(json.loads((root / 'receipt').read_text())['container_id'], container)

    def test_image_is_read_from_the_hosted_workflow(self):
        image = LOCAL.image_from_workflow()
        self.assertRegex(image, r'^ghcr.io/onesyue/yueops-ci-toolchain@sha256:[0-9a-f]{64}$')
        self.assertIn(image, (ROOT / '.github/workflows/build.yml').read_text())

    def test_every_shared_workflow_step_is_used_locally(self):
        workflow = (ROOT / '.github/workflows/build.yml').read_text()
        hosted = set(re.findall(r'\.ci-policy/scripts/ops-validation-([a-z-]+)\.sh', workflow))
        local = (ROOT / 'scripts/ci-check-container.sh').read_text()
        called = set(re.findall(r'^\s*run_step ([a-z-]+)', local, re.M))
        self.assertEqual(hosted, called)
        self.assertIn('cp -a --no-preserve=ownership', local)
        self.assertNotIn('export YUEOPS_REQUIRE_PRODUCER_CONTRACT', local)
        self.assertNotIn('-m pytest', local)
        self.assertIn('pytest-shards.py" join', local)

    def test_failed_role_does_not_hide_later_role_or_skip_join(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            admission = root / 'admission.json'
            admission.write_text(json.dumps({
                'validation_only': True, 'mode': 'sharded',
                'validation_matrix': [dict(validation='yueops', ops_role=role)
                                      for role in ['ordinary-000', 'ordinary-001', 'native']],
                'identity': dict(policy_revision='a' * 40, run_id='1', run_attempt='1'),
                'source_revision': 'b' * 40, 'board_revision': 'c' * 40,
                'admission_sha256': 'd' * 64,
            }))
            seen = []

            def command(args, log, receipt):
                env = dict(arg.split('=', 1) for arg in args if '=' in arg)
                role = env['OPS_ROLE']
                seen.append(role)
                self.assertEqual(args[-2], 'bash')
                self.assertTrue(args[-1].endswith('/scripts/ci-check-container.sh'))
                self.assertIn('--platform', args)
                self.assertIn('--privileged', args)
                self.assertFalse(any('docker.sock' in item for item in args))
                log.write_text('')
                if role == 'ordinary-000':
                    log.write_text('FAILED tests/test_a.py::test_red - AssertionError\n')
                    return 1
                if role == 'join':
                    self.assertEqual(env['CI_CHECK_RESULT'], 'failure')
                return 0

            with patch.object(LOCAL, 'execute_container', side_effect=command), \
                    patch.object(LOCAL.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)):
                status = LOCAL.run(root, root, root, admission, root / 'output', 'e' * 40)
            self.assertEqual(status, 1)
            self.assertEqual(seen, ['ordinary-000', 'ordinary-001', 'native', 'join'])
            summary = json.loads((root / 'output/execution.json').read_text())
            self.assertTrue(summary['complete'])
            self.assertEqual(summary['roles'], seen)
            self.assertEqual(summary['exit_codes']['ordinary-000'], 1)
            self.assertEqual((root / 'output/failures.txt').read_text(), 'tests/test_a.py::test_red\n')


if __name__ == '__main__':
    unittest.main()
