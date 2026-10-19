"""validate-yueops runs the yueops node unit suites (2026-10-17 W6.10).

The Mini App (158 cases), console (28) and site (12) `node --test` suites were
never executed by any CI. This pins the central step, its job gate and the
three entry points so a removed or renamed line turns red.
"""
from __future__ import annotations

from pathlib import Path

import re
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]


def _validate_steps() -> list[dict]:
    text = (ROOT / ".github" / "workflows" / "build.yml").read_text()
    job = text.split("\n  validate:\n", 1)[1].split("\n  build:\n", 1)[0]
    result = []
    for match in re.finditer(r"^      - name: (.+)\n((?:(?!^      - |^  [a-z]).*\n)*)", job, re.M):
        body = match.group(2)
        condition = re.search(r"^        if: (.+)$", body, re.M)
        script = re.search(r"^        run: \|\n((?:          .*\n|\n)*)", body, re.M)
        result.append({"name": match.group(1), "if": condition.group(1) if condition else "",
                       "run": textwrap.dedent(script.group(1)) if script else ""})
    assert len(result) >= 20, "validation step scan did not reach its target"
    return result


class YueOpsNodeTestPolicy(unittest.TestCase):
    def test_validate_yueops_runs_all_three_node_suites(self):
        steps = _validate_steps()
        names = [s.get("name", "") for s in steps]
        step = next(s for s in steps if s.get("name") == "Run yueops node unit tests (Mini App, console, site)")
        assert step["if"] == "matrix.validation == 'yueops'"
        run = step["run"]
        for line in ("set -euo pipefail",
                     "npm --prefix telegram-bot/yue/miniapp test",
                     "npm --prefix frontend test",
                     "pnpm --dir site install --frozen-lockfile --ignore-scripts",
                     "pnpm --dir site test"):
            assert line in run, line
        # Dependencies must be installed before the suites run.
        index = names.index(step["name"])
        assert names.index("Validate yueops frontend") < index
        assert names.index("Validate Yue mini app") < index


    def test_validate_job_keeps_the_utc_lens(self):
        workflow = (ROOT / ".github" / "workflows" / "build.yml").read_text()
        job = workflow.split("\n  validate:\n", 1)[1].split("    strategy:", 1)[0]
        assert "    env:\n      TZ: UTC\n" in job


    def test_real_central_step_installs_browser_and_stops_when_installation_fails(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        tmp_path = Path(directory.name)
        import os
        import subprocess
        step = next(s for s in _validate_steps() if s.get("name") == "Run yueops node unit tests (Mini App, console, site)")
        bindir = tmp_path / "bin"
        bindir.mkdir()
        log = tmp_path / "calls"
        for name in ("npm", "pnpm", "corepack", "node", "id", "sudo"):
            path = bindir / name
            path.write_text("#!/bin/sh\n"
                            'printf "%s %s\\n" "${0##*/}" "$*" >> "$CALL_LOG"\n'
                            'case "${0##*/}" in node) echo pnpm@11.27.1;; id) echo 1001;; sudo) exit 1;; esac\n'
                            'case "$*" in *"playwright install"*) exit "${INSTALL_EXIT:-0}";; esac\n')
            path.chmod(0o755)
        env = {**os.environ, "PATH": str(bindir) + ":" + os.environ["PATH"], "CALL_LOG": str(log)}
        for failure in (False, True):
            log.write_text("")
            result = subprocess.run(["bash", "-c", step["run"]], cwd=tmp_path, env={**env, "INSTALL_EXIT": "17" if failure else "0"}, capture_output=True, text=True)
            calls = log.read_text().splitlines()
            install = "pnpm --dir site exec playwright install chromium"
            assert install in calls, calls
            assert calls.index("pnpm --dir site install --frozen-lockfile --ignore-scripts") < calls.index(install)
            if failure:
                assert result.returncode == 17
                assert "pnpm --dir site test" not in calls
            else:
                assert result.returncode == 0, result.stderr
                assert calls.index(install) < calls.index("pnpm --dir site test")


def _native_step():
    return next(step for step in _validate_steps()
                if step['name'] == 'Validate yueops PostgreSQL and systemd native obligations')


def _native_driver():
    return _native_step()['run'].split('<<\'PY\'\n', 1)[1].split('\nPY\n', 1)[0]


def _assert_native_contract(test, workflow):
    test.assertIn('YUEBOARD_MONEY_SCHEMA_FIXTURE: ${{ github.workspace }}/.ci-yueboard/test/fixtures/schema.sql', workflow)
    for required in (
        'test "$(git -C .ci-yueboard rev-parse HEAD)" = "$board_pin"',
        'git -C .ci-yueboard diff --exit-code "$board_pin" -- test/fixtures/schema.sql',
        'test -f "$YUEBOARD_MONEY_SCHEMA_FIXTURE"',
        'test ! -L "$YUEBOARD_MONEY_SCHEMA_FIXTURE"',
        'test "$(id -u)" = 1001',
        '.venv/bin/python "$native_driver" tests/test_board139_schema_acl_native_20261018.py 6 1001',
        'sudo -n env PATH="$PATH" TZ=UTC "$PWD/.venv/bin/python"',
        '"$native_driver" tests/test_node_systemd_pilot_20261018.py 38 0',
        'scripts/run-native-nginx-tests.py',
    ):
        test.assertIn(required, workflow)


class YueOpsNativeObligationPolicy(unittest.TestCase):
    def test_native_step_keeps_reviewed_fixture_and_separate_uid_phases(self):
        workflow = (ROOT / '.github/workflows/build.yml').read_text()
        _assert_native_contract(self, workflow)
        steps = _validate_steps()
        names = [step['name'] for step in steps]
        self.assertEqual(_native_step()['if'], "matrix.validation == 'yueops'")
        self.assertLess(names.index('Validate yueops backend'), names.index(_native_step()['name']))
        self.assertLess(names.index(_native_step()['name']), names.index('Validate yueops frontend'))
        self.assertIn('class RequiredCases(consumer.NativeGate)', _native_driver())

    def test_contract_rejects_missing_fixture_pin_and_root_phase(self):
        workflow = (ROOT / '.github/workflows/build.yml').read_text()
        for removed in (
            'test -f "$YUEBOARD_MONEY_SCHEMA_FIXTURE"',
            'test ! -L "$YUEBOARD_MONEY_SCHEMA_FIXTURE"',
            'test "$(git -C .ci-yueboard rev-parse HEAD)" = "$board_pin"',
            'test "$(id -u)" = 1001',
            '"$native_driver" tests/test_node_systemd_pilot_20261018.py 38 0',
        ):
            with self.subTest(removed=removed), self.assertRaises(AssertionError):
                _assert_native_contract(self, workflow.replace(removed, '', 1))

    def test_real_driver_refuses_wrong_execution_context_before_importing_pytest(self):
        import os
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, '-c', _native_driver(), 'tests/test_fixture.py', '6', str(os.geteuid() + 1)],
            capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('native obligation execution context differs', result.stderr)
        self.assertNotIn('ModuleNotFoundError', result.stderr)

    def test_actual_collection_adapter_refuses_holes_and_deselection(self):
        # The separate Linux receipt uses the unchanged private NativeGate and
        # real pytest. Public policy tests its adapter without private checkout.
        import ast
        import contextlib
        import io
        import json
        from types import SimpleNamespace
        tree = ast.parse(_native_driver())
        node = next(item for item in tree.body if isinstance(item, ast.ClassDef))

        class ConsumerGate:
            def __init__(self, required):
                self.required, self.passed, self.bad = set(required), set(), set()

            def pytest_sessionfinish(self, session, exitstatus):
                if self.required - self.passed or self.bad:
                    session.exitstatus = 1

        context = {'consumer': SimpleNamespace(NativeGate=ConsumerGate),
                   'target': 'tests/test_fixture.py', 'floor': 6,
                   'os': SimpleNamespace(geteuid=lambda: 1001),
                   'sys': SimpleNamespace(platform='linux'), 'json': json}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<native-workflow>', 'exec'), context)  # noqa: S102
        names = ['tests/test_fixture.py::test_case[' + str(i) + ']' for i in range(6)]
        for mode in ('pass', 'short', 'duplicate', 'wrong_module', 'missing_call',
                     'skip', 'failed', 'collect_error', 'collect_skip', 'deselected', 'nonzero'):
            with self.subTest(mode=mode):
                gate = context['RequiredCases']()
                selected = names.copy()
                if mode == 'short':
                    selected.pop()
                if mode == 'duplicate':
                    selected[-1] = selected[0]
                if mode == 'wrong_module':
                    selected[-1] = 'tests/other.py::test_case'
                session = SimpleNamespace(items=[SimpleNamespace(nodeid=n) for n in selected],
                                          exitstatus=2 if mode == 'nonzero' else 0)
                gate.pytest_collection_finish(session)
                gate.passed = set(names[:-1] if mode == 'missing_call' else names)
                if mode in ('skip', 'failed'):
                    gate.bad.add(names[0])
                if mode in ('collect_error', 'collect_skip'):
                    gate.pytest_collectreport(SimpleNamespace(failed=mode == 'collect_error',
                                                              skipped=mode == 'collect_skip'))
                if mode == 'deselected':
                    gate.pytest_deselected([SimpleNamespace(nodeid=names[0])])
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    gate.pytest_sessionfinish(session, session.exitstatus)
                receipt = json.loads(output.getvalue().split('NATIVE_OBLIGATION_RECEIPT ', 1)[1])
                self.assertEqual(receipt['uid'], 1001)
                self.assertEqual(receipt['platform'], 'linux')
                self.assertEqual(session.exitstatus == 0, mode == 'pass')
                self.assertEqual(receipt['exitstatus'], session.exitstatus)
