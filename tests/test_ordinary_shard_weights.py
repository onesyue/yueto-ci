"""Ordinary shard weights rebalance by measured duration and fall back to the stride."""
from __future__ import annotations

import importlib.util
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ordinary_shard_weights", ROOT / "scripts/pytest-shards.py")
SHARDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARDS)
WORKFLOW = (ROOT / ".github/workflows/build.yml").read_text()


def step(name):
    match = re.search(
        rf"^      - name: {re.escape(name)}\n(?P<body>(?:(?!^      - |^  [a-z]).*\n)*)",
        WORKFLOW, re.M)
    if match is None:
        raise AssertionError(name)
    body = match.group("body")
    script = re.search(r"^        run: \|\n((?:          .*\n|\n)*)", body, re.M)
    return body, textwrap.dedent(script.group(1)) if script else ""


def case(nodeid, seconds, kind="case", status="measured"):
    return {
        "event": "phase_timing", "schema": 1, "nodeid": nodeid, "when": "call",
        "report_kind": kind, "duration_status": status,
        "duration_seconds": seconds,
    }


class OrdinaryShardWeightTest(unittest.TestCase):
    def test_stride_matches_module_index_and_weights_split_the_slow_group(self):
        modules = [f"tests/test_{index:02d}.py" for index in range(16)]
        count = 4
        stride = SHARDS.assign_ordinary(modules, count, None)
        self.assertEqual(
            [item["modules"] for item in stride],
            [modules[index::count] for index in range(count)])
        slow = set(modules[0::count])
        weights = {module: 1000 for module in modules}
        for rank, module in enumerate(sorted(slow)):
            weights[module] = 50000 - rank
        balanced = SHARDS.assign_ordinary(modules, count, weights)
        for item in balanced:
            self.assertEqual(len(slow.intersection(item["modules"])), 1)
        self.assertEqual(len(slow.intersection(stride[0]["modules"])), 4)

        def heaviest(plan):
            return max(sum(weights[module] for module in item["modules"]) for item in plan)

        self.assertLess(heaviest(balanced), heaviest(stride))

    def test_unmeasured_module_uses_the_lower_median_not_zero(self):
        modules = ["tests/test_a.py", "tests/test_b.py", "tests/test_c.py", "tests/test_d.py"]
        aligned = SHARDS.align_weights(modules + ["tests/test_e.py"], {
            "tests/test_a.py": 10, "tests/test_b.py": 20, "tests/test_c.py": 30,
            "tests/test_d.py": 40, "tests/test_unknown.py": 999,
        })
        self.assertEqual(aligned["tests/test_e.py"], 20)
        self.assertNotIn("tests/test_unknown.py", aligned)
        missing = SHARDS.align_weights(
            modules, {"tests/test_a.py": 10, "tests/test_b.py": 40, "tests/test_c.py": 0})
        self.assertEqual(missing["tests/test_c.py"], 10)
        self.assertEqual(missing["tests/test_d.py"], 10)
        self.assertIsNone(SHARDS.align_weights(modules, {}))
        self.assertIsNone(SHARDS.align_weights(modules, {"tests/test_a.py": 1.5}))
        self.assertIsNone(SHARDS.align_weights(modules, {"tests/test_a.py": True}))
        self.assertIsNone(SHARDS.align_weights(modules, ["tests/test_a.py"]))

    def test_events_sum_case_phases_and_skip_corrupt_subtests_and_reference_copies(self):
        ordinary = {"tests/test_a.py", "tests/test_b.py"}
        events = self._events([
            case("tests/test_a.py::test_one", 0.5),
            case("tests/test_a.py::test_one", 0.25),
            case("tests/test_a.py::test_one", 20, kind="subtest"),
            case("tests/test_a.py::test_one", 9, status="unavailable"),
            case("tests/test_b.py::test_two", 0.0004),
            case("tests/test_other.py::test_three", 30),
            "{not json",
        ])
        self.assertEqual(SHARDS.weights_from_events(events, ordinary), {
            "tests/test_a.py": 750, "tests/test_b.py": 1,
        })
        self.assertEqual(SHARDS.weights_from_events(events.parent / "missing.jsonl", ordinary), {})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(root / "ops-shard-9-1-ordinary-000" / "events.jsonl", [
                case("tests/test_a.py::test_one", 1.5),
            ])
            self._write(root / "ops-shard-9-1-reference-ordinary-000" / "events.jsonl", [
                case("tests/test_a.py::test_one", 50),
            ])
            self._write(root / "ops-shard-9-1-serial" / "events.jsonl", [
                case("tests/test_b.py::test_two", 40),
            ])
            output = root / "ordinary-weights.json"
            wrote = SHARDS.publish_ordinary_weights({
                "ops_plan": {"assignments": [
                    {"id": "ordinary-000", "modules": ["tests/test_a.py", "tests/test_b.py"]},
                    {"id": "serial", "modules": ["tests/test_c.py"]},
                ]},
            }, root, output)
            self.assertTrue(wrote)
            self.assertEqual(json.loads(output.read_text()), {"tests/test_a.py": 1500})
            self.assertFalse(SHARDS.publish_ordinary_weights(
                {"ops_plan": {"assignments": []}}, root / "missing", output))

    def test_artifact_choice_prefers_weights_and_a_fetch_failure_keeps_the_stride(self):
        self.assertEqual(SHARDS.choose_weight_artifact([
            "yueops-pytest-timing-11-1", "ops-ordinary-weights-10-1", "unrelated",
        ]), "ops-ordinary-weights-10-1")
        self.assertEqual(
            SHARDS.choose_weight_artifact(["yueops-pytest-timing-11-1"]),
            "yueops-pytest-timing-11-1")
        self.assertIsNone(SHARDS.choose_weight_artifact(["unrelated"]))
        self.assertEqual(SHARDS.select_weight_artifact([
            (11, ["yueops-pytest-timing-11-1"]),
            (10, ["ops-ordinary-weights-10-1"]),
        ]), (10, "ops-ordinary-weights-10-1"))
        self.assertEqual(SHARDS.artifact_names_from_listing(
            "ops-ordinary-weights-11-1\ttrue\nyueops-pytest-timing-11-1\tfalse\n"),
            ["yueops-pytest-timing-11-1"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "weights.json"
            timing = root / "timing"
            status, reason = SHARDS.fetch_previous_ordinary_weights(
                output, timing, runner=lambda _argv: (1, "", ""))
            self.assertEqual((status, reason), ("stride", "run list failed"))
            self.assertFalse(output.exists())
            captured = io.StringIO()
            args = type("Args", (), {"output": output, "timing_output": timing})()
            with contextlib.redirect_stderr(captured):
                code = SHARDS.previous_ordinary_weights_command(
                    args, runner=lambda _argv: (1, "", ""))
            self.assertEqual(code, 0)
            self.assertIn("ORDINARY_WEIGHTS: stride (run list failed)", captured.getvalue())

            def runner(argv):
                if argv[1:3] == ["run", "list"]:
                    return 0, json.dumps([{"databaseId": 11}, {"databaseId": "10"}]), ""
                if argv[1] == "api" and "/runs/11/" in argv[3]:
                    return 0, "ops-ordinary-weights-11-1\ttrue\nyueops-pytest-timing-11-1\tfalse\n", ""
                if argv[1:3] == ["run", "download"]:
                    self.assertIn("yueops-pytest-timing-11-1", argv)
                    dest = Path(argv[argv.index("-D") + 1])
                    dest.mkdir(parents=True, exist_ok=True)
                    (dest / "events.jsonl").write_text(json.dumps(case("tests/test_a.py::test_one", 1)) + "\n")
                    return 0, "", ""
                return 1, "", ""

            status, _reason = SHARDS.fetch_previous_ordinary_weights(output, timing, runner=runner)
            self.assertEqual(status, "timed-events")
            self.assertTrue((timing / "events.jsonl").is_file())
            self.assertFalse(output.exists())

            def weights_runner(argv):
                if argv[1:3] == ["run", "list"]:
                    return 0, json.dumps([{"databaseId": 11}, {"databaseId": 10}]), ""
                if argv[1] == "api" and "/runs/11/" in argv[3]:
                    return 0, "yueops-pytest-timing-11-1\tfalse\n", ""
                if argv[1] == "api" and "/runs/10/" in argv[3]:
                    return 0, "ops-ordinary-weights-10-1\tfalse\n", ""
                if argv[1:3] == ["run", "download"]:
                    self.assertIn("ops-ordinary-weights-10-1", argv)
                    dest = Path(argv[argv.index("-D") + 1])
                    dest.mkdir(parents=True, exist_ok=True)
                    (dest / "ordinary-weights.json").write_text("{")
                    return 0, "", ""
                return 1, "", ""

            status, reason = SHARDS.fetch_previous_ordinary_weights(output, timing, runner=weights_runner)
            self.assertEqual(status, "stride")
            self.assertEqual(reason, "ordinary weights file unusable")

    def test_missing_gh_and_missing_admission_do_not_fail_the_command(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = dict(os.environ, PATH=str(root), PYTHONDONTWRITEBYTECODE="1")
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/pytest-shards.py"), "previous-ordinary-weights",
                 "--output", str(root / "weights.json"), "--timing-output", str(root / "timing")],
                capture_output=True, text=True, env=env, timeout=20, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("ORDINARY_WEIGHTS: stride", result.stderr)
            self.assertNotIn("http", result.stderr.casefold())
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/pytest-shards.py"), "publish-ordinary-weights",
                 "--admission", str(root / "missing.json"), "--evidence", str(root),
                 "--output", str(root / "ordinary-weights.json")],
                capture_output=True, text=True, env=env, timeout=20, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("ORDINARY_WEIGHTS: absent", result.stderr)
            self.assertFalse((root / "ordinary-weights.json").exists())

    def test_weight_fetch_stays_outside_the_executed_plan_script(self):
        fetch, _script = step("Read previous ordinary shard weights")
        _body, plan = step("Plan complete Ops jobs before collection")
        publish, _script = step("Publish ordinary shard weights")
        upload, _script = step("Upload ordinary shard weights")
        retain, _script = step("Retain complete validation verdict")
        self.assertIn("previous-ordinary-weights", fetch)
        self.assertIn("GH_TOKEN: ${{ github.token }}", fetch)
        self.assertNotIn("secrets.", fetch)
        self.assertNotIn("gh ", plan)
        self.assertIn("scripts/pytest-shards.py expand", plan)
        self.assertIn("--weights", plan)
        self.assertIn("--timing", plan)
        self.assertIn("publish-ordinary-weights", publish)
        self.assertIn("actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a", upload)
        self.assertIn("if-no-files-found: warn", upload)
        self.assertIn("ops-ordinary-weights-${{ github.run_id }}-${{ github.run_attempt }}", upload)
        self.assertIn("if-no-files-found: error", retain)
        self.assertNotIn("if:", retain)
        self.assertLess(WORKFLOW.index("- name: Read previous ordinary shard weights"),
                        WORKFLOW.index("- name: Plan complete Ops jobs before collection"))
        self.assertLess(WORKFLOW.index("- name: Publish ordinary shard weights"),
                        WORKFLOW.index("- name: Retain complete validation verdict"))

    def _events(self, rows):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "events.jsonl"
        self._write(path, rows)
        return path

    def _write(self, path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        for row in rows:
            lines.append(row if isinstance(row, str) else json.dumps(row))
        path.write_text("".join(line + "\n" for line in lines))




if __name__ == "__main__":
    unittest.main()
