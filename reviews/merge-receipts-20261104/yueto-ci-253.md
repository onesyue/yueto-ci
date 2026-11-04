# Final signed successor review

The current copied95-case log comes from `.claude/state/takeover/20261104/resume-1039/indirect-topology-linux-r2.log`. The original85-case copied log discussed in the retained3dd review is preserved in predecessor commit `a406ea97ea990f24f36023fa82e623dc5ccdfa70`, not in the current `.log` file.

Current head `be5755522508bb2ef0f7cba6661dd3c4937bf1a0` appends the independently reviewed topology correction to original3dd1557. Host and Linux complete merge-policy modules each passed95 cases with zero skips; compile and semantic diagnostics passed. The initial Linux tmpfs did not allow the CLI fixture executables; the unchanged source passed after using executable temporary storage, matching the normal CI fixture requirement. Original failures remain retained. The old single-parent historical rows160/161 retain their exact pending/history-unavailable findings and existing accepted-history handling. No baseline bytes changed, and new unaccepted red rows remain blocking. Original source review below establishes the parent; the new independent delta approval binds this signed successor. Fresh native merge audit remains required.

```json
{
  "verdict": "APPROVE",
  "reviewer": "root/link independent reviewer",
  "reviewed_at": "2026-11-04T05:39:58.753467+00:00",
  "base": "3dd15572ce00baafd4b6ba06f87a520d678b61c1",
  "scope": "Frozen unsupported-topology three-file delta only",
  "files": {
    "scripts/merge-hygiene-audit.py": "349543abfd4fd2167feeca75d747c710b720459d00ed1c144b34014216dba4be",
    "tests/test_merge_hygiene_indirect.py": "3a7edbb6a01cbc185d883724e2c5f487b90a4b741b98a7cd11d52f23cf9881bb",
    "merge-receipts/README.md": "db152b89f4a10ef0d6647da5e65f8e3f1606ee56741295e33c6e7de084c93fad"
  },
  "diff_sha256": "4689a834ab23daec447b8d00af68f5f1dada85209ccb3056a2695f914dc6566a",
  "findings": [],
  "checks": [
    "Exact commit identity, parents list, each valid SHA/object and uniqueness are validated before parent count. Malformed or duplicated parents still raise and CLI stays incomplete.",
    "Well-formed count other than2 returnsNone without modifying ordinary findings. Unregistered red and missing receipt remain blocking; no INDIRECT metadata is emitted.",
    "Existing exact accepted-history classification remains downstream and retains original pending/history-unavailable findings. No baseline edits, PR-number exceptions or new receipt exemption.",
    "Normal two-parent attribution and direct-source/premerge safety rules are unchanged. README accurately separates unsupported from malformed evidence.",
    "Regression exercises actual CLI main JSON/exit semantics: unsupported0/1/3 parents remaincomplete+unregistered1; exact accepted history retains findings; removing accepted mapping blocks; malformed/duplicate shapes remainincomplete exit2."
  ],
  "verification_reused": "Writer reports affected suite host95/Linux95 pass0skip and semantic diagnostics clear. Earlier Linux noexec temporary-filesystem failures retained and not counted as pass. No API audit or tests rerun by reviewer.",
  "signed_head": "be5755522508bb2ef0f7cba6661dd3c4937bf1a0",
  "signature": "G",
  "bound_at": "2026-11-04T05:41:33.162037+00:00",
  "binding": "Exact signed successor matches all three previously approved frozen file hashes; prior APPROVE retained, without test/API rerun. Prior3dd full-history unsupported-topology failures remain historical failed evidence."
}
```

## Retained original source review and evidence

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
