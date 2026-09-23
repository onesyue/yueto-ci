#!/usr/bin/env python3
"""Would an earlier run's verification evidence be reusable?  MEASUREMENT ONLY.

P3 (2026-09-24) asked for "reuse a prior successful verification of the same
source SHA instead of re-running identical validate jobs", behind a default-off
flag, *only if the trust argument is airtight*.  The identity half can be made
airtight within GitHub Actions' guarantees and is encoded below.  The freshness
half cannot (see ``NOT_REPRODUCED_BY_IDENTITY``): the validate jobs contain
gates whose verdict depends on the time they run, not on their inputs.  So this
file never skips anything.  It reports, for a promote run, whether evidence
that passes every identity check exists and how many validate minutes reusing
it would have saved -- the number that decides whether splitting those gates
out (the precondition for real reuse) is worth doing.

Identity checks (every one must hold; the first failure is the reason):

1. same repository, workflow path ``.github/workflows/build.yml``, event
   ``workflow_dispatch``, default branch, and **the same yueto-ci commit**
   (``head_sha``).  One commit pins the workflow blob *and* every planner /
   contract input it reads (services.json, validation-targets.json,
   native-node-contract.json, scripts/*), so "same workflow file blob and same
   planner/contract inputs" reduces to commit equality -- no weaker
   per-file comparison is attempted;
2. completed, not this run, created within ``--max-age-hours``;
3. exactly one ``plan`` job, successful, whose runner-printed env block names
   the same ``SERVICE``, the same exact 40-hex ``REF_OVERRIDE``, event
   ``workflow_dispatch`` and an empty ``MANUAL_YUEBOARD_CONTRACT_REF`` (a manual
   contract override validates against a different YueBoard tree).  The env
   block is written by the runner before any user code runs; a duplicated key
   line is rejected, the same binding ``scripts/match-build-run.py`` uses;
4. every validate job the current plan needs is present, ``success``, on the
   GitHub-hosted ``ubuntu-latest`` label in the ``GitHub Actions`` runner group
   (never the manual self-hosted fallback);
5. each of those jobs ran on the **same runner image version** as this run
   (``Runner Image / Version:`` from the job log header, vs ``$ImageVersion``).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.request

WORKFLOW_PATH = ".github/workflows/build.yml"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
ENV_LINE = r"^\d{{4}}-\d{{2}}-\d{{2}}T[0-9:.]+Z +{key}:(?: (?P<value>.*?))?\s*$"
IMAGE_VERSION = re.compile(
    r"##\[group\]Runner Image\s*\n(?:.*\n){0,3}?\S+Z Version: (?P<version>[0-9.]+)"
)

# Gates inside the validate jobs whose verdict can change with wall-clock time
# for identical inputs.  Reusing evidence would silently skip re-asking them
# at promote time; this is why reuse is not enabled (module docstring).
NOT_REPRODUCED_BY_IDENTITY = (
    "yueops: pip-audit against the live PyPI advisory database",
    "yueops: npm-audit-gate.py (frontend + mini app) against the live npm advisory database",
    "yueboard: pnpm-audit-gate.mjs against the live npm advisory database",
    "time-dependent tests (date/expiry/timezone windows) judged at run time",
    "anything installed from mutable package indexes during validation",
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


def assess_candidate(current: dict, cand: dict, now: dt.datetime, max_age: dt.timedelta) -> str:
    """Return "" when the candidate passes every identity check, else the reason."""
    run = cand["run"]
    if run.get("id") == current["run_id"]:
        return "this run"
    if (run.get("head_repository") or {}).get("full_name") != current["repository"]:
        return "different repository"
    if run.get("path") != WORKFLOW_PATH:
        return "different workflow path"
    if run.get("event") != "workflow_dispatch":
        return f"event {run.get('event')}"
    if run.get("head_branch") != current["default_branch"]:
        return f"branch {run.get('head_branch')}"
    if run.get("head_sha") != current["head_sha"]:
        return "different yueto-ci commit (workflow/planner/contract inputs may differ)"
    if run.get("status") != "completed":
        return "not completed"
    created = _ts(run["created_at"])
    if not (dt.timedelta(0) <= now - created <= max_age):
        return "outside freshness window"
    plans = [j for j in cand["jobs"] if j.get("name") == "plan"]
    if len(plans) != 1 or plans[0].get("conclusion") != "success":
        return "plan job missing or unsuccessful"
    log = cand.get("plan_log", "")
    if env_value(log, "SERVICE") != current["service"]:
        return "different service"
    ref = env_value(log, "REF_OVERRIDE")
    if not ref or not SHA40.match(ref) or ref != current["ref"]:
        return "different or non-exact source ref"
    if env_value(log, "EVENT_NAME") != "workflow_dispatch":
        return "plan env event mismatch"
    if env_value(log, "MANUAL_YUEBOARD_CONTRACT_REF") != "":
        return "manual YueBoard contract override (or unreadable)"
    by_name = {j.get("name"): j for j in cand["jobs"]}
    for name in current["validation_jobs"]:
        job = by_name.get(name)
        if job is None:
            return f"{name} missing"
        if job.get("conclusion") != "success":
            return f"{name} {job.get('conclusion')}"
        if job.get("labels") != ["ubuntu-latest"] or job.get("runner_group_name") != "GitHub Actions":
            return f"{name} not on the hosted ubuntu-latest class"
        seen = cand.get("image_versions", {}).get(name, "")
        if not seen or seen != current["image_version"]:
            return f"{name} runner image {seen or 'unreadable'} != {current['image_version'] or 'unknown'}"
    return ""


def assess(current: dict, candidates: list[dict], now: dt.datetime, max_age_hours: float = 24) -> dict:
    max_age = dt.timedelta(hours=max_age_hours)
    rejected = {}
    for cand in sorted(candidates, key=lambda c: c["run"].get("created_at", ""), reverse=True):
        reason = assess_candidate(current, cand, now, max_age)
        if not reason:
            minutes = sum(
                (_ts(j["completed_at"]) - _ts(j["started_at"])).total_seconds() / 60
                for j in cand["jobs"] if j.get("name") in current["validation_jobs"]
            )
            return {
                "identity_reusable": True, "evidence_run": cand["run"]["id"],
                "validate_minutes": round(minutes, 1), "rejected": rejected,
                "enabled": False, "not_reproduced_by_identity": list(NOT_REPRODUCED_BY_IDENTITY),
            }
        rejected[str(cand["run"].get("id"))] = reason
    return {"identity_reusable": False, "rejected": rejected, "enabled": False,
            "not_reproduced_by_identity": list(NOT_REPRODUCED_BY_IDENTITY)}


def validation_job_names(matrix: list[dict]) -> list[str]:
    """Mirror the validate job's `name:` expression in build.yml."""
    return sorted(
        f"validate-yue-node-{m['node_profile']}" if m.get("node_profile") else f"validate-{m['validation']}"
        for m in matrix
    )


class Api:
    def __init__(self, repository: str, token: str):
        self.base = f"https://api.github.com/repos/{repository}"
        self.token = token

    def get(self, path: str, raw: bool = False, limit: int | None = None):
        req = urllib.request.Request(self.base + "/" + path, headers={
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        with urllib.request.urlopen(req, timeout=30) as response:
            data = response.read(limit) if limit else response.read()
        return data.decode("utf-8", "replace") if raw else json.loads(data)


def probe(args: argparse.Namespace) -> int:
    env = os.environ
    repository = env["GITHUB_REPOSITORY"]
    current = {
        "repository": repository,
        "run_id": int(env["GITHUB_RUN_ID"]),
        "head_sha": env["GITHUB_SHA"],
        "default_branch": args.default_branch,
        "service": args.service,
        "ref": args.ref,
        "validation_jobs": validation_job_names(json.loads(args.validation_matrix)),
        "image_version": env.get("ImageVersion", ""),
    }
    if not SHA40.match(args.ref):
        result = {"identity_reusable": False, "rejected": {}, "reason": "current ref is not an exact 40-hex SHA"}
    else:
        api = Api(repository, env["GITHUB_TOKEN"])
        runs = api.get(
            f"actions/workflows/build.yml/runs?head_sha={current['head_sha']}"
            "&event=workflow_dispatch&status=completed&per_page=30"
        ).get("workflow_runs", [])
        now = dt.datetime.now(dt.timezone.utc)
        candidates = []
        for run in runs:
            if run.get("id") == current["run_id"] or now - _ts(run["created_at"]) > dt.timedelta(hours=args.max_age_hours):
                continue
            jobs = api.get(f"actions/runs/{run['id']}/jobs?per_page=100").get("jobs", [])
            cand = {"run": run, "jobs": jobs, "plan_log": "", "image_versions": {}}
            plans = [j for j in jobs if j.get("name") == "plan"]
            if len(plans) == 1:
                cand["plan_log"] = api.get(f"actions/jobs/{plans[0]['id']}/logs", raw=True)
            for job in jobs:
                if job.get("name") in current["validation_jobs"] and job.get("conclusion") == "success":
                    head = api.get(f"actions/jobs/{job['id']}/logs", raw=True, limit=65536)
                    cand["image_versions"][job["name"]] = image_version(head)
            candidates.append(cand)
        result = assess(current, candidates, now, args.max_age_hours)
    verdict = (
        f"identity-reusable evidence: run {result['evidence_run']} "
        f"({result['validate_minutes']} validate min) -- NOT used, reuse is disabled"
        if result.get("identity_reusable") else
        "no identity-reusable evidence (" + (result.get("reason") or f"{len(result['rejected'])} candidate(s) rejected") + ")"
    )
    print(f"::notice title=verification-evidence {args.service}::{verdict}")
    summary = env.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(f"## Verification evidence reuse probe (measurement only)\n\n{verdict}\n\n")
            for rid, why in result.get("rejected", {}).items():
                handle.write(f"- run {rid}: {why}\n")
    print(json.dumps(result, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("probe")
    p.add_argument("--service", required=True)
    p.add_argument("--ref", required=True)
    p.add_argument("--validation-matrix", required=True)
    p.add_argument("--default-branch", default="master")
    p.add_argument("--max-age-hours", type=float, default=24)
    args = parser.parse_args(argv)
    try:
        return probe(args)
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
        # Measurement only: a broken probe must be visible, never gating.
        print(f"::warning title=verification-evidence::probe unavailable: {exc}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
