# Merge hygiene API budget batch

The original batch below records v1 behavior. The PR #174 continuation at the
end supersedes its zero-call verdict-cache contract with mandatory ETag
revalidation of mutable remote evidence. Historical measurements remain intact.

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

## PR #174 merge and exact-head review — 2026-11-03

Acceptance contract: merge origin/master (5a551af) into cx/audit-api-cache-1103b,
without rebasing or force pushing; preserve PR #172 accepted-history SHA256,
frozen_at and receipt enforcement plus cache/ETag/rate-floor behavior. Run the
full pytest suite, compile/lint checks and Linux policy CI. Sign commits using
normal hooks and push normally. Review the entire final PR diff against master;
resolve fixable P1 findings and repeat tests/review on the changed candidate.
Write ../review-174.txt ending in a verdict bound to the full pushed HEAD SHA.
No production deployment is part of this task. Rollback is a signed follow-up
revert; existing published history is preserved.

Checklist:
- Merge integration: sole conflict is the import/constants/helper section of
  scripts/merge-hygiene-audit.py; retain both sides.
- Verification and publication: pending full pytest and CI at merged candidate.
- Exact-head review: pending published candidate, including stale-cache risks.
- Parked: retain the existing out-of-scope findings above.

Lane ledger for this continuation:
- Integration /root: sole writer of source, tests and this findings record.
- Exact-head review: reserve one independent read-only lane after publication;
  owns only ../review-174.txt. No duplicate source investigation.

DONE Merge integration: preserved both conflict sides. AST comparison confirms
baseline, receipt, enforcement_cutoff and premerge are identical to master.
Accepted-history JSON and exception registry are also identical to master.

DONE Full pytest at merged working tree: 675 passed, 1 skipped, 5824 subtests
passed in 582.88 seconds. Invocation: PATH with GNU coreutils first, TZ=UTC,
test-child-only commit.gpgsign=false, heavy-run.sh python3 -m pytest -q -ra
--junitxml=../pytest-174-merge.xml. Log: ../pytest-174-merge.log. The skip requires
the absent yueops-src checkout; it is not a pass. Compileall, bash syntax,
ShellCheck, actionlint and git diff --check passed. Saved script diagnostics: {}.

DONE_WITH_CONCERNS Linux container validation did not reach tests: the existing
requirements-policy.txt pins an amd64 PyYAML wheel hash, incompatible with the
ARM64 Docker wheel. Log: ../linux-174-merge.log. No dependency policy was changed;
await the native amd64 Central policy CI on the pushed merge commit.

P1 repair acceptance: the independent reviewer reproduced stale green at
f861271e1d36533a6baeb4a3aa7b29bad375c83b (../review-174-repro.txt). A check-run
conclusion changed under unchanged merge/PR metadata; the warm audit omitted it.
Reviews/checks/statuses are mutable, so final verdicts must be recomputed after
every page is revalidated by HTTP/ETag. Cache only immutable compare results,
ignore all v1 entries, preserve fail-closed quota/API paths and local baseline/
receipt checks. This supersedes the original zero-call merged-verdict contract
to satisfy the owner's explicit no-stale-false-green requirement.

Blast radius: CACHE_VERSION/merged_findings consumers are the audit script,
cache tests, measurement fixture and README/PR description; no consumers were
found in workspace scripts/docs/skills. Preserve historical review evidence.
Independent review lane: /root/exact_head_review, read-only repository access;
report ownership ../review-174.txt, reproduction ../review-174-repro.txt.

DONE Red regression at old implementation: all 9 mutable-evidence/failure
subcases failed as expected (../pytest-174-regression-red.log). After repair,
74 related tests and 186 subtests passed (../pytest-174-targeted.log). Controls
cover changed checks, dismissed reviews, changed statuses, legacy v1 green
entries, and warm 401/500/rate-floor failures in JSON/text. ETags in fixtures now
reflect response content instead of a constant validator.

DONE Revised request measurements against master 5a551af are saved in
call-counts-revalidated.json, produced by measure-calls.py. Warm one/100-merge
audits make 5/303 conditional requests for both repos and zero charged fixture
requests. Immutable comparisons save one request per yueto-ci merged PR.

DONE Saved-file Pyright diagnostics are empty for the changed audit script and
cache tests. Compileall, explicit Ruff E4/E7/E9/F and diff whitespace checks pass.
The original merged candidate is MERGEABLE; its Central policy CI run is
https://github.com/onesyue/yueto-ci/actions/runs/41571629123. A new full pytest run
is in progress for the P1 repair; final review will use its signed pushed HEAD.

DONE Linux acceptance for merge candidate f861271: Central policy CI completed
successfully at https://github.com/onesyue/yueto-ci/actions/runs/41571629123.
The redundant local amd64 setup container ci174-amd64 was stopped and removed;
its pending prerequisite is now owned by final-head hosted Linux CI after the
P1 repair push. Setup log: ../linux-174-amd64-setup.log. No container result is
reported as a passed test. Full final-head local pytest remains running.

DONE Final repair full pytest: 678 passed, 1 skipped, 5833 subtests passed in
410.72 seconds, exit 0. Log ../pytest-174-final.log; exact invocation and source
hashes are in verification-final.json. The skipped external-source check remains
unverified. No source/test/measurement bytes changed during the full run.

Master advanced during validation to e05012e with receipts/review artifacts only;
the original requested master merge at 5a551af is retained. Final PR review uses
the current master ref and records the actual merge base, with no repeated
source testing for unchanged audit code. Signed repair publication and final
exact-head review/hosted CI follow this receipt.
