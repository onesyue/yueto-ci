"""Drive the real CI wrapper; fake Docker records the isolation boundary."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import signal
import time
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/validate-board-ua-cores.sh'
IMAGE = 'golang@sha256:4fa7c968ba93f1635670522dbb01a2c78150443e1385746924566079f36570ea'
CONTAINER = 'a' * 64


class BoardOfflineCoreGateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / 'source'
        (self.base / 'real-home').mkdir()
        (self.base / 'home-alias').symlink_to(self.base / 'real-home', target_is_directory=True)
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        (self.source / 'scripts/ci').mkdir(parents=True)
        (self.source / 'go.mod').write_text('module fixture\n\ngo 1.27.0\ntoolchain go1.27.4\n')
        (self.source / 'scripts/ci/core-assets.json').write_text('{}\n')
        (self.source / 'scripts/ci/ua-core-gate.sh').write_text('echo unexpected-host-core-execution >&2; exit 97\n')
        (self.source / 'scripts/ci/prepare-ua-cores.py').write_text('''import json, os, sys
with open(os.environ['CALLS'], 'a') as log: log.write(json.dumps(['prepare', *sys.argv[1:]])+'\\n')
if '--download-only' not in sys.argv: sys.exit(85)
sys.exit(int(os.environ.get('PREPARE_EXIT', '0')))
''')
        self.shim('uname', '''case "$*" in
-s) echo Linux;;
-m) echo "${FIXTURE_MACHINE:-x86_64}";;
*) exit 98;; esac''')
        self.shim('go', '''case "$*" in
"env GOVERSION") echo "${FIXTURE_GO_VERSION:-go1.27.4}";;
"env GOHOSTOS") echo "${FIXTURE_GO_OS:-linux}";;
"env GOHOSTARCH") echo "${FIXTURE_GO_ARCH:-amd64}";;
"env GOMODCACHE") echo "${FIXTURE_MODULE_CACHE:-$FIXTURE_BASE/modules}";;
"env GOCACHE") echo "$FIXTURE_BASE/compiler";;
*) exit 98;; esac''')
        self.shim('timeout', 'shift 3; exec "$@"')
        docker = self.bin / 'docker'
        docker.write_text('#!' + sys.executable + '\n' + '''import json, os, sys, time
from pathlib import Path
args = sys.argv[1:]
with open(os.environ['CALLS'], 'a') as log: log.write(json.dumps(args)+'\\n')
rows = [json.loads(line) for line in Path(os.environ['CALLS']).read_text().splitlines()]
action = args[0]
seed = action == 'create' and args[-1] == 'true'
if args[:2] == ['volume', 'create']: action = 'volume-create'
if args[:2] == ['volume', 'rm']: action = 'volume-rm'
if seed: action = 'seed-create'
if os.environ.get('DOCKER_FAIL') == action: sys.exit(73)
if action == 'volume-create':
    number = sum(row[:2] == ['volume', 'create'] for row in rows)
    print('invalid' if os.environ.get('INVALID_VOLUME_ID') else str(number) * 64)
if action == 'cp':
    assert args[1] == '-a'
    if str(sum(row[0] == 'cp' for row in rows)) == os.environ.get('CP_FAIL_AT'): sys.exit(74)
if args[0] == 'create':
    required = ['--network', 'none', '--cap-drop', 'ALL']
    if any(value not in args for value in required): sys.exit(71)
    if any('type=bind' in value for value in args): sys.exit(72)
    if not seed:
        for value in ['--read-only', 'GOTOOLCHAIN=local', 'GOPROXY=off', '/tmp:rw,exec,nosuid,nodev']:
            if value not in args: sys.exit(71)
        if not any(value.endswith('dst=/source,readonly') for value in args): sys.exit(72)
        if 'bash scripts/ci/ua-core-gate.sh --cache-dir /cores/data' not in args[-1]: sys.exit(74)
    print(('b' if seed else 'a') * 64)
if args[0] == 'start' and os.environ.get('DOCKER_BLOCK'): time.sleep(60)
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
        self.assertEqual([args[0] for args in commands],
                         ['prepare', 'pull', *(['volume'] * 4), 'create', *(['cp'] * 4),
                          'create', 'start', 'inspect', 'rm', 'rm', *(['volume'] * 4)])
        self.assertEqual(commands[0][1:], ['--download-only', '--cache-dir', str(Path(self.env['UA_CORE_CACHE']).resolve())])
        self.assertEqual(commands[1], ['pull', '--platform', 'linux/amd64', IMAGE])
        create = next(row for row in commands if row[0] == 'create' and row[-1] != 'true')
        self.assertIn(IMAGE, create)
        self.assertEqual(create[create.index('--platform') + 1], 'linux/amd64')
        for flag, value in [('--network', 'none'), ('--cpus', '2'), ('--memory', '4g'),
                            ('--cap-drop', 'ALL'), ('--security-opt', 'no-new-privileges')]:
            self.assertEqual(create[create.index(flag) + 1], value)
        allowed = {'TZ=UTC', 'HOME=/tmp/ua-home', 'GOMODCACHE=/go-mod/data', 'GOCACHE=/go-build/data',
                   'GOPROXY=off', 'GOSUMDB=off', 'GOTOOLCHAIN=local', 'UA_GO_ARCH=amd64', 'CGO_ENABLED=1',
                   'YUEBOARD_CORE_GATE_PROCS=2', 'GOMAXPROCS=2'}
        self.assertEqual({create[i+1] for i, arg in enumerate(create) if arg == '-e'}, allowed)
        self.assertNotIn('must-never-be-forwarded', ' '.join(create))
        self.assertNotIn('untrusted-path', ' '.join(create))
        self.assertNotIn('--privileged', create)
        self.assertNotIn('/var/run/docker.sock', ' '.join(create))
        self.assertIn(['rm', '--force', CONTAINER], commands)
        self.assertEqual([row for row in commands if row[0] == 'start'], [['start', '--attach', CONTAINER]])
        receipts = list(self.base.glob('ua-core-ci.*/resources.jsonl'))
        self.assertEqual(len(receipts), 1)
        resources = [json.loads(line) for line in receipts[0].read_text().splitlines()]
        created = {(row['kind'], row['id']) for row in resources if row['action'] == 'created'}
        removed = {(row['kind'], row['id']) for row in resources if row['action'] == 'removed' and row['exit_code'] == 0}
        self.assertEqual(len(created), 6)
        self.assertEqual(created, removed)
        self.assertNotIn('unexpected-host-core-execution', result.stdout + result.stderr)

    def test_transport_does_not_assume_job_paths_exist_on_daemon(self):
        result = self.run_wrapper()
        self.assertEqual(result.returncode, 0, result.stderr)
        creates = [row for row in self.commands() if row[0] == 'create']
        self.assertEqual(len(creates), 2, 'stopped seed plus isolated parser required')
        users = [row[row.index('--user') + 1] for row in creates]
        self.assertEqual(users, [f'{os.getuid()}:{os.getgid()}'] * 2)
        self.assertFalse(any('type=bind' in arg for row in creates for arg in row))
        copies = [row for row in self.commands() if row[0] == 'cp']
        self.assertEqual(len(copies), 4)
        self.assertTrue(all(row[1] == '-a' for row in copies))

    def test_failures_propagate_and_cleanup_only_an_owned_container(self):
        for overrides, starts, containers in [({'PREPARE_EXIT': '7'}, False, 0),
                                              ({'DOCKER_FAIL': 'pull'}, False, 0),
                                              ({'DOCKER_FAIL': 'volume-create'}, False, 0),
                                              ({'DOCKER_FAIL': 'seed-create'}, False, 0),
                                              ({'CP_FAIL_AT': '2'}, False, 1),
                                              ({'DOCKER_FAIL': 'create'}, False, 1),
                                              ({'DOCKER_FAIL': 'start'}, True, 2),
                                              ({'DOCKER_STATE': 'exited 7'}, True, 2),
                                              ({'DOCKER_STATE': 'running 0'}, True, 2),
                                              ({'DOCKER_FAIL': 'rm'}, True, 2),
                                              ({'DOCKER_FAIL': 'volume-rm'}, True, 2),
                                              ({'INVALID_VOLUME_ID': '1'}, False, 0)]:
            with self.subTest(overrides=overrides):
                result = self.run_wrapper(**overrides)
                self.assertNotEqual(result.returncode, 0)
                commands = self.commands()
                self.assertEqual(any(row[0] == 'start' for row in commands), starts)
                self.assertEqual(sum(row[0] == 'rm' for row in commands), containers)
                created_volumes = sum(row[:2] == ['volume', 'create'] for row in commands)
                removed_volumes = sum(row[:2] == ['volume', 'rm'] for row in commands)
                if 'INVALID_VOLUME_ID' in overrides or overrides.get('DOCKER_FAIL') == 'volume-create':
                    self.assertEqual(removed_volumes, 0)
                else:
                    self.assertEqual(removed_volumes, created_volumes)

    def test_arm64_platform_is_explicit_for_pull_seed_and_gate(self):
        result = self.run_wrapper(FIXTURE_GO_ARCH='arm64', FIXTURE_MACHINE='aarch64')
        self.assertEqual(result.returncode, 0, result.stderr)
        for row in self.commands():
            if row[0] in ('pull', 'create'):
                self.assertEqual(row[row.index('--platform') + 1], 'linux/arm64')
        create = next(row for row in self.commands() if row[0] == 'create' and row[-1] != 'true')
        self.assertIn('UA_GO_ARCH=arm64', create)
        self.assertIn('[ "$(go env GOHOSTARCH)" = "$UA_GO_ARCH" ]', create[-1])

    def test_term_cleans_every_owned_resource(self):
        self.calls.unlink(missing_ok=True)
        process = subprocess.Popen(['bash', str(SCRIPT)], cwd=self.source,
                                   env=self.env | {'DOCKER_BLOCK': '1'}, start_new_session=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if any(row[0] == 'start' for row in self.commands()):
                    break
                if process.poll() is not None:
                    self.fail('wrapper exited before cancellable gate')
                time.sleep(0.02)
            else:
                self.fail('wrapper never started gate')
            os.killpg(process.pid, signal.SIGTERM)
            stdout, stderr = process.communicate(timeout=10)
            self.assertNotEqual(process.returncode, 0, stdout + stderr)
            commands = self.commands()
            self.assertEqual(sum(row[0] == 'rm' for row in commands), 2)
            self.assertEqual(sum(row[:2] == ['volume', 'rm'] for row in commands), 4)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()

    def test_missing_source_mismatched_toolchain_and_invalid_mount_refuse(self):
        for overrides in [{'FIXTURE_GO_VERSION': 'go1.27.3'}, {'FIXTURE_GO_ARCH': 'arm64'},
                          {'FIXTURE_GO_OS': 'darwin'}, {'FIXTURE_MACHINE': 'riscv64'},
                          {'FIXTURE_MODULE_CACHE': os.environ['HOME']},
                          {'HOME': str(self.base / 'home-alias'), 'FIXTURE_MODULE_CACHE': str(self.base / 'real-home')},
                          {'UA_CORE_CACHE': 'relative'},
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
                         ('bash scripts/ci/ua-core-gate.sh --cache-dir /cores/data', 'true')]:
            with self.subTest(mutation=old):
                mutated = self.base / 'mutated.sh'
                self.assertIn(old, original)
                mutated.write_text(original.replace(old, new))
                self.assertNotEqual(self.run_wrapper(mutated).returncode, 0)

    def test_shared_quality_gate_runs_after_warmup_and_before_protocol(self):
        jobs = yaml.safe_load((ROOT / '.github/workflows/build.yml').read_text())['jobs']
        steps = jobs['validate']['steps']
        compiler = next(s for s in steps if s.get('name') == 'Set up YueBoard Go')['with']['go-version']
        self.assertIn(f'readonly UA_GO_VERSION=go{compiler}\n', SCRIPT.read_text())
        self.assertIn(f'[ "$(go env GOVERSION)" = go{compiler} ]', SCRIPT.read_text())
        gate = next(s for s in steps if s.get('name') == 'Validate YueBoard backend quality gates')
        self.assertEqual(gate['if'], "matrix.validation == 'yueboard' && matrix.board_role == 'quality'")
        self.assertNotIn('continue-on-error', gate)
        self.assertIn('board-validation.sh quality', gate['run'])
        executor = (ROOT / 'scripts/board-validation.sh').read_text()
        quality = executor.split('  quality)\n', 1)[1].split('  race)\n', 1)[0]
        command = 'bash "$policy/scripts/validate-board-ua-cores.sh"'
        self.assertIn(command, quality)
        self.assertIn('timeout --signal=TERM --kill-after=60s 30m', quality)
        self.assertLess(quality.index('go test ./...'), quality.index(command))
        self.assertLess(quality.index(command), quality.index('scripts/ci/proto-gate.sh'))
        self.assertIn('UA_CORE_CACHE="$temp/yueboard-ua-cores" RUNNER_TEMP="$temp"', quality)
        cache = next(s for s in steps if s.get('name') == 'Restore verified public UA core archives')
        self.assertLess(steps.index(cache), steps.index(gate))
        self.assertIn("steps.go_cache.outputs.enabled == 'true'", cache['if'])
        self.assertNotIn('restore-keys', cache['with'])
        self.assertIn('core-assets.json', cache['with']['key'])
