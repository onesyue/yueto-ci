"""validate-yueops runs the yueops node unit suites (2026-10-17 W6.10).

The Mini App (158 cases), console (28) and site (12) `node --test` suites were
never executed by any CI. This pins the central step, its job gate and the
three entry points so a removed or renamed line turns red.
"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _validate_steps() -> list[dict]:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "build.yml").read_text())
    return workflow["jobs"]["validate"]["steps"]


def test_validate_yueops_runs_all_three_node_suites():
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


def test_validate_job_keeps_the_utc_lens():
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "build.yml").read_text())
    assert workflow["jobs"]["validate"]["env"]["TZ"] == "UTC"
