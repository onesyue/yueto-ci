# PR #71 backfill and forward receipt enforcement

All six previously absent targets received independent read-only Codex review
of the merged diff and an exact-head local yt-premerge attempt. No workflow was
dispatched and no PR was merged by this session.

| Target | Recorded result |
| --- | --- |
| yueops #263 | Exception: review approved; ordinary/native admission rejected the central source-pin mismatch. No override. |
| yueto #57 | Exception: review requested native-worktree cleanup changes; contracts and fast-check failed. |
| yueto #56 | Exception: review approved; contracts and fast-check failed. |
| yueto #52 | Exception: review found fail-open inventory handling and a lock/write race; contracts and fast-check failed. |
| yueto-ci #70 | Receipt: independent approval and passing exact-head yt-premerge policy suite, 589 tests. |
| yueto-ci #69 | Receipt: independent approval and passing exact-head yt-premerge policy suite, 595 tests. |
| yueops #262, yue-node #23, yuelink-ci #34 | Existing receipts preserved. |
| yueto #43 | Existing truthful exception preserved. |

The initial yueto-ci attempts failed using system Python without pytest. Both
retries used the already installed `/tmp/yci-venv/bin/python`; no dependencies
were installed. Original failed logs and successful retry logs remain adjacent
to the review artifacts. Raw log bytes, including whitespace, are preserved.
The root parity failures also include cross-repository contract failures and
non-default sibling checkouts; no baseline equivalence or whole-estate pass is
claimed. No unrelated repository source or admission pin was changed.

The forward policy activates at yueto-ci #71's actual GitHub merge timestamp.
Subsequent merges require receipts even if GitHub checks/reviews were green;
exceptions cannot waive their findings. The audit retains its post-activation
scan horizon, and the candidate premerge command requires committed,
non-backfilled evidence while preserving red/pending/unknown checks. README
explains companion evidence commits for yueto-ci to avoid a self-referential SHA.

Validation: branch policy suite 602 tests passed; final receipt-focused suite
30 tests passed; shell syntax, ShellCheck, Python syntax and source/doc whitespace
checks passed. Independent enforcement review approved after its stale premerge
timestamp finding was fixed and covered by real-CLI regressions. See
`enforcement-review.md` and its logs. The live 24-hour audit also exposed unrelated
historical unregistered PRs; this batch does not register or suppress those.
