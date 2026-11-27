#!/usr/bin/env python3
"""Bind reusable validation to an exact source, policy, workflow, hosted image and input plan."""

from __future__ import annotations

import copy
import hashlib
import datetime as dt
import json
import os
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_CI_LIB = str(Path(__file__).resolve().parent / "lib")
if _CI_LIB not in sys.path:
    sys.path.insert(0, _CI_LIB)
from ci_constants import GITHUB_API_ORIGIN, GITHUB_HTTP_TIMEOUT_SECONDS, LOG_HEADER_BYTE_LIMIT, VALIDATION_IMAGE_WORKERS

WORKFLOW_PATH = ".github/workflows/build.yml"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
ENV_LINE = r"^\d{{4}}-\d{{2}}-\d{{2}}T[0-9:.]+Z +{key}:(?: (?P<value>[^\r\n]*))?[ \t]*\r?$"
IMAGE_VERSION = re.compile(
    r"##\[group\]Runner Image\s*\n(?:.*\n){0,3}?\S+Z Version: (?P<version>[0-9.]+)"
)

# Residual inputs to validate itself. Freshness is independently required.
NOT_REPRODUCED_BY_IDENTITY = (
    "wall-clock dates, expiry and timezone windows in product tests",
    "PyPI, npm/pnpm and Go module downloads on a cold cache, including locked dependencies",
    "Node 24 and host Python 3.13 patch selection, browser downloads and apt package indexes",
)


def env_value(log: str, key: str) -> str | None:
    """The single runner-printed value of ``key``; None if absent or duplicated."""
    clean = ANSI.sub("", log)
    hits = re.findall(ENV_LINE.format(key=re.escape(key)), clean, re.M)
    return hits[0] if len(hits) == 1 else None


def image_version(log_head: str) -> str:
    m = IMAGE_VERSION.search(ANSI.sub("", log_head))
    return m.group("version") if m else ""


def _ts(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def inputs_digest(admission, selection, service, migration_base):
    # Run/attempt seal the original join. They do not change the test inputs.
    value = copy.deepcopy(admission)
    del value["admission_sha256"]
    contexts = [value["identity"]]
    if value["ops_plan"] is not None:
        contexts.append(value["ops_plan"]["context"])
        del value["ops_plan"]["plan_sha256"]
    for context in contexts:
        del context["run_id"], context["run_attempt"]
    # Timing weights only choose assignments. The actual assignments are bound.
    value.pop("ordinary_weights", None)
    data = json.dumps([value, selection, service, migration_base],
                      sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def eligible_run(current, run, now):
    return (run["id"] != current["run_id"]
            and (run.get("head_repository") or {}).get("full_name") == current["repository"]
            and run.get("path") == WORKFLOW_PATH and run.get("event") == "workflow_dispatch"
            and run.get("head_branch") == current["default_branch"]
            and run.get("head_sha") == current["head_sha"]
            and run.get("status") == "completed" and run.get("conclusion") == "success"
            and dt.timedelta() <= now - _ts(run["created_at"]) <= dt.timedelta(hours=24))


def hosted_success(job):
    return (job.get("status") == "completed" and job.get("conclusion") == "success"
            and job.get("labels") == ["ubuntu-24.04"]
            and job.get("runner_group_name") == "GitHub Actions")


def matching_candidate(current, run, api):
    attempt = run["run_attempt"]
    jobs = api.get(f"actions/runs/{run['id']}/attempts/{attempt}/jobs?per_page=100")
    rows = jobs["jobs"]
    if jobs["total_count"] != len(rows):
        return False
    names = ["plan", "validation-evidence", *current["validation_jobs"]]
    required = [job for job in rows if job["name"] in names]
    if (not current["validation_jobs"] or sorted(job["name"] for job in required) != sorted(set(names))
            or len(names) != len(set(names))
            or not all(hosted_success(job) and job.get("run_attempt") == attempt for job in required)):
        return False
    plan = next(job for job in required if job["name"] == "plan")
    log = api.get(f"actions/jobs/{plan['id']}/logs", raw=True)
    if (env_value(log, "SERVICE") != current["service"]
            or env_value(log, "REF_OVERRIDE") != current["ref"]
            or env_value(log, "EVENT_NAME") != "workflow_dispatch"
            or env_value(log, "VALIDATION_IDENTITY") != current["binding"]):
        return False

    def same_image(job):
        header = api.get(f"actions/jobs/{job['id']}/logs", raw=True, limit=LOG_HEADER_BYTE_LIMIT)
        return image_version(header) == current["image_version"]

    with ThreadPoolExecutor(max_workers=VALIDATION_IMAGE_WORKERS) as pool:
        return all(pool.map(same_image, required))


def reusable_run(current, api, now):
    if (not current["enabled"] or not SHA40.fullmatch(current["ref"])
            or not SHA40.fullmatch(current["head_sha"]) or not current["image_version"]
            or not re.fullmatch(r"[0-9a-f]{64}:[0-9a-f]{64}", current["binding"])):
        return None
    runs = api.get(f"actions/workflows/build.yml/runs?head_sha={current['head_sha']}"
                   "&event=workflow_dispatch&status=success&per_page=30")["workflow_runs"]
    for run in runs:
        if eligible_run(current, run, now) and matching_candidate(current, run, api):
            return run
    return None


def validation_job_names(matrix: list[dict]) -> list[str]:
    """Mirror the validate job's `name:` expression in build.yml."""
    return sorted(
        (f"validate-yueboard-{m['board_role']}" if m.get("board_role")
         else f"validate-yueops-{m['ops_role']}"
         if m.get("ops_role") and m["ops_role"] != "legacy"
         else f"validate-yue-node-{m['node_profile']}" if m.get("node_profile")
         else f"validate-{m['validation']}")
        for m in matrix
    )


class Api:
    def __init__(self, repository: str, token: str):
        self.base = f"{GITHUB_API_ORIGIN}/repos/{repository}"
        self.token = token

    def get(self, path: str, raw: bool = False, limit: int | None = None):
        req = urllib.request.Request(self.base + "/" + path, headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        # Actions log downloads redirect to signed storage URLs.
        req.add_unredirected_header("Authorization", f"Bearer {self.token}")
        with urllib.request.urlopen(req, timeout=GITHUB_HTTP_TIMEOUT_SECONDS) as response:
            data = response.read(limit) if limit else response.read()
        return data.decode("utf-8", "replace") if raw else json.loads(data)


def main():
    env = os.environ
    admission = json.loads((Path(env["RUNNER_TEMP"]) / "ops-admission.json").read_bytes())
    selection = json.loads(env["EVIDENCE_SELECTION"])
    if sys.argv[1] == "identity":
        inputs = inputs_digest(admission, selection, env["EVIDENCE_SERVICE"], env["EVIDENCE_BASE"])
        workflow = hashlib.sha256(Path(WORKFLOW_PATH).read_bytes()).hexdigest()
        print(f"binding={workflow}:{inputs}")
        return
    if sys.argv[1] != "decide":
        raise ValueError("unknown command")
    matrix = admission["validation_matrix"]
    group = {row["validation"] for row in matrix}
    flags = {"yue-node": "REUSE_YUE_NODE", "yueops": "REUSE_YUEOPS"}
    # Default ON (owner t1520u/t1525u, 2026-11-27): a ship must not re-run the
    # 40-job validation its exact SHA already passed as a premerge. The binding
    # (source SHA, yueto-ci commit, workflow SHA-256, runner image, effective
    # inputs, 24h, hosted) is unchanged and freshness still runs every time.
    # The repository variable is now only a kill switch: "false" turns it off.
    flag = flags.get(next(iter(group)), "") if len(group) == 1 else ""
    enabled = bool(flag) and env.get(flag, "").strip().lower() != "false"
    builds = json.loads(env["EVIDENCE_BUILDS"])
    planned_ops = {row["service"] for row in builds if row["validation"] == "yueops"}
    covered = (bool(builds) and all(row["validation"] in group and row["ref"] == env["EVIDENCE_REF"]
                                    for row in builds)
               and planned_ops == {row["service"] for row in selection})
    current = {
        "repository": env["GITHUB_REPOSITORY"], "run_id": int(env["GITHUB_RUN_ID"]),
        "head_sha": env["GITHUB_SHA"], "default_branch": env["DEFAULT_BRANCH"],
        "service": env["EVIDENCE_SERVICE"], "ref": env["EVIDENCE_REF"],
        "binding": env["VALIDATION_IDENTITY"], "image_version": env.get("ImageVersion", ""),
        "validation_jobs": validation_job_names(matrix) + ["select-" + row["service"] for row in selection],
        "enabled": enabled and covered and env["EVIDENCE_PROMOTE"] == "true"
                   and env["GITHUB_REF"] == "refs/heads/" + env["DEFAULT_BRANCH"]
                   and all(row["ref"] == env["EVIDENCE_REF"] for row in matrix),
    }
    try:
        run = reusable_run(current, Api(current["repository"], env["GH_TOKEN"]), dt.datetime.now(dt.timezone.utc))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        # Log only the error class: storage redirects may include signed URLs.
        print(f"Evidence lookup unavailable ({type(exc).__name__}). Full validation required.")
        return
    if run:
        message = f"REPRODUCED_BY_IDENTITY from run {run['id']} attempt {run['run_attempt']}"
        print(message)
        with open(env["GITHUB_STEP_SUMMARY"], "a") as out:
            print(message, file=out)
            for residual in NOT_REPRODUCED_BY_IDENTITY:
                print(f"- Original run observed {residual}", file=out)
        with open(env["GITHUB_OUTPUT"], "a") as out:
            print(f"attempt={int(run['run_attempt'])}\nrun={int(run['id'])}", file=out)
    else:
        print("Full validation required")


if __name__ == "__main__":
    main()
