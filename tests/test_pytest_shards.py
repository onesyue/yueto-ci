"""Real Git and pytest controls for the disconnected Ops shard primitives."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("pytest_shards", ROOT / "scripts/pytest-shards.py")
SHARDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARDS)


class ShardPrimitives(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="pytest shards ")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.source = self.base / "source"
        self.policy = self.base / "policy"
        self.site = self.base / "site"
        self.source.mkdir()
        (self.source / "scripts").mkdir()
        (self.source / "tests").mkdir()
        (self.source / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
        (self.source / "pytest.ini").write_text(
            "[pytest]\ntestpaths = tests\npython_files = test_*.py\n"
            "python_functions = test_*\nasyncio_mode = auto\n")
        (self.source / "scripts/run-pytest-parallel.sh").write_text(
            "#!/bin/sh\nexec python3 -m pytest -q\n")
        (self.source / "tests/test_a.py").write_text(
            "import pytest\n"
            "def test_pass(): pass\n"
            "@pytest.mark.skip(reason='existing fixture skip')\n"
            "def test_skip(): pass\n"
            "@pytest.mark.xfail(reason='existing fixture xfail')\n"
            "def test_xfail(): assert False\n")
        (self.source / "tests/test_b é.py").write_text(
            "import subprocess,sys\n"
            "def test_subtests(subtests):\n"
            "    for i in (1,2):\n"
            "        with subtests.test(i=i): assert i > 0\n"
            "def test_nested(tmp_path):\n"
            "    child=tmp_path/'test_nested_child.py'\n"
            "    child.write_text('def test_child(): pass\\n')\n"
            "    assert subprocess.run([sys.executable,'-m','pytest','-q',str(child)]).returncode==0\n")
        (self.source / "tests/test_c.py").write_text(
            "import os,pytest\n"
            "@pytest.fixture\n"
            "def context():\n"
            "    if os.environ.get('CASE_FAILURE')=='setup': pytest.fail('setup')\n"
            "    yield\n"
            "    if os.environ.get('CASE_FAILURE')=='teardown': pytest.fail('teardown')\n"
            "def test_case(context):\n"
            "    if os.environ.get('CASE_FAILURE')=='call': pytest.fail('call')\n"
            "    if os.environ.get('CASE_FAILURE')=='abort': os._exit(7)\n")
        (self.source / "tests/test_skip_module.py").write_text(
            "import pytest\npytest.skip('existing collection skip', allow_module_level=True)\n")
        (self.policy / "scripts").mkdir(parents=True)
        for name in ("lens_report.py", "lens-report-source.json", "pytest-timing.py", "pytest-shards.py"):
            shutil.copyfile(ROOT / "scripts" / name, self.policy / "scripts" / name)
        self.env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", TZ="UTC",
                        PYTEST_ADDOPTS="", PYTHONPATH=str(self.site),
                        GITHUB_REPOSITORY="onesyue/yueto-ci", GITHUB_RUN_ID="42",
                        GITHUB_RUN_ATTEMPT="1", RUNNER_OS="Linux", RUNNER_ARCH="X64",
                        ImageVersion="fixture-image")
        for key in ("LENS_REPORT", "LENS_REPORT_OWNER", "LENS_INVOCATION_ID", "PYTEST_PLUGINS"):
            self.env.pop(key, None)
        for repo in (self.source, self.policy):
            self.git(repo, "init", "-q")
            self.git(repo, "add", ".")
            self.commit(repo)
        self.env["GITHUB_SHA"] = self.git(self.policy, "rev-parse", "HEAD").stdout.strip()
        self.context = {
            "policy_revision": self.env["GITHUB_SHA"], "board_revision": "b" * 40,
            "run_id": "42", "run_attempt": "1", "runner_os": "Linux",
            "runner_arch": "X64", "runner_image": "fixture-image",
        }
        self.plan = SHARDS.plan(self.source, self.context, 2, ["tests/test_c.py"])
        self.serial = next(a for a in self.plan["assignments"] if a["id"] == "serial")
        self.ordinal = 0

    def git(self, repo, *args):
        return subprocess.run(["git", "-C", str(repo), *args], env=self.env,
                              capture_output=True, text=True, check=True)

    def commit(self, repo):
        self.git(repo, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "-qm", "source fixture")

    def run_session(self, assignment=None, collect_only=False, **extra):
        """Materialize a real producer envelope around the actual pytest command."""
        self.ordinal += 1
        output = self.base / f"evidence-{self.ordinal}"
        env = self.env | extra
        env["GITHUB_JOB"] = "reference" if assignment is None else "ordinary-shards"
        command = [sys.executable, str(self.policy / "scripts/pytest-timing.py"),
                   "install", "--output", str(output), "--site", str(self.site)]
        installed = subprocess.run(command, cwd=self.source, env=env,
                                   capture_output=True, text=True, check=True, timeout=15)
        env["LENS_REPORT"] = str(output / "events.jsonl")
        env["LENS_INVOCATION_ID"] = installed.stdout.strip()
        modules = ["tests"] if assignment is None else assignment["modules"]
        argv = [sys.executable, "-m", "pytest",
                *( ["--collect-only"] if assignment is None or collect_only else []), "-q", *modules,
                "--junitxml", str(output / "pytest.xml")]
        selection = {
            "plan_sha256": self.plan["plan_sha256"],
            "assignment_id": "reference" if assignment is None else assignment["id"],
            "modules": modules, "pytest_argv": argv, "pytest_addopts": env["PYTEST_ADDOPTS"],
        }
        (output / "selection.json").write_text(json.dumps(selection))
        (output / "pytest-start-unix-ns.txt").write_text(str(time.time_ns()))
        result = subprocess.run(argv, cwd=self.source, env=env, capture_output=True,
                                text=True, timeout=25, check=False)
        (output / "pytest-finish-unix-ns.txt").write_text(str(time.time_ns()))
        (output / "pytest-exit-code.txt").write_text(str(result.returncode))
        (output / "pytest.log").write_text(result.stdout + result.stderr)
        return output, result

    def bundle(self):
        reference, result = self.run_session()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        directories = []
        for assignment in self.plan["assignments"]:
            output, result = self.run_session(assignment)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            directories.append(output)
        return reference, directories

    def reject(self, reference, directories, pattern=None):
        with self.assertRaises(ValueError) as error:
            SHARDS.aggregate(self.plan, reference, directories)
        if pattern:
            self.assertIn(pattern, str(error.exception))

    def mutate_json(self, directory, name, mutation):
        path = directory / name
        original = path.read_bytes()
        value = json.loads(original)
        mutation(value)
        path.write_text(json.dumps(value))
        self.addCleanup(path.write_bytes, original)
        return original

    def test_deterministic_plan_tracks_whole_modules_and_serial_ownership(self):
        self.assertEqual(self.plan, SHARDS.plan(self.source, self.context, 2, ["tests/test_c.py"]))
        modules = [p for a in self.plan["assignments"] for p in a["modules"]]
        self.assertEqual(sorted(modules), sorted(self.plan["modules"]))
        self.assertIn("tests/test_b é.py", modules)
        self.assertEqual(self.serial["modules"], ["tests/test_c.py"])
        self.assertEqual(SHARDS.validate_plan(self.plan), self.plan)

    def test_plan_rejects_wrong_root_dirty_untracked_and_configuration(self):
        with self.assertRaises(ValueError):
            SHARDS.plan(self.source / "tests", self.context, 2, [])
        path = self.source / "tests/test_a.py"
        original = path.read_bytes()
        path.write_text("dirty\n")
        with self.assertRaises(ValueError):
            SHARDS.plan(self.source, self.context, 2, [])
        path.write_bytes(original)
        untracked = self.source / "tests/test_extra.py"
        untracked.write_text("def test_extra(): pass\n")
        with self.assertRaises(ValueError):
            SHARDS.plan(self.source, self.context, 2, [])
        untracked.unlink()
        # An ignored conftest still executes during collection.
        self.git(self.source, "config", "core.excludesFile", str(self.base / "excludes"))
        (self.base / "excludes").write_text("conftest.py\n")
        ignored = self.source / "tests/conftest.py"
        ignored.write_text("raise RuntimeError('untracked collection hook')\n")
        with self.assertRaisesRegex(ValueError, "test Python input"):
            SHARDS.plan(self.source, self.context, 2, [])
        ignored.unlink()
        config = self.source / "pytest.ini"
        config.write_text(config.read_text() + "addopts = --ignore=tests/test_a.py\n")
        self.git(self.source, "add", "pytest.ini")
        self.commit(self.source)
        with self.assertRaisesRegex(ValueError, "unsupported"):
            SHARDS.plan(self.source, self.context, 2, [])

    def test_invalid_capacity_serial_assignment_empty_and_symlink_are_rejected(self):
        for count in (0, -1, True, 99):
            with self.subTest(count=count), self.assertRaises(ValueError):
                SHARDS.plan(self.source, self.context, count, [])
        for serial in (["../escape.py"], ["tests/test_c.py"] * 2):
            with self.subTest(serial=serial), self.assertRaises(ValueError):
                SHARDS.plan(self.source, self.context, 1, serial)
        path = self.source / "tests/test_a.py"
        path.unlink()
        path.symlink_to(self.source / "tests/test_c.py")
        self.git(self.source, "add", "tests/test_a.py")
        self.commit(self.source)
        with self.assertRaisesRegex(ValueError, "symlink"):
            SHARDS.plan(self.source, self.context, 2, [])
        self.git(self.source, "rm", "-r", "tests")
        self.commit(self.source)
        with self.assertRaisesRegex(ValueError, "empty"):
            SHARDS.plan(self.source, self.context, 1, [])

    def test_actual_root_conftest_and_collection_symlinks_require_owned_sources(self):
        hook = self.source / "conftest.py"
        external = self.base / "external-hook.py"
        content = "raise RuntimeError('controlled external collection hook')\n"
        hook.write_text(content)
        for ignored in (False, True):
            if ignored:
                excludes = self.base / "excludes"
                excludes.write_text("conftest.py\n")
                self.git(self.source, "config", "core.excludesFile", str(excludes))
            with self.subTest(ignored=ignored):
                _, result = self.run_session()
                self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
                self.assertIn("controlled external collection hook", result.stderr)
                with self.assertRaisesRegex(ValueError, "untracked root conftest"):
                    SHARDS.plan(self.source, self.context, 2, [])
        # A tracked in-repository collection hook remains a supported input.
        hook.write_text("def pytest_collection_modifyitems(items): assert items\n")
        self.git(self.source, "add", "-f", "conftest.py")
        self.commit(self.source)
        SHARDS.plan(self.source, self.context, 2, [])
        _, result = self.run_session()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        hook.unlink()
        external.write_text(content)
        for relative in ("conftest.py", "tests/conftest.py"):
            with self.subTest(relative=relative):
                path = self.source / relative
                path.symlink_to(external)
                self.git(self.source, "add", "-f", relative)
                self.commit(self.source)
                _, result = self.run_session()
                self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
                self.assertIn("controlled external collection hook", result.stderr)
                with self.assertRaisesRegex(ValueError, "symlink"):
                    SHARDS.plan(self.source, self.context, 2, [])
                self.git(self.source, "rm", relative)
                self.commit(self.source)

    def test_actual_pytest_ini_cuts_off_conftest_above_source_root(self):
        (self.base / "conftest.py").write_text(
            "raise RuntimeError('outside supported collection root')\n")
        self.assertEqual(self.plan, SHARDS.plan(self.source, self.context, 2,
                                              ["tests/test_c.py"]))
        _, result = self.run_session()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("6 tests collected", result.stdout)

    def test_actual_reference_and_shards_keep_skip_nested_subtest_and_readonly_evidence(self):
        reference, directories = self.bundle()
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                  for d in [reference, *directories] for p in d.iterdir()}
        result = SHARDS.aggregate(self.plan, reference, directories)
        self.assertEqual(result["status"], "ORDINARY_CORPUS_COMPLETE")
        self.assertEqual(result["case_count"], 6)
        self.assertFalse(result["release_acceptance"])
        self.assertEqual(result["native_and_skip_policy_acceptance"], "NOT_EVALUATED")
        self.assertEqual(result["modules_without_selected_cases"], ["tests/test_skip_module.py"])
        outcomes = [o["outcome"] for r in result["shards"] for o in r["nonpassing_outcomes"]]
        self.assertEqual(sorted(outcomes), ["skipped", "xfail"])
        self.assertFalse(any("test_child" in n for r in result["shards"] for n in r["nodeids"]))
        after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                 for d in [reference, *directories] for p in d.iterdir()}
        self.assertEqual(before, after)

    def test_missing_duplicate_changed_plan_and_mismatched_identities_reject(self):
        reference, directories = self.bundle()
        self.reject(reference, directories[:-1], "missing")
        self.reject(reference, [directories[0]] * len(directories), "duplicate")
        for key, wrong in (("source_revision", "f" * 40), ("policy_revision", "f" * 40),
                           ("entry_sha256", "0" * 64), ("source_tracked_dirty", True)):
            with self.subTest(key=key):
                old = self.mutate_json(directories[0], "metadata.json",
                                       lambda d, k=key, v=wrong: d.update({k: v}))
                self.reject(reference, directories, "identity")
                (directories[0] / "metadata.json").write_bytes(old)
        for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "ImageVersion"):
            with self.subTest(key=key):
                old = self.mutate_json(directories[0], "metadata.json",
                                       lambda d, k=key: d["identity"].update({k: "other"}))
                self.reject(reference, directories,
                            "invocation digest" if key == "ImageVersion" else "identity")
                (directories[0] / "metadata.json").write_bytes(old)
        plan = copy.deepcopy(self.plan)
        plan["assignments"][0]["modules"] = plan["assignments"][1]["modules"]
        with self.assertRaisesRegex(ValueError, "digest"):
            SHARDS.aggregate(plan, reference, directories)

    def test_actual_sessions_bind_each_image_without_replacing_planning_provenance(self):
        reference, ran = self.run_session(ImageVersion="20261012.334.1")
        self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        directories = []
        for i, assignment in enumerate(self.plan["assignments"]):
            output, ran = self.run_session(assignment, ImageVersion=f"20261018.{340+i}.1")
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
            directories.append(output)
        result = SHARDS.aggregate(self.plan, reference, directories)
        observations = result["runner_observations"]
        self.assertEqual(observations["planning_runner_image"], "fixture-image")
        self.assertTrue(observations["mixed_execution_images"])
        self.assertEqual(observations["roles"]["reference"]["runner_image"], "20261012.334.1")
        self.assertEqual(len(observations["execution_images"]), len(directories) + 1)
        self.assertEqual(observations["performance_comparison"], "NOT_ESTABLISHED")
        self.assertEqual(result["case_count"], 6)
        self.assertFalse(result["release_acceptance"])

    def test_per_role_runtime_context_and_rejection_cannot_be_omitted_or_relabelled(self):
        reference, directories = self.bundle()
        path = directories[0] / "metadata.json"
        original = path.read_bytes()
        for key, value in (("RUNNER_OS", "Windows"), ("RUNNER_ARCH", "ARM64"),
                           ("ImageVersion", ""), ("ImageVersion", "UNKNOWN"),
                           ("ImageVersion", "line\nbreak")):
            with self.subTest(key=key, value=value):
                metadata = json.loads(original)
                metadata["identity"][key] = value
                path.write_text(json.dumps(metadata))
                self.reject(reference, directories, "runner")
        path.write_bytes(original)
        (directories[0] / "rejected.json").write_text('{"status":"REJECTED"}')
        self.reject(reference, directories, "rejected execution")

    def test_lost_case_deselection_and_missing_terminal_reject(self):
        reference, directories = self.bundle()
        first = directories[0]
        for mutation in ("terminal", "truncated", "exit", "selection", "session"):
            with self.subTest(mutation=mutation):
                clone = self.base / mutation
                shutil.copytree(first, clone)
                if mutation == "terminal":
                    rows = (clone / "events.jsonl").read_text().splitlines()
                    (clone / "events.jsonl").write_text("\n".join(rows[:-1]) + "\n")
                elif mutation == "truncated":
                    with (clone / "events.jsonl").open("a") as out:
                        out.write('{"event":')
                elif mutation == "exit":
                    (clone / "pytest-exit-code.txt").write_text("1")
                elif mutation == "session":
                    rows = [json.loads(r) for r in (clone / "events.jsonl").read_text().splitlines()]
                    for row in rows:
                        row.pop("session_id", None)
                    (clone / "events.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
                else:
                    value = json.loads((clone / "selection.json").read_text())
                    value["modules"] = []
                    (clone / "selection.json").write_text(json.dumps(value))
                self.reject(reference, [clone, *directories[1:]])
        output, result = self.run_session(self.plan["assignments"][0], PYTEST_ADDOPTS="-k test_pass")
        self.assertEqual(result.returncode, 0)
        self.reject(reference, [output, *directories[1:]], "selection")
        # A false reference omitting a case cannot be constructed from the successful shards.
        rows = [json.loads(r) for r in (reference / "events.jsonl").read_text().splitlines()]
        corpus = next(r for r in rows if r.get("event") == "collection_corpus")
        corpus["nodeids"].pop()
        corpus["count"] -= 1
        corpus["ordered_nodeids_sha256"] = hashlib.sha256(
            json.dumps(corpus["nodeids"], ensure_ascii=False).encode()).hexdigest()
        (reference / "events.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        self.reject(reference, directories, "union")

    def test_actual_setup_call_teardown_and_abrupt_exit_are_never_success(self):
        reference, _ = self.run_session()
        for kind in ("setup", "call", "teardown", "abort"):
            with self.subTest(kind=kind):
                output, result = self.run_session(self.serial, CASE_FAILURE=kind)
                self.assertNotEqual(result.returncode, 0)
                with self.assertRaises(ValueError):
                    SHARDS.inspect_session(output, self.plan, self.serial)
        self.assertTrue((reference / "events.jsonl").is_file())

    def test_actual_collection_error_is_not_missing_success(self):
        # Commit the failing module, so this is a legitimate but failing source identity.
        (self.source / "tests/test_c.py").write_text("raise RuntimeError('collection failure')\n")
        self.git(self.source, "add", "tests/test_c.py")
        self.commit(self.source)
        self.plan = SHARDS.plan(self.source, self.context, 2, ["tests/test_c.py"])
        output, result = self.run_session(self.plan["assignments"][-1])
        self.assertEqual(result.returncode, 2)
        with self.assertRaises(ValueError):
            SHARDS.inspect_session(output, self.plan, self.plan["assignments"][-1])

    def test_expected_empty_module_keeps_exit_five_and_never_counts_as_a_pass(self):
        self.plan = SHARDS.plan(self.source, self.context, 4, [])
        reference, result = self.run_session()
        self.assertEqual(result.returncode, 0)
        directories, empty = [], None
        for assignment in self.plan["assignments"]:
            output, result = self.run_session(assignment)
            directories.append(output)
            if assignment["modules"] == ["tests/test_skip_module.py"]:
                empty = output
                self.assertEqual(result.returncode, 5)
            else:
                self.assertEqual(result.returncode, 0)
        result = SHARDS.aggregate(self.plan, reference, directories)
        self.assertEqual(result["case_count"], 6)
        recorded = [r for r in result["shards"] if r["empty_assigned_collection"]]
        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0]["pytest_process_exit_code"], 5)
        self.assertEqual(recorded[0]["nodeids"], [])
        self.assertIsNotNone(empty)

    def test_cli_errors_fail_closed_and_workflow_requires_join(self):
        context = self.base / "context.json"
        context.write_text(json.dumps(self.context))
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/pytest-shards.py"), "plan",
             "--source", str(self.source), "--context", str(context), "--shards", "0"],
            capture_output=True, text=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stderr)["status"], "REJECTED")
        workflow = (ROOT / ".github/workflows/build.yml").read_text()
        self.assertIn("pytest-shards.py join", workflow)
        self.assertIn("needs: [plan, validate, validation-evidence]", workflow)


    def test_two_module_reference_parts_union_and_reject_a_drop_or_skip_mismatch(self):
        ordinary = [item for item in self.plan["assignments"] if item["id"].startswith("ordinary-")]
        self.assertGreaterEqual(len(ordinary), 2)
        parts = []
        for assignment in ordinary:
            output, result = self.run_session(assignment, collect_only=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            rows = [json.loads(line) for line in (output / "events.jsonl").read_text().splitlines()]
            corpus = next(row for row in rows if row.get("event") == "collection_corpus")
            parts.append({"nodeids": list(corpus["nodeids"]), "collection_skips": {}})
        joined = SHARDS.join_reference_collections(parts)
        self.assertEqual(set(joined["nodeids"]), set().union(*(part["nodeids"] for part in parts)))
        self.assertGreaterEqual(len({nodeid.split("::", 1)[0] for nodeid in joined["nodeids"]}), 2)
        dropped = [dict(parts[0], nodeids=parts[0]["nodeids"][:-1]), *parts[1:]]
        with self.assertRaisesRegex(ValueError, "missing node id"):
            SHARDS.require_reference_join(dropped, joined["nodeids"], {})
        mismatched = [parts[0], dict(parts[1], collection_skips={"tests/test_a.py": "other"})]
        with self.assertRaisesRegex(ValueError, "collection skip mismatch"):
            SHARDS.require_reference_join(mismatched, joined["nodeids"], {})

if __name__ == "__main__":
    unittest.main()
