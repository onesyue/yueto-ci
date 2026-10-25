"""Execute the real workflow shell, source-entry protocol and artifact join."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import itertools
import json
import os
import py_compile
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


class OpsShardWorkflow(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.ShardPrimitives()
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
        """Prepare two real Git lock blobs and a source-bound policy fixture."""
        lock = self.source / "frontend/package-lock.json"
        lock.parent.mkdir()
        value = {"packages": {"first": {"version": "1.0"}, "second": {"version": "1.0"}}}
        lock.write_text(json.dumps(value))
        self.fixture.git(self.source, "add", "frontend/package-lock.json")
        self.fixture.commit(self.source)
        before = self.fixture.git(self.source, "rev-parse", "HEAD").stdout.strip()
        baseline = copy.deepcopy(self.baseline)
        baseline["source_revision"] = before
        baseline["common_inputs"] = self.consumer.shared_inputs(self.source, before)
        raw = (json.dumps(baseline, indent=2, ensure_ascii=False) + "\n").encode()
        files = self.consumer.tree_inputs(self.source, before)
        value["packages"]["first"]["version"] = "1.1"
        lock.write_text(json.dumps(value))
        self.fixture.git(self.source, "add", "frontend/package-lock.json")
        self.fixture.commit(self.source)
        after = self.fixture.git(self.source, "rev-parse", "HEAD").stdout.strip()
        for row in self.targets["matrix"] + self.targets["validation_matrix"]:
            row["ref"] = after
        policy = self.policy / "ops-pytest-skip-baseline.json"
        policy.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, "shared collection/dependency inputs changed"):
            self.call(self.consumer.expand, self.targets, self.source,
                      self.board_sha, "ubuntu-24.04", 4, 4)
        baseline["reviewed_shared_input_transition"] = {
            "schema": 1, "original_baseline_sha256": self.consumer.sha(raw),
            "source_before": before, "source_after": after,
            "independent_review_sha256": "a" * 64, "source_freeze_sha256": "b" * 64,
            "path": "frontend/package-lock.json",
            "before_blob": files["frontend/package-lock.json"][1],
            "after_blob": self.consumer.tree_inputs(self.source, after)["frontend/package-lock.json"][1],
            "common_input_modes": {p: files[p][0] for p in baseline["common_inputs"]},
        }
        policy.write_text(json.dumps(baseline, indent=2, ensure_ascii=False) + "\n")
        self.fixture.git(self.policy, "add", "ops-pytest-skip-baseline.json")
        self.fixture.commit(self.policy)
        self.env["GITHUB_SHA"] = self.fixture.git(self.policy, "rev-parse", "HEAD").stdout.strip()
        self.admission = self.call(self.consumer.expand, self.targets, self.source,
                                   self.board_sha, "ubuntu-24.04", 4, 4)
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
        with self.assertRaisesRegex(ValueError, "shared collection/dependency inputs changed"):
            self.call(self.consumer.envelope, wrong)
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
        frontend_source = self.reviewed_lock_transition()
        policy = self.policy / "ops-pytest-skip-baseline.json"
        baseline = json.loads(policy.read_text())
        frontend = baseline["reviewed_shared_input_transition"]
        before = self.consumer.tree_inputs(self.source, frontend_source)
        for name in inputs:
            path = self.source / name
            path.write_text(path.read_text().replace("before", "after"))
        self.fixture.git(self.source, "add", *inputs)
        self.fixture.commit(self.source)
        python_source = self.fixture.git(self.source, "rev-parse", "HEAD").stdout.strip()
        after = self.consumer.tree_inputs(self.source, python_source)
        python_record = {
            "schema": 1, "original_baseline_sha256": frontend["original_baseline_sha256"],
            "prior_frontend_transition_sha256": self.consumer.sha(self.consumer.encoded(frontend)),
            "source_before": frontend_source, "source_after": python_source,
            "independent_review_sha256": "c" * 64, "source_freeze_sha256": "d" * 64,
            "changes": {name: {"before_blob": before[name][1], "after_blob": after[name][1],
                                "mode": "100644"} for name in inputs},
        }
        baseline["reviewed_python_input_transition"] = python_record
        lock = self.source / "frontend/package-lock.json"
        lock.write_text(lock.read_text().replace('"1.1"', '"1.2"'))
        self.fixture.git(self.source, "add", "frontend/package-lock.json")
        self.fixture.commit(self.source)
        security_source = self.fixture.git(self.source, "rev-parse", "HEAD").stdout.strip()
        security = {
            "schema": 1, "original_baseline_sha256": frontend["original_baseline_sha256"],
            "prior_transition_chain_sha256": self.consumer.sha(self.consumer.encoded({
                "reviewed_shared_input_transition": frontend,
                "reviewed_python_input_transition": python_record})),
            "source_before": python_source, "source_after": security_source,
            "independent_review_sha256": "e" * 64, "source_freeze_sha256": "f" * 64,
            "path": "frontend/package-lock.json", "before_blob": frontend["after_blob"],
            "after_blob": self.consumer.tree_inputs(self.source, security_source)[
                "frontend/package-lock.json"][1], "mode": "100644",
        }
        for row in self.targets["matrix"] + self.targets["validation_matrix"]:
            row["ref"] = security_source
        targets = self.base / "security-targets.json"
        targets.write_text(json.dumps(self.targets))
        command = [sys.executable, str(self.policy / "scripts/pytest-shards.py"), "expand",
                   "--targets", str(targets), "--source", str(self.source),
                   "--board", self.board_sha, "--runner", "ubuntu-24.04",
                   "--capacity", "4", "--shards", "4"]
        policy.write_text(json.dumps(baseline, indent=2, ensure_ascii=False) + "\n")
        rejected = subprocess.run(command, env=self.env, capture_output=True, text=True)
        self.assertEqual(rejected.returncode, 1, rejected.stdout + rejected.stderr)
        self.assertIn("shared collection/dependency inputs changed", rejected.stderr)
        baseline["reviewed_frontend_security_transition"] = security
        policy.write_text(json.dumps(baseline, indent=2, ensure_ascii=False) + "\n")
        self.fixture.git(self.policy, "add", "ops-pytest-skip-baseline.json")
        self.fixture.commit(self.policy)
        self.env["GITHUB_SHA"] = self.fixture.git(self.policy, "rev-parse", "HEAD").stdout.strip()
        admitted = subprocess.run(command, env=self.env, capture_output=True, text=True)
        self.assertEqual(admitted.returncode, 0, admitted.stdout + admitted.stderr)
        self.admission = json.loads(admitted.stdout)
        self.assertEqual(self.admission["common_inputs"][security["path"]], security["after_blob"])
        ran = self.run_role("reference")
        self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        wrong = copy.deepcopy(self.admission)
        wrong["common_inputs"]["uv.lock"] = before["uv.lock"][1]
        del wrong["admission_sha256"]
        self.consumer.seal(wrong, "admission_sha256")
        with self.assertRaisesRegex(ValueError, "shared collection/dependency inputs changed"):
            self.call(self.consumer.envelope, wrong)

    def test_miniapp_successor_reaches_expand_cli_reference_and_resealed_refusals(self):
        miniapp_path = "telegram-bot/yue/miniapp/package-lock.json"
        lock = self.source / miniapp_path
        lock.parent.mkdir(parents=True)
        lock.write_text('{"controlled_miniapp": "before"}\n')
        self.fixture.git(self.source, "add", miniapp_path)
        self.fixture.commit(self.source)
        # Preserve and execute the preceding transition's actual CLI/reference
        # controls before adding the separately admitted MiniApp-only commit.
        self.test_security_successor_reaches_expand_cli_and_reference_envelope()
        (self.base / "runner-reference").rename(self.base / "runner-reference-frontend")
        prior_reference = self.artifacts / (self.prefix + "reference")
        prior_reference.rename(self.artifacts / (self.prefix + "frontend-reference"))
        policy = self.policy / "ops-pytest-skip-baseline.json"
        baseline = json.loads(policy.read_text())
        security = baseline["reviewed_frontend_security_transition"]
        before = self.consumer.tree_inputs(self.source, security["source_after"])
        lock.write_text('{"controlled_miniapp": "after"}\n')
        self.fixture.git(self.source, "add", miniapp_path)
        self.fixture.commit(self.source)
        after_source = self.fixture.git(self.source, "rev-parse", "HEAD").stdout.strip()
        after = self.consumer.tree_inputs(self.source, after_source)
        for row in self.targets["matrix"] + self.targets["validation_matrix"]:
            row["ref"] = after_source
        targets = self.base / "miniapp-targets.json"
        targets.write_text(json.dumps(self.targets))
        command = [sys.executable, str(self.policy / "scripts/pytest-shards.py"), "expand",
                   "--targets", str(targets), "--source", str(self.source),
                   "--board", self.board_sha, "--runner", "ubuntu-24.04",
                   "--capacity", "4", "--shards", "4"]
        rejected = subprocess.run(command, env=self.env, capture_output=True, text=True)
        self.assertEqual(rejected.returncode, 1, rejected.stdout + rejected.stderr)
        self.assertIn("shared collection/dependency inputs changed", rejected.stderr)
        key = "reviewed_miniapp_security_transition"
        baseline[key] = {
            "schema": 1, "original_baseline_sha256": security["original_baseline_sha256"],
            "prior_transition_chain_sha256": self.consumer.sha(self.consumer.encoded({
                name: baseline[name] for name in ("reviewed_shared_input_transition",
                    "reviewed_python_input_transition", "reviewed_frontend_security_transition")})),
            "source_before": security["source_after"], "source_after": after_source,
            "independent_review_sha256": "1" * 64, "source_freeze_sha256": "2" * 64,
            "path": miniapp_path, "before_blob": before[miniapp_path][1],
            "after_blob": after[miniapp_path][1], "mode": "100644",
        }
        policy.write_text(json.dumps(baseline, indent=2, ensure_ascii=False) + "\n")
        self.fixture.git(self.policy, "add", "ops-pytest-skip-baseline.json")
        self.fixture.commit(self.policy)
        self.env["GITHUB_SHA"] = self.fixture.git(self.policy, "rev-parse", "HEAD").stdout.strip()
        admitted = subprocess.run(command, env=self.env, capture_output=True, text=True)
        self.assertEqual(admitted.returncode, 0, admitted.stdout + admitted.stderr)
        self.admission = json.loads(admitted.stdout)
        self.assertEqual(self.admission["common_inputs"][miniapp_path], after[miniapp_path][1])
        ran = self.run_role("reference")
        self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        self.call(self.consumer.envelope, self.admission)
        frontend = baseline["reviewed_shared_input_transition"]
        for path, blob in (("uv.lock", baseline["common_inputs"]["uv.lock"]),
                           ("frontend/package-lock.json", frontend["after_blob"]),
                           (miniapp_path, "0" * 40)):
            wrong = copy.deepcopy(self.admission)
            wrong["common_inputs"][path] = blob
            del wrong["admission_sha256"]
            self.consumer.seal(wrong, "admission_sha256")
            with self.subTest(resealed_path=path), self.assertRaisesRegex(ValueError, "inputs changed"):
                self.call(self.consumer.envelope, wrong)
        for mutation in ("omit", "null", "changed_predecessor_review", "changed_parent"):
            wrong_baseline = copy.deepcopy(baseline)
            if mutation == "omit":
                del wrong_baseline[key]
            elif mutation == "null":
                wrong_baseline[key] = None
            elif mutation == "changed_predecessor_review":
                wrong_baseline["reviewed_frontend_security_transition"]["independent_review_sha256"] = "0" * 64
            else:
                wrong_baseline[key]["source_before"] = "0" * 40
            policy.write_text(json.dumps(wrong_baseline, indent=2, ensure_ascii=False) + "\n")
            wrong = copy.deepcopy(self.admission)
            wrong["skip_baseline_sha256"] = self.consumer.sha(policy.read_bytes())
            del wrong["admission_sha256"]
            self.consumer.seal(wrong, "admission_sha256")
            with self.subTest(resealed_policy=mutation), self.assertRaises(ValueError):
                self.call(self.consumer.envelope, wrong)
            rejected = subprocess.run(command, env=self.env, capture_output=True, text=True)
            self.assertEqual(rejected.returncode, 1, rejected.stdout + rejected.stderr)
        policy.write_text(json.dumps(baseline, indent=2, ensure_ascii=False) + "\n")

    def test_reviewed_lock_does_not_waive_actual_new_skip(self):
        self.reviewed_lock_transition()
        with self.assertRaisesRegex(ValueError, "new or changed case skip"):
            self.full_bundle({"NEW_SKIP": "1"})

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
                reason = ("symlink shared test input" if change == "symlink" else
                          "shared collection/dependency input modes changed"
                          if change in ("added", "missing", "lock-mode", "other-mode") else
                          "shared collection/dependency inputs changed")
                with self.assertRaisesRegex(ValueError, reason):
                    self.call(self.consumer.expand, self.targets, self.source,
                              self.board_sha, "ubuntu-24.04", 4, 4)

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
        with self.assertRaisesRegex(ValueError, "shared collection/dependency inputs changed"):
            self.call(self.consumer.expand, self.targets, self.source,
                      self.board_sha, "ubuntu-24.04", 4, 4)
        new_files = self.consumer.tree_inputs(self.source, after)
        predecessor = baseline["reviewed_shared_input_transition"]
        baseline["reviewed_python_input_transition"] = {
            "schema": 1, "original_baseline_sha256": predecessor["original_baseline_sha256"],
            "prior_frontend_transition_sha256": self.consumer.sha(self.consumer.encoded(predecessor)),
            "source_before": before, "source_after": after,
            "independent_review_sha256": "c" * 64, "source_freeze_sha256": "d" * 64,
            "changes": {p: {"before_blob": old_files[p][1], "after_blob": new_files[p][1],
                            "mode": old_files[p][0]} for p in paths},
        }
        policy.write_text(json.dumps(baseline, indent=2, ensure_ascii=False) + "\n")
        self.fixture.git(self.policy, "add", "ops-pytest-skip-baseline.json")
        self.fixture.commit(self.policy)
        self.env["GITHUB_SHA"] = self.fixture.git(self.policy, "rev-parse", "HEAD").stdout.strip()
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
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "inputs changed"):
                wrong = copy.deepcopy(self.admission)
                wrong["common_inputs"][path] = "e" * 40
                del wrong["admission_sha256"]
                self.consumer.seal(wrong, "admission_sha256")
                self.call(self.consumer.envelope, wrong)
        (self.artifacts / (self.prefix + "native") / "native.json").unlink()
        with self.assertRaises(ValueError):
            self.join()

    def test_reviewed_python_inputs_still_reject_actual_new_skip(self):
        self.reviewed_python_transition()
        with self.assertRaisesRegex(ValueError, "new or changed case skip"):
            self.full_bundle({"NEW_SKIP": "1"})

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
        for role in ("reference", *[a["id"] for a in self.admission["ops_plan"]["assignments"]]):
            result = self.run_role(role, extra)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = self.run_role("native")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return self.join()

    def join(self, result="success", expected=None):
        return self.call(self.consumer.join, self.admission, self.artifacts, result,
                         expected or self.admission["admission_sha256"])

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
            env = self.env | {"RUNNER_TEMP": str(runner), "VALIDATION_RESULT": status,
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
        self.assertIn("needs: [plan, validate, validation-evidence]", workflow)
        self.assertLess(workflow.index("- name: Require complete selected validation and corpus"),
                        workflow.index("- name: Retain complete validation verdict"))

    def test_actual_selection_rejects_wrong_interpreter_identity(self):
        ran = self.run_role("reference")
        self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        root = self.artifacts / (self.prefix + "reference")
        directory = next(path for path in (root / "parts").iterdir() if path.is_dir())
        assignment = next(item for item in self.admission["ops_plan"]["assignments"]
                          if item["id"] == directory.name)
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

    def test_real_new_tool_skip_cannot_admit_images(self):
        with self.assertRaisesRegex(ValueError, "new or changed case skip"):
            self.full_bundle({"NEW_SKIP": "1"})

    def test_real_new_import_skip_cannot_hide_in_matching_empty_corpora(self):
        with self.assertRaisesRegex(ValueError, "new or changed collection skip"):
            self.full_bundle({"NEW_COLLECTION": "1"})

    def test_real_changed_collection_skip_reason_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "new or changed collection skip"):
            self.full_bundle({"COLLECTION_REASON": "changed dependency reason"})

    def test_changed_skip_module_and_shared_inputs_require_reviewed_refresh(self):
        path = self.source / "tests/test_a.py"
        path.write_text(path.read_text() + "\n# Changed skipped module.\n")
        self.fixture.git(self.source, "add", "tests/test_a.py")
        self.fixture.commit(self.source)
        revision = self.fixture.git(self.source, "rev-parse", "HEAD").stdout.strip()
        for row in self.targets["matrix"] + self.targets["validation_matrix"]:
            row["ref"] = revision
        self.admission = self.call(self.consumer.expand, self.targets, self.source,
                                   self.board_sha, "ubuntu-24.04", 4, 4)
        with self.assertRaisesRegex(ValueError, "new or changed case skip"):
            self.full_bundle()
        for name in ("pytest.ini", "uv.lock"):
            path = self.source / name
            path.write_text((path.read_text() if path.exists() else "") + "\n# Changed input.\n")
            self.fixture.git(self.source, "add", name)
            self.fixture.commit(self.source)
            revision = self.fixture.git(self.source, "rev-parse", "HEAD").stdout.strip()
            for row in self.targets["matrix"] + self.targets["validation_matrix"]:
                row["ref"] = revision
            with self.assertRaisesRegex(ValueError, "shared collection/dependency inputs"):
                self.call(self.consumer.expand, self.targets, self.source,
                          self.board_sha, "ubuntu-24.04", 4, 4)

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
        with self.assertRaisesRegex(ValueError, "new or changed case skip"):
            self.consumer.admit_skips(wrong, result["ordinary"], result["native_and_source_gates"])
        # Independent qualification cannot replace this run's original native gates.
        (self.artifacts / (self.prefix + "native") / "native.json").unlink()
        with self.assertRaises(ValueError):
            self.join()

    def test_reviewed_ssh_transition_keeps_actual_original_source_admission(self):
        self.reviewed_ssh_skip_transition(original_source=True)
        result = self.full_bundle()
        self.assertEqual(result["status"], "VALIDATION_MATRIX_COMPLETE")
        self.assertFalse(result["skip_admission"]["skips_are_passes"])

    def test_reviewed_ssh_transition_rejects_actual_new_case_skip(self):
        self.reviewed_ssh_skip_transition()
        with self.assertRaisesRegex(ValueError, "new or changed case skip"):
            self.full_bundle({"NEW_SKIP": "1"})

    def test_reviewed_ssh_transition_rejects_actual_changed_skip_reason(self):
        self.reviewed_ssh_skip_transition()
        with self.assertRaisesRegex(ValueError, "new or changed case skip"):
            self.full_bundle({"SSH_REVIEWED_REASON": "different but plausible missing tool"})

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
        self.assertEqual([m["ops_role"] for m in value["validation_matrix"][:3]],
                         ["native", "reference", "serial"])
        self.assertEqual([m for m in value["validation_matrix"] if m["validation"] != "yueops"], other)
        self.assertEqual(len(value["validation_matrix"]), 11)
        self.assertEqual(list(self.artifacts.iterdir()), [])
        self.assertIn("admission_sha256=", output.read_text())

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
        self.assertIn("needs: [plan, validate, validation-evidence]", text)
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
        self.assertNotIn("continue-on-error", text[text.index("  validate:\n"):text.index("  build:\n")]
                         .replace("continue-on-error: true", "", 2))


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
        with self.assertRaisesRegex(ValueError, "new or changed case skip"):
            self.consumer.admit_skips(self.admission, ordinary, result["native_and_source_gates"])

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
        parts = self.artifacts / (self.prefix + "reference") / "parts"
        path = next(item for item in parts.glob("*/pytest.xml")
                    if b"collection skipped" in item.read_bytes())
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


class ReviewedW85InputPolicy(unittest.TestCase):
    def setUp(self):
        self.consumer = fixture.SHARDS
        full = self.consumer.skip_baseline()
        full, _ = self.consumer.reviewed_audit_dependency_transition(full)
        self.baseline, _ = self.consumer.reviewed_w85_observability_transition(full)
        self.key = "reviewed_w85_input_transition"
        self.record = self.baseline[self.key]
        self.maps = [dict(self.baseline["common_inputs"])]
        for key in ("reviewed_shared_input_transition", "reviewed_python_input_transition",
                    "reviewed_frontend_security_transition", "reviewed_miniapp_security_transition",
                    self.key):
            record = self.baseline[key]
            changes = ({p: c["after_blob"] for p, c in record["changes"].items()}
                       if "changes" in record else {record["path"]: record["after_blob"]})
            self.maps.append(self.maps[-1] | changes)
        self.modes = self.baseline["reviewed_shared_input_transition"]["common_input_modes"]

    def files(self, common):
        return {p: (self.modes[p], blob) for p, blob in common.items()}

    def test_exact_w85_record_preserves_entire_prior_policy_and_skip_evidence(self):
        original, record = self.consumer.reviewed_w85_input_transition(self.baseline)
        raw = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
        self.assertEqual(self.consumer.sha(raw),
                         "f32c36a2e73051004a1b2cf164cdfb09204e14a0247361cdc6974f6080a3d779")
        self.assertEqual(record["source_after"], "1d8ae9784b709ebb220f064c52a33ef42d3a5145")
        self.assertEqual(record["qualified_policy_revision"], "c7e67c4b51cdc9c12d2779b2618be3ef608f3ccf")
        self.assertEqual(len(original["cases"]), 1005)
        self.assertEqual(len(original["collection_skips"]), 1)
        self.assertEqual(len(original["reviewed_hosted"]["cases"]), 18)
        self.assertEqual(self.consumer.reviewed_skip_module_transition(self.baseline),
                         self.consumer.reviewed_skip_module_transition(original))
        for common in self.maps[:-1]:
            self.consumer.admit_shared_inputs(original, common, self.files(common))
        with self.assertRaisesRegex(ValueError, "inputs changed"):
            self.consumer.admit_shared_inputs(original, self.maps[-1], self.files(self.maps[-1]))

    def test_all_108_dependency_combinations_admit_only_six_complete_maps(self):
        paths = ["frontend/package-lock.json", "pyproject.toml", "uv.lock",
                 "telegram-bot/yue/requirements.txt", "telegram-bot/yue/miniapp/package-lock.json"]
        variants = [list(dict.fromkeys(m[p] for m in self.maps)) for p in paths]
        attempted = accepted = 0
        for blobs in itertools.product(*variants):
            common = self.maps[0] | dict(zip(paths, blobs, strict=True))
            attempted += 1
            with self.subTest(blobs=blobs):
                if common in self.maps:
                    self.consumer.admit_shared_inputs(self.baseline, common, self.files(common))
                    accepted += 1
                else:
                    with self.assertRaisesRegex(ValueError, "inputs changed"):
                        self.consumer.admit_shared_inputs(self.baseline, common, self.files(common))
        self.assertEqual((attempted, accepted), (108, 6))

    def test_record_and_entire_history_drift_refuse_even_valid_hash_shapes(self):
        mutations = []
        for field in self.record:
            changed = copy.deepcopy(self.baseline)
            del changed[self.key][field]
            mutations.append(("missing-" + field, changed))
        for field in ("prior_baseline_sha256", "independent_review_sha256",
                      "source_freeze_sha256", "dependency_audit_sha256",
                      "source_before", "source_after", "qualified_policy_revision"):
            changed = copy.deepcopy(self.baseline)
            changed[self.key][field] = "f" * len(self.record[field])
            mutations.append((field, changed))
        for path in self.record["changes"]:
            for field, value in (("before_blob", "f" * 40), ("after_blob", "f" * 40),
                                 ("mode", "100755"), ("extra", True)):
                changed = copy.deepcopy(self.baseline)
                changed[self.key]["changes"][path][field] = value
                mutations.append((path + field, changed))
        for key in self.baseline:
            if key == self.key:
                continue
            changed = copy.deepcopy(self.baseline)
            del changed[key]
            mutations.append(("missing-history-" + key, changed))
        for key in ("reviewed_miniapp_security_transition", "reviewed_ssh_skip_module_transition"):
            changed = copy.deepcopy(self.baseline)
            changed[key]["independent_review_sha256"] = "f" * 64
            mutations.append(("changed-review-" + key, changed))
        changed = copy.deepcopy(self.baseline)
        changed["cases"][next(iter(changed["cases"]))]["reason"] = "Skipped: invented new reason"
        mutations.append(("historical-skip-reason", changed))
        for value in (None, [], False):
            mutations.append(("invalid-record-" + str(value), self.baseline | {self.key: value}))
        for label, changed in mutations:
            for common in self.maps:
                with self.subTest(mutation=label, common=common), self.assertRaises(ValueError):
                    self.consumer.admit_shared_inputs(changed, common)

    def test_all_55_inputs_keep_blob_mode_membership_and_no_unknown_path(self):
        common = self.maps[-1]
        self.assertEqual(len(common), 55)
        files = self.files(common)
        for path in common:
            with self.subTest(blob=path), self.assertRaises(ValueError):
                self.consumer.admit_shared_inputs(self.baseline, common | {path: "f" * 40}, files)
            for mode in ("100755", "120000"):
                with self.subTest(path=path, mode=mode), self.assertRaises(ValueError):
                    self.consumer.admit_shared_inputs(
                        self.baseline, common, files | {path: (mode, files[path][1])})
            with self.subTest(missing=path), self.assertRaises(ValueError):
                self.consumer.admit_shared_inputs(
                    self.baseline, {p: b for p, b in common.items() if p != path}, files)
        with self.assertRaises(ValueError):
            self.consumer.admit_shared_inputs(self.baseline, common | {"new.lock": "f" * 40}, files)

    def test_sealed_current_map_keeps_source_policy_and_mixed_input_refusals(self):
        policy = self.consumer.git(ROOT, "rev-parse", "HEAD").decode().strip()
        identity = {"policy_revision": policy, "run_id": "42", "run_attempt": "1"}
        board = "5046b327de669b1aa83907772db37da1f261a98b"
        source = self.record["source_after"]
        plan = self.consumer.seal({
            "schema": 1, "kind": "ops-pytest-module-plan", "source_revision": source,
            "context": identity | {"board_revision": board, "runner_os": "Linux",
                                    "runner_arch": "X64", "runner_image": "controlled-image"},
            "pytest_ini_sha256": "a" * 64, "entry_sha256": "b" * 64,
            "recorder_sha256": "c" * 64, "modules": {"tests/test_control.py": "d" * 64},
            "assignments": [{"id": "ordinary-000", "modules": ["tests/test_control.py"]}],
        }, "plan_sha256")
        value = self.consumer.seal({
            "schema": 1, "identity": identity, "mode": "sharded", "source_revision": source,
            "board_revision": board, "ops_plan": plan, "common_inputs": self.maps[-1],
            "skip_baseline_sha256": self.consumer.sha((ROOT / self.consumer.SKIP_BASELINE).read_bytes()),
            "skip_module_blobs": {"tests/test_control.py": "e" * 40},
            "validation_matrix": [{"validation": "yueops", "repo": "onesyue/yueops",
                                   "ref": source, "ops_role": role}
                                  for role in self.consumer.role_order(plan)],
        }, "admission_sha256")
        env = {"GITHUB_SHA": policy, "GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": "1",
               "GITHUB_REPOSITORY": "onesyue/yueto-ci"}
        with patch.dict(os.environ, env):
            self.consumer.envelope(value)
            for path in self.record["changes"]:
                wrong = copy.deepcopy(value)
                wrong["common_inputs"][path] = self.record["changes"][path]["before_blob"]
                del wrong["admission_sha256"]
                self.consumer.seal(wrong, "admission_sha256")
                with self.subTest(resealed_path=path), self.assertRaisesRegex(ValueError, "inputs changed"):
                    self.consumer.envelope(wrong)
            for kind in ("source", "policy", "baseline"):
                wrong = copy.deepcopy(value)
                if kind == "source":
                    wrong["source_revision"] = "f" * 40
                elif kind == "policy":
                    wrong["identity"]["policy_revision"] = "f" * 40
                else:
                    wrong["skip_baseline_sha256"] = "f" * 64
                del wrong["admission_sha256"]
                self.consumer.seal(wrong, "admission_sha256")
                with self.subTest(resealed_identity=kind), self.assertRaises(ValueError):
                    self.consumer.envelope(wrong)


class ReviewedHostedSkipPolicy(unittest.TestCase):
    def setUp(self):
        self.consumer = fixture.SHARDS
        full = self.consumer.skip_baseline()
        full, _ = self.consumer.reviewed_audit_dependency_transition(full)
        self.baseline, _ = self.consumer.reviewed_w85_observability_transition(full)
        self.baseline.pop("reviewed_w85_input_transition")
        self.ssh_record = self.baseline.pop("reviewed_ssh_skip_module_transition")
        self.reviewed = self.baseline["reviewed_hosted"]
        self.value = {"skip_baseline_sha256": "a" * 64,
                      "ops_plan": {"context": {"runner_os": "Linux", "runner_arch": "X64"}},
                      "skip_module_blobs": {n.split("::")[0]: r["module_blob"]
                                            for n, r in self.reviewed["cases"].items()}}

    def result(self, rows):
        session = {"execution_context": self.baseline["context"], "collection_skips": {},
                   "junit_sha256": "b" * 64, "nonpassing_outcomes": []}
        return {"reference": session | {"assignment_id": "reference"},
                "shards": [session | {"assignment_id": "ordinary-000", "nonpassing_outcomes": rows}]}

    def test_exact_ssh_record_and_all_validly_shaped_identity_mutations(self):
        baseline = self.baseline | {"reviewed_ssh_skip_module_transition": self.ssh_record}
        original, successors = self.consumer.reviewed_skip_module_transition(baseline)
        self.assertEqual(original, self.baseline)
        self.assertEqual(self.ssh_record["prior_baseline_sha256"],
                         "8332986b05c7036540653f9ed8f85813bacb720c90a2252c3453de254dfd89ae")
        self.assertEqual(set(successors), self.consumer.SSH_SKIP_CASES)
        mutations = []
        for field in ("prior_baseline_sha256", "independent_review_sha256", "source_freeze_sha256",
                      "qualification_receipt_sha256", "composition_review_sha256"):
            changed = copy.deepcopy(baseline)
            changed["reviewed_ssh_skip_module_transition"][field] = "f" * 64
            mutations.append((field, changed))
        for field in ("source_before", "source_after", "qualified_source"):
            changed = copy.deepcopy(baseline)
            changed["reviewed_ssh_skip_module_transition"][field] = "f" * 40
            mutations.append((field, changed))
        for nodeid in sorted(self.consumer.SSH_SKIP_CASES):
            for field in ("before_blob", "after_blob"):
                changed = copy.deepcopy(baseline)
                changed["reviewed_ssh_skip_module_transition"]["cases"][nodeid][field] = "f" * 40
                mutations.append((nodeid + field, changed))
        for label, changed in mutations:
            with self.subTest(mutation=label), self.assertRaisesRegex(ValueError, "transition identity"):
                self.consumer.reviewed_skip_module_transition(changed)
        for mutation in ("missing", "null", "additional_case", "historical_reason"):
            changed = copy.deepcopy(baseline)
            if mutation == "missing":
                del changed["reviewed_ssh_skip_module_transition"]["source_freeze_sha256"]
            elif mutation == "null":
                changed["reviewed_ssh_skip_module_transition"] = None
            elif mutation == "additional_case":
                changed["reviewed_ssh_skip_module_transition"]["cases"]["tests/test_other.py::test_skip"] = {}
            else:
                changed["cases"][sorted(self.consumer.SSH_SKIP_CASES)[0]]["reason"] = "Skipped: changed"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.consumer.reviewed_skip_module_transition(changed)

    def test_exact_original_baseline_and_historical_collection_are_preserved(self):
        import hashlib
        original = dict(self.baseline)
        miniapp_record = original.pop("reviewed_miniapp_security_transition")
        prior_bytes = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
        self.assertEqual(hashlib.sha256(prior_bytes).hexdigest(),
                         "c88859a02e303a79a784e4f51db1faa7ffddf1adb26ec45d7c42f90e7aa36edd")
        self.assertEqual(miniapp_record["prior_transition_chain_sha256"],
                         self.consumer.sha(self.consumer.encoded({name: original[name] for name in (
                             "reviewed_shared_input_transition", "reviewed_python_input_transition",
                             "reviewed_frontend_security_transition")})))
        security_record = original.pop("reviewed_frontend_security_transition")
        python_record = original.pop("reviewed_python_input_transition")
        frontend_bytes = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
        self.assertEqual(hashlib.sha256(frontend_bytes).hexdigest(),
                         "a78106fca2d61bcbb1cd7e72435eccc9c8f65bfaf4f82a6661f19bc3e4dc7061")
        record = original.pop("reviewed_shared_input_transition")
        restored = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
        self.assertEqual(hashlib.sha256(restored).hexdigest(),
                         "49d7462f8d59b9a9a035d36fc113647f82a01c71079886c053fc637da2092e9f")
        self.assertEqual(record["original_baseline_sha256"], hashlib.sha256(restored).hexdigest())
        self.assertEqual(python_record["original_baseline_sha256"], hashlib.sha256(restored).hexdigest())
        self.assertEqual(python_record["prior_frontend_transition_sha256"],
                         self.consumer.sha(self.consumer.encoded(record)))
        self.assertEqual(security_record["original_baseline_sha256"], hashlib.sha256(restored).hexdigest())
        self.assertEqual(security_record["prior_transition_chain_sha256"],
                         self.consumer.sha(self.consumer.encoded({
                             "reviewed_shared_input_transition": record,
                             "reviewed_python_input_transition": python_record})))
        del original["reviewed_hosted"]
        digest = hashlib.sha256((json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()).hexdigest()
        self.assertEqual(digest, self.reviewed["observation"]["original_baseline_sha256"])
        self.assertEqual(len(original["cases"]), 1005)
        self.assertEqual(len(original["collection_skips"]), 1)
        self.assertEqual(len(self.reviewed["cases"]), 18)

    def test_reviewed_shared_input_preserves_all_55_inputs_and_rejects_other_changes(self):
        record = self.baseline["reviewed_shared_input_transition"]
        original = self.baseline["common_inputs"]
        self.assertEqual(len(original), 55)
        self.assertEqual(record["source_after"], "a2a16b8f66185c7b73e50aafd6d40e79faa4ad75")
        self.assertEqual(record["independent_review_sha256"],
                         "77ac618111acb7e27a683e009460a77a1376afb240c4bc16910df16777854449")
        self.assertEqual(record["source_freeze_sha256"],
                         "8d25e29294003c98fa28a7e7a0542f1cad5933c0d6311fe7935d0c8ad6cd49f6")
        self.assertEqual(record["before_blob"], "e265053bb00e8a6cc36bef7c5f37c29fdd7c2936")
        self.assertEqual(record["after_blob"], "5383263b00bee86a0a1ac093ab2360e9ea828cde")
        effective = original | {record["path"]: record["after_blob"]}
        files = {p: (record["common_input_modes"][p], b) for p, b in effective.items()}
        self.consumer.admit_shared_inputs(self.baseline, original, files)
        self.consumer.admit_shared_inputs(self.baseline, effective, files)
        for path in original:
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.consumer.admit_shared_inputs(self.baseline, effective | {path: "c" * 40}, files)
            with self.subTest(mode=path), self.assertRaises(ValueError):
                wrong = files | {path: ("100755" if files[path][0] == "100644" else "100644",
                                       files[path][1])}
                self.consumer.admit_shared_inputs(self.baseline, effective, wrong)
        for key in record:
            with self.subTest(missing=key), self.assertRaises(ValueError):
                wrong = copy.deepcopy(self.baseline)
                del wrong["reviewed_shared_input_transition"][key]
                self.consumer.admit_shared_inputs(wrong, effective, files)

        for key, value in (("path", "frontend/other-lock.json"),
                           ("before_blob", "d" * 40), ("original_baseline_sha256", "e" * 64),
                           ("source_after", "UNKNOWN"), ("independent_review_sha256", "UNKNOWN"),
                           ("common_input_modes", {})):
            with self.subTest(key=key), self.assertRaises(ValueError):
                wrong = copy.deepcopy(self.baseline)
                wrong["reviewed_shared_input_transition"][key] = value
                self.consumer.admit_shared_inputs(wrong, effective, files)

    def test_python_transition_all_16_complete_input_maps(self):
        baseline = self.baseline
        record = baseline["reviewed_python_input_transition"]
        frontend = baseline["reviewed_shared_input_transition"]
        self.assertEqual(record["source_before"], frontend["source_after"])
        self.assertEqual(record["source_after"], "5cbb65a1b6d7a02a509f97e26291ec53ef855645")
        self.assertEqual(record["independent_review_sha256"],
                         "8b87cb3d92e8eea856f891af9a01d7102bbf06e4bd29bc351e2b02c165c69a82")
        self.assertEqual(record["source_freeze_sha256"],
                         "b3308860976dbcec269212e44c623ad79fe52b8f1ca4ec9f9f9e89cd8520919b")
        changes = {frontend["path"]: frontend["after_blob"]} | {
            p: c["after_blob"] for p, c in record["changes"].items()}
        accepted = []
        for bits in itertools.product((0, 1), repeat=4):
            common = dict(baseline["common_inputs"])
            common.update({p: b for bit, (p, b) in zip(bits, changes.items(), strict=True) if bit})
            files = {p: (frontend["common_input_modes"][p], b) for p, b in common.items()}
            with self.subTest(bits=bits):
                if bits in ((0, 0, 0, 0), (1, 0, 0, 0), (1, 1, 1, 1)):
                    self.consumer.admit_shared_inputs(baseline, common, files)
                    accepted.append(bits)
                else:
                    with self.assertRaisesRegex(ValueError, "inputs changed"):
                        self.consumer.admit_shared_inputs(baseline, common, files)
        self.assertEqual(len(accepted), 3)

    def test_python_transition_rejects_record_and_predecessor_drift_on_every_map(self):
        record = self.baseline["reviewed_python_input_transition"]
        frontend = self.baseline["reviewed_shared_input_transition"]
        original = self.baseline["common_inputs"]
        effective = original | {frontend["path"]: frontend["after_blob"]}
        converted = effective | {p: c["after_blob"] for p, c in record["changes"].items()}
        mutations = []
        for key in record:
            wrong = copy.deepcopy(self.baseline)
            del wrong["reviewed_python_input_transition"][key]
            mutations.append(("missing-" + key, wrong))
        for key, value in (("unknown", True), ("schema", 2),
                           ("original_baseline_sha256", "a" * 64),
                           ("prior_frontend_transition_sha256", "b" * 64),
                           ("source_before", "c" * 40), ("source_after", "UNKNOWN"),
                           ("independent_review_sha256", None), ("source_freeze_sha256", "UNKNOWN")):
            wrong = copy.deepcopy(self.baseline)
            wrong["reviewed_python_input_transition"][key] = value
            mutations.append((key, wrong))
        for path in record["changes"]:
            for key, value in (("before_blob", "e" * 40), ("after_blob", "UNKNOWN"),
                               ("after_blob", record["changes"][path]["before_blob"]),
                               ("mode", "100755"), ("extra", True)):
                wrong = copy.deepcopy(self.baseline)
                wrong["reviewed_python_input_transition"]["changes"][path][key] = value
                mutations.append((path + key + str(value), wrong))
            wrong = copy.deepcopy(self.baseline)
            del wrong["reviewed_python_input_transition"]["changes"][path]
            mutations.append(("missing-path-" + path, wrong))
        wrong = copy.deepcopy(self.baseline)
        wrong["reviewed_python_input_transition"]["changes"]["requirements.txt"] = dict(
            next(iter(record["changes"].values())))
        mutations.append(("unknown-path", wrong))
        for kind in ("missing-predecessor", "changed-predecessor", "changed-history", "null"):
            wrong = copy.deepcopy(self.baseline)
            if kind == "missing-predecessor":
                del wrong["reviewed_shared_input_transition"]
            elif kind == "changed-predecessor":
                wrong["reviewed_shared_input_transition"]["independent_review_sha256"] = "e" * 64
            elif kind == "changed-history":
                wrong["source_revision"] = "f" * 40
            else:
                wrong["reviewed_python_input_transition"] = None
            mutations.append((kind, wrong))
        for label, wrong in mutations:
            for index, common in enumerate((original, effective, converted)):
                with self.subTest(mutation=label, map=index), self.assertRaises(ValueError):
                    self.consumer.admit_shared_inputs(wrong, common)

    def test_python_transition_keeps_all_input_blobs_modes_and_members(self):
        frontend = self.baseline["reviewed_shared_input_transition"]
        record = self.baseline["reviewed_python_input_transition"]
        common = self.baseline["common_inputs"] | {frontend["path"]: frontend["after_blob"]}
        common.update({p: c["after_blob"] for p, c in record["changes"].items()})
        files = {p: (frontend["common_input_modes"][p], b) for p, b in common.items()}
        for path in common:
            with self.subTest(blob=path), self.assertRaises(ValueError):
                self.consumer.admit_shared_inputs(self.baseline, common | {path: "d" * 40}, files)
            for mode in ("100755", "120000"):
                with self.subTest(path=path, mode=mode), self.assertRaises(ValueError):
                    self.consumer.admit_shared_inputs(
                        self.baseline, common, files | {path: (mode, files[path][1])})
            with self.subTest(missing=path), self.assertRaises(ValueError):
                self.consumer.admit_shared_inputs(self.baseline, {p: b for p, b in common.items()
                                                                  if p != path}, files)
        with self.assertRaises(ValueError):
            self.consumer.admit_shared_inputs(self.baseline, common | {"new.lock": "e" * 40}, files)

    def security_maps(self):
        original = self.baseline["common_inputs"]
        frontend = self.baseline["reviewed_shared_input_transition"]
        python_record = self.baseline["reviewed_python_input_transition"]
        security = self.baseline["reviewed_frontend_security_transition"]
        effective = original | {frontend["path"]: frontend["after_blob"]}
        converted = effective | {p: c["after_blob"] for p, c in python_record["changes"].items()}
        secured = converted | {security["path"]: security["after_blob"]}
        return original, effective, converted, secured

    def test_security_transition_all_24_complete_input_maps(self):
        frontend = self.baseline["reviewed_shared_input_transition"]
        python_record = self.baseline["reviewed_python_input_transition"]
        security = self.baseline["reviewed_frontend_security_transition"]
        maps = self.security_maps()
        self.assertEqual(security["before_blob"], frontend["after_blob"])
        accepted = []
        for lock, bits in itertools.product(range(3), itertools.product((0, 1), repeat=3)):
            common = dict(maps[0])
            common[security["path"]] = (frontend["before_blob"], frontend["after_blob"],
                                         security["after_blob"])[lock]
            for bit, (path, change) in zip(bits, python_record["changes"].items(), strict=True):
                if bit:
                    common[path] = change["after_blob"]
            files = {p: (frontend["common_input_modes"][p], b) for p, b in common.items()}
            with self.subTest(lock=lock, python=bits):
                if common in maps:
                    self.consumer.admit_shared_inputs(self.baseline, common, files)
                    accepted.append((lock, bits))
                else:
                    with self.assertRaisesRegex(ValueError, "inputs changed"):
                        self.consumer.admit_shared_inputs(self.baseline, common, files)
        self.assertEqual(len(accepted), 4)

    def test_security_transition_rejects_record_or_history_drift_on_every_map(self):
        key = "reviewed_frontend_security_transition"
        record = self.baseline[key]
        mutations = []
        for field in record:
            wrong = copy.deepcopy(self.baseline)
            del wrong[key][field]
            mutations.append(("missing-" + field, wrong))
        for field, value in (("schema", True), ("schema", 2), ("extra", True),
                             ("original_baseline_sha256", "0" * 64),
                             ("prior_transition_chain_sha256", "0" * 64),
                             ("source_before", "UNKNOWN"), ("source_after", record["source_before"]),
                             ("independent_review_sha256", None), ("source_freeze_sha256", "UNKNOWN"),
                             ("path", "frontend/package.json"), ("mode", "100755"),
                             ("before_blob", "0" * 40), ("after_blob", record["before_blob"]),
                             ("after_blob", "UNKNOWN")):
            wrong = copy.deepcopy(self.baseline)
            wrong[key][field] = value
            mutations.append((field + str(value), wrong))
        for predecessor in ("reviewed_shared_input_transition", "reviewed_python_input_transition"):
            wrong = copy.deepcopy(self.baseline)
            del wrong[predecessor]
            mutations.append(("missing-" + predecessor, wrong))
            wrong = copy.deepcopy(self.baseline)
            wrong[predecessor]["independent_review_sha256"] = "0" * 64
            mutations.append(("changed-" + predecessor, wrong))
        for value in (None, [], False):
            mutations.append(("invalid-record-" + str(value), self.baseline | {key: value}))
        for label, wrong in mutations:
            for index, common in enumerate(self.security_maps()):
                with self.subTest(mutation=label, map=index), self.assertRaises(ValueError):
                    self.consumer.admit_shared_inputs(wrong, common)

    def test_security_transition_preserves_all_inputs_modes_and_omission_refusal(self):
        frontend = self.baseline["reviewed_shared_input_transition"]
        *historical, common = self.security_maps()
        files = {p: (frontend["common_input_modes"][p], b) for p, b in common.items()}
        omitted = dict(self.baseline)
        # Exercise the exact historical policy without either security successor.
        omitted.pop("reviewed_miniapp_security_transition")
        del omitted["reviewed_frontend_security_transition"]
        for old in historical:
            self.consumer.admit_shared_inputs(omitted, old, files)
        with self.assertRaisesRegex(ValueError, "inputs changed"):
            self.consumer.admit_shared_inputs(omitted, common, files)
        for path in common:
            with self.subTest(blob=path), self.assertRaises(ValueError):
                self.consumer.admit_shared_inputs(self.baseline, common | {path: "0" * 40}, files)
            for mode in ("100755", "120000"):
                with self.subTest(path=path, mode=mode), self.assertRaises(ValueError):
                    self.consumer.admit_shared_inputs(
                        self.baseline, common, files | {path: (mode, files[path][1])})
            with self.subTest(missing=path), self.assertRaises(ValueError):
                self.consumer.admit_shared_inputs(self.baseline, {p: b for p, b in common.items()
                                                                  if p != path}, files)
        with self.assertRaises(ValueError):
            self.consumer.admit_shared_inputs(self.baseline, common | {"new.lock": "0" * 40}, files)

    def miniapp_maps(self):
        historical = self.security_maps()
        record = self.baseline["reviewed_miniapp_security_transition"]
        return (*historical, historical[-1] | {record["path"]: record["after_blob"]})

    def test_miniapp_transition_all_48_complete_input_maps(self):
        frontend = self.baseline["reviewed_shared_input_transition"]
        python_record = self.baseline["reviewed_python_input_transition"]
        security = self.baseline["reviewed_frontend_security_transition"]
        miniapp = self.baseline["reviewed_miniapp_security_transition"]
        maps = self.miniapp_maps()
        self.assertEqual(miniapp["source_before"], security["source_after"])
        self.assertEqual(miniapp["before_blob"], maps[0][miniapp["path"]])
        accepted, attempted = [], 0
        for lock, bits, mini in itertools.product(range(3), itertools.product((0, 1), repeat=3), (0, 1)):
            common = dict(maps[0])
            common[security["path"]] = (frontend["before_blob"], frontend["after_blob"],
                                         security["after_blob"])[lock]
            common[miniapp["path"]] = (miniapp["before_blob"], miniapp["after_blob"])[mini]
            for bit, (path, change) in zip(bits, python_record["changes"].items(), strict=True):
                if bit:
                    common[path] = change["after_blob"]
            files = {p: (frontend["common_input_modes"][p], b) for p, b in common.items()}
            with self.subTest(lock=lock, python=bits, miniapp=mini):
                attempted += 1
                if common in maps:
                    self.consumer.admit_shared_inputs(self.baseline, common, files)
                    accepted.append((lock, bits, mini))
                else:
                    with self.assertRaisesRegex(ValueError, "inputs changed"):
                        self.consumer.admit_shared_inputs(self.baseline, common, files)
        self.assertEqual((attempted, len(accepted)), (48, 5))

    def test_miniapp_transition_rejects_record_history_and_predecessor_drift(self):
        key = "reviewed_miniapp_security_transition"
        record = self.baseline[key]
        mutations = []
        for field in record:
            wrong = copy.deepcopy(self.baseline)
            del wrong[key][field]
            mutations.append(("missing-" + field, wrong))
        for field, value in (("schema", True), ("schema", 2), ("extra", True),
                             ("original_baseline_sha256", "0" * 64),
                             ("prior_transition_chain_sha256", "0" * 64),
                             ("source_before", "0" * 40), ("source_after", record["source_before"]),
                             ("source_after", "UNKNOWN"), ("independent_review_sha256", None),
                             ("source_freeze_sha256", "UNKNOWN"),
                             ("path", "frontend/package-lock.json"), ("mode", "100755"),
                             ("before_blob", "0" * 40), ("after_blob", record["before_blob"]),
                             ("after_blob", "UNKNOWN")):
            wrong = copy.deepcopy(self.baseline)
            wrong[key][field] = value
            mutations.append((field + str(value), wrong))
        for predecessor in ("reviewed_shared_input_transition", "reviewed_python_input_transition",
                            "reviewed_frontend_security_transition"):
            for mutation in ("missing", "null", "changed-review", "changed-freeze"):
                wrong = copy.deepcopy(self.baseline)
                if mutation == "missing":
                    del wrong[predecessor]
                elif mutation == "null":
                    wrong[predecessor] = None
                else:
                    field = "independent_review_sha256" if mutation == "changed-review" else "source_freeze_sha256"
                    wrong[predecessor][field] = "0" * 64
                mutations.append((mutation + predecessor, wrong))
        wrong = copy.deepcopy(self.baseline)
        wrong["source_revision"] = "0" * 40
        mutations.append(("changed-original-history", wrong))
        for value in (None, [], False):
            mutations.append(("invalid-record-" + str(value), self.baseline | {key: value}))
        for label, wrong in mutations:
            for index, common in enumerate(self.miniapp_maps()):
                with self.subTest(mutation=label, map=index), self.assertRaises(ValueError):
                    self.consumer.admit_shared_inputs(wrong, common)

    def test_miniapp_transition_preserves_all_inputs_modes_and_omission_refusal(self):
        frontend = self.baseline["reviewed_shared_input_transition"]
        *historical, common = self.miniapp_maps()
        self.assertEqual(len(common), 55)
        files = {p: (frontend["common_input_modes"][p], b) for p, b in common.items()}
        omitted = dict(self.baseline)
        del omitted["reviewed_miniapp_security_transition"]
        for old in historical:
            self.consumer.admit_shared_inputs(omitted, old, files)
        with self.assertRaisesRegex(ValueError, "inputs changed"):
            self.consumer.admit_shared_inputs(omitted, common, files)
        for path in common:
            with self.subTest(blob=path), self.assertRaises(ValueError):
                self.consumer.admit_shared_inputs(self.baseline, common | {path: "0" * 40}, files)
            for mode in ("100755", "120000"):
                with self.subTest(path=path, mode=mode), self.assertRaises(ValueError):
                    self.consumer.admit_shared_inputs(
                        self.baseline, common, files | {path: (mode, files[path][1])})
            with self.subTest(missing=path), self.assertRaises(ValueError):
                self.consumer.admit_shared_inputs(self.baseline, {p: b for p, b in common.items()
                                                                  if p != path}, files)
        with self.assertRaises(ValueError):
            self.consumer.admit_shared_inputs(self.baseline, common | {"new.lock": "0" * 40}, files)

    def test_each_exact_variant_retains_disposition_and_rejects_identity_drift(self):
        selected = [(n, r) for n, r in self.reviewed["cases"].items()
                    if r["disposition"] != "SAME_RUN_NATIVE_REQUIRED"]
        self.assertEqual(len(selected), 12)
        self.assertEqual(sum(r["disposition"] == "OWNER_CANCELED" for _, r in selected), 7)
        for nodeid, record in selected:
            for variant in record["variants"]:
                row = {"nodeid": nodeid, "outcome": record["outcome"], **variant}
                accepted = self.consumer.admit_skips(self.value, self.result([row]), {})
                self.assertEqual(accepted["disposition_counts"][record["disposition"]], 1)
                self.assertFalse(accepted["skips_are_passes"])
                for key, wrong in (("nodeid", nodeid + "_new"), ("outcome", "xfail"),
                                   ("when", "teardown"), ("reason", "Skipped: unreviewed dependency")):
                    with self.subTest(nodeid=nodeid, key=key), self.assertRaises(ValueError):
                        self.consumer.admit_skips(self.value, self.result([row | {key: wrong}]), {})
                wrong_value = copy.deepcopy(self.value)
                wrong_value["skip_module_blobs"][nodeid.split("::")[0]] = "c" * 40
                with self.assertRaises(ValueError):
                    self.consumer.admit_skips(wrong_value, self.result([row]), {})
                context = self.result([row])
                context["shards"][0]["execution_context"] = {"platform": "linux", "uid": 0}
                with self.assertRaises(ValueError): self.consumer.admit_skips(self.value, context, {})
                wrong_value = copy.deepcopy(self.value)
                wrong_value["ops_plan"]["context"]["runner_arch"] = "UNKNOWN"
                with self.assertRaises(ValueError):
                    self.consumer.admit_skips(wrong_value, self.result([row]), {})
        # Tests improving from historical SKIP to PASS do not have to remain skipped.
        self.assertEqual(sum(self.consumer.admit_skips(self.value, self.result([]), {})[
            "disposition_counts"].values()), 0)


class ReviewedW85ObservabilityPolicy(unittest.TestCase):
    def setUp(self):
        self.consumer = fixture.SHARDS
        self.baseline = self.consumer.skip_baseline()
        self.key = "reviewed_w85_observability_transition"
        self.record = self.baseline[self.key]
        self.maps = [dict(self.baseline["common_inputs"])]
        for key in ("reviewed_shared_input_transition", "reviewed_python_input_transition",
                    "reviewed_frontend_security_transition", "reviewed_miniapp_security_transition",
                    "reviewed_w85_input_transition", self.key):
            record = self.baseline[key]
            changes = ({p: c["after_blob"] for p, c in record["changes"].items()}
                       if "changes" in record else {record["path"]: record["after_blob"]})
            self.maps.append(self.maps[-1] | changes)
        self.modes = self.baseline["reviewed_shared_input_transition"]["common_input_modes"]

    def files(self, common):
        return {p: (self.modes[p], blob) for p, blob in common.items()}

    def test_peel_restores_bff_baseline_and_exact_observability_successor(self):
        peeled, _ = self.consumer.reviewed_audit_dependency_transition(self.baseline)
        original, record = self.consumer.reviewed_w85_observability_transition(peeled)
        raw = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
        self.assertEqual(self.consumer.sha(raw),
                         "4f7b178ae050b44118efb1e2be1c294f2ad26d5fa0300bd5121a33d9029d96db")
        self.assertEqual(record["source_before"], "1d8ae9784b709ebb220f064c52a33ef42d3a5145")
        self.assertEqual(record["source_after"], "8e1a9c514ef61a423540ad7de4951867ab6b9b89")
        self.assertEqual(record["qualified_policy_revision"],
                         "bff07d53690d007dcc303c83e5319ff8820eb57b")
        self.assertEqual(record["independent_review_sha256"],
                         "87971a39c8839bb2784fa3d603458f7f3dff5d3e274d656349b5427b898e3025")
        self.assertEqual(record["source_freeze_sha256"],
                         "b8c255201e7ba245c14842b0f06d80b1dfc79631e040605617a020ae58ee3ff8")
        self.assertEqual(record["qualification_receipt_sha256"],
                         "44f01abc3259a3f8c212264caafce44f2e64516c1da015a1e59f087634f2c502")
        self.assertEqual(record["changes"], {
            "requirements-observability.txt": {
                "before_blob": "acd388f90b41f54482df25935b934476a7bc6e6a",
                "after_blob": "5411e4aadd7fbecb2ad3f6d6894ffd420b4a27b7",
                "mode": "100644",
            },
        })
        self.assertEqual(len(self.maps), 7)
        for common in self.maps[:-1]:
            self.consumer.admit_shared_inputs(original, common, self.files(common))
        with self.assertRaisesRegex(ValueError, "inputs changed"):
            self.consumer.admit_shared_inputs(original, self.maps[-1], self.files(self.maps[-1]))
        for common in self.maps:
            self.consumer.admit_shared_inputs(self.baseline, common, self.files(common))

    def test_audit_dependency_successor_admits_only_the_reviewed_lock_map(self):
        peeled, record = self.consumer.reviewed_audit_dependency_transition(self.baseline)
        restored = (json.dumps(peeled, indent=2, ensure_ascii=False) + "\n").encode()
        self.assertEqual(self.consumer.sha(restored), record["prior_baseline_sha256"])
        self.assertEqual(record["source_before"], "8e1a9c514ef61a423540ad7de4951867ab6b9b89")
        self.assertEqual(record["source_after"], "36a37ac2e54096ea59af22f5afca73afd6b7c71c")
        self.assertEqual(self.consumer.sha(self.consumer.encoded(record)),
                         self.consumer.AUDIT_DEPENDENCY_TRANSITION_SHA256)
        successor = dict(self.maps[-1])
        for path, change in record["changes"].items():
            self.assertEqual(successor[path], change["before_blob"])
            successor[path] = change["after_blob"]
        self.consumer.admit_shared_inputs(self.baseline, successor, self.files(successor))
        with self.assertRaisesRegex(ValueError, "inputs changed"):
            self.consumer.admit_shared_inputs(
                self.baseline, successor | {"pyproject.toml": "f" * 40}, self.files(successor))

    def test_zod_lock_successor_admits_only_the_reviewed_client_locks(self):
        peeled, record = self.consumer.reviewed_zod_lock_transition(self.baseline)
        restored = (json.dumps(peeled, indent=2, ensure_ascii=False) + "\n").encode()
        self.assertEqual(self.consumer.sha(restored), record["prior_baseline_sha256"])
        self.assertEqual(record["source_after"], "b18aa7f2163c0b22544d780287eb4dc7f88fcf7f")
        self.assertEqual(self.consumer.sha(self.consumer.encoded(record)),
                         self.consumer.ZOD_LOCK_TRANSITION_SHA256)
        successor = dict(self.maps[-1])
        audit = self.baseline["reviewed_audit_dependency_transition"]["changes"]
        for path, change in audit.items():
            successor[path] = change["after_blob"]
        for path, change in record["changes"].items():
            self.assertEqual(successor[path], change["before_blob"])
            successor[path] = change["after_blob"]
        self.consumer.admit_shared_inputs(self.baseline, successor, self.files(successor))
        with self.assertRaisesRegex(ValueError, "inputs changed"):
            self.consumer.admit_shared_inputs(
                self.baseline,
                successor | {"frontend/package-lock.json": "a" * 40},
                self.files(successor),
            )

    def test_216_dependency_combinations_admit_exactly_seven_maps(self):
        paths = ["frontend/package-lock.json", "pyproject.toml", "uv.lock",
                 "telegram-bot/yue/requirements.txt", "telegram-bot/yue/miniapp/package-lock.json",
                 "requirements-observability.txt"]
        variants = [list(dict.fromkeys(m[p] for m in self.maps)) for p in paths]
        self.assertEqual([len(item) for item in variants], [3, 3, 3, 2, 2, 2])
        attempted = accepted = 0
        for blobs in itertools.product(*variants):
            common = self.maps[0] | dict(zip(paths, blobs, strict=True))
            attempted += 1
            if common in self.maps:
                self.consumer.admit_shared_inputs(self.baseline, common, self.files(common))
                accepted += 1
            else:
                with self.assertRaisesRegex(ValueError, "inputs changed"):
                    self.consumer.admit_shared_inputs(self.baseline, common, self.files(common))
        self.assertEqual((attempted, accepted), (216, 7))

    def test_all_55_inputs_keep_blob_mode_membership_and_no_unknown_path(self):
        common = self.maps[-1]
        self.assertEqual(len(common), 55)
        self.assertEqual(common["requirements-observability.txt"],
                         "5411e4aadd7fbecb2ad3f6d6894ffd420b4a27b7")
        files = self.files(common)
        for path in common:
            with self.subTest(blob=path), self.assertRaises(ValueError):
                self.consumer.admit_shared_inputs(self.baseline, common | {path: "f" * 40}, files)
            for mode in ("100755", "120000"):
                with self.subTest(path=path, mode=mode), self.assertRaises(ValueError):
                    self.consumer.admit_shared_inputs(
                        self.baseline, common, files | {path: (mode, files[path][1])})
            with self.subTest(missing=path), self.assertRaises(ValueError):
                self.consumer.admit_shared_inputs(
                    self.baseline, {p: b for p, b in common.items() if p != path}, files)
        with self.assertRaises(ValueError):
            self.consumer.admit_shared_inputs(self.baseline, common | {"new.lock": "f" * 40}, files)

    def test_malformed_identity_history_and_omission_refuse(self):
        mutations = []
        for field in self.record:
            changed = copy.deepcopy(self.baseline)
            del changed[self.key][field]
            mutations.append(("missing-" + field, changed))
        for field in ("prior_baseline_sha256", "independent_review_sha256",
                      "source_freeze_sha256", "qualification_receipt_sha256",
                      "source_before", "source_after", "qualified_policy_revision"):
            changed = copy.deepcopy(self.baseline)
            changed[self.key][field] = "f" * len(self.record[field])
            mutations.append((field, changed))
        path = "requirements-observability.txt"
        for field, value in (("before_blob", "f" * 40), ("after_blob", "f" * 40),
                             ("mode", "100755"), ("extra", True)):
            changed = copy.deepcopy(self.baseline)
            changed[self.key]["changes"][path][field] = value
            mutations.append((field, changed))
        changed = copy.deepcopy(self.baseline)
        changed[self.key]["changes"]["pyproject.toml"] = {
            "before_blob": "a" * 40, "after_blob": "b" * 40, "mode": "100644"}
        mutations.append(("extra-path", changed))
        for key in ("reviewed_w85_input_transition", "reviewed_miniapp_security_transition"):
            changed = copy.deepcopy(self.baseline)
            del changed[key]
            mutations.append(("missing-" + key, changed))
            changed = copy.deepcopy(self.baseline)
            changed[key]["independent_review_sha256"] = "f" * 64
            mutations.append(("changed-review-" + key, changed))
        changed = copy.deepcopy(self.baseline)
        changed["cases"][next(iter(changed["cases"]))]["reason"] = "Skipped: invented new reason"
        mutations.append(("historical-skip-reason", changed))
        for value in (None, [], False):
            mutations.append(("invalid-record-" + str(value), self.baseline | {self.key: value}))
        for label, changed in mutations:
            for index, common in enumerate(self.maps):
                with self.subTest(mutation=label, map=index), self.assertRaises(ValueError):
                    self.consumer.admit_shared_inputs(changed, common)
        omitted = dict(self.baseline)
        del omitted[self.key]
        omitted.pop("reviewed_relay_metrics_module_transition", None)
        omitted.pop("reviewed_relay_skip_module_transition", None)
        omitted.pop("reviewed_audit_dependency_transition", None)
        omitted.pop("reviewed_zod_lock_transition", None)
        omitted.pop("reviewed_scanner_input_transition", None)
        omitted.pop("reviewed_current_skip_transition", None)
        for common in self.maps[:-1]:
            self.consumer.admit_shared_inputs(omitted, common, self.files(common))
        with self.assertRaisesRegex(ValueError, "inputs changed"):
            self.consumer.admit_shared_inputs(omitted, self.maps[-1], self.files(self.maps[-1]))

    def test_sealed_envelope_rejects_resealed_source_policy_history_and_map(self):
        policy = self.consumer.git(ROOT, "rev-parse", "HEAD").decode().strip()
        identity = {"policy_revision": policy, "run_id": "42", "run_attempt": "1"}
        board = "5046b327de669b1aa83907772db37da1f261a98b"
        source = self.record["source_after"]
        plan = self.consumer.seal({
            "schema": 1, "kind": "ops-pytest-module-plan", "source_revision": source,
            "context": identity | {"board_revision": board, "runner_os": "Linux",
                                   "runner_arch": "X64", "runner_image": "controlled-image"},
            "pytest_ini_sha256": "a" * 64, "entry_sha256": "b" * 64,
            "recorder_sha256": "c" * 64, "modules": {"tests/test_control.py": "d" * 64},
            "assignments": [{"id": "ordinary-000", "modules": ["tests/test_control.py"]}],
        }, "plan_sha256")
        value = self.consumer.seal({
            "schema": 1, "identity": identity, "mode": "sharded", "source_revision": source,
            "board_revision": board, "ops_plan": plan, "common_inputs": self.maps[-1],
            "skip_baseline_sha256": self.consumer.sha((ROOT / self.consumer.SKIP_BASELINE).read_bytes()),
            "skip_module_blobs": {"tests/test_control.py": "e" * 40},
            "validation_matrix": [{"validation": "yueops", "repo": "onesyue/yueops",
                                   "ref": source, "ops_role": role}
                                  for role in self.consumer.role_order(plan)],
        }, "admission_sha256")
        env = {"GITHUB_SHA": policy, "GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": "1",
               "GITHUB_REPOSITORY": "onesyue/yueto-ci"}
        with patch.dict(os.environ, env):
            self.consumer.envelope(value)
            previous = copy.deepcopy(value)
            previous["common_inputs"]["requirements-observability.txt"] = self.record["changes"][
                "requirements-observability.txt"]["before_blob"]
            del previous["admission_sha256"]
            self.consumer.seal(previous, "admission_sha256")
            self.consumer.envelope(previous)
            wrong = copy.deepcopy(value)
            wrong["common_inputs"]["requirements-observability.txt"] = "f" * 40
            del wrong["admission_sha256"]
            self.consumer.seal(wrong, "admission_sha256")
            with self.assertRaisesRegex(ValueError, "inputs changed"):
                self.consumer.envelope(wrong)
            mixed = copy.deepcopy(value)
            mixed["common_inputs"]["uv.lock"] = self.maps[0]["uv.lock"]
            del mixed["admission_sha256"]
            self.consumer.seal(mixed, "admission_sha256")
            with self.assertRaisesRegex(ValueError, "inputs changed"):
                self.consumer.envelope(mixed)
            for kind in ("source", "policy", "history"):
                wrong = copy.deepcopy(value)
                if kind == "source":
                    wrong["source_revision"] = "f" * 40
                elif kind == "policy":
                    wrong["identity"]["policy_revision"] = "f" * 40
                else:
                    wrong["skip_baseline_sha256"] = "f" * 64
                del wrong["admission_sha256"]
                self.consumer.seal(wrong, "admission_sha256")
                with self.subTest(resealed_identity=kind), self.assertRaises(ValueError):
                    self.consumer.envelope(wrong)


class CurrentNavigationSkipPolicy(unittest.TestCase):
    def test_reviewed_navigation_cases_remain_unexecuted_and_exact(self):
        consumer = fixture.SHARDS
        baseline = consumer.skip_baseline()
        record = baseline["reviewed_current_skip_transition"]
        modules = {
            "tests/test_panel_spa_error_cache_e2e.py":
                "b6f699837760729d98a3303babb475b084ff5ec2",
            "tests/test_miniapp_existing_app_nginx_native_20261013.py":
                "812e3509c7213cf16f507271f5a1d4f8c0cefe29",
        }
        reasons = {
            "tests/test_panel_spa_error_cache_e2e.py":
                "Skipped: real-nginx E2E requires Docker; skip is not evidence",
            "tests/test_miniapp_existing_app_nginx_native_20261013.py":
                "Skipped: real Mini mirror NGINX gate requires isolated Linux UID0",
        }
        nodeids = set(baseline["cases"]) | set(record["additions"])
        rows = [{"nodeid": nodeid, "outcome": "skipped", "when": "setup",
                 "reason": reasons[nodeid.split("::", 1)[0]]}
                for nodeid in sorted(nodeids) if nodeid.split("::", 1)[0] in modules]
        self.assertEqual(len(rows), 23)
        panel = "tests/test_panel_spa_error_cache_e2e.py::"
        for plane in (0, 1):
            self.assertIn(panel + "test_mirror_without_navigation_cookie_serves_only_"
                          f"the_secured_interstitial[plane{plane}]", {r["nodeid"] for r in rows})
        value = {"skip_module_blobs": modules,
                 "skip_baseline_sha256": consumer.sha((ROOT / consumer.SKIP_BASELINE).read_bytes())}
        session = {"execution_context": baseline["context"], "collection_skips": {},
                   "junit_sha256": "b" * 64, "nonpassing_outcomes": rows}
        result = {"reference": session | {"assignment_id": "reference"},
                  "shards": [session | {"assignment_id": "ordinary-000"}]}
        accepted = consumer.admit_skips(value, result, {"obligations": {}})
        self.assertEqual(accepted["status"], "NO_NEW_SKIPS")
        self.assertIs(accepted["skips_are_passes"], False)
        self.assertEqual(accepted["disposition_counts"]["HISTORICAL_UNEXECUTED"], 46)
        for module in modules:
            with self.subTest(module=module, mutation="blob"), self.assertRaises(ValueError):
                consumer.admit_skips(value | {"skip_module_blobs": modules | {module: "f" * 40}},
                                     result, {"obligations": {}})
            for field, replacement in (("reason", "Skipped: unreviewed reason"),
                                       ("nodeid", module + "::test_unreviewed")):
                changed = copy.deepcopy(result)
                row = next(r for r in changed["shards"][0]["nonpassing_outcomes"]
                           if r["nodeid"].startswith(module + "::"))
                row[field] = replacement
                with self.subTest(module=module, mutation=field), self.assertRaises(ValueError):
                    consumer.admit_skips(value, changed, {"obligations": {}})


class CurrentRelaySkipPolicy(unittest.TestCase):
    def test_exact_relay_native_cases_remain_ordinary_skips(self):
        consumer = fixture.SHARDS
        baseline = consumer.skip_baseline()
        record = baseline["reviewed_current_skip_transition"]
        self.assertEqual(record["source_revision"],
                         "3b981eaeb042ed03762489e5360f61d4d0f9f16a")
        self.assertEqual((len(record["additions"]), len(record["updates"])), (34, 59))
        self.assertEqual(record["prior_baseline_sha256"],
                         "9aa6b338f4411e9508bb0a0978924ee383ccf95cedcc3c0d2dd2145b50f3d7d5")
        module = "tests/test_relay4_tuning_20261025.py"
        blob = "0596e8a63a8c68a290033d6d1ca495a4f666f5ba"
        reasons = {
            "test_real_dpkg_transaction_has_a_finite_package_deadline": (
                ["False", "True"],
                "requires Linux UID0 and the real dpkg process and transaction database"),
            "test_real_dpkg_leader_death_retains_custody_until_maintainer_exit": (
                ["False", "True"], "requires Linux UID0 and real dpkg leader/maintainer processes"),
            "test_actual_journal_unit_boundary_and_independent_recovery": (
                ["commit", "budget_recovery", "lost_history", "missing_floor",
                 "owner_exit_before_package"],
                "requires an isolated Docker systemd PID1 journal lab"),
        }
        expected = {
            module + "::" + name + "[" + parameter + "]": {
                "outcome": "skipped", "reason": "Skipped: " + reason, "module_blob": blob}
            for name, (parameters, reason) in reasons.items() for parameter in parameters
        }
        expected[module + "::test_systemd_custody_drains_a_maintainer_that_escapes_its_original_session"] = {
            "outcome": "skipped", "reason": "Skipped: requires an isolated systemd PID1 cgroup custody lab",
            "module_blob": blob}
        actual = {key: value for key, value in record["additions"].items()
                  if key.startswith(module + "::")}
        self.assertEqual(actual, expected)
        self.assertFalse(set(expected) & set(baseline["cases"]))
        self.assertFalse(set(expected) & set(baseline["reviewed_hosted"]["cases"]))
        value = {"skip_module_blobs": {module: blob},
                 "skip_baseline_sha256": consumer.sha((ROOT / consumer.SKIP_BASELINE).read_bytes())}
        rows = [{"nodeid": key, "outcome": "skipped", "when": "setup", "reason": case["reason"]}
                for key, case in expected.items()]
        session = {"execution_context": baseline["context"], "collection_skips": {},
                   "junit_sha256": "b" * 64, "nonpassing_outcomes": rows}
        result = {"reference": session | {"assignment_id": "reference"},
                  "shards": [session | {"assignment_id": "ordinary-000"}]}
        accepted = consumer.admit_skips(value, result, {"obligations": {}})
        self.assertEqual(accepted["status"], "NO_NEW_SKIPS")
        self.assertIs(accepted["skips_are_passes"], False)
        self.assertEqual(accepted["disposition_counts"], {
            "HISTORICAL_UNEXECUTED": 20, "OWNER_CANCELED": 0, "SAME_RUN_NATIVE_REQUIRED": 0})
        with self.assertRaisesRegex(ValueError, "new or changed case"):
            consumer.admit_skips(value | {"skip_module_blobs": {module: "f" * 40}},
                                 result, {"obligations": {}})
        for field, replacement in (("reason", "unreviewed reason"),
                                   ("nodeid", module + "::test_unreviewed")):
            changed = copy.deepcopy(result)
            changed["shards"][0]["nonpassing_outcomes"][0][field] = replacement
            with self.subTest(mutation=field), self.assertRaisesRegex(ValueError, "new or changed case"):
                consumer.admit_skips(value, changed, {"obligations": {}})


class ScannerInputSuccessorPolicy(unittest.TestCase):
    def setUp(self):
        self.consumer = fixture.SHARDS
        self.baseline, _ = self.consumer.reviewed_relay_skip_module_transition(
            self.consumer.skip_baseline())
        self.original, self.record = self.consumer.reviewed_scanner_input_transition(self.baseline)
        self.path = "tests/_shell_early_exit_pipes.py"
        self.maps = [dict(self.original["common_inputs"])]
        for key in ("reviewed_shared_input_transition", "reviewed_python_input_transition",
                    "reviewed_frontend_security_transition", "reviewed_miniapp_security_transition",
                    "reviewed_w85_input_transition", "reviewed_w85_observability_transition",
                    "reviewed_audit_dependency_transition", "reviewed_zod_lock_transition"):
            record = self.original[key]
            changes = record.get("changes", {record.get("path"): record})
            self.maps.append(self.maps[-1] | {path: change["after_blob"]
                                             for path, change in changes.items()})
        self.successor = self.maps[-1] | {
            self.path: self.record["changes"][self.path]["after_blob"]}
        self.modes = self.original["reviewed_shared_input_transition"]["common_input_modes"]

    def files(self, common):
        return {path: (self.modes[path], blob) for path, blob in common.items()}

    def test_exact_scanner_successor_preserves_all_nine_historical_maps(self):
        self.assertEqual(self.record["source_before"], "3b981eaeb042ed03762489e5360f61d4d0f9f16a")
        self.assertEqual(self.record["source_after"], "4214a4c6cb36ce8ee46e7901174586db81ab75f7")
        self.assertEqual(self.record["qualified_policy_revision"],
                         "4cc1d14ce81daf7526cff51f8e8eba6195b1e1a9")
        self.assertEqual(self.record["changes"], {self.path: {
            "before_blob": "cc552db08771988cc93b6be7ee67bd98ee376017",
            "after_blob": "472b8b725a9e88df04fa4ab80f0e59e755fdade8", "mode": "100644"}})
        self.assertEqual((len(self.maps), len(self.successor)), (9, 55))
        self.assertEqual(self.consumer.reviewed_current_skip_transition(self.baseline),
                         self.consumer.reviewed_current_skip_transition(self.original))
        for index, common in enumerate([*self.maps, self.successor]):
            with self.subTest(complete_map=index):
                self.consumer.admit_shared_inputs(self.baseline, common, self.files(common))
        with self.assertRaisesRegex(ValueError, "inputs changed"):
            self.consumer.admit_shared_inputs(self.original, self.successor, self.files(self.successor))

    def test_unknown_helper_path_mode_and_mixed_maps_are_rejected(self):
        for label, common in (
            ("unknown-blob", self.successor | {self.path: "f" * 40}),
            ("unknown-path", self.successor | {"tests/_unreviewed.py": "f" * 40}),
            ("missing-path", {p: b for p, b in self.successor.items() if p != self.path}),
            ("mixed-map", self.successor | {"uv.lock": self.maps[0]["uv.lock"]}),
        ):
            with self.subTest(mutation=label), self.assertRaises(ValueError):
                self.consumer.admit_shared_inputs(self.baseline, common)
        files = self.files(self.successor)
        files[self.path] = ("100755", self.successor[self.path])
        with self.assertRaisesRegex(ValueError, "modes changed"):
            self.consumer.admit_shared_inputs(self.baseline, self.successor, files)

    def test_stale_successor_blob_and_changed_review_cannot_relabel_history(self):
        # The complete predecessor map remains valid historical input. Its helper
        # cannot be relabeled as the reviewed4214 successor by changing the record.
        for field, value in (("after_blob", self.record["changes"][self.path]["before_blob"]),
                             ("mode", "100755")):
            changed = copy.deepcopy(self.baseline)
            changed["reviewed_scanner_input_transition"]["changes"][self.path][field] = value
            with self.subTest(mutation=field), self.assertRaisesRegex(ValueError, "transition identity"):
                self.consumer.admit_shared_inputs(changed, self.successor)
        for field in ("source_after", "independent_review_sha256", "qualification_receipt_sha256"):
            changed = copy.deepcopy(self.baseline)
            changed["reviewed_scanner_input_transition"][field] = "f" * len(self.record[field])
            with self.subTest(mutation=field), self.assertRaises(ValueError):
                self.consumer.admit_shared_inputs(changed, self.successor)
        changed = copy.deepcopy(self.baseline)
        changed["common_inputs"][self.path] = "f" * 40
        with self.assertRaisesRegex(ValueError, "historical baseline changed"):
            self.consumer.admit_shared_inputs(changed, self.successor)


class RelaySkipModuleSuccessorPolicy(unittest.TestCase):
    def setUp(self):
        self.consumer = fixture.SHARDS
        self.baseline = self.consumer.skip_baseline()
        self.key = "reviewed_relay_skip_module_transition"
        self.record = self.baseline[self.key]
        self.original, self.successors = self.consumer.reviewed_relay_skip_module_transition(
            self.baseline)
        self.module = "tests/test_relay4_tuning_20261025.py"
        self.old_blob = "0596e8a63a8c68a290033d6d1ca495a4f666f5ba"
        self.new_blob = "6db5102e988bb2fc71acf1fa7ff0c786ad7e09fc"
        cases = self.original["reviewed_current_skip_transition"]["additions"]
        self.cases = {key: case for key, case in cases.items()
                      if key.startswith(self.module + "::")}
        session = {"execution_context": self.baseline["context"], "collection_skips": {},
                   "junit_sha256": "b" * 64,
                   "nonpassing_outcomes": [
                       {"nodeid": key, "outcome": case["outcome"], "when": "setup",
                        "reason": case["reason"]} for key, case in self.cases.items()]}
        self.result = {"reference": session | {"assignment_id": "reference"},
                       "shards": [copy.deepcopy(session) | {"assignment_id": "ordinary-000"}]}

    def value(self, blob):
        return {"skip_module_blobs": {self.module: blob},
                "skip_baseline_sha256": self.consumer.sha(
                    (ROOT / self.consumer.SKIP_BASELINE).read_bytes())}

    def test_exact_successor_preserves_complete_predecessor_and_all_skip_facts(self):
        restored = (json.dumps(self.original, indent=2, ensure_ascii=False) + "\n").encode()
        self.assertEqual(self.consumer.sha(restored),
                         "0078b5948f06329475ea0e54a5d6f8ec89e439319c602c9fbf2049f27379e924")
        self.assertEqual(self.record["source_before"], "4214a4c6cb36ce8ee46e7901174586db81ab75f7")
        self.assertEqual(self.record["source_after"], "943a7a1249d2501b46f5fca1667115d369663cc2")
        self.assertEqual(self.record["qualified_policy_revision"],
                         "454399d13b01052a35c4ab431ec1f1f143e66693")
        self.assertEqual(self.record["module"], {
            "path": self.module, "mode": "100644",
            "before_blob": self.old_blob, "after_blob": self.new_blob})
        current = self.original["reviewed_current_skip_transition"]
        self.assertEqual((len(current["additions"]), len(current["updates"])), (34, 59))
        self.assertEqual(len(self.successors), 10)
        self.assertEqual(self.successors, {
            key: case | {"module_blob": self.new_blob} for key, case in self.cases.items()})
        self.assertEqual(self.consumer.reviewed_scanner_input_transition(self.baseline),
                         self.consumer.reviewed_scanner_input_transition(self.original))
        self.assertEqual(self.baseline["reviewed_hosted"], self.original["reviewed_hosted"])

    def test_native_skip_consumer_accepts_only_old_and_exact_reviewed_module(self):
        for blob in (self.old_blob, self.new_blob):
            with self.subTest(module=blob):
                result = self.consumer.admit_skips(self.value(blob), self.result, {"obligations": {}})
                self.assertEqual(result["status"], "NO_NEW_SKIPS")
                self.assertIs(result["skips_are_passes"], False)
                self.assertEqual(result["disposition_counts"], {
                    "HISTORICAL_UNEXECUTED": 20, "OWNER_CANCELED": 0,
                    "SAME_RUN_NATIVE_REQUIRED": 0})
        with self.assertRaisesRegex(ValueError, "new or changed case"):
            self.consumer.admit_skips(self.value("f" * 40), self.result, {"obligations": {}})
        with patch.object(self.consumer, "skip_baseline", return_value=self.original):
            with self.assertRaisesRegex(ValueError, "new or changed case"):
                self.consumer.admit_skips(self.value(self.new_blob), self.result, {"obligations": {}})

    def test_actual_successor_module_mode_is_checked_by_shared_input_admission(self):
        common = self.baseline["common_inputs"]
        modes = self.baseline["reviewed_shared_input_transition"]["common_input_modes"]
        files = {path: (modes[path], blob) for path, blob in common.items()}
        self.consumer.admit_shared_inputs(self.baseline, common, files)
        self.consumer.admit_shared_inputs(
            self.baseline, common, files | {self.module: ("100644", self.new_blob)})
        for mode in ("100755", "120000"):
            with self.subTest(mode=mode), self.assertRaisesRegex(
                    ValueError, "relay skip module mode changed"):
                self.consumer.admit_shared_inputs(
                    self.baseline, common, files | {self.module: (mode, self.new_blob)})

    def test_unknown_case_reason_or_outcome_is_not_admitted_by_new_module(self):
        for field, replacement in (("nodeid", self.module + "::test_unreviewed"),
                                   ("reason", "Skipped: unreviewed reason"),
                                   ("outcome", "xfailed")):
            changed = copy.deepcopy(self.result)
            changed["shards"][0]["nonpassing_outcomes"][0][field] = replacement
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "new or changed case"):
                self.consumer.admit_skips(self.value(self.new_blob), changed, {"obligations": {}})

    def test_changed_review_module_or_history_cannot_relabel_skip_evidence(self):
        mutations = []
        for field in ("source_before", "source_after", "qualified_policy_revision",
                      "independent_review_sha256", "source_freeze_sha256",
                      "qualification_receipt_sha256"):
            changed = copy.deepcopy(self.baseline)
            changed[self.key][field] = "f" * len(self.record[field])
            mutations.append((field, changed))
        for field, value in (("path", "tests/test_unreviewed.py"), ("mode", "100755"),
                             ("before_blob", "f" * 40), ("after_blob", self.old_blob)):
            changed = copy.deepcopy(self.baseline)
            changed[self.key]["module"][field] = value
            mutations.append((field, changed))
        changed = copy.deepcopy(self.baseline)
        changed["reviewed_current_skip_transition"]["additions"][
            next(iter(self.cases))]["reason"] = "Skipped: changed history"
        mutations.append(("historical-reason", changed))
        changed = copy.deepcopy(self.baseline)
        del changed["reviewed_scanner_input_transition"]
        mutations.append(("missing-predecessor", changed))
        for label, changed in mutations:
            with self.subTest(mutation=label), self.assertRaises(ValueError):
                self.consumer.reviewed_relay_skip_module_transition(changed)


class RelayMetricsModuleSuccessorPolicy(unittest.TestCase):
    def setUp(self):
        self.consumer = fixture.SHARDS
        self.baseline = self.consumer.skip_baseline()
        self.key = "reviewed_relay_metrics_module_transition"
        self.record = self.baseline[self.key]
        self.original, self.successors = self.consumer.reviewed_relay_metrics_module_transition(
            self.baseline)
        self.module = "tests/test_relay4_tuning_20261025.py"
        self.new_blob = "8053af6952c5ac8dddaece3f1a25a6958f7dfeb8"
        session = {"execution_context": self.baseline["context"], "collection_skips": {},
                   "junit_sha256": "b" * 64,
                   "nonpassing_outcomes": [
                       {"nodeid": nodeid, "outcome": case["outcome"], "when": "setup",
                        "reason": case["reason"]} for nodeid, case in self.successors.items()]}
        self.result = {"reference": session | {"assignment_id": "reference"},
                       "shards": [copy.deepcopy(session) | {"assignment_id": "ordinary-000"}]}

    def value(self, blob):
        return {"skip_module_blobs": {self.module: blob},
                "skip_baseline_sha256": self.consumer.sha(
                    (ROOT / self.consumer.SKIP_BASELINE).read_bytes())}

    def test_metrics_binding_preserves_both_predecessors_and_exact_skip_facts(self):
        restored = (json.dumps(self.original, indent=2, ensure_ascii=False) + "\n").encode()
        self.assertEqual(self.consumer.sha(restored),
                         "4489a94dd5cac7fc570492090fbb26eeff444be6221524325609447711dd6e8f")
        self.assertEqual(self.record["source_before"], "943a7a1249d2501b46f5fca1667115d369663cc2")
        self.assertEqual(self.record["source_after"], "13e257b70cb5ea3083145d10bc4da6b197734f0f")
        prior, cases = self.consumer.reviewed_relay_skip_module_transition(self.original)
        self.assertEqual(len(cases), 10)
        self.assertEqual(self.successors, {
            nodeid: case | {"module_blob": self.new_blob} for nodeid, case in cases.items()})
        self.assertEqual(self.original["reviewed_relay_skip_module_transition"],
                         self.baseline["reviewed_relay_skip_module_transition"])
        current = prior["reviewed_current_skip_transition"]
        self.assertEqual((len(current["additions"]), len(current["updates"])), (34, 59))
        self.assertEqual(self.original["reviewed_hosted"], self.baseline["reviewed_hosted"])

    def test_actual_skip_consumer_accepts_current_and_preserves_old_module_identities(self):
        for blob in ("0596e8a63a8c68a290033d6d1ca495a4f666f5ba",
                     "6db5102e988bb2fc71acf1fa7ff0c786ad7e09fc", self.new_blob):
            with self.subTest(blob=blob):
                result = self.consumer.admit_skips(self.value(blob), self.result, {"obligations": {}})
                self.assertEqual(result["status"], "NO_NEW_SKIPS")
                self.assertIs(result["skips_are_passes"], False)
                self.assertEqual(result["disposition_counts"], {
                    "HISTORICAL_UNEXECUTED": 20, "OWNER_CANCELED": 0,
                    "SAME_RUN_NATIVE_REQUIRED": 0})
        with (patch.object(self.consumer, "skip_baseline", return_value=self.original),
              self.assertRaisesRegex(ValueError, "new or changed case")):
            self.consumer.admit_skips(self.value(self.new_blob), self.result, {"obligations": {}})

    def test_current_module_requires_actual_regular_file_mode(self):
        common = self.baseline["common_inputs"]
        modes = self.baseline["reviewed_shared_input_transition"]["common_input_modes"]
        files = {path: (modes[path], blob) for path, blob in common.items()}
        self.consumer.admit_shared_inputs(
            self.baseline, common, files | {self.module: ("100644", self.new_blob)})
        for mode in ("100755", "120000"):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "module mode changed"):
                self.consumer.admit_shared_inputs(
                    self.baseline, common, files | {self.module: (mode, self.new_blob)})

    def test_actual_consumer_rejects_unknown_blob_new_case_reason_and_outcome(self):
        with self.assertRaisesRegex(ValueError, "new or changed case"):
            self.consumer.admit_skips(self.value("f" * 40), self.result, {"obligations": {}})
        for field, replacement in (("nodeid", self.module + "::test_unreviewed"),
                                   ("reason", "Skipped: changed reason"), ("outcome", "xfailed")):
            changed = copy.deepcopy(self.result)
            changed["shards"][0]["nonpassing_outcomes"][0][field] = replacement
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "new or changed case"):
                self.consumer.admit_skips(self.value(self.new_blob), changed, {"obligations": {}})

    def test_stale_source_native_qualification_or_predecessor_cannot_relabel_evidence(self):
        for field in ("source_before", "source_after", "qualified_policy_revision",
                      "independent_review_sha256", "source_freeze_sha256",
                      "qualification_receipt_sha256"):
            changed = copy.deepcopy(self.baseline)
            changed[self.key][field] = "f" * len(self.record[field])
            with (self.subTest(field=field),
                  patch.object(self.consumer, "skip_baseline", return_value=changed),
                  self.assertRaisesRegex(ValueError, "transition identity")):
                self.consumer.admit_skips(self.value(self.new_blob), self.result, {"obligations": {}})
        for field, replacement in (("mode", "100755"), ("after_blob", "f" * 40),
                                   ("before_blob", "f" * 40), ("path", "tests/test_other.py")):
            changed = copy.deepcopy(self.baseline)
            changed[self.key]["module"][field] = replacement
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "transition identity"):
                self.consumer.reviewed_relay_metrics_module_transition(changed)
        changed = copy.deepcopy(self.baseline)
        changed["reviewed_relay_skip_module_transition"]["source_after"] = "f" * 40
        with self.assertRaisesRegex(ValueError, "historical baseline changed"):
            self.consumer.reviewed_relay_metrics_module_transition(changed)


if __name__ == "__main__":
    unittest.main()
