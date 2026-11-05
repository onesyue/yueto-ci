# yueboard #152 review at f9aee30e921d5cf6d0f2fa79f4fa0a2ab5999675

Reviewed range: 92e0b56c2be1524a64ee7a5cd5e654e53821e311..f9aee30e921d5cf6d0f2fa79f4fa0a2ab5999675 (post-merge backfill; codex on mac-5f08d00f, read-only sandbox)
Started: 2026-11-05T03:44:46Z

Reading additional input from stdin...
OpenAI Codex v0.166.0
--------
workdir: /Users/j/codex-runs/mh1105/yb-152
model: gpt-6-astra
provider: openai
approval: never
sandbox: read-only
reasoning effort: medium
reasoning summaries: none
session id: 01a1a9cf-24c9-7fa2-8a00-f6579495b723
--------
user
You are reviewing merged PR onesyue/yueboard #152 at exact head f9aee30e921d5cf6d0f2fa79f4fa0a2ab5999675. Review ONLY the diff: git diff 92e0b56c2be1524a64ee7a5cd5e654e53821e311 f9aee30e921d5cf6d0f2fa79f4fa0a2ab5999675 (and git log 92e0b56c2be1524a64ee7a5cd5e654e53821e311..f9aee30e921d5cf6d0f2fa79f4fa0a2ab5999675). Do not modify files. Check correctness, regressions, weakened/removed tests, security, and that the change matches its title/intent. Output a final line exactly 'VERDICT: approve' or 'VERDICT: changes' followed by concise bullet findings.
2026-11-05T03:44:52.288102Z ERROR codex_models_manager::manager: failed to refresh available models: request timed out
codex
I’ll read the repository review guidance, then review only the specified diff and commit log without modifying files.
exec
/bin/zsh -lc "pwd; rg --files -g 'CLAUDE.md' -g 'AGENTS.md' -g '*status*' -g '*batch*' -g '*findings*' -g '*review*'" in /Users/j/codex-runs/mh1105/yb-152
 succeeded in 0ms:
/Users/j/codex-runs/mh1105/yb-152
CLAUDE.md
AGENTS.md
findings-ai-group.md
web-admin/src/lib/mail-batch.ts
web-admin/src/lib/mail-batch.test.ts
web-admin/src/components/orders/commission-status-control.tsx
web-admin/src/components/orders/commission-status-menu.tsx
web-admin/src/components/users/batch-dialogs.tsx
web-admin/src/components/__tests__/withdraw-chain-status.test.tsx
web-admin/src/components/__tests__/commission-review.test.tsx
web-admin/src/components/status-badge.tsx
web-admin/src/components/mail-batch-progress.tsx
web-admin/src/components/withdraw-chain-status.tsx
packages/ui/src/ui/status-badge.tsx
docs/performance/perf40-findings.md
docs/a5-device-signup-findings.md
docs/ci-integration-96f85bcd-findings.md
docs/contracts/economy-pack-findings.md
web/src/components/ui/status-badge.tsx
test/integration/review_findings_20261011_integration_test.go
test/integration/review_x4b_20261011_integration_test.go
test/integration/review2_restore_speed_20261011_integration_test.go
test/integration/withdraw_review_integration_test.go
test/integration/review2_findings_20261011_integration_test.go
test/e2e/linux/findings.md
web/src/routes/status.tsx
web/src/components/order-status-badge.tsx
internal/modules/invitealias/ai_review_test.go
internal/modules/subextra/preview_test.go
internal/modules/subextra/preview.go
internal/modules/subextra/preview.html
web/src/lib/status-page.ts
web/src/lib/network-status.ts
web/src/lib/status-page.test.ts
internal/modules/admin/order_commission_status.go
internal/modules/admin/config_status_page_test.go
internal/modules/admin/server_manage_batch.go
web/src/lib/testdata/email-verify-status.golden.json
internal/modules/admin/withdraw_review.go
internal/modules/giftcard/preview_lifetime_test.go
internal/modules/uticket/close_reply_status_test.go
internal/modules/nodesync/machine_status_error.go
internal/modules/nodesync/traffic_batch_integration_test.go
internal/modules/nodesync/yueops_internal_status.go
internal/modules/nodesync/internal_notify_batch_test.go
internal/modules/emby/support_status_test.go
internal/modules/emby/support_status_integration_test.go
internal/modules/emby/support_status.go
internal/modules/admin/pluginschema/SubPreview.json
internal/platform/db/slowquery_batch_integration_test.go
internal/platform/statuspage/statuspage_test.go
internal/platform/statuspage/statuspage.go
internal/platform/commission/status.go
internal/platform/db/migrations/00145_settle_closed_ticket_reply_status.sql

exec
/bin/zsh -lc 'cat CLAUDE.md; git log --format=fuller 92e0b56c2be1524a64ee7a5cd5e654e53821e311..f9aee30e921d5cf6d0f2fa79f4fa0a2ab5999675; git diff --stat 92e0b56c2be1524a64ee7a5cd5e654e53821e311 f9aee30e921d5cf6d0f2fa79f4fa0a2ab5999675' in /Users/j/codex-runs/mh1105/yb-152
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
go test ./internal/modules/emby/ -run TestToUsername -v
gofmt -w <file>
```

## PostgreSQL integration tests

Integration tests use in-process `httptest` servers and a real PostgreSQL schema
fixture derived from production `pg_dump`. They catch execution-only errors such
as ambiguous columns, unused INSERT parameters and pgx fatal-close on mismatched
types. Fixtures include PG17/18 `transaction_timeout`, requiring PostgreSQL 17+.
The actual CI environment uses PostgreSQL 18.

```sh
YUEBOARD_TEST_DATABASE_URL=postgres://postgres:pw@127.0.0.1:5432/yueboard_test \
  go test -tags integration -v ./test/integration/...
```

**That command does not cover the module integration suites.** `nodesync`,
`emby`, `handoff`, `deviceidentity`, `user`, `referencelock`, `order`, `db` and
`nativeproto` require their own coverage. Missing DSNs can call `t.Skip` while
`go test` still prints `ok`; inspect actual verbose run/pass/skip events.
`TestClonedReportOutboxCannotDoubleBill` and the billing-report cases are among
the critical tests outside `./test/integration/`.

The public central runner owns the current sequencing. Run domain fixtures on
a fresh PostgreSQL service, the clean-PG gate in an independent fresh database
of the same cluster, module suites serially, then full db/nativeproto migrations
and production-scale cases. Earlier migrations can create roles that hide a
fixture-initialization defect. `deviceidentity` and `nodesync` rebuild `public`
and must follow consumers of the full fixture.

For a targeted module run against an explicitly disposable database:

```sh
YUEBOARD_TRAFFIC_TEST_DATABASE_URL=postgres://postgres:pw@127.0.0.1:5432/yueboard_test \
YUEBOARD_TEST_DATABASE_URL=postgres://postgres:pw@127.0.0.1:5432/yueboard_test \
YUEBOARD_EMAILVERIFY_TEST_DATABASE_URL=postgres://postgres:pw@127.0.0.1:5432/yueboard_test \
YUEBOARD_TEST_FIXTURES=$PWD/test/fixtures \
YUEBOARD_MIGRATION_TEST_ALLOW_RESET=YES_I_UNDERSTAND_THIS_DATABASE_IS_DISPOSABLE \
  go test -count=1 -p 1 -tags integration -v \
    ./internal/modules/user ./internal/platform/referencelock \
    ./internal/modules/order ./internal/modules/emby ./internal/modules/handoff \
    ./internal/platform/deviceidentity ./internal/modules/nodesync
```

`user` and `referencelock` were missing from all commands before 2026-09-21.
`nativeproto` uses the migration DSN. `internal/platform/toolchain`'s
`TestEveryIntegrationPackageRunsInCI` detects integration packages omitted from
CI orchestration. A successful package line alone is insufficient.

Migration tests need separate explicit inputs:

```sh
YUEBOARD_MIGRATION_TEST_DATABASE_URL=postgres://postgres:pw@127.0.0.1:5432/yueboard_test \
YUEBOARD_MIGRATION_TEST_ALLOW_RESET=YES_I_UNDERSTAND_THIS_DATABASE_IS_DISPOSABLE \
YUEBOARD_MIGRATION_TEST_PRODUCTION_SCALE=1 \
  go test -count=1 -tags integration -v ./internal/platform/db ./internal/platform/nativeproto
```

These tests are destructive (`DROP SCHEMA public CASCADE`). Use the native
runner's ordering or a separate disposable database, never production.
`TestNativeMigrationsProductionScaleOnPostgres` executes the complete goose
chain from zero, including the approximately 1.1-million-row scale fixture.
`TestNativeMigrationsOnPostgres` checks a selected chain's ACL, trigger and
catalog semantics. An ACL migration requires updated semantic assertions, not
just adding its filename. The 2026-08-12 `emby_launch_audit` permission failure
exposed the cost of skipped real PostgreSQL migration tests.

The shared integration account/server also shares the checkout rate limiter.
Production defaults to ten checkouts per user per minute. `TestMain` defaults
`YUEBOARD_CHECKOUT_RATE_LIMIT_PER_MINUTE` to `10000` before `bootHandler`, unless
the caller sets it, to prevent unrelated later cases receiving 429. Keep the
production default protected by `checkout_rate_limit_default_test.go`.
`t.Setenv` inside a test cannot reconfigure a limiter already read by `order.New`.

Use workspace `../scripts/run-yueboard-pg18-gauntlet.sh` when no suitable local
PostgreSQL is running. It uses disposable `postgres:18.6-alpine`, a pool size of
four and automatic container cleanup. Do not run heavy tests on the bastion:
it has been CPU-steal constrained since the dated 2026-10-11 observation.
Clean up disposable containers, binaries and accounts. Production database
inspection remains read-only; never use it for destructive tests.

## Architecture

The backend is a modular monolith using chi and pgx/pgxpool, with no ORM.

- `internal/modules/<mod>/`: business domains with `New(pool, st, ...)` and
  `Routes(chi.Router)`. Do not import another business module.
- `internal/platform/<pkg>/`: shared `db`, `auth`, `settings`, `apiresp`, `mail`,
  `verify`, `metrics`, `antigfw`, `resource` and `apptime` infrastructure.
- `internal/server/server.go`: composition only. Middleware order matters:
  `antigfw.Harden` first (`Server: nginx`), then `RealIP`,
  `antigfw.TarpitMiddleware`, RequestID, Recoverer and metrics.
- `cmd/yueboard/main.go`: constructs `server.Deps`. Wire new modules here and
  mirror the wiring in `test/integration/harness_test.go::bootHandler`.
  `deps.Extra` is for `/api`; `deps.Root` is for root endpoints.

User modules mount only under `/api/v1/*`, using relative paths such as
`/user/emby` in `Routes`. `/api/v2/*` contains the admin group and subscription
aliases, not user APIs. `TestAdminRoutesGuarded` protects that boundary after
stale dual-prefix guidance was corrected on 2026-09-05.

Admin traffic uses `/api/v2/{secure_path}/*` inside the `/api` group, never the
root group. The production secure path exists only in settings; do not record
it in source. Subscription delivery and node synchronization use `deps.Root`.
For explicitly parallel development, each worker owns its package; the main
integrator alone wires `main.go` and `harness_test.go`.

## Schema and generated data access

- Goose migrations live in `internal/platform/db/migrations/*.sql` and are
  embedded. Run `yueboard migrate up|down|status`; service startup does not
  auto-migrate. `adoptBaseline` recognizes existing `users` and stamps version
  1 without rerunning 00001. Actual column conversion begins at 00002.
- Named SQL in `internal/modules/<mod>/queries/` generates that module's `store/`
  via sqlc. Never hand-edit generated code or import another module's store.
  Shared `plugins`, `settings` and `personal_access_tokens` stores belong in
  the corresponding platform package.
- Unmarked migrations must expand: add tables, nullable/defaulted columns,
  indexes, functions or grants. `DROP TABLE|COLUMN|FUNCTION`, `RENAME`,
  `ALTER … TYPE` and `SET NOT NULL` without a default require
  `-- +yue contract-of: NNNNN` at the Up header, with NNNNN no greater than the
  deployed `schema-compat.txt` floor. Advance that floor only after actual
  successful deployment. `make check-migrations`, PG18 integration and runtime
  `migrate up` enforce the same rule. The exemption set is capped at 83.
- `test/fixtures/schema.sql` is the shared real-DDL source for sqlc and
  integration. Update it with column migrations. `make generate` pins sqlc;
  `make check-generated` rejects regeneration drift. Query native nullable
  timestamps, preserve NULL through pgtype and convert epochs at response time.
- Keep `resource.PlanResource`, `apptime` (Asia/Shanghai), the v1 envelope and
  403-JSON logout semantics, and anti-GFW nginx-404 behavior. These are client
  and domain contracts, not disposable PHP migration leftovers. A future owned
  `/api/v3` requires coordinated client/token migration, separate from schema work.

## Required workspace skills

Do not split this file merely to reduce its apparent size; shared procedures
already live in the workspace `.claude/skills/` and are linked for both agents.

- `pg-safety`: migrations, grants, role manifests, cross-owner reads and monetary
  eligibility. Required privileges exceed the statement verb: DELETE predicates
  need SELECT, and `ON CONFLICT (a,b) DO UPDATE` needs table-level SELECT.
- `release-chain`: default-branch pushes participate in the release process.
- `guard-authoring`: guards, assertions and contract checks must detect faults.
- Also use `node-lifecycle`, `fleet-diagnose`, `generated-blocks` and
  `round-closeout` when their scope applies.

## Incident lessons

- pgx v5 `rows.Scan` type mismatches call `rows.fatal()` and silently truncate
  the rowset. Match real column types, including nullable values and floating
  monetary columns. Real-schema integration is essential.
- Plugin configuration is JSON text in `plugins.config`, not `settings`.
  `invitealias`/`emby` use `SELECT is_enabled, config FROM plugins WHERE code=$1`
  with a 60-second process cache. Preserve permissive legacy bool/integer forms
  such as `true`, `1`, `"1"` and `"3"` where the existing contract requires them.
- PHP `preg_replace` without `/u` operates on bytes; Go regexp operates on runes.
  `emby.toUsername` uses a byte loop for compatibility. Derived keys/hashes must
  preserve the original `config('app.key')` string, including `base64:`. Compare
  PHP `hash_hmac` output and verify the real external-service consumer.
- Prefix package-level identifiers within modules (`ce`, `ia`, `emby`, etc.) to
  avoid cross-file and future package-merging collisions.

## Anti-GFW behavior

Read `docs/anti-gfw.md` before changing `internal/platform/antigfw`. Active
probing motivates `Server: nginx`, nginx-404 responses for invalid unauthenticated
subscription/node tokens, probe-IP tarpits and optional `YUEBOARD_DECOY_HTML`.
Do not expose endpoint fingerprints such as `token is error`.
**API requests carrying Authorization still require JSON 403 for client logout.**
Decoy 404 applies to unauthenticated subscription/node/unmatched routes.

## Canonical node contract

`proto/yuenode/v1/yuenode.proto` is canonical. The Node copy is an exact mirror,
protected by `proto/CANONICAL.sha256`, `scripts/sync-proto.sh` and Go tests.
Change Board first, synchronize Node, run `buf generate` on both sides and
commit proto plus generated code in each repository. Ordinary builds consume
tracked generated code and do not require buf.

`scripts/ci/proto-gate.sh` runs lint and breaking checks against
`proto/breaking-baseline.binpb`. Additive fields/RPCs are permitted. A wire break
requires upgrading the complete affected fleet before accepting a new baseline
with `--accept-baseline` and recording the rationale. Do not copy an old fleet
count from this document. Divergent `machine_id` comments once gave the two
proto files and generated code three meanings despite identical field numbers;
green compilation does not prove semantic agreement.

## References

- `docs/architecture.md`: architecture decisions and deployment shape.
- `docs/api-contract.md`: production v1 wire contract.
- `docs/anti-gfw.md`, `docs/observability.md`, `deploy/README.md`.
- `docs/pgo.md`: profile refresh/merge and freshness gates.
- Workspace `../docs/privatization-roadmap.md`: roadmap and migration history.
commit f9aee30e921d5cf6d0f2fa79f4fa0a2ab5999675
Author:     onesyue <47652916+onesyue@users.noreply.github.com>
AuthorDate: Thu Nov 5 09:04:34 2026 +0800
Commit:     onesyue <47652916+onesyue@users.noreply.github.com>
CommitDate: Thu Nov 5 09:04:34 2026 +0800

    ui(mail): unify HTML email shell with #0A84FF, light/dark
 internal/modules/admin/mailtemplate.go            | 18 +++++++++------
 internal/modules/remindmailcron/remindmailcron.go | 27 +++++++++++++---------
 internal/platform/mailtheme/appearance.go         | 17 ++++++++++++++
 internal/platform/mailtheme/layout.go             | 28 +++++++++++------------
 internal/platform/mailtheme/layout_test.go        |  4 ++--
 web-admin/src/routes/_admin/mail-templates.tsx    | 20 ++++++++++++----
 6 files changed, 75 insertions(+), 39 deletions(-)

exec
/bin/zsh -lc 'git diff 92e0b56c2be1524a64ee7a5cd5e654e53821e311 f9aee30e921d5cf6d0f2fa79f4fa0a2ab5999675; for p in ../AGENTS.md ../CLAUDE.md; do if test -f "$p"; then cat "$p"; fi; done' in /Users/j/codex-runs/mh1105/yb-152
 succeeded in 0ms:
diff --git a/internal/modules/admin/mailtemplate.go b/internal/modules/admin/mailtemplate.go
index f147a0c3..5e0e9d5d 100644
--- a/internal/modules/admin/mailtemplate.go
+++ b/internal/modules/admin/mailtemplate.go
@@ -13,6 +13,7 @@ import (
 	"github.com/onesyue/yueboard/internal/platform/apiresp"
 	"github.com/onesyue/yueboard/internal/platform/audit"
 	"github.com/onesyue/yueboard/internal/platform/i18n"
+	"github.com/onesyue/yueboard/internal/platform/mailtheme"
 )
 
 type mailTemplateDefinition struct {
@@ -310,13 +311,16 @@ func (m *Module) mailTemplateDefaults(ctx context.Context, lang string, def mail
 }
 
 func mailTemplateLayout(lang, title, body string) string {
-	return `<div style="background:#f3f4f6;padding:32px 12px">` +
-		`<table width="600" style="max-width:100%;margin:auto;background:#fff;border-radius:12px;overflow:hidden">` +
-		`<tr><td style="background:#415a94;color:#fff;padding:20px 32px;font-size:21px">{{name}}</td></tr>` +
-		`<tr><td style="padding:32px"><h1 style="font-size:24px">` + title + `</h1>` +
-		`<div style="font-size:14px;line-height:1.8;color:#333">` + body + `</div></td></tr>` +
-		`<tr><td style="padding:18px 32px;background:#f7f7f7"><a href="{{url}}">` + html.EscapeString(i18n.T(lang, "返回 {{name}}")) + `</a></td></tr>` +
-		`</table></div>`
+	// Title has already been escaped by renderMailPlaceholders; Render escapes text fields.
+	return mailtheme.Render(mailtheme.Doc{
+		Lang:  i18n.LangOrDefault(lang),
+		Title: html.UnescapeString(title),
+		Brand: "{{name}}",
+		Blocks: []string{
+			mailtheme.Paragraph(body),
+			mailtheme.Button("{{url}}", i18n.T(lang, "返回 {{name}}")),
+		},
+	})
 }
 
 func renderMailPlaceholders(value string, vars map[string]string) string {
diff --git a/internal/modules/remindmailcron/remindmailcron.go b/internal/modules/remindmailcron/remindmailcron.go
index 9875d6c0..bdfb2b23 100644
--- a/internal/modules/remindmailcron/remindmailcron.go
+++ b/internal/modules/remindmailcron/remindmailcron.go
@@ -20,6 +20,7 @@ import (
 	"github.com/onesyue/yueboard/internal/platform/i18n"
 	"github.com/onesyue/yueboard/internal/platform/inbox"
 	"github.com/onesyue/yueboard/internal/platform/mail"
+	"github.com/onesyue/yueboard/internal/platform/mailtheme"
 	"github.com/onesyue/yueboard/internal/platform/metrics"
 	"github.com/onesyue/yueboard/internal/platform/quotaidentity"
 	"github.com/onesyue/yueboard/internal/platform/reminderrules"
@@ -566,26 +567,30 @@ func trafficSubject(lang, appName string) string {
 
 // Expiry copy uses an absolute date for all shared reminder buckets.
 func remindExpiryEventBody(lang, name, url string, expiredAt int64, days int) string {
-	n, u := html.EscapeString(name), html.EscapeString(url)
 	date := time.Unix(expiredAt, 0).In(apptime.Loc()).Format("2006-01-02 15:04")
 	key := "您的订阅将于 {date} 到期。为避免服务中断，请及时续费。"
 	if days == 0 {
 		key = "您的订阅已于 {date} 到期。请续费以恢复服务。"
 	}
 	body := html.EscapeString(i18n.T(lang, key, "date", date))
-	return `<div style="max-width:520px;margin:0 auto;font-family:sans-serif"><h2>` + n + `</h2><p>` + body +
-		`</p><p><a href="` + u + `">` + html.EscapeString(i18n.T(lang, "立即续费")) + `</a></p></div>`
+	return mailtheme.Render(mailtheme.Doc{
+		Lang: i18n.LangOrDefault(lang), Title: name, Brand: name,
+		Blocks: []string{mailtheme.Paragraph(body), mailtheme.Button(url, i18n.T(lang, "立即续费"))},
+	})
 }
 
 func remindTrafficBody(lang, name, url string, pct int) string {
-	n, u := html.EscapeString(name), html.EscapeString(url)
-	t := func(zh string, vars ...any) string { return html.EscapeString(i18n.T(lang, zh, vars...)) }
-	return `<div style="max-width:520px;margin:0 auto;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1f2937">` +
-		`<h2 style="color:#111827">` + t("流量提醒") + `</h2>` +
-		`<p>` + n + `：` + t("您本月的套餐流量已使用") + ` <strong>` + fmt.Sprintf("%d%%", pct) + `</strong>。</p>` +
-		`<p>` + t("请合理安排使用，避免提前耗尽。如需更多流量，可前往面板升级套餐。") + `</p>` +
-		`<p style="margin:24px 0"><a href="` + u + `" style="background:#2563eb;color:#fff;padding:10px 20px;border-radius:6px;text-decoration:none">` + t("查看用量") + `</a></p>` +
-		`<p style="color:#9ca3af;font-size:12px">` + t("此邮件由系统自动发送，请勿直接回复。") + `</p></div>`
+	t := func(zh string, vars ...any) string { return i18n.T(lang, zh, vars...) }
+	return mailtheme.Render(mailtheme.Doc{
+		Lang: i18n.LangOrDefault(lang), Title: t("流量提醒"), Brand: name,
+		Blocks: []string{
+			mailtheme.Paragraph(html.EscapeString(name) + "：" + html.EscapeString(t("您本月的套餐流量已使用")) +
+				" " + mailtheme.Strong(fmt.Sprintf("%d%%", pct)) + "。"),
+			mailtheme.Paragraph(html.EscapeString(t("请合理安排使用，避免提前耗尽。如需更多流量，可前往面板升级套餐。"))),
+			mailtheme.Button(url, t("查看用量")),
+		},
+		FooterNote: t("此邮件由系统自动发送，请勿直接回复。"),
+	})
 }
 
 // remindmailRoundTimeout 是单轮的硬上限。cron 是串行 Ticker：一轮卡住（锁等待、慢查询、
diff --git a/internal/platform/mailtheme/appearance.go b/internal/platform/mailtheme/appearance.go
new file mode 100644
index 00000000..bbc5d134
--- /dev/null
+++ b/internal/platform/mailtheme/appearance.go
@@ -0,0 +1,17 @@
+package mailtheme
+
+// Email-specific CSS uses the dark roles from design/tokens/yue.tokens.json.
+// Inline light styles remain the fallback for clients that strip media queries.
+// The owner-requested brand accent is decorative; action text keeps AA contrast.
+const themeStyles = `<style>
+:root { color-scheme: light dark; supported-color-schemes: light dark; }
+a { color: ` + ColorBrandText + `; }
+@media (prefers-color-scheme: dark) {
+.mail-canvas { background-color: #101010 !important; }
+.mail-card { background: #1c1c1e !important; border-color: #45403b !important; border-top-color: #0A84FF !important; }
+.mail-primary { color: #fcfbfa !important; }
+.mail-copy { color: #c9c3bc !important; }
+.mail-code { background: #1f1f1f !important; border-color: #45403b !important; color: #fcfbfa !important; }
+.mail-link, .mail-copy a { color: #0A84FF !important; }
+}
+</style>`
diff --git a/internal/platform/mailtheme/layout.go b/internal/platform/mailtheme/layout.go
index 754a0507..d8148acc 100644
--- a/internal/platform/mailtheme/layout.go
+++ b/internal/platform/mailtheme/layout.go
@@ -26,23 +26,23 @@ func Render(d Doc) string {
 	var b strings.Builder
 	b.WriteString(`<!DOCTYPE html><html lang="` + html.EscapeString(d.Lang) + `"><head><meta charset="UTF-8">`)
 	b.WriteString(`<meta name="viewport" content="width=device-width, initial-scale=1.0">`)
-	b.WriteString(`<meta name="color-scheme" content="light"><meta name="supported-color-schemes" content="light">`)
-	b.WriteString(`<title>` + html.EscapeString(d.Title) + `</title></head>`)
-	b.WriteString(`<body style="margin:0;padding:0;background-color:` + ColorCanvas + `;font-family:` + FontSans + `;color:` + ColorTextPrimary + `;">`)
-	b.WriteString(`<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:` + ColorCanvas + `;padding:` + px(Space10) + ` ` + px(Space4) + `;"><tr><td align="center">`)
+	b.WriteString(`<meta name="color-scheme" content="light dark"><meta name="supported-color-schemes" content="light dark">`)
+	b.WriteString(`<title>` + html.EscapeString(d.Title) + `</title>` + themeStyles + `</head>`)
+	b.WriteString(`<body class="mail-canvas mail-primary" style="margin:0;padding:0;background-color:` + ColorCanvas + `;font-family:` + FontSans + `;color:` + ColorTextPrimary + `;">`)
+	b.WriteString(`<table class="mail-canvas" role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:` + ColorCanvas + `;padding:` + px(Space10) + ` ` + px(Space4) + `;"><tr><td align="center">`)
 	b.WriteString(`<table role="presentation" width="` + strconv.Itoa(ContentWidth) + `" cellpadding="0" cellspacing="0" style="max-width:` + px(ContentWidth) + `;width:100%;">`)
-	b.WriteString(`<tr><td style="padding-bottom:` + px(Space6) + `;text-align:center;font-size:` + px(SizeTitle) + `;font-weight:` + strconv.Itoa(WeightTitle) + `;color:` + ColorTextPrimary + `;">` + html.EscapeString(d.Brand) + `</td></tr>`)
-	b.WriteString(`<tr><td style="background:` + ColorRaised + `;border:1px solid ` + ColorStroke + `;border-radius:` + px(RadiusCard) + `;padding:` + px(Space8) + `;">`)
+	b.WriteString(`<tr><td class="mail-primary" style="padding-bottom:` + px(Space6) + `;text-align:center;font-size:` + px(SizeTitle) + `;font-weight:` + strconv.Itoa(WeightTitle) + `;color:` + ColorTextPrimary + `;">` + html.EscapeString(d.Brand) + `</td></tr>`)
+	b.WriteString(`<tr><td class="mail-card" style="background:` + ColorRaised + `;border:1px solid ` + ColorStroke + `;border-top:4px solid #0A84FF;border-radius:` + px(RadiusCard) + `;padding:` + px(Space8) + `;">`)
 	b.WriteString(`<table role="presentation" width="100%" cellpadding="0" cellspacing="0">`)
-	b.WriteString(`<tr><td style="font-size:` + px(SizeTitleLg) + `;font-weight:` + strconv.Itoa(WeightTitle) + `;line-height:1.35;color:` + ColorTextPrimary + `;padding-bottom:` + px(Space2) + `;">` + html.EscapeString(d.Title) + `</td></tr>`)
+	b.WriteString(`<tr><td class="mail-primary" style="font-size:` + px(SizeTitleLg) + `;font-weight:` + strconv.Itoa(WeightTitle) + `;line-height:1.35;color:` + ColorTextPrimary + `;padding-bottom:` + px(Space2) + `;">` + html.EscapeString(d.Title) + `</td></tr>`)
 	for _, block := range d.Blocks {
 		b.WriteString(block)
 	}
 	b.WriteString(`</table></td></tr>`)
-	b.WriteString(`<tr><td style="padding-top:` + px(Space6) + `;text-align:center;font-size:` + px(SizeCaption) + `;line-height:` + LineBody + `;color:` + ColorTextTertiary + `;">`)
+	b.WriteString(`<tr><td class="mail-copy" style="padding-top:` + px(Space6) + `;text-align:center;font-size:` + px(SizeCaption) + `;line-height:` + LineBody + `;color:` + ColorTextTertiary + `;">`)
 	if d.FooterURL != "" {
 		u := html.EscapeString(d.FooterURL)
-		b.WriteString(`<a href="` + u + `" style="font-size:` + px(SizeLabel) + `;color:` + ColorTextTertiary + `;text-decoration:none;">` + u + `</a><br>`)
+		b.WriteString(`<a class="mail-link" href="` + u + `" style="font-size:` + px(SizeLabel) + `;color:` + ColorTextTertiary + `;text-decoration:none;">` + u + `</a><br>`)
 	}
 	b.WriteString(html.EscapeString(d.FooterNote))
 	b.WriteString(`</td></tr></table></td></tr></table></body></html>`)
@@ -52,18 +52,18 @@ func Render(d Doc) string {
 // Paragraph renders body copy. inner is trusted HTML: the caller escapes every
 // translated or user-derived piece (Strong helps with emphasis).
 func Paragraph(inner string) string {
-	return `<tr><td style="font-size:` + px(SizeBody) + `;line-height:` + LineBody + `;color:` + ColorTextSecondary + `;padding-bottom:` + px(Space6) + `;">` + inner + `</td></tr>`
+	return `<tr><td class="mail-copy" style="font-size:` + px(SizeBody) + `;line-height:` + LineBody + `;color:` + ColorTextSecondary + `;padding-bottom:` + px(Space6) + `;">` + inner + `</td></tr>`
 }
 
 // Strong emphasises plain text inside a Paragraph.
 func Strong(text string) string {
-	return `<strong style="color:` + ColorTextPrimary + `;font-weight:` + strconv.Itoa(WeightTitle) + `;">` + html.EscapeString(text) + `</strong>`
+	return `<strong class="mail-primary" style="color:` + ColorTextPrimary + `;font-weight:` + strconv.Itoa(WeightTitle) + `;">` + html.EscapeString(text) + `</strong>`
 }
 
 // Code renders a one-time code in the mono stack with tabular figures.
 func Code(code string) string {
 	return `<tr><td align="center" style="padding-bottom:` + px(Space6) + `;">` +
-		`<div style="display:inline-block;background:` + ColorSubtle + `;border:1px solid ` + ColorStroke + `;border-radius:` + px(RadiusInner) + `;padding:` + px(Space4) + ` ` + px(Space8) + `;font-family:` + FontMono + `;font-size:` + px(SizeDisplaySm) + `;font-weight:` + strconv.Itoa(WeightTitle) + `;letter-spacing:6px;font-variant-numeric:tabular-nums;color:` + ColorTextPrimary + `;">` +
+		`<div class="mail-code" style="display:inline-block;background:` + ColorSubtle + `;border:1px solid ` + ColorStroke + `;border-radius:` + px(RadiusInner) + `;padding:` + px(Space4) + ` ` + px(Space8) + `;font-family:` + FontMono + `;font-size:` + px(SizeDisplaySm) + `;font-weight:` + strconv.Itoa(WeightTitle) + `;letter-spacing:6px;font-variant-numeric:tabular-nums;color:` + ColorTextPrimary + `;">` +
 		html.EscapeString(code) + `</div></td></tr>`
 }
 
@@ -74,11 +74,11 @@ func Button(href, label string) string {
 
 // Note renders secondary guidance in the tertiary text colour (>= 4.5:1).
 func Note(text string) string {
-	return `<tr><td style="font-size:` + px(SizeLabel) + `;line-height:` + LineBody + `;color:` + ColorTextTertiary + `;">` + html.EscapeString(text) + `</td></tr>`
+	return `<tr><td class="mail-copy" style="font-size:` + px(SizeLabel) + `;line-height:` + LineBody + `;color:` + ColorTextTertiary + `;">` + html.EscapeString(text) + `</td></tr>`
 }
 
 // URL renders a copyable fallback link that wraps on narrow screens.
 func URL(href string) string {
 	u := html.EscapeString(href)
-	return `<tr><td style="font-size:` + px(SizeLabel) + `;line-height:` + LineBody + `;color:` + ColorTextTertiary + `;word-break:break-all;padding-top:` + px(Space2) + `;">` + u + `</td></tr>`
+	return `<tr><td class="mail-copy" style="font-size:` + px(SizeLabel) + `;line-height:` + LineBody + `;color:` + ColorTextTertiary + `;word-break:break-all;padding-top:` + px(Space2) + `;">` + u + `</td></tr>`
 }
diff --git a/internal/platform/mailtheme/layout_test.go b/internal/platform/mailtheme/layout_test.go
index ff56697d..23ed1f07 100644
--- a/internal/platform/mailtheme/layout_test.go
+++ b/internal/platform/mailtheme/layout_test.go
@@ -18,8 +18,8 @@ func TestRenderEscapesPlainTextFields(t *testing.T) {
 			t.Fatalf("unescaped %q in output", raw)
 		}
 	}
-	if !strings.Contains(out, "悦&lt;通&gt;") || !strings.Contains(out, `<meta name="color-scheme" content="light">`) {
-		t.Fatalf("missing escaped brand or light colour-scheme meta")
+	if !strings.Contains(out, "悦&lt;通&gt;") || !strings.Contains(out, `<meta name="color-scheme" content="light dark">`) {
+		t.Fatalf("missing escaped brand or light/dark colour-scheme meta")
 	}
 }
 
diff --git a/web-admin/src/routes/_admin/mail-templates.tsx b/web-admin/src/routes/_admin/mail-templates.tsx
index 305127f8..e23668e0 100644
--- a/web-admin/src/routes/_admin/mail-templates.tsx
+++ b/web-admin/src/routes/_admin/mail-templates.tsx
@@ -1,6 +1,6 @@
 import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
 import { createFileRoute } from "@tanstack/react-router";
-import { Pencil, RotateCcw, Send } from "lucide-react";
+import { Mail, Pencil, RotateCcw, Send } from "lucide-react";
 import { useState } from "react";
 import { toast } from "sonner";
 
@@ -101,7 +101,17 @@ function MailTemplatesPage() {
               <TableBody>
                 {query.data?.map((tpl) => (
                   <TableRow key={`${tpl.name}:${tpl.locale}`}>
-                    <TableCell className="font-medium">{tpl.label}</TableCell>
+                    <TableCell>
+                      <div className="flex items-center gap-3">
+                        <span className="rounded-lg bg-accent p-2 text-accent-foreground" aria-hidden="true">
+                          <Mail className="size-4" />
+                        </span>
+                        <div className="min-w-0">
+                          <p className="font-medium">{tpl.label}</p>
+                          <p className="max-w-48 truncate text-xs text-muted-foreground md:hidden">{tpl.subject}</p>
+                        </div>
+                      </div>
+                    </TableCell>
                     <TableCell className="hidden max-w-xs truncate text-sm text-muted-foreground md:table-cell">
                       {tpl.subject}
                     </TableCell>
@@ -111,7 +121,7 @@ function MailTemplatesPage() {
                       ) : tpl.customized ? (
                         <StatusBadge tone="brand">{t("已自定义")}</StatusBadge>
                       ) : (
-                        <span className="text-sm text-muted-foreground">{t("默认")}</span>
+                        <StatusBadge tone="neutral">{t("默认")}</StatusBadge>
                       )}
                     </TableCell>
                     <TableCell className="hidden text-xs text-muted-foreground lg:table-cell whitespace-nowrap">
@@ -296,12 +306,12 @@ function MailTemplateForm({
           value={content}
           onChange={(e) => setContent(e.target.value)}
           rows={12}
-          className="font-mono text-sm"
+          className="min-h-72 rounded-xl bg-soft font-mono text-sm"
         />
       </FormField>
 
       {(detail.required_vars.length > 0 || detail.optional_vars.length > 0) && (
-        <div className="grid grid-cols-1 gap-3 rounded-md border bg-soft p-3">
+        <div className="grid grid-cols-1 gap-3 rounded-xl border bg-soft p-4">
           <VarChips title={t("必填占位符（正文必须包含）")} vars={detail.required_vars} />
           <VarChips title={t("可选占位符")} vars={detail.optional_vars} />
           <span className="text-xs text-muted-foreground">

codex
- No actionable correctness, security, or regression findings in the specified diff.
- Changes match the commit’s email styling intent. The test update preserves escaping checks and adjusts the expected color scheme; no tests were removed.
- Static review only; tests and email-client rendering were not run.

VERDICT: approve
tokens used
33,909
- No actionable correctness, security, or regression findings in the specified diff.
- Changes match the commit’s email styling intent. The test update preserves escaping checks and adjusts the expected color scheme; no tests were removed.
- Static review only; tests and email-client rendering were not run.

VERDICT: approve
Finished: 2026-11-05T03:45:35Z exit=0
