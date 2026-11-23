"""Check the local Node adapter against the public job without contacting forks."""
import contextlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import ci_check_node_local as local

SHA = 'a' * 40


class NodeLocalBoardRouting(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        scripts = self.root / 'scripts'
        scripts.mkdir()
        (scripts / 'ci-check.sh').write_text((ROOT / 'scripts/ci-check.sh').read_text())
        (scripts / 'ci_check_board.py').write_text(
            'from pathlib import Path\nimport sys\n'
            'assert len(sys.argv) == 3 and sys.argv[1] == "--root"\n'
            'root = Path(sys.argv[2])\n'
            '(root / "resolver-called").touch()\n'
            'if not (root / "revision").exists():\n'
            '    sys.exit(2)\n'
            'print((root / "revision").read_text(), end="")\n')
        (scripts / 'ci_check_node_local.py').write_text(
            'from pathlib import Path\nimport sys\n'
            'print((Path(sys.argv[3]) / "revision").read_text(), end="")\n')
        self.desired = self.root / 'desired'
        self.desired.mkdir()
        tools = self.root / 'bin'
        tools.mkdir()
        git = tools / 'git'
        # Stub Git transport and record the commit actually checked out for the adapter.
        git.write_text('''#!/bin/bash
set -eu
case "$1" in
  clone)
    destination=${@: -1}
    mkdir -p "$destination"
    if [[ "$destination" = */policy ]]; then
      cp -R "$FIXTURE_ROOT/scripts" "$FIXTURE_ROOT/native-node-contract.json" "$destination"
    fi
    ;;
  -C)
    case "$3" in
      rev-parse) printf '%040d\\n' 1 ;;
      checkout) printf '%s\\n' "${@: -1}" > "$2/revision" ;;
      status|remote|fetch) ;;
      -c) [[ "$5" = -c && "$7" = fetch ]] ;;
      *) exit 99 ;;
    esac
    ;;
  *) exit 99 ;;
esac
''')
        git.chmod(0o755)
        self.env = {
            'PATH': f'{tools}{os.pathsep}{os.environ["PATH"]}',
            'YUETO_ROOT': str(self.desired),
            'CI_CHECK_OUTPUT': str(self.root / 'output'),
            'FIXTURE_ROOT': str(self.root),
        }
        self.write_pin('d' * 40)

    def write_pin(self, sha):
        (self.root / 'native-node-contract.json').write_text(json.dumps({'yueboard_contract_pin': sha}))

    def run_cli(self, *options):
        return subprocess.run(
            ['bash', self.root / 'scripts/ci-check.sh', 'yue-node', SHA, '--local', *options],
            env=self.env, capture_output=True, text=True, timeout=15)

    def test_explicit_board_revision_bypasses_resolver(self):
        result = self.run_cli('--board-ref', 'b' * 40)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'b' * 40)
        self.assertFalse((self.desired / 'resolver-called').exists())

    def test_signed_desired_revision_is_independent_of_legacy_pin(self):
        (self.desired / 'revision').write_text('c' * 40)
        for pin in ('d' * 40, 'e' * 40):
            with self.subTest(pin=pin):
                self.write_pin(pin)
                result = self.run_cli()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), 'c' * 40)
        self.assertTrue((self.desired / 'resolver-called').exists())

    def test_invalid_explicit_ref_fails_without_resolving(self):
        for ref in ('', 'b' * 39, 'g' * 40):
            with self.subTest(ref=ref):
                result = self.run_cli('--board-ref', ref)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('board ref must be an exact 40-hex commit SHA', result.stderr)
        self.assertFalse((self.desired / 'resolver-called').exists())

    def test_unavailable_or_invalid_desired_fails_without_pin_fallback(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('could not resolve the signed desired Board revision', result.stderr)
        (self.desired / 'revision').write_text('invalid')
        result = self.run_cli()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('board ref must be an exact 40-hex commit SHA', result.stderr)
        self.assertFalse((self.root / 'output').exists())


class NodeLocal(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / 'node'
        self.board = self.root / 'pinned-board'
        self.home = self.root / 'empty-home'
        for path in (self.source, self.board, self.home):
            path.mkdir()
        self.env = {'PATH': os.environ['PATH'], 'HOME': str(self.home)}

    def execute(self, system='Linux', failures=None, missing=None):
        calls = []
        def record(command, *, cwd, env, stdout, stderr):
            self.assertEqual(cwd, self.source)
            name = Path(stdout.name).stem
            calls.append((name, list(map(str, command)), env.copy()))
            return subprocess.CompletedProcess(command, (failures or {}).get(name, 0))

        # Keep the real workflow planner and JSON decoding. Stub only role
        # execution and the host inventory to exercise Darwin and Linux.
        output = io.StringIO()
        plan = subprocess.check_output(
            ['bash', ROOT / 'scripts/plan-build-targets.sh', 'yue-node-validation', SHA], text=True)
        with patch.object(local.platform, 'system', return_value=system), \
             patch.object(local.subprocess, 'check_output', return_value=plan), \
             patch.object(local.subprocess, 'run', side_effect=record), \
             patch.object(local.shutil, 'which', side_effect=lambda tool, path: None if tool == missing else tool), \
             patch.dict(os.environ, {'YUETO_FORK_READ_TOKEN': 'fixture-only', 'GH_TOKEN': 'fixture-only'}), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            rc = local.run(self.source, SHA, self.board, self.root, str(self.home))
        return rc, calls, output.getvalue()

    def test_linux_roles_match_public_workflow(self):
        jobs = yaml.safe_load((ROOT / '.github/workflows/build.yml').read_text())['jobs']
        validate = jobs['validate']
        self.assertEqual(validate['strategy']['matrix']['include'],
                         '${{ fromJSON(needs.plan.outputs.validation_matrix) }}')
        planning = '\n'.join(step.get('run', '') for step in jobs['plan']['steps'])
        planner = re.search(r'target_plan="\$\(bash (scripts/[\w-]+\.sh) "\$SERVICE" "\$REF_OVERRIDE"', planning)[1]
        matrix = json.loads(subprocess.check_output(['bash', ROOT / planner, 'yue-node', SHA]))
        profiles = [row['node_profile'] for row in matrix['validation_matrix']]
        self.assertEqual(local.profiles(SHA, self.env), profiles)

        expected = []
        for step in validate['steps']:
            body = step.get('run', '')
            for script, phase in re.findall(r'bash \.ci-policy/scripts/(node-validation-preflight\.sh) (\w+)', body):
                expected.append((phase, ['bash', str(ROOT / 'scripts' / script), phase,
                                         str(self.source), str(ROOT), str(self.board)]))
            if 'make verify-fork-tags' in body:
                expected.append(('verify-fork-tags', ['make', 'verify-fork-tags']))
            if 'bash .ci-policy/scripts/node-validation.sh "$NODE_PROFILE" "$GITHUB_WORKSPACE"' in body:
                self.assertEqual(step['env']['NODE_PROFILE'], '${{ matrix.node_profile }}')
                expected.extend((p, ['bash', str(ROOT / 'scripts/node-validation.sh'), p, str(self.source)])
                                for p in profiles)
        rc, calls, _ = self.execute()
        self.assertEqual(rc, 0)
        self.assertEqual([(name, command) for name, command, _ in calls], expected)
        for name, _, env in calls:
            self.assertNotIn('GH_TOKEN', env)
            self.assertNotIn('YUETO_FORK_READ_TOKEN', env)
            if name == 'verify-fork-tags':
                self.assertIn('GIT_CONFIG_VALUE_0', env)
            else:
                self.assertEqual(env['HOME'], str(self.home))
                self.assertFalse(any(key.startswith('GIT_CONFIG') for key in env))

    def test_mutated_matrix_rejected(self):
        plan = json.loads(subprocess.check_output(
            ['bash', ROOT / 'scripts/plan-build-targets.sh', 'yue-node-validation', SHA]))
        rows = plan['validation_matrix']
        for changed in (rows[:1], [rows[0], rows[0]],
                        [rows[0], dict(rows[1], ref='b' * 40)]):
            with self.subTest(matrix=changed), patch.object(
                    local.subprocess, 'check_output', return_value=json.dumps({'validation_matrix': changed})):
                with self.assertRaises(ValueError):
                    local.profiles(SHA, self.env)

    def test_darwin_runs_portable_gates_and_marks_every_linux_profile(self):
        rc, calls, output = self.execute('Darwin')
        self.assertEqual(rc, 3)
        self.assertEqual([name for name, _, _ in calls], ['contract', 'verify-fork-tags'])
        self.assertEqual([line for line in output.splitlines() if line.startswith('SKIP-PLATFORM')],
                         ['SKIP-PLATFORM dependencies', 'SKIP-PLATFORM hy2', 'SKIP-PLATFORM vless'])

    def test_failed_gate_stops_profiles_but_profile_failure_finishes_sibling(self):
        for name in ('contract', 'verify-fork-tags', 'hy2'):
            with self.subTest(name=name):
                rc, calls, output = self.execute(failures={name: 1})
                self.assertEqual(rc, 1)
                self.assertIn('FAIL ' + name, output)
                self.assertEqual(calls[-1][0], 'vless' if name == 'hy2' else name)

    def test_missing_tool_reports_infrastructure_failure(self):
        rc, _, output = self.execute('Darwin', missing='gpg')
        self.assertEqual(rc, 2)
        self.assertIn('MISSING-TOOL verify-fork-tags gpg', output)
        rc, calls, _ = self.execute(failures={'dependencies': 1})
        self.assertEqual(rc, 2)
        self.assertEqual([name for name, _, _ in calls], ['dependencies'])


if __name__ == '__main__':
    unittest.main()
