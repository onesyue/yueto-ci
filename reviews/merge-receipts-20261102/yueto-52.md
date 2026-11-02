# Independent Codex review — yueto #52

- Reviewer: codex, independent read-only agent `/root/review_yueto`
- Reviewed at: 2026-11-02T09:11:50Z
- Head: `a64adbb3905b70a2e56e31f2c0e42f868e78bbaa`
- Comparison base: `da5b238560c9ec7eacd786ca3a6dc2b5058f593d`
- Verdict: **CHANGES**

P2 — scripts/release-yaml.py:1381–1384 returns empty locks for an existing non-directory LOCK_DIR and uses load_locks() without strict=True. That reader can suppress unreadable/non-directory inventory failures, allowing a ledger write; the outer exception handler cannot catch a suppressed error. Use strict inventory enumeration and a subprocess negative control.

P2 — scripts/release-yaml.py:1468–1481 checks foreign locks before entering the separate ledger_transaction. A release can acquire .inventory.lock after the snapshot and before the ledger modification, since release acquisition does not use release-yaml.lock. Serialize inventory observation and ledger mutation; add a concurrency interleaving test. Reviewed historical release-yaml/release-lock inventory and ledger transactions, new tests and contract registration. Existing tests cover already-present foreign locks, not observation failure or concurrent acquisition.

Read-only source review using historical Git objects; reviewer made no edits, ran no suites, dispatched no workflows and performed no deployments. Parent session records parity separately below. Approval is scoped to the diff and is not parity evidence.

## Local parity

Ran at 2026-11-02T09:18:05.596872+00:00. Command: `YT_PAR=2 PYTHONDONTWRITEBYTECODE=1 YUETO_ROOT=/home/box/Projects/yueto /home/box/Projects/yueto/scripts/yt-premerge yueto a64adbb3905b70a2e56e31f2c0e42f868e78bbaa`. Independent Codex requested changes: non-strict lock inventory enumeration can fail open, and the lock check/ledger write is not atomic with release acquisition. Exact-head yt-premerge exited 1: contracts and fast-check failed, including missing pytest and cross-repository contract mismatches. No approval or passing parity is claimed. Original log `yueto-52.log` SHA256 `bc5ed78fce33c372e7ebd642649c737b0ec1815c2bb9a7290ee8f7555be0fd5f`; stage logs are adjacent. Main sibling checkouts are not all on default branches, so no baseline equivalence is claimed. Temporary checkout and logs removed after copying evidence.
