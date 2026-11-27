"""Bind a validation dispatch to one request, policy commit and source commit."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

from ci_check_failures import failure_ids

_CI_LIB = str(Path(__file__).resolve().parent / "lib")
if _CI_LIB not in sys.path:
    sys.path.insert(0, _CI_LIB)
from ci_constants import GITHUB_HTTPS_ORIGIN, RUN_DISCOVERY_DEADLINE_SECONDS, RUN_DISCOVERY_POLL_SECONDS

REPO = "onesyue/yueto-ci"


def gh(*args: str) -> str:
    return subprocess.check_output(["gh", *args], text=True)


def runs(branch: str) -> list[dict]:
    return json.loads(gh("run", "list", "--repo", REPO, "--workflow", "build.yml",
                         "--branch", branch, "--event", "workflow_dispatch", "--limit", "100",
                         "--json", "databaseId,displayTitle,headSha,event,status,conclusion"))


PENDING = frozenset({"queued", "requested", "pending", "waiting", "in_progress"})
# One official run per service in flight (owner rule t1520u, 2026-11-27). A
# YueOps validation alone fills the account's ~20 hosted job slots; a second
# concurrent one only queues behind it and doubles everyone's wait.
MAX_PENDING_PER_SERVICE = 1


def pending_dispatches() -> list[dict]:
    """Pending build.yml dispatches on every branch (master premerges included)."""
    rows = json.loads(gh("run", "list", "--repo", REPO, "--workflow", "build.yml",
                         "--event", "workflow_dispatch", "--limit", "100",
                         "--json", "databaseId,displayTitle,headSha,event,status,conclusion"))
    return [row for row in rows if row.get("status") in PENDING]


def admit(rows: list[dict], repo: str, source: str, policy: str) -> dict | None:
    """Reuse a pending run for this exact request, or refuse while the service is busy."""
    prefix = f"Build & publish images {repo} "
    mine = [row for row in rows if row.get("status") in PENDING
            and str(row.get("displayTitle", "")).startswith(prefix)]
    same = [row for row in mine if re.fullmatch(
        rf"{re.escape(prefix)}{source} \[nonce:[0-9a-f]{{32}}\]", row["displayTitle"])]
    for row in same:
        if row.get("headSha") == policy:
            return row
    if same:
        raise ValueError(f"run {same[0]['databaseId']} already validates {source} on another policy "
                         "revision; wait for it, not dispatched")
    if len(mine) >= MAX_PENDING_PER_SERVICE:
        raise ValueError(f"{repo} already has a pending official run {mine[0]['databaseId']}; "
                         "wait for it, not dispatched")
    return None


def select_run(rows: list[dict], before: set[int], title: str, policy: str) -> dict | None:
    matches = [row for row in rows if row["databaseId"] not in before
               and row["displayTitle"] == title and row["event"] == "workflow_dispatch"]
    if len(matches) > 1:
        raise ValueError("multiple runs carry the validation request identity")
    if not matches:
        return None
    if matches[0]["headSha"] != policy:
        raise ValueError("dispatched workflow revision differs from the reviewed local revision")
    return matches[0]


def dispatch(branch: str, policy: str, source: str, base: str, output: Path, *, board: str = "", repo: str = "yueops") -> int:
    if repo not in {"yueops", "yueboard", "yue-node"}:
        raise ValueError("unsupported validation repository")
    for name, value in (("policy", policy), ("source", source)):
        if re.fullmatch(r"[0-9a-f]{40}", value) is None:
            raise ValueError(f"{name} must be an exact commit SHA")
    if repo == "yueboard" and board:
        raise ValueError("Board context applies only to yueops and yue-node")
    if repo != "yueops" and base:
        raise ValueError("migration base applies only to yueops")
    if repo != "yueboard" and re.fullmatch(r"[0-9a-f]{40}", board) is None:
        raise ValueError("Board context must be an exact commit SHA")
    if repo == "yueops" and re.fullmatch(r"[0-9a-f]{40}", base) is None:
        raise ValueError("migration base must be an exact commit SHA")
    remote = gh("api", f"repos/{REPO}/commits/{branch}", "--jq", ".sha").strip()
    if remote != policy:
        raise ValueError("push the exact local policy commit before dispatching")
    before = {row["databaseId"] for row in runs(branch)}
    reused = admit(pending_dispatches(), repo, source, policy)
    if reused:
        request = reused["displayTitle"].rsplit("[nonce:", 1)[1].rstrip("]")
        before.discard(reused["databaseId"])
    else:
        request = uuid.uuid4().hex
    title = f"Build & publish images {repo} {source} [nonce:{request}]"
    output.mkdir(parents=True, exist_ok=True)
    receipt = output / "dispatch.json"
    intent = {"repository": repo, "request": request, "reused": bool(reused), "policy_revision": policy, "source_revision": source,
              "migration_base": base, "board_revision": board, "branch": branch, "prior_runs": sorted(before)}
    receipt.write_text(json.dumps(intent, indent=2) + "\n")
    fields = ["-f", f"service={repo}", "-f", f"ref={source}",
              "-f", "validation_only=true", "-f", "promote=false",
              "-f", "runner=ubuntu-24.04", "-f", f"nonce={request}"]
    if repo == "yueops":
        fields += ["-f", f"migration_base={base}"]
    if board:
        fields += ["-f", f"yueboard_contract_ref={board}"]
    if not reused:
        gh("workflow", "run", "build.yml", "--repo", REPO, "--ref", branch, *fields)
    deadline = time.monotonic() + RUN_DISCOVERY_DEADLINE_SECONDS
    row = None
    while time.monotonic() < deadline:
        row = select_run(runs(branch), before, title, policy)
        if row:
            break
        time.sleep(RUN_DISCOVERY_POLL_SECONDS)
    if row is None:
        raise ValueError(f"no run matched request {request}; intent retained at {receipt}")
    run_id = str(row["databaseId"])
    receipt.write_text(json.dumps(intent | {"run_id": run_id}, indent=2) + "\n")
    print(f"ci-check: {GITHUB_HTTPS_ORIGIN}/{REPO}/actions/runs/{run_id}", file=sys.stderr)
    # A failed watch is not a successful validation, nor a reason to discard logs.
    subprocess.run(["gh", "run", "watch", run_id, "--repo", REPO, "--exit-status"],
                   stdout=sys.stderr, check=False)
    final = json.loads(gh("run", "view", run_id, "--repo", REPO,
                         "--json", "status,conclusion,headSha,displayTitle,event"))
    (output / "result.json").write_text(json.dumps(final, indent=2) + "\n")
    if final["status"] != "completed":
        raise ValueError(f"run {run_id} has not completed; resume using {receipt}")
    if (final["headSha"] != policy or final["displayTitle"] != title
            or final["event"] != "workflow_dispatch"):
        raise ValueError("completed run identity changed")
    # Download all jobs: a failed pytest command may have been captured by a
    # later evidence step. Failure-only logs are not a complete test corpus.
    log = gh("run", "view", run_id, "--repo", REPO, "--log")
    (output / "remote.log").write_text(log)
    failures = failure_ids(log, repo)
    (output / "failures.txt").write_text("".join(item + "\n" for item in failures))
    for item in failures:
        print(item)
    if failures or final["conclusion"] != "success":
        print(f"ci-check: run {run_id} concluded {final['conclusion']}; logs: {output}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("branch", "policy", "source", "output"):
        parser.add_argument(f"--{field}", required=True)
    parser.add_argument("--repo", default="yueops")
    parser.add_argument("--base", default="")
    parser.add_argument("--board", default="")
    args = parser.parse_args()
    try:
        return dispatch(args.branch, args.policy, args.source, args.base, Path(args.output), board=args.board, repo=args.repo)
    except (ValueError, subprocess.CalledProcessError, OSError) as error:
        print(f"ci-check: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
