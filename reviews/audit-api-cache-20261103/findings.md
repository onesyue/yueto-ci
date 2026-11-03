# Merge hygiene API budget batch

Acceptance contract: cache completed remote merge findings by owner/repository,
pull request number and merge commit SHA. A warm merged-PR lookup must make zero
API calls. Revalidate local receipts, exceptions and enforcement on every audit.
Conditional GETs must reuse bodies only after HTTP 304; stop closed-PR pagination
at the effective cutoff without dropping recently updated older merges. Remaining
quota below 300 (configurable) must exit 2 with `incomplete: rate-floor`. Retries
must respect Retry-After/reset and be finite. Existing verdicts and exit codes
must remain unchanged. Run offline fixtures and repository tests, then sign,
push and open a PR to master with measured fixture counts; do not merge.

Checklist:
- Cache: implemented; cold merged-PR evidence uses four calls for yueto-ci,
  disk hit after module reload uses zero.
- Conditional requests and quota/backoff: implemented; offline 304, floor and
  bounded retry/reset controls pass.
- Pagination and unchanged verdicts: effective updated cutoff covered; baseline
  and candidate fixture verdicts compare equal.
- Tests and independent review: passed locally with one explicit unrelated skip;
  Linux acceptance remains UNKNOWN. Signed commit, push and PR: blocked by
  environment permissions/connectivity, with concrete publication handoff saved.
- Parked: existing Pyright diagnostics (possibly unbound `rows` in main; dynamic
  fixtures/imports in the existing tests). No unrelated cleanup planned.
  Reviewer also noted cache identity does not isolate Enterprise hosts; current
  scope is onesyue/github.com. Multi-host support remains outside this batch.

Lane ledger:
- Implementation `/root`: sole writer of scripts/merge-hygiene-audit.py,
  tests/test_merge_hygiene_audit.py, tests/test_merge_hygiene_cache.py,
  tests/test_merge_receipt_enforcement.py,
  tests/fixtures/merge-hygiene/approved.json, README.md and this review directory.
- Independent review `cache_review`: read-only review of the diff, cache trust
  boundary, quota/backoff, cutoff and verdict preservation. No file ownership.

Baseline: branch cx/audit-api-cache-1103b at 2c150a3, clean working tree. Existing
audit already stops after a page whose last updated_at predates the effective
cutoff. No existing batch evidence was found in this checkout. Docker access is
denied by the sandbox, so local Linux parity is not yet established.

DONE Independent read-only review by `/root/cache_review`: no blocking defects.
The reviewer checked cache completeness, local evidence revalidation, HTTP/304,
quota/backoff and cutoff behavior without repeating implementation tests.

DONE Fixture measurements (no network): see `call-counts.json` and reproduce with
`python3 reviews/audit-api-cache-20261103/measure-calls.py 2c150a3`.

| Fixture | Before, including rerun | After cold | After rerun | Rerun charged |
| --- | ---: | ---: | ---: | ---: |
| One yueops merge | 5 | 5 | 2 (304) | 0 |
| 100 yueops merges | 303 | 303 | 3 (304) | 0 |
| One yueto-ci merge | 6 | 6 | 2 (304) | 0 |
| 100 yueto-ci merges | 403 | 403 | 3 (304) | 0 |

Counts include activation lookup and PR list pages. The 100-merge fixture has a
full second page older than cutoff; both baseline and candidate stop there.
The baseline already implemented cutoff pagination, so no false savings are
attributed to that existing behavior. Every before/after result compares equal.

DONE Initial targeted validation: 51 merge-hygiene tests and 8 real-CLI receipt
tests passed. Compileall and diff whitespace check passed. Explicit Ruff
E4/E7/E9/F checks passed; this repository has no Ruff gate, and the workstation's
broader wrapper surfaced existing style rules rather than repository failures.
New cache tests have no Pyright diagnostics; script retains its preexisting one.

Initial full run: 664 tests in 365.444 seconds, 22 failures, 13 errors, 1 skip.
The discovery guard detected the new helper base class because it requires
direct unittest.TestCase inheritance. Replaced that base with an ordinary setup
helper, retaining the existing guard unchanged. The 51 hygiene tests and all
5 discovery controls then passed; independent review approved the correction.

The remaining failures were isolated to the test environment: fixture commits
inherited GPG signing and failed under sandbox; Go's default cache was not
writable (even `go list go/ast` failed until given a writable GOCACHE); macOS
`/sbin/sha256sum` lacks the GNU output expected by the CI checksum control.
The final full run uses a temporary Go cache, installed GNU coreutils first on
PATH and commit.gpgsign=false only in the test child environment. The repository
and user's signing configuration remain unchanged.

DONE Final full run: 664 tests in 631.055 seconds, exit 0, 663 passed, 1 skipped,
zero failures/errors. The skip is
`PRSharedInputTransitions.test_shared_input_source_objects_exist_when_source_available`
because the yueops source checkout is unavailable; it is not counted as passed.
The complete invocation, environment, source hashes and log reference are in
`verification.json`. The final log is `/tmp/ci-cache-repo-tests-final.log`.
Compileall, shell syntax, ShellCheck, actionlint and diff whitespace checks pass.
This macOS result does not establish the required Linux CI acceptance.

BLOCKED Publishing and Linux validation: Docker socket access is denied by
sandbox. GitHub access failed with `error connecting to api.github.com`. Git
staging failed creating the linked worktree index.lock outside writable roots
with `Operation not permitted`. No commit, push or PR was made. The PR body and
exact publication commands are saved in `pr-body.md` and `handoff.md`.
