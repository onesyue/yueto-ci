"""Exercise the per-image publish decision and source quarantine with real pytest."""
import importlib.util
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("service_validation", ROOT / "scripts/service-validation.py")
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class ServiceValidationTest(unittest.TestCase):
    def test_owned_shared_and_missing_conclusions(self):
        names = ["yue-bot", "checkin-api", "yue-node"]
        builds = [dict(service=name, validation="yue-node" if name == "yue-node" else "yueops") for name in names]
        validations = [dict(validation="yueops", ops_role="ordinary-1"), dict(validation="yue-node", node_profile="hy2")]
        jobs = [dict(name=name, status="completed", conclusion="success") for name in
                ("validate-yueops-ordinary-1", "validate-yue-node-hy2", "freshness-yueops", "freshness-yue-node", "select-yue-bot", "select-checkin-api")]
        def verdict():
            return policy.results(builds, validations, jobs)
        jobs[0].update(conclusion="failure", steps=[dict(name="Owned pytest verdict for yue-bot", conclusion="failure")])
        self.assertEqual(verdict(), (dict(zip(names, [False, True, True])), True))
        jobs[0]["steps"].append(dict(name="Shared dependency install", conclusion="failure"))
        self.assertEqual(verdict(), (dict(zip(names, [False, False, True])), False))
        jobs[0]["conclusion"] = "success"
        jobs.pop(1)
        jobs[-1]["conclusion"] = "failure"
        self.assertEqual(verdict(), (dict(zip(names, [True, False, False])), True))

    def test_advisories_require_one_successful_completion_for_their_source(self):
        groups = ("yueboard", "yue-node", "yueops")
        builds = [dict(service=g, validation=g) for g in groups]
        validations = [dict(validation=g) for g in groups]
        for group in groups:
            jobs = [dict(name=name, status="completed", conclusion="success") for name in
                    [*("validate-" + g for g in groups), *("freshness-" + g for g in groups if g != group),
                     "select-yueops"]]
            good = dict(name="freshness-" + group, status="completed", conclusion="success")
            for extra in ([], [good, good], [good | {"status": "in_progress"}],
                          [good | {"conclusion": "skipped"}], [good | {"conclusion": "failure"}], [good]):
                services, shared = policy.results(builds, validations, jobs + extra)
                self.assertEqual(services, {g: g != group or extra == [good] for g in groups})
                self.assertEqual(shared, services["yueops"])

    def test_validate_executors_leave_live_audits_to_freshness(self):
        jobs = yaml.safe_load((ROOT / ".github/workflows/build.yml").read_text())["jobs"]
        self.assertIn("freshness", jobs["validation-evidence"]["needs"])
        self.assertIn("validate", jobs["validation-evidence"]["needs"])
        for job in ("validate", "ops-service-selection"):
            self.assertEqual(jobs[job]["env"]["NPM_CONFIG_AUDIT"], "false")
            commands = "\n".join(step.get("run", "") for step in jobs[job]["steps"])
            paths = set(re.findall(r"\.ci-policy/(scripts/[\w.-]+\.(?:sh|py))", commands))
            self.assertIn("scripts/ops-validation-dependencies.sh", paths)
            if job == "validate":
                self.assertIn("scripts/board-validation-output.py", paths)
                paths.add("scripts/board-validation.sh")  # Invoked by the output adapter.
            for path in paths:
                commands += "\n" + (ROOT / path).read_text()
            self.assertNotRegex(commands, r"pip-audit|(?:p?npm)[- ]audit|govulncheck\s+\./|bash scripts/check-vulnerabilities\.sh")

        fresh = jobs["freshness"]
        self.assertEqual(fresh["needs"], ["plan"])
        self.assertEqual(fresh["strategy"]["matrix"]["include"], "${{ fromJSON(needs.plan.outputs.freshness_matrix) }}")
        self.assertEqual(fresh["name"], "freshness-${{ matrix.validation }}")
        steps = fresh["steps"]
        for group, gate in (("yueops", "ops-validation-python-audit.sh"),
                            ("yueops", "ops-validation-npm-audit.sh"),
                            ("yueboard", "board-frontend-audit.sh"),
                            ("yueboard", 'govulncheck" ./...'),
                            ("yue-node", "bash scripts/check-vulnerabilities.sh")):
            owners = [step for step in steps if gate in step.get("run", "")]
            self.assertEqual(len(owners), 1, gate)
            self.assertEqual(owners[0]["if"], f"matrix.validation == '{group}'")
            self.assertNotIn("continue-on-error", owners[0])

    def test_publish_cell_uses_only_its_own_result_and_artifact(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/build.yml").read_text())
        publish = workflow["jobs"]["publish"]["steps"]
        gate = publish[0]
        self.assertEqual(gate["env"]["SERVICE"], "${{ matrix.service }}")
        self.assertEqual(gate["env"]["SERVICES"], "${{ needs.validation-evidence.outputs.services }}")
        services = json.dumps({"yue-bot": False, "checkin-api": True})
        for service, expected in (("yue-bot", 1), ("checkin-api", 0), ("missing", 1)):
            ran = subprocess.run(["bash", "-c", gate["run"]], capture_output=True,
                                 env=dict(os.environ, SERVICES=services, SERVICE=service))
            self.assertEqual(ran.returncode, expected)
        download = next(step for step in publish if step.get("name") == "Download this service selection verdict")
        self.assertTrue(download["with"]["name"].endswith("-${{ matrix.service }}"))

    def test_quarantine_and_fallback_in_pytest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tests = root / "tests"
            tests.mkdir()
            (root / "pytest.ini").write_text("[pytest]\n")
            module = "tests/test_bot_fixture.py"
            (root / module).write_text("def test_bad(): assert False\ndef test_other(): assert False\n")
            env = dict(os.environ, PYTHONPATH=str(ROOT / "scripts"), PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
                       YUETO_OPS_TEST_SOURCE=tmp, YUETO_OWNED_FAILURES=tmp, YUETO_SHARED_SELECTION="[]")
            def run(case):
                return subprocess.run([sys.executable, "-m", "pytest", "-p", "ops_quarantine", "-q", case],
                                      cwd=root, env=env, capture_output=True, text=True)
            nodeid = module + "::test_bad"
            self.assertEqual(run(nodeid).returncode, 1)
            env["YUETO_SHARED_SELECTION"] = '[{"service":"yue-bot"}]'
            self.assertEqual(run(nodeid).returncode, 0)
            self.assertTrue((root / "yue-bot").is_file())
            env["YUETO_SHARED_SELECTION"] = "[]"
            entry = dict(nodeid=nodeid, owner="ops", reason="fixture", added="2020-01-01", expires="2099-01-01")
            path = tests / "quarantine.json"
            path.write_text(json.dumps(dict(schema=1, entries=[entry])))
            ran = run(nodeid)
            self.assertEqual(ran.returncode, 0, ran.stderr)
            self.assertIn("1 xfailed", ran.stdout)
            self.assertEqual(run(module + "::test_other").returncode, 1)
            entry["expires"] = "2021-01-01"
            path.write_text(json.dumps(dict(schema=1, entries=[entry])))
            ran = run(nodeid)
            self.assertNotEqual(ran.returncode, 0)
            self.assertIn("expired quarantine entry", ran.stderr)
