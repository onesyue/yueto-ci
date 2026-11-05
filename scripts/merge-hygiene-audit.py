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
CACHE_VERSION = 2
# Exact approved snapshot bytes; every path uses this pin. Tests may patch it,
# but CLI arguments cannot authorize a replacement snapshot.
ACCEPTED_HISTORY_SHA256 = "6223d77fdf5ae6ab5b3530509ad8b8883629e0c6fc7ed4f48047ba0f23e33cd9"


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
        try:
            status, headers, body = response_parts(result.stdout)
        except ValueError:
            # A truncated/absent gh response is not evidence. Retry the read
            # within the same three-attempt budget, then remain incomplete.
            if attempt == 2:
                raise
            time.sleep(attempt + 1)
            continue
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


def baseline(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate baseline key")
            result[key] = value
        return result

    def nonempty(value):
        return isinstance(value, str) and bool(value.strip())

    contents = path.read_bytes()
    if hashlib.sha256(contents).hexdigest() != ACCEPTED_HISTORY_SHA256:
        raise ValueError("baseline SHA256 does not match approved snapshot")
    value = json.loads(contents, object_pairs_hook=unique)
    if (not isinstance(value, dict) or set(value) != {"schema", "frozen_at", "approver", "entries"}
            or type(value["schema"]) is not int or value["schema"] != 1
            or not nonempty(value["frozen_at"]) or not nonempty(value["approver"])
            or not isinstance(value["entries"], list)):
        raise ValueError("invalid baseline schema")
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
                        r"(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])",
                        value["frozen_at"]):
        raise ValueError("baseline frozen_at must be an ISO timezone timestamp")
    frozen_at = timestamp(value["frozen_at"])
    result = {}
    for entry in value["entries"]:
        if (not isinstance(entry, dict) or set(entry) != {"repo", "pr", "head", "findings", "reason"}
                or entry["repo"] not in REPOS or type(entry["pr"]) is not int or entry["pr"] <= 0
                or not isinstance(entry["head"], str) or not re.fullmatch(r"[0-9a-fA-F]{40}", entry["head"])
                or not isinstance(entry["findings"], list) or not all(map(nonempty, entry["findings"]))
                or len(set(entry["findings"])) != len(entry["findings"]) or not nonempty(entry["reason"])):
            raise ValueError("invalid baseline entry")
        key = (entry["repo"], entry["pr"], entry["head"])
        if key in result:
            raise ValueError("duplicate baseline entry")
        result[key] = entry
    return frozen_at, result


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
    path = cache_path("compare", key)
    inputs = {"key": key, "head": pr["head"]["sha"], "base": pr["base"]["sha"],
              "merged_at": pr["merged_at"], "author": pr["user"]["login"]}
    prefix = f"repos/{owner}/{repo}"
    sha = pr["head"]["sha"]
    # Reviews and check runs can change after merge without changing the PR's
    # refs or updated_at. Revalidate every evidence page via HTTP/ETag before
    # deriving a verdict; an unavailable endpoint must never reuse old green.
    reasons = findings(
        pr, all_rows(f'{prefix}/pulls/{pr["number"]}/reviews'),
        all_rows(f"{prefix}/commits/{sha}/check-runs?filter=all", "check_runs"),
        all_rows(f"{prefix}/commits/{sha}/statuses"))
    cached = read_cache(path)
    if (isinstance(cached, dict) and cached.get("inputs") == inputs
            and type(cached.get("evidence_only")) is bool):
        only_evidence = cached["evidence_only"]
    else:
        # Only the file comparison between immutable commit SHAs is reusable
        # without HTTP validation. Version 2 ignores all old verdict snapshots.
        only_evidence = evidence_only(owner, repo, pr["base"]["sha"], sha)
        write_cache(path, {"inputs": inputs, "evidence_only": only_evidence})
    return reasons, only_evidence


def merged_row(owner, repo, pr, enforced_since, registered):
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
    return {"repo": repo, "pr": pr["number"], "url": pr["html_url"],
            "head": pr["head"]["sha"], "merged_at": pr["merged_at"], "findings": reasons,
            "exception": None if required else registered.get((repo, pr["number"])),
            "receipt": evidence, "satisfied_by_receipt": satisfied,
            **({"evidence_only": True} if only_evidence else {})}


def indirect_merge(owner, repo, pr, enforced_since, registered):
    """Attribute automatic ancestor closure to its independently admitted merge source."""
    prefix = f"repos/{owner}/{repo}"
    merge_sha, old_head = pr["merge_commit_sha"], pr["head"]["sha"]
    commit = api(f"{prefix}/git/commits/{merge_sha}")
    if not isinstance(commit, dict):
        raise ValueError("invalid indirect merge commit response")
    parents = commit.get("parents")
    if (commit.get("sha") != merge_sha or not isinstance(parents, list)
            or any(not isinstance(p, dict) or not isinstance(p.get("sha"), str)
                   or not re.fullmatch(r"[0-9a-f]{40}", p["sha"]) for p in parents)
            or len({p["sha"] for p in parents}) != len(parents)):
        raise ValueError("invalid indirect merge parent evidence")
    if len(parents) != 2:
        return None  # Unsupported topology retains ordinary findings and history rules.
    first, second = (p["sha"] for p in parents)
    if old_head == second:
        return None  # A direct source's red/missing evidence is never transferable.
    associated = all_rows(f"{prefix}/commits/{merge_sha}/pulls")
    if any(not isinstance(p, dict) for p in associated):
        raise ValueError("invalid associated PR response")
    direct = [p for p in associated if p.get("merged_at") and p.get("merge_commit_sha") == merge_sha
              and p["head"]["sha"] == second]
    if len(direct) != 1:
        raise ValueError("indirect merge requires one unambiguous associated direct PR")
    direct = direct[0]
    expected_repo = f"{owner}/{repo}"
    if (type(direct["number"]) is not int or direct["number"] <= 0
            or not isinstance(direct.get("merged_at"), str)
            or not isinstance(pr.get("merged_at"), str)
            or direct["number"] == pr["number"] or direct.get("state") != "closed"
            or pr.get("state") != "closed"
            or direct["base"]["repo"]["full_name"] != expected_repo
            or pr["base"]["repo"]["full_name"] != expected_repo
            or not pr["base"]["ref"] or direct["base"]["ref"] != pr["base"]["ref"]
            or timestamp(direct["merged_at"]) > timestamp(pr["merged_at"])):
        raise ValueError("indirect merge target or timestamp mismatch")
    # Both immutable comparisons still use authenticated fresh HTTP/ETag evidence.
    for target, ancestor in ((second, True), (first, False)):
        comparison = api(f"{prefix}/compare/{old_head}...{target}")
        if not isinstance(comparison, dict):
            raise ValueError("invalid indirect merge comparison response")
        ahead, behind = comparison.get("ahead_by"), comparison.get("behind_by")
        merge_base = comparison["merge_base_commit"]["sha"]
        if (comparison["base_commit"]["sha"] != old_head
                or not isinstance(merge_base, str) or not re.fullmatch(r"[0-9a-f]{40}", merge_base)
                or type(ahead) is not int or type(behind) is not int or min(ahead, behind) < 0
                or type(comparison.get("total_commits")) is not int
                or comparison["total_commits"] != ahead):
            raise ValueError("incomplete indirect merge ancestry evidence")
        if ancestor:
            valid = comparison.get("status") == "ahead" and merge_base == old_head and behind == 0 and ahead > 0
        else:
            valid = (comparison.get("status") in ("behind", "diverged")
                     and merge_base != old_head and behind > 0
                     and (comparison["status"] == "behind") == (ahead == 0))
        if not valid:
            raise ValueError("old head is not newly introduced ancestry of this merge")
    # Evaluate the actual source normally, at its own merge time. No recursion,
    # baseline exception, evidence-only waiver or post-merge green substitution.
    direct_row = merged_row(owner, repo, direct, enforced_since, registered)
    if direct_row["findings"] or not direct_row["receipt"] or direct_row.get("evidence_only"):
        raise ValueError("indirect merge direct source lacks ordinary passing receipt admission")
    return {"direct_pr": direct["number"], "direct_head": second, "merge_sha": merge_sha,
            "direct_merged_at": direct["merged_at"], "indirect_merged_at": pr["merged_at"],
            "direct_receipt_artifact": direct_row["receipt"]["review"]["artifact"]}


def audit(owner, repos, cutoff, registered, now):
    enforced_since = enforcement_cutoff(owner)
    # Post-activation violations cannot age out through --hours or a quiet repo.
    if enforced_since is not None:
        cutoff = min(cutoff, enforced_since)
    results = []
    for repo in repos:
        prefix = f"repos/{owner}/{repo}"
        merged = []
        rows = []
        for batch in pages(prefix + "/pulls?state=closed&sort=updated&direction=desc"):
            for pr in batch:
                if not pr.get("merged_at") or not cutoff <= timestamp(pr["merged_at"]) <= now:
                    continue
                sha = pr["head"]["sha"]
                if not re.fullmatch(r"[0-9a-f]{40}", sha):
                    raise ValueError("invalid PR head SHA")
                row = merged_row(owner, repo, pr, enforced_since, registered)
                merged.append(pr)
                rows.append(row)
            if batch and timestamp(batch[-1]["updated_at"]) < cutoff:
                break
        for pr, row in zip(merged, rows):
            # Only investigate observed collateral closures, never turn a lone
            # bad merge into an ancestry search for some unrelated green PR.
            siblings = [p for p in merged if p["merge_commit_sha"] == pr["merge_commit_sha"]]
            if row["findings"] and len(siblings) > 1:
                binding = indirect_merge(owner, repo, pr, enforced_since, registered)
                if binding:
                    row["indirect_merge"] = binding | {"historical_findings": list(row["findings"])}
                    row["findings"] = []
            if row["findings"] or row["receipt"] or row.get("evidence_only") or row.get("indirect_merge"):
                results.append(row)
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
    parser.add_argument("--baseline", type=Path, default=ROOT / "accepted-history-20261103.json")
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
        frozen_at, accepted = baseline(args.baseline)
        rows = audit(args.owner, args.repos, now - timedelta(hours=args.hours),
                     exceptions(args.exceptions), now)
        # Apply only to merged history, before the open premerge candidate exists.
        for row in rows:
            entry = accepted.get((row["repo"], row["pr"], row["head"]))
            if (row["merged_at"] and entry and timestamp(row["merged_at"]) <= frozen_at
                    and set(row["findings"]) <= set(entry["findings"])):
                row["accepted_history"] = entry
        if args.premerge:
            rows.append(premerge(args.owner, args.premerge[0], int(args.premerge[1])))
        result = {"schema": 1, "complete": True, "findings": rows,
                  "accepted_history": sum(bool(r.get("accepted_history")) for r in rows),
                  "unregistered": sum(bool(r["findings"]) and r["exception"] is None
                                      and not r.get("accepted_history")
                                      for r in rows)}
    except RateFloorError:
        result = {"schema": 1, "complete": False, "error": "incomplete: rate-floor"}
    except (ValueError, OSError, KeyError, TypeError, OverflowError):
        # Never turn inaccessible private repositories or malformed evidence into green.
        result = {"schema": 1, "complete": False,
                  "error": "API/evidence/exception/baseline input unavailable or invalid; audit incomplete"}
    if args.format == "json":
        print(json.dumps(result, indent=2))
    elif not result["complete"]:
        print(result["error"])
    else:
        for row in result["findings"]:
            if row.get("indirect_merge"):
                binding = row["indirect_merge"]
                print(f'INDIRECT {row["url"]}: actual-source PR{binding["direct_pr"]} '
                      f'head={binding["direct_head"]} merge={binding["merge_sha"]}')
                print(f'  historical old-head findings (not passed): {", ".join(binding["historical_findings"])}')
                continue
            if row.get("accepted_history"):
                print(f'INFO accepted-history {row["url"]}: {", ".join(row["findings"])}')
                print(f'  {row["accepted_history"]["reason"]}')
                continue
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
