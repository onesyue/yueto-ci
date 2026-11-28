"""Per-service YueOps scope: path filter, owned pytest, and promotion verdicts."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ops-service-scope.py"
SHELL = ROOT / "scripts" / "ops-service-owned.sh"
PLANNER = ROOT / "scripts" / "plan-build-targets.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"
MANIFEST = ROOT / "ops-service-scope.json"
SERVICES = ROOT / "services.json"
TARGETS = ROOT / "validation-targets.json"
POSTGRES = "mirror.gcr.io/library/postgres:18@sha256:4ef4dbc939d61acea57712655ddb4b4ab27419c913f94cca0cd57cb3ea3c2280"

_SPEC = importlib.util.spec_from_file_location("ops_service_scope", SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
scope = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(scope)


def _digest(number: int) -> str:
    return "sha256:" + f"{number:064x}"


def _run_scope(args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [os.environ.get("PYTHON", "python3"), str(SCRIPT), *args],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


class OpsServiceScopeTest(unittest.TestCase):
    def planner(self, service: str, paths: list[str] | None = None, *, empty_env: bool = False) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.pop("OPS_CHANGED_PATHS", None)
        if empty_env:
            env["OPS_CHANGED_PATHS"] = ""
        if paths is not None:
            handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
            handle.write("\n".join(paths) + "\n")
            handle.close()
            self.addCleanup(os.unlink, handle.name)
            env["OPS_CHANGED_PATHS"] = handle.name
        return subprocess.run(
            ["bash", str(PLANNER), service],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_scripts_are_executable(self) -> None:
        for path in (SCRIPT, SHELL):
            mode = path.stat().st_mode
            self.assertTrue(mode & stat.S_IXUSR, path.name)

    def test_telegram_only_change_builds_yue_bot_and_keeps_sibling_digests(self) -> None:
        plain = self.planner("all")
        self.assertEqual(plain.returncode, 0, plain.stderr)
        self.assertNotIn("ops_service", plain.stdout)
        empty = self.planner("all", empty_env=True)
        self.assertEqual(empty.stdout, plain.stdout)

        filtered = self.planner("all", paths=["telegram-bot/yue/handlers.py"])
        self.assertEqual(filtered.returncode, 0, filtered.stderr)
        plan = json.loads(filtered.stdout)
        names = [row["service"] for row in plan["matrix"]]
        self.assertEqual(names, ["yue-node", "yue-bot", "yueboard"])
        ops_rows = [row for row in plan["validation_matrix"] if row["validation"] == "yueops"]
        self.assertEqual(len(ops_rows), 1)
        self.assertEqual(ops_rows[0]["ops_service"], "yue-bot")
        self.assertEqual(ops_rows[0]["ops_services"], ["yue-bot"])
        for row in plan["validation_matrix"]:
            if row["validation"] != "yueops":
                self.assertNotIn("ops_service", row)
                self.assertNotIn("ops_services", row)
        self.assertTrue(plan["has_builds"])

        previous = {
            "yue-node": _digest(1),
            "yueops-web": _digest(2),
            "checkin-api": _digest(3),
            "yue-bot": _digest(4),
            "yueboard": _digest(5),
        }
        rebuilt = {name: _digest(100 + index) for index, name in enumerate(names)}
        digests = scope.image_digests(previous, plan, rebuilt)
        self.assertEqual(digests["checkin-api"], previous["checkin-api"])
        self.assertEqual(digests["yueops-web"], previous["yueops-web"])
        self.assertNotEqual(digests["yue-bot"], previous["yue-bot"])
        stale = dict(rebuilt)
        stale["yue-bot"] = previous["yue-bot"]
        with self.assertRaises(scope.ScopeError):
            scope.image_digests(previous, plan, stale)
        extra = dict(rebuilt)
        extra["checkin-api"] = _digest(9)
        with self.assertRaises(scope.ScopeError):
            scope.image_digests(previous, plan, extra)
        missing = dict(rebuilt)
        del missing["yue-bot"]
        with self.assertRaises(scope.ScopeError):
            scope.image_digests(previous, plan, missing)
        odd_previous = dict(previous)
        odd_previous["checkin-api"] = "not-a-digest"
        self.assertEqual(scope.image_digests(odd_previous, plan, rebuilt)["checkin-api"], "not-a-digest")

        group = self.planner("yueops", paths=["telegram-bot/yue/handlers.py"])
        self.assertEqual(group.returncode, 0, group.stderr)
        group_plan = json.loads(group.stdout)
        self.assertEqual([row["service"] for row in group_plan["matrix"]], ["yue-bot"])
        group_digests = scope.image_digests(
            previous,
            group_plan,
            {"yue-bot": _digest(77)},
        )
        self.assertEqual(group_digests["checkin-api"], previous["checkin-api"])
        self.assertEqual(group_digests["yueops-web"], previous["yueops-web"])

    def test_group_dispatch_and_multi_owned_paths(self) -> None:
        both = self.planner("all", paths=["telegram-bot/yue/handlers.py", "frontend/src/app.tsx"])
        self.assertEqual(both.returncode, 0, both.stderr)
        plan = json.loads(both.stdout)
        self.assertEqual(
            [row["service"] for row in plan["matrix"]],
            ["yue-node", "yueops-web", "yue-bot", "yueboard"],
        )
        ops = [row for row in plan["validation_matrix"] if row["validation"] == "yueops"]
        self.assertEqual(ops[0]["ops_services"], ["yue-bot", "yueops-web"])
        self.assertNotIn("ops_service", ops[0])

    def test_unknown_and_shared_paths_keep_every_ops_service(self) -> None:
        cases = [
            ["yueops/runtime.py"],
            ["scripts/foo.sh"],
            ["docs/README.md"],
            ["alembic/versions/x.py"],
            ["telegram-bot/yue/handlers.py", "docs/README.md"],
            ["telegram-bot-extra/x.py"],
            ["services/yue-bot-extra/app.py"],
            [],
        ]
        for paths in cases:
            with self.subTest(paths=paths):
                result = self.planner("all", paths=paths)
                self.assertEqual(result.returncode, 0, result.stderr)
                plan = json.loads(result.stdout)
                ops_names = [row["service"] for row in plan["matrix"] if row["validation"] == "yueops"]
                self.assertEqual(ops_names, ["yueops-web", "checkin-api", "yue-bot"])
                ops = [row for row in plan["validation_matrix"] if row["validation"] == "yueops"]
                self.assertEqual(len(ops), 1)
                self.assertEqual(ops[0]["ops_services"], ["checkin-api", "yue-bot", "yueops-web"])
                self.assertNotIn("ops_service", ops[0])

    def test_path_edges_and_explicit_dispatch_are_not_filtered(self) -> None:
        dotted = self.planner("all", paths=["./telegram-bot/yue/handlers.py"])
        self.assertEqual([row["service"] for row in json.loads(dotted.stdout)["matrix"] if row["validation"] == "yueops"], ["yue-bot"])
        bare = self.planner("all", paths=["telegram-bot"])
        self.assertEqual([row["service"] for row in json.loads(bare.stdout)["matrix"] if row["validation"] == "yueops"], ["yue-bot"])
        windows = self.planner("all", paths=["telegram-bot\\yue\\handlers.py"])
        self.assertEqual([row["service"] for row in json.loads(windows.stdout)["matrix"] if row["validation"] == "yueops"], ["yue-bot"])
        with self.assertRaises(scope.ScopeError):
            scope.affected_services(["/telegram-bot/yue/handlers.py"])
        with self.assertRaises(scope.ScopeError):
            scope.affected_services(["telegram-bot/../frontend/x"])

        plain = self.planner("checkin-api")
        filtered = self.planner("checkin-api", paths=["telegram-bot/yue/handlers.py"])
        self.assertEqual(filtered.returncode, 0, filtered.stderr)
        self.assertEqual(filtered.stdout, plain.stdout)
        self.assertNotIn("ops_service", filtered.stdout)
        full = json.loads(self.planner("all").stdout)
        kept, selection, stamped = scope.filter_plan(full, ["telegram-bot/yue/handlers.py"], "checkin-api")
        self.assertFalse(stamped)
        self.assertEqual(kept, full)
        self.assertEqual([row["service"] for row in selection], ["checkin-api", "yue-bot", "yueops-web"])

    def test_red_yue_bot_verdict_blocks_only_yue_bot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, status in (
                ("yue-bot", "failed"),
                ("yueops-web", "passed"),
                ("checkin-api", "passed"),
            ):
                (root / f"{name}.json").write_text(
                    json.dumps({"service": name, "status": status}) + "\n",
                    encoding="utf-8",
                )
            loaded = scope.load_verdicts(root)
            verdicts = {name: item["status"] for name, item in loaded.items()}
            with self.assertRaises(scope.PromotionRefused):
                scope.assert_promotable("yue-bot", verdicts)
            scope.assert_promotable("yueops-web", verdicts)
            scope.assert_promotable("checkin-api", verdicts)
            refused = _run_scope(["assert-promotable", "--service", "yue-bot", "--verdicts", str(root)])
            self.assertEqual(refused.returncode, 1)
            self.assertEqual(refused.stdout, "")
            allowed = _run_scope(["assert-promotable", "--service", "yueops-web", "--verdicts", str(root)])
            self.assertEqual(allowed.returncode, 0, allowed.stderr)
            (root / "yue-bot.json").unlink()
            with self.assertRaises(scope.PromotionRefused):
                scope.assert_promotable("yue-bot", {name: item["status"] for name, item in scope.load_verdicts(root).items()})
            scope.assert_promotable(
                "checkin-api",
                {name: item["status"] for name, item in scope.load_verdicts(root).items()},
            )
            missing = _run_scope(["assert-promotable", "--service", "yue-bot", "--verdicts", str(root)])
            self.assertEqual(missing.returncode, 1)
            sibling = _run_scope(["assert-promotable", "--service", "checkin-api", "--verdicts", str(root)])
            self.assertEqual(sibling.returncode, 0, sibling.stderr)

    def test_verdict_files_fail_closed(self) -> None:
        with self.assertRaises(scope.ScopeError):
            scope.service_verdicts({"not-a-service": "passed"})
        with self.assertRaises(scope.ScopeError):
            scope.service_verdicts({"yue-bot": "skipped"})
        parsed = scope.service_verdicts({"yue-bot": "passed"})
        self.assertNotIn("checkin-api", parsed)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for outcome, status in (
                ("success", "passed"),
                ("failure", "failed"),
                ("cancelled", "failed"),
                ("skipped", "failed"),
            ):
                path = root / "yue-bot.json"
                written = _run_scope([
                    "write-verdict", "--service", "yue-bot", "--outcome", outcome, "--output", str(path),
                ])
                self.assertEqual(written.returncode, 0, written.stderr)
                self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["status"], status)
            with self.assertRaises(scope.ScopeError):
                scope.write_verdict("yue-bot", "success", root / "other.json")
            nested = root / "nested"
            nested.mkdir()
            (nested / "yue-bot.json").write_text(json.dumps({"service": "yue-bot", "status": "passed"}), encoding="utf-8")
            with self.assertRaises(scope.ScopeError):
                scope.load_verdicts(root, "yue-bot")
            (nested / "yue-bot.json").unlink()
            (root / "yue-bot.json").write_text("{", encoding="utf-8")
            with self.assertRaises(scope.ScopeError):
                scope.load_verdicts(root)
            (root / "yue-bot.json").write_text(
                json.dumps({"service": "checkin-api", "status": "passed"}),
                encoding="utf-8",
            )
            with self.assertRaises(scope.ScopeError):
                scope.load_verdicts(root)
            (root / "notes.json").write_text("{", encoding="utf-8")
            (root / "yue-bot.json").write_text(
                json.dumps({"service": "yue-bot", "status": "passed"}),
                encoding="utf-8",
            )
            with self.assertRaises(scope.ScopeError):
                scope.load_verdicts(root)

    def test_owned_modules_and_shell_selection(self) -> None:
        self.assertNotIn("shell=True", SCRIPT.read_text(encoding="utf-8"))
        shell_text = SHELL.read_text(encoding="utf-8")
        self.assertNotIn("<(", shell_text)
        self.assertNotIn(">(", shell_text)
        self.assertNotIn("mapfile", shell_text)
        mutated = shell_text.replace('done <"$tmp"', 'done < <(cat "$tmp")')
        with self.assertRaises(AssertionError):
            self.assertNotIn("<(", mutated)

        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            tests = source / "tests"
            tests.mkdir()
            for name in (
                "test_bot_one.py",
                "test_miniapp_one.py",
                "test_web_one.py",
                "test_checkin_one.py",
                "test_unrelated.py",
            ):
                (tests / name).write_text("def test_ok():\n    assert True\n", encoding="utf-8")
            (tests / "test_bot_bad name.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
            with self.assertRaisesRegex(scope.ScopeError, "refused"):
                scope.owned_modules("yue-bot", source=source)
            (tests / "test_bot_bad name.py").unlink()
            modules = scope.owned_modules("yue-bot", source=source)
            self.assertEqual(modules, ["tests/test_bot_one.py", "tests/test_miniapp_one.py"])
            with self.assertRaisesRegex(scope.ScopeError, "empty"):
                scope.owned_modules("yue-bot", modules=["tests/test_web_one.py"])
            custom = json.loads(MANIFEST.read_text(encoding="utf-8"))
            custom["tests"]["yueops-web"] = ["tests/test_"]
            with self.assertRaisesRegex(scope.ScopeError, "two services"):
                scope.owned_modules("yue-bot", modules=["tests/test_bot_x.py"], manifest=custom)

            fake_bin = source / ".venv" / "bin"
            fake_bin.mkdir(parents=True)
            fake = fake_bin / "python"
            fake.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\" >> \"$RECORD\"\nexit 0\n", encoding="utf-8")
            fake.chmod(0o755)
            record = source / "record"
            env = os.environ.copy()
            env.update(SERVICE="yue-bot", OPS_SOURCE=str(source), RECORD=str(record))
            ran = subprocess.run(["bash", str(SHELL)], cwd=source, env=env, capture_output=True, text=True, check=False)
            self.assertEqual(ran.returncode, 0, ran.stderr)
            recorded = record.read_text(encoding="utf-8").splitlines()
            self.assertEqual(recorded, ["-m", "pytest", "tests/test_bot_one.py", "tests/test_miniapp_one.py"])
            unset = os.environ.copy()
            unset.pop("SERVICE", None)
            unset["OPS_SOURCE"] = str(source)
            missing = subprocess.run(["bash", str(SHELL)], cwd=source, env=unset, capture_output=True, text=True, check=False)
            self.assertNotEqual(missing.returncode, 0)

            only_web = source / "only-web"
            (only_web / "tests").mkdir(parents=True)
            (only_web / "tests" / "test_web_one.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
            empty_env = os.environ.copy()
            empty_env.update(SERVICE="yue-bot", OPS_SOURCE=str(only_web), RECORD=str(source / "unused"))
            empty = subprocess.run(["bash", str(SHELL)], cwd=only_web, env=empty_env, capture_output=True, text=True, check=False)
            self.assertNotEqual(empty.returncode, 0)
            self.assertIn("empty", empty.stderr)

    def test_changed_paths_uses_migration_base(self) -> None:
        self.assertIn('"cat-file"', SCRIPT.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            init = subprocess.run(["git", "init", "-b", "master"], cwd=repo, capture_output=True, text=True, check=False)
            if init.returncode != 0:
                subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
                subprocess.run(["git", "checkout", "-b", "master"], cwd=repo, check=True, capture_output=True)
            target = repo / "telegram-bot" / "yue"
            target.mkdir(parents=True)
            (target / "handlers.py").write_text("one\n", encoding="utf-8")
            (repo / "yueops").mkdir()
            (repo / "yueops" / "a.py").write_text("shared\n", encoding="utf-8")
            base = self._commit(repo, "base")
            (target / "handlers.py").write_text("two\n", encoding="utf-8")
            subprocess.run(["git", "mv", "yueops/a.py", "frontend-not-yet"], cwd=repo, check=False, capture_output=True)
            renamed = repo / "frontend"
            renamed.mkdir()
            if (repo / "yueops" / "a.py").exists():
                (repo / "yueops" / "a.py").rename(renamed / "a.py")
            else:
                (renamed / "a.py").write_text("shared\n", encoding="utf-8")
            self._commit(repo, "change")
            paths = scope.changed_paths(repo, base)
            self.assertIn("telegram-bot/yue/handlers.py", paths)
            self.assertTrue(any(path.startswith("frontend/") or path.startswith("yueops/") for path in paths))
            listed = _run_scope(["changed-paths", "--source", str(repo), "--base", base])
            self.assertEqual(listed.returncode, 0, listed.stderr)
            self.assertEqual(listed.stdout.splitlines(), paths)
            missing = _run_scope(["changed-paths", "--source", str(repo), "--base", "a" * 40])
            self.assertEqual(missing.returncode, 1)
            self.assertEqual(missing.stdout, "")
            with self.assertRaises(scope.ScopeError):
                scope.changed_paths(repo, "A" * 40)

    def test_planner_invokes_the_filter_only_when_paths_are_present(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scripts = root / "scripts"
            scripts.mkdir()
            (scripts / "plan-build-targets.sh").write_text(PLANNER.read_text(encoding="utf-8"), encoding="utf-8")
            (root / "services.json").write_text(SERVICES.read_text(encoding="utf-8"), encoding="utf-8")
            (root / "validation-targets.json").write_text(TARGETS.read_text(encoding="utf-8"), encoding="utf-8")
            plain = subprocess.run(
                ["bash", str(scripts / "plan-build-targets.sh"), "all"],
                cwd=root,
                env={key: value for key, value in os.environ.items() if key != "OPS_CHANGED_PATHS"},
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(plain.returncode, 0, plain.stderr)
            self.assertNotIn("ops_service", plain.stdout)
            path = root / "paths.txt"
            path.write_text("telegram-bot/yue/handlers.py\n", encoding="utf-8")
            env = os.environ.copy()
            env["OPS_CHANGED_PATHS"] = str(path)
            invoked = subprocess.run(
                ["bash", str(scripts / "plan-build-targets.sh"), "all"],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(invoked.returncode, 0)

    def test_filter_plan_fail_closed_edges(self) -> None:
        plain = self.planner("yue-node")
        raw = plain.stdout
        path = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
        path.write("telegram-bot/yue/handlers.py\n")
        path.close()
        self.addCleanup(os.unlink, path.name)
        copied = _run_scope([
            "filter-plan", "--dispatch", "all", "--paths", path.name, "--selection-output", path.name + ".sel",
        ], stdin=raw)
        self.assertEqual(copied.returncode, 0, copied.stderr)
        self.assertEqual(copied.stdout, raw)
        selection = Path(path.name + ".sel")
        self.addCleanup(selection.unlink, missing_ok=True)
        self.assertEqual(json.loads(selection.read_text(encoding="utf-8")), [])

        full = self.planner("all").stdout
        kept = _run_scope([
            "filter-plan", "--dispatch", "all", "--keep-all", "--selection-output", path.name + ".keep",
        ], stdin=full)
        self.assertEqual(kept.returncode, 0, kept.stderr)
        self.assertEqual(kept.stdout, full)
        keep_selection = json.loads(Path(path.name + ".keep").read_text(encoding="utf-8"))
        self.addCleanup(Path(path.name + ".keep").unlink, missing_ok=True)
        self.assertEqual([row["service"] for row in keep_selection], ["checkin-api", "yue-bot", "yueops-web"])

        missing_paths = _run_scope(["filter-plan", "--dispatch", "all", "--paths", path.name + ".absent"], stdin=full)
        self.assertEqual(missing_paths.returncode, 1)
        self.assertNotEqual(missing_paths.returncode, 2)
        invalid = _run_scope(["filter-plan", "--dispatch", "all", "--keep-all"], stdin="{")
        self.assertEqual(invalid.returncode, 1)
        self.assertEqual(invalid.stdout, "")

        duplicate = json.loads(full)
        ops_row = next(row for row in duplicate["matrix"] if row["service"] == "yue-bot")
        duplicate["matrix"].append(json.loads(json.dumps(ops_row)))
        rejected = _run_scope(["filter-plan", "--dispatch", "all", "--keep-all"], stdin=json.dumps(duplicate) + "\n")
        self.assertEqual(rejected.returncode, 1)

        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        manifest["schema"] = True
        with tempfile.TemporaryDirectory() as temporary:
            document = Path(temporary) / "ops-service-scope.json"
            document.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(scope.ScopeError):
                scope.load_manifest(document, SERVICES)
            overlap = json.loads(MANIFEST.read_text(encoding="utf-8"))
            overlap["owned"]["checkin-api"].append("telegram-bot/")
            document.write_text(json.dumps(overlap), encoding="utf-8")
            with self.assertRaisesRegex(scope.ScopeError, "overlap"):
                scope.load_manifest(document, SERVICES)
            extra_key = json.loads(MANIFEST.read_text(encoding="utf-8"))
            extra_key["extra"] = []
            document.write_text(json.dumps(extra_key), encoding="utf-8")
            with self.assertRaises(scope.ScopeError):
                scope.load_manifest(document, SERVICES)

    def test_validation_only_selection_and_unknown_ops_row(self) -> None:
        validation = {
            "repo": "onesyue/yueops",
            "ref": "master",
            "validation": "yueops",
        }
        plan = {"matrix": [], "validation_matrix": [dict(validation)], "has_builds": False}
        explicit, selection, stamped = scope.filter_plan(plan, ["telegram-bot/yue/handlers.py"], "checkin-api")
        self.assertFalse(stamped)
        self.assertEqual(explicit["has_builds"], False)
        self.assertEqual([row["service"] for row in selection], ["checkin-api"])
        self.assertNotIn("ops_service", explicit["validation_matrix"][0])
        hosted, hosted_selection, hosted_stamped = scope.filter_plan(plan, ["telegram-bot/yue/handlers.py"], "all")
        self.assertTrue(hosted_stamped)
        self.assertEqual(hosted["has_builds"], False)
        self.assertEqual(hosted["validation_matrix"][0]["ops_service"], "yue-bot")
        self.assertEqual([row["service"] for row in hosted_selection], ["yue-bot"])
        kept, kept_selection, kept_stamped = scope.filter_plan(plan, None, "all", keep_all=True)
        self.assertFalse(kept_stamped)
        self.assertEqual([row["service"] for row in kept_selection], ["checkin-api", "yue-bot", "yueops-web"])
        unknown = {
            "matrix": [{
                "service": "not-a-service",
                "repo": "onesyue/yueops",
                "ref": "master",
                "validation": "yueops",
            }],
            "validation_matrix": [dict(validation)],
            "has_builds": True,
        }
        dropped, dropped_selection, dropped_stamped = scope.filter_plan(
            unknown, ["telegram-bot/yue/handlers.py"], "all",
        )
        self.assertTrue(dropped_stamped)
        self.assertEqual(dropped["matrix"], [])
        self.assertEqual(dropped["validation_matrix"], [])
        self.assertEqual(dropped["has_builds"], False)
        self.assertEqual(dropped_selection, [])

    def assert_workflow_gate(self, workflow: str, python_source: str) -> None:
        self.assertIn("\n  ops-service-selection:\n", workflow)
        self.assertIn('"cat-file"', python_source)
        self.assertNotIn("shell=True", python_source)
        self.assertLess(workflow.index("git -C .ops-shard-source rev-parse --verify refs/remotes/origin/master"),
                        workflow.index("- name: Scope YueOps services by changed paths"))
        self.assertLess(workflow.index("- name: Scope YueOps services by changed paths"),
                        workflow.index("- name: Read previous ordinary shard weights"))
        self.assertEqual(workflow.count('echo "matrix=$matrix"'), 1)
        self.assertLess(workflow.index('echo "matrix=$matrix"'),
                        workflow.index("- name: Scope YueOps services by changed paths"))
        scope_step = workflow.split("- name: Scope YueOps services by changed paths", 1)[1].split("\n      - name:", 1)[0]
        self.assertIn("id: ops_scope", scope_step)
        self.assertIn("changed-paths", scope_step)
        self.assertIn("--keep-all", scope_step)
        self.assertIn("yue-local-release", scope_step)
        self.assertIn("python3 scripts/ops-service-scope.py", scope_step)
        job = workflow.split("\n  ops-service-selection:\n", 1)[1].split("\n  publish:\n", 1)[0]
        self.assertIn("fail-fast: false", job)
        self.assertRegex(job, r"(?m)^    timeout-minutes: 120$")
        self.assertNotIn("continue-on-error", job)
        self.assertNotRegex(job, r"(?m)^    permissions:\s*$")
        self.assertNotRegex(job, r"(?m)^    concurrency:\s*$")
        for forbidden in (
            "built-${SOURCE_SHA}",
            "promotion_tag_args=",
            "Authorize and promote verified default-branch digest",
            "CANDIDATE_SOURCE_SHA",
            "Generate signed GitHub build provenance",
            "Record verified candidate digest",
            "Mark this source revision as built",
            "postgresql-18",
        ):
            self.assertNotIn(forbidden, job)
        self.assertIn("Run service-owned pytest selection", job)
        self.assertNotIn("Execute owned Ops pytest selection", job)
        publish = workflow.split("\n  publish:\n", 1)[1]
        self.assertTrue(publish.startswith(
            "    needs: [build, plan, validate, validation-evidence, ops-service-selection]\n"
        ))
        self.assertIn(
            "(needs.ops-service-selection.result == 'success' "
            "|| needs.ops-service-selection.result == 'failure' "
            "|| needs.ops-service-selection.result == 'skipped')",
            publish,
        )
        self.assertIn("Refuse promotion without a passed service selection", workflow)
        self.assertIn("Mark this source revision as built", workflow)
        self.assertLess(workflow.index("Refuse promotion without a passed service selection"),
                        workflow.index("Mark this source revision as built"))
        refuse = workflow.split("- name: Refuse promotion without a passed service selection", 1)[1].split("\n      - name:", 1)[0]
        self.assertIn("python3 .ci-policy/scripts/ops-service-scope.py assert-promotable", refuse)
        self.assertIn(
            "matrix: ${{ steps.resume.outputs.matrix || steps.ops_scope.outputs.matrix || steps.plan.outputs.matrix }}",
            workflow,
        )
        self.assertIn(
            "has_builds: ${{ steps.ops_scope.outputs.has_builds || steps.plan.outputs.has_builds }}",
            workflow,
        )
        self.assertIn(
            "ops_selection_matrix: ${{ steps.ops_scope.outputs.ops_selection_matrix || '[]' }}",
            workflow,
        )
        images = re.findall(r"^    services:\n      postgres:\n        image: ([^\n]+)$", workflow, re.M)
        self.assertEqual(images, [POSTGRES, POSTGRES])
        self.assertNotIn("\n  abort-on-validate-failure:", workflow)
        for gate in ("build",):
            rest = workflow.split(f"\n  abort-on-{gate}-failure:\n", 1)[1]
            # The next job key is indented two spaces. Four-space comments
            # inside the abort job must stay in the slice.
            boundary = re.search(r"\n  (?=\S)", rest)
            abort = rest[: boundary.start()] if boundary else rest
            self.assertIn(f"needs: [plan, {gate}]", abort)
            self.assertNotIn("ops-service-selection", abort)

    def test_workflow_gate_rejects_mutations(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        python_source = SCRIPT.read_text(encoding="utf-8")
        self.assert_workflow_gate(workflow, python_source)
        cases = (
            workflow.replace("Refuse promotion without a passed service selection", "Skip owned selection"),
            workflow.replace("changed-paths", "changed-files"),
            workflow.replace("\n  ops-service-selection:\n", "\n  dropped-selection:\n"),
        )
        for broken in cases:
            with self.subTest(broken=broken[:80]), self.assertRaises(AssertionError):
                self.assert_workflow_gate(broken, python_source)
        with self.assertRaises(AssertionError):
            self.assert_workflow_gate(workflow, python_source.replace('"cat-file"', '"rev-parse"'))
        with self.assertRaises(AssertionError):
            self.assert_workflow_gate(workflow, python_source + "\nshell=True\n")

    def _commit(self, repo: Path, message: str) -> str:
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            [
                "git", "-c", "commit.gpgsign=false", "-c", "user.name=policy",
                "-c", "user.email=policy@example.com", "commit", "-m", message,
            ],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        )
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True)
        return result.stdout.strip()


if __name__ == "__main__":
    unittest.main()
