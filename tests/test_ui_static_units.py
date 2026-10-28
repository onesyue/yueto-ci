"""Static UI units: catalog, unit-scoped fingerprint, promote gates, poll.

The four scratch units share one contract:

* services.json and validation-targets.json name the same repo, ref, and
  validation, and each unit runs only lint / tsc / unit / a11y / bundle budget;
* the fingerprint contains the unit path and the unit Dockerfile, nothing
  outside that set;
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


class DockerfileContractTest(unittest.TestCase):
    def test_scratch_image_contains_only_dist_and_manifest(self) -> None:
        for name in UI_UNITS:
            text = UI.render_dockerfile(name)
            facts = FP.parse_dockerfile(text)
            self.assertEqual(facts.problems, [], text)
            target = next(row for row in UI.ui_targets() if row["service"] == name)
            self.assertEqual(facts.sources, [target["unit_path"]])
            self.assertTrue(facts.external_images)
            self.assertTrue(all(image.endswith("@" + "sha256:" + facts.external_images[0].split("@sha256:")[1]) or "@sha256:" in image for image in facts.external_images))
            final = text.split("FROM scratch\n", 1)[1]
            self.assertEqual(final, (
                "COPY --from=build /src/unit/dist /dist\n"
                "COPY --from=build /out/ui-manifest.json /ui-manifest.json\n"
            ))
            self.assertIn("ui-requires.json", text)
            self.assertIn("requires_backend", text)
            self.assertIn("source_revision", text)
            self.assertIn("sha256", text)
            self.assertNotIn("# syntax=", text)


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
        self.assertFalse(UI.decide_unit("unchanged"))
        self.assertTrue(UI.decide_unit("changed"))


if __name__ == "__main__":
    unittest.main()
