"""validate-yueops runs the yueops node unit suites (2026-10-17 W6.10).

The Mini App (158 cases), console (28) and site (12) `node --test` suites were
never executed by any CI. This pins the central step, its job gate and the
three entry points so a removed or renamed line turns red.
"""
from __future__ import annotations

from pathlib import Path

import re
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]


def _validate_steps() -> list[dict]:
    text = (ROOT / ".github" / "workflows" / "build.yml").read_text()
    job = text.split("\n  validate:\n", 1)[1].split("\n  build:\n", 1)[0]
    result = []
    for match in re.finditer(r"^      - name: (.+)\n((?:(?!^      - |^  [a-z]).*\n)*)", job, re.M):
        body = match.group(2)
        condition = re.search(r"^        if: (.+)$", body, re.M)
        script = re.search(r"^        run: \|\n((?:          .*\n|\n)*)", body, re.M)
        result.append({"name": match.group(1), "if": condition.group(1) if condition else "",
                       "run": textwrap.dedent(script.group(1)) if script else ""})
    assert len(result) >= 20, "validation step scan did not reach its target"
    return result


class YueOpsNodeTestPolicy(unittest.TestCase):
    def test_validate_yueops_runs_all_three_node_suites(self):
        steps = _validate_steps()
        names = [s.get("name", "") for s in steps]
        step = next(s for s in steps if s.get("name") == "Run yueops node unit tests (Mini App, console, site)")
        assert step["if"] == "matrix.validation == 'yueops'"
        run = step["run"]
        for line in ("set -euo pipefail",
                     "npm --prefix telegram-bot/yue/miniapp test",
                     "npm --prefix frontend test",
                     "pnpm --dir site install --frozen-lockfile --ignore-scripts",
                     "pnpm --dir site test"):
            assert line in run, line
        # Dependencies must be installed before the suites run.
        index = names.index(step["name"])
        assert names.index("Validate yueops frontend") < index
        assert names.index("Validate Yue mini app") < index


    def test_validate_job_keeps_the_utc_lens(self):
        workflow = (ROOT / ".github" / "workflows" / "build.yml").read_text()
        job = workflow.split("\n  validate:\n", 1)[1].split("    strategy:", 1)[0]
        assert "    env:\n      TZ: UTC\n" in job


    def test_real_central_step_installs_browser_and_stops_when_installation_fails(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        tmp_path = Path(directory.name)
        import os
        import subprocess
        step = next(s for s in _validate_steps() if s.get("name") == "Run yueops node unit tests (Mini App, console, site)")
        bindir = tmp_path / "bin"
        bindir.mkdir()
        log = tmp_path / "calls"
        for name in ("npm", "pnpm", "corepack", "node", "id", "sudo"):
            path = bindir / name
            path.write_text("#!/bin/sh\n"
                            'printf "%s %s\\n" "${0##*/}" "$*" >> "$CALL_LOG"\n'
                            'case "${0##*/}" in node) echo pnpm@11.27.1;; id) echo 1001;; sudo) exit 1;; esac\n'
                            'case "$*" in *"playwright install"*) exit "${INSTALL_EXIT:-0}";; esac\n')
            path.chmod(0o755)
        env = {**os.environ, "PATH": str(bindir) + ":" + os.environ["PATH"], "CALL_LOG": str(log)}
        for failure in (False, True):
            log.write_text("")
            result = subprocess.run(["bash", "-c", step["run"]], cwd=tmp_path, env={**env, "INSTALL_EXIT": "17" if failure else "0"}, capture_output=True, text=True)
            calls = log.read_text().splitlines()
            install = "pnpm --dir site exec playwright install chromium"
            assert install in calls, calls
            assert calls.index("pnpm --dir site install --frozen-lockfile --ignore-scripts") < calls.index(install)
            if failure:
                assert result.returncode == 17
                assert "pnpm --dir site test" not in calls
            else:
                assert result.returncode == 0, result.stderr
                assert calls.index(install) < calls.index("pnpm --dir site test")
