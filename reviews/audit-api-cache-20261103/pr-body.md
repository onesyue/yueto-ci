Repeated merge-hygiene audits refetched reviews, check runs, statuses and (for
yueto-ci) comparisons for every historical merged pull request, exhausting the
onesyue REST quota. Cache complete remote findings by owner/repo, PR number and
merge commit SHA so a previously audited merge makes zero evidence requests.
Receipts, exception registrations and activation enforcement remain live checks.

GETs now persist ETags and response bodies and send If-None-Match on reruns.
Closed-PR pagination retains the existing updated-descending effective cutoff,
with regression tests for recently updated older merges and activation bounds.
Remaining quota below 300 exits 2 with `incomplete: rate-floor`; the floor and
cache directory are configurable through `MERGE_HYGIENE_RATE_FLOOR` and
`MERGE_HYGIENE_CACHE_DIR`. HTTP 403/429 retries honor Retry-After/reset, use bounded
backoff and never expose HTTP/credential diagnostics. Existing verdicts and
0/1/2 exit semantics are preserved.

Measured offline against baseline `2c150a3` using identical fixtures:

| Fixture | Before rerun | After cold | After rerun | Charged on rerun |
| --- | ---: | ---: | ---: | ---: |
| One yueops merged PR | 5 | 5 | 2 × 304 | 0 |
| 100 yueops merged PRs | 303 | 303 | 3 × 304 | 0 |
| One yueto-ci merged PR | 6 | 6 | 2 × 304 | 0 |
| 100 yueto-ci merged PRs | 403 | 403 | 3 × 304 | 0 |

Counts include policy-anchor lookup and PR discovery. All fixture verdicts match
baseline; these are measured fixture request counts, not live quota claims.
Evidence and reproduction: `reviews/audit-api-cache-20261103/call-counts.json`
and `measure-calls.py`. A separate test reloads the module from disk and asserts
that a cached merged PR makes zero API/subprocess calls.

Validation: 51 merge-hygiene unit tests and 8 real-CLI receipt tests passed;
compileall, shell syntax, ShellCheck, actionlint and explicit Ruff E4/E7/E9/F
checks passed. Independent read-only review found no blocking issues.
Full repository suite: 664 tests, 663 passed and 1 skipped (the yueops sibling
source checkout is unavailable), with no failures/errors. Test fixtures use an
isolated writable Go cache, installed GNU coreutils and child-only Git signing
override; candidate commits still require signing. Evidence and publishing
limitations are recorded in `reviews/audit-api-cache-20261103/findings.md` and
`verification.json`. Linux CI remains required because this session cannot
access Docker. Do not merge as part of this task.

The immutable cache preserves the first complete remote snapshot for each merge.
Removing the cache forces a refresh; a cache version bump invalidates entries
when interpretation changes. No live repositories or production were modified.
