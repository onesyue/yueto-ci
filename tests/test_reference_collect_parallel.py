#!/usr/bin/env python3
"""The reference collect must overlap independent parts and keep their order."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "ops_shards_parallel", ROOT / "scripts" / "pytest-shards.py")
assert SPEC and SPEC.loader
SHARDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARDS)


class ReferenceCollectParallelTest(unittest.TestCase):
    def test_bounded_map_overlaps_and_preserves_order(self):
        started = []
        release = threading.Event()

        def work(name):
            started.append(name)
            if len(started) < 2:
                self.assertTrue(release.wait(2), "the second part never started")
            else:
                release.set()
            time.sleep(0.05)
            return name

        began = time.monotonic()
        self.assertEqual(SHARDS.map_bounded([lambda: work("a"), lambda: work("b")], 2), ["a", "b"])
        self.assertLess(time.monotonic() - began, 0.2)
        self.assertEqual(SHARDS.map_bounded([lambda: "only"], 4), ["only"])
        with self.assertRaises(ValueError):
            SHARDS.map_bounded([], 0)


class ActualReferenceCollectorTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="reference collector spaces ")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.source = self.base / "source"
        self.output = self.base / "reference evidence"
        self.observations = self.base / "observed imports"
        self.observations.mkdir()
        (self.source / "tests").mkdir(parents=True)
        (self.source / "scripts").mkdir()
        (self.source / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
        (self.source / "pytest.ini").write_text(
            "[pytest]\ntestpaths = tests\npython_files = test_*.py\n"
            "python_functions = test_*\nasyncio_mode = auto\n")
        (self.source / "scripts/run-pytest-parallel.sh").write_text(
            "#!/bin/sh\nexec python3 -m pytest -q\n")
        for name in ("a", "b"):
            (self.source / "tests" / f"test_{name}.py").write_text(
                "import json, os, time\nfrom pathlib import Path\n"
                "import pytest, yueto_lens_report\n"
                f"name = {name!r}\n"
                "observations = Path(os.environ['REFERENCE_OBSERVATIONS'])\n"
                "(observations / (name + '.json')).write_text(json.dumps({\n"
                "    'pid': os.getpid(), 'plugin': yueto_lens_report.__file__,\n"
                "    'invocation': os.environ['LENS_INVOCATION_ID']}))\n"
                "if os.environ.get('REFERENCE_BARRIER') == '1':\n"
                "    deadline = time.monotonic() + 8\n"
                "    while len(list(observations.glob('*.json'))) != 2:\n"
                "        if time.monotonic() >= deadline:\n"
                "            raise RuntimeError('collectors did not overlap')\n"
                "        time.sleep(0.01)\n"
                "if os.environ.get('REFERENCE_FAILURE') == name:\n"
                "    raise RuntimeError('actual collection failure')\n"
                "if os.environ.get('REFERENCE_SKIP') == name:\n"
                "    pytest.skip('fixture collection skip', allow_module_level=True)\n"
                f"def test_{name}():\n"
                "    raise AssertionError('collect-only must not execute the test')\n")
        self.env = os.environ | {
            "PYTHONDONTWRITEBYTECODE": "1", "TZ": "UTC", "PYTEST_ADDOPTS": "--durations=25",
            "PYTHONPATH": "", "GITHUB_REPOSITORY": "onesyue/yueto-ci",
            "GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": "2", "GITHUB_JOB": "reference",
            "RUNNER_OS": "Linux", "RUNNER_ARCH": "X64", "ImageVersion": "fixture-image",
            "GITHUB_SHA": subprocess.check_output(
                ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
            "REFERENCE_OBSERVATIONS": str(self.observations),
        }
        for key in ("LENS_REPORT", "LENS_REPORT_OWNER", "LENS_INVOCATION_ID",
                    "PYTEST_PLUGINS", "PYTEST_DISABLE_PLUGIN_AUTOLOAD"):
            self.env.pop(key, None)
        for args in (("init", "-q"), ("add", "."),
                     ("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                      "-c", "commit.gpgsign=false", "commit", "-qm", "collector fixture")):
            subprocess.run(["git", "-C", str(self.source), *args], env=self.env,
                           check=True, capture_output=True)

    def collect(self, scenario="normal", **extra):
        driver = """
import importlib.util, json, os, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location('actual_collector', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
source, output, site = map(Path, sys.argv[2:5])
context = dict(policy_revision=os.environ['GITHUB_SHA'], board_revision='b' * 40,
               run_id='42', run_attempt='2', runner_os='Linux', runner_arch='X64',
               runner_image='fixture-image')
expected = module.plan(source, context, 2, [])
runner = module.runner_context(context, os.environ)
if sys.argv[5] == 'duplicate':
    expected['assignments'][1]['modules'] = expected['assignments'][0]['modules']
if sys.argv[5] == 'runner':
    runner['runner_image'] = 'changed-before-collection'
timing = module.load_timing()
timing.install(output, site)
(output / 'expected-plan.json').write_text(json.dumps(expected))
module.os.cpu_count = lambda: 2
raise SystemExit(module.collect_reference_parts(expected, source, output, site, runner, timing))
"""
        return subprocess.run(
            [sys.executable, "-c", driver, str(ROOT / "scripts/pytest-shards.py"),
             str(self.source), str(self.output), str(self.base / "shared site"), scenario],
            cwd=self.source, env=self.env | extra, capture_output=True, text=True,
            timeout=25, check=False)

    def test_actual_parts_load_private_plugins_and_keep_distinct_invocations(self):
        result = self.collect(REFERENCE_BARRIER="1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        joined = json.loads((self.output / "joined.json").read_text())
        expected = json.loads((self.output / "expected-plan.json").read_text())
        self.assertEqual(joined["nodeids"], ["tests/test_a.py::test_a", "tests/test_b.py::test_b"])
        observations = [json.loads(p.read_text()) for p in sorted(self.observations.glob("*.json"))]
        self.assertEqual(len({o["pid"] for o in observations}), 2)
        self.assertEqual(len({o["plugin"] for o in observations}), 2)
        self.assertEqual(len({o["invocation"] for o in observations}), 2)
        invocations = []
        for role in joined["parts"]:
            part = self.output / "parts" / role
            metadata = json.loads((part / "metadata.json").read_text())
            invocations.append(metadata["invocation_id"])
            observation = next(o for o in observations if o["invocation"] == metadata["invocation_id"])
            self.assertTrue(Path(observation["plugin"]).is_relative_to(part))
            self.assertEqual(Path(observation["plugin"]).read_bytes(),
                             (ROOT / "scripts/lens_report.py").read_bytes())
            rows = [json.loads(line) for line in (part / "events.jsonl").read_text().splitlines()]
            session = next(row for row in rows if row["event"] == "session_identity")
            self.assertEqual(session["invocation_id"], metadata["invocation_id"])
            selection = json.loads((part / "selection.json").read_text())
            argv = selection["pytest_argv"]
            self.assertEqual(argv[argv.index("-o") + 1], f"cache_dir={part / 'pytest-cache'}")
            self.assertEqual(selection["pytest_addopts"], "--durations=25")
            assignment = next(a for a in expected["assignments"] if a["id"] == role)
            assignment = assignment | {"collect_only": True}
            inspected = SHARDS.inspect_session(part, expected, assignment)
            self.assertEqual(inspected["invocation_id"], metadata["invocation_id"])
            original = (part / "selection.json").read_bytes()
            for option in ("cache_dir=relative", f"cache_dir={self.base}", "-k"):
                with self.subTest(rejected_cache=option):
                    changed = json.loads(original)
                    changed["pytest_argv"][argv.index("-o") + 1] = option
                    (part / "selection.json").write_text(json.dumps(changed))
                    with self.assertRaisesRegex(ValueError, "unexpected pytest arguments"):
                        SHARDS.inspect_session(part, expected, assignment)
            (part / "selection.json").write_bytes(original)
        self.assertEqual(joined["invocation_id"], invocations[0])
        self.assertEqual(len(set(invocations)), 2)

    def test_actual_collection_failure_does_not_publish_join(self):
        result = self.collect(REFERENCE_FAILURE="b")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("reference part failed", result.stderr)
        self.assertTrue((self.observations / "b.json").is_file())
        exits = [int(p.read_text()) for p in self.output.glob("parts/*/pytest-exit-code.txt")]
        self.assertTrue(any(code not in (0, 5) for code in exits))
        self.assertFalse((self.output / "joined.json").exists())

    def test_actual_duplicate_corpus_is_rejected(self):
        result = self.collect("duplicate")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate node id", result.stderr)
        self.assertEqual(len(list(self.output.glob("parts/*/events.jsonl"))), 2)
        self.assertFalse((self.output / "joined.json").exists())

    def test_actual_collection_skip_is_retained(self):
        result = self.collect(REFERENCE_SKIP="b")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        joined = json.loads((self.output / "joined.json").read_text())
        self.assertEqual(joined["nodeids"], ["tests/test_a.py::test_a"])
        self.assertEqual(joined["collection_skips"],
                         {"tests/test_b.py": "Skipped: fixture collection skip"})

    def test_prepared_runner_mismatch_blocks_collection(self):
        result = self.collect("runner")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("runner identity changed during preparation", result.stderr)
        self.assertTrue(list(self.output.glob("parts/*/metadata.json")))
        self.assertFalse(list(self.output.glob("parts/*/events.jsonl")))
        self.assertFalse((self.output / "joined.json").exists())


if __name__ == "__main__":
    unittest.main()
