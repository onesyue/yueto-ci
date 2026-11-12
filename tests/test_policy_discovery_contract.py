"""Keep every policy case reachable by policy-ci's stdlib discovery runner.

policy-ci.yml used to name each test file on its own line. A new file was only
executed once someone also remembered to add that line; PolicyCiRunsEveryTestFileTest
caught the omission, but only because it happened to exist in one of the listed
files. Discovery removes the list; this contract keeps discovery honest:

* the workflow really runs ``python3 scripts/run-policy-tests.py``
  and no longer carries a per-file list that could silently diverge;
* every ``test_*`` case in ``tests/test_*.py`` is reachable by unittest: it lives
  on a ``unittest.TestCase`` subclass, or the module defines ``load_tests`` (the
  dead-man suite wraps plain functions that way);
* discovery actually loads at least the floor of cases, so an import-time
  failure or an empty glob cannot pass as "nothing to run".
"""

from __future__ import annotations

import ast
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_CI = ROOT / ".github" / "workflows" / "policy-ci.yml"
DISCOVER = "python3 scripts/run-policy-tests.py"
# 2026-09-28: 8 files / 150+ cases. Floors, not exact counts.
MIN_FILES = 8
MIN_CASES = 150


def _runner():
    path = ROOT / "scripts" / "run-policy-tests.py"
    spec = importlib.util.spec_from_file_location("run_policy_tests", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("policy runner did not load")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _is_testcase_base(base: ast.expr) -> bool:
    if isinstance(base, ast.Attribute):
        return base.attr == "TestCase"
    return isinstance(base, ast.Name) and base.id == "TestCase"


def undiscovered_cases(directory: Path) -> list[str]:
    errors: list[str] = []
    for path in sorted(directory.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        has_load_tests = any(
            isinstance(node, ast.FunctionDef) and node.name == "load_tests"
            for node in tree.body
        )
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test_") and not has_load_tests:
                    errors.append(f"{path.name}:{node.lineno}: {node.name}")
            elif isinstance(node, ast.ClassDef):
                cases = [
                    child
                    for child in node.body
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and child.name.startswith("test_")
                ]
                if cases and not any(_is_testcase_base(b) for b in node.bases):
                    errors.append(f"{path.name}:{node.lineno}: {node.name}")
    return errors


def count_cases(suite: unittest.TestSuite) -> int:
    return sum(
        count_cases(item) if isinstance(item, unittest.TestSuite) else 1
        for item in suite
    )


class PolicyDiscoveryContractTest(unittest.TestCase):
    def test_policy_ci_runs_discovery_not_a_hand_kept_list(self) -> None:
        workflow = POLICY_CI.read_text(encoding="utf-8")
        self.assertIn(DISCOVER, workflow)
        # A leftover per-file line would mean two sources of truth again.
        self.assertNotRegex(workflow, r"python3 tests/test_[a-z0-9_]+\.py")

    def test_every_case_is_reachable_by_unittest(self) -> None:
        directory = ROOT / "tests"
        self.assertGreaterEqual(len(list(directory.glob("test_*.py"))), MIN_FILES)
        self.assertEqual(undiscovered_cases(directory), [])

    def test_discovery_loads_every_module_and_the_case_floor(self) -> None:
        suite = unittest.defaultTestLoader.discover(
            str(ROOT / "tests"), pattern="test_*.py", top_level_dir=str(ROOT / "tests")
        )
        failed_imports = [
            str(test) for test in _flatten(suite)
            if type(test).__name__ == "_FailedTest"
        ]
        self.assertEqual(failed_imports, [])
        self.assertGreaterEqual(count_cases(suite), MIN_CASES)

    def test_rejects_plain_functions_and_unregistered_classes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path = directory / "test_example.py"
            path.write_text(
                "def test_hidden():\n    pass\n"
                "class HiddenTests:\n    def test_hidden(self):\n        pass\n"
            )
            self.assertEqual(len(undiscovered_cases(directory)), 2)
            path.write_text(
                "import unittest\n"
                "def load_tests(loader, tests, pattern):\n    return tests\n"
                "def test_wrapped():\n    pass\n"
                "class VisibleTests(unittest.TestCase):\n"
                "    def test_visible(self):\n        pass\n"
            )
            self.assertEqual(undiscovered_cases(directory), [])

    def test_rejects_a_workflow_that_went_back_to_a_list(self) -> None:
        workflow = POLICY_CI.read_text(encoding="utf-8")
        mutated = workflow.replace(DISCOVER, "python3 tests/test_build_policy.py")
        self.assertNotIn(DISCOVER, mutated)
        self.assertRegex(mutated, r"python3 tests/test_[a-z0-9_]+\.py")

    def test_runner_discovers_files_instead_of_naming_them(self) -> None:
        script = (ROOT / "scripts" / "run-policy-tests.py").read_text(encoding="utf-8")
        self.assertIn("test_*.py", script)
        self.assertIn("unittest", script)
        self.assertIn("discover", script)
        self.assertNotIn("test_build_policy.py", script)

    def test_parallel_processes_run_every_discovered_module(self) -> None:
        runner = _runner()
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for name in ("a", "b"):
                (directory / f"test_{name}.py").write_text(
                    "import unittest\n"
                    "from pathlib import Path\n"
                    "class T(unittest.TestCase):\n"
                    "    def test_runs(self):\n"
                    f"        Path({str(directory / name)!r}).write_text('ran')\n"
                )
            self.assertEqual(runner.run_policy_tests(directory, cwd=directory, workers=2), 0)
            self.assertEqual((directory / "a").read_text(), "ran")
            self.assertEqual((directory / "b").read_text(), "ran")

    def test_import_error_fails_and_the_sibling_still_runs(self) -> None:
        runner = _runner()
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            marker = directory / "ok"
            (directory / "test_ok.py").write_text(
                "import unittest\n"
                "from pathlib import Path\n"
                "class Ok(unittest.TestCase):\n"
                "    def test_ok(self):\n"
                f"        Path({str(marker)!r}).write_text('ok')\n"
            )
            (directory / "test_broken.py").write_text("raise ImportError('policy import boom')\n")
            self.assertEqual(runner.run_policy_tests(directory, cwd=directory, workers=2), 1)
            self.assertEqual(marker.read_text(), "ok")

    def test_empty_discovery_fails(self) -> None:
        runner = _runner()
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self.assertEqual(runner.run_policy_tests(directory, cwd=directory, workers=2), 1)
            self.assertEqual(runner.discovered_modules(directory), [])


def _flatten(suite: unittest.TestSuite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _flatten(item)
        else:
            yield item


if __name__ == "__main__":
    unittest.main()
