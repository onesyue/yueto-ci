# yueboard #114 review at 453999bb25b8e37c4c1bbcdf7d85dd15a57bca09

You are an independent code reviewer for onesyue/yueboard PR #114 at exact head 453999bb25b8e37c4c1bbcdf7d85dd15a57bca09. Review ONLY the change in 'git diff 99e2bd65619df9ef42b69383855617bf0f8f83e8 453999bb25b8e37c4c1bbcdf7d85dd15a57bca09' (use git show/diff; do not modify anything). Look for correctness bugs, security problems, secret exposure, weakened tests, and regressions. Do not print any secret values. Final line must be exactly 'VERDICT: approve' or 'VERDICT: changes', preceded by concise bullet findings with file:line.
2026-11-03T12:18:01.702317Z ERROR codex_models_manager::manager: failed to refresh available models: request timed out
2026-11-03T12:18:03.787335Z ERROR codex_api::endpoint::responses_websocket: failed to connect to Responses WebSocket stage=Unknown
codex
I’ll read the repository’s review rules, then inspect only the specified commit diff and the context needed to assess it. I’ll keep the review read-only and avoid printing secret values.

exec
/bin/zsh -lc 'pwd; git status --short; git rev-parse --show-toplevel; git cat-file -t 453999bb25b8e37c4c1bbcdf7d85dd15a57bca09; git diff --stat 99e2bd65619df9ef42b69383855617bf0f8f83e8 453999bb25b8e37c4c1bbcdf7d85dd15a57bca09' in <path>
 succeeded in 0ms:
<path>
error: fsmonitor_ipc__send_query: unspecified error on '.git/fsmonitor--daemon.ipc'
<path>
commit
 cmd/yueboard/main.go                               |   2 +
 contracts/openapi/yueboard-api.v1.json             |  58 +++++
 internal/modules/admin/admin_test.go               |   2 +-
 internal/modules/admin/audit.go                    |   1 +
 internal/modules/admin/audit_auto.go               |   1 +
 internal/modules/admin/user.go                     |   1 +
 internal/modules/admin/user_unban.go               | 114 +++++++++
 internal/modules/admin/user_unban_test.go          |  68 ++++++
 internal/modules/bannedprotect/decide.go           |   3 +-
 internal/modules/bannedprotect/decide_test.go      |   8 +-
 internal/modules/bannedprotect/filter_test.go      |   6 +
 internal/modules/nodesync/builders.go              |   6 +
 internal/modules/nodesync/internal.go              |   1 +
 internal/modules/nodesync/yueops_internal_unban.go | 132 +++++++++++
 .../modules/nodesync/yueops_internal_unban_test.go | 196 +++++++++++++++
 internal/modules/nodesync/yueops_scope.go          |   1 +
 internal/platform/apiresp/problem_test.go          |   2 +
 internal/platform/audit/audit.go                   |   2 +
 .../admin_user_unban_integration_test.go           | 160 +++++++++++++
 test/integration/harness_test.go                   |   2 +
 test/integration/yueops_unban_integration_test.go  | 263 +++++++++++++++++++++
 web-admin/src/api/users.ts                         |   5 +
 .../__tests__/unban-user-dialog.test.tsx           |  45 ++++
 .../src/components/users/unban-user-dialog.tsx     |  84 +++++++
 web-admin/src/routes/_admin/users_.$id.tsx         |  19 +-
 25 files changed, 1169 insertions(+), 13 deletions(-)

