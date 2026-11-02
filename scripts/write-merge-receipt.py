#!/usr/bin/env python3
"""Write a receipt bound to the actual merged PR head (onesyue repositories)."""
import argparse
from datetime import timedelta
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def load_audit():
    spec = importlib.util.spec_from_file_location(
        "merge_hygiene_audit", Path(__file__).with_name("merge-hygiene-audit.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AUDIT = load_audit()


def evidence_path(value):
    path = Path(value)
    full = ROOT / path
    if (path.is_absolute() or ".." in path.parts
            or not full.resolve().is_relative_to(ROOT.resolve()) or not full.is_file()):
        raise ValueError("evidence path must be a repo-relative file inside repository")
    return full


def validate_candidate(repo, pr, value, contents, review):
    # The candidate cannot yet be in HEAD. Use a private module and temporary
    # snapshot for the audit's exact receipt checks, supplying prospective file
    # bytes at its committed_text I/O boundary. The real audit still requires
    # both files to be committed; no audit policy or shared module is changed.
    audit = load_audit()
    with tempfile.TemporaryDirectory(prefix="merge-receipt-validation-") as directory:
        audit.ROOT = Path(directory)
        candidate = audit.ROOT / "merge-receipts" / repo / f'{pr["number"]}.json'
        artifact = audit.ROOT / value["review"]["artifact"]
        if candidate == artifact:
            raise ValueError("review artifact cannot be the receipt itself")
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(review, encoding="utf-8")
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_text(contents, encoding="utf-8")
        audit.committed_text = lambda path: path.read_text(encoding="utf-8")
        if audit.receipt(repo, pr) != value:
            raise ValueError("audit rejected proposed receipt")


def write_receipt(args):
    pr = AUDIT.api(f"repos/onesyue/{args.repo}/pulls/{args.pr}")
    if pr["number"] != args.pr:
        raise ValueError("GitHub returned a different PR")
    if not pr.get("merged_at") or not pr.get("merged"):
        raise ValueError("PR is not merged; receipts require the actual merged head")
    head = pr["head"]["sha"]
    for label, provided in (("review", args.reviewed_head), ("parity", args.parity_head)):
        if provided != head:
            raise ValueError(f"{label} head differs from merged head {head}; "
                             f"{label} must be redone at the merged head, "
                             "e.g. after a master merge-in; never substitute heads")
    merged = AUDIT.timestamp(pr["merged_at"])
    moments = [AUDIT.timestamp(args.reviewed_at), AUDIT.timestamp(args.ran_at)]
    if any(moment > merged + timedelta(hours=24) for moment in moments):
        raise ValueError("review/parity timestamp is more than 24h after merged_at")
    artifact = evidence_path(args.review_artifact)
    log = evidence_path(args.parity_log)
    destination = ROOT / "merge-receipts" / args.repo / f"{args.pr}.json"
    if (destination.is_symlink()
            or not destination.resolve().is_relative_to(ROOT.resolve())):
        raise ValueError("receipt destination must be inside repository and not a symlink")
    if destination.exists() and not args.replace:
        raise ValueError("receipt already exists; use --replace to overwrite")
    value = {
        "schema": 1, "repo": args.repo, "pr": args.pr, "head": head,
        "backfilled": any(moment > merged for moment in moments),
        "review": {"tool": "codex", "verdict": args.verdict,
                   "reviewed_head": args.reviewed_head,
                   "artifact": Path(args.review_artifact).as_posix(),
                   "reviewer": args.reviewer, "reviewed_at": args.reviewed_at},
        "parity": {"result": args.result, "head": args.parity_head,
                   "command": args.parity_command,
                   "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
                   "ran_at": args.ran_at, "runner": args.runner},
    }
    contents = json.dumps(value, indent=2) + "\n"
    validate_candidate(args.repo, pr, value, contents, artifact.read_text(encoding="utf-8"))
    if args.dry_run:
        print(contents, end="")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation also protects against a receipt appearing during validation.
        with destination.open("w" if args.replace else "x", encoding="utf-8") as output:
            output.write(contents)
        print(destination.relative_to(ROOT).as_posix())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, choices=AUDIT.REPOS)
    parser.add_argument("--pr", required=True, type=int)
    for flag in ("review-artifact", "reviewed-head", "reviewed-at", "parity-log",
                 "parity-head", "parity-command", "ran-at"):
        parser.add_argument("--" + flag, required=True)
    parser.add_argument("--runner", required=True, choices=("box", "yueto-ci", "mac-5f08d00f"))
    parser.add_argument("--reviewer", default="codex")
    parser.add_argument("--verdict", required=True, choices=("approve",))
    parser.add_argument("--result", required=True, choices=("pass",))
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.pr <= 0:
        parser.error("--pr must be positive")
    try:
        write_receipt(args)
    except ValueError as error:
        print(f"Cannot write receipt: {error}", file=sys.stderr)
        return 2
    except (OSError, KeyError, TypeError):
        # Do not print API payloads or subprocess diagnostics.
        print("Cannot write receipt: API response or evidence files unavailable/invalid",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
