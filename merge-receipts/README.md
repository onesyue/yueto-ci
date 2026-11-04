# Merge evidence receipts

Owner decision: 2026-11-02 15:36 SGT. Independent Codex approval and recorded
local CI parity replace human GitHub approval evidence for this audit. GitHub
branch rules still apply; receipts never erase red, pending or unknown checks.

Schema 1 uses exactly these fields (no extra fields at any level):

```json
{
  "schema": 1,
  "repo": "yueto-ci",
  "pr": 123,
  "head": "<merged PR head: 40 hex characters>",
  "backfilled": true,
  "review": {
    "tool": "codex",
    "verdict": "approve",
    "reviewed_head": "<same head>",
    "artifact": "reviews/merge-receipts-20261102/yueto-ci-123.md",
    "reviewer": "codex",
    "reviewed_at": "2026-11-02T08:00:00Z"
  },
  "parity": {
    "result": "pass",
    "head": "<same head>",
    "command": "<actual local test command>",
    "log_sha256": "<SHA256 of actual command-output log: 64 hex characters>",
    "ran_at": "2026-11-02T08:00:00Z",
    "runner": "box"
  }
}
```

Place receipts at `merge-receipts/<repo>/<pr>.json`. They must match their
committed HEAD version; new/modified uncommitted receipts fail closed. Artifacts
must match their committed HEAD version and be existing files inside this repository (absolute paths and traversal are
rejected). Reviewer identity must differ from the PR author, case-insensitively;
`codex` is allowed. Runners are `box`, `yueto-ci`, and `mac-5f08d00f`.
Both timestamps require a timezone and must be at most 24 hours after merge.
Post-merge execution requires `backfilled: true`; retrospective recording of
pre-merge evidence also uses true. This flag is always a JSON boolean.

The merged PR's **head** is used, not its merge commit. Receipt validation checks
structure and bindings; the committed review and its provenance must establish
that the review and logged command actually occurred. The log hash identifies
original bytes, not a reconstructed summary. Historical command transcripts are
retained at the source paths recorded in review artifacts; their copied reviews
retain scope, skips and environment limitations. A limited local test command is
not evidence that every hosted/release test ran.

Valid receipts remove only `no_approving_review_at_merge` and
`no_check_evidence_at_merge`. `RECEIPT` lines show the exact head, backfill flag,
and satisfied findings. Any remaining findings still produce their own
UNREGISTERED/REGISTERED line and retain the existing exit-code semantics.
Malformed or inaccessible receipts produce audit incomplete (exit 2), even if
an exception exists. After yueto-ci #71 merges, every PR merged strictly later
requires a valid receipt unless evidence-only (below); exceptions cannot waive any of its findings, including
red or pending checks. The activation PR and older PRs retain historical rules.
See the root README for the lane premerge command and companion evidence flow.
`--premerge <repo> <pr>` requires committed, non-backfilled evidence for the live
open PR head even before activation, except for evidence-only PRs.

An **evidence-only** PR in `yueto-ci` adds or modifies files exclusively under
`merge-receipts/` or `reviews/merge-receipts-*/`. These PRs stop the
receipt-of-receipt chain: both the audit and `--premerge` waive the receipt
requirement and only the missing approval/check-evidence findings. They still
need normal branch rules; red, pending and unknown checks remain findings.
Clean rows include `"evidence_only": true` and print as `EVIDENCE-ONLY`.
Mixed source/evidence PRs, removed or renamed files, and other repositories use
normal rules. File lists are paginated; API errors, lists of 3,000 or more files,
or a previous filename outside the allowed paths make the audit incomplete.

## Write or repair a receipt after merge

Use `scripts/write-merge-receipt.py` from this checkout to fetch the merged PR
from `onesyue` and bind the receipt to its actual `head.sha`:

```sh
python3 scripts/write-merge-receipt.py \
  --repo yueops --pr 75 \
  --review-artifact reviews/merge-receipts-20261102/yueops-75.md \
  --reviewed-head "$REVIEWED_HEAD" --reviewed-at "$REVIEWED_AT" \
  --parity-log reviews/merge-receipts-20261102/yueops-75.log \
  --parity-head "$PARITY_HEAD" --parity-command 'python3 -m pytest -q' \
  --ran-at "$RAN_AT" --runner box --verdict approve --result pass
```

Supply the actual evidence heads and timezone-bearing timestamps. If a master
merge-in changed the PR head, redo the review and parity at the merged head;
never relabel old evidence with the new SHA. The writer refuses unmerged PRs,
head mismatches, missing/outside-repository evidence files, and timestamps more
than 24 hours after merge. It hashes the parity log's original bytes and sets
`backfilled` when either evidence timestamp is after `merged_at`. The reviewer
defaults to `codex`; use `--reviewer` to specify another independent reviewer.

Use `--dry-run` to print the JSON without changing checkout files. Existing
receipts require `--replace`, which overwrites without creating a backup; the
previous committed version remains in git history. Before writing, the writer
runs the audit's `receipt()` validation against a temporary snapshot of the
proposed evidence. This checks the prospective contents, not git commitment:
commit the receipt and review artifact through the companion evidence flow
before running the normal audit, which still requires exact committed contents.
This post-merge writer does not replace the premerge gate described above.

## Automatic ancestor PR closure

GitHub can mark an open ancestor PR merged when a reviewed descendant is merged.
The old head's failed checks remain failed; do not fabricate a passing receipt
for that old head. The audit can classify an observed shared-merge ancestor as
`INDIRECT` only with a normal two-parent merge, a complete associated-PR lookup
identifying one direct PR at the second parent, the same repository/target and
valid direct-before-indirect merge timestamps. It must prove the old head is a
strict ancestor of the second parent and is not already in the first parent's
history. GitHub propagation can make the two timestamps differ.

The direct source receives the ordinary fresh as-of-merge review/check/status
and exact committed-receipt validation. Red, pending, unknown, late-only green,
missing or malformed evidence never transfers acceptance. Evidence-only and
accepted-history exceptions cannot certify this direct source. No recursive
inheritance is allowed. Missing/ambiguous API or ancestry proof and malformed
commit/parent evidence leave the audit incomplete. A well-formed merge with a
parent count other than two cannot receive indirect attribution: its ordinary
findings remain unchanged, including any existing exact accepted-history
classification. Unaccepted red findings still block. Premerge still checks the
actual proposed live head.

Machine and text output preserve the old findings as explicitly historical,
not-passed evidence alongside the direct PR, head, merge SHA and both timestamps.
Only immutable file-comparison cache entries are reused; no indirect verdict is
persisted or accepted without current authenticated evidence.
