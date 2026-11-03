# Publish the merge-hygiene API cache change

Historical handoff, superseded by the PR #174 continuation in findings.md.
The branch is now published; v2 revalidates mutable evidence on every audit.

The user authorized implementation, tests, a signed commit, a branch push and a
pull request to master. Merging is explicitly forbidden. The local branch is
`cx/audit-api-cache-1103b` in `/Users/j/Projects/yueto-wt/ci-cache-1103b`.
Baseline HEAD is `2c150a3`; no commit or push has been made in this session.

Implementation and offline evidence are ready for continuation. Consult
`findings.md` for the full test result and remaining environment limitations.
The independent review approved the code and the subsequent discovery-compatible
test setup correction. Do not repeat the unchanged fixture
measurements or targeted tests unless the files change or evidence exceeds
24 hours. The full Linux CI gate is still required.

Local full-suite execution requires a writable GOCACHE and GNU coreutils ahead
of macOS utilities on PATH. Test fixture repositories must not inherit mandatory
GPG signing: the test launcher appends commit.gpgsign=false to GIT_CONFIG_COUNT
only for its child process. This is a fixture-environment adjustment; keep actual
candidate commits signed. The installed runtime is Python 3.13.15 with locked
pytest 9.1.1 and PyYAML 6.0.3. Go is locally 1.27.1; hosted CI pins 1.27.2.

This session cannot write the linked worktree's Git metadata outside its writable
roots: `git add` failed creating
`/Users/j/Projects/yueto/yueto-ci/.git/worktrees/ci-cache-1103b/index.lock`
with `Operation not permitted`. GitHub access failed connecting to api.github.com,
and Docker socket access was denied. There is no pending permission prompt.

From an environment with the required Git/network permissions, inspect the diff
and stage exactly these paths (including this review evidence):

```sh
git add README.md scripts/merge-hygiene-audit.py \
  tests/fixtures/merge-hygiene/approved.json \
  tests/test_merge_hygiene_audit.py tests/test_merge_hygiene_cache.py \
  tests/test_merge_receipt_enforcement.py \
  reviews/audit-api-cache-20261103/findings.md \
  reviews/audit-api-cache-20261103/call-counts.json \
  reviews/audit-api-cache-20261103/verification.json \
  reviews/audit-api-cache-20261103/measure-calls.py \
  reviews/audit-api-cache-20261103/pr-body.md \
  reviews/audit-api-cache-20261103/handoff.md
git diff --cached --stat
git commit -S -m "Cache merged PR audit evidence and protect the REST quota"
git push --set-upstream origin cx/audit-api-cache-1103b
gh pr create --repo onesyue/yueto-ci --base master \
  --head cx/audit-api-cache-1103b \
  --title "Cache merge-hygiene audits and protect the REST quota" \
  --body-file reviews/audit-api-cache-20261103/pr-body.md
```

Read back the pull request URL, exact head SHA and the Central policy CI result
on Ubuntu/Python 3.13. Record any remaining CI failure; do not claim Linux
acceptance from the macOS run or skipped tests. Do not merge.
