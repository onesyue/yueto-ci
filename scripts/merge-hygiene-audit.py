#!/usr/bin/env python3
"""Audit merged PRs via gh api. Exit 0 clean/registered, 1 unregistered, 2 incomplete.

GitHub REST exposes current check runs, not a complete history of overwritten
runs or dismissed reviews. Missing/ambiguous evidence fails closed. Committed Codex/parity receipts can satisfy missing evidence, never red checks.
This retrospective audit does not override GitHub branch rules.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

REPOS = ("yueops", "yueboard", "yueto", "yueto-ci", "yuelink", "yuelink-ci", "yue-node")
ROOT = Path(__file__).resolve().parents[1]


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return result


def api(endpoint):
    # Do not echo gh stderr: authentication/transport diagnostics may contain secrets.
    result = subprocess.run(["gh", "api", endpoint], capture_output=True, text=True)
    if result.returncode:
        raise ValueError("GitHub API request failed; audit incomplete")
    return json.loads(result.stdout)


def pages(endpoint, key=None):
    page = 1
    while True:
        data = api(f"{endpoint}{'&' if '?' in endpoint else '?'}per_page=100&page={page}")
        rows = data[key] if key else data
        if not isinstance(rows, list):
            raise ValueError("unexpected GitHub API response")
        yield rows
        if len(rows) < 100:
            break
        page += 1


def all_rows(endpoint, key=None):
    return [row for batch in pages(endpoint, key) for row in batch]


def findings(pr, reviews, checks, statuses):
    merged = timestamp(pr["merged_at"])
    reasons = []
    latest_reviews = {}
    for review in sorted(reviews, key=lambda r: (r.get("submitted_at") or "", r["id"])):
        if not review.get("submitted_at") or timestamp(review["submitted_at"]) > merged:
            continue
        if review["state"] in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            latest_reviews[review["user"]["login"]] = review
    if not any(r["state"] == "APPROVED" and login != pr["user"]["login"]
               and r["user"].get("type") != "Bot" for login, r in latest_reviews.items()):
        reasons.append("no_approving_review_at_merge")

    # Only checks from the same app/suite/name can replace one another.
    # Without suite identity, preserve each run rather than hide an independent
    # failure. REST started_at is execution time, not queue creation time.
    latest_checks = {}
    observed_checks = {}
    for check in checks:
        suite = (check.get("check_suite") or {}).get("id")
        identity = ("suite", suite) if suite is not None else ("run", check["id"])
        key = (check["app"]["id"], identity, check["name"])
        observed_checks[key] = check["name"]
        created = check.get("created_at")
        started = check.get("started_at")
        if created:
            existed = timestamp(created)
        elif started and timestamp(started) <= merged:
            existed = timestamp(started)
        else:
            # Even an older green run cannot establish whether this attempt
            # was queued at merge. Do not suppress this ambiguity by key.
            reasons.append("check_history_unavailable:" + check["name"])
            continue
        if existed > merged:
            continue
        if key not in latest_checks or (existed, check["id"]) > latest_checks[key][0]:
            latest_checks[key] = ((existed, check["id"]), check)
    for key in observed_checks.keys() - latest_checks.keys():
        reasons.append("check_history_unavailable:" + observed_checks[key])
    latest_statuses = {}
    for status in statuses:
        created = timestamp(status["created_at"])
        if created <= merged:
            key = status["context"]
            if key not in latest_statuses or (created, status["id"]) > latest_statuses[key][0]:
                latest_statuses[key] = ((created, status["id"]), status)
    if not latest_checks and not latest_statuses:
        reasons.append("no_check_evidence_at_merge")
    for _, check in latest_checks.values():
        completed = check.get("completed_at")
        if check["status"] != "completed" or not completed or timestamp(completed) > merged:
            reasons.append("check_pending_at_merge:" + check["name"])
        elif check["conclusion"] not in ("success", "neutral", "skipped"):
            reasons.append("check_nonpassing_at_merge:" + check["name"])
    for _, status in latest_statuses.values():
        if status["state"] != "success":
            reasons.append("status_nonpassing_at_merge:" + status["context"])
    return sorted(set(reasons))


def exceptions(path):
    value = json.loads(path.read_text())
    if set(value) != {"schema", "exceptions"} or value["schema"] != 1:
        raise ValueError("invalid exception schema")
    result = {}
    for entry in value["exceptions"]:
        if (set(entry) != {"repo", "pr", "reason", "approver"}
                or entry["repo"] not in REPOS or type(entry["pr"]) is not int or entry["pr"] <= 0
                or not all(isinstance(entry[k], str) and entry[k].strip() for k in ("reason", "approver"))):
            raise ValueError("exceptions require exact repo/PR, reason and approver")
        key = (entry["repo"], entry["pr"])
        if key in result:
            raise ValueError("duplicate exception")
        result[key] = entry
    return result


# Receipt schema 1 is deliberately closed: misspelled or additional fields fail
# rather than silently weakening the evidence contract.
def committed_text(path):
    relative = path.relative_to(ROOT).as_posix()
    committed = subprocess.run(["git", "show", f"HEAD:{relative}"], cwd=ROOT,
                               capture_output=True, text=True)
    if committed.returncode or committed.stdout != path.read_text():
        raise ValueError("receipt and review must match committed evidence")
    return committed.stdout


def receipt(repo, pr):
    path = ROOT / "merge-receipts" / repo / f'{pr["number"]}.json'
    if not path.exists() and not path.is_symlink():
        return None
    contents = committed_text(path)
    def exact(value, keys):
        if not isinstance(value, dict) or set(value) != set(keys.split()):
            raise ValueError("invalid receipt schema")
    def nonempty(value):
        return isinstance(value, str) and bool(value.strip())
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate receipt key")
            result[key] = value
        return result
    value = json.loads(contents, object_pairs_hook=unique)
    exact(value, "schema repo pr head review parity backfilled")
    review, parity = value["review"], value["parity"]
    exact(review, "tool verdict reviewed_head artifact reviewer reviewed_at")
    exact(parity, "result head command log_sha256 ran_at runner")
    sha = pr["head"]["sha"]
    if (type(value["schema"]) is not int or value["schema"] != 1
            or value["repo"] != repo or type(value["pr"]) is not int
            or value["pr"] != pr["number"] or type(value["backfilled"]) is not bool
            or not isinstance(value["head"], str)
            or not re.fullmatch(r"[0-9a-fA-F]{40}", value["head"])
            or value["head"] != sha or review["reviewed_head"] != sha
            or parity["head"] != sha or review["tool"] != "codex"
            or review["verdict"] != "approve" or not nonempty(review["reviewer"])
            or review["reviewer"].strip().casefold() == pr["user"]["login"].casefold()
            or parity["result"] != "pass" or not nonempty(parity["command"])
            or parity["runner"] not in ("box", "yueto-ci", "mac-5f08d00f")
            or not isinstance(parity["log_sha256"], str)
            or not re.fullmatch(r"[0-9a-fA-F]{64}", parity["log_sha256"])
            or not nonempty(review["artifact"])):
        raise ValueError("invalid receipt evidence")
    artifact = Path(review["artifact"])
    if (artifact.is_absolute() or ".." in artifact.parts
            or not (ROOT / artifact).resolve().is_relative_to(ROOT.resolve())
            or not (ROOT / artifact).is_file()):
        raise ValueError("review artifact must exist inside repository")
    committed_text(ROOT / artifact)
    merged = timestamp(pr["merged_at"])
    for when in (review["reviewed_at"], parity["ran_at"]):
        if not isinstance(when, str):
            raise ValueError("receipt time must be an ISO timezone timestamp")
        moment = timestamp(when)
        if moment > merged + timedelta(hours=24) or (moment > merged and not value["backfilled"]):
            raise ValueError("receipt outside evidence window or unmarked backfill")
    return value


def audit(owner, repos, cutoff, registered, now):
    results = []
    for repo in repos:
        prefix = f"repos/{owner}/{repo}"
        for batch in pages(prefix + "/pulls?state=closed&sort=updated&direction=desc"):
            for pr in batch:
                if not pr.get("merged_at") or not cutoff <= timestamp(pr["merged_at"]) <= now:
                    continue
                sha = pr["head"]["sha"]
                if not re.fullmatch(r"[0-9a-f]{40}", sha):
                    raise ValueError("invalid PR head SHA")
                reasons = findings(
                    pr, all_rows(f'{prefix}/pulls/{pr["number"]}/reviews'),
                    all_rows(f"{prefix}/commits/{sha}/check-runs?filter=all", "check_runs"),
                    all_rows(f"{prefix}/commits/{sha}/statuses"))
                evidence = receipt(repo, pr)
                satisfied = []
                if evidence:
                    satisfied = [r for r in reasons if r in (
                        "no_approving_review_at_merge", "no_check_evidence_at_merge")]
                    reasons = [r for r in reasons if r not in satisfied]
                if reasons or evidence:
                    results.append({"repo": repo, "pr": pr["number"], "url": pr["html_url"],
                                    "head": sha, "merged_at": pr["merged_at"], "findings": reasons,
                                    "exception": registered.get((repo, pr["number"])),
                                    "receipt": evidence, "satisfied_by_receipt": satisfied})
            if batch and timestamp(batch[-1]["updated_at"]) < cutoff:
                break
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", default="onesyue")
    parser.add_argument("--repos", nargs="+", choices=REPOS, default=list(REPOS))
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--exceptions", type=Path, default=ROOT / "merge-hygiene-exceptions.json")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    args = parser.parse_args()
    if args.hours <= 0 or not re.fullmatch(r"[A-Za-z0-9-]+", args.owner):
        parser.error("positive --hours and valid GitHub --owner required")
    now = datetime.now(timezone.utc)
    try:
        rows = audit(args.owner, args.repos, now - timedelta(hours=args.hours),
                     exceptions(args.exceptions), now)
        result = {"schema": 1, "complete": True, "findings": rows,
                  "unregistered": sum(r["exception"] is None
                                      and not (r.get("receipt") and not r["findings"])
                                      for r in rows)}
    except (ValueError, OSError, KeyError, TypeError):
        # Never turn inaccessible private repositories or malformed evidence into green.
        result = {"schema": 1, "complete": False,
                  "error": "API/evidence/exception input unavailable or invalid; audit incomplete"}
    if args.format == "json":
        print(json.dumps(result, indent=2))
    elif not result["complete"]:
        print(result["error"])
    else:
        for row in rows:
            if row.get("receipt"):
                print(f'RECEIPT {row["url"]}: head={row["head"]} '
                      f'backfilled={str(row["receipt"]["backfilled"]).lower()} '
                      f'satisfies={", ".join(row["satisfied_by_receipt"]) or "supplemental evidence"}')
                if not row["findings"]:
                    continue
            state = "REGISTERED" if row["exception"] else "UNREGISTERED"
            print(f'{state} {row["url"]}: {", ".join(row["findings"])}')
            if row["exception"]:
                print(f'  {row["exception"]["approver"]}: {row["exception"]["reason"]}')
        print(f'{result["unregistered"]} unregistered merge hygiene violation(s)')
    return 2 if not result["complete"] else int(result["unregistered"] > 0)


if __name__ == "__main__":
    sys.exit(main())
