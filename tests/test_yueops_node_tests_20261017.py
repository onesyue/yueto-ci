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


def _validate_steps(text: str | None = None) -> list[dict]:
    if text is None:
        text = (ROOT / ".github" / "workflows" / "build.yml").read_text()
    job = text.split("\n  validate:\n", 1)[1].split("\n  build:\n", 1)[0]
    result = []
    for match in re.finditer(r"^      - name: (.+)\n((?:(?!^      - |^  [a-z]).*\n)*)", job, re.M):
        body = match.group(2)
        condition = re.search(r"^        if: (.+)$", body, re.M)
        directory = re.search(r"^        working-directory: (.+)$", body, re.M)
        optional = re.search(r"^        continue-on-error: (.+)$", body, re.M)
        script = re.search(r"^        run: \|\n((?:          .*\n|\n)*)", body, re.M)
        result.append({"name": match.group(1), "if": condition.group(1) if condition else "",
                       "working-directory": directory.group(1) if directory else "",
                       "continue-on-error": optional.group(1) if optional else "",
                       "run": textwrap.dedent(script.group(1)) if script else ""})
    assert len(result) >= 20, "validation step scan did not reach its target"
    return result


def _console_lint_step(workflow: str) -> dict:
    steps = _validate_steps(workflow)
    names = [step["name"] for step in steps]
    assert names.count("Validate yueops frontend") == 1
    step = steps[names.index("Validate yueops frontend")]
    assert step["if"] == "matrix.validation == 'yueops' && (matrix.ops_role == 'native' || matrix.ops_role == 'legacy')"
    assert step["working-directory"] == "frontend"
    assert not step["continue-on-error"]
    commands = step["run"].splitlines()
    assert commands[:4] == ["set -euo pipefail", "npm ci --ignore-scripts",
                            "npm run lint", "npm run build"]
    assert commands.count("npm run lint") == 1
    assert names.index(step["name"]) < names.index("Run yueops node unit tests (Mini App, console, site)")
    assert names.index(step["name"]) < names.index("Record complete Ops native and source gates")
    return step


class YueOpsConsoleLintPolicy(unittest.TestCase):
    def workflow(self):
        return (ROOT / ".github" / "workflows" / "build.yml").read_text()

    def test_console_lint_is_required_in_the_existing_early_frontend_step(self):
        _console_lint_step(self.workflow())

    def test_actual_workflow_guard_rejects_absent_optional_wrong_consumer_and_order(self):
        workflow = self.workflow()
        start = workflow.index("      - name: Validate yueops frontend\n")
        end = workflow.index("      - name: Validate Yue mini app\n", start)
        body = workflow[start:end]
        changes = {
            "omitted": body.replace("          npm run lint\n", ""),
            "optional": body.replace("npm run lint", "npm run lint --if-present"),
            "wrong directory": body.replace("working-directory: frontend", "working-directory: telegram-bot/yue/miniapp"),
            "wrong consumer": body.replace("npm run lint", "npm --prefix telegram-bot/yue/miniapp run lint"),
            "before install": body.replace("npm ci --ignore-scripts\n          npm run lint", "npm run lint\n          npm ci --ignore-scripts"),
            "after build": body.replace("npm run lint\n          npm run build", "npm run build\n          npm run lint"),
            "ignored failure": body.replace("npm run lint", "npm run lint || true"),
            "optional step": body.replace("        run: |", "        continue-on-error: true\n        run: |"),
            "wrong role": body.replace("matrix.ops_role == 'native'", "matrix.ops_role == 'ordinary'"),
        }
        for name, changed in changes.items():
            with self.subTest(name=name), self.assertRaises(AssertionError):
                _console_lint_step(workflow[:start] + changed + workflow[end:])

    def test_real_console_step_runs_lint_after_install_and_propagates_failure(self):
        import json
        import os
        import subprocess
        import sys
        step = _console_lint_step(self.workflow())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "frontend").mkdir()
            (root / "scripts").mkdir()
            bindir = root / "bin"
            bindir.mkdir()
            log = root / "calls.jsonl"
            npm = bindir / "npm"
            npm.write_text(f"#!{sys.executable}\n" + """import json, os, pathlib, sys
args = sys.argv[1:]
phase = {('ci', '--ignore-scripts'): 'install', ('run', 'lint'): 'lint', ('run', 'build'): 'build'}.get(tuple(args))
if phase is None:
    raise SystemExit(91)
with open(os.environ['CALL_LOG'], 'a') as out:
    out.write(json.dumps({'phase': phase, 'cwd': str(pathlib.Path.cwd()), 'argv': args}) + '\\n')
raise SystemExit(int(os.environ['FAIL_EXIT']) if phase == os.environ['FAIL_PHASE'] else 0)
""")
            npm.chmod(0o755)
            audit = root / "scripts" / "npm-audit-gate.py"
            audit.write_text("""import json, os, pathlib, sys
with open(os.environ['CALL_LOG'], 'a') as out:
    out.write(json.dumps({'phase': 'audit', 'cwd': str(pathlib.Path.cwd()), 'argv': sys.argv[1:]}) + '\\n')
""")
            env = {**os.environ, "PATH": str(bindir) + os.pathsep + os.environ["PATH"],
                   "CALL_LOG": str(log), "GITHUB_WORKSPACE": str(root), "YUE_CI_PYTHON": sys.executable}
            for failure, code, expected in (("", 0, ["install", "lint", "build", "audit"]),
                                            ("install", 23, ["install"]),
                                            ("lint", 37, ["install", "lint"])):
                with self.subTest(failure=failure):
                    log.write_text("")
                    result = subprocess.run(["bash", "-c", step["run"]],
                                            cwd=root / step["working-directory"],
                                            env={**env, "FAIL_PHASE": failure, "FAIL_EXIT": str(code)},
                                            capture_output=True, text=True, timeout=10)
                    calls = [json.loads(line) for line in log.read_text().splitlines()]
                    self.assertEqual(result.returncode, code, result.stderr)
                    self.assertEqual([row["phase"] for row in calls], expected)
                    self.assertTrue(all(Path(row["cwd"]) == (root / "frontend").resolve() for row in calls))
                    if not failure:
                        self.assertEqual(calls[-1]["argv"], [str(root / "frontend")])


class YueOpsNodeTestPolicy(unittest.TestCase):
    def test_validate_yueops_runs_all_three_node_suites(self):
        steps = _validate_steps()
        names = [s.get("name", "") for s in steps]
        step = next(s for s in steps if s.get("name") == "Run yueops node unit tests (Mini App, console, site)")
        assert step["if"] == "matrix.validation == 'yueops' && (matrix.ops_role == 'native' || matrix.ops_role == 'legacy')"
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


def execute_fixture_native(directory, output, targets, *, mode="pass"):
    """Real YAML driver + pytest + source NativeGate; only OS/UID and cases are controlled."""
    import json
    import os
    import shutil
    import subprocess
    import sys
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "scripts").mkdir(exist_ok=True)
    actual = os.environ.get("W122_OPS_ENTRY")
    gate = directory / "scripts/run-native-nginx-tests.py"
    if actual:
        shutil.copyfile(Path(actual).with_name("run-native-nginx-tests.py"), gate)
    else:
        gate.write_text("""class NativeGate:
    def __init__(self, required):
        self.required,self.passed,self.bad=set(required),set(),set()
    def pytest_runtest_logreport(self, report):
        if report.failed or report.skipped:self.bad.add(report.nodeid)
        if report.when=='call' and report.passed:self.passed.add(report.nodeid)
    def pytest_sessionfinish(self, session, exitstatus):
        if self.required-self.passed or self.bad:session.exitstatus=1
""")
    driver = directory / "driver.py"
    driver.write_text(_native_driver())
    results = []
    for target, (floor, uid) in targets.items():
        module = directory / target
        module.parent.mkdir(exist_ok=True)
        if "board139_schema_acl" in target:
            body = """import pytest
@pytest.mark.parametrize('role',['PUBLIC','app_yue_bot','app_checkin','yueboard_runtime'])
def test_actual_audit_refuses_nonowner_execute(role): pass
def test_actual_audit_refuses_grant_option_and_foreign_owner(): pass
def test_actual_bootstrap_adopts_139_trigger_owner_and_empty_acl(): pass
"""
        else:
            body = "import pytest\n" + "\n".join(
                f"def test_case_{i}(): pass" for i in range(floor)) + "\n"
        if mode != "pass":
            statement = {"skip": "pytest.skip('controlled missing native tool')",
                         "xfail": "pytest.xfail('controlled expected failure')",
                         "failure": "assert False"}[mode]
            body = body.replace("pass", statement, 1)
        module.write_text(body)
        path = output / (Path(target).stem + ".json")
        bootstrap = (
            "import sys,pytest;from unittest.mock import patch;"
            f"sys.argv={[str(driver), target, str(floor), str(uid), str(path)]!r}\n"
            f"with patch('sys.platform','linux'),patch('os.geteuid',return_value={uid}):\n"
            f" exec(compile(open({str(driver)!r}).read(),{str(driver)!r},'exec'))\n"
        )
        env = dict(os.environ, PYTEST_ADDOPTS="", PYTHONPATH="", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
        for key in ("LENS_REPORT", "LENS_REPORT_OWNER", "LENS_INVOCATION_ID", "PYTEST_PLUGINS"):
            env.pop(key, None)
        ran = subprocess.run([sys.executable, "-B", "-c", bootstrap], cwd=directory,
                             env=env, capture_output=True, text=True, timeout=20, check=False)
        if not path.is_file():
            raise AssertionError(ran.stdout + ran.stderr)
        results.append((ran, json.loads(path.read_text())))
    return results


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
        'sudo -n env PATH="$PATH" TZ=UTC YUEBOARD_REPO_PATH="$PWD/.ci-yueboard"',
        'tests/test_schema_contract_receipt_20261020.py 30 0',
        '"$native_driver" tests/native_loadshed_installer_20261030.py 7 0',
    ):
        test.assertIn(required, workflow)


class YueOpsNativeObligationPolicy(unittest.TestCase):
    def test_native_step_keeps_reviewed_fixture_and_separate_uid_phases(self):
        workflow = (ROOT / '.github/workflows/build.yml').read_text()
        _assert_native_contract(self, workflow)
        steps = _validate_steps()
        names = [step['name'] for step in steps]
        self.assertEqual(_native_step()['if'], "matrix.validation == 'yueops' && (matrix.ops_role == 'native' || matrix.ops_role == 'legacy')")
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
            '"$native_driver" tests/native_loadshed_installer_20261030.py 7 0',
        ):
            with self.subTest(removed=removed), self.assertRaises(AssertionError):
                _assert_native_contract(self, workflow.replace(removed, '', 1))

    def test_receipt_contract_rejects_removed_call_floor_uid_or_board_env(self):
        workflow = (ROOT / '.github/workflows/build.yml').read_text()
        target = 'tests/test_schema_contract_receipt_20261020.py'
        for before, after in (
            (target + ' 30 0', ''),
            (target + ' 30 0', target + ' 29 0'),
            (target + ' 30 0', target + ' 30 1001'),
            ('YUEBOARD_REPO_PATH="$PWD/.ci-yueboard"', ''),
            ('YUEBOARD_REPO_PATH="$PWD/.ci-yueboard"', 'YUEBOARD_REPO_PATH=/tmp/unbound'),
        ):
            with self.subTest(after=after), self.assertRaises(AssertionError):
                _assert_native_contract(self, workflow.replace(before, after, 1))

    def test_actual_native_step_dispatches_receipt_root_context_and_preserves_failure(self):
        import json
        import os
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            bindir = root / 'bin'
            bindir.mkdir()
            fixture = root / '.ci-yueboard/test/fixtures/schema.sql'
            fixture.parent.mkdir(parents=True)
            fixture.write_text('-- isolated fixture\n')
            for name, body in {
                'jq': 'echo fixture-pin',
                'git': 'case "$*" in *rev-parse*) echo fixture-pin;; esac',
                'id': 'echo 1001',
                'sudo': 'test "$1" = -n; shift; exec "$@"',
            }.items():
                path = bindir / name
                path.write_text('#!/bin/sh\n' + body + '\n')
                path.chmod(0o755)
            python = root / '.venv/bin/python'
            python.parent.mkdir(parents=True)
            python.write_text('#!' + sys.executable + '\n' + textwrap.dedent("""
                import json, os, sys
                from pathlib import Path
                with open(os.environ['CALL_LOG'], 'a') as log:
                    log.write(json.dumps({'argv': sys.argv[1:],
                        'board': os.environ.get('YUEBOARD_REPO_PATH'),
                        'tz': os.environ.get('TZ')}) + '\\n')
                if len(sys.argv)>2 and 'test_schema_contract_receipt' in sys.argv[2]:
                    assert Path(os.environ['YUEBOARD_REPO_PATH']).is_dir()
                    raise SystemExit(int(os.environ['RECEIPT_RC']))
                """))
            python.chmod(0o755)
            log = root / 'calls.jsonl'
            env = {**os.environ, 'PATH': str(bindir) + ':' + os.environ['PATH'],
                   'CALL_LOG': str(log), 'RUNNER_TEMP': str(root),
                   'YUEBOARD_MONEY_SCHEMA_FIXTURE': str(fixture)}
            env.pop('YUEBOARD_REPO_PATH', None)
            for code in (0, 19):
                with self.subTest(code=code):
                    log.write_text('')
                    result = subprocess.run(['bash', '-c', _native_step()['run']],
                        cwd=root, env={**env, 'RECEIPT_RC': str(code)},
                        capture_output=True, text=True, timeout=20, check=False)
                    self.assertEqual(result.returncode, code, result.stderr)
                    rows = [json.loads(line) for line in log.read_text().splitlines()]
                    self.assertEqual(len(rows), 5)
                    self.assertEqual(rows[3]['argv'][1:4],
                        ['tests/native_loadshed_installer_20261030.py', '7', '0'])
                    self.assertEqual(rows[3]['tz'], 'UTC')
                    self.assertIn('native-start', rows[0]['argv'])
                    self.assertEqual(rows[-1]['argv'][1:],
                        ['tests/test_schema_contract_receipt_20261020.py', '30', '0',
                         str(root / 'ops-shard-evidence/test_schema_contract_receipt_20261020.json')])
                    self.assertEqual(rows[-1]['board'], str(root / '.ci-yueboard'))
                    self.assertEqual(rows[-1]['tz'], 'UTC')
                    self.assertFalse(list(root.glob('yueops-native.*.py')))

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


class PersistedNativeReceipts(unittest.TestCase):
    def test_actual_driver_persists_success_and_nonpassing_terminal(self):
        import json
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for mode in ("pass", "failure", "skip", "xfail"):
                output = root / (mode + "-receipts")
                output.mkdir()
                binding = {"fixture": "same invocation"}
                (output / "native-context.json").write_text(json.dumps(binding))
                ran, receipt = execute_fixture_native(
                    root / mode, output, {"tests/test_native_fixture.py": (6, 1001)},
                    mode=mode)[0]
                self.assertEqual(ran.returncode == 0, mode == "pass", ran.stdout + ran.stderr)
                self.assertEqual(receipt["process_exitstatus"], ran.returncode)
                self.assertEqual(receipt["binding"], binding)
                self.assertEqual(receipt["floor"], 6)
                self.assertEqual(len(receipt["required"]), 6)
                self.assertEqual(bool(receipt["failed_or_skipped"]), mode != "pass")


class LoadShedNativeRegistration(unittest.TestCase):
    def setUp(self):
        import importlib.util
        import json
        spec = importlib.util.spec_from_file_location("loadshed_policy", ROOT / "scripts/pytest-shards.py")
        assert spec is not None and spec.loader is not None
        self.consumer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.consumer)
        self.baseline = json.loads((ROOT / "ops-pytest-skip-baseline.json").read_text())
        self.target = "tests/native_loadshed_installer_20261030.py"

    def test_baseline_pin_inventory_and_workflow_agree(self):
        original, inputs = self.consumer.required_native_inputs(self.baseline)
        self.assertEqual(inputs, self.consumer.NATIVE_INPUTS)
        self.assertEqual(set(inputs), {self.target})
        self.assertEqual(self.consumer.NATIVE_TARGETS[self.target], (7, 0))
        predecessor, _ = self.consumer.reviewed_retired_host_transition(self.baseline)
        self.assertEqual(original["cases"], predecessor["cases"])
        self.consumer.reviewed_estate_input_transition(self.baseline)
        common = original["common_inputs"] | inputs
        files = {p: ("100644", blob) for p, blob in common.items()}
        self.consumer.admit_shared_inputs(self.baseline, common, files)
        for changed in (original["common_inputs"], common | {self.target: "f" * 40}):
            with self.subTest(changed=changed.get(self.target)), self.assertRaisesRegex(
                    ValueError, "missing or changed required native input"):
                self.consumer.admit_shared_inputs(self.baseline, changed)
        with self.assertRaisesRegex(ValueError, "mode or tree changed"):
            self.consumer.admit_shared_inputs(
                self.baseline, common, files | {self.target: ("120000", inputs[self.target])})

    def test_pin_and_historical_seal_mutations_fail(self):
        import copy
        for mode in ("pin", "history", "extra"):
            changed = copy.deepcopy(self.baseline)
            if mode == "pin":
                changed["required_native_inputs"]["inputs"][self.target] = "f" * 40
            elif mode == "history":
                changed["events_sha256"] = "f" * 64
            else:
                changed["required_native_inputs"]["inputs"]["tests/extra.py"] = "f" * 40
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.consumer.required_native_inputs(changed)

    def test_loadshed_receipt_is_required_and_cannot_reduce_floor_or_change_uid(self):
        import json
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "native-context.json").write_text("{}")
            for target, (floor, uid) in self.consumer.NATIVE_TARGETS.items():
                names = sorted(f"{target}::test_case_{i}" for i in range(floor))
                row = dict(target=target, floor=floor, uid=uid, platform="linux", binding={},
                           required=names, passed=names, collection_bad=False,
                           failed_or_skipped=[], exitstatus=0, process_exitstatus=0)
                (output / (Path(target).stem + ".json")).write_text(json.dumps(row))
            path = output / (Path(self.target).stem + ".json")
            original = path.read_text()
            with patch.object(self.consumer, "native_execution_context", return_value={}):
                self.consumer.native_receipts({}, output)
                for mode in ("missing", "floor", "uid", "incomplete"):
                    row = json.loads(original)
                    if mode == "missing":
                        path.unlink()
                    else:
                        if mode == "floor": row["floor"] = 6
                        elif mode == "uid": row["uid"] = 1001
                        else: row["passed"] = row["passed"][:-1]
                        path.write_text(json.dumps(row))
                    with self.subTest(mode=mode), self.assertRaises(ValueError):
                        self.consumer.native_receipts({}, output)
                    path.write_text(original)
