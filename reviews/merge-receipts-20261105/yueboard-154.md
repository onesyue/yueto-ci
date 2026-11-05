# yueboard #154 review at 5c672a97d119fde7ab1baa45355d88d01655d770

VERDICT: approve   (or VERDICT: changes)
followed by concise bullet findings.
codex
I’ll review the exact diff, trace callers of the removed functions, and check for weakened tests or integration compilation issues without modifying files.
exec
/bin/zsh -lc 'pwd; git status --short; git rev-parse origin/master; git rev-parse 5c672a97d119fde7ab1baa45355d88d01655d770; cat CLAUDE.md' in /Users/j/codex-runs/1104d/yb-lint
 succeeded in 5ms:
/Users/j/codex-runs/1104d/yb-lint
error: fsmonitor_ipc__send_query: unspecified error on '/Users/j/Projects/yueto/yueboard/.git/worktrees/yb-lint/fsmonitor--daemon.ipc'
92e0b56c2be1524a64ee7a5cd5e654e53821e311
5c672a97d119fde7ab1baa45355d88d01655d770
# CLAUDE.md

Guidance for engineering agents working in `onesyue/yueboard`, an independent
repository in the Yue.to workspace. Read `../CLAUDE.md` for workspace rules.
Commit and push this repository separately.

## Purpose and compatibility

**Native Go control plane for Yue.to.** The strangler rewrite originated from
Xboard, but production Xboard was retired on 2026-07-23. There is no PHP process,
container or fallback. PostgreSQL uses native names such as `users`, `orders`,
`plugins` and `settings`. Released clients retain the compatible HTTP wire
contract in `docs/api-contract.md`.

1. **Preserve client contracts.** The v1 envelope remains
   `{status,message,data,error}` through `internal/platform/apiresp` where that
   contract applies. Authentication rejection must be HTTP 403 with non-HTML
   JSON: clients use non-HTML 401/403 responses to detect logout. Check the
   contract's endpoint-specific exceptions before changing responses.
2. **Never restore the retired panel fallback.** `internal/platform/fallback`
   was deleted and legacy fallback environment variables are unsupported.
   Unmatched routes use the anti-GFW decoy/404 behavior. Implement missing
   business endpoints natively with contract coverage.

## Commands

```sh
go run ./cmd/yueboard          # :8080; health-only mode without DATABASE_URL
go build ./... && go vet ./...
