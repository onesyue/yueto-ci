# Independent review: yueto #104

Reviewer: codex (RC1104 review-root lane; not the change author).
Reviewed at: 2026-11-04T12:42:44Z
Head: 8944e7065f5ff1b5bc5aa9cf8dc87f07b78ed697
First parent: a7f9198b3ca2c4b2bd1791ff9ed449925b5b63bc
Comparison: exact head against its first parent in a detached worktree.

VERDICT: approve

This approval is limited to the documentation diff. Receipt admission is BLOCKED by failed local parity.

The change removes eight historical documents, records their immutable recovery revision and SHA-256 values, records retained documents, updates historical citations, and replaces personal attribution in an existing plan. No executable source, migration, guard, release input or runtime configuration changes.

Independent checks verified that the removal manifest covers exactly all eight deletions, that every recorded SHA-256 matches the blob recovered from the recorded parent revision, and that every retained manifest path exists at the head. The three handoffs explicitly carry supersession notices. Historical narrative removal does not establish that its old obligations are complete. The archive documentation preserves that distinction and the Git recovery path. Existing archive policy assertions and both operational-document guard scan lists were examined; the deleted reports are outside those explicit lists. No references to the eight removed basenames were found in tracked scripts or hook files. No surviving relative Markdown citation to those deleted files was identified in the scoped citation scan.

The local external archive's existence or bytes were not independently verified; Git blob recovery was verified instead. External component consumers and production behavior were not tested. Historical reports were assessed for recovery and supersession, not re-audited as current production truth.

Nonblocking formatting concern: both new CSV manifests use CRLF, and the actual `git diff --check HEAD^ HEAD` returns 2 with trailing-whitespace diagnostics. This is not reported as clean formatting.

## Local parity

The exact-head README delegates to documented checks for the changed component. Documentation changes were checked with the workspace's documented Python test entry and the two relevant document-guard self-test modules; this is not the complete release gate. `python` in the sanitized log denotes the preinstalled workspace virtual-environment interpreter.

- Runner: mac-5f08d00f (Mac).
- Start: 2026-11-04T12:40:48Z.
- End: 2026-11-04T12:41:02Z.
- `bash scripts/status-all.sh`: rc 1, detached/default-branch comparison UNKNOWN.
- `git diff --check HEAD^ HEAD`: rc 2.
- `python -m pytest -q --tb=no --show-capture=no scripts/test-root-doc-truth.py scripts/test-doc-path-truth.py`: rc 1; 22 failed, 72 passed, 5 skipped.
- Log: `parity-logs/20261104/yueto-104.log`.

The detached root does not include independent component checkouts. Some path checks require those components. The full failure set has not been established as pre-existing or exclusively environmental; the actual failure remains a failure. Skips are not passes. Tracebacks and captured output were disabled at invocation; the retained command output transparently redacts internal absolute paths and IP addresses. No passing receipt is justified by this run.
