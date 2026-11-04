# Independent exact-head review: yueboard 135

Reviewer: codex (RC1104 independent review lane).
Reviewed at: 2026-11-04T12:43:12Z
Head: 5ecbd23e84563dcaa01e2d82c569cd1e22027648
First parent: ba838b22bc7dc80190662855eb6439bc8b28c73c
Comparison: first parent to exact head in a detached worktree.

VERDICT: approve

Reviewed both changed files against the first parent and traced completeProvisioning, resolveAccountLocked, embyEntitledLocked, the feature flag and the existing pending-credential restore flow. Recovery is restricted to a disabled-account rejection, checks present entitlement, enables the durable bound Emby ID and retries authentication once. The existing server/account identity validation and conditional binding update remain in place. The new stateful transport test covers entitled, expired, banned, missing-plan and feature-disabled cases. No blocking defect found in this diff.

Limitations: The full local test run is required separately. This review does not assert live Emby behavior or production authentication acceptance.

Parity evidence: `parity-logs/20261104/yueboard-135.log`. Runner: mac-5f08d00f. Actual command: `go vet ./... && YUEBOARD_CONTRACT_BASELINE=ba838b22bc7dc80190662855eb6439bc8b28c73c go test ./...`. Started: 2026-11-04T12:40:26Z; finished: 2026-11-04T12:41:52Z; exit code: 1. `go vet` succeeded and the full `go test` command ran; tests requiring local listeners failed because the sandbox prohibits socket binding. Parity is FAIL, not pass. The log also retains the earlier toolchain-download failure; the retry used the installed pinned Go 1.27.3 and existing module cache with a writable build cache. No test scope was removed. Local path and IP literals are redacted; output semantics and exit status are preserved. No receipt is eligible from this result.
