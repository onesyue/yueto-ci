# yueboard #156 review at 46fa9355be9b8ab5ab5110eddbd8b086581bced2

Reviewed range: c5dd144ca477566cf002159aaba638491ac2a2a9..46fa9355be9b8ab5ab5110eddbd8b086581bced2 (post-merge backfill; codex on mac-5f08d00f, read-only sandbox)
Started: 2026-11-05T03:44:46Z

Reading additional input from stdin...
OpenAI Codex v0.166.0
--------
workdir: /Users/j/codex-runs/mh1105/yb-156
model: gpt-6-astra
provider: openai
approval: never
sandbox: read-only
reasoning effort: medium
reasoning summaries: none
session id: 01a1a9cf-24c9-75a2-b3b2-8127cb98bf59
--------
user
You are reviewing merged PR onesyue/yueboard #156 at exact head 46fa9355be9b8ab5ab5110eddbd8b086581bced2. Review ONLY the diff: git diff c5dd144ca477566cf002159aaba638491ac2a2a9 46fa9355be9b8ab5ab5110eddbd8b086581bced2 (and git log c5dd144ca477566cf002159aaba638491ac2a2a9..46fa9355be9b8ab5ab5110eddbd8b086581bced2). Do not modify files. Check correctness, regressions, weakened/removed tests, security, and that the change matches its title/intent. Output a final line exactly 'VERDICT: approve' or 'VERDICT: changes' followed by concise bullet findings.
2026-11-05T03:44:52.289328Z ERROR codex_models_manager::manager: failed to refresh available models: request timed out
codex
I’ll read the repository guidance, then review only the specified commit range and diff for correctness, regressions, test coverage, security, and intent. I won’t modify files.
exec
/bin/zsh -lc 'pwd; cat CLAUDE.md; git log --oneline c5dd144ca477566cf002159aaba638491ac2a2a9..46fa9355be9b8ab5ab5110eddbd8b086581bced2; git diff --stat c5dd144ca477566cf002159aaba638491ac2a2a9 46fa9355be9b8ab5ab5110eddbd8b086581bced2' in /Users/j/codex-runs/mh1105/yb-156
 succeeded in 0ms:
/Users/j/codex-runs/mh1105/yb-156
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
46fa9355 fix(subscribe,i18n): keep R-14 branded node names (悦 · 🇭🇰 香港1)
 docs/design/admin-dashboard.reference.html       | 12 ++++----
 internal/modules/subscribe/display_name.go       |  4 +++
 internal/modules/subscribe/display_name_test.go  | 21 +++++++++++++
 internal/modules/subscribe/template_i18n.go      | 25 +++++++++++-----
 internal/modules/subscribe/template_i18n_test.go | 23 ++++++++++++++
 internal/platform/i18n/business.go               | 38 ++++++++++++++++++++++--
 internal/platform/i18n/business_test.go          | 36 ++++++++++++++++++++++
 7 files changed, 143 insertions(+), 16 deletions(-)

exec
/bin/zsh -lc 'git diff c5dd144ca477566cf002159aaba638491ac2a2a9 46fa9355be9b8ab5ab5110eddbd8b086581bced2; for p in ../AGENTS.md ../CLAUDE.md; do if test -f "$p"; then cat "$p"; fi; done' in /Users/j/codex-runs/mh1105/yb-156
 succeeded in 0ms:
diff --git a/docs/design/admin-dashboard.reference.html b/docs/design/admin-dashboard.reference.html
index 0488f91d..f218609c 100644
--- a/docs/design/admin-dashboard.reference.html
+++ b/docs/design/admin-dashboard.reference.html
@@ -153,12 +153,12 @@
         <div class="card">
           <div class="card-h"><div class="ti"><b>🖧 节点流量排行</b></div><span class="sel">今天 ▾</span></div>
           <div class="rankbody">
-            <div class="rrow"><div class="l1"><span class="nm">悦·🇹🇼台湾1</span><span class="ch down">↓ 27.6%</span></div><div class="l2"><span class="track"><i style="width:100%"></i></span><span class="gb">614.11 GB</span></div></div>
-            <div class="rrow"><div class="l1"><span class="nm">悦·🇹🇼台湾家宽2 💎</span><span class="ch up">↑ 23.1%</span></div><div class="l2"><span class="track"><i style="width:89%"></i></span><span class="gb">544.63 GB</span></div></div>
-            <div class="rrow"><div class="l1"><span class="nm">悦·🇹🇼台湾2</span><span class="ch down">↓ 29.3%</span></div><div class="l2"><span class="track"><i style="width:83%"></i></span><span class="gb">512.95 GB</span></div></div>
-            <div class="rrow"><div class="l1"><span class="nm">悦·🇭🇰香港家宽2 💎</span><span class="ch up">↑ 147.2%</span></div><div class="l2"><span class="track"><i style="width:55%"></i></span><span class="gb">335.93 GB</span></div></div>
-            <div class="rrow"><div class="l1"><span class="nm">悦·🇯🇵日本1</span><span class="ch down">↓ 27.2%</span></div><div class="l2"><span class="track"><i style="width:32%"></i></span><span class="gb">199.32 GB</span></div></div>
-            <div class="rrow"><div class="l1"><span class="nm">悦·🇺🇸美国专属1 💎</span><span class="ch down">↓ 10.1%</span></div><div class="l2"><span class="track"><i style="width:31%"></i></span><span class="gb">191.24 GB</span></div></div>
+            <div class="rrow"><div class="l1"><span class="nm">悦 · 🇹🇼 台湾1</span><span class="ch down">↓ 27.6%</span></div><div class="l2"><span class="track"><i style="width:100%"></i></span><span class="gb">614.11 GB</span></div></div>
+            <div class="rrow"><div class="l1"><span class="nm">悦 · 🇹🇼 台湾家宽2 💎</span><span class="ch up">↑ 23.1%</span></div><div class="l2"><span class="track"><i style="width:89%"></i></span><span class="gb">544.63 GB</span></div></div>
+            <div class="rrow"><div class="l1"><span class="nm">悦 · 🇹🇼 台湾2</span><span class="ch down">↓ 29.3%</span></div><div class="l2"><span class="track"><i style="width:83%"></i></span><span class="gb">512.95 GB</span></div></div>
+            <div class="rrow"><div class="l1"><span class="nm">悦 · 🇭🇰 香港家宽2 💎</span><span class="ch up">↑ 147.2%</span></div><div class="l2"><span class="track"><i style="width:55%"></i></span><span class="gb">335.93 GB</span></div></div>
+            <div class="rrow"><div class="l1"><span class="nm">悦 · 🇯🇵 日本1</span><span class="ch down">↓ 27.2%</span></div><div class="l2"><span class="track"><i style="width:32%"></i></span><span class="gb">199.32 GB</span></div></div>
+            <div class="rrow"><div class="l1"><span class="nm">悦 · 🇺🇸 美国专属1 💎</span><span class="ch down">↓ 10.1%</span></div><div class="l2"><span class="track"><i style="width:31%"></i></span><span class="gb">191.24 GB</span></div></div>
           </div>
         </div>
 
diff --git a/internal/modules/subscribe/display_name.go b/internal/modules/subscribe/display_name.go
index 8dd43d58..74815985 100644
--- a/internal/modules/subscribe/display_name.go
+++ b/internal/modules/subscribe/display_name.go
@@ -94,6 +94,10 @@ func prepareDisplayNames(servers []*serverRow) {
 		if s == nil || s.placeholder || isSubscriptionNoticeName(s.Name) {
 			continue
 		}
+		name := strings.TrimSpace(s.Name)
+		if strings.HasPrefix(name, "悦 ·") || strings.HasPrefix(name, "悦·") {
+			continue
+		}
 		region := displayRegion(s.Name)
 		protocol := map[string]string{"vless": "VLESS", "hysteria": "Hysteria2"}[s.Type]
 		if region == "" || protocol == "" {
diff --git a/internal/modules/subscribe/display_name_test.go b/internal/modules/subscribe/display_name_test.go
index e1680a01..7bb183aa 100644
--- a/internal/modules/subscribe/display_name_test.go
+++ b/internal/modules/subscribe/display_name_test.go
@@ -77,6 +77,27 @@ func TestDisplayNamesNumberingAndMultiplier(t *testing.T) {
 	}
 }
 
+func TestDisplayNamesPreserveBrandedNames(t *testing.T) {
+	rows := []*serverRow{
+		{Name: "悦 · 🇭🇰 香港1", Type: "hysteria"},
+		{Name: "悦 · 🇭🇰 香港2", Type: "vless"},
+		{Name: "悦 · 🇭🇰 香港3 💎", Type: "vless"},
+		{Name: "悦·🇭🇰香港4", Type: "hysteria"},
+		{Name: " \t悦 · 🇭🇰 香港5\n", Type: "vless"},
+		{Name: " \t悦·🇭🇰香港6 💎\n", Type: "hysteria"},
+	}
+	legacy := &serverRow{Name: "香港 legacy [x1.50]", Type: "vless"}
+	prepareDisplayNames(append(rows, legacy))
+	for _, row := range rows {
+		if row.DisplayName != "" {
+			t.Errorf("branded name %q rewritten as %q", row.Name, row.DisplayName)
+		}
+	}
+	if want := "香港 01 VLESS [x1.50]"; legacy.DisplayName != want {
+		t.Errorf("legacy display name = %q, want %q", legacy.DisplayName, want)
+	}
+}
+
 func displayTestRows() []*serverRow {
 	a, b, c, d := realityServer(), realityServer(), hy2Server(), hy2Server()
 	a.Name, b.Name, c.Name, d.Name = "美国 AI解锁 Reality x1.5", "美国 Reality x1.0", "美国 AI解锁 HY2 x2.0", "美国 HY2 x3.0"
diff --git a/internal/modules/subscribe/template_i18n.go b/internal/modules/subscribe/template_i18n.go
index 88b56538..bfce7e37 100644
--- a/internal/modules/subscribe/template_i18n.go
+++ b/internal/modules/subscribe/template_i18n.go
@@ -2,32 +2,41 @@ package subscribe
 
 import "strings"
 
-// subscriptionTemplateTranslations 是 zh-CN 模板 → English 的确定性派生词典。
-//
-// 这些词只对应代理组的「稳定显示名」，不是协议键；定义处和引用处同时替换，适用于
-// sing-box JSON、Clash/Stash YAML 与 Surge/Surfboard INI。长词必须排在短词前，
-// 否则先把「香港聚合」替掉会让「悦·🇭🇰香港聚合」再也匹配不到品牌化译名。
-//
-// 这条派生路径是 DB 英文模板缺席时的安全默认。运营创建 locale=en 的显式模板后，
-// template() 直接使用那一行，不再经过这里。
+// subscriptionTemplateTranslations maps stable display labels, never protocol keys.
+// Branded keys precede their shorter unbranded forms so definitions and references
+// receive the same translation. Explicit English DB templates bypass this fallback.
 var subscriptionTemplateTranslations = [...]struct {
 	zh string
 	en string
 }{
 	{"悦通服务", "Yue Services"},
+	{"悦 · 自动选择", "Yue · Auto Select"},
 	{"悦·自动选择", "Yue · Auto Select"},
+	{"悦 · 故障转移", "Yue · Fallback"},
 	{"悦·故障转移", "Yue · Fallback"},
+	{"悦 · 🇭🇰 香港聚合", "Yue · 🇭🇰 Hong Kong Pool"},
 	{"悦·🇭🇰香港聚合", "Yue · 🇭🇰 Hong Kong Pool"},
+	{"悦 · 🇹🇼 台湾聚合", "Yue · 🇹🇼 Taiwan Pool"},
 	{"悦·🇹🇼台湾聚合", "Yue · 🇹🇼 Taiwan Pool"},
+	{"悦 · 🇯🇵 日本聚合", "Yue · 🇯🇵 Japan Pool"},
 	{"悦·🇯🇵日本聚合", "Yue · 🇯🇵 Japan Pool"},
+	{"悦 · 🇰🇷 韩国聚合", "Yue · 🇰🇷 South Korea Pool"},
 	{"悦·🇰🇷韩国聚合", "Yue · 🇰🇷 South Korea Pool"},
+	{"悦 · 🇸🇬 新加坡聚合", "Yue · 🇸🇬 Singapore Pool"},
 	{"悦·🇸🇬新加坡聚合", "Yue · 🇸🇬 Singapore Pool"},
+	{"悦 · 🇺🇸 美国聚合", "Yue · 🇺🇸 United States Pool"},
 	{"悦·🇺🇸美国聚合", "Yue · 🇺🇸 United States Pool"},
+	{"悦 · 🇬🇧 英国聚合", "Yue · 🇬🇧 United Kingdom Pool"},
 	{"悦·🇬🇧英国聚合", "Yue · 🇬🇧 United Kingdom Pool"},
+	{"悦 · 🇩🇪 德国聚合", "Yue · 🇩🇪 Germany Pool"},
 	{"悦·🇩🇪德国聚合", "Yue · 🇩🇪 Germany Pool"},
+	{"悦 · 🇦🇺 澳大利亚聚合", "Yue · 🇦🇺 Australia Pool"},
 	{"悦·🇦🇺澳大利亚聚合", "Yue · 🇦🇺 Australia Pool"},
+	{"悦 · 🇨🇦 加拿大聚合", "Yue · 🇨🇦 Canada Pool"},
 	{"悦·🇨🇦加拿大聚合", "Yue · 🇨🇦 Canada Pool"},
+	{"悦 · 🇳🇱 荷兰聚合", "Yue · 🇳🇱 Netherlands Pool"},
 	{"悦·🇳🇱荷兰聚合", "Yue · 🇳🇱 Netherlands Pool"},
+	{"悦 · 🌏 更多地区", "Yue · 🌏 More Regions"},
 	{"悦·🌏更多地区", "Yue · 🌏 More Regions"},
 	{"新加坡聚合", "Singapore Pool"},
 	{"澳大利亚聚合", "Australia Pool"},
diff --git a/internal/modules/subscribe/template_i18n_test.go b/internal/modules/subscribe/template_i18n_test.go
index 3d6f604b..5a45490d 100644
--- a/internal/modules/subscribe/template_i18n_test.go
+++ b/internal/modules/subscribe/template_i18n_test.go
@@ -1,6 +1,7 @@
 package subscribe
 
 import (
+	"fmt"
 	"strings"
 	"testing"
 )
@@ -51,3 +52,25 @@ func TestTemplateTranslationKeysAreLongestFirst(t *testing.T) {
 		}
 	}
 }
+
+func TestLocalizeSubscriptionTemplateSpacedBrands(t *testing.T) {
+	for _, translation := range subscriptionTemplateTranslations {
+		if !strings.HasPrefix(translation.zh, "悦 · ") {
+			continue
+		}
+		for _, format := range []string{
+			"proxy-groups:\n  - name: %s\n    proxies: [%s]\nrules:\n  - MATCH,%s\n",
+			`{"outbounds":[{"tag":"%s","outbounds":["%s"]}],"route":{"final":"%s"}}`,
+			"[Proxy Group]\n%s = select, %s\n[Rule]\nFINAL,%s\n",
+		} {
+			raw := fmt.Sprintf(format, translation.zh, translation.zh, translation.zh)
+			want := fmt.Sprintf(format, translation.en, translation.en, translation.en)
+			if got := localizeSubscriptionTemplate(raw); got != want {
+				t.Errorf("translation of %q: got %q, want %q", translation.zh, got, want)
+			}
+			if got := localizeSubscriptionTemplate(want); got != want {
+				t.Errorf("translation is not idempotent: %q", got)
+			}
+		}
+	}
+}
diff --git a/internal/platform/i18n/business.go b/internal/platform/i18n/business.go
index e4f795d6..ba57e5c0 100644
--- a/internal/platform/i18n/business.go
+++ b/internal/platform/i18n/business.go
@@ -1,6 +1,11 @@
 package i18n
 
-import "strings"
+import (
+	"regexp"
+	"strings"
+)
+
+var canonicalSpacedNodeSuffix = regexp.MustCompile(`^( ?)(家宽|专属|AI解锁|保底|维护中)?( ?)[0-9]+( ?保底| ?维护中)?( ?💎)?$`)
 
 // LocalizeNodeName returns an explicit DB translation when present, otherwise
 // derives the English form of Yue's canonical node naming convention.
@@ -17,7 +22,11 @@ func LocalizeNodeName(locale, source, explicit string) string {
 	if strings.TrimSpace(explicit) != "" {
 		return explicit
 	}
-	rest, ok := strings.CutPrefix(source, "悦·")
+	prefix := "悦·"
+	if strings.HasPrefix(source, "悦 ·") {
+		prefix = "悦 ·"
+	}
+	rest, ok := strings.CutPrefix(source, prefix)
 	if !ok {
 		return source
 	}
@@ -48,6 +57,31 @@ func LocalizeNodeName(locale, source, explicit string) string {
 		{"🇷🇺俄罗斯", "🇷🇺 Russia"},
 	}
 	for _, country := range countries {
+		// R-14 names retain branding and separators, including attached ordinals.
+		flag, english, _ := strings.Cut(country.en, " ")
+		chinese := strings.TrimPrefix(country.zh, flag)
+		for _, separator := range []string{"", " "} {
+			countryPrefix := flag + separator + chinese
+			brandSpace := ""
+			candidate := rest
+			if strings.HasPrefix(candidate, " ") {
+				brandSpace = " "
+				candidate = strings.TrimPrefix(candidate, " ")
+			}
+			suffix, matched := strings.CutPrefix(candidate, countryPrefix)
+			spaced := prefix == "悦 ·" || brandSpace != "" || separator != ""
+			if !matched || !spaced {
+				continue
+			}
+			if !canonicalSpacedNodeSuffix.MatchString(suffix) {
+				return source
+			}
+			suffix = strings.NewReplacer(
+				"家宽", "Residential", "专属", "Dedicated", "AI解锁", "AI Unlocked",
+				"保底", "Fallback", "维护中", "Maintenance",
+			).Replace(suffix)
+			return prefix + brandSpace + flag + separator + english + suffix
+		}
 		if !strings.HasPrefix(rest, country.zh) {
 			continue
 		}
diff --git a/internal/platform/i18n/business_test.go b/internal/platform/i18n/business_test.go
index 79e7a4b8..716c0095 100644
--- a/internal/platform/i18n/business_test.go
+++ b/internal/platform/i18n/business_test.go
@@ -38,3 +38,39 @@ func TestLocalizeServerGroupName(t *testing.T) {
 		t.Fatal(got)
 	}
 }
+
+func TestLocalizeNodeNamePreservesR14Spacing(t *testing.T) {
+	for source, want := range map[string]string{
+		"悦 · 🇭🇰 香港1":        "悦 · 🇭🇰 Hong Kong1",
+		"悦 · 🇭🇰 香港家宽1💎":     "悦 · 🇭🇰 Hong KongResidential1💎",
+		"悦 · 🇯🇵 日本 专属 2 💎":  "悦 · 🇯🇵 Japan Dedicated 2 💎",
+		"悦 · 🇺🇸 美国 AI解锁12💎": "悦 · 🇺🇸 United States AI Unlocked12💎",
+		"悦 · 🇸🇬 新加坡保底1":     "悦 · 🇸🇬 SingaporeFallback1",
+		"悦 · 🇩🇪 德国维护中2":     "悦 · 🇩🇪 GermanyMaintenance2",
+		"悦 · 🇹🇼 台湾1 保底 💎":   "悦 · 🇹🇼 Taiwan1 Fallback 💎",
+		"悦 · 🇬🇧 英国1 维护中":    "悦 · 🇬🇧 United Kingdom1 Maintenance",
+		"悦·🇭🇰 香港1":          "悦·🇭🇰 Hong Kong1",
+		"悦 ·🇭🇰香港1":          "悦 ·🇭🇰Hong Kong1",
+		"悦 · 🇳🇿新西兰2":        "悦 · 🇳🇿New Zealand2",
+	} {
+		t.Run(source, func(t *testing.T) {
+			if got := LocalizeNodeName(En, source, ""); got != want {
+				t.Errorf("got %q, want %q", got, want)
+			}
+			if got := LocalizeNodeName(ZhCN, source, "Override"); got != source {
+				t.Errorf("Chinese name changed to %q", got)
+			}
+			if got := LocalizeNodeName(En, source, "Override"); got != "Override" {
+				t.Errorf("explicit translation lost: %q", got)
+			}
+		})
+	}
+	for _, source := range []string{
+		"悦 · 🇭🇰 香港beta", "悦 · 🇭🇰 香港", "悦 · 未知1",
+		"悦 · 🇭🇰 香港1 custom", "悦 · 🇭🇰 香港1💎💎", "悦 · 🇯🇵 香港1",
+	} {
+		if got := LocalizeNodeName(En, source, ""); got != source {
+			t.Errorf("custom name %q changed to %q", source, got)
+		}
+	}
+}

exec
/bin/zsh -lc 'git diff -U100 c5dd144ca477566cf002159aaba638491ac2a2a9 46fa9355be9b8ab5ab5110eddbd8b086581bced2 -- internal/modules/subscribe/display_name.go internal/platform/i18n/business.go; git log --format=fuller c5dd144ca477566cf002159aaba638491ac2a2a9..46fa9355be9b8ab5ab5110eddbd8b086581bced2' in /Users/j/codex-runs/mh1105/yb-156
 succeeded in 0ms:
diff --git a/internal/modules/subscribe/display_name.go b/internal/modules/subscribe/display_name.go
index 8dd43d58..74815985 100644
--- a/internal/modules/subscribe/display_name.go
+++ b/internal/modules/subscribe/display_name.go
@@ -1,196 +1,200 @@
 package subscribe
 
 import (
 	"fmt"
 	"net/url"
 	"regexp"
 	"regexp/syntax"
 	"strings"
 	"unicode"
 	"unicode/utf8"
 )
 
 // Order breaks equal-position ties only when they identify the same region.
 // Empty labels deliberately mark ambiguous geographical tokens.
 var displayRegions = []struct {
 	region string
 	tokens []string
 }{
 	{"香港", []string{"🇭🇰", "香港", "Hong Kong", "HongKong", "HK"}},
 	{"台湾", []string{"🇹🇼", "台湾", "台灣", "台北", "Taiwan", "Taipei", "TW"}},
 	{"日本", []string{"🇯🇵", "日本", "东京", "東京", "大阪", "Japan", "Tokyo", "Osaka", "JP"}},
 	{"新加坡", []string{"🇸🇬", "新加坡", "狮城", "Singapore", "SG"}},
 	{"美国", []string{"🇺🇸", "美国", "美國", "洛杉矶", "纽约", "西雅图", "圣何塞", "United States", "USA", "US", "Los Angeles", "New York", "Seattle", "San Jose"}},
 	{"韩国", []string{"🇰🇷", "韩国", "韓國", "首尔", "Seoul", "South Korea", "KR"}},
 	{"英国", []string{"🇬🇧", "英国", "英國", "伦敦", "United Kingdom", "London", "UK", "GB"}},
 	{"德国", []string{"🇩🇪", "德国", "德國", "法兰克福", "Germany", "Frankfurt", "DE"}},
 	{"法国", []string{"🇫🇷", "法国", "法國", "巴黎", "France", "Paris", "FR"}},
 	{"加拿大", []string{"🇨🇦", "加拿大", "多伦多", "温哥华", "Canada", "Toronto", "Vancouver", "CA"}},
 	{"澳大利亚", []string{"🇦🇺", "澳大利亚", "悉尼", "墨尔本", "Australia", "Sydney", "Melbourne", "AU"}},
 	{"荷兰", []string{"🇳🇱", "荷兰", "阿姆斯特丹", "Netherlands", "Amsterdam", "NL"}},
 	{"印度", []string{"🇮🇳", "印度", "孟买", "India", "Mumbai", "IN"}},
 	{"", []string{"Korea", "刚果", "Congo", "Georgia", "圣何塞", "San Jose"}},
 }
 
 func displayRegion(name string) string {
 	lower := strings.ToLower(name)
 	position, region := len(lower)+1, ""
 	ambiguous := false
 	for _, entry := range displayRegions {
 		for _, token := range entry.tokens {
 			token = strings.ToLower(token)
 			offset := 0
 			for offset <= len(lower) {
 				index := strings.Index(lower[offset:], token)
 				if index < 0 {
 					break
 				}
 				index += offset
 				end := index + len(token)
 				// Latin aliases are whole tokens, with optional numeric node suffixes.
 				latin := token[0] < utf8.RuneSelf
 				before, _ := utf8.DecodeLastRuneInString(lower[:index])
 				after, _ := utf8.DecodeRuneInString(lower[end:])
 				bounded := !latin || (!unicode.IsLetter(before) && !unicode.IsLetter(after))
 				if bounded && index <= position {
 					if index < position {
 						position, region, ambiguous = index, entry.region, entry.region == ""
 					} else if region != entry.region {
 						ambiguous = true
 					}
 				}
 				offset = end
 			}
 		}
 	}
 	// An earlier unrecognized flag is evidence of an unknown region, not
 	// permission to use a later transit/destination token.
 	for index, r := range lower {
 		if r >= '\U0001F1E6' && r <= '\U0001F1FF' && index < position {
 			return ""
 		}
 	}
 	if ambiguous {
 		return ""
 	}
 	return region
 }
 
 // Copy the complete multiplier spelling, including brackets and internal spaces.
 // Never derive, round, or normalize a billing value here.
 const displayMultiplierCore = `(?:倍率[ \t]*[:：=]?[ \t]*[0-9]+(?:\.[0-9]+)?[x×✕*]?|[x×✕*][ \t]*[0-9]+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?(?:[ \t]*倍(?:率)?|[x×✕*]))`
 
 // Each alternative is a complete token with paired delimiters. No arbitrary
 // bracket contents or numeric continuation may be swallowed by a partial match.
 var displayMultiplier = regexp.MustCompile(`(?i)(?:\[[ \t]*` + displayMultiplierCore + `[ \t]*\]|【[ \t]*` + displayMultiplierCore + `[ \t]*】|\([ \t]*` + displayMultiplierCore + `[ \t]*\)|（[ \t]*` + displayMultiplierCore + `[ \t]*）|` + displayMultiplierCore + `)`)
 
 // Unknown numeric units may carry billing information. Preserve them rather
 // than guess; plain numeric node ordinals remain eligible for display names.
 var displayDigitUnit = regexp.MustCompile(`\p{N}[\p{N}.,]*[\p{Z}\s]*[\p{L}\p{S}%‰]`)
 
 func prepareDisplayNames(servers []*serverRow) {
 	ordinals := map[string]int{}
 	for _, s := range servers {
 		if s == nil || s.placeholder || isSubscriptionNoticeName(s.Name) {
 			continue
 		}
+		name := strings.TrimSpace(s.Name)
+		if strings.HasPrefix(name, "悦 ·") || strings.HasPrefix(name, "悦·") {
+			continue
+		}
 		region := displayRegion(s.Name)
 		protocol := map[string]string{"vless": "VLESS", "hysteria": "Hysteria2"}[s.Type]
 		if region == "" || protocol == "" {
 			continue
 		}
 		ordinals[region]++
 		multipliers, safe := displayMultipliers(s.Name)
 		if !safe {
 			continue
 		}
 		s.DisplayName = fmt.Sprintf("%s %02d %s", region, ordinals[region], protocol)
 		for _, text := range multipliers {
 			s.DisplayName += " " + text
 		}
 	}
 }
 
 // Used only by renderers without name-dependent template selection. INI names
 // are sanitized before the shared final allocation, just as they are on output.
 func displayRows(servers []*serverRow, key func(string) string, emits func(*serverRow) bool) []*serverRow {
 	rows := make([]*serverRow, 0, len(servers))
 	originals := make([]string, 0, len(servers))
 	for _, s := range servers {
 		if s == nil || (emits != nil && !emits(s)) {
 			continue
 		}
 		copy := *s
 		rows = append(rows, &copy)
 		originals = append(originals, s.Name)
 	}
 	for i, name := range finalDisplayNames(rows, originals, nil, key) {
 		rows[i].Name = name
 	}
 	return rows
 }
 
 // Allocate the complete final namespace in one pass, with kept identities first.
 // Collision suffixes are separate from the name, preserving multiplier text.
 func finalDisplayNames(rows []*serverRow, originals, reserved []string, key func(string) string) []string {
 	names, indexes := []string{}, []int{}
 	for _, changing := range []bool{false, true} {
 		for i, original := range originals {
 			name := rows[i].DisplayName
 			if name == "" {
 				name = original
 			}
 			if (name != original) != changing {
 				continue
 			}
 			if key != nil {
 				name = key(name)
 			}
 			names = append(names, name)
 			indexes = append(indexes, i)
 		}
 	}
 	final := make([]string, len(originals))
 	for i, name := range uniqueNames(names, reserved, key) {
 		final[indexes[i]] = name
 	}
 	return final
 }
 
 // Template inventories include the emitted nodes themselves. Remove one entry
 // per identity before allocating; any additional template reservation remains.
 func displayAliases(rows []*serverRow, originals, reserved []string, key func(string) string) map[string]string {
 	if key == nil {
 		key = func(name string) string { return name }
 	}
 	own := map[string]int{}
 	for _, name := range originals {
 		own[key(name)]++
 	}
 	external := []string{}
 	for _, name := range reserved {
 		if own[key(name)] > 0 {
 			own[key(name)]--
 			continue
 		}
 		external = append(external, name)
 	}
 	aliases := map[string]string{}
 	for i, name := range finalDisplayNames(rows, originals, external, key) {
 		if name != originals[i] {
 			aliases[originals[i]] = name
 		}
 	}
 	return aliases
 }
 
 func displayAlias(name string, aliases map[string]string) string {
 	if renamed, ok := aliases[name]; ok {
 		return renamed
 	}
 	return name
 }
 
 // Reference-only traversal; passwords, endpoints, expressions and group names
 // are not identities and must never be subjected to string replacement.
 func rewriteDisplayReferences(value any, aliases map[string]string) {
diff --git a/internal/platform/i18n/business.go b/internal/platform/i18n/business.go
index e4f795d6..ba57e5c0 100644
--- a/internal/platform/i18n/business.go
+++ b/internal/platform/i18n/business.go
@@ -1,111 +1,145 @@
 package i18n
 
-import "strings"
+import (
+	"regexp"
+	"strings"
+)
+
+var canonicalSpacedNodeSuffix = regexp.MustCompile(`^( ?)(家宽|专属|AI解锁|保底|维护中)?( ?)[0-9]+( ?保底| ?维护中)?( ?💎)?$`)
 
 // LocalizeNodeName returns an explicit DB translation when present, otherwise
 // derives the English form of Yue's canonical node naming convention.
 //
 // Derivation is deliberate: production nodes are routinely replaced and get a
 // new numeric suffix. Requiring every replacement to copy name_i18n would turn
 // an operational node swap into a translation outage. Names outside the strict
 // canonical grammar fail closed to their source value so an operator's custom
 // label is never guessed or mangled.
 func LocalizeNodeName(locale, source, explicit string) string {
 	if Normalize(locale) != En {
 		return source
 	}
 	if strings.TrimSpace(explicit) != "" {
 		return explicit
 	}
-	rest, ok := strings.CutPrefix(source, "悦·")
+	prefix := "悦·"
+	if strings.HasPrefix(source, "悦 ·") {
+		prefix = "悦 ·"
+	}
+	rest, ok := strings.CutPrefix(source, prefix)
 	if !ok {
 		return source
 	}
 	countries := [...]struct{ zh, en string }{
 		{"🇭🇰香港", "🇭🇰 Hong Kong"},
 		{"🇹🇼台湾", "🇹🇼 Taiwan"},
 		{"🇯🇵日本", "🇯🇵 Japan"},
 		{"🇺🇸美国", "🇺🇸 United States"},
 		{"🇸🇬新加坡", "🇸🇬 Singapore"},
 		{"🇲🇾马来西亚", "🇲🇾 Malaysia"},
 		{"🇮🇳印度", "🇮🇳 India"},
 		{"🇬🇧英国", "🇬🇧 United Kingdom"},
 		{"🇰🇷韩国", "🇰🇷 South Korea"},
 		{"🇻🇳越南", "🇻🇳 Vietnam"},
 		{"🇹🇭泰国", "🇹🇭 Thailand"},
 		{"🇩🇪德国", "🇩🇪 Germany"},
 		{"🇳🇱荷兰", "🇳🇱 Netherlands"},
 		{"🇪🇸西班牙", "🇪🇸 Spain"},
 		{"🇸🇪瑞典", "🇸🇪 Sweden"},
 		{"🇨🇦加拿大", "🇨🇦 Canada"},
 		{"🇧🇷巴西", "🇧🇷 Brazil"},
 		{"🇲🇽墨西哥", "🇲🇽 Mexico"},
 		{"🇦🇪阿联酋", "🇦🇪 United Arab Emirates"},
 		{"🇹🇷土耳其", "🇹🇷 Türkiye"},
 		{"🇦🇺澳大利亚", "🇦🇺 Australia"},
 		{"🇳🇬尼日利亚", "🇳🇬 Nigeria"},
 		{"🇳🇿新西兰", "🇳🇿 New Zealand"},
 		{"🇷🇺俄罗斯", "🇷🇺 Russia"},
 	}
 	for _, country := range countries {
+		// R-14 names retain branding and separators, including attached ordinals.
+		flag, english, _ := strings.Cut(country.en, " ")
+		chinese := strings.TrimPrefix(country.zh, flag)
+		for _, separator := range []string{"", " "} {
+			countryPrefix := flag + separator + chinese
+			brandSpace := ""
+			candidate := rest
+			if strings.HasPrefix(candidate, " ") {
+				brandSpace = " "
+				candidate = strings.TrimPrefix(candidate, " ")
+			}
+			suffix, matched := strings.CutPrefix(candidate, countryPrefix)
+			spaced := prefix == "悦 ·" || brandSpace != "" || separator != ""
+			if !matched || !spaced {
+				continue
+			}
+			if !canonicalSpacedNodeSuffix.MatchString(suffix) {
+				return source
+			}
+			suffix = strings.NewReplacer(
+				"家宽", "Residential", "专属", "Dedicated", "AI解锁", "AI Unlocked",
+				"保底", "Fallback", "维护中", "Maintenance",
+			).Replace(suffix)
+			return prefix + brandSpace + flag + separator + english + suffix
+		}
 		if !strings.HasPrefix(rest, country.zh) {
 			continue
 		}
 		suffix := strings.TrimPrefix(rest, country.zh)
 		kind := ""
 		for _, candidate := range [...]struct{ zh, en string }{
 			{"家宽", "Residential"},
 			{"专属", "Dedicated"},
 			{"AI解锁", "AI Unlocked"},
 		} {
 			if strings.HasPrefix(suffix, candidate.zh) {
 				kind = candidate.en
 				suffix = strings.TrimPrefix(suffix, candidate.zh)
 				break
 			}
 		}
 		if !canonicalNodeOrdinal(suffix) {
 			return source
 		}
 		parts := []string{"Yue ·", country.en}
 		if kind != "" {
 			parts = append(parts, kind)
 		}
 		parts = append(parts, suffix)
 		return strings.Join(parts, " ")
 	}
 	return source
 }
 
 func canonicalNodeOrdinal(value string) bool {
 	value = strings.TrimSuffix(value, "💎")
 	if value == "" {
 		return false
 	}
 	for _, r := range value {
 		if r < '0' || r > '9' {
 			return false
 		}
 	}
 	return true
 }
 
 // LocalizeServerGroupName follows the same explicit-override/derived-default
 // contract as node names. Only the two canonical production group names are
 // derived; custom operator labels remain untouched.
 func LocalizeServerGroupName(locale, source, explicit string) string {
 	if Normalize(locale) != En {
 		return source
 	}
 	if strings.TrimSpace(explicit) != "" {
 		return explicit
 	}
 	switch source {
 	case "专属":
 		return "Dedicated"
 	case "Yue":
 		return "Yue"
 	default:
 		return source
 	}
 }
commit 46fa9355be9b8ab5ab5110eddbd8b086581bced2
Author:     onesyue <47652916+onesyue@users.noreply.github.com>
AuthorDate: Thu Nov 5 11:00:56 2026 +0800
Commit:     onesyue <47652916+onesyue@users.noreply.github.com>
CommitDate: Thu Nov 5 11:00:56 2026 +0800

    fix(subscribe,i18n): keep R-14 branded node names (悦 · 🇭🇰 香港1)
    
    - display_name: skip region/ordinal/protocol rewrite for 悦 ·/悦· names
    - i18n LocalizeNodeName: accept spaced 悦 · and flag+space+country
    - template_i18n: accept spaced group keys (悦 · 🇭🇰 香港聚合)
    - tests; design reference updated to spaced form

codex
- No actionable correctness, regression, or security issues found in the specified diff.
- Changes match the stated intent; existing tests remain intact, with added coverage for branded names and translations.
- Static review only; tests were not run.

VERDICT: approve
tokens used
23,832
- No actionable correctness, regression, or security issues found in the specified diff.
- Changes match the stated intent; existing tests remain intact, with added coverage for branded names and translations.
- Static review only; tests were not run.

VERDICT: approve
Finished: 2026-11-05T03:45:36Z exit=0
