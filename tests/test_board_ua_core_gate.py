"""Drive the real CI wrapper; fake Docker records the isolation boundary."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/validate-board-ua-cores.sh'
IMAGE = 'golang@sha256:c292963ad0e5f51e843c726edc204a4e4c26a859ba1e4d736d91028aa3633048'
CONTAINER = 'a' * 64


class BoardOfflineCoreGateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / 'source'
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        (self.source / 'scripts/ci').mkdir(parents=True)
        (self.source / 'go.mod').write_text('module fixture\n\ngo 1.27.0\ntoolchain go1.27.3\n')
        (self.source / 'scripts/ci/core-assets.json').write_text('{}\n')
        (self.source / 'scripts/ci/ua-core-gate.sh').write_text('echo unexpected-host-core-execution >&2; exit 97\n')
        (self.source / 'scripts/ci/prepare-ua-cores.py').write_text('''import json, os, sys
with open(os.environ['CALLS'], 'a') as log: log.write(json.dumps(['prepare', *sys.argv[1:]])+'\\n')
if '--download-only' not in sys.argv: sys.exit(85)
sys.exit(int(os.environ.get('PREPARE_EXIT', '0')))
''')
        self.shim('uname', 'echo Linux')
        self.shim('go', '''case "$*" in
"env GOVERSION") echo "${FIXTURE_GO_VERSION:-go1.27.3}";;
"env GOMODCACHE") echo "$FIXTURE_BASE/modules";;
"env GOCACHE") echo "$FIXTURE_BASE/compiler";;
*) exit 98;; esac''')
        self.shim('timeout', 'shift 3; exec "$@"')
        docker = self.bin / 'docker'
        docker.write_text('#!' + sys.executable + '\n' + '''import json, os, sys
args = sys.argv[1:]
with open(os.environ['CALLS'], 'a') as log: log.write(json.dumps(args)+'\\n')
if args[0] == 'create':
    required = ['--network', 'none', '--read-only', '--cap-drop', 'ALL', 'GOTOOLCHAIN=local', 'GOPROXY=off', '/tmp:rw,exec,nosuid,nodev']
    if any(value not in args for value in required): sys.exit(71)
    if not any(value.endswith('dst=/source,readonly') for value in args): sys.exit(72)
    if 'bash scripts/ci/ua-core-gate.sh --cache-dir /cores' not in args[-1]: sys.exit(74)
if os.environ.get('DOCKER_FAIL') == args[0]: sys.exit(73)
if args[0] == 'create': print('a'*64)
if args[0] == 'inspect': print(os.environ.get('DOCKER_STATE', 'exited 0'))
''')
        docker.chmod(0o755)
        self.calls = self.base / 'calls'
        self.env = {**os.environ, 'PATH': str(self.bin) + os.pathsep + os.environ['PATH'],
                    'FIXTURE_BASE': str(self.base), 'RUNNER_TEMP': str(self.base),
                    'UA_CORE_CACHE': str(self.base / 'cores'), 'CALLS': str(self.calls),
                    'GH_TOKEN': 'must-never-be-forwarded', 'YUEBOARD_MIHOMO_BINS': 'untrusted-path'}

    def shim(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/bash\nset -euo pipefail\n' + body + '\n')
        path.chmod(0o755)

    def run_wrapper(self, script=SCRIPT, /, **env):
        self.calls.unlink(missing_ok=True)
        return subprocess.run(['bash', str(script)], cwd=self.source,
                              env={**self.env, **env}, capture_output=True, text=True, timeout=15)

    def commands(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []

    def test_actual_wrapper_downloads_without_execution_then_runs_only_isolated(self):
        result = self.run_wrapper()
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = self.commands()
        self.assertEqual([args[0] for args in commands], ['prepare', 'pull', 'create', 'start', 'inspect', 'rm'])
        self.assertEqual(commands[0][1:], ['--download-only', '--cache-dir', self.env['UA_CORE_CACHE']])
        self.assertEqual(commands[1], ['pull', IMAGE])
        create = commands[2]
        self.assertIn(IMAGE, create)
        for flag, value in [('--network', 'none'), ('--cpus', '2'), ('--memory', '4g'),
                            ('--cap-drop', 'ALL'), ('--security-opt', 'no-new-privileges')]:
            self.assertEqual(create[create.index(flag) + 1], value)
        allowed = {'TZ=UTC', 'HOME=/tmp/ua-home', 'GOMODCACHE=/go-mod', 'GOCACHE=/go-build',
                   'GOPROXY=off', 'GOSUMDB=off', 'GOTOOLCHAIN=local', 'CGO_ENABLED=1',
                   'YUEBOARD_CORE_GATE_PROCS=2', 'GOMAXPROCS=2'}
        self.assertEqual({create[i+1] for i, arg in enumerate(create) if arg == '-e'}, allowed)
        self.assertNotIn('must-never-be-forwarded', ' '.join(create))
        self.assertNotIn('untrusted-path', ' '.join(create))
        self.assertNotIn('--privileged', create)
        self.assertNotIn('/var/run/docker.sock', ' '.join(create))
        self.assertEqual(commands[-1], ['rm', '--force', CONTAINER])
        self.assertNotIn('unexpected-host-core-execution', result.stdout + result.stderr)

    def test_failures_propagate_and_cleanup_only_an_owned_container(self):
        for overrides, last, owns in [({'PREPARE_EXIT': '7'}, 'prepare', False),
                                      ({'DOCKER_FAIL': 'pull'}, 'pull', False),
                                      ({'DOCKER_FAIL': 'create'}, 'create', False),
                                      ({'DOCKER_FAIL': 'start'}, 'rm', True),
                                      ({'DOCKER_STATE': 'exited 7'}, 'rm', True),
                                      ({'DOCKER_STATE': 'running 0'}, 'rm', True)]:
            with self.subTest(overrides=overrides):
                result = self.run_wrapper(**overrides)
                self.assertNotEqual(result.returncode, 0)
                commands = self.commands()
                self.assertEqual(commands[-1][0], last)
                self.assertEqual(any(row[0] == 'rm' for row in commands), owns)

    def test_missing_source_mismatched_toolchain_and_invalid_mount_refuse(self):
        for overrides in [{'FIXTURE_GO_VERSION': 'go1.27.4'}, {'UA_CORE_CACHE': 'relative'},
                          {'UA_CORE_CACHE': str(self.base / 'comma,cache')}]:
            with self.subTest(overrides=overrides):
                self.assertNotEqual(self.run_wrapper(**overrides).returncode, 0)
                self.assertEqual(self.commands(), [])
        (self.source / 'scripts/ci/ua-core-gate.sh').unlink()
        self.assertNotEqual(self.run_wrapper().returncode, 0)
        self.assertEqual(self.commands(), [])

    def test_removing_isolation_readonly_source_or_download_only_is_detected(self):
        original = SCRIPT.read_text()
        for old, new in [('--network none', '--network bridge'),
                         ('dst=/source,readonly', 'dst=/source'),
                         ('--download-only --cache-dir', '--cache-dir'),
                         ('/tmp:rw,exec,nosuid,nodev', '/tmp:rw,nosuid,nodev'),
                         ('bash scripts/ci/ua-core-gate.sh --cache-dir /cores', 'true')]:
            with self.subTest(mutation=old):
                mutated = self.base / 'mutated.sh'
                self.assertIn(old, original)
                mutated.write_text(original.replace(old, new))
                self.assertNotEqual(self.run_wrapper(mutated).returncode, 0)

    def test_workflow_gate_is_mandatory_quality_only_after_existing_warmup(self):
        jobs = yaml.safe_load((ROOT / '.github/workflows/build.yml').read_text())['jobs']
        steps = jobs['validate']['steps']
        index = next(i for i, step in enumerate(steps) if step.get('name') == 'Validate YueBoard UA parsers without network access')
        gate = steps[index]
        self.assertEqual(gate['if'], "matrix.validation == 'yueboard' && matrix.board_role == 'quality'")
        self.assertNotIn('continue-on-error', gate)
        self.assertEqual(gate['run'], 'bash .ci-policy/scripts/validate-board-ua-cores.sh')
        self.assertEqual(gate['env'], {'UA_CORE_CACHE': '${{ runner.temp }}/yueboard-ua-cores'})
        self.assertEqual(gate['timeout-minutes'], 30)
        self.assertLess(next(i for i, s in enumerate(steps) if s.get('name') == 'Validate YueBoard backend quality gates'), index)
        cache = next(s for s in steps if s.get('name') == 'Restore verified public UA core archives')
        self.assertIn("steps.go_cache.outputs.enabled == 'true'", cache['if'])
        self.assertNotIn('restore-keys', cache['with'])
        self.assertIn('core-assets.json', cache['with']['key'])
