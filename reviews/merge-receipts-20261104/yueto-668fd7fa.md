# Independent review: yueto direct commit 668fd7fa

Reviewer: codex (RC1104 review-root lane; not the change author).
Reviewed at: 2026-11-04T12:42:44Z
Head: 668fd7fad2ad391962e9847c6ac24e2ccf2fc3cf
First parent: 8944e7065f5ff1b5bc5aa9cf8dc87f07b78ed697
Comparison: exact head against its first parent in a detached worktree.
Context supplied by coordinator: PR #105 content was cherry-picked by direct push, not merged as that PR.

VERDICT: approve

This approval is limited to the two added documentation files and does not approve an executable database migration, establish complete feature removal, or establish a merged PR. Receipt admission is BLOCKED by failed local parity and absence of merged-PR admission for this direct commit.

The inventory describes search matches as candidates rather than dead-code proof, records unverified external component work, preserves shared memories and institution-email consumers, and expressly leaves existing settlements, rewards, exits and appeals unresolved. The SQL draft is not under a migration runner and all 20 lines are comments. Its five proposed tables are ordered with dependent grant/review/reward/member tables before events, omit CASCADE, and require a new reviewed component migration before execution. It neither queries a database nor performs deletion. No executable application, schema or release input changes occur in this diff.

External inventory counts and claimed production retirement were not independently remeasured. Approval concerns the bounded, non-executable draft and its explicit limitations; it does not certify that any future drop would be safe. The inventory contains workstation locations in the source document; these are deliberately not reproduced here.

## Local parity

The exact-head README delegates to documented checks for the changed component. The two document-guard self-test modules were run using the documented workspace Python entry. `python` in the sanitized log denotes the preinstalled workspace virtual-environment interpreter. This is not the full release gate or a database integration test.

- Runner: mac-5f08d00f (Mac).
- Start: 2026-11-04T12:41:02Z.
- End: 2026-11-04T12:41:09Z.
- `bash scripts/status-all.sh`: rc 1, detached/default-branch comparison UNKNOWN.
- `git diff --check HEAD^ HEAD`: rc 0.
- `python -m pytest -q --tb=no --show-capture=no scripts/test-root-doc-truth.py scripts/test-doc-path-truth.py`: rc 1; 22 failed, 72 passed, 5 skipped.
- Log: `parity-logs/20261104/yueto-668fd7fa.log`.

The detached root lacks independent component checkouts, which some path checks require. The full failure set is not proven exclusively environmental or pre-existing. Failures and skips are preserved rather than called passing parity. Tracebacks and captured output were disabled at invocation; retained output transparently redacts internal absolute paths and IP addresses.
