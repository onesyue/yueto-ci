# yueto-ci #179 — INCIDENT receipt (missing premerge receipt / P1 window)

INCIDENT: the owner identified this merge as occurring without a prior receipt
during the P1 window. This retrospective record uses the exception format of
`0c470b566a9cd3e7c3d3435efed1959989b50ee2` (yueops #298).
PARITY: NOT pass. Independent exact-head approval remains missing.

## Merge facts and provenance

- PR: https://github.com/onesyue/yueto-ci/pull/179
- Title: merge-hygiene-audit: cut GitHub REST usage (cache/ETag/cutoff/rate floor).
- State: merged into `master` from `cx/audit-api-cache-1103c` by `cursor[bot]`;
  confirmed on the GitHub PR page on 2026-11-03.
- Head: `bd051adae75a3f924b2cb9faae5b933c1aa66283`, the merge's second parent.
- Merge: `9b318b9f51200c0f1d384218ae8d2fc13d6cf2fb`.
- First parent: `5067bfd5151ccb8c457109d0da3e30f3372798ff`.
- Merge event: `2026-11-03T04:18:34Z`, supplied by the owner. The local merge
  object's committer timestamp is `2026-11-03T04:18:33Z`; these are different
  timestamps, and the latter is not substituted for GitHub's merge event.
- `git ls-tree 9b318b9f51200c0f1d384218ae8d2fc13d6cf2fb^1 --
  merge-receipts/yueto-ci/179.json` returns no entry. The receipt is also absent
  at this checkout's base `0c470b566a9cd3e7c3d3435efed1959989b50ee2`.

The requested API collection was attempted with:

```sh
gh pr view 179 --repo onesyue/yueto-ci --json number,url,title,state,headRefOid,baseRefName,baseRefOid,mergeCommit,mergedAt,mergedBy,statusCheckRollup,commits
```

It failed with `error connecting to api.github.com`; no JSON was obtained.
The public GitHub PR and Actions pages were read as a fallback, and commit
identities were checked against local Git objects. This is not a successful
`gh pr view` capture. Exact API timestamps and complete check/review history
remain UNKNOWN; API readback is outstanding for the coordinator. Rechecking
this command on 2026-11-03 produced the same connection error. The public REST
endpoint was also unavailable through the web reader; no API response is
represented as successfully collected.

## Checks observed

The [PR checks page](https://github.com/onesyue/yueto-ci/pull/179/checks) binds
`Central policy CI` to `bd051ad`. The
[workflow run](https://github.com/onesyue/yueto-ci/actions/runs/41574191513)
reports Success, triggered by the pull request on 2026-11-03 at 03:46, with a
total duration of 5m 41s. Its
[policy tests + workflow lint job](https://github.com/onesyue/yueto-ci/actions/runs/41574191513/job/125713789646)
reports success and a duration of 5m 37s. The PR merge timeline reports one
passed check. No precise `startedAt`/`completedAt` values or authenticated job
logs were obtained, so no complete merge-time check-history verdict is claimed.
Hosted success does not supply the missing independent review or local parity.

## Withdrawn evidence and remaining obligations

[PR #180](https://github.com/onesyue/yueto-ci/pull/180) is still open as observed
on 2026-11-03. Its withdrawal commit
`690bb67023513071de1189936c7d63a13031bae6` removes the attempted pass receipt.
The withdrawal artifact is available with:

```sh
git show 690bb67023513071de1189936c7d63a13031bae6:reviews/merge-receipts-20261103/receipts-179-68-withdrawn.md
```

It records a verdict for `7fb302a6627e413fb4bed5c968f9f8fe5bd526f3`, not the
merged head, and prose in place of a parity command transcript. The claimed
runner `mac+linux` is also outside the allowed runner set. The attempted receipt
and its withdrawal are not ancestors of this checkout's base. Their recorded
tree equivalence does not establish an exact-head review or parity run.

Still required for a passing receipt: an independent approval naming
`bd051adae75a3f924b2cb9faae5b933c1aa66283`, an actual passing local parity log
from an accepted runner at that head, and compliant evidence timestamps.
No review verdict, runner, test timestamp or log hash is relabeled here.

## Schema and validation scope

Receipt schema 1 requires exactly `schema repo pr head review parity backfilled`
and permits only `review.verdict: approve` and `parity.result: pass`. It has no
incident field. The exception schema permits exactly `repo pr reason approver`;
the `reason` carries the `INCIDENT` marker, matching #298's location and naming.
No schema, validator, test or accepted-history snapshot is changed, and no
`merge-receipts/yueto-ci/179.json` pass receipt is created.

This registration documents the incident under the owner's explicit request.
The existing post-activation enforcement continues to reject a missing required
receipt; an exception cannot waive that finding. Receipt-validation tests below
validate this documentation change, not the source PR's local parity.

Validation on 2026-11-03:

- `python3 -m unittest discover -s tests -p 'test_*merge*.py' -v`: 86 tests
  passed in 3.821s, no skips, exit 0. This covers the audit, cache, receipt
  enforcement and writer. Original output: `/tmp/receipt-179-validation.log`.
  Reused within 24 hours: the validator and test sources are unchanged.
  Log SHA256: `6d6d521c8ea093224859ba87eb40aaf778e531f4b2efd64b03e53733c7589a50`.
- The existing `exceptions()` validator accepted the updated registry. Its
  previous entries are unchanged; only the #179 incident entry was appended.
  The JSON matches the repository's two-space format, and `receipt()` still
  returns no passing receipt for #179.
- `git diff --check` passed. The added evidence passed checks for IPv4 addresses,
  common credential/private-key patterns, and URLs containing queries or userinfo.
  Current registry and format validation output:
  `/tmp/receipt-179-incident-validation.log`.
- GitHub API readback remains outstanding. These offline checks do not resolve
  the missing exact-head approval/parity or establish a green live audit.

## API readback (coordinator, 2026-11-03 ~13:45 SGT)

`gh pr view 179 --json headRefOid,mergeCommit,statusCheckRollup` succeeded outside
the sandbox: head `bd051adae75a3f924b2cb9faae5b933c1aa66283`, merge
`9b318b9f51200c0f1d384218ae8d2fc13d6cf2fb`, checks: `policy tests + workflow lint`
= SUCCESS. Matches the facts above. Independent exact-head approval and local
parity remain missing (PARITY: NOT pass).
