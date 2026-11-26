#!/usr/bin/env python3
"""Count failing pytest node ids in recent failed image-build runs.

Read-only. The gh CLI supplies job logs. This tool does not rerun workflows,
download unrelated artifacts, or print log bodies.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ci_check_failures  # noqa: E402

WORKFLOW = "Build & publish images"
PYTEST_STEPS = (
    "Execute owned Ops pytest selection",
    "Run service-owned pytest selection",
    "Validate yueops backend",
)
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_YUEOPS_SHA = re.compile(r"\byueops ([0-9a-f]{40})\b")
_SECRET = re.compile(r"(token|password|secret|authorization|bearer)", re.IGNORECASE)


def yueops_sha(title: str) -> str:
    match = _YUEOPS_SHA.search(title or "")
    return match.group(1) if match else ""


def reason_for(log_text: str, nodeid: str) -> str:
    """Return a short assertion tail, never a secret-bearing line."""
    needle = "FAILED " + nodeid + " - "
    for line in log_text.splitlines():
        payload = _ANSI.sub("", line).split("Z ", 1)[-1]
        if needle not in payload:
            continue
        reason = payload.split(needle, 1)[1].strip()
        if _SECRET.search(reason) or "://" in reason:
            return "redacted"
        return reason[:160]
    return ""


def failed_pytest_jobs(jobs: list[dict]) -> list[dict]:
    selected = []
    for job in jobs:
        if job.get("conclusion") != "failure":
            continue
        names = [step.get("name") for step in job.get("steps") or [] if step.get("conclusion") == "failure"]
        if any(name in PYTEST_STEPS for name in names):
            selected.append(job)
    return selected


def cluster(records: list[dict]) -> list[dict]:
    """Aggregate parsed run records into node-id counts."""
    grouped: dict[str, dict] = {}
    for record in records:
        for nodeid in record["nodeids"]:
            row = grouped.setdefault(nodeid, {
                "id": nodeid,
                "count": 0,
                "runs": [],
                "yueops_shas": [],
                "reasons": Counter(),
            })
            row["count"] += 1
            if record["run_id"] not in row["runs"]:
                row["runs"].append(record["run_id"])
            sha = record.get("yueops_sha") or ""
            if sha and sha not in row["yueops_shas"]:
                row["yueops_shas"].append(sha)
            reason = record.get("reasons", {}).get(nodeid)
            if reason:
                row["reasons"][reason] += 1
    rows = []
    for row in grouped.values():
        reason = row["reasons"].most_common(1)[0][0] if row["reasons"] else ""
        rows.append({
            "id": row["id"],
            "count": row["count"],
            "runs": row["runs"],
            "yueops_shas": row["yueops_shas"],
            "reason": reason,
        })
    rows.sort(key=lambda item: (-item["count"], item["id"]))
    return rows


def classify(row: dict, success_shas: set[str]) -> str:
    """A node id is a flake when every failing YueOps commit also has a green run."""
    shas = set(row.get("yueops_shas") or [])
    if shas and shas <= success_shas:
        return "flake"
    return "real"


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


def gh_exec(args: list[str]) -> str:
    allowed = {"run", "api"}
    if not args or args[0] not in allowed:
        raise ValueError("refusing gh command")
    if args[0] == "run" and args[1] not in {"list", "view"}:
        raise ValueError("refusing gh command")
    env = os.environ.copy()
    env["NO_COLOR"] = "1"
    last = "gh failed"
    for attempt in range(4):
        result = subprocess.run(["gh", *args], capture_output=True, text=True, env=env, check=False)
        if result.returncode == 0:
            return strip_ansi(result.stdout)
        detail = strip_ansi(result.stderr).strip().splitlines()
        last = detail[0] if detail else "gh failed"
        if not any(token in last.lower() for token in ("stream", "eof", "timeout", "reset", "temporarily")):
            break
        time.sleep(attempt + 1)
    raise RuntimeError(last)


def _json_loads(text: str):
    return json.loads(strip_ansi(text))


def collect(gh, repo: str, workflow: str, limit: int, workers: int = 4) -> tuple[list[dict], dict]:
    runs = _json_loads(gh([
        "run", "list", "--repo", repo, "--workflow", workflow, "--status", "failure",
        "--limit", str(limit),
        "--json", "databaseId,url,displayTitle,createdAt,headSha",
    ]))
    records = []
    stats = {"runs": len(runs), "pytest_jobs": 0, "jobs_without_node_ids": 0, "log_errors": 0}

    def one(run: dict) -> list[dict]:
        payload = _json_loads(gh([
            "api", f"repos/{repo}/actions/runs/{run['databaseId']}/jobs?per_page=100",
        ]))
        jobs = payload["jobs"] if isinstance(payload, dict) else payload
        found = []
        for job in failed_pytest_jobs(jobs):
            try:
                log_text = gh(["run", "view", "--repo", repo, "--job", str(job["id"]), "--log-failed"])
            except RuntimeError:
                found.append({
                    "run_id": run["databaseId"],
                    "url": run.get("url") or "",
                    "yueops_sha": yueops_sha(run.get("displayTitle") or ""),
                    "job_id": job["id"],
                    "job_name": job.get("name") or "",
                    "nodeids": [],
                    "reasons": {},
                    "log_error": True,
                })
                continue
            nodeids = ci_check_failures.node_ids(log_text)
            reasons = {nodeid: reason_for(log_text, nodeid) for nodeid in nodeids}
            found.append({
                "run_id": run["databaseId"],
                "url": run.get("url") or "",
                "yueops_sha": yueops_sha(run.get("displayTitle") or ""),
                "job_id": job["id"],
                "job_name": job.get("name") or "",
                "nodeids": nodeids,
                "reasons": reasons,
            })
        return found

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 2))) as pool:
        for found in pool.map(one, runs):
            for record in found:
                stats["pytest_jobs"] += 1
                if record.get("log_error"):
                    stats["log_errors"] += 1
                elif not record["nodeids"]:
                    stats["jobs_without_node_ids"] += 1
                records.append(record)
    return records, stats


def success_shas(gh, repo: str, workflow: str, limit: int) -> set[str]:
    runs = _json_loads(gh([
        "run", "list", "--repo", repo, "--workflow", workflow, "--status", "success",
        "--limit", str(limit),
        "--json", "displayTitle",
    ]))
    return {yueops_sha(run.get("displayTitle") or "") for run in runs} - {""}


def render(rows: list[dict], stats: dict, success: set[str]) -> str:
    lines = [
        f"runs {stats['runs']}",
        f"pytest_jobs {stats['pytest_jobs']}",
        f"jobs_without_node_ids {stats['jobs_without_node_ids']}",
        f"log_errors {stats['log_errors']}",
    ]
    for row in rows:
        kind = classify(row, success)
        lines.append(f"{row['count']}\t{kind}\t{row['id']}\t{row['reason']}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None, gh=gh_exec) -> int:
    parser = argparse.ArgumentParser(description="Count failing pytest ids from recent failed image builds")
    parser.add_argument("--repo", default="onesyue/yueto-ci")
    parser.add_argument("--workflow", default=WORKFLOW)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--success-limit", type=int, default=40)
    args = parser.parse_args(argv)
    if args.limit < 1 or args.limit > 50:
        print("limit must be 1..50", file=sys.stderr)
        return 2
    records, stats = collect(gh, args.repo, args.workflow, args.limit)
    # One record per job. Counts in cluster() are per job, which matches shard fan-out.
    # Collapse to one hit per run so a 16-shard fan-out does not multiply one test.
    per_run: dict[int, dict] = {}
    for record in records:
        bucket = per_run.setdefault(record["run_id"], {
            "run_id": record["run_id"],
            "url": record["url"],
            "yueops_sha": record["yueops_sha"],
            "nodeids": [],
            "reasons": {},
        })
        for nodeid in record["nodeids"]:
            if nodeid not in bucket["nodeids"]:
                bucket["nodeids"].append(nodeid)
            if nodeid not in bucket["reasons"] and record["reasons"].get(nodeid):
                bucket["reasons"][nodeid] = record["reasons"][nodeid]
    rows = cluster(list(per_run.values()))
    print(render(rows, stats, success_shas(gh, args.repo, args.workflow, args.success_limit)), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
