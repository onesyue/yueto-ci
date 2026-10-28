"""Static UI units: catalog, unit-scoped fingerprint, promote gates, poll.

The four scratch units share one contract:

* services.json and validation-targets.json name the same repo, ref, and
  validation, and each unit runs only lint / tsc / unit / a11y / bundle budget;
* the fingerprint contains the unit path and the unit Dockerfile. A pnpm
  workspace unit also contains the root manifests and the workspace packages
  required to build its artifact paths; a copy outside that set is unknown;
* promote-source-gate plus the SBOM, cosign, and SLSA steps apply to ui-*
  with no per-service skip;
* poll dispatches a unit with promote=true only when those inputs changed.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
UI_UNITS = ("ui-console", "ui-miniapp", "ui-site", "ui-board-web")
CHECKS = ["lint", "tsc", "unit", "a11y", "bundle-budget"]
GATES = (
    "Validate complete platform SBOM set",
    "Sign & attest image (Sigstore keyless)",
    "Generate signed GitHub build provenance",
)
PROMOTE_STEP = "Authorize and promote verified default-branch digest"


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


UI = load("ui_static_units_under_test", "ui_static_units.py")
FP = load("ui_fingerprint_under_test", "input-fingerprint.py")
GATE = load("ui_promote_gate_under_test", "promote-source-gate.py")


def step_condition(workflow: str, name: str) -> str:
    start = workflow.index(f"      - name: {name}\n")
    lines = []
    for line in workflow[start:].splitlines()[1:]:
        if line.startswith("      - name:") or (line and not line.startswith(" ")):
            break
        if line.startswith("        if:"):
            lines.append(line.strip())
        elif lines and line.startswith("          "):
            lines.append(line.strip())
        elif lines:
            break
    return " ".join(lines)


def step_body(workflow: str, name: str) -> str:
    start = workflow.index(f"      - name: {name}\n")
    rest = workflow[start:]
    cuts = []
    nxt = rest.find("\n      - name: ", 1)
    if nxt != -1:
        cuts.append(nxt)
    job = re.search(r"\n  [a-z0-9-]+:\n", rest[1:])
    if job is not None:
        cuts.append(job.start() + 1)
    end = min(cuts) if cuts else len(rest)
    return rest[:end]


class CatalogTest(unittest.TestCase):
    def test_services_and_validation_match(self) -> None:
        services = {row["service"]: row for row in UI.services()}
        targets = {row["service"]: row for row in UI.targets()}
        self.assertEqual(UI.CHECKS, CHECKS)
        for name in UI_UNITS:
            image = services[name]
            target = targets[name]
            self.assertEqual(set(image), UI.SERVICE_KEYS)
            self.assertEqual(set(target), UI.UI_TARGET_KEYS)
            self.assertEqual(image["repo"], target["repo"])
            self.assertEqual(image["ref"], target["ref"])
            self.assertEqual(image["validation"], target["validation"])
            self.assertEqual(image["validation"], name)
            self.assertEqual(image["group"], name)
            self.assertEqual(image["context"], ".")
            self.assertEqual(image["dockerfile"], f"services/{name}/Dockerfile")
            self.assertEqual(image["platforms"], "linux/amd64")
            self.assertEqual(target["checks"], CHECKS)
            self.assertEqual(target["unit_path"], UI.unit_scope(image))
            self.assertIn(target["frontend_step"], (ROOT / ".github/workflows/build.yml").read_text())
            self.assertIn(target["package_manager"], ("npm", "pnpm"))
            self.assertIn(image["repo"], ("onesyue/yueops", "onesyue/yueboard"))
        self.assertEqual(targets["ui-console"]["unit_path"], "frontend")
        self.assertEqual(targets["ui-miniapp"]["unit_path"], "telegram-bot/yue/miniapp")
        self.assertEqual(targets["ui-site"]["unit_path"], "site")
        self.assertEqual(targets["ui-board-web"]["unit_path"], "web")
        self.assertEqual(targets["ui-board-web"]["layout"], "pnpm-workspace")
        self.assertEqual(targets["ui-board-web"]["artifact_paths"], ["web", "web-admin"])
        for name in ("ui-console", "ui-miniapp", "ui-site"):
            self.assertEqual(targets[name]["layout"], "package")
            self.assertEqual(targets[name]["artifact_paths"], [targets[name]["unit_path"]])
        self.assertEqual(targets["ui-console"]["frontend_step"], "Validate yueops frontend")
        self.assertEqual(targets["ui-board-web"]["frontend_step"], "Validate yueboard frontends")
        self.assertEqual(services["ui-console"]["repo"], "onesyue/yueops")
        self.assertEqual(services["ui-board-web"]["repo"], "onesyue/yueboard")

    def test_planner_selects_one_image_and_one_frontend_validation(self) -> None:
        exact = "a" * 40
        for name, repo in (
            ("ui-console", "onesyue/yueops"),
            ("ui-board-web", "onesyue/yueboard"),
        ):
            result = subprocess.run(
                ["bash", str(ROOT / "scripts/plan-build-targets.sh"), name, exact],
                cwd=ROOT, check=True, capture_output=True, text=True,
            )
            plan = json.loads(result.stdout)
            self.assertEqual([row["service"] for row in plan["matrix"]], [name])
            self.assertEqual(plan["matrix"][0]["dockerfile"], f"services/{name}/Dockerfile")
            self.assertTrue(plan["has_builds"])
            self.assertEqual(plan["validation_matrix"], [{
                "repo": repo, "ref": exact, "validation": name,
            }])

    def test_frontend_fastlane_reuses_the_existing_steps_and_skips_the_gauntlet(self) -> None:
        workflow = (ROOT / ".github/workflows/build.yml").read_text()
        console = step_body(workflow, "Validate yueops frontend")
        board = step_body(workflow, "Validate yueboard frontends")
        self.assertIn(
            "if: matrix.validation == 'yueops' && (matrix.ops_role == 'native' || matrix.ops_role == 'legacy')",
            console,
        )
        self.assertIn("npm run lint", console)
        self.assertIn("if: matrix.validation == 'yueboard' && (matrix.board_role == 'frontends' || matrix.board_role == 'components' || matrix.board_role == 'e2e')", board)
        self.assertIn("pnpm --filter yueboard-web", board)
        board_lint = step_body(workflow, "Validate YueBoard frontend lint")
        self.assertIn("pnpm run lint", board_lint)
        ui = step_body(workflow, "Validate UI static unit")
        self.assertIn("if: startsWith(matrix.validation, 'ui-')", ui)
        self.assertIn("ui_static_units.py validate", ui)
        self.assertNotIn("go test", ui)
        self.assertNotIn("pytest", ui)
        self.assertNotIn("migration_base", ui)
        script = (ROOT / "scripts/ui_static_units.py").read_text()
        self.assertIn('["npm", "run", "lint"]', script)
        self.assertIn('"run", "lint"', script)
        self.assertIn('["npm", "test"]', script)
        self.assertIn('"test:a11y"', script)
        self.assertIn('"bundle-budget"', script)
        self.assertIn('"tsc", "--noEmit"', script)

    def test_validation_plan_runs_only_the_five_frontend_checks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            frontend = source / "frontend"
            frontend.mkdir()
            (frontend / "package.json").write_text("{}\n")
            workdir, prelude, checks = UI.validation_plan(source, "ui-console")
            self.assertEqual(workdir, frontend)
            self.assertEqual(prelude, [])
            self.assertEqual(checks, [
                ["npm", "ci", "--ignore-scripts"],
                ["npm", "run", "lint"],
                ["npx", "--no-install", "tsc", "--noEmit"],
                ["npm", "test"],
                ["npm", "run", "test:a11y"],
                ["npm", "run", "bundle-budget"],
            ])
            flat = " ".join(" ".join(command) for command in checks)
            for forbidden in ("pytest", "go test", "squawk", "migration", "npm run build"):
                self.assertNotIn(forbidden, flat)

            web = source / "web"
            web.mkdir()
            (web / "package.json").write_text(json.dumps({
                "name": "yueboard-web", "packageManager": "pnpm@11.27.1",
            }))
            (source / "pnpm-workspace.yaml").write_text("packages:\n  - web\n")
            workdir, prelude, checks = UI.validation_plan(source, "ui-board-web")
            self.assertEqual(workdir, source)
            self.assertEqual(prelude, [
                ["corepack", "enable"],
                ["corepack", "install", "--global", "pnpm@11.27.1"],
            ])
            self.assertEqual(checks[0], ["pnpm", "install", "--frozen-lockfile", "--ignore-scripts"])
            self.assertEqual(checks[1], ["pnpm", "--filter", "yueboard-web", "run", "lint"])
            self.assertEqual(checks[2][:4], ["pnpm", "--filter", "yueboard-web", "exec"])
            self.assertIn("--ignore-scripts", " ".join(checks[0]))

    def test_real_fastlane_stops_on_the_failing_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            unit = source / "frontend"
            unit.mkdir()
            (unit / "package.json").write_text("{}\n")
            bindir = source / "bin"
            bindir.mkdir()
            log = source / "calls"
            for tool in ("npm", "npx"):
                path = bindir / tool
                path.write_text(textwrap.dedent(f"""\
                    #!{os.sys.executable}
                    import os, sys
                    line = {tool!r} + ' ' + ' '.join(sys.argv[1:])
                    open(os.environ['CALL_LOG'], 'a').write(line + '\\n')
                    if os.environ.get('FAIL') and line == os.environ['FAIL']:
                        raise SystemExit(9)
                """))
                path.chmod(0o755)
            env = {**os.environ, "PATH": str(bindir) + os.pathsep + os.environ["PATH"], "CALL_LOG": str(log)}
            for failure, expected in (
                ("", [
                    "npm ci --ignore-scripts",
                    "npm run lint",
                    "npx --no-install tsc --noEmit",
                    "npm test",
                    "npm run test:a11y",
                    "npm run bundle-budget",
                ]),
                ("npm run lint", ["npm ci --ignore-scripts", "npm run lint"]),
            ):
                log.write_text("")
                result = subprocess.run(
                    [os.sys.executable, str(ROOT / "scripts/ui_static_units.py"), "validate",
                     "--validation", "ui-console", "--source", str(source)],
                    env={**env, "FAIL": failure}, capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0 if not failure else 9, result.stderr)
                self.assertEqual(log.read_text().splitlines(), expected)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def board_fixture(
    root: Path,
    *,
    extra_dep: str | None = None,
    ui_field: str = "dependencies",
    ui_spec: str = "workspace:*",
    package_manager: str | None = "pnpm@11.27.1",
    npmrc: bool = False,
    patch: bool = False,
    admin_depends: bool = True,
    root_dep: str | None = None,
) -> None:
    """Minimal yueboard-shaped pnpm workspace.

    ``packages/unused`` depends on ``@yueto/other``. Neither is required by
    web or web-admin unless ``extra_dep`` names one of them.
    """
    root_package: dict = {"private": True}
    if root_dep:
        root_package["dependencies"] = {root_dep: "workspace:*"}
    if package_manager is not None:
        root_package["packageManager"] = package_manager
    if patch:
        root_package["pnpm"] = {"patchedDependencies": {"left-pad@1.0.0": "patches/left-pad@1.0.0.patch"}}
        write_json(root / "patches/left-pad@1.0.0.patch", {"not": "json"})
        (root / "patches/left-pad@1.0.0.patch").write_text("--- a/a\n+++ b/a\n", encoding="utf-8")
    write_json(root / "package.json", root_package)
    (root / "pnpm-workspace.yaml").write_text(
        "packages:\n  - web\n  - web-admin\n  - packages/*\n",
        encoding="utf-8",
    )
    (root / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    write_json(root / "packages/ui/package.json", {"name": "@yueto/ui", "version": "0.0.0", "private": True})
    (root / "packages/ui/index.js").write_text("exports.mark = 'ui'\n", encoding="utf-8")
    write_json(root / "packages/unused/package.json", {
        "name": "@yueto/unused",
        "version": "0.0.0",
        "private": True,
        "dependencies": {"@yueto/other": "workspace:*"},
    })
    (root / "packages/unused/index.js").write_text("exports.mark = 'unused'\n", encoding="utf-8")
    write_json(root / "packages/other/package.json", {"name": "@yueto/other", "version": "0.0.0", "private": True})
    (root / "packages/other/index.js").write_text("exports.mark = 'other'\n", encoding="utf-8")
    web_deps = {"@yueto/ui": ui_spec}
    if extra_dep:
        web_deps[extra_dep] = "workspace:*"
    web = {"name": "yueboard-web", "private": True, ui_field: web_deps, "scripts": {"build": "node build.js"}}
    write_json(root / "web/package.json", web)
    (root / "web/ui-requires.json").write_text('{"requires_backend":["yueboard"]}\n', encoding="utf-8")
    (root / "web/app.js").write_text("app\n", encoding="utf-8")
    admin: dict = {
        "name": "yueboard-web-admin",
        "private": True,
        "scripts": {"build": "node build.js"},
    }
    if admin_depends:
        admin["dependencies"] = {"@yueto/ui": ui_spec}
    write_json(root / "web-admin/package.json", admin)
    (root / "web-admin/app.js").write_text("admin\n", encoding="utf-8")
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs/readme.md").write_text("outside\n", encoding="utf-8")
    if npmrc:
        (root / ".npmrc").write_text("ignore-scripts=true\n", encoding="utf-8")


SCRATCH = (
    "COPY --from=build /src/unit/dist /dist\n"
    "COPY --from=build /out/ui-manifest.json /ui-manifest.json\n"
)


class DockerfileContractTest(unittest.TestCase):
    def test_scratch_image_contains_only_dist_and_manifest(self) -> None:
        for name in UI_UNITS:
            target = next(row for row in UI.ui_targets() if row["service"] == name)
            if target["layout"] != "package":
                continue
            text = UI.render_dockerfile(name)
            facts = FP.parse_dockerfile(text)
            self.assertEqual(facts.problems, [], text)
            self.assertEqual(facts.sources, [target["unit_path"]])
            self.assertTrue(facts.external_images)
            self.assertTrue(all("@sha256:" in image for image in facts.external_images))
            self.assertEqual(text.split("FROM scratch\n", 1)[1], SCRATCH)
            self.assertIn("ui-requires.json", text)
            self.assertIn("requires_backend", text)
            self.assertIn("source_revision", text)
            self.assertIn("sha256", text)
            self.assertNotIn("pnpm-workspace.yaml", text)
            self.assertNotIn("# syntax=", text)

    def test_console_miniapp_and_site_install_inside_the_unit(self) -> None:
        workflow = (ROOT / ".github/workflows/build.yml").read_text()
        console = step_body(workflow, "Validate yueops frontend")
        self.assertIn("working-directory: frontend", console)
        self.assertIn("npm ci --ignore-scripts", console)
        self.assertIn("npm --prefix telegram-bot/yue/miniapp ci --ignore-scripts", workflow)
        self.assertIn('require(\'./site/package.json\').packageManager', workflow)
        self.assertIn("pnpm --dir site install --frozen-lockfile --ignore-scripts", workflow)
        self.assertIn("COPY frontend/ /src/unit/", UI.render_dockerfile("ui-console"))
        self.assertIn("COPY telegram-bot/yue/miniapp/ /src/unit/", UI.render_dockerfile("ui-miniapp"))
        site = UI.render_dockerfile("ui-site")
        self.assertIn("COPY site/ /src/unit/", site)
        self.assertIn("pnpm install --frozen-lockfile --ignore-scripts", site)
        self.assertIn("WORKDIR /src/unit", site)

    def _render_board(self, root: Path) -> str:
        return UI.render_dockerfile("ui-board-web", root)

    def test_board_dockerfile_copies_the_workspace_closure_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            board_fixture(root)
            text = self._render_board(root)
            facts = FP.parse_dockerfile(text)
            self.assertEqual(facts.problems, [], text)
            self.assertEqual(sorted(facts.sources), [
                "package.json",
                "packages/ui",
                "pnpm-lock.yaml",
                "pnpm-workspace.yaml",
                "web",
                "web-admin",
            ])
            copies = [line for line in text.splitlines() if line.startswith("COPY ") and "--from" not in line]
            self.assertEqual(copies, [
                "COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./",
                "COPY packages/ui/ packages/ui/",
                "COPY web/ web/",
                "COPY web-admin/ web-admin/",
            ])
            self.assertNotIn("packages/unused", text)
            self.assertNotIn("packages/other", text)
            self.assertNotIn("@yueto/unused", text)
            self.assertNotIn("docs/", text)
            self.assertIn("pnpm install --frozen-lockfile --ignore-scripts", text)
            self.assertIn("pnpm --filter yueboard-web --filter yueboard-web-admin run build", text)
            self.assertNotIn("pnpm run build", text.replace(
                "pnpm --filter yueboard-web --filter yueboard-web-admin run build",
                "",
            ))
            self.assertIn("cp -a web/dist/. /src/unit/dist/web/", text)
            self.assertIn("cp -a web-admin/dist/. /src/unit/dist/web-admin/", text)
            self.assertIn("cp web/ui-requires.json /src/unit/ui-requires.json", text)
            self.assertNotIn("WORKDIR /src/unit\n", text)
            self.assertIn("cd /src/unit \\\n", text)
            self.assertEqual(text.split("FROM scratch\n", 1)[1], SCRATCH)
            self.assertIn("requires_backend", text)
            self.assertIn("source_revision", text)
            read_text, list_paths = UI._directory_reader(root)
            entry = next(row for row in UI.ui_services() if row["service"] == "ui-board-web")
            self.assertEqual(
                sorted(facts.sources),
                sorted(UI.allowed_copy_sources(entry, read_text, list_paths())),
            )

    def test_board_closure_follows_dev_file_and_extra_workspace_deps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            board_fixture(root, ui_field="devDependencies", admin_depends=False)
            text = UI.render_dockerfile("ui-board-web", root)
            self.assertIn("COPY packages/ui/ packages/ui/", text)
            self.assertNotIn("packages/unused", text)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            board_fixture(root, ui_spec="file:../packages/ui")
            text = UI.render_dockerfile("ui-board-web", root)
            self.assertIn("COPY packages/ui/ packages/ui/", text)
            self.assertNotIn("packages/other", text)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            board_fixture(root, extra_dep="@yueto/unused")
            text = UI.render_dockerfile("ui-board-web", root)
            self.assertIn("COPY packages/unused/ packages/unused/", text)
            self.assertIn("COPY packages/other/ packages/other/", text)
            self.assertNotIn("docs/", text)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            board_fixture(root, root_dep="@yueto/other")
            text = UI.render_dockerfile("ui-board-web", root)
            self.assertIn("COPY packages/other/ packages/other/", text)
            self.assertNotIn("packages/unused", text)

    def test_board_copies_npmrc_and_declared_patches_only_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            board_fixture(root, npmrc=True, patch=True)
            text = UI.render_dockerfile("ui-board-web", root)
            self.assertIn(
                "COPY package.json pnpm-workspace.yaml pnpm-lock.yaml .npmrc ./",
                text,
            )
            self.assertIn("COPY patches/left-pad@1.0.0.patch patches/left-pad@1.0.0.patch", text)

    def test_board_render_refuses_a_missing_source_or_package_manager(self) -> None:
        with self.assertRaises(UI.ScopeError) as missing:
            UI.render_dockerfile("ui-board-web")
        self.assertIn("--source", str(missing.exception))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            board_fixture(root, package_manager=None)
            with self.assertRaises(UI.ScopeError) as unpinned:
                UI.render_dockerfile("ui-board-web", root)
            self.assertIn("packageManager", str(unpinned.exception))
        result = subprocess.run(
            [os.sys.executable, str(ROOT / "scripts/ui_static_units.py"), "dockerfile", "ui-board-web"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("--source", result.stderr)

    def test_package_units_reject_a_workspace_dependency_when_source_is_present(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            frontend = source / "frontend"
            write_json(frontend / "package.json", {"name": "console", "dependencies": {"react": "^18"}})
            (frontend / "package-lock.json").write_text("{}\n", encoding="utf-8")
            self.assertEqual(
                UI.render_dockerfile("ui-console", source),
                UI.render_dockerfile("ui-console"),
            )
            write_json(frontend / "package.json", {
                "name": "console",
                "dependencies": {"@yueto/kit": "file:../packages/yue-web-kit"},
            })
            with self.assertRaises(UI.ScopeError) as escaped:
                UI.render_dockerfile("ui-console", source)
            self.assertIn("file:../packages/yue-web-kit", str(escaped.exception))
            write_json(frontend / "package.json", {
                "name": "console",
                "dependencies": {"@yueto/ui": "workspace:*"},
            })
            with self.assertRaises(UI.ScopeError) as workspace_dep:
                UI.render_dockerfile("ui-console", source)
            self.assertIn("workspace:*", str(workspace_dep.exception))
            write_json(frontend / "package.json", {"name": "console"})
            (source / "pnpm-workspace.yaml").write_text("packages:\n  - frontend\n", encoding="utf-8")
            with self.assertRaises(UI.ScopeError) as member:
                UI.render_dockerfile("ui-console", source)
            self.assertIn("pnpm workspace", str(member.exception))
            (source / "pnpm-workspace.yaml").write_text("packages:\n  - packages/*\n", encoding="utf-8")
            write_json(source / "packages/ui/package.json", {"name": "@yueto/ui", "private": True})
            self.assertEqual(
                UI.render_dockerfile("ui-console", source),
                UI.render_dockerfile("ui-console"),
            )


class Tree:
    def __init__(self, revisions: dict[str, dict[str, bytes]]):
        self.revisions = revisions
        self.blobs: dict[str, bytes] = {}

    def entries(self, rev: str):
        out = {}
        for path, body in self.revisions[rev].items():
            oid = hashlib.sha1(body).hexdigest()
            self.blobs[oid] = body
            out[path] = ("100644", "blob", oid)
        return out

    def blob(self, oid: str) -> bytes:
        return self.blobs[oid]

    def _get(self, path: str) -> dict:
        older, newer = path.removeprefix("compare/").split("...")
        if older == newer:
            return {"status": "identical"}
        order = sorted(self.revisions)
        return {"status": "ahead" if order.index(older) < order.index(newer) else "behind"}


class FingerprintAndPromoteTest(unittest.TestCase):
    def entry(self) -> dict:
        return next(row for row in UI.ui_services() if row["service"] == "ui-console")

    def files(self, app: bytes, docs: bytes, dockerfile: str | None = None) -> dict[str, bytes]:
        text = dockerfile if dockerfile is not None else UI.render_dockerfile("ui-console")
        return {
            "services/ui-console/Dockerfile": text.encode(),
            "services/ui-console/notes.txt": b"not an input\n",
            "frontend/app.js": app,
            "frontend/ui-requires.json": b'{"requires_backend":["checkin-api"]}\n',
            "docs/readme.md": docs,
            ".gitattributes": b"* text=auto\n",
            ".dockerignore": b"docs/\n",
        }

    def fingerprint(self, app: bytes = b"v1\n", docs: bytes = b"a\n", dockerfile: str | None = None) -> dict:
        tree = Tree({"rev": self.files(app, docs, dockerfile)})
        return FP.compute(tree, "rev", self.entry())

    def test_fingerprint_excludes_paths_outside_the_unit(self) -> None:
        result = self.fingerprint()
        self.assertNotIn("unknown", result, result.get("unknown"))
        blob = json.dumps(result)
        for outside in ("docs/readme.md", ".gitattributes", ".dockerignore", "services/ui-console/notes.txt"):
            self.assertNotIn(outside, blob)
        paths = [row[0] for row in result["files"]]
        self.assertTrue(paths)
        unit = "frontend"
        dockerfile = "services/ui-console/Dockerfile"
        for path in paths:
            self.assertTrue(UI.path_in_unit(path, unit, dockerfile), path)
        self.assertEqual(result["sources"], ["frontend"])
        self.assertIn("frontend/app.js", paths)
        self.assertIn("frontend/ui-requires.json", paths)

    def test_a_dockerfile_that_copies_outside_the_unit_is_unknown(self) -> None:
        text = UI.render_dockerfile("ui-console").replace(
            "COPY frontend/ /src/unit/\n",
            "COPY frontend/ /src/unit/\nCOPY docs/readme.md /src/readme.md\n",
        )
        result = self.fingerprint(dockerfile=text)
        self.assertIn("unknown", result)
        self.assertIn("escape", result["unknown"])
        self.assertNotIn("files", result)
        self.assertNotIn("docs/readme.md", json.dumps({k: v for k, v in result.items() if k != "unknown"}))

    def test_promote_gate_accepts_an_outside_change_and_refuses_a_unit_change(self) -> None:
        base, head, unit = "1" * 40, "2" * 40, "3" * 40
        dockerfile = UI.render_dockerfile("ui-console")
        tree = Tree({
            base: self.files(b"v1\n", b"a\n", dockerfile),
            head: self.files(b"v1\n", b"b\n", dockerfile),
            unit: self.files(b"v2\n", b"b\n", dockerfile),
        })
        entry = self.entry()
        self.assertEqual(FP.compare(FP.compute(tree, base, entry), FP.compute(tree, head, entry)), "unchanged")
        self.assertIn("inputs identical", GATE.gate(tree, FP, entry=entry, source=base, head=head, latest=None))
        with self.assertRaises(GATE.Refused) as caught:
            GATE.gate(tree, FP, entry=entry, source=base, head=unit, latest=None)
        self.assertIn("frontend/app.js", str(caught.exception))

    def test_dockerfile_change_is_a_unit_input_change(self) -> None:
        base, head = "4" * 40, "5" * 40
        changed = UI.render_dockerfile("ui-console").replace("WORKDIR /src\n", "WORKDIR /src\n# unit dockerfile\n")
        tree = Tree({
            base: self.files(b"v1\n", b"a\n"),
            head: self.files(b"v1\n", b"a\n", changed),
        })
        entry = self.entry()
        self.assertEqual(FP.compare(FP.compute(tree, base, entry), FP.compute(tree, head, entry)), "changed")
        self.assertTrue(UI.decide_unit("changed"))
        self.assertFalse(UI.decide_unit("unchanged"))
        self.assertFalse(UI.decide_unit("unknown"))
        self.assertTrue(UI.decide_unit("absent"))


def board_tree(root: Path, dockerfile: str) -> dict[str, bytes]:
    files = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    files["services/ui-board-web/Dockerfile"] = dockerfile.encode()
    return files


class BoardWorkspaceFingerprintTest(unittest.TestCase):
    def entry(self) -> dict:
        return next(row for row in UI.ui_services() if row["service"] == "ui-board-web")

    def test_fingerprint_tracks_the_ui_package_and_refuses_an_extra_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            board_fixture(root)
            dockerfile = UI.render_dockerfile("ui-board-web", root)
            base, head, outside, unused = "1" * 40, "2" * 40, "3" * 40, "4" * 40
            files = board_tree(root, dockerfile)
            changed_ui = dict(files)
            changed_ui["packages/ui/index.js"] = b"exports.mark = 'ui2'\n"
            changed_docs = dict(files)
            changed_docs["docs/readme.md"] = b"edited\n"
            changed_unused = dict(files)
            changed_unused["packages/unused/index.js"] = b"exports.mark = 'unused2'\n"
            extra = dockerfile.replace(
                "COPY packages/ui/ packages/ui/\n",
                "COPY packages/ui/ packages/ui/\nCOPY docs/readme.md /src/readme.md\n",
            )
            tree = Tree({
                base: files,
                head: changed_ui,
                outside: changed_docs,
                unused: changed_unused,
                "e" * 40: board_tree(root, extra),
            })
            entry = self.entry()
            base_fp = FP.compute(tree, base, entry)
            self.assertNotIn("unknown", base_fp, base_fp.get("unknown"))
            paths = [row[0] for row in base_fp["files"]]
            self.assertIn("packages/ui/index.js", paths)
            self.assertIn("web/app.js", paths)
            self.assertIn("web/ui-requires.json", paths)
            self.assertIn("pnpm-lock.yaml", paths)
            self.assertNotIn("packages/unused/index.js", paths)
            self.assertNotIn("packages/other/index.js", paths)
            self.assertNotIn("docs/readme.md", paths)
            self.assertEqual(FP.compare(base_fp, FP.compute(tree, head, entry)), "changed")
            self.assertEqual(FP.compare(base_fp, FP.compute(tree, outside, entry)), "unchanged")
            self.assertEqual(FP.compare(base_fp, FP.compute(tree, unused, entry)), "unchanged")
            escaped = FP.compute(tree, "e" * 40, entry)
            self.assertIn("escape", escaped.get("unknown", ""))
            self.assertIn("docs/readme.md", escaped["unknown"])
            with self.assertRaises(GATE.Refused) as caught:
                GATE.gate(tree, FP, entry=entry, source=base, head=head, latest=None)
            self.assertIn("packages/ui/index.js", str(caught.exception))
            self.assertIn(
                "inputs identical",
                GATE.gate(tree, FP, entry=entry, source=base, head=outside, latest=None),
            )
            self.assertIn(
                "inputs identical",
                GATE.gate(tree, FP, entry=entry, source=base, head=unused, latest=None),
            )

    def test_legacy_board_tree_without_a_workspace_file_stays_on_web(self) -> None:
        only_web = UI.render_dockerfile("ui-site").replace(
            "COPY site/ /src/unit/\n", "COPY web/ /src/unit/\n",
        )
        extra = only_web.replace(
            "COPY web/ /src/unit/\n",
            "COPY web/ /src/unit/\nCOPY package.json /src/package.json\n",
        )
        files = {
            "web/package.json": b'{"name":"yueboard-web"}\n',
            "web/app.js": b"v1\n",
            "package.json": b'{"packageManager":"pnpm@11.27.1"}\n',
            "services/ui-board-web/Dockerfile": only_web.encode(),
        }
        widened = dict(files)
        widened["services/ui-board-web/Dockerfile"] = extra.encode()
        tree = Tree({"a" * 40: files, "b" * 40: widened})
        entry = self.entry()
        known = FP.compute(tree, "a" * 40, entry)
        self.assertNotIn("unknown", known, known.get("unknown"))
        self.assertEqual(known["sources"], ["web"])
        self.assertEqual([row[0] for row in known["files"]], ["web/app.js", "web/package.json"])
        unknown = FP.compute(tree, "b" * 40, entry)
        self.assertIn("escape", unknown.get("unknown", ""))
        self.assertIn("package.json", unknown["unknown"])


class PromoteGatesAreUnconditionalTest(unittest.TestCase):
    def test_sbom_cosign_slsa_and_promote_are_not_skipped_for_ui_units(self) -> None:
        workflow = (ROOT / ".github/workflows/build.yml").read_text()
        for name in GATES:
            condition = step_condition(workflow, name)
            self.assertEqual(condition, "", name)
            body = step_body(workflow, name)
            self.assertNotIn("matrix.service", body)
            self.assertNotIn("ui-", body)
        promote = step_condition(workflow, PROMOTE_STEP)
        self.assertEqual(promote, "if: needs.plan.outputs.promote == 'true'")
        body = step_body(workflow, PROMOTE_STEP)
        self.assertIn("python3 .ci-policy/scripts/promote-source-gate.py", body)
        self.assertIn("SERVICE_NAME: ${{ matrix.service }}", body)
        self.assertNotIn("startsWith(matrix.service", body)
        self.assertNotIn("matrix.validation !=", body)
        # The gate script is the one the product images already use.
        self.assertIn("def gate(", (ROOT / "scripts/promote-source-gate.py").read_text())


class PollDispatchTest(unittest.TestCase):
    def test_product_groups_do_not_include_ui_units(self) -> None:
        poll = (ROOT / ".github/workflows/poll-sources.yml").read_text()
        code = "\n".join(line for line in poll.splitlines() if not line.lstrip().startswith("#"))
        start = code.index("groups=$(jq -c '")
        program = code[start + len("groups=$(jq -c '"):code.index("' services.json)", start)]
        result = subprocess.run(
            ["jq", "-c", program, str(ROOT / "services.json")],
            check=True, capture_output=True, text=True,
        )
        groups = {row["group"] for row in json.loads(result.stdout)}
        self.assertTrue(groups.isdisjoint(set(UI_UNITS)))
        self.assertIn("yueops", groups)
        self.assertIn("yueboard", groups)
        self.assertIn("python3 scripts/ui_static_units.py poll", code)
        self.assertEqual(code.count("-f promote=true"), 1)
        self.assertIn("ui-*)", code[max(0, code.index("-f promote=true") - 600):code.index("-f promote=true")])

    def run_dispatch(self, pending: list[dict]) -> list[str]:
        workflow = (ROOT / ".github/workflows/poll-sources.yml").read_text()
        trigger = workflow.split("- name: Trigger builds", 1)[1]
        lines = trigger.split("        run: |\n", 1)[1].splitlines()
        block = []
        for line in lines:
            if line and not line.startswith("          "):
                break
            block.append(line[10:])
        script = "\n".join(block)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "runs.json").write_text("[]")
            gh = base / "gh"
            gh.write_text(textwrap.dedent("""\
                #!/usr/bin/env bash
                set -euo pipefail
                if [ "$1 $2" = "run list" ]; then
                  jq -r 'length' "$RUNS"
                elif [ "$1 $2" = "workflow run" ]; then
                  printf '%s\\n' "$*" >> "$DISPATCHES"
                else
                  exit 97
                fi
            """))
            gh.chmod(0o755)
            log = base / "dispatches"
            result = subprocess.run(
                ["bash", "-c", script], text=True, capture_output=True, timeout=10,
                env={
                    **os.environ,
                    "PATH": f"{base}{os.pathsep}{os.environ['PATH']}",
                    "RUNS": str(base / "runs.json"),
                    "DISPATCHES": str(log),
                    "GITHUB_REPOSITORY": "onesyue/yueto-ci",
                    "PENDING": json.dumps(pending),
                },
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return log.read_text().splitlines() if log.exists() else []

    def test_poll_promotes_only_a_ui_unit_and_leaves_product_images_unpromoted(self) -> None:
        sha = "a" * 40
        self.assertEqual(self.run_dispatch([
            {"group": "ui-console", "sha": sha, "repo": "onesyue/yueops"},
        ]), [
            f"workflow run build.yml -R onesyue/yueto-ci -f service=ui-console -f ref={sha} -f promote=true",
        ])
        self.assertEqual(self.run_dispatch([
            {"group": "yue-node", "sha": sha, "repo": "onesyue/yue-node"},
        ]), [
            f"workflow run build.yml -R onesyue/yueto-ci -f service=yue-node -f ref={sha} -f promote=false",
        ])
        # An outside-only tree does not select the unit; a unit-path edit does.
        self.assertFalse(UI.decide_unit("unchanged"))
        self.assertTrue(UI.decide_unit("changed"))


if __name__ == "__main__":
    unittest.main()
