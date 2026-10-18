#!/usr/bin/env python3
"""Run every applicable PostgreSQL integration test, reject skips/non-execution."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit

DOMAIN = ['./test/integration']
COMMANDS = ['./cmd/yueboard']
MODULES = [
    './internal/modules/user', './internal/platform/referencelock',
    './internal/modules/order', './internal/modules/emby', './internal/modules/handoff',
    './internal/platform/deviceidentity', './internal/modules/nodesync',
    './internal/modules/subscribe', './internal/modules/statcron',
    './internal/modules/remindmailcron',
]
MIGRATIONS = ['./internal/platform/db', './internal/platform/nativeproto']
ORDER = DOMAIN + COMMANDS + MODULES + MIGRATIONS
COMMAND_GATE = Path('scripts/ci/net-operator-pg18-gate.sh')
# Historical sources may omit only reviewed additions whose schema/capability
# did not exist yet. Every suite actually discovered still must execute.
HISTORICAL_ADDITIONS = {'./internal/modules/user', './internal/platform/referencelock',
                        './internal/platform/nativeproto'}
FLOOR_ADDITIONS = {'./internal/modules/subscribe': 138, './internal/modules/statcron': 139}
CAPABILITY_ADDITIONS = {
    './internal/modules/remindmailcron': Path('internal/platform/reminderrules/rules_g.go'),
}
DSNS = ['YUEBOARD_TEST_DATABASE_URL', 'YUEBOARD_TRAFFIC_TEST_DATABASE_URL',
        'YUEBOARD_EMAILVERIFY_TEST_DATABASE_URL', 'YUEBOARD_MIGRATION_TEST_DATABASE_URL']


def fail(message: str) -> None:
    raise RuntimeError(message)


def check_environment() -> None:
    values = []
    for key in DSNS:
        value = os.environ.get(key, '')
        if not value:
            fail(f'{key} is required; refusing a silently skipped integration suite')
        parsed = urlsplit(value)
        if parsed.scheme not in ('postgres', 'postgresql') or parsed.hostname not in ('127.0.0.1', 'localhost') or parsed.path != '/yueboard_test':
            fail(f'{key} must point at the loopback disposable yueboard_test service')
        values.append(value)
    if len(set(values)) != 1:
        fail('all four integration DSNs must address the same disposable service/database')
    if os.environ.get('YUEBOARD_MIGRATION_TEST_ALLOW_RESET') != 'YES_I_UNDERSTAND_THIS_DATABASE_IS_DISPOSABLE':
        fail('disposable migration reset acknowledgement is required')
    if os.environ.get('YUEBOARD_MIGRATION_TEST_PRODUCTION_SCALE') != '1':
        fail('production-scale migration cases must be enabled')


def discover() -> list[dict]:
    helper = Path(__file__).with_name('list-integration-tests.go')
    result = subprocess.run(['go', 'run', str(helper)], stdout=subprocess.PIPE, text=True, check=True)
    entries = json.loads(result.stdout)
    found = {row['path'] for row in entries}
    floor = int(Path('schema-floor.txt').read_text().strip())
    # Floor 134 predates the root-only operator CLI. Its owned Linux gate is
    # the capability marker; older sources may omit only this command package.
    required = set(ORDER) - set(COMMANDS) - (HISTORICAL_ADDITIONS if floor < 130 else set())
    required -= {path for path, minimum in FLOOR_ADDITIONS.items() if floor < minimum}
    required -= {path for path, marker in CAPABILITY_ADDITIONS.items() if not marker.is_file()}
    if COMMAND_GATE.is_file():
        required.update(COMMANDS)
    if not required <= found or found - set(ORDER) or len(found) != len(entries):
        fail(f'integration package plan mismatch: missing={sorted(required-found)} unplanned={sorted(found-set(ORDER))}')
    for row in entries:
        if not row['tests']:
            fail(f"no integration test functions discovered in {row['path']}")
    print(f'Integration discovery: floor={floor}; packages={len(entries)}; '
          f'tests={sum(len(row["tests"]) for row in entries)}; '
          f'explicit historical omissions={sorted(set(ORDER)-found)}', flush=True)
    return entries


def run_group(paths: list[str], entries: list[dict]) -> dict:
    expected = {row['import_path']: set(row['tests']) for row in entries if row['path'] in paths}
    selected = [path for path in paths if any(row['path'] == path for row in entries)]
    if not selected or not expected:
        fail('empty integration execution group')
    # The earlier backend phase runs all ordinary tests and the race suite.
    # Here execute exactly the AST-discovered integration tests; unrelated
    # opt-in binary/template unit checks must not masquerade as PG coverage.
    test_names = sorted(set().union(*expected.values()))
    pattern = '^(' + '|'.join(re.escape(name) for name in test_names) + ')$'
    command = ['go', 'test', '-count=1', '-p', '1', '-tags', 'integration',
               '-run', pattern, '-json', '-v', *selected]
    print('+ ' + ' '.join(command), flush=True)
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    runs: dict[str, set[str]] = {package: set() for package in expected}
    passed: dict[str, set[str]] = {package: set() for package in expected}
    completed: set[str] = set()
    issues: list[str] = []
    counts = {'top_level_passed': 0, 'subtests_passed': 0, 'skipped': 0}
    assert process.stdout is not None
    for line in process.stdout:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            print(line, end='', flush=True)
            issues.append('non-JSON Go test output')
            continue
        if event.get('Output'):
            print(event['Output'], end='', flush=True)
        package, test, action = event.get('Package'), event.get('Test'), event.get('Action')
        if action == 'skip':
            counts['skipped'] += 1
            issues.append(f'skipped: {package}/{test or "<package>"}')
        if action == 'fail':
            issues.append(f'failed: {package}/{test or "<package>"}')
        if package not in expected:
            continue  # Build diagnostics remain fully visible above.
        if action == 'run' and test:
            runs[package].add(test)
        if action == 'pass' and test:
            passed[package].add(test)
            counts['subtests_passed' if '/' in test else 'top_level_passed'] += 1
        if action == 'pass' and not test:
            completed.add(package)
    process.stdout.close()
    status = process.wait()
    if status:
        issues.append(f'go test exited {status}')
    for package, tests in expected.items():
        missing = tests - (runs[package] & passed[package])
        if missing:
            issues.append(f'{package}: integration tests not run and passed: {sorted(missing)}')
        if package not in completed:
            issues.append(f'{package}: no successful package completion')
    if issues:
        fail('\n'.join(issues))
    print('Integration execution: ' + json.dumps({'packages': selected, **counts}), flush=True)
    return {'packages': selected, **counts}


def run_commands(entries: list[dict]) -> dict:
    selected = [row for row in entries if row['path'] in COMMANDS]
    if not selected:
        return {'packages': [], 'top_level_passed': 0, 'subtests_passed': 0, 'skipped': 0}
    if len(selected) != 1 or not COMMAND_GATE.is_file():
        fail('command integration requires its native root/UID1001 execution gate')
    # The hosted runner is non-root: go test here would silently skip the
    # issuer. Execute the source's owned Linux PG18/UID0+1001 gate instead.
    command = ['bash', str(COMMAND_GATE)]
    print('+ ' + ' '.join(command), flush=True)
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(process.stdout, end='', flush=True)
    runs = set(re.findall(r'^\s*=== RUN\s+(\S+)\s*$', process.stdout, re.M))
    passed = set(re.findall(r'^\s*--- PASS: (\S+) ', process.stdout, re.M))
    # The native operator gate owns privileged issuer/UID controls only. These
    # Independently reviewed traffic/quota CLI tests use the disposable CI PG
    # and must run through the ordinary JSON execution verifier, not be waived.
    ordinary = {'TestTrafficLedgerCLIProcess', 'TestTrafficLedgerIndependentCLIRefusesRollbackOnTimeout',
                'TestQuotaRemindersCLIProcess', 'TestQuotaRemindersIndependentCutoverCLI'}
    ordinary_tests = set(selected[0]['tests']) & ordinary
    missing = (set(selected[0]['tests']) - ordinary_tests) - (runs & passed)
    if process.returncode or missing or re.search(r'--- (SKIP|FAIL):', process.stdout):
        fail(f'native command gate exited {process.returncode}; integration tests not run and passed: {sorted(missing)}')
    counts = {'top_level_passed': sum('/' not in test for test in passed),
              'subtests_passed': sum('/' in test for test in passed), 'skipped': 0}
    if ordinary_tests:
        ordinary_row = {**selected[0], 'tests': sorted(ordinary_tests)}
        extra = run_group(COMMANDS, [ordinary_row])
        for key in counts:
            counts[key] += extra[key]
    print('Native command execution: ' + json.dumps({'packages': COMMANDS, **counts}), flush=True)
    return {'packages': COMMANDS, **counts}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['domain', 'remaining'], required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    check_environment()
    entries = discover()
    manifest = hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()
    if args.phase == 'domain':
        if args.receipt.exists():
            fail('refusing to reuse an earlier integration receipt')
        result = run_group(DOMAIN, entries)
        with args.receipt.open('x') as file:
            json.dump({'manifest_sha256': manifest, 'domain': result}, file)
    else:
        receipt = json.loads(args.receipt.read_text())
        if receipt.get('manifest_sha256') != manifest or receipt.get('domain', {}).get('packages') != DOMAIN:
            fail('missing or changed successful domain proof before module/migration tests')
        receipt['commands'] = run_commands(entries)
        receipt['modules'] = run_group(MODULES, entries)
        # Full db/nativeproto suites, including compatibility, production-scale
        # and runtime-role cases. They destroy public and must run last.
        receipt['migrations'] = run_group(MIGRATIONS, entries)
        executed = [path for group in ('domain', 'commands', 'modules', 'migrations') for path in receipt[group]['packages']]
        if set(executed) != {row['path'] for row in entries} or len(executed) != len(entries):
            fail('discovered and executed integration packages differ')
        args.receipt.write_text(json.dumps(receipt, indent=2) + '\n')
        print(f'PostgreSQL integration complete: {len(executed)} packages, no skipped tests', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f'::error::{error}', file=sys.stderr)
        sys.exit(1)
