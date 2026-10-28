"""Execute the workflow cache planner and real Go consumers with isolated caches."""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/build.yml"
CACHE_ACTION = "actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9"


def step(name):
    match = re.search(
        r"^      - name: " + re.escape(name) + r"\n(.*?)(?=^      - |\Z)",
        WORKFLOW.read_text(), re.M | re.S,
    )
    assert match, f"missing actual workflow consumer: {name}"
    return match.group(1)


def scalar(body, name):
    match = re.search(r"^ +"+re.escape(name)+r": (.+)$", body, re.M)
    assert match, f"missing {name}"
    return match.group(1)


def output_input(body, field, outputs):
    expression = scalar(body, field)
    match = re.fullmatch(r"\$\{\{ steps\.go_cache\.outputs\.([a-z_]+) \}\}", expression)
    assert match, f"unexpected cache expression: {expression}"
    return outputs[match.group(1)]


class GoCachePolicyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.env = dict(os.environ, GITHUB_REPOSITORY="onesyue/yueto-ci",
                        GITHUB_REF="refs/heads/master", GITHUB_EVENT_NAME="workflow_dispatch",
                        CACHE_RUNNER="ubuntu-24.04", RUNNER_ENVIRONMENT="github-hosted",
                        RUNNER_OS="Linux", RUNNER_ARCH="X64", ImageOS="ubuntu24",
                        ImageVersion="20261020.1", SOURCE_REPOSITORY="onesyue/yueboard",
                        VALIDATION_KIND="yueboard", NODE_PROFILE="", YUE_CI_PYTHON=sys.executable,
                        GITHUB_OUTPUT=str(self.root / "output"), GOWORK="off")
        self.git("init", "-q")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "Fixture")
        self.git("config", "commit.gpgsign", "false")
        self.git("remote", "add", "origin", "https://github.com/onesyue/yueboard")
        (self.source / "go.mod").write_text("module cache.example/fixture\n\ngo 1.23\n")
        (self.source / "go.sum").write_text("")
        (self.source / "fixture.go").write_text("package fixture\nconst Value = 1\n")
        self.commit()
        (self.source / ".ci-policy").symlink_to(ROOT, target_is_directory=True)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.go_env = dict(GOVERSION="go1.27.2", GOOS="linux", GOARCH="amd64",
                           GOHOSTOS="linux", GOHOSTARCH="amd64", CGO_ENABLED="1",
                           CC="gcc", GOMODCACHE=str(self.root / "modules"),
                           GOCACHE=str(self.root / "compiler"))
        (self.bin / "go").write_text(
            "#!" + sys.executable + "\nimport os\nprint(os.environ['FIXTURE_GO_ENV'])\n")
        (self.bin / "gcc").write_text("#!/bin/sh\necho 'gcc fixture 14.2'\n")
        for tool in self.bin.iterdir():
            tool.chmod(0o755)
        self.env["PATH"] = str(self.bin) + os.pathsep + os.environ["PATH"]

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.source,
                                       stderr=subprocess.DEVNULL, text=True).strip()

    def commit(self):
        self.git("add", "go.mod", "go.sum", "fixture.go")
        self.git("commit", "-qm", "fixture", "--allow-empty")
        self.git("update-ref", "refs/remotes/origin/master", "HEAD")

    def plan(self, **changes):
        output = Path(self.env["GITHUB_OUTPUT"])
        output.write_text("")
        body = step("Plan trusted Go caches")
        environment = dict(self.env, FIXTURE_GO_ENV=json.dumps(self.go_env), **changes)
        context = dict(zip(
            ("matrix.validation", "matrix.repo", "matrix.node_profile", "github.event.inputs.runner"),
            (environment.pop(key) for key in (
                "VALIDATION_KIND", "SOURCE_REPOSITORY", "NODE_PROFILE", "CACHE_RUNNER")),
        ))
        bindings = re.search(r"^        env:\n((?:          .*\n)*)", body, re.M)
        self.assertIsNotNone(bindings, "execute the actual workflow environment bindings")
        for line in bindings.group(1).splitlines():
            key, value = line.strip().split(": ", 1)
            expression = re.fullmatch(r"\$\{\{ (.+) \}\}", value)
            environment[key] = context[expression.group(1)] if expression else ast.literal_eval(value)
        command = ast.literal_eval(scalar(body, "run"))
        result = subprocess.run(["bash", "-eu", "-c", command], cwd=self.source,
                                env=environment,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        values = dict(line.split("=", 1) for line in output.read_text().splitlines())
        self.assertIn("enabled", values, "planner entry point must actually execute")
        return values

    def test_exact_hit_and_changed_source_use_actual_cache_inputs(self):
        first = self.plan()
        self.assertEqual(first["enabled"], "true")
        self.assertEqual(self.plan(), first)
        compiler = step("Restore and refresh Go compiler cache")
        module = step("Restore Go modules")
        (self.source / "fixture.go").write_text("package fixture\nconst Value = 2\n")
        self.commit()
        changed = self.plan()
        self.assertNotEqual(output_input(compiler, "key", changed), output_input(compiler, "key", first))
        self.assertEqual(output_input(compiler, "restore-keys", changed), first["compiler_restore"])
        self.assertTrue(first["compiler_key"].startswith(changed["compiler_restore"]))
        self.assertEqual(output_input(module, "key", first), output_input(module, "key", changed))
        self.assertEqual(output_input(compiler, "path", changed), self.go_env["GOCACHE"])
        self.assertEqual(output_input(module, "path", changed), self.go_env["GOMODCACHE"])
        self.assertNotIn("restore-keys:", module)
        self.assertNotIn("\n", changed["compiler_restore"])
        self.assertLess(len(changed["compiler_key"]), 512)

    def test_dependency_toolchain_image_and_workload_cannot_share_fallback(self):
        first = self.plan()
        for field in ("GOVERSION", "GOARCH", "CGO_ENABLED", "GOEXPERIMENT"):
            with self.subTest(field=field):
                before = self.go_env.copy()
                self.go_env[field] = "different"
                self.assertNotEqual(self.plan()["compiler_restore"], first["compiler_restore"])
                self.go_env = before
        self.assertNotEqual(self.plan(ImageVersion="changed")["compiler_restore"], first["compiler_restore"])
        (self.source / "go.sum").write_text("different dependency\n")
        self.commit()
        dependency = self.plan()
        self.assertNotEqual(dependency["compiler_restore"], first["compiler_restore"])
        self.assertNotEqual(dependency["module_key"], first["module_key"])
        vendor = self.source / "vendor"
        vendor.mkdir()
        (vendor / "modules.txt").write_text("# vendored fixture\n")
        self.git("add", "vendor/modules.txt")
        self.commit()
        self.git("remote", "set-url", "origin", "https://github.com/onesyue/yue-node")
        args = dict(VALIDATION_KIND="yue-node", SOURCE_REPOSITORY="onesyue/yue-node")
        hy2 = self.plan(**args, NODE_PROFILE="hy2")
        vless = self.plan(**args, NODE_PROFILE="vless")
        self.assertEqual(hy2["enabled"], "true")
        self.assertNotEqual(hy2["compiler_restore"], vless["compiler_restore"])

    def test_untrusted_local_unknown_and_dirty_inputs_do_not_read_or_write(self):
        for changes in (
            {"GITHUB_REF": "refs/heads/feature"},
            {"GITHUB_EVENT_NAME": "pull_request"},
            {"GITHUB_REPOSITORY": "fork/yueto-ci"},
            {"SOURCE_REPOSITORY": "fork/yueboard"},
            {"CACHE_RUNNER": "yue-local-release"},
            {"RUNNER_ENVIRONMENT": "self-hosted"},
            {"ImageVersion": ""},
            {"NODE_PROFILE": "unknown"},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(self.plan(**changes), {"enabled": "false"})
        (self.source / "fixture.go").write_text("package fixture\nconst Value = 3\n")
        self.assertEqual(self.plan(), {"enabled": "false"})
        self.git("add", "fixture.go")
        self.git("commit", "-qm", "unmerged source")
        self.assertEqual(self.plan(), {"enabled": "false"})
        self.git("update-ref", "-d", "refs/remotes/origin/master")
        self.assertEqual(self.plan(), {"enabled": "false"})

    def test_missing_tool_metadata_is_optional_but_does_not_claim_a_cache_hit(self):
        (self.bin / "go").write_text("#!/bin/sh\nexit 1\n")
        self.assertEqual(self.plan(), {"enabled": "false"})

    def test_workflow_gates_and_optional_cache_failures_remain_independent(self):
        for name in ("Restore Go modules", "Restore and refresh Go compiler cache"):
            body = step(name)
            self.assertEqual(scalar(body, "uses"), CACHE_ACTION + " # v6.1.0")
            self.assertEqual(scalar(body, "if"), "steps.go_cache.outputs.enabled == 'true'")
            self.assertEqual(scalar(body, "continue-on-error"), "true")
            self.assertEqual(scalar(body, "SEGMENT_DOWNLOAD_TIMEOUT_MINS"), "'2'")
            self.assertNotIn("save-always:", body)
        # No service validation consumer can acquire a cache-hit skip condition.
        self.assertEqual(scalar(step("Validate yue-node"), "if"),
                         "matrix.validation == 'yue-node'")
        board_roles = {
            "Validate YueBoard backend quality gates": "quality",
            "Validate YueBoard protocol compatibility": "quality",
            "Validate YueBoard PostgreSQL integration": "postgres",
            "Validate YueBoard clean PostgreSQL lifecycle": "postgres",
            "Validate YueBoard PostgreSQL module and migration integration": "migration",
            "Validate YueBoard frontend lint": "frontends",
            "Validate YueBoard component tests": "components",
            "Validate YueBoard end-to-end suite": "e2e",
            "Validate YueBoard responsive and design contracts": "frontends",
        }
        workspace_steps = {
            "Validate YueBoard frontend lint",
            "Validate YueBoard component tests",
            "Validate YueBoard end-to-end suite",
        }
        for name, role in board_roles.items():
            expected = ("matrix.validation == 'yueboard' && "
                        "(matrix.board_role == 'postgres' || matrix.board_role == 'migration')"
                        if name == "Validate YueBoard PostgreSQL integration"
                        else f"matrix.validation == 'yueboard' && matrix.board_role == '{role}'")
            if name in workspace_steps:
                expected += " && steps.board_frontend.outputs.layout == 'workspace'"
            self.assertEqual(scalar(step(name), "if"), expected)
        workflow = WORKFLOW.read_text()
        self.assertLess(workflow.index("- name: Restore and refresh Go compiler cache"),
                        workflow.index("- name: Keep Go test execution independent"))
        self.assertLess(workflow.index("- name: Keep Go test execution independent"),
                        workflow.index("- name: Validate yue-node\n"))
        self.assertEqual(scalar(step("Set up Go"), "cache"), "false")

    def test_real_go_cold_restored_changed_source_and_missing_cache(self):
        real_go = shutil.which("go")
        self.assertIsNotNone(real_go, "real Go execution is required; never skip")
        env = dict(os.environ, GOCACHE=str(self.root / "real-compiler"),
                   GOMODCACHE=str(self.root / "real-modules"), GOWORK="off", GOFLAGS="",
                   GOTOOLCHAIN="local", GOPROXY="off")

        def run(*args):
            result = subprocess.run([real_go, *args], cwd=self.source, env=env,
                                    capture_output=True, text=True, timeout=90)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result.stdout + result.stderr

        first = self.plan()
        compiler = step("Restore and refresh Go compiler cache")
        store = self.root / "cache-service"
        store.mkdir()
        key = output_input(compiler, "key", first)
        cold = run("build", "-x", "./...")
        self.assertIn("compile ", cold)
        shutil.copytree(env["GOCACHE"], store / key)
        shutil.rmtree(env["GOCACHE"])
        shutil.copytree(store / key, env["GOCACHE"])
        self.assertNotIn("compile ", run("build", "-x", "./..."))
        (self.source / "fixture.go").write_text("package fixture\nconst Value = 4\n")
        self.commit()
        changed = self.plan()
        fallback = output_input(compiler, "restore-keys", changed)
        self.assertEqual([p.name for p in store.iterdir() if p.name.startswith(fallback)], [key])
        self.assertIn("compile ", run("build", "-x", "./..."))
        successor = output_input(compiler, "key", changed)
        shutil.copytree(env["GOCACHE"], store / successor)
        self.assertTrue((store / key).is_dir(), "immutable predecessor was not overwritten")
        shutil.rmtree(env["GOCACHE"])
        shutil.copytree(store / successor, env["GOCACHE"])
        self.assertNotIn("compile ", run("build", "-x", "./..."))
        # Remote loss is optional, not a validation bypass.
        shutil.rmtree(env["GOCACHE"])
        self.assertIn("compile ", run("build", "-x", "./..."))
        (self.source / "fixture_test.go").write_text(
            'package fixture\nimport "testing"\nfunc TestValue(t *testing.T) {'
            'if Value != 4 { t.Fatal("wrong source") }}\n')
        run("test", "./...")
        self.assertIn("(cached)", run("test", "./..."))
        clear = scalar(step("Keep Go test execution independent of compiler cache"), "run")
        result = subprocess.run(["bash", "-eu", "-c", clear], cwd=self.source, env=env,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("(cached)", run("test", "./..."))
        self.assertNotIn("compile ", run("build", "-x", "./..."))


if __name__ == "__main__":
    unittest.main()
