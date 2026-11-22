"""Exercise the per-image publish decision and source quarantine with real pytest."""
import importlib.util
import json
import os
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
                ("validate-yueops-ordinary-1", "validate-yue-node-hy2", "select-yue-bot", "select-checkin-api")]
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
