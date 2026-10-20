"""The actual YAML consumer preserves pytest results and diagnoses partial timing."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/build.yml").read_text()


def step(name):
    match = re.search(
        rf"^      - name: {re.escape(name)}\n(?P<body>(?:(?!^      - |^  [a-z]).*\n)*)",
        WORKFLOW, re.M,
    )
    assert match, name
    body = match.group("body")
    script = re.search(r"^        run: \|\n((?:          .*\n|\n)*)", body, re.M)
    return body, textwrap.dedent(script.group(1)) if script else ""


class PytestTimingConsumer(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.source = self.base / "source"
        self.policy = self.source / ".ci-policy"
        self.site = self.base / "site"
        self.output = self.base / "runner/yueops-pytest-timing"
        self.output.parent.mkdir()
        (self.source / "scripts").mkdir(parents=True)
        (self.source / "tests").mkdir()
        (self.source / ".venv/bin").mkdir(parents=True)
        (self.source / ".venv/bin/python").symlink_to(sys.executable)
        (self.policy / "scripts").mkdir(parents=True)
        for name in ("lens_report.py", "lens-report-source.json", "pytest-timing.py"):
            shutil.copyfile(ROOT / "scripts" / name, self.policy / "scripts" / name)
        (self.source / "scripts/run-pytest-parallel.sh").write_text(
            '#!/bin/sh\n[ "$YUEOPS_PYTEST_SERIAL" = 1 ] || exit 81\n'
            'exec "$TIMING_TEST_PYTHON" -m pytest -q -p no:cacheprovider tests\n')
        (self.source / "scripts/security_scan.sh").write_text('echo \'{"fail":0}\'\n')
        for name in ("check-python-dependency-groups.py", "audit-route-consistency.py"):
            (self.source / "scripts" / name).write_text("")
        for directory in ("web", "checkin-api", "telegram-bot/yue"):
            (self.source / directory).mkdir(parents=True)
        bindir = self.base / "bin"
        bindir.mkdir()
        for name in ("uv", "jq", "sudo"):
            path = bindir / name
            path.write_text(
                "#!/bin/sh\n"
                + ('printf native >> "$NATIVE_CALLED"\n' if name == "sudo" else "")
                + "exit 0\n"
            )
            path.chmod(0o755)
        (bindir / "python3").symlink_to(sys.executable)
        self.env = dict(
            os.environ, PATH=str(bindir) + os.pathsep + os.environ["PATH"],
            PYTHONPATH=str(self.site), RUNNER_TEMP=str(self.output.parent),
            TIMING_TEST_PYTHON=sys.executable, NATIVE_CALLED=str(self.base / "native"),
            PYTEST_ADDOPTS="--durations=25", PYTHONDONTWRITEBYTECODE="1", TZ="UTC",
            GITHUB_RUN_ID="12345", GITHUB_RUN_ATTEMPT="2", GITHUB_JOB="validate",
            GITHUB_REPOSITORY="onesyue/yueto-ci",
        )
        for key in ("LENS_REPORT", "LENS_REPORT_OWNER", "LENS_INVOCATION_ID", "GITHUB_SHA"):
            self.env.pop(key, None)
        self.git(self.policy, "init", "-q")
        self.git(self.policy, "add", "scripts")
        self.git(self.policy, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "-qm", "fixture policy")
        self.env["GITHUB_SHA"] = self.git(self.policy, "rev-parse", "HEAD").stdout.strip()
        self.git(self.source, "init", "-q")
        self.git(self.source, "add", "scripts")
        self.git(self.source, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "-qm", "fixture source")

    def git(self, cwd, *args):
        return subprocess.run(["git", *args], cwd=cwd, check=True, text=True,
                              capture_output=True, env=self.env)

    def command(self, args, **kwargs):
        return subprocess.run(args, cwd=self.source, env=self.env,
                              capture_output=True, text=True, timeout=40, **kwargs)

    def install(self):
        # Actual preparation script, overriding only its fixture installation
        # directory: never mutate the test runner's real site-packages.
        _, script = step("Prepare passive yueops pytest timing")
        script = script.rstrip() + f' --site "{self.site}"\n'
        result = self.command(["bash", "-c", script])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def run_consumer(self, content, mutation=None):
        (self.source / "tests/test_cases.py").write_text(textwrap.dedent(content))
        self.install()
        _, script = step("Validate yueops backend")
        if mutation:
            script = mutation(script)
        run = self.command(["bash", "-c", script])
        _, summary = step("Summarize passive yueops pytest timing")
        summarized = self.command(["bash", "-c", summary])
        self.assertEqual(summarized.returncode, 0, summarized.stdout + summarized.stderr)
        return run, json.loads((self.output / "summary.json").read_text())

    def test_real_yaml_records_pass_skip_xfail_subtests_and_excludes_nested_pytest(self):
        run, summary = self.run_consumer("""
            import os, subprocess, sys, pytest
            def test_ok():
                pass
            @pytest.mark.skip(reason="fixture skip")
            def test_skip():
                pass
            @pytest.mark.xfail(reason="fixture xfail")
            def test_xfail():
                assert False
            def test_subtests(subtests):
                for value in (1, 2):
                    with subtests.test(value=value):
                        assert value > 0
            def test_nested(tmp_path):
                (tmp_path / "test_child.py").write_text("def test_child():\\n    pass\\n")
                child = subprocess.run([sys.executable, "-m", "pytest", "-q", str(tmp_path)])
                assert child.returncode == 0
        """)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(summary["evidence_status"], "COMPLETE", summary)
        self.assertFalse(summary["release_acceptance"])
        self.assertTrue((self.base / "native").exists())
        session = summary["sessions"][0]
        self.assertEqual(session["reported_cases"], 5)
        self.assertEqual(session["subtest_reports_excluded_from_totals"], 2)
        self.assertEqual(set(session["phase_seconds"]), {"setup", "call", "teardown"})
        metadata = summary["metadata"]
        self.assertEqual(metadata["identity"]["GITHUB_RUN_ATTEMPT"], "2")
        self.assertEqual(metadata["source_revision"], self.git(self.source, "rev-parse", "HEAD").stdout.strip())
        self.assertEqual(metadata["policy_revision"], self.env["GITHUB_SHA"])
        self.assertEqual(summary["resources"]["status"], "UNKNOWN")
        rows = [json.loads(line) for line in (self.output / "events.jsonl").read_text().splitlines()]
        self.assertEqual(sum(r.get("event") == "start" for r in rows), 1)
        self.assertFalse(any("test_child" in r.get("nodeid", "") for r in rows))

    def test_setup_call_and_teardown_failure_keep_original_exit_and_complete_failed_evidence(self):
        run, summary = self.run_consumer("""
            import pytest
            @pytest.fixture
            def setup_fail():
                pytest.fail("setup")
            def test_setup(setup_fail):
                pass
            def test_call():
                pytest.fail("call")
            @pytest.fixture
            def teardown_fail():
                yield
                pytest.fail("teardown")
            def test_teardown(teardown_fail):
                pass
        """)
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        self.assertEqual(summary["pytest_process_exit_code"], 1)
        self.assertEqual(summary["evidence_status"], "COMPLETE", summary)
        self.assertFalse(summary["release_acceptance"])
        self.assertFalse((self.base / "native").exists())

    def test_abrupt_process_exit_is_partial_and_keeps_nonzero_exit(self):
        run, summary = self.run_consumer("def test_abort():\n    import os; os._exit(7)\n")
        self.assertEqual(run.returncode, 7, run.stdout + run.stderr)
        self.assertEqual(summary["evidence_status"], "PARTIAL", summary)
        self.assertIn("session has no terminal finish record", summary["problems"])
        self.assertFalse((self.base / "native").exists())

    def test_collection_error_cannot_be_complete_evidence(self):
        run, summary = self.run_consumer("raise RuntimeError('collection failed')\n")
        self.assertEqual(run.returncode, 2, run.stdout + run.stderr)
        self.assertEqual(summary["evidence_status"], "PARTIAL", summary)
        self.assertFalse((self.base / "native").exists())

    def test_removed_actual_recorder_binding_is_detected(self):
        run, summary = self.run_consumer(
            "def test_ok():\n    pass\n",
            lambda script: script.replace('LENS_REPORT="$timing_dir/events.jsonl"', "LENS_REPORT="),
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(summary["evidence_status"], "MISSING", summary)

    def test_missing_exit_receipt_and_changed_corpus_never_appear_complete(self):
        run, _ = self.run_consumer("def test_ok():\n    pass\n")
        self.assertEqual(run.returncode, 0)
        (self.output / "pytest-exit-code.txt").unlink()
        rows = [json.loads(line) for line in (self.output / "events.jsonl").read_text().splitlines()]
        corpus = next(r for r in rows if r.get("event") == "collection_corpus")
        corpus["count"] += 1
        (self.output / "events.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        _, script = step("Summarize passive yueops pytest timing")
        self.command(["bash", "-c", script])
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertEqual(summary["evidence_status"], "PARTIAL")
        self.assertIn("pytest process exit receipt missing or invalid", summary["problems"])
        self.assertIn("collected corpus digest/count mismatch", summary["problems"])

    def test_tampered_projection_is_refused_before_installation(self):
        with (self.policy / "scripts/lens_report.py").open("a") as stream:
            stream.write("\n# drift\n")
        result = self.command([
            sys.executable, str(self.policy / "scripts/pytest-timing.py"), "install",
            "--output", str(self.output), "--site", str(self.site),
        ])
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.site / "yueto_lens_report.py").exists())

    def test_yaml_binding_is_ops_only_ordered_always_retained_and_immutable(self):
        names = ["Prepare passive yueops pytest timing", "Validate yueops backend",
                 "Summarize passive yueops pytest timing", "Upload passive yueops pytest timing"]
        self.assertEqual([WORKFLOW.index("- name: " + n) for n in names],
                         sorted(WORKFLOW.index("- name: " + n) for n in names))
        for name in names:
            body, _ = step(name)
            self.assertIn("matrix.validation == 'yueops'", body)
            if name.startswith(("Summarize", "Upload")):
                self.assertIn("if: always()", body)
        upload, _ = step(names[-1])
        self.assertIn("actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a", upload)
        self.assertIn("${{ github.run_id }}-${{ github.run_attempt }}", upload)
        self.assertIn("path: ${{ runner.temp }}/yueops-pytest-timing/", upload)
        backend, script = step(names[1])
        self.assertIn("PYTEST_ADDOPTS: --durations=25", backend)
        self.assertEqual(script.count("bash scripts/run-pytest-parallel.sh"), 1)
        self.assertIn("YUEOPS_PYTEST_SERIAL=1", script)
        self.assertIn('if [ "$pytest_rc" -ne 0 ]; then exit "$pytest_rc"; fi', script)
        policy = (ROOT / ".github/workflows/policy-ci.yml").read_text()
        install = "python3 -m pip install --require-hashes --only-binary=:all: -r requirements-policy.txt"
        self.assertIn(install, policy)
        self.assertLess(policy.index(install), policy.index("python3 -m unittest discover"))
        requirements = (ROOT / "requirements-policy.txt").read_text()
        self.assertEqual(len(re.findall(r"^[a-z]+==.*--hash=sha256:[0-9a-f]{64}$",
                                        requirements, re.M)), 5)


if __name__ == "__main__":
    unittest.main()
