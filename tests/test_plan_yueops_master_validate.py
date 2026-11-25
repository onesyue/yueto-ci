from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def load():
    path = SCRIPTS / "plan-yueops-master-validate.py"
    spec = importlib.util.spec_from_file_location("plan_yueops_master_validate", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def version(updated: str, *tags: str) -> dict:
    return {
        "updated_at": updated,
        "metadata": {"container": {"tags": list(tags)}},
    }


def test_newest_promoted_revision_picks_the_latest_marker():
    planner = load()
    old = "promoted-" + ("a" * 40) + "-" + ("1" * 64)
    new = "promoted-" + ("b" * 40) + "-" + ("2" * 64)
    latest = planner.newest_promoted_revision(
        [
            version("2026-11-01T00:00:00Z", "latest", old),
            version("2026-11-26T00:00:00Z", new),
        ]
    )
    assert latest == "b" * 40


def test_malformed_promotion_marker_fails_closed():
    planner = load()
    with pytest.raises(planner.PlanError, match="malformed promotion marker"):
        planner.newest_promoted_revision([version("2026-11-26T00:00:00Z", "promoted-not-a-sha")])


def test_missing_promoted_marker_fails_closed():
    planner = load()
    with pytest.raises(planner.PlanError, match="no promoted"):
        planner.newest_promoted_revision([version("2026-11-26T00:00:00Z", "latest")])


def test_plan_wires_source_baseline_and_board(monkeypatch):
    planner = load()
    monkeypatch.setattr(planner, "resolve_source_sha", lambda token, ref="master": "c" * 40)
    monkeypatch.setattr(planner, "resolve_board_revision", lambda: "d" * 40)
    payload = planner.plan(
        token="t",
        ref="master",
        versions_for=lambda _name: [
            version("2026-11-26T00:00:00Z", "promoted-" + ("e" * 40) + "-" + ("3" * 64)),
        ],
    )
    assert payload == {
        "source": "c" * 40,
        "migration_base": "e" * 40,
        "board_revision": "d" * 40,
    }


def test_plan_without_token_fails_closed():
    planner = load()
    with pytest.raises(planner.PlanError, match="GH_API_TOKEN"):
        planner.plan(token="", ref="master", versions_for=lambda _name: [])


def test_find_dispatched_workflow_run_returns_the_new_match():
    path = SCRIPTS / "find-dispatched-workflow-run.py"
    spec = importlib.util.spec_from_file_location("find_dispatched_workflow_run", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    title = "Build & publish images yueops " + ("c" * 40) + " [nonce:abcd]"
    before = [{"databaseId": 1, "displayTitle": title}]
    after = before + [{"databaseId": 2, "displayTitle": title}]
    assert module.find_run(title, before, after) == 2
    assert module.find_run(title, before, before) is None


def test_select_existing_prefers_a_successful_run_for_the_same_sha():
    path = SCRIPTS / "select-existing-yueops-validate-run.py"
    spec = importlib.util.spec_from_file_location("select_existing_yueops_validate_run", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    source = "c" * 40
    other = "d" * 40
    runs = [
        {"databaseId": 1, "displayTitle": f"Build & publish images yueops {source} [nonce:{'a'*32}]", "status": "completed", "conclusion": "failure"},
        {"databaseId": 2, "displayTitle": f"Build & publish images yueops {other} [nonce:{'b'*32}]", "status": "completed", "conclusion": "success"},
        {"databaseId": 3, "displayTitle": f"Build & publish images yueops {source} [nonce:{'c'*32}]", "status": "completed", "conclusion": "success"},
        {"databaseId": 4, "displayTitle": f"Build & publish images yueops {source} [nonce:{'d'*32}]", "status": "in_progress", "conclusion": ""},
    ]
    assert module.select(source, runs) == ("success", 3)
    assert module.select(source, runs[:2] + runs[3:]) == ("pending", 4)
    assert module.select(source, runs[:1]) == ("none", None)
