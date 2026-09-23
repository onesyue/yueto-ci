"""P2/P3 shadow analysis: input fingerprints and verification-evidence probe.

Three things are pinned here:

* the fingerprint is *exactly* the BuildKit input set -- changes outside it
  are unchanged, changes inside it (content, mode, ignore file, Dockerfile)
  are changed, and anything unprovable is unknown, never unchanged;
* the evidence probe's identity checks each reject on their own;
* both are wired into build.yml as a non-gating, read-only side job that no
  release step can come to depend on by accident.

Every positive assertion is paired with a mutation that must turn it red.
"""

from __future__ import annotations

import base64
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


FP = load("input_fingerprint", "input-fingerprint.py")
EV = load("verification_evidence", "verification-evidence.py")

ENTRY = {
    "service": "svc", "group": "g", "repo": "onesyue/x", "ref": "master",
    "validation": "x", "context": ".", "dockerfile": "services/svc/Dockerfile",
    "platforms": "linux/amd64",
}
PIN = "@sha256:" + "a" * 64
DOCKERFILE = f"""# syntax=docker/dockerfile:1
FROM python:3.13-slim{PIN} AS build
COPY --from=ghcr.io/astral-sh/uv:0.1{PIN} /uv /bin/
COPY pyproject.toml uv.lock ./
FROM python:3.13-slim{PIN}
# a comment between instructions
COPY --from=build /opt/venv /opt/venv
COPY --chown=65532:65532 app/ ./app/
COPY --chown=65532:65532 \\
     scripts/ ./scripts/
RUN --mount=type=cache,target=/root/.cache true
"""


class Repo:
    """A throwaway git repository with a helper to commit a file map."""

    def __init__(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.git("init", "-q", "-b", "master")
        self.git("config", "user.email", "t@example.invalid")
        self.git("config", "user.name", "t")
        self.git("config", "commit.gpgsign", "false")

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(self.path), *args], check=True, capture_output=True, text=True
        ).stdout.strip()

    def commit(self, files: dict[str, str | None], mode: dict[str, str] | None = None) -> str:
        for rel, body in files.items():
            target = self.path / rel
            if body is None:
                target.unlink()
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body)
        for rel, bits in (mode or {}).items():
            os.chmod(self.path / rel, int(bits, 8))
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", "c")
        return self.git("rev-parse", "HEAD")


BASE_FILES = {
    "services/svc/Dockerfile": DOCKERFILE,
    # Dead: BuildKit never reads a plain .dockerignore beside a -f Dockerfile.
    "services/svc/.dockerignore": "scripts/\n",
    ".dockerignore": "docs/\n*.md\n**/__pycache__/\n",
    "pyproject.toml": "[project]\n",
    "uv.lock": "lock\n",
    "app/main.py": "print(1)\n",
    "app/README.md": "nested md is NOT matched by a root-only *.md\n",
    "app/__pycache__/x.pyc": "junk\n",
    "scripts/deploy.sh": "echo deploy\n",
    "docs/guide.md": "doc\n",
    "tests/test_app.py": "def test(): pass\n",
    "README.md": "root readme\n",
}


class IgnoreSemanticsTest(unittest.TestCase):
    """moby/patternmatcher semantics, the parts our repos actually rely on."""

    def test_root_anchoring_double_star_and_negation(self) -> None:
        rules = FP.IgnoreRules.parse(
            "# comment\n*.md\n**/*_test.go\ndocs/\n/build\ntest/*\n!test/frontend/\n"
        )
        cases = {
            "README.md": True, "app/README.md": False,           # *.md is root-only
            "a/b/x_test.go": True, "x_test.go": True, "x.go": False,
            "docs/a/b.txt": True, "sub/docs/a.txt": False,
            "build": True, "build/x": True, "web/build": False,
            "test/unit/a.go": True, "test/frontend/a.ts": False,
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(rules.ignored(path), expected)

    def test_negation_is_order_sensitive(self) -> None:
        self.assertFalse(FP.IgnoreRules.parse("a/*\n!a/keep\n").ignored("a/keep"))
        self.assertTrue(FP.IgnoreRules.parse("!a/keep\na/*\n").ignored("a/keep"))


class DockerfileParserTest(unittest.TestCase):
    def test_sources_stages_and_caveats(self) -> None:
        facts = FP.parse_dockerfile(DOCKERFILE)
        self.assertEqual(facts.problems, [])
        self.assertEqual(sorted(facts.sources), ["app", "pyproject.toml", "scripts", "uv.lock"])
        self.assertEqual(len(facts.external_images), 3)
        self.assertTrue(any("floating Dockerfile frontend" in c for c in facts.caveats))

    def test_unprovable_constructs_are_problems(self) -> None:
        cases = {
            "FROM python:3.13-slim\n": "not digest-pinned",
            f"FROM a{PIN}\nCOPY $APP/ /app\n": "uses a variable",
            f"FROM a{PIN}\nCOPY --exclude=*.md . /app\n": "--exclude",
            f"FROM a{PIN}\nADD https://example.invalid/x.tgz /x\n": "without checksum",
            f"FROM a{PIN}\nCOPY --from=ghcr.io/x/y:1 /a /a\n": "not digest-pinned",
            f"FROM a{PIN}\nRUN --mount=type=secret,id=t true\n": "secret mount",
            "FROM ${BASE}\n": "build arg",
        }
        for text, needle in cases.items():
            with self.subTest(text=text):
                facts = FP.parse_dockerfile(text)
                self.assertTrue(any(needle in p for p in facts.problems), facts.problems)

    def test_bind_mount_json_form_and_heredoc(self) -> None:
        facts = FP.parse_dockerfile(
            f"FROM a{PIN} AS s\n"
            'COPY ["web/a b.txt", "/x"]\n'
            "RUN --mount=type=bind,source=tools,target=/t make\n"
            "RUN --mount=type=bind,from=s,source=/o,target=/o true\n"
            "RUN <<EOF\nCOPY smuggled /nope\nEOF\n"
            "ADD --checksum=sha256:00 https://example.invalid/x /x\n"
        )
        self.assertEqual(facts.problems, [])
        self.assertEqual(sorted(facts.sources), ["tools", "web/a b.txt"])


class FingerprintTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Repo()
        self.addCleanup(self.repo.tmp.cleanup)
        self.base = self.repo.commit(dict(BASE_FILES))
        self.git = FP.LocalGit(self.repo.path)

    def fp(self, rev: str) -> dict:
        return FP.compute(self.git, rev, ENTRY)

    def state(self, files: dict, mode: dict | None = None) -> str:
        head = self.repo.commit(files, mode)
        return FP.compare(self.fp(self.base), self.fp(head))

    def test_deterministic_and_reports_the_dead_ignore_file(self) -> None:
        a, b = self.fp(self.base), self.fp(self.base)
        self.assertEqual(a["fingerprint"], b["fingerprint"])
        self.assertEqual(a["ignore_file"], ".dockerignore")
        self.assertEqual(a["dead_ignore_files"], ["services/svc/.dockerignore"])
        paths = [p for p, _, _ in a["files"]]
        # The dead file's `scripts/` exclusion is NOT applied.
        self.assertIn("scripts/deploy.sh", paths)
        self.assertIn("app/README.md", paths)
        self.assertNotIn("app/__pycache__/x.pyc", paths)
        self.assertNotIn("docs/guide.md", paths)

    def test_changes_outside_the_input_set_are_unchanged(self) -> None:
        for files in (
            {"docs/guide.md": "changed\n"},
            {"tests/test_app.py": "changed\n"},
            {"README.md": "changed\n"},
            {"app/__pycache__/x.pyc": "changed\n"},
            {"brand-new/untouched.txt": "x\n"},
        ):
            with self.subTest(files=files):
                self.assertEqual(self.state(files), "unchanged")

    def test_changes_inside_the_input_set_are_changed(self) -> None:
        for files, mode in (
            ({"app/main.py": "print(2)\n"}, None),
            ({"app/new.py": "x\n"}, None),
            ({"scripts/deploy.sh": None}, None),
            ({"app/README.md": "embedded docs count\n"}, None),
            ({"uv.lock": "lock2\n"}, None),
            ({"services/svc/Dockerfile": DOCKERFILE + "# trailing\n"}, None),
            ({".dockerignore": "docs/\n"}, None),
            ({}, {"app/main.py": "755"}),
            ({"x/.gitattributes": "* -text\n"}, None),
        ):
            with self.subTest(files=files, mode=mode):
                self.base = self.repo.git("rev-parse", "HEAD")
                self.assertEqual(self.state(files, mode), "changed")

    def test_dockerfile_specific_ignore_file_wins(self) -> None:
        head = self.repo.commit({"services/svc/Dockerfile.dockerignore": "scripts/\n"})
        result = self.fp(head)
        self.assertEqual(result["ignore_file"], "services/svc/Dockerfile.dockerignore")
        self.assertNotIn("scripts/deploy.sh", [p for p, _, _ in result["files"]])
        # With it in effect, a scripts/ change no longer touches this image.
        after = self.repo.commit({"scripts/deploy.sh": "echo v2\n"})
        self.assertEqual(FP.compare(result, self.fp(after)), "unchanged")

    def test_unknown_never_reads_as_unchanged(self) -> None:
        bad = self.repo.commit({"services/svc/Dockerfile": "FROM python:3.13-slim\nCOPY . .\n"})
        result = self.fp(bad)
        self.assertIn("not digest-pinned", result["unknown"])
        self.assertEqual(FP.compare(result, result), "unknown")
        self.assertEqual(FP.verdict("unknown", "unchanged"), "would-build (unknown)")
        self.assertEqual(FP.verdict("unchanged", "unknown"), "would-build (unknown)")
        self.assertEqual(FP.verdict("unchanged", "unchanged"), "would-skip")
        filt = self.repo.commit({"services/svc/Dockerfile": DOCKERFILE, "lfs/.gitattributes": "*.bin filter=lfs\n"})
        self.assertIn("checkout filter", self.fp(filt)["unknown"])

    def test_empty_selection_hits_the_scan_floor(self) -> None:
        head = self.repo.commit({"services/svc/Dockerfile": f"FROM a{PIN}\nCOPY nothing-here /x\n"})
        self.assertIn("scan floor", self.fp(head)["unknown"])

    def test_github_api_tree_source_gives_the_same_fingerprint(self) -> None:
        git = self.git

        class FakeApi(FP.GitHubTree):
            def _get(self, path: str) -> dict:
                if path.startswith("git/trees/"):
                    rev = path.split("/")[2].split("?")[0]
                    return {"truncated": False, "tree": [
                        {"path": p, "mode": m, "type": t, "sha": o}
                        for p, (m, t, o) in git.entries(rev).items()
                    ]}
                if path.startswith("git/blobs/"):
                    oid = path.rsplit("/", 1)[1]
                    return {"encoding": "base64", "content": base64.b64encode(git.blob(oid)).decode()}
                raise AssertionError(path)

        api = FakeApi("onesyue/x", "token")
        self.assertEqual(FP.compute(api, self.base, ENTRY)["fingerprint"], self.fp(self.base)["fingerprint"])

        class Truncated(FakeApi):
            def _get(self, path: str) -> dict:
                body = super()._get(path)
                if path.startswith("git/trees/"):
                    body["truncated"] = True
                return body

        self.assertIn("truncated", FP.compute(Truncated("onesyue/x", "t"), self.base, ENTRY)["unknown"])

    def test_mutations_of_the_matcher_are_caught(self) -> None:
        """Deletion mutations: each must break one of the assertions above."""
        original_selected, original_ignored = FP.selected, FP.IgnoreRules.ignored
        try:
            FP.selected = lambda path, sources: True          # everything is input
            self.base = self.repo.git("rev-parse", "HEAD")
            self.assertEqual(self.state({"tests/test_app.py": "mut\n"}), "changed")
            FP.selected = original_selected
            FP.IgnoreRules.ignored = lambda self, path: False  # ignore file dropped
            self.base = self.repo.git("rev-parse", "HEAD")
            self.assertEqual(self.state({"docs/guide.md": "mut\n"}), "unchanged")  # outside COPY anyway
            self.base = self.repo.git("rev-parse", "HEAD")
            self.assertEqual(self.state({"app/__pycache__/x.pyc": "mut\n"}), "changed")
        finally:
            FP.selected, FP.IgnoreRules.ignored = original_selected, original_ignored


class RecipeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")
        self.services = json.loads((ROOT / "services.json").read_text(encoding="utf-8"))

    def test_recipe_tracks_the_build_job_only(self) -> None:
        entry = self.services[0]
        base = FP.recipe(entry, self.text)["fingerprint"]
        in_build = self.text.replace("provenance: mode=max", "provenance: mode=min", 1)
        self.assertNotEqual(FP.recipe(entry, in_build)["fingerprint"], base)
        in_plan = self.text.replace("timeout-minutes: 10", "timeout-minutes: 11", 1)
        self.assertEqual(FP.recipe(entry, in_plan)["fingerprint"], base)
        self.assertEqual(FP.recipe({**entry, "ref": "0" * 40}, self.text)["fingerprint"], base)
        self.assertNotEqual(FP.recipe({**entry, "platforms": "linux/arm64"}, self.text)["fingerprint"], base)
        self.assertIn("unknown", FP.recipe(entry, self.text.replace("\n  build:\n", "\n  built:\n")))

    def test_build_job_slice_is_stable_when_build_is_last_or_followed(self) -> None:
        entry = self.services[0]
        base = FP.recipe(entry, self.text)["fingerprint"]
        self.assertTrue(self.text.rstrip().endswith(FP.BUILD_JOB.search(self.text).group(0).rstrip()))
        followed = self.text.rstrip("\n") + "\n\n  later-job:\n    runs-on: x\n"
        self.assertEqual(FP.recipe(entry, followed)["fingerprint"], base)


class ShadowWiringTest(unittest.TestCase):
    """The shadow job must stay a side job no release step can depend on."""

    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")
        match = re.search(r"(?ms)^  input-shadow:\n(?P<body>.*?)(?=^  [a-z-]+:\n)", self.text)
        self.assertIsNotNone(match)
        self.job = match.group("body")

    def test_non_gating_read_only_and_bounded(self) -> None:
        self.assertIn("    continue-on-error: true\n", self.job)
        self.assertRegex(self.job, r"(?m)^    timeout-minutes: [1-9]$")
        perms = re.findall(r"(?m)^      ([a-z-]+): (read|write)$", self.job)
        self.assertEqual(perms, [("contents", "read"), ("packages", "read"),
                                 ("actions", "read"), ("attestations", "read")])
        for forbidden in ("imagetools create", "cosign", "build-push-action", "gh workflow run",
                          "GITHUB_OUTPUT", "outputs:"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.job)

    def test_nothing_depends_on_it(self) -> None:
        self.assertNotIn("needs.input-shadow", self.text)
        needs = re.findall(r"(?m)^    needs: (.+)$", self.text)
        self.assertTrue(needs)
        self.assertFalse(any("input-shadow" in n for n in needs))
        self.assertIn("    needs: [plan, validate]\n", self.text)

    def test_placed_before_build_and_never_named_like_a_service(self) -> None:
        self.assertLess(self.text.index("\n  input-shadow:\n"), self.text.index("\n  build:\n"))
        # ship.sh picks digests by `^<service>\t` job-name prefix in run logs.
        services = [e["service"] for e in json.loads((ROOT / "services.json").read_text())]
        self.assertFalse(any("input-shadow".startswith(s) for s in services))

    def test_evidence_probe_is_measurement_only(self) -> None:
        self.assertIn("scripts/verification-evidence.py probe", self.job)
        self.assertIn("if: needs.plan.outputs.promote == 'true'", self.job)
        self.assertNotIn("reuse_verification", self.text)
        self.assertNotIn("needs.validate.result == 'skipped'", self.text)
        source = (ROOT / "scripts" / "verification-evidence.py").read_text()
        self.assertIn('"enabled": False', source)
        self.assertNotIn('"enabled": True', source)


def _job(name: str, conclusion: str = "success", labels=None, group="GitHub Actions") -> dict:
    return {"name": name, "conclusion": conclusion, "labels": labels or ["ubuntu-latest"],
            "runner_group_name": group, "started_at": "2026-09-24T01:00:00Z",
            "completed_at": "2026-09-24T01:20:00Z", "id": 1}


PLAN_LOG = """2026-09-24T01:00:00.1Z ##[group]Runner Image
2026-09-24T01:00:00.2Z Image: ubuntu-24.04
2026-09-24T01:00:00.3Z Version: 20260907.300.1
2026-09-24T01:00:01.0Z env:
2026-09-24T01:00:01.1Z   SERVICE: yueops
2026-09-24T01:00:01.2Z   REF_OVERRIDE: {ref}
2026-09-24T01:00:01.3Z   EVENT_NAME: workflow_dispatch
2026-09-24T01:00:01.4Z   MANUAL_YUEBOARD_CONTRACT_REF:
"""


class EvidenceProbeTest(unittest.TestCase):
    NOW = dt.datetime(2026, 9, 24, 3, 0, tzinfo=dt.timezone.utc)
    REF = "b" * 40

    def current(self) -> dict:
        return {"repository": "onesyue/yueto-ci", "run_id": 99, "head_sha": "c" * 40,
                "default_branch": "master", "service": "yueops", "ref": self.REF,
                "validation_jobs": ["validate-yueops"], "image_version": "20260907.300.1"}

    def candidate(self, **run_over) -> dict:
        run = {"id": 7, "head_repository": {"full_name": "onesyue/yueto-ci"},
               "path": ".github/workflows/build.yml", "event": "workflow_dispatch",
               "head_branch": "master", "head_sha": "c" * 40, "status": "completed",
               "created_at": "2026-09-24T01:00:00Z"}
        run.update(run_over)
        return {"run": run, "jobs": [_job("plan"), _job("validate-yueops")],
                "plan_log": PLAN_LOG.format(ref=self.REF),
                "image_versions": {"validate-yueops": "20260907.300.1"}}

    def test_positive_case_is_reported_but_never_enabled(self) -> None:
        result = EV.assess(self.current(), [self.candidate()], self.NOW)
        self.assertTrue(result["identity_reusable"])
        self.assertEqual(result["evidence_run"], 7)
        self.assertEqual(result["validate_minutes"], 20.0)
        self.assertFalse(result["enabled"])
        self.assertTrue(any("pip-audit" in g for g in result["not_reproduced_by_identity"]))

    def test_every_identity_check_rejects_on_its_own(self) -> None:
        mutations = {
            "other repository": lambda c: c["run"].update(head_repository={"full_name": "evil/fork"}),
            "other workflow": lambda c: c["run"].update(path=".github/workflows/x.yml"),
            "other event": lambda c: c["run"].update(event="repository_dispatch"),
            "other branch": lambda c: c["run"].update(head_branch="feature"),
            "other ci commit": lambda c: c["run"].update(head_sha="d" * 40),
            "in progress": lambda c: c["run"].update(status="in_progress"),
            "too old": lambda c: c["run"].update(created_at="2026-09-22T01:00:00Z"),
            "this run": lambda c: c["run"].update(id=99),
            "plan failed": lambda c: c["jobs"].__setitem__(0, _job("plan", "failure")),
            "other service": lambda c: c.update(plan_log=c["plan_log"].replace("SERVICE: yueops", "SERVICE: yueboard")),
            "other ref": lambda c: c.update(plan_log=c["plan_log"].replace(self.REF, "e" * 40)),
            "duplicated ref line": lambda c: c.update(plan_log=c["plan_log"] + f"2026-09-24T01:00:02Z   REF_OVERRIDE: {self.REF}\n"),
            "contract override": lambda c: c.update(plan_log=c["plan_log"].replace("CONTRACT_REF:", "CONTRACT_REF: " + "f" * 40)),
            "validate failed": lambda c: c["jobs"].__setitem__(1, _job("validate-yueops", "failure")),
            "validate missing": lambda c: c["jobs"].pop(1),
            "self-hosted": lambda c: c["jobs"].__setitem__(1, _job("validate-yueops", labels=["self-hosted", "yue-local-release"])),
            "other runner image": lambda c: c["image_versions"].update({"validate-yueops": "20260914.1"}),
            "unreadable runner image": lambda c: c["image_versions"].clear(),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                cand = self.candidate()
                before = json.dumps(cand, sort_keys=True)
                mutate(cand)
                self.assertNotEqual(json.dumps(cand, sort_keys=True), before, "mutation was a no-op")
                result = EV.assess(self.current(), [cand], self.NOW)
                self.assertFalse(result["identity_reusable"], label)
                self.assertEqual(len(result["rejected"]), 1)

    def test_log_parsers(self) -> None:
        log = PLAN_LOG.format(ref=self.REF)
        self.assertEqual(EV.env_value(log, "MANUAL_YUEBOARD_CONTRACT_REF"), "")
        self.assertIsNone(EV.env_value(log, "ABSENT"))
        self.assertEqual(EV.image_version(log), "20260907.300.1")
        provisioner = log.replace("##[group]Runner Image\n", "##[group]Runner Image Provisioner\n")
        self.assertEqual(EV.image_version(provisioner), "")
        self.assertEqual(
            EV.validation_job_names([{"validation": "yue-node", "node_profile": "hy2"},
                                     {"validation": "yue-node", "node_profile": "vless"},
                                     {"validation": "yueops"}]),
            ["validate-yue-node-hy2", "validate-yue-node-vless", "validate-yueops"],
        )


if __name__ == "__main__":
    unittest.main()
