"""Run shared Ops entrypoints with stale host paths in their environment."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RuntimeCheckoutPaths(unittest.TestCase):
    def test_consumers_receive_paths_in_the_executing_namespace(self):
        for role in ('selection', 'backend', 'notices'):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp).resolve() / 'container checkout'
                policy = source / '.ci-policy'
                (policy / 'scripts').mkdir(parents=True)
                (source / '.ci-yueboard/.git').mkdir(parents=True)
                (source / '.venv/bin').mkdir(parents=True)
                (source / 'tests').mkdir()
                (source / 'tests/test_yueboard_notices_contract_20261028.py').touch()
                script = policy / 'scripts' / f'ops-validation-{role}.sh'
                shutil.copyfile(ROOT / 'scripts' / script.name, script)
                # Stop at the first external consumer, before dependencies or network.
                consumer = source / '.venv/bin' / ('mktemp' if role == 'backend' else 'python')
                consumer.write_text('#!/bin/sh\nprintf "%s\\n%s\\n" "$YUEBOARD_REPO_PATH" "$YUETO_CI_REPO_PATH" > "$RECEIPT"\nexit 79\n')
                consumer.chmod(0o755)
                receipt = Path(tmp) / 'paths.txt'
                env = os.environ | {
                    'PATH': str(consumer.parent) + os.pathsep + os.environ['PATH'],
                    'YUEBOARD_REPO_PATH': '/host-only/source/.ci-yueboard',
                    'YUETO_CI_REPO_PATH': '/host-only/source/.ci-policy',
                    'GITHUB_WORKSPACE': '/host-only/source',
                    'RUNNER_TEMP': tmp, 'OPS_ROLE': role, 'RECEIPT': str(receipt),
                }
                result = subprocess.run(['bash', str(script)], cwd=source, env=env,
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 79, result.stderr)
                self.assertEqual(receipt.read_text().splitlines(), [
                    str(source / '.ci-yueboard'), str(policy)])


if __name__ == '__main__':
    unittest.main()
