# yueboard #115 review at e74f600f93d2c6382015dd2f34013b7ce2835dc9

You are an independent code reviewer for onesyue/yueboard PR #115 at exact head e74f600f93d2c6382015dd2f34013b7ce2835dc9. Review ONLY the change in 'git diff 305452a3f75f4854a49c175b5d54c16e8aaa6d3c e74f600f93d2c6382015dd2f34013b7ce2835dc9' (use git show/diff; do not modify anything). Look for correctness bugs, security problems, secret exposure, weakened tests, and regressions. Do not print any secret values. Final line must be exactly 'VERDICT: approve' or 'VERDICT: changes', preceded by concise bullet findings with file:line.
2026-11-03T12:18:05.734986Z ERROR codex_models_manager::manager: failed to refresh available models: request timed out
2026-11-03T12:18:05.788044Z ERROR rmcp::transport::worker: worker quit with fatal: Transport channel closed, when Client(HttpRequest(HttpRequest("http/request failed: error sending request for url (https://mcp.context7.com/mcp)")))
codex
I’ll read the repository guidance, then review only the specified commit range. I’ll keep all actions read-only and report findings without exposing secret values.

exec
/bin/zsh -lc 'cat CLAUDE.md ../AGENTS.md ../CLAUDE.md' in <path>
 succeeded in 0ms:
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
go test ./...
go test ./internal/modules/emby/...

Note: full vitest at this head has 1 failure (device-block-action "unblocking retains the existing HWID request format", 15s timeout); the same test fails on base master 305452a3 — pre-existing, not in this diff.
