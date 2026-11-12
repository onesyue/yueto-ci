"""Execute the real workflow shell, source-entry protocol and artifact join."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import itertools
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

import test_pytest_shards as fixture
import test_pytest_timing as yaml_consumer
import test_yueops_node_tests_20261017 as native_consumer

ROOT = Path(__file__).resolve().parents[1]
TAIL = ["tests/test_telegram_locale_ordering_20260821.py",
        "tests/test_miniapp_http_e2e_20260802.py"]


def assert_only_named_caches_are_optional(case, text):
    validation = text[text.index("  validate:\n"):text.index("  build:\n")]
    cache_action = "actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9"
    for name in ("Restore Go modules", "Restore and refresh Go compiler cache",
                 "Restore verified public UA core archives"):
        pattern = (rf"^      - name: {re.escape(name)}\n"
                   r"(?:(?!^      - |^  [a-z]).*\n)*")
        blocks = list(re.finditer(pattern, validation, re.M))
        case.assertEqual(len(blocks), 1, name)
        block = blocks[0].group()
        case.assertRegex(block, rf"(?m)^        uses: {re.escape(cache_action)}(?: #.*)?$")
        case.assertNotRegex(block, r"(?m)^        run:")
        case.assertEqual(block.count("        continue-on-error: true\n"), 1, name)
        validation = validation.replace(
            block, block.replace("        continue-on-error: true\n", "", 1), 1)
    case.assertNotIn("continue-on-error", validation)


class OptionalCacheContract(unittest.TestCase):
    def test_only_exact_pinned_cache_steps_are_optional(self):
        text = (ROOT / ".github/workflows/build.yml").read_text()
        assert_only_named_caches_are_optional(self, text)
        for name in ("Validate YueBoard UA parsers without network access",
                     "Validate yueops backend",
                     "Validate yueops PostgreSQL and systemd native obligations"):
            with self.subTest(gate=name), self.assertRaises(AssertionError):
                mutated = text.replace(f"      - name: {name}\n",
                                       f"      - name: {name}\n        continue-on-error: true\n", 1)
                assert_only_named_caches_are_optional(self, mutated)
        for old, new in (
            ("  validate:\n", "  validate:\n    continue-on-error: true\n"),
            ("  validation-evidence:\n", "  validation-evidence:\n    continue-on-error: true\n"),
            ("Restore verified public UA core archives", "Unknown optional cache"),
            ("actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9", "actions/cache@main"),
        ):
            with self.subTest(mutation=new), self.assertRaises(AssertionError):
                assert_only_named_caches_are_optional(self, text.replace(old, new))


class OpsShardWorkflow(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.ShardPrimitives()
        self.fixture.sign_commits = True
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.source, self.policy, self.base = (self.fixture.source, self.fixture.policy,
                                               self.fixture.base)
        self.env = self.fixture.env | {"PYTEST_ADDOPTS": "--durations=25"}
        self.board = self.base / "board"
        self.board.mkdir()
        (self.board / "schema.sql").write_text("-- controlled Board fixture\n")
        self.fixture.git(self.board, "init", "-q")
        self.fixture.git(self.board, "add", ".")
        self.fixture.commit(self.board)
        self.board_sha = self.fixture.git(self.board, "rev-parse", "HEAD").stdout.strip()
        (self.policy / "native-node-contract.json").write_text(
            json.dumps({"yueboard_contract_pin": self.board_sha}))
        self.fixture.git(self.policy, "add", "native-node-contract.json")
        self.fixture.commit(self.policy)
        self.env["GITHUB_SHA"] = self.fixture.git(self.policy, "rev-parse", "HEAD").stdout.strip()
        # CI's protocol fixture is local and credential-free. Cross-repository
        # qualification supplies the exact new Ops entry through this override.
        entry = self.source / "scripts/run-pytest-parallel.sh"
        actual = os.environ.get("W122_OPS_ENTRY")
        if actual:
            self.assertTrue(Path(actual).is_file(), "declared actual source entry is missing")
            entry.write_bytes(Path(actual).read_bytes())
        else:
            entry.write_text("#!/bin/sh\nexec .venv/bin/python - \"$@\" <<'PY'\n" + textwrap.dedent("""
                import json,os,sys
                from pathlib import Path
                if sys.argv[1:]==["--describe-ci-selection"]:
                    print(json.dumps({"schema":1,"serial_modules":TAIL}))
                    raise SystemExit(0)
                assert sys.argv[1]=="--ci-selection" and sys.argv[3]=="--selection-receipt"
                value=json.loads(Path(sys.argv[2]).read_text())
                argv=[sys.executable,"-m","pytest",*(["--collect-only"] if value["assignment_id"]=="reference" else []),"-q",*value["modules"],"--junitxml",str(Path(sys.argv[4]).with_name("pytest.xml"))]
                Path(sys.argv[4]).write_text(json.dumps({k:value[k] for k in ("plan_sha256","assignment_id","modules")}|{"pytest_argv":argv,"pytest_addopts":os.environ["PYTEST_ADDOPTS"]}))
                os.execv(sys.executable,argv)
                """).replace("TAIL", repr(TAIL)) + "PY\n")
        for name in TAIL:
            (self.source / name).write_text("def test_serial(): pass\n")
        skip_case = self.source / "tests/test_a.py"
        skip_case.write_text(skip_case.read_text().replace("import pytest", "import os,pytest").replace(
            "reason='existing fixture skip'", "reason=os.environ.get('REVIEWED_REASON','existing fixture skip')"))
        case = self.source / "tests/test_c.py"
        case.write_text(case.read_text().replace(
            "import os,pytest\n", "import os,pytest\n"
            "if os.environ.get('NEW_COLLECTION'): pytest.skip('new missing dependency', allow_module_level=True)\n"
        ).replace("def test_case(context):\n", "def test_case(context):\n"
                  "    if os.environ.get('NEW_SKIP'): pytest.skip('new missing tool')\n"))
        (self.source / "tests/test_skip_module.py").write_text(
            "import os,pytest\npytest.skip(os.environ.get('COLLECTION_REASON',"
            "'existing collection skip'), allow_module_level=True)\n")
        self.fixture.git(self.source, "add", "scripts/run-pytest-parallel.sh", "tests")
        self.fixture.commit(self.source)
        self.source_sha = self.fixture.git(self.source, "rev-parse", "HEAD").stdout.strip()
        (self.source / ".ci-policy").symlink_to(self.policy, target_is_directory=True)
        (self.source / ".ci-yueboard").symlink_to(self.board, target_is_directory=True)
        (self.source / ".venv").symlink_to(Path(sys.prefix), target_is_directory=True)
        # Git mutation controls must not commit or reset the fixture's runtime links.
        exclude = self.source / ".git/info/exclude"
        exclude.write_text(exclude.read_text() + "\n/.ci-policy\n/.ci-yueboard\n/.venv\n")
        self.env["PATH"] = str(self.source / ".venv/bin") + os.pathsep + os.environ["PATH"]
        self.env["YUEBOARD_REPO_PATH"] = str(self.board)
        self.env["YUETO_CI_REPO_PATH"] = str(self.policy)
        spec = importlib.util.spec_from_file_location("actual_ops_shards",
                                                     self.policy / "scripts/pytest-shards.py")
        self.consumer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.consumer)
        self.fixture.env["GITHUB_SHA"] = self.env["GITHUB_SHA"]
        baseline, ran = self.fixture.run_session(
            {"id": "ordinary-000", "modules": list(self.fixture.plan["modules"])})
        self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        self.baseline = self.consumer.generate_skip_baseline(
            self.source, self.source_sha, baseline / "events.jsonl", baseline / "pytest.xml",
            baseline / "events.jsonl", self.source_sha, "fixture original execution")
        (self.policy / "ops-pytest-skip-baseline.json").write_text(json.dumps(self.baseline))
        self.fixture.git(self.policy, "add", "ops-pytest-skip-baseline.json")
        self.fixture.commit(self.policy)
        self.env["GITHUB_SHA"] = self.fixture.git(self.policy, "rev-parse", "HEAD").stdout.strip()
        # The evidence join step reads the source at $GITHUB_WORKSPACE/.admission-source.
        (self.policy / ".admission-source").symlink_to(self.source, target_is_directory=True)
        self.targets = {
            "matrix": [{"service": s, "repo": "onesyue/yueops", "validation": "yueops",
                        "ref": self.source_sha} for s in ("yueops-web", "yue-bot", "checkin-api")],
            "validation_matrix": [{"repo": "onesyue/yueops", "validation": "yueops",
                                   "ref": self.source_sha}], "has_builds": True,
        }
        with patch.dict(os.environ, self.env, clear=True):
            self.admission = self.consumer.expand(self.targets, self.source, self.board_sha,
                                                   "ubuntu-24.04", 4, 4)
        self.artifacts = self.base / "artifacts"
        self.artifacts.mkdir()
        self.prefix = "ops-shard-42-1-"

    def call(self, function, *args):
        with patch.dict(os.environ, self.env, clear=True):
            return function(*args)

    def reviewed_lock_transition(self):
        """A signed master commit that changes a lockfile is admitted."""
        lock = self.source / "frontend/package-lock.json"
        lock.parent.mkdir()
        value = {"packages": {"first": {"version": "1.0"}, "second": {"version": "1.0"}}}
        lock.write_text(json.dumps(value))
        self.fixture.git(self.source, "add", "frontend/package-lock.json")
        self.fixture.commit(self.source)
        value["packages"]["first"]["version"] = "1.1"
        lock.write_text(json.dumps(value))
        self.fixture.git(self.source, "add", "frontend/package-lock.json")
        self.fixture.commit(self.source)
        after = self.fixture.git(self.source, "rev-parse", "HEAD").stdout.strip()
        for row in self.targets["matrix"] + self.targets["validation_matrix"]:
            row["ref"] = after
        self.admission = self.call(self.consumer.expand, self.targets, self.source,
                                   self.board_sha, "ubuntu-24.04", 4, 4)
        self.assertEqual(self.admission["admission_rule"], "signed-default-branch")
        self.assertEqual(self.admission["common_inputs"],
                         self.consumer.shared_inputs(self.source, after))
        return after

    def test_reviewed_lock_reaches_actual_source_native_and_join_without_waiving_evidence(self):
        self.reviewed_lock_transition()
        self.assertNotEqual(self.admission["common_inputs"], self.baseline["common_inputs"])
        joined = self.full_bundle()
        self.assertFalse(joined["skip_admission"]["skips_are_passes"])
        wrong = copy.deepcopy(self.admission)
        wrong["common_inputs"]["frontend/package-lock.json"] = "c" * 40
        del wrong["admission_sha256"]
        self.consumer.seal(wrong, "admission_sha256")
        with self.assertRaisesRegex(ValueError, "shared inputs differ from the signed commit"):
            self.call(self.consumer.check_source, wrong, self.source, self.board)
        (self.artifacts / (self.prefix + "native") / "native.json").unlink()
        with self.assertRaises(ValueError):
            self.join()

    def test_security_successor_reaches_expand_cli_and_reference_envelope(self):
        inputs = {"pyproject.toml": '[tool.transition]\nvalue = "before"\n',
                  "uv.lock": "# before\n", "telegram-bot/yue/requirements.txt": "# before\n"}
        for name, content in inputs.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        self.fixture.git(self.source, "add", *inputs)
        self.fixture.commit(self.source)
        for name in inputs:
            path = self.source / name
            path.write_text(path.read_text().replace("before", "after"))
        self.fixture.git(self.source, "add", *inputs)
        self.fixture.commit(self.source)
        security_source = self.fixture.git(self.source, "rev-parse", "HEAD").stdout.strip()
        for row in self.targets["matrix"] + self.targets["validation_matrix"]:
            row["ref"] = security_source
        targets = self.base / "security-targets.json"
        targets.write_text(json.dumps(self.targets))
        command = [sys.executable, str(self.policy / "scripts/pytest-shards.py"), "expand",
                   "--targets", str(targets), "--source", str(self.source),
                   "--board", self.board_sha, "--runner", "ubuntu-24.04",
                   "--capacity", "4", "--shards", "4"]
        admitted = subprocess.run(command, env=self.env, capture_output=True, text=True)
        self.assertEqual(admitted.returncode, 0, admitted.stdout + admitted.stderr)
        self.admission = json.loads(admitted.stdout)
        self.assertEqual(self.admission["admission_rule"], "signed-default-branch")
        self.assertEqual(self.admission["common_inputs"],
                         self.consumer.shared_inputs(self.source, security_source))
        ran = self.run_role("reference")
        self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        wrong = copy.deepcopy(self.admission)
        wrong["common_inputs"]["uv.lock"] = "c" * 40
        del wrong["admission_sha256"]
        self.consumer.seal(wrong, "admission_sha256")
        with self.assertRaisesRegex(ValueError, "shared inputs differ from the signed commit"):
            self.call(self.consumer.check_source, wrong, self.source, self.board)

    def test_miniapp_successor_reaches_expand_cli_reference_and_resealed_refusals(self):
        miniapp_path = "telegram-bot/yue/miniapp/package-lock.json"
        self.test_security_successor_reaches_expand_cli_and_reference_envelope()
        (self.base / "runner-reference").rename(self.base / "runner-reference-frontend")
        prior_reference = self.artifacts / (self.prefix + "reference")
        if prior_reference.exists():
            prior_reference.rename(self.artifacts / (self.prefix + "frontend-reference"))
        lock = self.source / miniapp_path
        lock.parent.mkdir(parents=True)
        lock.write_text('{"controlled_miniapp": "before"}\n')
        self.fixture.git(self.source, "add", miniapp_path)
        self.fixture.commit(self.source)
        lock.write_text('{"controlled_miniapp": "after"}\n')
        self.fixture.git(self.source, "add", miniapp_path)
        self.fixture.commit(self.source)
        after_source = self.fixture.git(self.source, "rev-parse", "HEAD").stdout.strip()
        for row in self.targets["matrix"] + self.targets["validation_matrix"]:
            row["ref"] = after_source
        targets = self.base / "miniapp-targets.json"
        targets.write_text(json.dumps(self.targets))
        command = [sys.executable, str(self.policy / "scripts/pytest-shards.py"), "expand",
                   "--targets", str(targets), "--source", str(self.source),
                   "--board", self.board_sha, "--runner", "ubuntu-24.04",
                   "--capacity", "4", "--shards", "4"]
        admitted = subprocess.run(command, env=self.env, capture_output=True, text=True)
        self.assertEqual(admitted.returncode, 0, admitted.stdout + admitted.stderr)
        self.admission = json.loads(admitted.stdout)
        after = self.consumer.tree_inputs(self.source, after_source)
        self.assertEqual(self.admission["common_inputs"][miniapp_path], after[miniapp_path][1])
        ran = self.run_role("reference")
        self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        wrong = copy.deepcopy(self.admission)
        wrong["common_inputs"][miniapp_path] = "0" * 40
        del wrong["admission_sha256"]
        self.consumer.seal(wrong, "admission_sha256")
        with self.assertRaisesRegex(ValueError, "shared inputs differ from the signed commit"):
            self.call(self.consumer.check_source, wrong, self.source, self.board)

    def test_reviewed_lock_admits_a_reasoned_new_skip(self):
        self.reviewed_lock_transition()
        result = self.full_bundle({"NEW_SKIP": "1"})
        self.assertEqual(result["status"], "VALIDATION_MATRIX_COMPLETE")
        self.assertFalse(result["skip_admission"]["skips_are_passes"])
        self.assertTrue(any("::test_case" in node
                            for node in result["skip_admission"]["reported_skips"]))

    def test_reviewed_lock_rejects_actual_unreviewed_tree_and_mode_changes(self):
        accepted = self.reviewed_lock_transition()
        lock = self.source / "frontend/package-lock.json"
        for change in ("second-node", "other-blob", "other-input", "added", "missing",
                       "lock-mode", "other-mode", "symlink"):
            with self.subTest(change=change):
                self.fixture.git(self.source, "reset", "--hard", accepted)
                if change == "second-node":
                    value = json.loads(lock.read_text())
                    value["packages"]["second"]["version"] = "1.1"
                    lock.write_text(json.dumps(value))
                elif change == "other-blob":
                    lock.write_text(lock.read_text() + "\n")
                elif change == "other-input":
                    config = self.source / "pytest.ini"
                    config.write_text(config.read_text() + "# unreviewed\n")
                elif change == "added":
                    (self.source / "pyproject.toml").write_text("# new shared input\n")
                elif change == "missing":
                    lock.unlink()
                elif change in ("lock-mode", "other-mode"):
                    (lock if change == "lock-mode" else self.source / "pytest.ini").chmod(0o755)
                else:
                    lock.unlink()
                    lock.symlink_to("../pytest.ini")
                self.fixture.git(self.source, "add", "-A")
                self.fixture.commit(self.source)
                revision = self.fixture.git(self.source, "rev-parse", "HEAD").stdout.strip()
                for row in self.targets["matrix"] + self.targets["validation_matrix"]:
                    row["ref"] = revision
                if change == "symlink":
                    with self.assertRaisesRegex(ValueError, "symlink shared test input"):
                        self.call(self.consumer.expand, self.targets, self.source,
                                  self.board_sha, "ubuntu-24.04", 4, 4)
                else:
                    admitted = self.call(self.consumer.expand, self.targets, self.source,
                                         self.board_sha, "ubuntu-24.04", 4, 4)
                    self.assertEqual(admitted["admission_rule"], "signed-default-branch")
                    self.assertEqual(admitted["common_inputs"],
                                     self.consumer.shared_inputs(self.source, revision))

    def reviewed_python_transition(self):
        """Keep real dependency blobs in both sides of the Git fixture history."""
        paths = ("pyproject.toml", "uv.lock", "telegram-bot/yue/requirements.txt")
        for name in paths:
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# original dependency fixture\n")
        self.fixture.git(self.source, "add", *paths)
        self.fixture.commit(self.source)
        before = self.reviewed_lock_transition()
        policy = self.policy / "ops-pytest-skip-baseline.json"
        baseline = json.loads(policy.read_text())
        old_files = self.consumer.tree_inputs(self.source, before)
        for name in paths:
            (self.source / name).write_text("# reviewed dependency fixture\n")
        self.fixture.git(self.source, "add", *paths)
        self.fixture.commit(self.source)
        after = self.fixture.git(self.source, "rev-parse", "HEAD").stdout.strip()
        for row in self.targets["matrix"] + self.targets["validation_matrix"]:
            row["ref"] = after
        self.admission = self.call(self.consumer.expand, self.targets, self.source,
                                   self.board_sha, "ubuntu-24.04", 4, 4)
        self.assertEqual(self.admission["common_inputs"],
                         self.consumer.shared_inputs(self.source, after))

    def test_reviewed_python_inputs_reach_actual_native_and_join(self):
        self.reviewed_python_transition()
        joined = self.full_bundle()
        self.assertFalse(joined["skip_admission"]["skips_are_passes"])
        self.call(self.consumer.envelope, self.admission)
        for path in ("pyproject.toml", "uv.lock", "telegram-bot/yue/requirements.txt"):
            with self.subTest(path=path), self.assertRaisesRegex(
                    ValueError, "shared inputs differ from the signed commit"):
                wrong = copy.deepcopy(self.admission)
                wrong["common_inputs"][path] = "e" * 40
                del wrong["admission_sha256"]
                self.consumer.seal(wrong, "admission_sha256")
                self.call(self.consumer.check_source, wrong, self.source, self.board)
        (self.artifacts / (self.prefix + "native") / "native.json").unlink()
        with self.assertRaises(ValueError):
            self.join()

    def test_reviewed_python_inputs_admit_a_reasoned_new_skip(self):
        self.reviewed_python_transition()
        result = self.full_bundle({"NEW_SKIP": "1"})
        self.assertEqual(result["status"], "VALIDATION_MATRIX_COMPLETE")
        self.assertFalse(result["skip_admission"]["skips_are_passes"])
        self.assertTrue(any("::test_case" in node
                            for node in result["skip_admission"]["reported_skips"]))

    def run_role(self, role, extra=None):
        runner = self.base / ("runner-" + role)
        (runner / "ops-admission").mkdir(parents=True)
        (runner / "ops-admission/ops-admission.json").write_text(json.dumps(self.admission))
        env = self.env | {"RUNNER_TEMP": str(runner), "OPS_ROLE": role} | (extra or {})
        if role == "native":
            output = runner / "ops-shard-evidence"
            with patch.dict(os.environ, env, clear=True):
                self.consumer.native_start(self.admission, self.source, self.board, output)
            actual = native_consumer.execute_fixture_native(
                runner / "native-fixture", output, self.consumer.NATIVE_TARGETS)
            self.assertTrue(all(r.returncode == 0 for r, _ in actual),
                            "\n".join(r.stdout + r.stderr for r, _ in actual))
        _, script = yaml_consumer.step("Record complete Ops native and source gates"
                                      if role == "native" else "Execute owned Ops pytest selection")
        # Redirect only plugin installation, exactly as the existing timing consumer does.
        if role != "native":
            script = script.rstrip() + f' --site "{self.fixture.site}"\n'
        result = subprocess.run(["bash", "-c", script], cwd=self.source, env=env,
                                capture_output=True, text=True, timeout=30, check=False)
        output = runner / "ops-shard-evidence"
        if output.exists():
            shutil.move(str(output), self.artifacts / (self.prefix + role))
        return result

    def full_bundle(self, extra=None):
        assignments = [a["id"] for a in self.admission["ops_plan"]["assignments"]]
        for role in (*(f"reference-{assignment}" for assignment in assignments), *assignments):
            result = self.run_role(role, extra)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = self.run_role("native")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return self.join()

    def test_reference_parts_union_matches_the_single_collection(self):
        assignments = self.admission["ops_plan"]["assignments"]
        self.assertGreaterEqual(len(assignments), 2)
        parts = []
        for assignment in assignments:
            result = self.run_role("reference-" + assignment["id"])
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads((self.artifacts / (
                self.prefix + "reference-" + assignment["id"]) / "joined.json").read_text())
            self.assertEqual(payload["parts"], [assignment["id"]])
            parts.append({"assignment_id": assignment["id"], "nodeids": payload["nodeids"],
                          "collection_skips": payload["collection_skips"]})
        oracle = self.run_role("reference")
        self.assertEqual(oracle.returncode, 0, oracle.stdout + oracle.stderr)
        single = json.loads((self.artifacts / (self.prefix + "reference") / "joined.json").read_text())
        joined = self.consumer.join_reference_collections(parts)
        self.assertGreater(len(joined["nodeids"]), 0)
        self.assertEqual(set(joined["nodeids"]), set(single["nodeids"]))
        self.assertEqual(len(joined["nodeids"]), len(set(joined["nodeids"])))
        self.assertEqual(len(joined["nodeids"]), len(single["nodeids"]))
        self.assertEqual(joined["collection_skips"], single["collection_skips"])
        self.assertNotIn("reference", self.consumer.role_order(self.admission["ops_plan"]))

    def test_split_reference_refuses_a_missing_part_or_a_different_context(self):
        assignments = self.admission["ops_plan"]["assignments"]
        for assignment in assignments:
            result = self.run_role("reference-" + assignment["id"])
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for assignment in assignments:
            result = self.run_role(assignment["id"])
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.run_role("native").returncode, 0)
        part = self.artifacts / (self.prefix + "reference-" + assignments[0]["id"])
        held = part.rename(self.base / "held-reference-part")
        with self.assertRaisesRegex(ValueError, "missing or unexpected evidence roles"):
            self.join()
        held.rename(part)
        payload_path = part / "joined.json"
        payload = json.loads(payload_path.read_text())
        payload["execution_context"] = {"platform": "mutated", "uid": -1}
        payload_path.write_text(json.dumps(payload) + "\n")
        with self.assertRaisesRegex(ValueError, "reference part execution context differs"):
            self.consumer.materialize_split_reference(
                self.artifacts, self.prefix, assignments, self.base / "mutated-reference")

    def join(self, result="success", expected=None):
        return self.call(self.consumer.join, self.admission, self.artifacts, result,
                         expected or self.admission["admission_sha256"], self.source)

    def test_subprocess_imports_from_bot_cwd_in_reference_ordinary_and_serial(self):
        self.check_subprocess_imports(ambient_path=True)

    def test_subprocess_imports_without_inherited_pythonpath(self):
        self.env.pop("PYTHONPATH", None)
        self.check_subprocess_imports(ambient_path=False)

    def check_subprocess_imports(self, ambient_path):
        package = self.source / "yueops"
        package.mkdir()
        (package / "__init__.py").write_text("")
        (package / "brand_g.py").write_text("URL_SITE = 'reviewed-source'\n")
        bot = self.source / "telegram-bot/yue"
        bot.mkdir(parents=True)
        (bot / "service.py").write_text("from yueops.brand_g import URL_SITE\n")
        probe = textwrap.dedent('''
            import os, subprocess, sys
            from pathlib import Path
            def check_child_import():
                root = Path(__file__).resolve().parents[1]
                entries = os.environ['PYTHONPATH'].split(os.pathsep)
                assert len(entries) == 2 and all(Path(p).is_absolute() for p in entries)
                assert entries[1] == str(root)
                child = subprocess.run(
                    [sys.executable, '-c',
                     "from service import URL_SITE; assert URL_SITE == 'reviewed-source'"],
                    cwd=root / 'telegram-bot/yue', capture_output=True, text=True)
                assert child.returncode == 0, child.stderr
            check_child_import()
            def test_child_import():
                check_child_import()
        ''')
        # Exercise both collection-time children and test-time children, with
        # the same clean Python invocation and nested cwd as the real failure.
        (self.source / "tests/test_import_order.py").write_text(probe)
        serial = self.source / TAIL[0]
        serial.write_text(serial.read_text() + probe)
        self.fixture.git(self.source, "add", "yueops", "telegram-bot", "tests")
        self.fixture.commit(self.source)
        revision = self.fixture.git(self.source, "rev-parse", "HEAD").stdout.strip()
        for row in self.targets["matrix"] + self.targets["validation_matrix"]:
            row["ref"] = revision
        self.admission = self.call(self.consumer.expand, self.targets, self.source,
                                   self.board_sha, "ubuntu-24.04", 4, 4)
        # Ambient import paths must not leak into the reviewed child path.
        poison = self.base / "ambient"
        poison.mkdir()
        (poison / "yueops.py").write_text("raise RuntimeError('ambient import')\n")
        extra = ({"PYTHONPATH": os.pathsep.join((str(poison), "relative", ""))}
                 if ambient_path else {})
        joined = self.full_bundle(extra)
        self.assertEqual(joined["status"], "VALIDATION_MATRIX_COMPLETE")
        self.assertEqual(joined["ordinary"]["case_count"], 10)
        self.assertEqual(joined["skip_admission"]["status"], "NO_NEW_SKIPS")

    def test_actual_mixed_runner_allocations_reach_source_native_and_complete_join(self):
        roles = ["reference", *[a["id"] for a in self.admission["ops_plan"]["assignments"]], "native"]
        images = {}
        for i, role in enumerate(roles):
            images[role] = f"20261012.{334+i}.1"
            ran = self.run_role(role, {"ImageVersion": images[role]})
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        with patch.dict(self.env, {"ImageVersion": "separate-join-allocation"}):
            result = self.join()
        observed = result["runner_observations"]
        self.assertEqual({k: v["runner_image"] for k, v in observed["roles"].items()}, images)
        self.assertEqual(observed["planning_runner_image"], "fixture-image")
        self.assertTrue(observed["mixed_execution_images"])
        self.assertEqual(result["ordinary"]["case_count"], 8)
        self.assertFalse(result["skip_admission"]["skips_are_passes"])
        context = result["native_and_source_gates"]
        for row in context["obligations"].values():
            self.assertEqual(row["binding"]["runner_context"], observed["roles"]["native"])
        # A native terminal cannot substitute another allocation after preparation.
        directory = self.artifacts / (self.prefix + "native")
        (directory / "native.json").unlink()
        with self.assertRaisesRegex(ValueError, "changed during execution"):
            self.call(self.consumer.native_terminal, self.admission, self.source, self.board, directory)
        self.assertFalse((directory / "native.json").exists())

    def test_actual_precollection_rejection_is_retained_without_a_test_terminal(self):
        for extra in ({"RUNNER_OS": "Windows"}, {"RUNNER_ARCH": "ARM64"},
                      {"ImageVersion": ""}, {"ImageVersion": "UNKNOWN"}):
            with self.subTest(extra=extra):
                ran = self.run_role("reference", extra)
                self.assertNotEqual(ran.returncode, 0, ran.stdout + ran.stderr)
                directory = self.artifacts / (self.prefix + "reference")
                self.assertEqual([p.name for p in directory.iterdir()], ["rejected.json"])
                receipt = json.loads((directory / "rejected.json").read_text())
                self.assertEqual(receipt["status"], "REJECTED")
                self.assertFalse(receipt["release_acceptance"])
                self.assertEqual(receipt["assignment_id"], "reference")
                expected_image = extra.get("ImageVersion", self.env["ImageVersion"]) or None
                self.assertEqual(receipt["identity"]["ImageVersion"], expected_image)
                self.assertIn(receipt["reason_code"], ("RUNNER_PLATFORM_MISMATCH", "RUNNER_IDENTITY_MISSING"))
                with self.assertRaises(ValueError):
                    self.join()
                shutil.rmtree(directory)
                shutil.rmtree(self.base / "runner-reference")
        # The actual native-start CLI must also retain its pre-pytest rejection.
        admission = self.base / "native-rejected-admission.json"
        admission.write_text(json.dumps(self.admission))
        native_output = self.base / "native-rejected"
        ran = subprocess.run(
            [sys.executable, str(self.policy / "scripts/pytest-shards.py"), "native-start",
             "--admission", str(admission), "--source", str(self.source), "--board", str(self.board),
             "--output", str(native_output)], cwd=self.source,
            env=self.env | {"RUNNER_OS": "Windows"}, capture_output=True, text=True,
            timeout=15, check=False)
        self.assertNotEqual(ran.returncode, 0)
        self.assertEqual([p.name for p in native_output.iterdir()], ["rejected.json"])
        self.assertEqual(json.loads((native_output / "rejected.json").read_text())["stage"],
                         "native-start")
        # Source rejection follows the same actual CLI, before recorder/selection.
        (self.source / "tests/test_a.py").write_text("def test_changed(): pass\n")
        ran = self.run_role("reference")
        self.assertNotEqual(ran.returncode, 0)
        directory = self.artifacts / (self.prefix + "reference")
        self.assertEqual([p.name for p in directory.iterdir()], ["rejected.json"])
        self.assertEqual(json.loads((directory / "rejected.json").read_text())["reason_code"],
                         "SOURCE_IDENTITY_MISMATCH")

    def test_rejection_writer_preserves_existing_files_and_refuses_symlink_paths(self):
        from argparse import Namespace
        admission = self.base / "rejection-admission.json"
        admission.write_text(json.dumps(self.admission))
        output = self.base / "rejected"
        args = Namespace(command="run", output=output, role="reference", admission=admission)
        self.call(self.consumer.retain_rejection, args, ValueError("private failure sentinel"))
        original = (output / "rejected.json").read_bytes()
        self.assertNotIn(b"private failure sentinel", original)
        with self.assertRaises(FileExistsError):
            self.call(self.consumer.retain_rejection, args, ValueError("again"))
        self.assertEqual((output / "rejected.json").read_bytes(), original)
        link = self.base / "linked-output"
        link.symlink_to(output, target_is_directory=True)
        args.output = link / "child"
        with self.assertRaisesRegex(ValueError, "unsafe"):
            self.call(self.consumer.retain_rejection, args, ValueError("failure"))
        self.assertFalse((output / "child").exists())

    def test_actual_yaml_source_entry_and_join_keep_complete_corpus(self):
        result = self.full_bundle()
        self.assertEqual(result["status"], "VALIDATION_MATRIX_COMPLETE")
        self.assertEqual(result["ordinary"]["case_count"], 8)
        self.assertFalse(result["ordinary"]["release_acceptance"])
        self.assertEqual(result["skip_admission"]["status"], "NO_NEW_SKIPS")
        self.assertFalse(result["skip_admission"]["skips_are_passes"])
        self.assertEqual(result["host_linux_skip_policy"], "ROOT_GATE_UNCHANGED")
        receipt = json.loads((self.artifacts / (self.prefix + "serial") / "selection.json").read_text())
        metadata = json.loads((self.artifacts / (self.prefix + "serial") / "metadata.json").read_text())
        self.assertEqual(receipt["modules"], TAIL)
        self.assertEqual(receipt["pytest_argv"][0], metadata["python_executable"])
        self.assertEqual(receipt["pytest_argv"][1:-2], ["-m", "pytest", "-q", *TAIL])
        self.assertEqual(receipt["pytest_argv"][-2], "--junitxml")
        empty = [r for r in result["ordinary"]["shards"] if r["empty_assigned_collection"]]
        self.assertEqual(len(empty), 1)
        self.assertEqual(empty[0]["pytest_process_exit_code"], 5)
        runner = self.base / "join-runner"
        (runner / "ops-admission").mkdir(parents=True)
        (runner / "ops-admission/ops-admission.json").write_text(json.dumps(self.admission))
        self.artifacts.rename(runner / "ops-shard-evidence")
        self.artifacts = runner / "ops-shard-evidence"
        _, script = yaml_consumer.step("Require complete selected validation and corpus")
        report = runner / f"ops-validation-evidence-{self.env['GITHUB_RUN_ID']}-{self.env['GITHUB_RUN_ATTEMPT']}.json"
        for status in ("success", "failure", "cancelled", "skipped"):
            report.unlink(missing_ok=True)
            env = self.env | {"RUNNER_TEMP": str(runner), "GITHUB_WORKSPACE": str(self.policy),
                              "VALIDATION_RESULT": status,
                              "ADMISSION_SHA256": self.admission["admission_sha256"]}
            executed = subprocess.run(["bash", "-c", script], cwd=self.policy, env=env,
                                      capture_output=True, text=True, timeout=15, check=False)
            if status == "success":
                self.assertEqual(executed.returncode, 0, executed.stdout + executed.stderr)
                summary = json.loads(executed.stdout)
                full = report.read_bytes()
                self.assertEqual(json.loads(full), result)
                self.assertEqual(summary["status"], "VALIDATION_MATRIX_COMPLETE")
                self.assertEqual(summary["identity"], self.admission["identity"])
                self.assertEqual(summary["admission_sha256"], self.admission["admission_sha256"])
                self.assertEqual(summary["case_count"], 8)
                self.assertEqual(summary["report_sha256"], hashlib.sha256(full).hexdigest())
                self.assertEqual(summary["report_bytes"], len(full))
                self.assertLessEqual(len(executed.stdout.encode()), 8192)
                self.assertNotIn("tests/test_a.py", executed.stdout)
            else:
                self.assertNotEqual(executed.returncode, 0, executed.stdout + executed.stderr)
                self.assertEqual(executed.stdout, "")
                self.assertIn("selected validation matrix did not succeed", executed.stderr)
        report.write_text("retained prior verdict")
        executed = subprocess.run(["bash", "-c", script], cwd=self.policy,
                                  env=env | {"VALIDATION_RESULT": "success"},
                                  capture_output=True, text=True, timeout=15, check=False)
        self.assertNotEqual(executed.returncode, 0)
        self.assertEqual(executed.stdout, "")
        self.assertEqual(report.read_text(), "retained prior verdict")

    def test_complete_verdict_artifact_cannot_fail_open_or_replace_an_attempt(self):
        body, _ = yaml_consumer.step("Retain complete validation verdict")
        def required_artifact(contract):
            self.assertIn("uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a", contract)
            self.assertIn("name: ops-validation-evidence-${{ github.run_id }}-${{ github.run_attempt }}", contract)
            self.assertIn("path: ${{ runner.temp }}/ops-validation-evidence-${{ github.run_id }}-${{ github.run_attempt }}.json", contract)
            self.assertIn("if-no-files-found: error", contract)
            self.assertIn("overwrite: false", contract)
            self.assertNotIn("continue-on-error", contract)
            self.assertNotIn("if:", contract)
        required_artifact(body)
        for broken in (body.replace("if-no-files-found: error", "if-no-files-found: warn"),
                       body.replace("overwrite: false", "overwrite: true"),
                       body + "        continue-on-error: true\n",
                       body + "        if: false\n"):
            with self.subTest(contract=broken), self.assertRaises(AssertionError):
                required_artifact(broken)
        workflow = (ROOT / ".github/workflows/build.yml").read_text()
        join_job = workflow.split("  validation-evidence:\n", 1)[1].split("  build:\n", 1)[0]
        self.assertNotIn("continue-on-error", join_job)
        self.assertIn("timeout-minutes: 10", join_job)
        self.assertNotIn("timeout-minutes: 30", join_job)
        publish = workflow.split("\n  publish:\n", 1)[1]
        self.assertTrue(publish.startswith("    needs: [build, plan, validate, validation-evidence]\n"))
        self.assertLess(workflow.index("- name: Require complete selected validation and corpus"),
                        workflow.index("- name: Retain complete validation verdict"))

    def test_actual_selection_rejects_wrong_interpreter_identity(self):
        ran = self.run_role("reference")
        self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        root = self.artifacts / (self.prefix + "reference")
        # Pick a non-empty shard explicitly: directory order is filesystem dependent and
        # the empty skip-module shard legitimately exits 5, which is not what this test probes.
        assignment = next(item for item in self.admission["ops_plan"]["assignments"]
                          if "tests/test_a.py" in item["modules"])
        directory = root / "parts" / assignment["id"]
        marked = assignment | {"collect_only": True}
        self.consumer.inspect_session(directory, self.admission["ops_plan"], marked)
        path = directory / "selection.json"
        receipt = json.loads(path.read_text())
        receipt["pytest_argv"][0] += ".wrong-interpreter"
        path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, "wrong Python executable"):
            self.consumer.inspect_session(directory, self.admission["ops_plan"], marked)

    def test_actual_failure_is_not_retried_as_legacy(self):
        assignment = next(a for a in self.admission["ops_plan"]["assignments"]
                          if "tests/test_c.py" in a["modules"])
        result = self.run_role(assignment["id"], {"CASE_FAILURE": "call"})
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        directory = self.artifacts / (self.prefix + assignment["id"])
        self.assertEqual((directory / "pytest-exit-code.txt").read_text(), "1")
        rows = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
        self.assertEqual(sum(r.get("event") == "start" for r in rows), 1)
        with self.assertRaises(ValueError):
            self.join("failure")

    def test_real_new_tool_skip_is_reported_and_is_not_a_pass(self):
        result = self.full_bundle({"NEW_SKIP": "1"})
        self.assertEqual(result["status"], "VALIDATION_MATRIX_COMPLETE")
        self.assertFalse(result["skip_admission"]["skips_are_passes"])
        self.assertTrue(any("::test_case" in node
                            for node in result["skip_admission"]["reported_skips"]))

    def test_real_new_import_skip_is_reported(self):
        result = self.full_bundle({"NEW_COLLECTION": "1"})
        self.assertEqual(result["status"], "VALIDATION_MATRIX_COMPLETE")
        self.assertFalse(result["skip_admission"]["skips_are_passes"])
        self.assertIn("tests/test_c.py", result["skip_admission"]["reported_skips"])

    def test_real_changed_collection_skip_reason_is_reported(self):
        result = self.full_bundle({"COLLECTION_REASON": "changed dependency reason"})
        self.assertEqual(result["status"], "VALIDATION_MATRIX_COMPLETE")
        self.assertFalse(result["skip_admission"]["skips_are_passes"])
        self.assertIn("tests/test_skip_module.py", result["skip_admission"]["reported_skips"])

    def test_changed_skip_module_and_shared_inputs_require_reviewed_refresh(self):
        path = self.source / "tests/test_a.py"
        # A trailing comment is still the same case. The skip reason is not.
        path.write_text(path.read_text().replace(
            "existing fixture skip", "rewritten fixture skip", 1))
        self.fixture.git(self.source, "add", "tests/test_a.py")
        self.fixture.commit(self.source)
        revision = self.fixture.git(self.source, "rev-parse", "HEAD").stdout.strip()
        for row in self.targets["matrix"] + self.targets["validation_matrix"]:
            row["ref"] = revision
        self.admission = self.call(self.consumer.expand, self.targets, self.source,
                                   self.board_sha, "ubuntu-24.04", 4, 4)
        result = self.full_bundle()
        self.assertEqual(result["status"], "VALIDATION_MATRIX_COMPLETE")
        self.assertFalse(result["skip_admission"]["skips_are_passes"])
        for name in ("pytest.ini", "uv.lock"):
            path = self.source / name
            path.write_text((path.read_text() if path.exists() else "") + "\n# Changed input.\n")
            self.fixture.git(self.source, "add", name)
            self.fixture.commit(self.source)
            revision = self.fixture.git(self.source, "rev-parse", "HEAD").stdout.strip()
            for row in self.targets["matrix"] + self.targets["validation_matrix"]:
                row["ref"] = revision
            admitted = self.call(self.consumer.expand, self.targets, self.source,
                                  self.board_sha, "ubuntu-24.04", 4, 4)
            self.assertEqual(admitted["admission_rule"], "signed-default-branch")
            self.assertEqual(admitted["common_inputs"],
                             self.consumer.shared_inputs(self.source, revision))

    def reviewed_ssh_skip_transition(self, *, original_source=False):
        """Run real skips, then pin the isolated policy to exactly two successors."""
        actual = json.loads((ROOT / "ops-pytest-skip-baseline.json").read_text())
        for nodeid in sorted(self.consumer.SSH_SKIP_CASES):
            module, case = nodeid.split("::")
            reason = actual["cases"][nodeid]["reason"].removeprefix("Skipped: ")
            (self.source / module).write_text(
                "import os,pytest\n"
                f"@pytest.mark.skip(reason=os.environ.get('SSH_REVIEWED_REASON',{reason!r}))\n"
                f"def {case}(): pass\n")
        paths = sorted(n.split("::")[0] for n in self.consumer.SSH_SKIP_CASES)
        self.fixture.git(self.source, "add", *paths)
        self.fixture.commit(self.source)
        before = self.fixture.git(self.source, "rev-parse", "HEAD").stdout.strip()
        files = self.consumer.tree_inputs(self.source, before)
        modules = sorted(p for p in files if self.consumer.safe_module(p))
        self.fixture.env["GITHUB_SHA"] = self.env["GITHUB_SHA"]
        directory, executed = self.fixture.run_session({"id": "ordinary-000", "modules": modules})
        self.assertEqual(executed.returncode, 0, executed.stdout + executed.stderr)
        baseline = self.consumer.generate_skip_baseline(
            self.source, before, directory / "events.jsonl", directory / "pytest.xml",
            directory / "events.jsonl", before, "fixture original execution")
        for name in paths:
            path = self.source / name
            path.write_text(path.read_text() + "\n# Reviewed consumer coverage addition.\n")
        self.fixture.git(self.source, "add", *paths)
        self.fixture.commit(self.source)
        after = self.fixture.git(self.source, "rev-parse", "HEAD").stdout.strip()
        successors = self.consumer.tree_inputs(self.source, after)
        record = {
            "schema": 1,
            "prior_baseline_sha256": self.consumer.sha(
                (json.dumps(baseline, indent=2, ensure_ascii=False) + "\n").encode()),
            "source_before": before, "source_after": after, "qualified_source": after,
            "independent_review_sha256": "1" * 64, "source_freeze_sha256": "2" * 64,
            "qualification_receipt_sha256": "3" * 64, "composition_review_sha256": "4" * 64,
            "cases": {n: {"before_blob": files[n.split("::")[0]][1],
                           "after_blob": successors[n.split("::")[0]][1], "mode": "100644"}
                      for n in sorted(self.consumer.SSH_SKIP_CASES)},
        }
        baseline["reviewed_ssh_skip_module_transition"] = record
        policy = self.policy / "ops-pytest-skip-baseline.json"
        policy.write_text(json.dumps(baseline, indent=2, ensure_ascii=False) + "\n")
        # Bind the actual copied CLI to this fixture's exact reviewed record.
        # Production has no environment override or mutable admission allowlist.
        consumer = self.policy / "scripts/pytest-shards.py"
        original_pin = self.consumer.SSH_SKIP_TRANSITION_SHA256
        fixture_pin = self.consumer.sha(self.consumer.encoded(record))
        original_stat = consumer.stat()
        original_bytes = consumer.read_bytes()
        py_compile.compile(str(consumer), doraise=True,
                           invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
        current_bytes = original_bytes.replace(original_pin.encode(), fixture_pin.encode(), 1)
        self.assertNotEqual(original_pin, fixture_pin)
        self.assertEqual(len(current_bytes), len(original_bytes))
        consumer.write_bytes(current_bytes)
        os.utime(consumer, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        self.assertEqual((consumer.stat().st_mtime_ns, consumer.stat().st_size),
                         (original_stat.st_mtime_ns, original_stat.st_size))
        # Deliberately reproduce the public failure: a valid timestamp/size pyc
        # still contains the old pin, even though the owned source bytes changed.
        stale_spec = importlib.util.spec_from_file_location("stale_ssh_skip_consumer", consumer)
        stale = importlib.util.module_from_spec(stale_spec)
        stale_spec.loader.exec_module(stale)
        self.assertEqual(stale.SSH_SKIP_TRANSITION_SHA256, original_pin)
        spec = importlib.util.spec_from_file_location("actual_ssh_skip_consumer", consumer)
        self.consumer = importlib.util.module_from_spec(spec)
        # Preserve module metadata while executing this mutable fixture's exact
        # written source, which is also the source used by the real CLI below.
        exec(compile(consumer.read_bytes(), str(consumer), "exec"), self.consumer.__dict__)
        self.assertEqual(self.consumer.SSH_SKIP_TRANSITION_SHA256, fixture_pin)
        self.fixture.git(self.policy, "add", "ops-pytest-skip-baseline.json", "scripts/pytest-shards.py")
        self.fixture.commit(self.policy)
        self.env["GITHUB_SHA"] = self.fixture.git(self.policy, "rev-parse", "HEAD").stdout.strip()
        revision = before if original_source else after
        if original_source:
            self.fixture.git(self.source, "reset", "--hard", before)
        for row in self.targets["matrix"] + self.targets["validation_matrix"]:
            row["ref"] = revision
        self.admission = self.call(self.consumer.expand, self.targets, self.source,
                                   self.board_sha, "ubuntu-24.04", 4, 4)
        return baseline

    def test_reviewed_ssh_successors_reach_real_join_without_reclassifying_skips(self):
        baseline = self.reviewed_ssh_skip_transition()
        result = self.full_bundle()
        self.assertEqual(result["status"], "VALIDATION_MATRIX_COMPLETE")
        self.assertFalse(result["skip_admission"]["skips_are_passes"])
        self.assertEqual(result["skip_admission"]["disposition_counts"]["SAME_RUN_NATIVE_REQUIRED"], 0)
        rows = {r["nodeid"]: r for session in result["ordinary"]["shards"]
                for r in session["nonpassing_outcomes"]}
        for nodeid in self.consumer.SSH_SKIP_CASES:
            self.assertEqual(rows[nodeid]["outcome"], "skipped")
            self.assertEqual(rows[nodeid]["reason"], baseline["cases"][nodeid]["reason"])
        # Replacing a valid review digest cannot reuse an already admitted run.
        policy = self.policy / "ops-pytest-skip-baseline.json"
        original = policy.read_bytes()
        mutations = []
        for field in ("prior_baseline_sha256", "independent_review_sha256", "source_freeze_sha256",
                      "qualification_receipt_sha256", "composition_review_sha256"):
            changed = copy.deepcopy(baseline)
            changed["reviewed_ssh_skip_module_transition"][field] = "f" * 64
            mutations.append((field, changed))
        for nodeid in sorted(self.consumer.SSH_SKIP_CASES):
            changed = copy.deepcopy(baseline)
            changed["reviewed_ssh_skip_module_transition"]["cases"][nodeid]["after_blob"] = "f" * 40
            mutations.append((nodeid, changed))
        for label, changed in mutations:
            policy.write_text(json.dumps(changed))
            with self.subTest(join_mutation=label), self.assertRaisesRegex(
                    ValueError, "skip baseline or shared collection inputs differ"):
                self.join()
        policy.write_bytes(original)
        # A second, unreviewed module revision is not covered by the transition.
        module = sorted(self.consumer.SSH_SKIP_CASES)[0].split("::")[0]
        wrong = copy.deepcopy(self.admission)
        wrong["skip_module_blobs"][module] = "e" * 40
        accepted = self.consumer.admit_skips(wrong, result["ordinary"], result["native_and_source_gates"])
        self.assertEqual(accepted["status"], "NO_NEW_SKIPS")
        self.assertFalse(accepted["skips_are_passes"])
        self.assertTrue(any(nodeid.startswith(module + "::") for nodeid in accepted["reported_skips"]))
        # Independent qualification cannot replace this run's original native gates.
        (self.artifacts / (self.prefix + "native") / "native.json").unlink()
        with self.assertRaises(ValueError):
            self.join()

    def test_reviewed_ssh_transition_keeps_actual_original_source_admission(self):
        self.reviewed_ssh_skip_transition(original_source=True)
        result = self.full_bundle()
        self.assertEqual(result["status"], "VALIDATION_MATRIX_COMPLETE")
        self.assertFalse(result["skip_admission"]["skips_are_passes"])

    def test_reviewed_ssh_transition_reports_an_actual_new_case_skip(self):
        self.reviewed_ssh_skip_transition()
        result = self.full_bundle({"NEW_SKIP": "1"})
        self.assertEqual(result["status"], "VALIDATION_MATRIX_COMPLETE")
        self.assertFalse(result["skip_admission"]["skips_are_passes"])
        self.assertTrue(any("::test_case" in node
                            for node in result["skip_admission"]["reported_skips"]))

    def test_reviewed_ssh_transition_reports_an_actual_changed_skip_reason(self):
        self.reviewed_ssh_skip_transition()
        result = self.full_bundle({"SSH_REVIEWED_REASON": "different but plausible missing tool"})
        self.assertEqual(result["status"], "VALIDATION_MATRIX_COMPLETE")
        self.assertFalse(result["skip_admission"]["skips_are_passes"])
        self.assertTrue(any(nodeid in result["skip_admission"]["reported_skips"]
                            for nodeid in self.consumer.SSH_SKIP_CASES))

    def test_actual_plan_yaml_expands_all_targets_before_collection(self):
        other = [{"repo": "onesyue/yueboard", "ref": "b" * 40, "validation": "yueboard"},
                 {"repo": "onesyue/yue-node", "ref": "c" * 40, "validation": "yue-node",
                  "node_profile": "hy2"},
                 {"repo": "onesyue/yue-node", "ref": "c" * 40, "validation": "yue-node",
                  "node_profile": "vless"},
                 {"repo": "onesyue/yuelink", "ref": "d" * 40, "validation": "yuelink"}]
        targets = copy.deepcopy(self.targets)
        targets["validation_matrix"] = other + targets["validation_matrix"]
        runner = self.base / "plan-runner"
        runner.mkdir()
        (runner / "build-target-plan.json").write_text(json.dumps(targets))
        (self.policy / ".ops-shard-source").symlink_to(self.source, target_is_directory=True)
        output = self.base / "plan-output"
        env = self.env | {"RUNNER_TEMP": str(runner), "GITHUB_OUTPUT": str(output),
                          "OPS_BOARD": self.board_sha, "OPS_RUNNER": "ubuntu-24.04",
                          "OPS_SHARDS": "4", "OPS_CAPACITY": "2"}
        _, script = yaml_consumer.step("Plan complete Ops jobs before collection")
        result = subprocess.run(["bash", "-c", script], cwd=self.policy, env=env,
                                capture_output=True, text=True, timeout=20, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        value = json.loads((runner / "ops-admission.json").read_text())
        self.assertEqual(value["max_parallel"], 2)
        ops_roles = [m["ops_role"] for m in value["validation_matrix"] if m.get("ops_role")]
        self.assertEqual(ops_roles, self.consumer.role_order(value["ops_plan"]))
        self.assertNotIn("reference", ops_roles)
        self.assertEqual(
            {role[len("reference-"):] for role in ops_roles if role.startswith("reference-")},
            {a["id"] for a in value["ops_plan"]["assignments"]},
        )
        self.assertEqual(len(value["validation_matrix"]), len(other) + len(ops_roles))
        self.assertEqual(list(self.artifacts.iterdir()), [])
        self.assertIn("admission_sha256=", output.read_text())

    def test_plan_yaml_applies_duration_weights_outside_the_plan(self):
        ordinary = sorted(module for item in self.admission["ops_plan"]["assignments"]
                          if item["id"].startswith("ordinary-") for module in item["modules"])
        self.assertGreaterEqual(len(ordinary), 2)
        weights = {module: 1000 for module in ordinary}
        weights[ordinary[-1]] = 100000
        runner = self.base / "weighted-plan-runner"
        runner.mkdir()
        (runner / "build-target-plan.json").write_text(json.dumps(self.targets))
        (runner / "previous-ordinary-weights.json").write_text(json.dumps(weights))
        (self.policy / ".ops-shard-source").symlink_to(self.source, target_is_directory=True)
        output = self.base / "weighted-plan-output"
        env = self.env | {"RUNNER_TEMP": str(runner), "GITHUB_OUTPUT": str(output),
                          "OPS_BOARD": self.board_sha, "OPS_RUNNER": "ubuntu-24.04",
                          "OPS_SHARDS": "4", "OPS_CAPACITY": "2"}
        _, script = yaml_consumer.step("Plan complete Ops jobs before collection")
        self.assertNotIn("gh ", script)
        result = subprocess.run(["bash", "-c", script], cwd=self.policy, env=env,
                                capture_output=True, text=True, timeout=20, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        value = json.loads((runner / "ops-admission.json").read_text())
        self.assertNotIn("ordinary_weights", value["ops_plan"])
        self.assertEqual(value["ordinary_weights"], weights)
        self.consumer.validate_plan(value["ops_plan"])
        self.assertEqual(value["ops_plan"]["assignments"][0]["modules"], [ordinary[-1]])
        ignored = self.call(self.consumer.plan, self.source, value["ops_plan"]["context"], 4, TAIL)
        self.consumer.detach_ordinary_weights(ignored)
        self.assertEqual(ignored["assignments"][0]["modules"], [ordinary[0]])
        self.assertNotEqual(ignored["assignments"], value["ops_plan"]["assignments"])

    def test_matrix_selection_capacity_and_upfront_manual_compatibility(self):
        for count in (0, -1):
            with self.subTest(count=count), self.assertRaises(ValueError):
                self.call(self.consumer.expand, self.targets, self.source, self.board_sha,
                          "ubuntu-24.04", count, 4)
        for service in ("yueops-web", "yue-bot", "checkin-api"):
            targets = copy.deepcopy(self.targets)
            targets["matrix"] = [m for m in targets["matrix"] if m["service"] == service]
            value = self.call(self.consumer.expand, targets, self.source, self.board_sha,
                              "ubuntu-24.04", 1, 4)
            self.assertEqual(value["max_parallel"], 1)
            self.assertEqual(len(value["ops_plan"]["assignments"]), 5)
        # Missing hosted image identity never causes an automatic manual fallback.
        with patch.dict(os.environ, self.env | {"ImageVersion": ""}, clear=True):
            with self.assertRaises(ValueError):
                self.consumer.expand(self.targets, self.source, self.board_sha,
                                     "ubuntu-24.04", 1, 4)
            manual = self.consumer.expand(self.targets, None, self.board_sha,
                                          "yue-local-release", 4, 4)
        self.assertEqual(manual["mode"], "legacy")
        self.assertEqual(manual["max_parallel"], 1)
        self.assertEqual([m["ops_role"] for m in manual["validation_matrix"]], ["legacy"])
        self.assertIsNone(manual["ops_plan"])
        result = self.call(self.consumer.join, manual, self.artifacts, "success",
                           manual["admission_sha256"])
        self.assertFalse(result["sharded_corpus_evaluated"])
        for state in ("failure", "cancelled", "skipped", "", "timed_out"):
            with self.subTest(state=state), self.assertRaises(ValueError):
                self.call(self.consumer.join, manual, self.artifacts, state,
                          manual["admission_sha256"])

    def test_no_ops_and_source_only_link_preserve_mandatory_matrix(self):
        for kind in ("yueboard", "yue-node", "yuelink"):
            target = {"matrix": [] if kind == "yuelink" else [{"validation": kind}],
                      "validation_matrix": [{"validation": kind, "repo": "onesyue/" + kind,
                                             "ref": "b" * 40}]}
            value = self.call(self.consumer.expand, target, None, self.board_sha,
                              "ubuntu-24.04", 4, 4)
            self.assertEqual(value["mode"], "none")
            self.assertEqual(value["validation_matrix"], target["validation_matrix"])
            result = self.call(self.consumer.join, value, self.artifacts, "success",
                               value["admission_sha256"])
            self.assertFalse(result["sharded_corpus_evaluated"])
            with self.assertRaises(ValueError):
                self.call(self.consumer.join, value, self.artifacts, "failure",
                          value["admission_sha256"])

    def test_duplicate_or_moving_ops_source_and_wrong_board_are_rejected(self):
        targets = copy.deepcopy(self.targets)
        targets["validation_matrix"] *= 2
        with self.assertRaises(ValueError):
            self.call(self.consumer.expand, targets, self.source, self.board_sha,
                      "ubuntu-24.04", 4, 4)
        targets = copy.deepcopy(self.targets)
        targets["matrix"][0]["ref"] = "master"
        with self.assertRaises(ValueError):
            self.call(self.consumer.expand, targets, self.source, self.board_sha,
                      "ubuntu-24.04", 4, 4)
        (self.board / "schema.sql").write_text("-- changed\n")
        with self.assertRaisesRegex(ValueError, "Board"):
            self.call(self.consumer.native_terminal, self.admission, self.source, self.board,
                      self.base / "forbidden-native")

    def test_missing_native_stale_attempt_and_forged_plan_block_join(self):
        self.full_bundle()
        native_path = self.artifacts / (self.prefix + "native")
        retained = self.base / "retained-native"
        native_path.rename(retained)
        with self.assertRaises(ValueError):
            self.join()
        retained.rename(native_path)
        with self.assertRaisesRegex(ValueError, "digest"):
            self.join(expected="a" * 64)
        with (patch.dict(os.environ, self.env | {"GITHUB_RUN_ATTEMPT": "2"}, clear=True),
              self.assertRaisesRegex(ValueError, "stale")):
            self.consumer.join(self.admission, self.artifacts, "success",
                               self.admission["admission_sha256"])
        native = json.loads((native_path / "native.json").read_text())
        native["status"] = "skipped"
        (native_path / "native.json").write_text(json.dumps(native))
        with self.assertRaisesRegex(ValueError, "native"):
            self.join()

    def test_build_and_each_original_required_gate_keep_actual_role_owner(self):
        text = (ROOT / ".github/workflows/build.yml").read_text()
        build_job = text.split("\n  build:\n", 1)[1].split("\n  publish:\n", 1)[0]
        publish = text.split("\n  publish:\n", 1)[1]
        self.assertTrue(build_job.startswith("    needs: [plan]\n"))
        self.assertNotIn("Authorize and promote verified default-branch digest", build_job)
        self.assertNotIn("built-${SOURCE_SHA}", build_job)
        self.assertIn("needs: [build, plan, validate, validation-evidence]\n", publish)
        self.assertEqual(text.count("- name: Authorize and promote verified default-branch digest"), 1)
        self.assertEqual(text.count("- name: Mark this source revision as built"), 1)
        build = text.split("  build:\n", 1)[1]
        self.assertIn("if: needs.plan.outputs.has_builds == 'true'", build)
        self.assertNotIn("if: always()", build.split("    steps:", 1)[0])
        gates = ("Validate yueops backend", "Validate yueops PostgreSQL and systemd native obligations",
                 "Validate yueops frontend", "Validate Yue mini app",
                 "Lint changed YueOps SQL migrations")
        native_pos = text.index("- name: Record complete Ops native and source gates")
        for name in gates:
            body, _ = yaml_consumer.step(name)
            self.assertIn("matrix.ops_role == 'native' || matrix.ops_role == 'legacy'", body)
            self.assertLess(text.index("- name: " + name), native_pos)
        self.assertIn("if: always() && matrix.validation == 'yueops' && matrix.ops_role != 'legacy'",
                      yaml_consumer.step("Retain owned Ops evidence even after failure")[0])
        assert_only_named_caches_are_optional(self, text)


    def test_real_reviewed_reason_keeps_skip_and_changed_phase_is_rejected(self):
        nodeid = "tests/test_a.py::test_skip"
        original = self.baseline["cases"][nodeid]
        self.baseline["reviewed_hosted"] = {
            "schema": 1, "context": self.baseline["context"],
            "runner": {"runner_os": "Linux", "runner_arch": "X64"},
            "cases": {nodeid: {"module_blob": original["module_blob"],
                                "outcome": "skipped", "disposition": "HISTORICAL_UNEXECUTED",
                                "variants": [{"when": "setup", "reason": original["reason"]},
                                             {"when": "setup", "reason": "Skipped: reviewed tool absent"}]}}}
        (self.policy / "ops-pytest-skip-baseline.json").write_text(json.dumps(self.baseline))
        self.fixture.git(self.policy, "add", "ops-pytest-skip-baseline.json")
        self.fixture.commit(self.policy)
        self.env["GITHUB_SHA"] = self.fixture.git(self.policy, "rev-parse", "HEAD").stdout.strip()
        self.admission = self.call(self.consumer.expand, self.targets, self.source,
                                   self.board_sha, "ubuntu-24.04", 4, 4)
        result = self.full_bundle({"REVIEWED_REASON": "reviewed tool absent"})
        self.assertFalse(result["skip_admission"]["skips_are_passes"])
        self.assertGreater(result["skip_admission"]["disposition_counts"]["HISTORICAL_UNEXECUTED"], 0)
        # Actual pytest emitted the reviewed phase/reason, not a hand-built positive.
        ordinary = result["ordinary"]
        row = next(r for session in ordinary["shards"] for r in session["nonpassing_outcomes"]
                   if r["nodeid"] == nodeid)
        self.assertEqual(row["when"], "setup")
        row["when"] = "call"
        accepted = self.consumer.admit_skips(self.admission, ordinary, result["native_and_source_gates"])
        self.assertEqual(accepted["status"], "NO_NEW_SKIPS")
        self.assertFalse(accepted["skips_are_passes"])
        self.assertIn(nodeid, accepted["reported_skips"])

    def test_durable_native_semantics_reject_missing_stale_failed_and_reduced_evidence(self):
        result = self.full_bundle()
        directory = self.artifacts / (self.prefix + "native")
        originals = {p.name: p.read_bytes() for p in directory.iterdir()}
        target = "tests/test_board139_schema_acl_native_20261018.py"
        path = directory / (Path(target).stem + ".json")
        for mode in ("missing", "truncated", "malformed", "duplicate", "missing-one",
                     "wrong-module", "uid", "floor", "skip", "failed", "xfail",
                     "collection", "deselected", "exit", "process-exit", "run", "attempt",
                     "source", "board", "policy", "extra"):
            with self.subTest(mode=mode):
                for extra in directory.iterdir():
                    extra.unlink()
                for name, content in originals.items():
                    (directory / name).write_bytes(content)
                (directory / "native.json").unlink()
                row = json.loads(path.read_text())
                if mode == "missing": path.unlink()
                elif mode == "truncated": path.write_text('{"target":')
                elif mode == "malformed": path.write_text('[]')
                elif mode == "extra": (directory / "duplicate.json").write_text('{}')
                else:
                    if mode == "duplicate": row["required"].append(row["required"][0])
                    elif mode == "missing-one": row["passed"].pop()
                    elif mode == "wrong-module": row["required"][0] = "tests/other.py::test_wrong"
                    elif mode == "uid": row["uid"] = 0
                    elif mode == "floor": row["floor"] = 5
                    elif mode in ("skip", "failed", "xfail"): row["failed_or_skipped"] = [row["required"][0]]
                    elif mode in ("collection", "deselected"): row["collection_bad"] = True
                    elif mode == "exit": row["exitstatus"] = 2
                    elif mode == "process-exit": row["process_exitstatus"] = 1
                    elif mode in ("run", "attempt", "policy"):
                        key = {"run": "run_id", "attempt": "run_attempt", "policy": "policy_revision"}[mode]
                        row["binding"]["identity"][key] = "9" * (40 if mode == "policy" else 1)
                    else: row["binding"][mode + "_revision"] = "e" * 40
                    path.write_text(json.dumps(row))
                with self.assertRaises(ValueError):
                    self.call(self.consumer.native_terminal, self.admission,
                              self.source, self.board, directory)
                self.assertFalse((directory / "native.json").exists())
        # Conditional ACL closure is identity-based, never a six-count substitute.
        baseline = json.loads((ROOT / "ops-pytest-skip-baseline.json").read_text())
        baseline, _ = self.consumer.reviewed_estate_input_transition(baseline)
        compatible = baseline["reviewed_hosted"]["cases"]
        rows = [{"nodeid": n, "outcome": r["outcome"], **r["variants"][0]}
                for n, r in compatible.items() if r["disposition"] == "SAME_RUN_NATIVE_REQUIRED"]
        value = copy.deepcopy(self.admission)
        value["skip_module_blobs"].update({n.split("::")[0]: r["module_blob"]
                                          for n, r in compatible.items()})
        ordinary = {"reference": {"assignment_id": "reference", "execution_context": baseline["context"],
                                   "collection_skips": {}, "junit_sha256": "a" * 64,
                                   "nonpassing_outcomes": []}, "shards": []}
        ordinary["shards"] = [ordinary["reference"] | {"assignment_id": "ordinary-000",
                                                       "nonpassing_outcomes": rows}]
        native = result["native_and_source_gates"]
        with patch.object(self.consumer, "skip_baseline", return_value=baseline):
            accepted = self.consumer.admit_skips(value, ordinary, native)
            self.assertEqual(accepted["disposition_counts"]["SAME_RUN_NATIVE_REQUIRED"], 6)
            self.assertFalse(accepted["skips_are_passes"])
            forged = copy.deepcopy(native)
            forged["obligations"][target]["passed"][0] = target + "::wrong_same_count"
            with self.assertRaisesRegex(ValueError, "missing exact same-run native"):
                self.consumer.admit_skips(value, ordinary, forged)

    def test_missing_junit_and_reference_collection_disagreement_refuse(self):
        import xml.etree.ElementTree as ET
        self.full_bundle()
        path = next(item for root in self.artifacts.glob(self.prefix + "reference-*")
                    for item in (root / "parts").glob("*/pytest.xml")
                    if item.is_file() and b"collection skipped" in item.read_bytes())
        original = path.read_bytes()
        path.unlink()
        with self.assertRaises(ValueError): self.join()
        path.write_bytes(original)
        tree = ET.fromstring(original)
        suite = tree.find("testsuite")
        removed = 0
        for case in list(suite):
            skip = case.find("skipped")
            if skip is not None and skip.get("message") == "collection skipped":
                suite.remove(case)
                removed += 1
        self.assertEqual(removed, 1)
        path.write_bytes(ET.tostring(tree))
        with self.assertRaisesRegex(ValueError, "different collection skips"):
            self.join()


if __name__ == "__main__":
    unittest.main()
