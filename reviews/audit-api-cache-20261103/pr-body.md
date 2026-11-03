Repeated merge-hygiene audits consumed the REST quota by downloading the same
historical evidence. The audit now uses ETag conditional GETs for every mutable
reviews/check-runs/statuses page and recomputes findings on each run. Only file
comparisons between fixed base/head commit SHAs are reused without HTTP requests.
This retains quota savings while detecting changed same-SHA evidence and failing
incomplete when revalidation fails. Version 2 ignores the original verdict cache.

Merged master 5a551afd3cd86dc0d783726253d6e2c81927e869 into this branch without
rebasing. PR #172's accepted-history SHA256, frozen_at boundary and receipt
requirements are preserved. Local receipts, exceptions, baseline and activation
remain current inputs; an open PR still revalidates evidence and ref identity.

Closed-PR pagination retains the updated-descending effective cutoff. Remaining
quota below 300 exits 2 with `incomplete: rate-floor`; the floor and cache path
are configurable. HTTP 403/429 retries honor Retry-After/reset with bounded
backoff. No cached response is served on authentication or transport failure.

Offline measurements against master using identical fixtures:

| Fixture | Before rerun | After cold | After rerun | Charged on rerun |
| --- | ---: | ---: | ---: | ---: |
| One yueops merged PR | 5 | 5 | 5 × 304 | 0 |
| 100 yueops merged PRs | 303 | 303 | 303 × 304 | 0 |
| One yueto-ci merged PR | 6 | 6 | 5 × 304 | 0 |
| 100 yueto-ci merged PRs | 403 | 403 | 303 × 304 | 0 |

Counts include activation and discovery. These are fixture results, not measured
live quota savings. See `reviews/audit-api-cache-20261103/call-counts-revalidated.json`
and reproduce with `python3 reviews/audit-api-cache-20261103/measure-calls.py`.
The earlier call-counts.json and verification.json record the superseded v1 batch.

Independent exact-head review found one P1: indefinite verdict reuse concealed a
changed check conclusion. The fix revalidates mutable pages and adds warm-cache
controls for changed checks/reviews/statuses, failed requests, rate-floor exit and
legacy v1 cache entries. All nine negative subcases failed before repair; the
74 affected tests passed after repair. The full pytest suite passed with 678
passed, 1 skipped (unavailable external yueops-src), and 5833 passing subtests.
Exact commands, hashes and final review evidence are recorded in `reviews/audit-api-cache-20261103/findings.md`.

No production deployment, master merge, rebase, force push or hook bypass.
