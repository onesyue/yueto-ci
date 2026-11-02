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
