# yueboard #153 review at 9a5daa7940cf4e491517eeab920fda42c05cdc6f

Reviewed range: 92e0b56c2be1524a64ee7a5cd5e654e53821e311..9a5daa7940cf4e491517eeab920fda42c05cdc6f (post-merge backfill; codex on mac-5f08d00f, read-only sandbox)
Started: 2026-11-05T03:05:06Z

Reading additional input from stdin...
OpenAI Codex v0.166.0
--------
workdir: /Users/j/codex-runs/mh1105/yb-153
model: gpt-6-astra
provider: openai
approval: never
sandbox: read-only
reasoning effort: medium
reasoning summaries: none
session id: 01a1a9aa-d18e-70c0-8e19-08a980ce608f
--------
user
You are reviewing merged PR onesyue/yueboard #153 at exact head 9a5daa7940cf4e491517eeab920fda42c05cdc6f. Review ONLY the diff: git diff 92e0b56c2be1524a64ee7a5cd5e654e53821e311 9a5daa7940cf4e491517eeab920fda42c05cdc6f (and git log 92e0b56c2be1524a64ee7a5cd5e654e53821e311..9a5daa7940cf4e491517eeab920fda42c05cdc6f). Do not modify files. Check correctness, regressions, weakened/removed tests, security, and that the change matches its title/intent. Output a final line exactly 'VERDICT: approve' or 'VERDICT: changes' followed by concise bullet findings.
2026-11-05T03:05:11.677828Z ERROR codex_models_manager::manager: failed to refresh available models: request timed out
codex
I’ll read the repository guidance, then review only the specified commit range and diff without modifying files.
exec
/bin/zsh -lc 'pwd; cat CLAUDE.md; git status --short; git log --oneline 92e0b56c2be1524a64ee7a5cd5e654e53821e311..9a5daa7940cf4e491517eeab920fda42c05cdc6f; git diff --stat 92e0b56c2be1524a64ee7a5cd5e654e53821e311 9a5daa7940cf4e491517eeab920fda42c05cdc6f' in /Users/j/codex-runs/mh1105/yb-153
 succeeded in 0ms:
/Users/j/codex-runs/mh1105/yb-153
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
error: fsmonitor_ipc__send_query: unspecified error on '/Users/j/Projects/yueto/yueboard/.git/worktrees/yb-153/fsmonitor--daemon.ipc'
9a5daa79 ui: unify board user+admin visuals on shared tokens (#0A84FF), cards/states
 packages/ui/src/page.tsx               |  13 +--
 packages/ui/src/tokens.css             |  29 +++++--
 packages/ui/src/ui/card.tsx            |   2 +-
 packages/ui/src/ui/switch.tsx          |   2 +-
 packages/ui/src/ui/tabs.tsx            |   2 +-
 web-admin/src/index.css                |  24 ++----
 web-admin/src/routes/login.tsx         |   4 +-
 web/src/components/growth/surfaces.css | 150 ++++++++++++++++-----------------
 web/src/components/onboarding.css      |   2 +-
 web/src/index.css                      |  20 +----
 web/src/routes/_app/traffic.tsx        |   4 +-
 11 files changed, 122 insertions(+), 130 deletions(-)

exec
/bin/zsh -lc 'for f in ../AGENTS.md ../CLAUDE.md; do if test -f "$f"; then cat "$f"; fi; done; git diff 92e0b56c2be1524a64ee7a5cd5e654e53821e311 9a5daa7940cf4e491517eeab920fda42c05cdc6f; git log --format=fuller 92e0b56c2be1524a64ee7a5cd5e654e53821e311..9a5daa7940cf4e491517eeab920fda42c05cdc6f' in /Users/j/codex-runs/mh1105/yb-153
 succeeded in 0ms:
diff --git a/packages/ui/src/page.tsx b/packages/ui/src/page.tsx
index f3d8b138..deda7aad 100644
--- a/packages/ui/src/page.tsx
+++ b/packages/ui/src/page.tsx
@@ -9,6 +9,7 @@ import {
 } from "./loading-phase";
 import { cn } from "./utils";
 import { Button } from "./ui/button";
+import { Card } from "./ui/card";
 import { Skeleton } from "./ui/skeleton";
 
 export interface PageProps {
@@ -125,11 +126,11 @@ function SkeletonBody({ shape, rows, columns }: { shape: LoadingShape; rows: num
         style={{ gridTemplateColumns: `repeat(${Math.max(1, columns)}, minmax(0, 1fr))` }}
       >
         {Array.from({ length: rows }).map((_, r) => (
-          <div key={r} className="grid grid-cols-1 gap-3 rounded-xl border bg-card p-[var(--density-card-padding)]">
+          <Card data-slot="card-skeleton" key={r} className="grid grid-cols-1 gap-3 p-[var(--density-card-padding)]">
             <Skeleton className="h-4 w-1/3" />
             <Skeleton className="h-8 w-1/2" />
             <Skeleton className="h-3 w-2/3" />
-          </div>
+          </Card>
         ))}
       </div>
     );
@@ -218,7 +219,7 @@ export interface EmptyStateProps {
 export function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
   return (
     <div
-      className={cn("grid grid-cols-1 min-h-40 place-items-center gap-2 px-6 py-12 text-center", className)}
+      className={cn("grid grid-cols-1 min-h-40 place-items-center gap-2 rounded-card border border-dashed bg-muted/30 px-[var(--density-card-padding)] py-12 text-center", className)}
       role="status"
     >
       {icon ? <div className="text-muted-foreground [&_svg]:size-8">{icon}</div> : null}
@@ -272,7 +273,7 @@ export function ErrorState({
   return (
     <div
       className={cn(
-        "flex min-h-28 items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-4",
+        "flex min-h-28 items-start gap-3 rounded-card border border-destructive/30 bg-destructive/5 p-[var(--density-card-padding)]",
         className,
       )}
       role="alert"
@@ -470,7 +471,7 @@ export function StatCard({
   className,
 }: StatCardProps) {
   return (
-    <div className={cn("rounded-xl border bg-card p-[var(--density-card-padding)] shadow-soft", className)}>
+    <Card data-slot="stat-card" className={cn("gap-0 p-[var(--density-card-padding)]", className)}>
       <div className="flex items-center justify-between gap-2">
         <span className="text-xs font-medium text-muted-foreground">{label}</span>
         {icon ? <span className="text-tx3 [&_svg]:size-4">{icon}</span> : null}
@@ -496,6 +497,6 @@ export function StatCard({
         </div>
         {trend ? <div className="shrink-0 pb-0.5">{trend}</div> : null}
       </div>
-    </div>
+    </Card>
   );
 }
diff --git a/packages/ui/src/tokens.css b/packages/ui/src/tokens.css
index 0a7a679d..3762a844 100644
--- a/packages/ui/src/tokens.css
+++ b/packages/ui/src/tokens.css
@@ -136,14 +136,14 @@
   --elevation-overlay: 0 20px 50px -20px rgb(9 9 11 / 0.28);
 
   /* Comfortable is the consumer default; admin overrides only this density layer. */
-  --density-page-gap: 1.5rem;
-  --density-section-gap: 1rem;
+  --density-page-gap: var(--space-6);
+  --density-section-gap: var(--space-4);
   --density-control-height: 2.5rem;
   --density-control-height-sm: 2.25rem;
   --density-table-head-height: 2.75rem;
-  --density-table-cell-y: 0.75rem;
-  --density-card-padding: 1.5rem;
-  --density-card-gap: 1.5rem;
+  --density-table-cell-y: var(--space-3);
+  --density-card-padding: var(--space-6);
+  --density-card-gap: var(--space-6);
 
   /* shadcn compatibility aliases. */
   --background: var(--surface-canvas);
@@ -869,3 +869,22 @@
   --accent-foreground: var(--foreground);
   --ring: var(--yt-action-primary);
 }
+
+/* Shared keyboard skip target for both SPA shells. Route-focus behavior stays
+   in each shell; only this visual treatment is shared. */
+@layer components {
+  .app-skip-link {
+    position: fixed;
+    z-index: 100;
+    top: var(--space-3);
+    left: var(--space-3);
+    transform: translateY(-200%);
+    border-radius: var(--radius-8);
+    background: var(--action-fill);
+    color: var(--primary-foreground);
+    padding: var(--space-3) var(--space-4);
+    font-size: var(--text-body);
+    font-weight: 600;
+  }
+  .app-skip-link:focus { transform: translateY(0); }
+}
diff --git a/packages/ui/src/ui/card.tsx b/packages/ui/src/ui/card.tsx
index 064da53c..6cfe6ec7 100644
--- a/packages/ui/src/ui/card.tsx
+++ b/packages/ui/src/ui/card.tsx
@@ -7,7 +7,7 @@ function Card({ className, ...props }: React.ComponentProps<"div">) {
     <div
       data-slot="card"
       className={cn(
-        "flex flex-col gap-[var(--density-card-gap)] rounded-xl border bg-card py-[var(--density-card-padding)] text-card-foreground shadow-soft",
+        "flex min-w-0 flex-col gap-[var(--density-card-gap)] rounded-card border bg-card py-[var(--density-card-padding)] text-card-foreground shadow-soft",
         className
       )}
       {...props}
diff --git a/packages/ui/src/ui/switch.tsx b/packages/ui/src/ui/switch.tsx
index d0be22d3..22f00803 100644
--- a/packages/ui/src/ui/switch.tsx
+++ b/packages/ui/src/ui/switch.tsx
@@ -33,7 +33,7 @@ function Switch({
       <SwitchPrimitive.Thumb
         data-slot="switch-thumb"
         className={cn(
-          "pointer-events-none block size-4 rounded-full bg-background shadow-sm ring-0 transition-transform duration-[var(--spring-space-fast-duration)] ease-[var(--spring-space-fast)] data-[state=checked]:translate-x-4 data-[state=unchecked]:translate-x-0.5 dark:data-[state=unchecked]:bg-foreground dark:data-[state=checked]:bg-primary-foreground"
+          "pointer-events-none block size-4 rounded-full bg-background shadow-soft ring-0 transition-transform duration-[var(--spring-space-fast-duration)] ease-[var(--spring-space-fast)] data-[state=checked]:translate-x-4 data-[state=unchecked]:translate-x-0.5 dark:data-[state=unchecked]:bg-foreground dark:data-[state=checked]:bg-primary-foreground"
         )}
       />
     </SwitchPrimitive.Root>
diff --git a/packages/ui/src/ui/tabs.tsx b/packages/ui/src/ui/tabs.tsx
index d9f0290d..ce7b9c7e 100644
--- a/packages/ui/src/ui/tabs.tsx
+++ b/packages/ui/src/ui/tabs.tsx
@@ -62,7 +62,7 @@ function TabsTrigger({
     <TabsPrimitive.Trigger
       data-slot="tabs-trigger"
       className={cn(
-        "relative inline-flex h-[calc(100%-1px)] flex-1 items-center justify-center gap-1.5 rounded-md border border-transparent px-2 py-1 text-sm font-medium whitespace-nowrap text-muted-foreground transition-[background-color,border-color,color,box-shadow] duration-[var(--motion-base)] ease-[var(--motion-ease)] group-data-[orientation=vertical]/tabs:w-full group-data-[orientation=vertical]/tabs:justify-start hover:text-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-1 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-50 group-data-[variant=default]/tabs-list:data-[state=active]:shadow-sm group-data-[variant=line]/tabs-list:data-[state=active]:shadow-none dark:text-muted-foreground dark:hover:text-foreground [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
+        "relative inline-flex h-[calc(100%-1px)] flex-1 items-center justify-center gap-1.5 rounded-md border border-transparent px-2 py-1 text-sm font-medium whitespace-nowrap text-muted-foreground transition-[background-color,border-color,color,box-shadow] duration-[var(--motion-base)] ease-[var(--motion-ease)] group-data-[orientation=vertical]/tabs:w-full group-data-[orientation=vertical]/tabs:justify-start hover:text-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-1 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-50 group-data-[variant=default]/tabs-list:data-[state=active]:shadow-soft group-data-[variant=line]/tabs-list:data-[state=active]:shadow-none dark:text-muted-foreground dark:hover:text-foreground [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
         "group-data-[variant=line]/tabs-list:bg-transparent group-data-[variant=line]/tabs-list:data-[state=active]:bg-transparent dark:group-data-[variant=line]/tabs-list:data-[state=active]:border-transparent dark:group-data-[variant=line]/tabs-list:data-[state=active]:bg-transparent",
         "data-[state=active]:bg-background data-[state=active]:text-foreground dark:data-[state=active]:border-input dark:data-[state=active]:bg-input/30 dark:data-[state=active]:text-foreground",
         "after:absolute after:bg-foreground after:opacity-0 after:transition-opacity group-data-[orientation=horizontal]/tabs:after:inset-x-0 group-data-[orientation=horizontal]/tabs:after:bottom-[-5px] group-data-[orientation=horizontal]/tabs:after:h-0.5 group-data-[orientation=vertical]/tabs:after:inset-y-0 group-data-[orientation=vertical]/tabs:after:-right-1 group-data-[orientation=vertical]/tabs:after:w-0.5 group-data-[variant=line]/tabs-list:data-[state=active]:after:opacity-100",
diff --git a/web-admin/src/index.css b/web-admin/src/index.css
index 14b22cca..c776acd1 100644
--- a/web-admin/src/index.css
+++ b/web-admin/src/index.css
@@ -20,17 +20,17 @@
 
 /* Admin uses the same visual language with denser controls, tables, cards and page rhythm. */
 :root {
-  --density-page-gap: 1.25rem;
-  --density-section-gap: 0.75rem;
+  --density-page-gap: var(--space-5);
+  --density-section-gap: var(--space-3);
   --density-control-height: 2.25rem;
-  --density-control-height-sm: 2rem;
+  --density-control-height-sm: var(--space-8);
   --density-table-head-height: 2.25rem;
   /* 行高由「最高的行内元素 + 上下内边距」决定，而管理端每一行的最高元素是 32px 的
      图标按钮：8+32+8+1 = 49px，一屏只有 13 行。2026 dense 表格基准是 40–44px。
      收到 6px 后是 45px —— 再往下就得把行内按钮也缩小，那会牺牲点击目标，不换。 */
   --density-table-cell-y: 0.375rem;
-  --density-card-padding: 1.25rem;
-  --density-card-gap: 1rem;
+  --density-card-padding: var(--space-5);
+  --density-card-gap: var(--space-4);
 }
 
 @layer components {
@@ -61,20 +61,6 @@
   #main-content[data-route-focus]:focus-visible {
     outline: none;
   }
-  .app-skip-link {
-    position: fixed;
-    z-index: 100;
-    top: 0.75rem;
-    left: 0.75rem;
-    transform: translateY(-200%);
-    border-radius: 0.5rem;
-    background: var(--action-fill);
-    color: var(--primary-foreground);
-    padding: 0.625rem 0.875rem;
-    font-size: 0.875rem;
-    font-weight: 600;
-  }
-  .app-skip-link:focus { transform: translateY(0); }
 }
 
 /* Global reduced-motion rules come from @yueto/ui/tokens.css. */
diff --git a/web-admin/src/routes/login.tsx b/web-admin/src/routes/login.tsx
index c435dce6..8dc5fc47 100644
--- a/web-admin/src/routes/login.tsx
+++ b/web-admin/src/routes/login.tsx
@@ -155,10 +155,10 @@ function LoginPage() {
         <LanguageMenu />
         <ThemeToggle />
       </div>
-      <Card className="relative w-full max-w-md shadow-[var(--shadow-overlay)]">
+      <Card className="relative w-full max-w-md shadow-overlay">
         <CardHeader className="gap-4">
           <div className="flex items-center gap-3">
-            <span className="grid grid-cols-1 size-11 shrink-0 place-items-center rounded-xl bg-action-fill text-primary-foreground shadow-sm">
+            <span className="grid grid-cols-1 size-11 shrink-0 place-items-center rounded-xl bg-action-fill text-primary-foreground shadow-soft">
               {/* 与壳层侧边栏同一枚悦通品牌笔画标 */}
               <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true">
                 <path d="M4 17L10 7M10 17L16 7M16 17L20 10" />
diff --git a/web/src/components/growth/surfaces.css b/web/src/components/growth/surfaces.css
index bd8fc1db..90c89551 100644
--- a/web/src/components/growth/surfaces.css
+++ b/web/src/components/growth/surfaces.css
@@ -15,23 +15,23 @@
   max-width: 760px;
   margin: 0 auto;
   color: var(--growth-ink);
-  padding-bottom: 32px;
+  padding-bottom: var(--space-8);
 }
 .growth-heading {
-  padding: 12px 0 28px;
+  padding: var(--space-3) 0 calc(var(--space-6) + var(--space-1));
 }
 .growth-eyebrow {
-  font-size: 11px;
+  font-size: var(--text-micro);
   font-weight: 600;
   letter-spacing: 0.12em;
   color: var(--growth-muted);
 }
 .growth-heading h1 {
-  font-size: 30px;
+  font-size: var(--text-display-sm);
   line-height: 1.2;
   font-weight: 600;
   letter-spacing: -0.03em;
-  margin: 12px 0;
+  margin: var(--space-3) 0;
 }
 .growth-root p {
   line-height: 1.65;
@@ -42,37 +42,37 @@
 .growth-form p,
 .growth-empty p {
   color: var(--growth-muted);
-  font-size: 14px;
+  font-size: var(--text-body);
 }
 .growth-paper {
   background: var(--growth-paper);
   border: 1px solid var(--growth-border);
-  border-radius: 24px;
+  border-radius: var(--radius-16);
   overflow: hidden;
-  margin-bottom: 20px;
+  margin-bottom: var(--space-5);
 }
 .growth-root h2 {
-  font-size: 24px;
+  font-size: var(--text-heading);
   font-weight: 600;
   line-height: 1.3;
   letter-spacing: -0.025em;
-  margin: 20px 0 12px;
+  margin: var(--space-5) 0 var(--space-3);
 }
 .growth-root h3 {
-  font-size: 18px;
+  font-size: var(--text-title);
   font-weight: 600;
   line-height: 1.4;
-  margin: 8px 0;
+  margin: var(--space-2) 0;
 }
 .growth-form {
   display: grid;
-  gap: 20px;
-  padding: 8px 0 24px;
+  gap: var(--space-5);
+  padding: var(--space-2) 0 var(--space-6);
 }
 .growth-form label:not(.growth-check) {
   display: grid;
-  gap: 8px;
-  font-size: 13px;
+  gap: var(--space-2);
+  font-size: var(--text-label);
   font-weight: 500;
 }
 .growth-root input:not([type="checkbox"]),
@@ -82,8 +82,8 @@
   width: 100%;
   min-height: 48px;
   border: 1px solid var(--growth-border);
-  border-radius: 12px;
-  padding: 12px 16px;
+  border-radius: var(--radius-12);
+  padding: var(--space-3) var(--space-4);
   color: var(--growth-ink);
   background: var(--growth-paper);
   font: inherit;
@@ -98,18 +98,18 @@
 }
 .growth-primary {
   min-height: 48px;
-  padding: 12px 20px;
+  padding: var(--space-3) var(--space-5);
   width: 100%;
   border: 0;
-  border-radius: 12px;
+  border-radius: var(--radius-12);
   display: flex;
   justify-content: center;
   align-items: center;
-  gap: 12px;
+  gap: var(--space-3);
   color: var(--growth-on-brand);
   background: var(--growth-action);
   font: inherit;
-  font-size: 14px;
+  font-size: var(--text-body);
   font-weight: 600;
   cursor: pointer;
 }
@@ -120,31 +120,31 @@
 .growth-check {
   display: flex;
   align-items: start;
-  gap: 12px;
-  font-size: 13px;
+  gap: var(--space-3);
+  font-size: var(--text-label);
   line-height: 1.6;
   cursor: pointer;
 }
 .growth-check input {
   width: 18px;
   height: 18px;
-  margin: 2px 0;
+  margin: calc(var(--space-1) / 2) 0;
   flex-shrink: 0;
   accent-color: var(--growth-brand);
 }
 .growth-metrics {
   display: grid;
   grid-template-columns: repeat(2, minmax(0, 1fr));
-  gap: 24px;
-  margin: 24px 0;
+  gap: var(--space-6);
+  margin: var(--space-6) 0;
 }
 .growth-metric dt {
-  font-size: 12px;
+  font-size: var(--text-caption);
   color: var(--growth-muted);
-  margin-bottom: 8px;
+  margin-bottom: var(--space-2);
 }
 .growth-metric dd {
-  font-size: 24px;
+  font-size: var(--text-heading);
   font-weight: 600;
   letter-spacing: -0.02em;
   margin: 0;
@@ -152,7 +152,7 @@
   font-variant-numeric: tabular-nums;
 }
 .growth-metric small {
-  font-size: 14px;
+  font-size: var(--text-body);
   font-weight: 400;
   color: var(--growth-muted);
 }
@@ -160,11 +160,11 @@
   display: flex;
   align-items: center;
   justify-content: space-between;
-  gap: 12px;
+  gap: var(--space-3);
   list-style: none;
   min-height: 56px;
   cursor: pointer;
-  font-size: 14px;
+  font-size: var(--text-body);
   font-weight: 500;
 }
 .growth-root summary::-webkit-details-marker {
@@ -175,11 +175,11 @@
 }
 .growth-footnote {
   color: var(--growth-muted);
-  font-size: 12px;
-  margin: 12px 0 !important;
+  font-size: var(--text-caption);
+  margin: var(--space-3) 0 !important;
 }
 .growth-empty {
-  padding: 40px 32px;
+  padding: var(--space-10) var(--space-8);
   text-align: center;
 }
 .growth-empty > svg {
@@ -189,25 +189,25 @@
   display: flex;
   align-items: center;
   justify-content: space-between;
-  gap: 16px;
-  margin: 0 0 24px;
-  font-size: 12px;
+  gap: var(--space-4);
+  margin: 0 0 var(--space-6);
+  font-size: var(--text-caption);
   color: var(--growth-muted);
 }
 .growth-auto > span:first-child {
   display: flex;
   align-items: center;
-  gap: 8px;
+  gap: var(--space-2);
   color: var(--growth-ink);
 }
 .growth-dot {
   width: 6px;
   height: 6px;
-  border-radius: 9999px;
+  border-radius: var(--radius-pill);
   background: var(--growth-brand);
 }
 .growth-memory {
-  padding: 32px;
+  padding: var(--space-8);
 }
 .growth-memory-top {
   display: flex;
@@ -216,97 +216,97 @@
   color: var(--growth-brand);
 }
 .growth-memory h2 {
-  margin-top: 32px;
+  margin-top: var(--space-8);
 }
 .growth-memory-number {
-  font-size: 36px;
+  font-size: var(--text-display);
   font-weight: 600;
   letter-spacing: -0.04em;
   color: var(--growth-brand);
-  margin: 32px 0 8px;
+  margin: var(--space-8) 0 var(--space-2);
   line-height: 1.1;
 }
 .growth-memory-number > span {
-  font-size: 14px;
+  font-size: var(--text-body);
   font-weight: 400;
   letter-spacing: 0;
-  margin-left: 12px;
+  margin-left: var(--space-3);
   color: var(--growth-muted);
 }
 .growth-memory-caption {
-  font-size: 14px;
+  font-size: var(--text-body);
   color: var(--growth-muted);
 }
 .growth-memory-rule {
   height: 1px;
   background: var(--growth-border);
-  margin: 32px 0;
+  margin: var(--space-8) 0;
 }
 .growth-achievements {
   display: flex;
   flex-wrap: wrap;
-  gap: 8px 16px;
-  margin-top: 24px;
-  font-size: 12px;
+  gap: var(--space-2) var(--space-4);
+  margin-top: var(--space-6);
+  font-size: var(--text-caption);
   color: var(--growth-muted);
 }
 .growth-achievements > span {
   display: inline-flex;
   align-items: center;
-  gap: 4px;
+  gap: var(--space-1);
 }
 .growth-memory-signature {
   display: flex;
   flex-wrap: wrap;
   justify-content: space-between;
-  gap: 8px;
+  gap: var(--space-2);
   align-items: center;
   border-top: 1px solid var(--growth-border);
-  padding-top: 24px;
-  margin-top: 32px;
-  font-size: 12px;
+  padding-top: var(--space-6);
+  margin-top: var(--space-8);
+  font-size: var(--text-caption);
   color: var(--growth-muted);
 }
 .growth-memory-signature > span:first-child {
   font-weight: 600;
-  font-size: 16px;
+  font-size: var(--text-body-lg);
   color: var(--growth-ink);
 }
 .growth-center {
   text-align: center;
 }
 .growth-settings {
-  padding: 0 24px;
-  margin-top: 24px;
+  padding: 0 var(--space-6);
+  margin-top: var(--space-6);
 }
 .growth-settings summary > span {
   flex: 1;
 }
 .growth-settings .growth-form {
-  padding-top: 16px;
+  padding-top: var(--space-4);
 }
 .growth-loading {
   display: grid;
-  gap: 12px;
-  padding: 32px;
+  gap: var(--space-3);
+  padding: var(--space-8);
 }
 .growth-loading span {
   height: 20px;
   background: var(--growth-subtle);
-  border-radius: 8px;
+  border-radius: var(--radius-8);
 }
 .growth-loading span:last-child {
   width: 60%;
 }
 @media (max-width: 480px) {
   .growth-memory {
-    padding: 24px;
+    padding: var(--space-6);
   }
   .growth-empty {
-    padding: 32px 24px;
+    padding: var(--space-8) var(--space-6);
   }
   .growth-heading {
-    padding-top: 8px;
+    padding-top: var(--space-2);
   }
 }
 
@@ -314,8 +314,8 @@
   display: flex;
   align-items: center;
   justify-content: space-between;
-  gap: 16px;
-  margin: 0 0 20px;
+  gap: var(--space-4);
+  margin: 0 0 var(--space-5);
   flex-wrap: wrap;
 }
 .growth-segments {
@@ -323,16 +323,16 @@
   margin: 0;
   min-width: 0;
   display: inline-flex;
-  padding: 4px;
+  padding: var(--space-1);
   background: var(--growth-subtle);
-  border-radius: 999px;
+  border-radius: var(--radius-pill);
 }
 .growth-segments button {
   border: 0;
   background: transparent;
   color: var(--growth-muted);
-  padding: 10px 20px;
-  border-radius: 999px;
+  padding: calc(var(--space-2) + var(--space-1) / 2) var(--space-5);
+  border-radius: var(--radius-pill);
   font: inherit;
   cursor: pointer;
 }
@@ -343,9 +343,9 @@
 .growth-period-toolbar select {
   max-width: 100%;
   border: 1px solid var(--growth-border);
-  border-radius: 12px;
+  border-radius: var(--radius-12);
   background: var(--growth-paper);
   color: var(--growth-ink);
   font: inherit;
-  padding: 10px 12px;
+  padding: calc(var(--space-2) + var(--space-1) / 2) var(--space-3);
 }
diff --git a/web/src/components/onboarding.css b/web/src/components/onboarding.css
index 60989931..5c7539e1 100644
--- a/web/src/components/onboarding.css
+++ b/web/src/components/onboarding.css
@@ -2,7 +2,7 @@
  * Scale names mirror design/build-tokens.mjs's --yt-* projection. */
 .yt-onboarding {
   --yt-action-primary: var(--action-primary);
-  --yt-r-16: var(--radius-16, 1rem);
+  --yt-r-16: var(--radius-16);
   --yt-font-sans: var(--font-sans);
   font-family: var(--yt-font-sans);
 }
diff --git a/web/src/index.css b/web/src/index.css
index e2e9151f..6448615a 100644
--- a/web/src/index.css
+++ b/web/src/index.css
@@ -20,9 +20,9 @@
    20px 仍在 4px 网格上，且与 Mini App / YueLink 的手机节奏一致。 */
 @media (max-width: 639.98px) {
   :root {
-    --density-page-gap: 1.25rem;
-    --density-card-padding: 1.25rem;
-    --density-card-gap: 1.25rem;
+    --density-page-gap: var(--space-5);
+    --density-card-padding: var(--space-5);
+    --density-card-gap: var(--space-5);
   }
 }
 
@@ -70,20 +70,6 @@
   #main-content[data-route-focus]:focus-visible {
     outline: none;
   }
-  .app-skip-link {
-    position: fixed;
-    z-index: 100;
-    top: 0.75rem;
-    left: 0.75rem;
-    transform: translateY(-200%);
-    border-radius: 0.5rem;
-    background: var(--action-fill);
-    color: var(--primary-foreground);
-    padding: 0.625rem 0.875rem;
-    font-size: 0.875rem;
-    font-weight: 600;
-  }
-  .app-skip-link:focus { transform: translateY(0); }
 }
 
 /* Global reduced-motion rules come from @yueto/ui/tokens.css. */
diff --git a/web/src/routes/_app/traffic.tsx b/web/src/routes/_app/traffic.tsx
index 239fca78..60ca5672 100644
--- a/web/src/routes/_app/traffic.tsx
+++ b/web/src/routes/_app/traffic.tsx
@@ -74,11 +74,11 @@ function TrafficPage() {
               {days.length > 0 && (
                 <div className="flex items-center gap-3 text-xs text-muted-foreground">
                   <span className="flex items-center gap-1.5">
-                    <span className="size-2.5 rounded-[4px] bg-action-fill" aria-hidden="true" />
+                    <span className="size-2.5 rounded-[var(--radius-4)] bg-action-fill" aria-hidden="true" />
                     {t("上行")}
                   </span>
                   <span className="flex items-center gap-1.5">
-                    <span className="size-2.5 rounded-[4px] bg-[color-mix(in_srgb,var(--action-fill)_40%,transparent)]" aria-hidden="true" />
+                    <span className="size-2.5 rounded-[var(--radius-4)] bg-[color-mix(in_srgb,var(--action-fill)_40%,transparent)]" aria-hidden="true" />
                     {t("下行")}
                   </span>
                 </div>
commit 9a5daa7940cf4e491517eeab920fda42c05cdc6f
Author:     onesyue <47652916+onesyue@users.noreply.github.com>
AuthorDate: Thu Nov 5 09:09:44 2026 +0800
Commit:     onesyue <47652916+onesyue@users.noreply.github.com>
CommitDate: Thu Nov 5 09:09:44 2026 +0800

    ui: unify board user+admin visuals on shared tokens (#0A84FF), cards/states

exec
/bin/zsh -lc 'git diff --check 92e0b56c2be1524a64ee7a5cd5e654e53821e311 9a5daa7940cf4e491517eeab920fda42c05cdc6f; git diff -U160 92e0b56c2be1524a64ee7a5cd5e654e53821e311 9a5daa7940cf4e491517eeab920fda42c05cdc6f -- packages/ui/src/tokens.css web/src/index.css web-admin/src/index.css' in /Users/j/codex-runs/mh1105/yb-153
 succeeded in 0ms:
diff --git a/packages/ui/src/tokens.css b/packages/ui/src/tokens.css
index 0a7a679d..3762a844 100644
--- a/packages/ui/src/tokens.css
+++ b/packages/ui/src/tokens.css
@@ -1,306 +1,306 @@
 @import "./brand-bridge.css";
 @custom-variant dark (&:is(.dark *));
 /* 「减少透明度」（iOS/macOS 辅助功能 · prefers-reduced-transparency）：玻璃材质
    （半透明底色 + backdrop-blur）在这里降级为不透明表面。两个 SPA 都 @import 本文件，
    所以写 `reduce-transparency:bg-background reduce-transparency:backdrop-blur-none` 即可。 */
 @custom-variant reduce-transparency (@media (prefers-reduced-transparency: reduce));
 /* @generated from design/tokens/yue.tokens.json — do not edit (run node design/build-tokens.mjs) */
 
 /* Yue Design semantic tokens. Product apps consume these names; shadcn names below are aliases. */
 :root {
   /* @generated:begin tokens light */
   --radius-4: 4px;
   --radius-6: 6px;
   --radius-8: 8px;
   --radius-12: 12px;
   --radius-16: 16px;
   --radius-20: 20px;
   --radius-24: 24px;
   --radius-32: 32px;
   --radius-pill: 9999px;
   --space-1: 4px;
   --space-2: 8px;
   --space-3: 12px;
   --space-4: 16px;
   --space-5: 20px;
   --space-6: 24px;
   --space-8: 32px;
   --space-10: 40px;
   --space-12: 48px;
   --text-micro: 11px;
   --text-micro-lh: 1.45;
   --text-caption: 12px;
   --text-caption-lh: 1.5;
   --text-label: 13px;
   --text-label-lh: 1.5;
   --text-body: 14px;
   --text-body-lh: 1.5;
   --text-body-lg: 16px;
   --text-body-lg-lh: 1.5;
   --text-title: 18px;
   --text-title-lh: 1.4;
   --text-title-lg: 20px;
   --text-title-lg-lh: 1.35;
   --text-heading: 24px;
   --text-heading-lh: 1.3;
   --text-display-sm: 30px;
   --text-display-sm-lh: 1.2;
   --text-display: 36px;
   --text-display-lh: 1.1;
   --motion-fast: 100ms;
   --motion-base: 150ms;
   --motion-slow: 250ms;
   --motion-ease: cubic-bezier(0.2, 0, 0, 1);
   --motion-ease-out: cubic-bezier(0.16, 1, 0.3, 1);
   --chrome-blur: 22px;
   --chrome-saturate: 2;
   --chrome-tint: 86%;
   --chrome-clear: 73%;
   --spring-space-fast: cubic-bezier(0.2, 0, 0, 1);
   --spring-space-fast-duration: 231ms;
   --action-primary: #0a84ff;
   --brand-text: #0066cc;
   --action-fill: #0066cc;
   --action-fill-hover: #004a99;
   --state-success: #159f48;
   --state-success-text: #116f34;
   --state-success-fill: #15803d;
   --state-warning: #cf7106;
   --state-warning-text: #9d4807;
   --state-warning-fill: #b45309;
   --state-danger: #dc2626;
   --state-danger-text: #b91c1c;
   --state-danger-fill: #dc2626;
   --state-info: #2563eb;
   --state-info-text: #1d4ed8;
   --state-info-fill: #2563eb;
   --surface-canvas: #fafafa;
   --surface-raised: #ffffff;
   --surface-subtle: #f5f5f5;
   --stroke-subtle: #f5f3f0;
   --stroke-default: #e5e1dc;
   --stroke-strong: #8f8b87;
   --text-primary: #211e1b;
   --text-secondary: #514c47;
   --text-tertiary: #726e6a;
   --text-inverse: #ffffff;
   --text-on-fill: #ffffff;
   --connection-connected: #116f34;
   --connection-connecting: #9d4807;
   --connection-idle: #726e6a;
   --connection-failed: #b91c1c;
   /* @generated:end tokens light */
   color-scheme: light;
 
   /* ── Yue 2026 shared scales ────────────────────────────────────────────────
    * radius / space / type / motion are one scale across all five Yue surfaces
    * (yueboard 用户端+管理端, 官网, ops 控制台, Mini App, YueLink).
    * Spec: ../../../../docs/yue-visual-language-2026.md
    * Members are fixed: radius {4,6,8,12,16,20,24,32,pill}; space is a 4px grid.
    * A surface may only pick a *window* of the scale — never invent a value.  */
   /* Legacy shadcn anchor. Any component added later by `npx shadcn add` may
    * reference it, so it stays — but it is now defined *from* the scale rather
    * than being a second source of truth alongside it. */
   --radius: var(--radius-12);
 
 
   /* Type scale — size/line-height pairs. Weight ladder: 400 body · 500 label
    * · 600 title · 700 display. Nothing above 700, no half-pixel sizes.
    * Line-height decreases monotonically once past body size (1.5 at 14-16px
    * down to 1.1 at 36px) — the rule Tailwind encodes in its own default
    * ladder and the single most portable typographic convention of the lot. */
 
   /* Motion — three durations, two curves. Anything else is drift. */
 
   --surface-overlay: var(--surface-raised);
   --surface-sunken: var(--surface-subtle);
 
 
 
 
 
   --action-primary-hover: var(--action-fill-hover);
   --action-primary-foreground: #ffffff;
   --action-link: var(--brand-text);
   --action-link-hover: #3730a3;
   --action-focus: var(--action-primary);
   --action-soft: #eef2ff;
   --action-soft-foreground: #3730a3;
 
   --state-success-soft: #f0fdf4;
   --state-warning-soft: #fffbeb;
   --state-danger-soft: #fef2f2;
   --state-info-soft: #eff6ff;
 
   --shadow-card: 0 1px 2px rgb(9 9 11 / 0.04), 0 10px 30px -18px rgb(9 9 11 / 0.18);
   --elevation-overlay: 0 20px 50px -20px rgb(9 9 11 / 0.28);
 
   /* Comfortable is the consumer default; admin overrides only this density layer. */
-  --density-page-gap: 1.5rem;
-  --density-section-gap: 1rem;
+  --density-page-gap: var(--space-6);
+  --density-section-gap: var(--space-4);
   --density-control-height: 2.5rem;
   --density-control-height-sm: 2.25rem;
   --density-table-head-height: 2.75rem;
-  --density-table-cell-y: 0.75rem;
-  --density-card-padding: 1.5rem;
-  --density-card-gap: 1.5rem;
+  --density-table-cell-y: var(--space-3);
+  --density-card-padding: var(--space-6);
+  --density-card-gap: var(--space-6);
 
   /* shadcn compatibility aliases. */
   --background: var(--surface-canvas);
   --foreground: var(--text-primary);
   --card: var(--surface-raised);
   --card-foreground: var(--text-primary);
   --popover: var(--surface-overlay);
   --popover-foreground: var(--text-primary);
   --primary: var(--action-link);
   --primary-foreground: var(--action-primary-foreground);
   --secondary: var(--surface-subtle);
   --secondary-foreground: var(--text-primary);
   --muted: var(--surface-subtle);
   --muted-foreground: var(--text-secondary);
   --accent: var(--action-soft);
   --accent-foreground: var(--action-soft-foreground);
   --destructive: var(--state-danger-text);
   --destructive-foreground: var(--text-inverse);
   --border: var(--stroke-default);
   --input: var(--stroke-default);
   --ring: var(--action-focus);
   --sidebar: var(--surface-raised);
   --chrome-filter: blur(var(--chrome-blur)) saturate(calc(var(--chrome-saturate) * 100%));
   --sidebar-foreground: var(--text-primary);
   --sidebar-primary: var(--action-fill);
   --sidebar-primary-foreground: var(--action-primary-foreground);
   --sidebar-accent: var(--action-soft);
   --sidebar-accent-foreground: var(--action-soft-foreground);
   --sidebar-border: var(--stroke-subtle);
   --sidebar-ring: var(--action-focus);
 
   /* Legacy aliases kept while pages migrate to the semantic names. */
   --ink: var(--text-primary);
   --ink-tx: var(--text-inverse);
   --ink2: #27272a;
   --ink-soft: #f4f4f5;
   --tx2: var(--text-secondary);
   --tx3: var(--text-tertiary);
   --soft: var(--surface-subtle);
   --sunken: var(--surface-sunken);
   --line-soft: var(--stroke-subtle);
   --good: var(--state-success-text);
   /* 状态色文字档 2026-08-31 起上收进 token 源（design/tokens/yue.tokens.json
      state.*.text：浅=700 档、暗=400 档），围栏内生成 --state-*-text，本组
      别名只做转发；.dark 无需再手动回指——围栏在暗色块重发即自动翻档。 */
   --good-text: var(--state-success-text);
   --crit: var(--state-danger-text);
   --warn: var(--state-warning-text);
   --warn-bg: var(--state-warning-soft);
   --info: var(--state-info);
   --warn-text: var(--state-warning-text);
   --crit-text: var(--state-danger-text);
   --info-text: var(--state-info-text);
   --track: var(--stroke-default);
   --brand: var(--action-primary);
   --sh: var(--shadow-card);
   --announce-bg: linear-gradient(110deg, #eef2ff, #e0e7ff 58%, #f5f3ff);
   --announce-tx: #312e81;
 }
 
 /* iOS 27 / macOS 27 tinted chrome. Navigation only; content stays on --surface-raised. */
 .yue-chrome {
   background: color-mix(in srgb, var(--surface-raised) var(--chrome-tint), transparent);
   -webkit-backdrop-filter: var(--chrome-filter);
   backdrop-filter: var(--chrome-filter);
 }
 @media (prefers-reduced-transparency: reduce) {
   .yue-chrome {
     background: var(--surface-raised);
     -webkit-backdrop-filter: none;
     backdrop-filter: none;
   }
 }
 
 .dark {
   /* @generated:begin tokens dark */
   --chrome-saturate: 1.85;
   --chrome-tint: 82%;
   --chrome-clear: 67%;
   --action-primary: #0a84ff;
   --brand-text: #0a84ff;
   --action-fill: #0066cc;
   --action-fill-hover: #004a99;
   --state-success: #4ade80;
   --state-success-text: #4ade80;
   --state-success-fill: #15803d;
   --state-warning: #fbbf24;
   --state-warning-text: #fbbf24;
   --state-warning-fill: #b45309;
   --state-danger: #f87171;
   --state-danger-text: #f87171;
   --state-danger-fill: #dc2626;
   --state-info: #60a5fa;
   --state-info-text: #60a5fa;
   --state-info-fill: #2563eb;
   --surface-canvas: #101010;
   --surface-raised: #1c1c1e;
   --surface-subtle: #1f1f1f;
   --stroke-subtle: #2b2824;
   --stroke-default: #45403b;
   --stroke-strong: #8f8b87;
   --text-primary: #fcfbfa;
   --text-secondary: #c9c3bc;
   --text-tertiary: #a59e96;
   --text-inverse: #211e1b;
   --text-on-fill: #ffffff;
   --connection-connected: #4ade80;
   --connection-connecting: #fbbf24;
   --connection-idle: #a59e96;
   --connection-failed: #f87171;
   /* @generated:end tokens dark */
   color-scheme: dark;
   --surface-overlay: var(--surface-raised);
   --surface-sunken: var(--surface-subtle);
 
 
 
 
 
   /* Keep the canonical brand token stable; readable inline links are a
      separate role, and filled controls use --action-fill below. */
   --action-primary-hover: var(--brand-text);
   --action-primary-foreground: #ffffff;
   --action-link: var(--brand-text);
   --action-link-hover: #c7d2fe;
   /* Accent text becomes lighter on dark canvases, while white-on-filled
    * actions need the darker 600/700 surface to retain 4.5:1 contrast. */
   --action-focus: var(--action-primary);
   --action-soft: #312e81;
   --action-soft-foreground: #e0e7ff;
 
   --state-success-soft: #052e16;
   --state-warning-soft: #422006;
   --state-danger-soft: #450a0a;
   --state-info-soft: #172554;
 
   /* Dark-mode construction rule (Yue 2026 §Dark): elevation is expressed by
    * SURFACE LIGHTNESS + a 1px stroke, never by a drop shadow. A black shadow
    * on a near-black canvas is invisible work; it only muddies the card edge.
    * Resting cards therefore carry no shadow in dark — only true floating
    * layers (dialog / popover / sheet), which sit over arbitrary content and
    * need to detach from it, keep one. */
   --shadow-card: none;
   --elevation-overlay: 0 24px 60px -20px rgb(0 0 0 / 0.8);
 
   --destructive-foreground: var(--text-inverse);
   --ink2: #d4d4d8;
   --ink-soft: #27272a;
   --announce-bg: linear-gradient(110deg, #1e1b4b, #312e81 58%, #2e1065);
   --announce-tx: #e0e7ff;
   /* --track 与 --*-text 别名随浅色块的 var() 转发自动翻档，不再手动回指。 */
 }
 
 /* Optional tenant palettes only replace the action family; surfaces and states stay consistent.
  *
  * Each palette's light primary is declared exactly once, here, and is read by two consumers:
  * the palette's own light override below (`--action-primary: var(--palette-<id>)`) and the
  * appearance picker's swatch (web/src/lib/theme.ts PALETTES → `var(--palette-<id>)`).
  * Before 2026-10-06 the picker carried hand-copied oklch approximations that had drifted
  * off the applied colour (ocean swatch hue 245 vs applied #2563eb ≈ 263). The default
@@ -712,160 +712,179 @@
   --connection-idle: oklch(0.541 0.008 67.7);
   --connection-failed: oklch(0.505 0.19 27.5);
 }
 .dark {
   --action-primary: oklch(0.624 0.206 255.5);
   --brand-text: oklch(0.624 0.206 255.5);
   --action-fill: oklch(0.522 0.177 255.8);
   --action-fill-hover: oklch(0.42 0.144 256.2);
   --state-success: oklch(0.8 0.182 151.7);
   --state-success-text: oklch(0.8 0.182 151.7);
   --state-success-fill: oklch(0.527 0.137 150.1);
   --state-warning: oklch(0.837 0.164 84.4);
   --state-warning-text: oklch(0.837 0.164 84.4);
   --state-warning-fill: oklch(0.555 0.146 49);
   --state-danger: oklch(0.711 0.166 22.2);
   --state-danger-text: oklch(0.711 0.166 22.2);
   --state-danger-fill: oklch(0.577 0.215 27.3);
   --state-info: oklch(0.714 0.143 254.6);
   --state-info-text: oklch(0.714 0.143 254.6);
   --state-info-fill: oklch(0.546 0.215 262.9);
   --surface-canvas: oklch(0.173 0 0);
   --surface-raised: oklch(0.227 0.004 286.1);
   --surface-subtle: oklch(0.239 0 0);
   --stroke-subtle: oklch(0.279 0.008 75.2);
   --stroke-default: oklch(0.375 0.011 67.5);
   --stroke-strong: oklch(0.639 0.008 67.7);
   --text-primary: oklch(0.989 0.002 67.8);
   --text-secondary: oklch(0.82 0.012 71.9);
   --text-tertiary: oklch(0.703 0.014 71.3);
   --text-inverse: oklch(0.237 0.007 67.5);
   --text-on-fill: oklch(1 0 0);
   --connection-connected: oklch(0.8 0.182 151.7);
   --connection-connecting: oklch(0.837 0.164 84.4);
   --connection-idle: oklch(0.703 0.014 71.3);
   --connection-failed: oklch(0.711 0.166 22.2);
 }
 @media (color-gamut: p3) {
 :root {
 
 }
 .dark {
 
 }
 }
 }
 
 @media (prefers-contrast: more) {
 :root {
   --action-primary: #004a99;
   --brand-text: #004a99;
   --action-fill: #004a99;
   --action-fill-hover: #004a99;
   --state-success: #166534;
   --state-success-text: #166534;
   --state-success-fill: #15803d;
   --state-warning: #92400e;
   --state-warning-text: #92400e;
   --state-warning-fill: #b45309;
   --state-danger: #991b1b;
   --state-danger-text: #991b1b;
   --state-danger-fill: #dc2626;
   --state-info: #1e40af;
   --state-info-text: #1e40af;
   --state-info-fill: #2563eb;
   --surface-canvas: #ffffff;
   --surface-raised: #ffffff;
   --surface-subtle: #ffffff;
   --stroke-subtle: #726e6a;
   --stroke-default: #514c47;
   --stroke-strong: #211e1b;
   --text-primary: #000000;
   --text-secondary: #38332e;
   --text-tertiary: #514c47;
   --text-inverse: #ffffff;
   --text-on-fill: #ffffff;
   --connection-connected: #166534;
   --connection-connecting: #92400e;
   --connection-idle: #514c47;
   --connection-failed: #991b1b;
 }
 .dark {
   --action-primary: #80bfff;
   --brand-text: #80bfff;
   --action-fill: #004a99;
   --action-fill-hover: #004a99;
   --state-success: #4ade80;
   --state-success-text: #4ade80;
   --state-success-fill: #15803d;
   --state-warning: #fbbf24;
   --state-warning-text: #fbbf24;
   --state-warning-fill: #b45309;
   --state-danger: #f87171;
   --state-danger-text: #f87171;
   --state-danger-fill: #dc2626;
   --state-info: #60a5fa;
   --state-info-text: #60a5fa;
   --state-info-fill: #2563eb;
   --surface-canvas: #000000;
   --surface-raised: #000000;
   --surface-subtle: #000000;
   --stroke-subtle: #a59e96;
   --stroke-default: #c9c3bc;
   --stroke-strong: #fcfbfa;
   --text-primary: #ffffff;
   --text-secondary: #fcfbfa;
   --text-tertiary: #c9c3bc;
   --text-inverse: #000000;
   --text-on-fill: #ffffff;
   --connection-connected: #4ade80;
   --connection-connecting: #fbbf24;
   --connection-idle: #c9c3bc;
   --connection-failed: #f87171;
 }
 }
 
 @supports (transition-timing-function: linear(0, 1)) {
 :root {
   --spring-space-fast: linear(0, 0.031, 0.106, 0.203, 0.309, 0.413, 0.511, 0.6, 0.677, 0.743, 0.799, 0.844, 0.881, 0.911, 0.934, 0.952, 0.966, 0.977, 0.984, 0.99, 0.994, 0.997, 0.999, 1, 1.001, 1.001, 1.001, 1.002, 1.001, 1.001, 1.001, 1.001, 1);
   --spring-space-fast-duration: 231ms;
 }
 }
 
 @media (prefers-reduced-motion: reduce) {
 :root {
   --spring-space-fast-duration: 0ms;
 }
 }
 /* @generated:end tokens modern */
 
 /* Apply the token bridge after the legacy theme defaults. */
 @media (prefers-contrast: no-preference) {
 :root:not([data-theme]), :root[data-theme="default"] {
   --action-primary: var(--yt-color-brand);
   --brand-text: var(--yt-color-brand-text);
   --action-fill: var(--yt-color-action-fill-default);
   --action-fill-hover: var(--yt-color-action-fill-hover);
   --action-link-hover: var(--yt-color-brand-text);
   --surface-canvas: var(--yt-color-surface-canvas);
   --surface-raised: var(--yt-color-surface-raised);
   --surface-subtle: var(--yt-color-surface-subtle);
   --action-soft: var(--yt-color-surface-subtle);
   --action-soft-foreground: var(--yt-color-brand-text);
 }
 }
 
 /* Temporary purchase-surface aliases while the shared blue-token branch lands.
    Keep these outside generated fences; other surfaces retain their theme. */
 .yt-purchase {
   --yt-action-primary: #0a84ff;
   --brand: var(--yt-action-primary);
   --action-fill: #0066cc;
   --action-fill-hover: #005bb5;
   --action-primary-foreground: #ffffff;
   --primary-foreground: var(--action-primary-foreground);
   --action-soft: color-mix(in srgb, var(--yt-action-primary) 10%, var(--surface-raised));
   --action-link: var(--foreground);
   --accent: var(--action-soft);
   --accent-foreground: var(--foreground);
   --ring: var(--yt-action-primary);
 }
+
+/* Shared keyboard skip target for both SPA shells. Route-focus behavior stays
+   in each shell; only this visual treatment is shared. */
+@layer components {
+  .app-skip-link {
+    position: fixed;
+    z-index: 100;
+    top: var(--space-3);
+    left: var(--space-3);
+    transform: translateY(-200%);
+    border-radius: var(--radius-8);
+    background: var(--action-fill);
+    color: var(--primary-foreground);
+    padding: var(--space-3) var(--space-4);
+    font-size: var(--text-body);
+    font-weight: 600;
+  }
+  .app-skip-link:focus { transform: translateY(0); }
+}
diff --git a/web-admin/src/index.css b/web-admin/src/index.css
index 14b22cca..c776acd1 100644
--- a/web-admin/src/index.css
+++ b/web-admin/src/index.css
@@ -1,80 +1,66 @@
 @import "tailwindcss";
 
 /* 组件库（dialog/sheet/dropdown/tooltip）自带 animate-in/fade-in-0 等类名，
    这些实用类由 tw-animate-css 提供——缺了它所有弹层都是零动画硬弹。 */
 @import "tw-animate-css";
 @import "@yueto/ui/tokens.css";
 
 /* Tailwind ignores node_modules by default; the shared source package is an explicit design source. */
 @source "../node_modules/@yueto/ui/src";
 
 @media (prefers-reduced-motion: no-preference) {
   .dashboard-charts {
     animation: dashboard-charts-in var(--motion-slow) var(--motion-ease-out) both;
   }
 }
 @keyframes dashboard-charts-in {
   from { opacity: 0; transform: translateY(8px); }
   to { opacity: 1; transform: translateY(0); }
 }
 
 /* Admin uses the same visual language with denser controls, tables, cards and page rhythm. */
 :root {
-  --density-page-gap: 1.25rem;
-  --density-section-gap: 0.75rem;
+  --density-page-gap: var(--space-5);
+  --density-section-gap: var(--space-3);
   --density-control-height: 2.25rem;
-  --density-control-height-sm: 2rem;
+  --density-control-height-sm: var(--space-8);
   --density-table-head-height: 2.25rem;
   /* 行高由「最高的行内元素 + 上下内边距」决定，而管理端每一行的最高元素是 32px 的
      图标按钮：8+32+8+1 = 49px，一屏只有 13 行。2026 dense 表格基准是 40–44px。
      收到 6px 后是 45px —— 再往下就得把行内按钮也缩小，那会牺牲点击目标，不换。 */
   --density-table-cell-y: 0.375rem;
-  --density-card-padding: 1.25rem;
-  --density-card-gap: 1rem;
+  --density-card-padding: var(--space-5);
+  --density-card-gap: var(--space-4);
 }
 
 @layer components {
   /*
    * 🚨 路由容器被**程序化**聚焦时不画聚焦环。
    *
    * 两套 SPA 的壳都会在每次路由变化后 `#main-content.focus({preventScroll:true})`
    * ——这对读屏与键盘用户是对的（换页后落点在内容里，而不是停在上一页的某个按钮）。
    * 但 Chrome 把「键盘发起的导航之后的程序化聚焦」判成 `:focus-visible`，于是给它画
    * 浏览器默认的 `outline: auto`：**整个主内容区外面套一圈紫环**。内容够高时它的下边缘
    * 在屏幕外，看起来像内容区自带一层圆角边框；内容短时（空态页）就是一条横跨全宽的
    * 紫色横线。2026-08-25 实测：`document.activeElement` 是 `MAIN#main-content`，
    * `:focus-visible` 为真，`outline-style: auto`。
    *
    * `tabindex="-1"` 的区域**不在 Tab 顺序里**，不是可键盘操作的控件，所以这里没有
    * WCAG 2.4.7 意义上的焦点指示义务；跳转的反馈由「焦点已经落在内容里」本身承担。
    * 只关这一个 id，页面内所有真正的控件照常有焦点环。
    *
    * 🚨 但上面这段推理只覆盖**路由切换时的程序化聚焦**，覆盖不了跳转链接。
    * 两个 shell 都渲染 `<a class="app-skip-link" href="#main-content">跳到主要内容</a>`，
    * 那是**用户主动发起**的键盘导航：Tab → 链接浮现 → Enter → 焦点确实落进 main，
    * 而屏幕上什么都不变——键盘用户拿不到「跳成功了」的任何反馈。
    * 所以只压制带 `data-route-focus` 的那一次：它由路由 effect 在调用 focus() 之前
    * 打上、由 shell 的 onBlur 摘掉。跳转链接聚焦的是同一个元素但没有这个标记，
    * 焦点环照常出现。
    */
   #main-content[data-route-focus]:focus,
   #main-content[data-route-focus]:focus-visible {
     outline: none;
   }
-  .app-skip-link {
-    position: fixed;
-    z-index: 100;
-    top: 0.75rem;
-    left: 0.75rem;
-    transform: translateY(-200%);
-    border-radius: 0.5rem;
-    background: var(--action-fill);
-    color: var(--primary-foreground);
-    padding: 0.625rem 0.875rem;
-    font-size: 0.875rem;
-    font-weight: 600;
-  }
-  .app-skip-link:focus { transform: translateY(0); }
 }
 
 /* Global reduced-motion rules come from @yueto/ui/tokens.css. */
diff --git a/web/src/index.css b/web/src/index.css
index e2e9151f..6448615a 100644
--- a/web/src/index.css
+++ b/web/src/index.css
@@ -1,114 +1,100 @@
 @import "tailwindcss";
 /* 组件库（dialog/sheet/dropdown/tooltip）自带 animate-in/fade-in-0 等类名，
    这些实用类由 tw-animate-css 提供——缺了它所有弹层都是零动画硬弹。 */
 @import "tw-animate-css";
 @import "@yueto/ui/tokens.css";
 
 /* Tailwind ignores node_modules by default; the shared source package is an explicit design source. */
 @source "../node_modules/@yueto/ui/src";
 
 @media (prefers-reduced-motion: no-preference) {
   .settings-layout > section {
     animation: yb-reveal var(--motion-slow) var(--motion-ease-out) both;
   }
 }
 
 /* Comfortable density defaults come from @yueto/ui/tokens.css. */
 
 /* 手机宽度（<640px）取触摸档的页间距（视觉语言 §2.8：触摸表面 16–20）。
    24px 卡内边距在 360px 视口里只剩 280px 正文宽，四宫格数字与两列按钮被挤到换行；
    20px 仍在 4px 网格上，且与 Mini App / YueLink 的手机节奏一致。 */
 @media (max-width: 639.98px) {
   :root {
-    --density-page-gap: 1.25rem;
-    --density-card-padding: 1.25rem;
-    --density-card-gap: 1.25rem;
+    --density-page-gap: var(--space-5);
+    --density-card-padding: var(--space-5);
+    --density-card-gap: var(--space-5);
   }
 }
 
 @layer base {
   /* Tenant background images remain a consumer-only capability. */
   html[data-site-bg="1"] {
     background-image: var(--site-bg-image);
     background-size: cover;
     background-position: center;
     background-repeat: no-repeat;
     background-attachment: fixed;
   }
   html[data-site-bg="1"] body {
     /* 主题感知薄纱: 背景图同时铺两主题, 全透明 body 让页面级文字直接压图
        (浅图杀 dark 白字 / 深图杀 light 黑字)。82% 底纱两边保底可读。 */
     background-color: color-mix(in srgb, var(--surface-canvas) 82%, transparent);
   }
 }
 
 @layer components {
   /*
    * 🚨 路由容器被**程序化**聚焦时不画聚焦环。
    *
    * 两套 SPA 的壳都会在每次路由变化后 `#main-content.focus({preventScroll:true})`
    * ——这对读屏与键盘用户是对的（换页后落点在内容里，而不是停在上一页的某个按钮）。
    * 但 Chrome 把「键盘发起的导航之后的程序化聚焦」判成 `:focus-visible`，于是给它画
    * 浏览器默认的 `outline: auto`：**整个主内容区外面套一圈紫环**。内容够高时它的下边缘
    * 在屏幕外，看起来像内容区自带一层圆角边框；内容短时（空态页）就是一条横跨全宽的
    * 紫色横线。2026-08-25 实测：`document.activeElement` 是 `MAIN#main-content`，
    * `:focus-visible` 为真，`outline-style: auto`。
    *
    * `tabindex="-1"` 的区域**不在 Tab 顺序里**，不是可键盘操作的控件，所以这里没有
    * WCAG 2.4.7 意义上的焦点指示义务；跳转的反馈由「焦点已经落在内容里」本身承担。
    * 只关这一个 id，页面内所有真正的控件照常有焦点环。
    *
    * 🚨 但上面这段推理只覆盖**路由切换时的程序化聚焦**，覆盖不了跳转链接。
    * 两个 shell 都渲染 `<a class="app-skip-link" href="#main-content">跳到主要内容</a>`，
    * 那是**用户主动发起**的键盘导航：Tab → 链接浮现 → Enter → 焦点确实落进 main，
    * 而屏幕上什么都不变——键盘用户拿不到「跳成功了」的任何反馈。
    * 所以只压制带 `data-route-focus` 的那一次：它由路由 effect 在调用 focus() 之前
    * 打上、由 shell 的 onBlur 摘掉。跳转链接聚焦的是同一个元素但没有这个标记，
    * 焦点环照常出现。
    */
   #main-content[data-route-focus]:focus,
   #main-content[data-route-focus]:focus-visible {
     outline: none;
   }
-  .app-skip-link {
-    position: fixed;
-    z-index: 100;
-    top: 0.75rem;
-    left: 0.75rem;
-    transform: translateY(-200%);
-    border-radius: 0.5rem;
-    background: var(--action-fill);
-    color: var(--primary-foreground);
-    padding: 0.625rem 0.875rem;
-    font-size: 0.875rem;
-    font-weight: 600;
-  }
-  .app-skip-link:focus { transform: translateY(0); }
 }
 
 /* Global reduced-motion rules come from @yueto/ui/tokens.css. */
 
 /* 加载 → 内容：卡片插入时淡入一次（2026-10-13 UX 第二阶段，业主要求加动画）。
    - 只动 opacity：合成层属性，不触发布局（CLS 不变），也不占主线程（INP 不变）——
      两条都在独占测量里按变体逐项比过，见车道报告；
    - 不叠位移：路由切换已经有 main 内 fade + slide-in，再加位移就成了两次弹跳；
    - 只在插入时播一次（CSS animation 语义），重渲染不重播；
    - Reduced motion: shared tokens cap durations at 0.01ms; the card rule below also disables its animation.
    管理端刻意不加：管理效率优先，表格频繁换页时淡入只会拖慢扫读。 */
 @keyframes yb-reveal {
   from { opacity: 0; }
   to { opacity: 1; }
 }
 [data-slot="card"] {
   animation: yb-reveal var(--motion-base) var(--motion-ease-out) both;
 }
 /* 首屏与路由入场期间整页已在淡入（或首屏为了 LCP 不动），卡片不再各自播。见 _app.tsx RouteStage。 */
 .yb-route-static [data-slot="card"],
 .yb-route-enter [data-slot="card"] {
   animation: none;
 }
 @media (prefers-reduced-motion: reduce) {
   [data-slot="card"] { animation: none; }
 }
 
 /* sonner 富色提示条的 token 覆盖已上收到 @yueto/ui/tokens.css（两个 SPA 共用）。 */

codex
VERDICT: approve

- No actionable correctness, regression, or security issues found in the specified diff.
- Changes match the shared-token and card/state styling intent.
- No tests removed or weakened.
- `git diff --check` passed; runtime rendering and tests were not executed.
tokens used
43,713
VERDICT: approve

- No actionable correctness, regression, or security issues found in the specified diff.
- Changes match the shared-token and card/state styling intent.
- No tests removed or weakened.
- `git diff --check` passed; runtime rendering and tests were not executed.
Finished: 2026-11-05T03:06:16Z exit=0
