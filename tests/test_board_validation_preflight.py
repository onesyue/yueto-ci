"""Real Board prerequisite shell: no source validation, network or Docker daemon."""
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
SCRIPT = ROOT / 'scripts/board-validation-preflight.sh'
def required_bash() -> str:
    executable = shutil.which('bash')
    assert executable
    return executable


BASH = required_bash()


class BoardPreflight(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.source = self.root / 'source with spaces'
        self.policy = self.root / 'policy with spaces'
        self.bin = self.root / 'bin'
        for path in (self.source, self.policy / 'scripts', self.bin):
            path.mkdir(parents=True)
        (self.source / 'go.mod').write_text('module fixture\n')
        subprocess.run(['git', 'init', '-q', str(self.source)], check=True)
        subprocess.run(['git', '-C', str(self.source), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(self.source), '-c', 'user.name=fixture', '-c',
                        'user.email=fixture@example.invalid', '-c', 'commit.gpgsign=false',
                        'commit', '-qm', 'fixture'], check=True)
        self.sha = subprocess.check_output(['git', '-C', str(self.source), 'rev-parse', 'HEAD'], text=True).strip()
        self.pin = self.policy / 'native-node-contract.json'
        self.pin.write_text(json.dumps({'yueboard_contract_pin': self.sha}))
        shutil.copy(ROOT / 'scripts/authorize-yueboard-promotion.sh', self.policy / 'scripts')
        self.log = self.root / 'calls'
        self.env = dict(os.environ, PATH=str(self.bin), YUE_CI_PYTHON=sys.executable,
                        CALL_LOG=str(self.log), PROMOTE='false', TZ='Asia/Singapore')
        for key in ('GH_TOKEN', 'GITHUB_TOKEN', 'GH_ENTERPRISE_TOKEN', 'GITHUB_ENTERPRISE_TOKEN'):
            self.env.pop(key, None)
        stub = self.bin / 'stub'
        stub.write_text('#!' + sys.executable + '\n' + '''import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
with open(os.environ['CALL_LOG'], 'a') as f:
 f.write(json.dumps({'name': name, 'args': sys.argv[1:], 'cwd': os.getcwd(), 'tz': os.getenv('TZ')}) + '\\n')
if os.getenv('FAIL_TOOL') == name: sys.exit(23)
''')
        stub.chmod(0o755)
        for tool in ('buf', 'corepack', 'docker', 'gcc', 'go', 'make', 'node', 'psql'):
            (self.bin / tool).symlink_to(stub)
        for tool in ('bash', 'git', 'jq'):
            actual = shutil.which(tool)
            assert actual
            (self.bin / tool).symlink_to(actual)
        validator = self.policy / 'scripts/validate-native-node-contract.py'
        validator.write_text(stub.read_text().split('\n', 1)[1])

    def execute(self, phase, **extra):
        self.log.unlink(missing_ok=True)
        result = subprocess.run([BASH, str(SCRIPT), phase, str(self.source), str(self.policy)],
                                env=self.env | extra, capture_output=True, text=True)
        rows = [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
        return result, rows

    def test_dependencies_use_existing_tool_inventory_and_docker(self):
        result, rows = self.execute('dependencies')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(rows, [{'name': 'docker', 'args': ['info'], 'cwd': str(self.source), 'tz': 'UTC'}])
        for tool in ('bash', 'git', 'buf', 'corepack', 'docker', 'gcc', 'go', 'make', 'node', 'psql'):
            path = self.bin / tool
            target = path.readlink()
            path.unlink()
            try:
                result, rows = self.execute('dependencies')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('missing required yueboard tool: ' + tool, result.stderr)
                self.assertEqual(rows, [])
            finally:
                path.symlink_to(target)
        result, rows = self.execute('dependencies', FAIL_TOOL='docker')
        self.assertEqual(result.returncode, 23)
        self.assertEqual(len(rows), 1)

    def test_contract_clears_cache_then_preserves_native_arguments_and_intent(self):
        for promote, matching in (('false', True), ('false', False), ('true', True)):
            self.pin.write_text(json.dumps({'yueboard_contract_pin': self.sha if matching else 'a'*40}))
            result, rows = self.execute('contract', PROMOTE=promote)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([row['name'] for row in rows], ['go', 'validate-native-node-contract.py'])
            self.assertEqual(rows[0]['args'], ['clean', '-testcache'])
            self.assertEqual(rows[1]['args'], ['--kind', 'yueboard', '--source', '.'])
            self.assertTrue(all(row['cwd'] == str(self.source) and row['tz'] == 'UTC' for row in rows))

    def test_contract_failures_stop_later_validation(self):
        for failing in ('go', 'validate-native-node-contract.py'):
            result, rows = self.execute('contract', FAIL_TOOL=failing)
            self.assertEqual(result.returncode, 23)
            self.assertEqual(len(rows), 1 if failing == 'go' else 2)
        self.pin.write_text(json.dumps({'yueboard_contract_pin': 'a'*40}))
        result, rows = self.execute('contract', PROMOTE='true')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('refusing YueBoard promotion', result.stderr)
        self.assertEqual([r['name'] for r in rows], ['go'])
        self.pin.write_text(json.dumps({'yueboard_contract_pin': 'not-a-sha'}))
        result, rows = self.execute('contract')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual([r['name'] for r in rows], ['go'])
        for value in ('', 'invalid'):
            result, rows = self.execute('contract', PROMOTE=value)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(rows, [])

    def test_bad_inputs_and_credentials_stop_before_commands(self):
        for phase in ('dependencies', 'contract'):
            result, rows = self.execute(phase, YUE_CI_PYTHON='')
            self.assertEqual(result.returncode, 2)
            self.assertEqual(rows, [])
            for key in ('GH_TOKEN', 'GITHUB_TOKEN', 'GH_ENTERPRISE_TOKEN', 'GITHUB_ENTERPRISE_TOKEN'):
                result, rows = self.execute(phase, **{key: 'private-token-value'})
                self.assertEqual(result.returncode, 2)
                self.assertEqual(rows, [])
                self.assertNotIn('private-token-value', result.stdout + result.stderr)
        result, rows = self.execute('unknown')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(rows, [])
        for index in (1, 2):
            args = ['dependencies', str(self.source), str(self.policy)]
            args[index] = str(self.root / 'missing')
            result = subprocess.run([BASH, str(SCRIPT), *args], env=self.env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)

    def test_workflow_preserves_setup_cache_and_other_repositories(self):
        workflow = yaml.safe_load((ROOT / '.github/workflows/build.yml').read_text())
        steps = workflow['jobs']['validate']['steps']
        names = [step.get('name') for step in steps]
        dependencies = next(step for step in steps if step.get('name') == 'Preflight validation dependencies')
        contract = next(step for step in steps if step.get('name') == 'Classify YueBoard reviewed-pin authorization')
        native = next(step for step in steps if step.get('name') == 'Validate native-node cross-repository contract')
        cache_clear = next(step for step in steps if step.get('name') == 'Keep Go test execution independent of compiler cache')
        for setup in ('Set up YueBoard Go', 'Set up Node', 'Set up Buf for YueBoard protocol compatibility'):
            self.assertLess(names.index(setup), names.index(dependencies['name']))
        self.assertLess(names.index(dependencies['name']), names.index('Plan trusted Go caches'))
        self.assertLess(names.index('Restore and refresh Go compiler cache'), names.index(contract['name']))
        self.assertLess(names.index(contract['name']), names.index('Validate YueBoard backend quality gates'))
        self.assertEqual(contract['if'], "matrix.validation == 'yueboard'")
        self.assertEqual(contract['env'], {'PROMOTE': '${{ needs.plan.outputs.promote }}'})
        self.assertEqual(cache_clear['if'], "matrix.validation == 'yue-node'")
        self.assertEqual(cache_clear['run'], 'go clean -testcache')
        self.assertEqual(native['if'], "matrix.validation == 'yue-node' || matrix.validation == 'yueops'")
        self.assertIn('--yueboard-contract-source .ci-yueboard', native['run'])
        self.assertIn('exec bash .ci-policy/scripts/board-validation-preflight.sh dependencies', dependencies['run'])
        self.assertIn('yue-node) tools+=(base64 docker gcc go gpg jq make)', dependencies['run'])
        self.assertIn('yueops) tools+=(docker initdb jq node npm pg_ctl postgres psql sing-box-1.14 uv)', dependencies['run'])
        self.assertIn('board-validation-preflight.sh contract', contract['run'])
