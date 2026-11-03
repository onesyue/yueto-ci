#!/usr/bin/env python3
"""Audit merged PRs via gh api. Exit 0 clean/registered, 1 unregistered, 2 incomplete.

GitHub REST exposes current check runs, not a complete history of overwritten
runs or dismissed reviews. Missing/ambiguous evidence fails closed. Committed Codex/parity receipts can satisfy missing evidence, never red checks.
This retrospective audit does not override GitHub branch rules.
"""
import argparse
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

REPOS = ("yueops", "yueboard", "yueto", "yueto-ci", "yuelink", "yuelink-ci", "yue-node")
ROOT = Path(__file__).resolve().parents[1]
# Bump when the interpretation of cached remote evidence changes.
CACHE_VERSION = 1


class RateFloorError(ValueError):
    pass


def cache_path(kind, key):
    root = Path(os.environ.get("MERGE_HYGIENE_CACHE_DIR", "~/.cache/yueto/merge-hygiene")).expanduser()
    digest = hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()
    return root / f"v{CACHE_VERSION}" / kind / f"{digest}.json"


def read_cache(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        # A missing, corrupt or incompatible entry is a miss, never a clean audit.
        return None


def write_cache(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def response_parts(output):
    headers, separator, body = output.replace("\r\n", "\n").partition("\n\n")
    lines = headers.splitlines()
    match = re.fullmatch(r"HTTP/\S+ (\d{3})(?: .*)?", lines[0] if lines else "")
    if not separator or not match:
        raise ValueError("invalid GitHub HTTP response; audit incomplete")
    return int(match[1]), {key.lower(): value.strip() for key, value in
                          (line.split(":", 1) for line in lines[1:] if ":" in line)}, body


def retry_delay(headers, attempt):
    delay = 60 * 2 ** attempt
    if "retry-after" in headers:
        value = headers["retry-after"]
        delay = float(value) if value.isdigit() else parsedate_to_datetime(value).timestamp() - time.time()
    if headers.get("x-ratelimit-remaining") == "0" and "x-ratelimit-reset" in headers:
        delay = max(delay, float(headers["x-ratelimit-reset"]) - time.time() + 1)
    return max(1, delay)


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return result


def api(endpoint):
    floor = int(os.environ.get("MERGE_HYGIENE_RATE_FLOOR", "300"))
    if floor < 0:
        raise ValueError("invalid rate floor")
    path = cache_path("http", endpoint)
    cached = read_cache(path)
    if not (isinstance(cached, dict) and cached.get("endpoint") == endpoint
            and isinstance(cached.get("etag"), str) and cached["etag"]
            and "\n" not in cached["etag"] and "\r" not in cached["etag"] and "body" in cached):
        cached = None
    command = ["gh", "api", endpoint, "--include"]
    if cached:
        command += ["-H", "If-None-Match: " + cached["etag"]]
    for attempt in range(3):
        # Never echo headers, bodies or gh stderr: they may contain secrets.
        result = subprocess.run(command, capture_output=True, text=True)
        status, headers, body = response_parts(result.stdout)
        remaining = headers.get("x-ratelimit-remaining")
        if remaining is not None and int(remaining) < floor:
            raise RateFloorError("incomplete: rate-floor")
        if status == 304:
            if cached is None:
                raise ValueError("304 without cached body; audit incomplete")
            return cached["body"]
        if status in (403, 429):
            if attempt == 2:
                break
            delay = retry_delay(headers, attempt)
            # Avoid holding a premerge gate for an entire hourly reset window.
            # Exiting incomplete is preferable to retrying before GitHub allows it.
            if delay > 300:
                break
            time.sleep(delay)
            continue
        if result.returncode or status != 200:
            break
        data = json.loads(body)
        if headers.get("etag"):
            write_cache(path, {"endpoint": endpoint, "etag": headers["etag"], "body": data})
        else:
            path.unlink(missing_ok=True)
        return data
    raise ValueError("GitHub API request failed; audit incomplete")


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


def enforcement_cutoff(owner):
    # This PR is the immutable activation anchor, not the caller's wall clock.
    # A failed lookup must never silently restore the historical exception policy.
    anchor = api("repos/onesyue/yueto-ci/pulls/71")
    if anchor["number"] != 71 or anchor["base"]["repo"]["full_name"] != "onesyue/yueto-ci":
        raise ValueError("invalid receipt policy activation anchor")
    if anchor.get("merged_at"):
        return timestamp(anchor["merged_at"])
    if anchor["state"] != "open":
        raise ValueError("receipt policy activation PR closed without merge")
    return None


def evidence_only(owner, repo, base_sha, head_sha):
    if repo != "yueto-ci":
        return False
    if any(not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha)
           for sha in (base_sha, head_sha)):
        raise ValueError("invalid PR base or head SHA")
    # Compare uses the merge base of these immutable commits. The mutable PR
    # files endpoint can describe another head even if a refetch sees A -> B -> A.
    comparison = api(f"repos/{owner}/{repo}/compare/{base_sha}...{head_sha}")
    if not isinstance(comparison, dict):
        raise ValueError("invalid compare response; audit incomplete")
    files = comparison.get("files")
    total = comparison.get("total_commits")
    if (not isinstance(files, list) or len(files) >= 300
            or type(total) is not int or total < 0 or bool(total) != bool(files)):
        raise ValueError("compare file evidence missing, truncated or inconsistent; audit incomplete")

    def allowed(path):
        return (isinstance(path, str) and ".." not in path.split("/")
                and re.fullmatch(r"(?:merge-receipts/|reviews/merge-receipts-[^/]+/).+", path)
                is not None)

    for entry in files:
        if "previous_filename" in entry and not allowed(entry["previous_filename"]):
            raise ValueError("previous filename outside evidence paths; audit incomplete")
    return bool(files) and all(entry["status"] in ("added", "modified")
                               and allowed(entry["filename"]) for entry in files)


def merged_findings(owner, repo, pr):
    merge_sha = pr["merge_commit_sha"]
    if not isinstance(merge_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", merge_sha):
        raise ValueError("invalid PR merge commit SHA")
    key = [owner, repo, pr["number"], merge_sha]
    path = cache_path("merged", key)
    inputs = {"key": key, "head": pr["head"]["sha"], "base": pr["base"]["sha"],
              "merged_at": pr["merged_at"], "author": pr["user"]["login"]}
    cached = read_cache(path)
    if (isinstance(cached, dict) and cached.get("inputs") == inputs
            and isinstance(cached.get("findings"), list)
            and all(isinstance(reason, str) for reason in cached["findings"])
            and type(cached.get("evidence_only")) is bool):
        return cached["findings"], cached["evidence_only"]
    prefix = f"repos/{owner}/{repo}"
    sha = pr["head"]["sha"]
    reasons = findings(
        pr, all_rows(f'{prefix}/pulls/{pr["number"]}/reviews'),
        all_rows(f"{prefix}/commits/{sha}/check-runs?filter=all", "check_runs"),
        all_rows(f"{prefix}/commits/{sha}/statuses"))
    only_evidence = evidence_only(owner, repo, pr["base"]["sha"], sha)
    # Persist only a complete remote snapshot. Receipts, exceptions and policy
    # activation are local/current decisions and must be evaluated on every run.
    write_cache(path, {"inputs": inputs, "findings": reasons, "evidence_only": only_evidence})
    return reasons, only_evidence


def audit(owner, repos, cutoff, registered, now):
    enforced_since = enforcement_cutoff(owner)
    # Post-activation violations cannot age out through --hours or a quiet repo.
    if enforced_since is not None:
        cutoff = min(cutoff, enforced_since)
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
                reasons, only_evidence = merged_findings(owner, repo, pr)
                if only_evidence:
                    reasons = [r for r in reasons if r not in (
                        "no_approving_review_at_merge", "no_check_evidence_at_merge")]
                evidence = receipt(repo, pr)
                satisfied = []
                if evidence:
                    satisfied = [r for r in reasons if r in (
                        "no_approving_review_at_merge", "no_check_evidence_at_merge")]
                    reasons = [r for r in reasons if r not in satisfied]
                required = enforced_since is not None and timestamp(pr["merged_at"]) > enforced_since
                if required and not evidence and not only_evidence:
                    reasons.append("required_merge_receipt_missing")
                if reasons or evidence or only_evidence:
                    results.append({"repo": repo, "pr": pr["number"], "url": pr["html_url"],
                                    "head": sha, "merged_at": pr["merged_at"], "findings": reasons,
                                    "exception": None if required else registered.get((repo, pr["number"])),
                                    "receipt": evidence, "satisfied_by_receipt": satisfied,
                                    **({"evidence_only": True} if only_evidence else {})})
            if batch and timestamp(batch[-1]["updated_at"]) < cutoff:
                # merged_at alone is unsafe: an older merge can be updated today
                # and precede newer merges in this updated-descending listing.
                break
    return results


def premerge(owner, repo, number):
    prefix = f"repos/{owner}/{repo}"
    pr = api(f"{prefix}/pulls/{number}")
    if pr["number"] != number or pr["state"] != "open" or pr.get("merged_at"):
        raise ValueError("premerge requires an open PR")
    head_sha, base_sha = pr["head"]["sha"], pr["base"]["sha"]
    reviews = all_rows(f"{prefix}/pulls/{number}/reviews")
    checks = all_rows(f"{prefix}/commits/{head_sha}/check-runs?filter=all", "check_runs")
    statuses = all_rows(f"{prefix}/commits/{head_sha}/statuses")
    # The historical audit can take minutes. Evaluate newly fetched checks at
    # observation time, not at the earlier start of that audit.
    now = datetime.now(timezone.utc)
    candidate = pr | {"merged_at": now.isoformat()}
    only_evidence = evidence_only(owner, repo, base_sha, head_sha)
    # Reject refs that have moved since the initial capture as well.
    refreshed = api(f"{prefix}/pulls/{number}")
    if refreshed["head"]["sha"] != head_sha or refreshed["base"]["sha"] != base_sha:
        raise ValueError("PR head or base changed while fetching evidence; audit incomplete")
    evidence = receipt(repo, candidate)
    reasons = findings(candidate, reviews, checks, statuses)
    if evidence:
        if evidence["backfilled"] or any(timestamp(evidence[part][field]) > now
                for part, field in (("review", "reviewed_at"), ("parity", "ran_at"))):
            raise ValueError("premerge evidence must already exist and not be backfilled")
        reasons = [r for r in reasons if r not in (
            "no_approving_review_at_merge", "no_check_evidence_at_merge")]
    elif not only_evidence:
        reasons.append("required_merge_receipt_missing")
    if only_evidence:
        reasons = [r for r in reasons if r not in (
            "no_approving_review_at_merge", "no_check_evidence_at_merge")]
    return {"repo": repo, "pr": number, "url": pr["html_url"], "head": pr["head"]["sha"],
            "merged_at": None, "findings": reasons, "exception": None,
            "receipt": evidence, "satisfied_by_receipt": [],
            **({"evidence_only": True} if only_evidence else {})}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", default="onesyue")
    parser.add_argument("--repos", nargs="+", choices=REPOS, default=list(REPOS))
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--exceptions", type=Path, default=ROOT / "merge-hygiene-exceptions.json")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    parser.add_argument("--premerge", nargs=2, metavar=("REPO", "PR"),
                        help="also require committed evidence and passing current checks for an open PR")
    args = parser.parse_args()
    if args.premerge and (args.premerge[0] not in REPOS or not args.premerge[1].isdigit()
                          or int(args.premerge[1]) <= 0):
        parser.error("--premerge requires a supported repo and positive PR number")
    if args.hours <= 0 or not re.fullmatch(r"[A-Za-z0-9-]+", args.owner):
        parser.error("positive --hours and valid GitHub --owner required")
    now = datetime.now(timezone.utc)
    try:
        rows = audit(args.owner, args.repos, now - timedelta(hours=args.hours),
                     exceptions(args.exceptions), now)
        if args.premerge:
            rows.append(premerge(args.owner, args.premerge[0], int(args.premerge[1])))
        result = {"schema": 1, "complete": True, "findings": rows,
                  "unregistered": sum(r["exception"] is None
                                      and not ((r.get("receipt") or r.get("evidence_only"))
                                               and not r["findings"])
                                      for r in rows)}
    except RateFloorError:
        result = {"schema": 1, "complete": False, "error": "incomplete: rate-floor"}
    except (ValueError, OSError, KeyError, TypeError, OverflowError):
        # Never turn inaccessible private repositories or malformed evidence into green.
        result = {"schema": 1, "complete": False,
                  "error": "API/evidence/exception input unavailable or invalid; audit incomplete"}
    if args.format == "json":
        print(json.dumps(result, indent=2))
    elif not result["complete"]:
        print(result["error"])
    else:
        for row in rows:
            if row.get("evidence_only") and not row["findings"]:
                print(f'EVIDENCE-ONLY {row["url"]}')
                continue
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
