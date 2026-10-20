"""Execute the real workflow shell, source-entry protocol and artifact join."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

import test_pytest_shards as fixture
import test_pytest_timing as yaml_consumer

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
            entry.write_text("#!/bin/sh\nexec python3 - \"$@\" <<'PY'\n" + textwrap.dedent("""
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

    def run_role(self, role, extra=None):
        runner = self.base / ("runner-" + role)
        (runner / "ops-admission").mkdir(parents=True)
        (runner / "ops-admission/ops-admission.json").write_text(json.dumps(self.admission))
        env = self.env | {"RUNNER_TEMP": str(runner), "OPS_ROLE": role} | (extra or {})
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

    def test_actual_yaml_source_entry_and_join_keep_complete_corpus(self):
        result = self.full_bundle()
        self.assertEqual(result["status"], "VALIDATION_MATRIX_COMPLETE")
        self.assertEqual(result["ordinary"]["case_count"], 8)
        self.assertFalse(result["ordinary"]["release_acceptance"])
        self.assertEqual(result["skip_admission"]["status"], "NO_NEW_SKIPS")
        self.assertFalse(result["skip_admission"]["skips_are_passes"])
        self.assertEqual(result["host_linux_skip_policy"], "ROOT_GATE_UNCHANGED")
        receipt = json.loads((self.artifacts / (self.prefix + "serial") / "selection.json").read_text())
        self.assertEqual(receipt["modules"], TAIL)
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
        for status in ("success", "failure", "cancelled", "skipped"):
            env = self.env | {"RUNNER_TEMP": str(runner), "VALIDATION_RESULT": status,
                              "ADMISSION_SHA256": self.admission["admission_sha256"]}
            executed = subprocess.run(["bash", "-c", script], cwd=self.policy, env=env,
                                      capture_output=True, text=True, timeout=15, check=False)
            if status == "success":
                self.assertEqual(executed.returncode, 0, executed.stdout + executed.stderr)
                self.assertEqual(json.loads(executed.stdout)["status"], "VALIDATION_MATRIX_COMPLETE")
            else:
                self.assertNotEqual(executed.returncode, 0, executed.stdout + executed.stderr)

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


if __name__ == "__main__":
    unittest.main()
