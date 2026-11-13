"""Execute Node prerequisites with disposable tools; no daemon or private access."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/node-validation-preflight.sh'
def required_bash() -> str:
    executable = shutil.which('bash')
    assert executable, 'bash is required for the real shell controls'
    return executable


BASH = required_bash()


class NodePreflight(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.source = self.root / 'node source'
        self.policy = self.root / 'policy'
        self.board = self.root / 'canonical board'
        self.bin = self.root / 'bin'
        for path in (self.source, self.policy / 'scripts', self.board, self.bin):
            path.mkdir(parents=True)
        (self.source / 'go.mod').write_text('module fixture\n')
        (self.policy / 'native-node-contract.json').write_text('{}')
        self.log = self.root / 'calls'
        program = '''import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
with open(os.environ['CALL_LOG'], 'a') as f:
 f.write(json.dumps({'name': name, 'args': sys.argv[1:], 'cwd': os.getcwd(), 'tz': os.getenv('TZ')})+'\\n')
if os.getenv('FAIL_TOOL') == name: sys.exit(23)
'''
        stub = self.bin / 'stub'
        stub.write_text('#!' + sys.executable + '\n' + program)
        stub.chmod(0o755)
        for tool in ('bash', 'git', 'base64', 'docker', 'gcc', 'go', 'gpg', 'jq', 'make'):
            (self.bin / tool).symlink_to(stub)
        (self.policy / 'scripts/validate-native-node-contract.py').write_text(program)
        self.env = {'PATH': str(self.bin), 'HOME': str(self.root), 'YUE_CI_PYTHON': sys.executable,
                    'CALL_LOG': str(self.log), 'TZ': 'Asia/Singapore'}

    def execute(self, phase, **extra):
        self.log.unlink(missing_ok=True)
        result = subprocess.run([BASH, str(SCRIPT), phase, str(self.source), str(self.policy), str(self.board)],
                                env=self.env | extra, text=True, capture_output=True)
        rows = [json.loads(s) for s in self.log.read_text().splitlines()] if self.log.exists() else []
        return result, rows

    def test_dependencies_check_every_tool_and_daemon_failure(self):
        result, rows = self.execute('dependencies')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(rows, [{'name': 'docker', 'args': ['info'], 'cwd': str(self.source), 'tz': 'UTC'}])
        for tool in ('bash', 'git', 'base64', 'docker', 'gcc', 'go', 'gpg', 'jq', 'make'):
            with self.subTest(tool=tool):
                path = self.bin / tool
                target = path.readlink()
                path.unlink()
                try:
                    result, rows = self.execute('dependencies')
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('missing required yue-node tool: ' + tool, result.stderr)
                    self.assertEqual(rows, [])
                finally:
                    path.symlink_to(target)
        result, _ = self.execute('dependencies', FAIL_TOOL='docker')
        self.assertEqual(result.returncode, 23)

    def test_contract_uses_exact_separate_board_and_propagates_failure(self):
        result, rows = self.execute('contract')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(rows, [{'name': 'validate-native-node-contract.py',
            'args': ['--kind', 'yue-node', '--source', '.', '--yueboard-contract-source', str(self.board)],
            'cwd': str(self.source), 'tz': 'UTC'}])
        result, _ = self.execute('contract', FAIL_TOOL='validate-native-node-contract.py')
        self.assertEqual(result.returncode, 23)

    def test_credentials_and_malformed_inputs_fail_before_execution(self):
        for phase in ('dependencies', 'contract'):
            for key in ('GH_TOKEN', 'GITHUB_TOKEN', 'GH_ENTERPRISE_TOKEN', 'GITHUB_ENTERPRISE_TOKEN',
                        'YUETO_FORK_READ_TOKEN', 'GIT_CONFIG_COUNT', 'GIT_CONFIG_GLOBAL', 'GIT_CONFIG_VALUE_0'):
                with self.subTest(phase=phase, key=key):
                    result, rows = self.execute(phase, **{key: 'fixture-secret'})
                    self.assertEqual(result.returncode, 2)
                    self.assertNotIn('fixture-secret', result.stdout + result.stderr)
                    self.assertEqual(rows, [])
            result, rows = self.execute(phase, YUE_CI_PYTHON='/nonexistent')
            self.assertEqual(result.returncode, 2)
            self.assertEqual(rows, [])
        result, rows = self.execute('unknown')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(rows, [])
        for path in (self.source / 'go.mod', self.policy / 'native-node-contract.json'):
            text = path.read_text()
            path.unlink()
            try:
                result, rows = self.execute('contract')
                self.assertEqual(result.returncode, 2)
                self.assertEqual(rows, [])
            finally:
                path.write_text(text)
        self.board.rmdir()
        result, rows = self.execute('contract')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(rows, [])

    def test_hosted_order_keeps_cache_and_fork_gate_separate(self):
        steps = yaml.safe_load((ROOT / '.github/workflows/build.yml').read_text())['jobs']['validate']['steps']
        names = [step.get('name') for step in steps]
        selected = {step.get('name'): step for step in steps}
        order = ['Preflight validation dependencies', 'Plan trusted Go caches',
                 'Restore and refresh Go compiler cache', 'Keep Go test execution independent of compiler cache',
                 'Validate native-node cross-repository contract', 'Verify yue-node signed fork tags', 'Validate yue-node']
        self.assertEqual([names.index(name) for name in order], sorted(names.index(name) for name in order))
        self.assertEqual(selected[order[3]]['run'], 'go clean -testcache')
        self.assertIn('node-validation-preflight.sh dependencies', selected[order[0]]['run'])
        self.assertIn('node-validation-preflight.sh contract', selected[order[4]]['run'])
        self.assertIn('--yueboard-contract-source .ci-yueboard', selected[order[4]]['run'])
        self.assertIn('make verify-fork-tags', selected[order[5]]['run'])
        self.assertIn('YUETO_FORK_READ_TOKEN', selected[order[5]]['env'])
        self.assertNotIn('YUETO_FORK_READ_TOKEN', selected[order[6]]['env'])
        self.assertNotIn('verify-fork-tags', selected[order[6]]['run'])
