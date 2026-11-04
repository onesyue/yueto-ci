# yueto-ci PR253 exact-source evidence

Head `3dd15572ce00baafd4b6ba06f87a520d678b61c1`. Original command-output log: `.claude/state/takeover/20261104/resume-1039/indirect-linux-tests.log`. The copied log retains original bytes. Independent source review and supplemental evidence follow. They do not imply publication or production acceptance.

```json
{
  "verdict": "APPROVE",
  "reviewer": "root/link independent reviewer",
  "reviewed_at": "2026-11-04T04:36:49.223055+00:00",
  "head": "3dd15572ce00baafd4b6ba06f87a520d678b61c1",
  "scope": [
    "scripts/merge-hygiene-audit.py",
    "tests/test_merge_hygiene_indirect.py",
    "merge-receipts/README.md"
  ],
  "file_sha256": {
    "scripts/merge-hygiene-audit.py": "04194fb649ae97335318609748f672a89a765ffd85e3d8edc597f7b83d60eb62",
    "tests/test_merge_hygiene_indirect.py": "c48daa26931d79d244d4657d94dc61f1f39b815c9a6992b732b5c5fcb7c9ceed",
    "merge-receipts/README.md": "905bfc1c5c91346a5e22cf088259cc9275be7aead356ac13eef207668b15b2f7"
  },
  "findings": [],
  "checks": [
    "Observed same-merge siblings trigger attribution only when the old row has findings; lone bad merges retain findings.",
    "Exactly two distinct valid parents and complete associated-PR pagination identify one direct second-parent head. No timestamp-window or commit-message selection.",
    "Old head must be a strict ancestor of second parent and absent from first-parent ancestry; compare identity, integer metadata (excluding booleans), status and merge-base consistency are checked.",
    "Repository, target branch, closed state and timezone-aware direct-before-indirect timestamps are validated. Missing or malformed API data fails closed through the normal incomplete path.",
    "Direct source uses ordinary fresh as-of-merge checks/reviews/statuses and exact committed receipt. No recursive attribution, evidence-only waiver or accepted-history transfer. Existing receipt semantics remain unchanged.",
    "Old red and missing receipt findings remain explicit historical not-passed evidence in JSON/text; direct red and premerge live-head failures remain blocking.",
    "Immutable comparison cache interpretation is unchanged; attribution verdict is recomputed from authenticated HTTP/ETag evidence."
  ],
  "test_evidence": "Writer reports affected suite host 85 passed / 0 skipped and Linux 85 passed / 0 skipped; reused without rerun. Negative tests reviewed for topology, ancestry, pagination/API failures, direct red/pending/late green, missing receipt, target/time mismatches, evidence-only, historical output and premerge.",
  "limitations": [
    "Source review is not a full-history audit or release authorization. Actual remote attribution readback remains coordinator-owned."
  ]
}
```

Original supplemental artifact: `.claude/state/takeover/20261104/resume-1039/indirect-live-248-proof-r2.json`

```json
{
  "scope": "actual API proof of indirect ancestor248; not a full historical merge audit",
  "old_head": "727f4068f98abaa528ceb67a391870b04887c6df",
  "historical_findings": [
    "check_nonpassing_at_merge:policy tests + workflow lint",
    "no_approving_review_at_merge",
    "required_merge_receipt_missing"
  ],
  "binding": {
    "direct_pr": 252,
    "direct_head": "f05a7b9e6a8039e86ca638cd333b63fe8932bd5c",
    "merge_sha": "05c6b56b7fba084129a7f2f933011c6041807c1a",
    "direct_merged_at": "2026-11-04T04:14:23Z",
    "indirect_merged_at": "2026-11-04T04:14:25Z",
    "direct_receipt_artifact": "reviews/merge-receipts-20261104/yueto-ci-252.md"
  }
}

```
