# yueboard #138 review at 6d5bcf0dfa16294bc4d7a9a06525a41a915ea641

Reviewed range: 08bf94184af24ebcc9f4af036cd7027fbf397cdb..6d5bcf0dfa16294bc4d7a9a06525a41a915ea641 (post-merge backfill; codex on mac-5f08d00f, read-only sandbox)
Started: 2026-11-05T03:05:06Z

Reading additional input from stdin...
OpenAI Codex v0.166.0
--------
workdir: /Users/j/codex-runs/mh1105/yb-138
model: gpt-6-astra
provider: openai
approval: never
sandbox: read-only
reasoning effort: medium
reasoning summaries: none
session id: 01a1a9aa-d18f-7181-bbb2-e8cc79951082
--------
user
You are reviewing merged PR onesyue/yueboard #138 at exact head 6d5bcf0dfa16294bc4d7a9a06525a41a915ea641. Review ONLY the diff: git diff 08bf94184af24ebcc9f4af036cd7027fbf397cdb 6d5bcf0dfa16294bc4d7a9a06525a41a915ea641 (and git log 08bf94184af24ebcc9f4af036cd7027fbf397cdb..6d5bcf0dfa16294bc4d7a9a06525a41a915ea641). Do not modify files. Check correctness, regressions, weakened/removed tests, security, and that the change matches its title/intent. Output a final line exactly 'VERDICT: approve' or 'VERDICT: changes' followed by concise bullet findings.
2026-11-05T03:05:11.697040Z ERROR codex_models_manager::manager: failed to refresh available models: request timed out
codex
I’ll read the repository’s review guidance, then inspect only the specified diff and commit log. I won’t modify files.
exec
/bin/zsh -lc 'pwd; cat CLAUDE.md; git log --oneline 08bf94184af24ebcc9f4af036cd7027fbf397cdb..6d5bcf0dfa16294bc4d7a9a06525a41a915ea641; git diff --stat 08bf94184af24ebcc9f4af036cd7027fbf397cdb 6d5bcf0dfa16294bc4d7a9a06525a41a915ea641' in /Users/j/codex-runs/mh1105/yb-138
 succeeded in 0ms:
/Users/j/codex-runs/mh1105/yb-138
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
6d5bcf0d Merge remote-tracking branch 'origin/master' into codex/1104c-region-single
d6b9bc57 region single-node: rewrite A/B-only entry-pair/x4b assertions to one-node-per-server; keep and restore entry protection guards
15cca4b4 subscribe: one panel server = one node in every format; remove A/B alternates and region merge
 internal/modules/subscribe/REGION-VALIDATION.md    |  84 ---
 internal/modules/subscribe/all_entry_pairs_test.go | 172 -----
 internal/modules/subscribe/cdn_canary.go           |  77 ---
 internal/modules/subscribe/cdn_canary_test.go      | 187 ------
 internal/modules/subscribe/delivery_reason_test.go |   4 +-
 .../subscribe/endpoint_ip_literal_delivery_test.go |  70 +-
 internal/modules/subscribe/endpoint_salt.go        | 119 ++--
 .../modules/subscribe/endpoint_salt_pin_test.go    |  21 +-
 .../modules/subscribe/endpoint_salt_wiring_test.go |   2 +-
 internal/modules/subscribe/entry_path_test.go      |  77 +--
 internal/modules/subscribe/entry_projection.go     |  72 ++-
 .../subscribe/info_rows_unreachable_test.go        |   2 +-
 internal/modules/subscribe/node_intelligence.go    |   4 +-
 .../modules/subscribe/pair_gate_parity_test.go     |  48 --
 internal/modules/subscribe/proxies.go              |  19 +-
 internal/modules/subscribe/region_ai_test.go       |  90 ---
 internal/modules/subscribe/region_entry.go         | 703 ---------------------
 internal/modules/subscribe/region_entry_test.go    | 690 --------------------
 internal/modules/subscribe/region_fallback_test.go |  67 --
 internal/modules/subscribe/singbox.go              |  13 -
 .../subscribe/single_entry_protection_test.go      | 117 ++++
 internal/modules/subscribe/subscribe.go            |   2 +-
 internal/modules/subscribe/subscribe_clash.go      |   6 -
 internal/modules/subscribe/subscribe_deliver.go    |  34 +-
 internal/modules/subscribe/surfboard.go            |   1 -
 internal/modules/subscribe/surge.go                |   1 -
 .../subscribe/testdata/cdn_canary_off_clash.golden |  59 --
 .../testdata/cdn_canary_off_clashmeta.golden       |  73 ---
 .../testdata/cdn_canary_off_general.golden         |   1 -
 .../subscribe/testdata/cdn_canary_off_loon.golden  |   8 -
 .../testdata/cdn_canary_off_quantumultx.golden     |   1 -
 .../testdata/cdn_canary_off_sing-box.golden        |   1 -
 .../subscribe/testdata/cdn_canary_off_stash.golden |  73 ---
 .../testdata/cdn_canary_off_surfboard.golden       | 643 -------------------
 .../subscribe/testdata/cdn_canary_off_surge.golden | 663 -------------------
 .../entry_intelligence_integration_test.go         |  15 +-
 .../entry_pairs_publication_integration_test.go    |  51 +-
 .../entry_x4b_admission_integration_test.go        |   4 +-
 38 files changed, 367 insertions(+), 3907 deletions(-)

exec
/bin/zsh -lc 'for f in ../AGENTS.md ../CLAUDE.md; do if test -f "$f"; then cat "$f"; fi; done; git diff 08bf94184af24ebcc9f4af036cd7027fbf397cdb 6d5bcf0dfa16294bc4d7a9a06525a41a915ea641 -- internal/modules/subscribe/endpoint_salt.go internal/modules/subscribe/entry_projection.go internal/modules/subscribe/proxies.go internal/modules/subscribe/subscribe_deliver.go internal/modules/subscribe/singbox.go internal/modules/subscribe/subscribe_clash.go internal/modules/subscribe/surfboard.go internal/modules/subscribe/surge.go internal/modules/subscribe/node_intelligence.go internal/modules/subscribe/subscribe.go' in /Users/j/codex-runs/mh1105/yb-138
 succeeded in 0ms:
diff --git a/internal/modules/subscribe/endpoint_salt.go b/internal/modules/subscribe/endpoint_salt.go
index dc89f08c..3d8e79c3 100644
--- a/internal/modules/subscribe/endpoint_salt.go
+++ b/internal/modules/subscribe/endpoint_salt.go
@@ -2,13 +2,13 @@ package subscribe
 
 import (
 	"context"
+	"encoding/json"
 	"errors"
 	"log/slog"
 	"maps"
 	"strings"
 	"time"
 
-	"github.com/onesyue/yueboard/internal/platform/entrypath"
 	"github.com/onesyue/yueboard/internal/platform/entrysalt"
 	"github.com/onesyue/yueboard/internal/platform/metrics"
 	"github.com/onesyue/yueboard/internal/platform/nativeproto"
@@ -52,8 +52,7 @@ func (m *Module) endpointSalt(ctx context.Context) *endpointSaltConfig {
 	return m.endpointSaltFromSnapshot(ctx, snapshot)
 }
 
-// One successful settings snapshot binds pair requirements to the salt material.
-// A cold database error must never become the legacy "pairs disabled" default.
+// Load salt material from one consistent settings snapshot.
 func (m *Module) entryProjectionConfig(ctx context.Context) (*endpointSaltConfig, bool, error) {
 	snapshot, err := m.settings.RawSnapshot(ctx)
 	if err != nil {
@@ -61,11 +60,11 @@ func (m *Module) entryProjectionConfig(ctx context.Context) (*endpointSaltConfig
 	}
 	required, present := snapshot["subscribe_entry_pairs_required"]
 	if present && required != "0" && required != "1" {
-		return nil, false, errors.New("invalid entry pair requirement")
+		return nil, false, errors.New("invalid entry protection requirement")
 	}
 	cfg := m.endpointSaltFromSnapshot(ctx, snapshot)
 	if required == "1" && cfg == nil {
-		return nil, true, errors.New("required entry pair configuration unavailable")
+		return nil, true, errors.New("required entry configuration unavailable")
 	}
 	return cfg, required == "1", nil
 }
@@ -77,7 +76,7 @@ func (m *Module) endpointSaltFromSnapshot(ctx context.Context, snapshot map[stri
 		(m.pool == nil || hit.persisted || time.Since(hit.attempt) < 30*time.Second) {
 		return hit.cfg
 	}
-	cfg, err := entrysalt.Parse(raw)
+	cfg, err := parseSubscriptionSalt(raw)
 	if err != nil {
 		// Do not expose canonical names on a corrupt/missing configuration.
 		// Prefer this process's last accepted generation, then the durable copy.
@@ -85,24 +84,16 @@ func (m *Module) endpointSaltFromSnapshot(ctx context.Context, snapshot map[stri
 		if hit != nil && hit.cfg != nil {
 			return hit.cfg
 		}
-		cfg, err = entrysalt.Parse(snapshot[subscribeEndpointSaltLastGoodKey])
+		cfg, err = parseSubscriptionSalt(snapshot[subscribeEndpointSaltLastGoodKey])
 		if err != nil {
 			return nil
 		}
 		return cfg
 	}
-	// Legacy salt documents may omit fault-domain metadata. Once pairs are
-	// required, such a document must not replace the last verified recovery
-	// material or poison this process's cache. Return it for the shared visible-
-	// product gate; hidden products do not enlarge that user's required scope.
-	if snapshot["subscribe_entry_pairs_required"] == "1" {
-		for _, namespace := range []map[string][]int{cfg.AlternateBuckets, cfg.CDNAlternateBuckets} {
-			for host := range namespace {
-				if cfg.EntryPairScopes[host] == "" {
-					return cfg
-				}
-			}
-		}
+	// Incomplete scope must not replace verified recovery material. Visible
+	// rows are checked by projectEntryEndpoints; hidden rows cannot widen access.
+	if snapshot["subscribe_entry_pairs_required"] == "1" && !completeEntryScopes(cfg) {
+		return cfg
 	}
 	// The Board owns this setting. Persist only while the source row is still
 	// the exact snapshot we parsed; a concurrent rotation must not be rolled
@@ -222,7 +213,7 @@ func applyEndpointSaltFor(cfg *endpointSaltConfig, subject entrysalt.Subject, se
 			if originHost == "" {
 				originHost = s.Host
 			}
-			if salted, ok := entrysalt.CDNEntryHost(cfg, subject, originHost, s.entryAlternate); ok {
+			if salted, ok := entrysalt.CDNEntryHost(cfg, subject, originHost, false); ok {
 				s.cdnOriginHost = originHost
 				rewriteCDNRow(s, salted)
 				n++
@@ -233,9 +224,6 @@ func applyEndpointSaltFor(cfg *endpointSaltConfig, subject entrysalt.Subject, se
 			continue
 		}
 		salted := entrysalt.SaltedHost(cfg, subject, s.Host)
-		if s.entryAlternate {
-			salted = entrysalt.AlternateSaltedHost(cfg, subject, s.Host)
-		}
 		if salted == "" {
 			continue
 		}
@@ -277,7 +265,7 @@ func dropUnsaltableCDNRows(cfg *endpointSaltConfig, subject entrysalt.Subject, s
 			// applyEndpointSaltFor has already replaced Host. Look up the
 			// canonical identity and require the actual three-field rewrite;
 			// merely recognizing a bucket suffix would admit unverified rows.
-			if salted, ok := entrysalt.CDNEntryHost(cfg, subject, s.cdnOriginHost, s.entryAlternate); ok &&
+			if salted, ok := entrysalt.CDNEntryHost(cfg, subject, s.cdnOriginHost, false); ok &&
 				s.Host == salted && gs(s.Settings, "tls_settings.server_name") == salted &&
 				gs(s.Settings, "network_settings.headers.Host") == salted {
 				kept = append(kept, s)
@@ -339,44 +327,61 @@ func isIPv4Literal(h string) bool {
 	return true
 }
 
-// expandEntryAlternates preserves product identity, credentials and permissions.
-// A is always followed by B; primary-bucket HMAC still distributes users across
-// the admitted pool. Display order is not a claim of independent failure domains.
-func expandEntryAlternates(cfg *endpointSaltConfig, subject entrysalt.Subject, servers []*serverRow, requireAll ...bool) ([]*serverRow, error) {
-	all := len(requireAll) != 0 && requireAll[0]
-	out := make([]*serverRow, 0, len(servers)*2)
-	for _, s := range servers {
-		if s == nil {
-			return nil, errors.New("nil entry product")
-		}
-		path, err := entrypath.Parse(s.Settings)
-		if err != nil {
+// Legacy alternate metadata belongs to node synchronization, not subscriptions.
+func parseSubscriptionSalt(raw string) (*endpointSaltConfig, error) {
+	var fields map[string]json.RawMessage
+	if err := json.Unmarshal([]byte(raw), &fields); err != nil {
+		return nil, err
+	}
+	rawScopes, hasScopes := fields["entry_pair_scopes"]
+	delete(fields, "alternate_buckets")
+	delete(fields, "cdn_alternate_buckets")
+	delete(fields, "entry_pair_scopes")
+	clean, err := json.Marshal(fields)
+	if err != nil {
+		return nil, err
+	}
+	cfg, err := entrysalt.Parse(string(clean))
+	if err != nil || cfg == nil {
+		return cfg, err
+	}
+	// Keep safety metadata independently of obsolete alternate assignments.
+	if hasScopes {
+		if err := json.Unmarshal(rawScopes, &cfg.EntryPairScopes); err != nil {
 			return nil, err
 		}
-		required := (path != nil && path.BackupRequired) || (all && !entryPairExempt(s))
-		if !required {
-			out = append(out, s)
-			continue
+		for host, scope := range cfg.EntryPairScopes {
+			_, normal := cfg.HostBuckets[host]
+			_, static := cfg.Hosts[host]
+			_, cdn := cfg.CDNHosts[host]
+			if (!normal && !static && !cdn) || (scope != "network" && scope != "machine" && scope != "shared") || (cdn && scope != "shared") {
+				return nil, errors.New("invalid entry scope")
+			}
 		}
-		if cfg == nil || subject.Token == "" {
-			return nil, errors.New("verified alternate entry unavailable")
+	}
+	return cfg, nil
+}
+
+// Every registered pool, including hidden pools, needs declared scope before
+// the document is eligible to replace verified recovery material.
+func completeEntryScopes(cfg *endpointSaltConfig) bool {
+	if cfg == nil {
+		return false
+	}
+	for host := range cfg.HostBuckets {
+		if cfg.EntryPairScopes[host] == "" {
+			return false
 		}
-		var primary, alternate string
-		if s.Type == "vless" && nativeproto.IsCDNWebSocketVless(s.Settings) {
-			primary, _ = entrysalt.CDNEntryHost(cfg, subject, s.Host, false)
-			alternate, _ = entrysalt.CDNEntryHost(cfg, subject, s.Host, true)
-		} else if hasExplicitSNI(s) {
-			primary = entrysalt.SaltedHost(cfg, subject, s.Host)
-			alternate = entrysalt.AlternateSaltedHost(cfg, subject, s.Host)
+	}
+	for host := range cfg.Hosts {
+		if cfg.EntryPairScopes[host] == "" {
+			return false
 		}
-		if primary == "" || alternate == "" || primary == alternate {
-			return nil, errors.New("verified distinct entry pair unavailable")
+	}
+	for host := range cfg.CDNHosts {
+		if cfg.EntryPairScopes[host] == "" {
+			return false
 		}
-		a, b := *s, *s
-		a.Name += " · A"
-		b.Name += " · B"
-		b.entryAlternate = true
-		out = append(out, &a, &b)
 	}
-	return out, nil
+	return true
 }
diff --git a/internal/modules/subscribe/entry_projection.go b/internal/modules/subscribe/entry_projection.go
index bbbc448d..1987f923 100644
--- a/internal/modules/subscribe/entry_projection.go
+++ b/internal/modules/subscribe/entry_projection.go
@@ -9,6 +9,7 @@ import (
 	"github.com/onesyue/yueboard/internal/platform/entrypath"
 	"github.com/onesyue/yueboard/internal/platform/entrysalt"
 	"github.com/onesyue/yueboard/internal/platform/metrics"
+	"github.com/onesyue/yueboard/internal/platform/nativeproto"
 )
 
 // publishedServers is the shared visibility gate for subscription delivery and
@@ -59,34 +60,26 @@ func validateEntrySalt(cfg *endpointSaltConfig, subject entrysalt.Subject, serve
 // projectEntryEndpoints is the common, side-effect-free publication pipeline.
 // Callers supply per-request rows; cached rows must never acquire account salts.
 // Risk/HWID recording stays in subscription delivery, outside this projection.
-func projectEntryEndpoints(cfg *endpointSaltConfig, subject entrysalt.Subject, servers []*serverRow, requireAll ...bool) ([]*serverRow, int, error) {
-	if len(requireAll) != 0 && requireAll[0] {
-		if cfg == nil {
-			return nil, 0, errors.New("required entry pair configuration unavailable")
-		}
-		if err := entrysalt.ValidateAlternates(cfg); err != nil {
-			return nil, 0, err
-		}
-		for _, server := range servers {
-			if server != nil && !entryPairExempt(server) && cfg.EntryPairScopes[server.Host] == "" {
-				return nil, 0, errors.New("visible native entry pair scope unavailable")
-			}
-		}
+func projectEntryEndpoints(cfg *endpointSaltConfig, subject entrysalt.Subject, servers []*serverRow, requireEntry ...bool) ([]*serverRow, int, error) {
+	strict := len(requireEntry) != 0 && requireEntry[0]
+	if err := validateSingleEntryProtection(cfg, subject, servers, strict); err != nil {
+		return nil, 0, err
 	}
 	if err := validateEntrySalt(cfg, subject, servers); err != nil {
 		return nil, 0, err
 	}
+	cloned := make([]*serverRow, len(servers))
+	for i, source := range servers {
+		row := *source
+		cloned[i] = &row
+	}
+	servers = cloned
 	salted := 0
-	if cfg != nil || len(requireAll) != 0 && requireAll[0] {
-		var err error
-		servers, err = expandEntryAlternates(cfg, subject, servers, requireAll...)
-		if err != nil {
-			return nil, 0, err
-		}
+	if cfg != nil {
 		salted = applyEndpointSaltFor(cfg, subject, servers)
 	}
 	servers = dropIPLiteralFleetRows(cfg, servers)
-	return appendCDNCanary(cfg, subject, dropUnsaltableCDNRows(cfg, subject, servers)), salted, nil
+	return dropUnsaltableCDNRows(cfg, subject, servers), salted, nil
 }
 
 // dropIPLiteralFleetRows enforces "no IP literal in any render" (plan W3.5)
@@ -125,3 +118,42 @@ func dropIPLiteralFleetRows(cfg *endpointSaltConfig, servers []*serverRow) []*se
 func entryPairExempt(s *serverRow) bool {
 	return s.external || (s.Host == "127.0.0.1" && s.Port == 9)
 }
+
+// Strict publication still requires a verified primary entry. Retired alternate
+// assignments never determine whether that single entry is publishable.
+func validateSingleEntryProtection(cfg *endpointSaltConfig, subject entrysalt.Subject, servers []*serverRow, strict bool) error {
+	if strict && cfg == nil {
+		return errors.New("required entry configuration unavailable")
+	}
+	for _, s := range servers {
+		if s == nil {
+			return errors.New("nil entry product")
+		}
+		path, err := entrypath.Parse(s.Settings)
+		if err != nil {
+			return err
+		}
+		if entryPairExempt(s) {
+			continue
+		}
+		if strict && cfg.EntryPairScopes[s.Host] == "" {
+			return errors.New("visible native entry scope unavailable")
+		}
+		if !strict && path == nil {
+			continue
+		}
+		if cfg == nil || subject.Token == "" || !hasExplicitSNI(s) {
+			return errors.New("verified entry unavailable")
+		}
+		primary := ""
+		if s.Type == "vless" && nativeproto.IsCDNWebSocketVless(s.Settings) {
+			primary, _ = entrysalt.CDNEntryHost(cfg, subject, s.Host, false)
+		} else {
+			primary = entrysalt.SaltedHost(cfg, subject, s.Host)
+		}
+		if primary == "" {
+			return errors.New("verified entry unavailable")
+		}
+	}
+	return nil
+}
diff --git a/internal/modules/subscribe/node_intelligence.go b/internal/modules/subscribe/node_intelligence.go
index 0e62c9cf..8ce94b14 100644
--- a/internal/modules/subscribe/node_intelligence.go
+++ b/internal/modules/subscribe/node_intelligence.go
@@ -359,12 +359,12 @@ func (m *Module) visibleClashProxies(ctx context.Context, uid int64, apiUA strin
 	servers = m.filterXHTTP(ctx, servers, proto, subUA)
 	servers = filterServersForRequest(servers, proto, flag, "", subUA)
 
-	saltCfg, requireAllPairs, saltConfigErr := m.entryProjectionConfig(ctx)
+	saltCfg, requireEntry, saltConfigErr := m.entryProjectionConfig(ctx)
 	if saltConfigErr != nil {
 		return nil, saltConfigErr
 	}
 	subject := saltSubjectFor(u, token, now)
-	servers, _, err = projectEntryEndpoints(saltCfg, subject, servers, requireAllPairs)
+	servers, _, err = projectEntryEndpoints(saltCfg, subject, servers, requireEntry)
 	if err != nil {
 		return nil, err
 	}
diff --git a/internal/modules/subscribe/proxies.go b/internal/modules/subscribe/proxies.go
index 95793df9..419fd4d5 100644
--- a/internal/modules/subscribe/proxies.go
+++ b/internal/modules/subscribe/proxies.go
@@ -13,16 +13,15 @@ import (
 
 // serverRow：订阅需要的 servers 字段 + 派生 password/port。
 type serverRow struct {
-	entryAlternate bool
-	ID             int64
-	Type           string
-	Name           string
-	Host           string
-	Port           int
-	Ports          string // 动态端口段（"20000-40000"），非空时写入 ports
-	Settings       map[string]any
-	Tags           []string
-	Password       string // 生产 = user.uuid
+	ID       int64
+	Type     string
+	Name     string
+	Host     string
+	Port     int
+	Ports    string // 动态端口段（"20000-40000"），非空时写入 ports
+	Settings map[string]any
+	Tags     []string
+	Password string // 生产 = user.uuid
 	// NameI18n 是 servers.name_i18n（`{"en": "..."}`）。缺该语言的 key 时
 	// **回落中文原名，绝不回落空串**：mihomo 拿到空 name 的 proxy 会整份配置
 	// 拒绝加载，那等于「换个语言 → 所有节点消失」。
diff --git a/internal/modules/subscribe/singbox.go b/internal/modules/subscribe/singbox.go
index 5e47c859..10cb9407 100644
--- a/internal/modules/subscribe/singbox.go
+++ b/internal/modules/subscribe/singbox.go
@@ -96,19 +96,6 @@ func (m *Module) renderSingBoxForClient(
 	if err := mergeSingBoxOutboundsByTransport(cfg, proxies, transportOf, i18n.T(i18n.FromContext(ctx), defaultGroupUnavailableNotice)); err != nil {
 		return nil, err
 	}
-	if regionOptions(ctx).enabled {
-		names := make([]string, len(proxies))
-		for i, p := range proxies {
-			names[i], _ = p["tag"].(string)
-		}
-		obs, _ := cfg["outbounds"].([]any)
-		rewrites := map[string]string{}
-		cfg["outbounds"] = applyRegionGroups(ctx, obs, proxyRows, names, true, regionGroupExtras{rewrites: rewrites})
-		rewriteRegionSingBoxRefs(cfg, rewrites)
-		if err := cleanSingBoxGroups(cfg); err != nil {
-			return nil, err
-		}
-	}
 	// After the merge: outbound tags (and route.final) are final here.
 	adaptSingBoxRuleSetDownload(cfg, core)
 	adaptSingBoxDNSAddressFilter(cfg, core)
diff --git a/internal/modules/subscribe/subscribe.go b/internal/modules/subscribe/subscribe.go
index 70e572e5..77824b60 100644
--- a/internal/modules/subscribe/subscribe.go
+++ b/internal/modules/subscribe/subscribe.go
@@ -609,7 +609,7 @@ func (m *Module) prependInfoServersFor(ctx context.Context, u *subUser, servers
 		c.Name = name
 		c.Host = "127.0.0.1"
 		c.Port, c.Ports = resolvePorts("9", "") // fixed port, no hopping range
-		c.entryAlternate, c.cdnOriginHost = false, ""
+		c.cdnOriginHost = ""
 		return &c
 	}
 	// 顺序对齐 ClientController::setSubscribeInfoToServers 的 array_unshift 累积结果（前→后）：
diff --git a/internal/modules/subscribe/subscribe_clash.go b/internal/modules/subscribe/subscribe_clash.go
index a472ef63..cc9ae798 100644
--- a/internal/modules/subscribe/subscribe_clash.go
+++ b/internal/modules/subscribe/subscribe_clash.go
@@ -92,7 +92,6 @@ func (m *Module) renderClashMeta(
 	reserved = append(reserved, clashTemplateProxyNames(base)...)
 	servers = dedupeServerNames(servers, reserved)
 
-	var proxyRows []*serverRow
 	var proxyObjs []any
 	var names []string
 	transportOf := map[string]string{}
@@ -106,7 +105,6 @@ func (m *Module) renderClashMeta(
 				enableRealityMLKEM(p)
 			}
 			connTag.markConnTag(p)
-			proxyRows = append(proxyRows, s)
 			proxyObjs = append(proxyObjs, p)
 			names = append(names, s.Name)
 		}
@@ -116,9 +114,6 @@ func (m *Module) renderClashMeta(
 	// native discard-port notice while regional/manual groups remain intact.
 	notices := mergeProxyGroupsByTransport(pg, names, clashTemplateProxyNames(base), transportOf,
 		i18n.T(i18n.FromContext(ctx), defaultGroupUnavailableNotice))
-	groups, _ := pg["proxy-groups"].([]any)
-	regionRewrites := map[string]string{}
-	pg["proxy-groups"] = applyRegionGroups(ctx, groups, proxyRows, names, false, regionGroupExtras{rewrites: regionRewrites, templateNames: clashTemplateProxyNames(base)})
 	for _, notice := range notices {
 		proxyObjs = append(proxyObjs, notice)
 		names = append(names, notice["name"].(string))
@@ -144,7 +139,6 @@ func (m *Module) renderClashMeta(
 		return nil, err
 	}
 	rl := map[string]any{"rules": aiConfig["rules"], "sub-rules": aiConfig["sub-rules"]}
-	rewriteRegionClashRules(rl, regionRewrites)
 	buildRules(rl, trustedSubscriptionDomain, clashOwnServiceTarget(pg["proxy-groups"]))
 	// Prune/repoint rules whose target group mergeProxyGroups just removed.
 	// A ?filter=/?types= that empties a region group leaves rules like
diff --git a/internal/modules/subscribe/subscribe_deliver.go b/internal/modules/subscribe/subscribe_deliver.go
index ed413329..e63f5766 100644
--- a/internal/modules/subscribe/subscribe_deliver.go
+++ b/internal/modules/subscribe/subscribe_deliver.go
@@ -78,7 +78,7 @@ func (m *Module) deliver(
 	//
 	// 用 subscriptionToken（users.token，每份订阅稳定）而不是 credential(uuid)：
 	// 加盐名必须对同一份订阅恒定，否则 DNS 生命周期与客户端缓存都会出问题。
-	saltCfg, requireAllPairs, saltConfigErr := m.entryProjectionConfig(ctx)
+	saltCfg, requireEntry, saltConfigErr := m.entryProjectionConfig(ctx)
 	if saltConfigErr != nil {
 		failDelivery(w, r, "subscribe.entry_salt.unavailable", saltConfigErr)
 		return
@@ -92,15 +92,15 @@ func (m *Module) deliver(
 	}
 	if saltCfg != nil {
 		m.recordFetchOrigin(ctx, u, r)
-		// Origin recording can quarantine the account: project both entries from
+		// Origin recording can quarantine the account: project the entry from
 		// its resulting tier, also used by the read-only intelligence endpoint.
 		saltSubject = saltSubjectFor(u, subscriptionToken, time.Now())
 	}
 	var salted int
 	var projectionErr error
-	servers, salted, projectionErr = projectEntryEndpoints(saltCfg, saltSubject, servers, requireAllPairs)
+	servers, salted, projectionErr = projectEntryEndpoints(saltCfg, saltSubject, servers, requireEntry)
 	if projectionErr != nil {
-		failDelivery(w, r, "subscribe.entry_alternate.unavailable", projectionErr)
+		failDelivery(w, r, "subscribe.entry_salt.unavailable", projectionErr)
 		return
 	}
 	if saltCfg != nil {
@@ -113,34 +113,12 @@ func (m *Module) deliver(
 	// VLESS 内层 Encryption 能力门（见 encryption_capability.go）：节点若被面板配成强制内层
 	// 加密，而本渲染器表达不了该字段，发出去的配置必然握手失败——剔除优于交付一个连不上的节点。
 	servers = filterServersByEncryptionCapability(servers, proto)
-	region := regionEntryOptions{
-		enabled:    m.settings.Get(ctx, regionEntrySetting, "0") == "1",
-		preserveAI: m.singleAIEnabled(ctx),
-	}
-	if region.enabled {
-		if err := validateRegionCredentials(servers); err != nil {
-			failDelivery(w, r, "subscribe.region.invalid_uuid", err)
-			return
-		}
-		ctx = context.WithValue(ctx, regionEntryKey{}, region)
-		switch proto {
-		case "general":
-			servers = regionFlatRows(servers, func(s *serverRow) bool { return s.Type == "hysteria" || s.Type == "vless" })
-		case "loon":
-			servers = regionFlatRows(servers, loonEmits)
-		case "quantumultx":
-			servers = regionFlatRows(servers, qxEmits)
-		}
-	}
-	requestedTypes := parseCSV(r.URL.Query().Get("types"))
-	if !region.enabled {
-		servers = preferDefaultLatencyTestCompatibleServers(servers, proto, clientName, requestedTypes)
-	}
+	servers = preferDefaultLatencyTestCompatibleServers(servers, proto, clientName, parseCSV(r.URL.Query().Get("types")))
 	// Saturated hosts temporarily leave the automatic default groups.
 	m.markDefaultGroupHold(ctx, servers)
 	m.markDirectDefaultMembers(ctx, servers)
 	// Notice rows are added after entry projection. Placeholders never take
-	// part in endpoint salting, A/B entry expansion, or the Shadowrocket TCP
+	// part in endpoint salting or the Shadowrocket TCP
 	// preference above. The share warning is omitted when a refusal reason is
 	// already chosen (banned, device limit, empty, and the other notice kinds).
 	if share := shareSubscriptionNoticeRows(w.Header(), servers); len(share) > 0 {
diff --git a/internal/modules/subscribe/surfboard.go b/internal/modules/subscribe/surfboard.go
index fa89be23..9c797cf3 100644
--- a/internal/modules/subscribe/surfboard.go
+++ b/internal/modules/subscribe/surfboard.go
@@ -63,6 +63,5 @@ func (m *Module) renderSurfboard(
 	// 会把视频 QUIC 变成长时间黑洞的目的 UDP/443 拒绝规则。
 	out = stripLegacyDestinationQUICFallback(out)
 	out = ensureINIManagedDirectRules(out)
-	out = applyRegionINI(ctx, out, servers)
 	return []byte(out)
 }
diff --git a/internal/modules/subscribe/surge.go b/internal/modules/subscribe/surge.go
index 164fda91..ac93f560 100644
--- a/internal/modules/subscribe/surge.go
+++ b/internal/modules/subscribe/surge.go
@@ -75,7 +75,6 @@ func (m *Module) renderSurge(
 	// 旧版保留 REJECT-NO-DROP 规则，避免普通 REJECT 在突发重试后退化为静默丢包。
 	out = configureSurgeQUICFallback(out, surgeSupportsGlobalQUICBlock(r))
 	out = ensureINIManagedDirectRules(out)
-	out = applyRegionINI(ctx, out, servers)
 	return []byte(out)
 }
 

exec
/bin/zsh -lc "git diff 08bf94184af24ebcc9f4af036cd7027fbf397cdb 6d5bcf0dfa16294bc4d7a9a06525a41a915ea641 -- '*test.go'" in /Users/j/codex-runs/mh1105/yb-138
 succeeded in 0ms:
diff --git a/internal/modules/subscribe/all_entry_pairs_test.go b/internal/modules/subscribe/all_entry_pairs_test.go
index 5f5897e9..5e9f8d14 100644
--- a/internal/modules/subscribe/all_entry_pairs_test.go
+++ b/internal/modules/subscribe/all_entry_pairs_test.go
@@ -1,20 +1,5 @@
 package subscribe
 
-import (
-	"context"
-	"encoding/base64"
-	"encoding/json"
-	"net/http/httptest"
-	"net/url"
-	"reflect"
-	"strings"
-	"testing"
-	"time"
-
-	"github.com/onesyue/yueboard/internal/platform/entrysalt"
-	"github.com/onesyue/yueboard/internal/platform/settings"
-)
-
 func allPairsFixture() (*endpointSaltConfig, []*serverRow) {
 	cfg := cdnSaltCfg()
 	cfg.QuarantineBuckets = 0
@@ -28,160 +13,3 @@ func allPairsFixture() (*endpointSaltConfig, []*serverRow) {
 	c.ID, c.Name = 13, "cdn-V"
 	return cfg, []*serverRow{h, v, c}
 }
-
-func TestAllNativePairsCloneIdentityAndCDNThreeFields(t *testing.T) {
-	cfg, rows := allPairsFixture()
-	before, _ := json.Marshal(rows)
-	projected, _, err := projectEntryEndpoints(cfg, entrysalt.Subject{Token: "example"}, rows, true)
-	if err != nil || len(projected) != 6 {
-		t.Fatalf("projection: %v (%d)", err, len(projected))
-	}
-	for i, source := range rows {
-		a, b := projected[2*i], projected[2*i+1]
-		if a.ID != source.ID || b.ID != source.ID || a.Password != source.Password || b.Password != source.Password || a.Port != source.Port || b.Ports != source.Ports || a.Host == b.Host || a.Name != source.Name+" · A" || b.Name != source.Name+" · B" {
-			t.Fatal("identity/adjacency changed")
-		}
-		if i < 2 && (!reflect.DeepEqual(a.Settings, source.Settings) || !reflect.DeepEqual(b.Settings, source.Settings)) {
-			t.Fatal("direct profile changed")
-		}
-		if i == 2 {
-			for _, r := range []*serverRow{a, b} {
-				if gs(r.Settings, "tls_settings.server_name") != r.Host || gs(r.Settings, "network_settings.headers.Host") != r.Host {
-					t.Fatal("CDN handshake differs")
-				}
-			}
-		}
-	}
-	after, _ := json.Marshal(rows)
-	if string(before) != string(after) {
-		t.Fatal("cache mutated")
-	}
-}
-
-func TestAllNativePairsReachNineRendererConsumers(t *testing.T) {
-	for _, flag := range []string{"general", "clashmeta", "clash", "stash", "singbox", "loon", "surge", "surfboard", "quantumultx"} {
-		t.Run(flag, func(t *testing.T) {
-			cfg, rows := allPairsFixture()
-			raw, _ := json.Marshal(cfg)
-			m := entryTestModule(t, "", "")
-			m.settings = settings.NewStatic(map[string]string{subscribeEndpointSaltKey: string(raw), "subscribe_entry_pairs_required": "1"})
-			for _, key := range []string{"clashmeta", "clash", "stash"} {
-				m.tmpls[key] = tmplEntry{content: "proxies: []\nproxy-groups:\n  - name: 悦 · 节点选择\n    type: select\n    proxies: [DIRECT]\nrules:\n  - MATCH,悦 · 节点选择\n", at: time.Now()}
-			}
-			m.tmpls["singbox"] = tmplEntry{content: `{"outbounds":[{"type":"selector","tag":"悦 · 节点选择","outbounds":["auto"]},{"type":"direct","tag":"direct"}]}`, at: time.Now()}
-			m.tmpls["surge"] = tmplEntry{content: defaultSurgeTemplate, at: time.Now()}
-			m.tmpls["surfboard"] = tmplEntry{content: defaultSurfboardTemplate, at: time.Now()}
-			wireFlag := flag
-			if flag == "singbox" {
-				wireFlag = "sing-box"
-			}
-			req := httptest.NewRequest("GET", "https://sub.example/s/tok?flag="+wireFlag, nil)
-			w := httptest.NewRecorder()
-			m.deliver(context.Background(), w, req, entrySubUser(), rows, 0, "uuid-test", "tok")
-			body := w.Body.String()
-			if flag == "general" || flag == "quantumultx" {
-				b, e := base64.StdEncoding.DecodeString(body)
-				if e != nil {
-					t.Fatal(e)
-				}
-				body = string(b)
-			}
-			body, _ = url.QueryUnescape(body)
-			if w.Code != 200 {
-				t.Fatalf("consumer %d: %.300s", w.Code, body)
-			}
-			want := []string{"direct-H", "direct-V", "cdn-V"}
-			if flag == "surge" || flag == "surfboard" {
-				want = want[:1]
-			}
-			if flag == "quantumultx" {
-				want = want[1:]
-			}
-			if flag == "clash" {
-				// Legacy Clash cores parse neither hysteria2 nor VLESS: since
-				// 2026-10-11 they receive only the upgrade placeholder
-				// (clash_legacy_core.go), never a pair they cannot load.
-				if strings.Contains(body, "direct-H") || !strings.Contains(body, "YueLink") {
-					t.Fatalf("legacy clash must get the upgrade hint only: %.500s", body)
-				}
-				want = nil
-			}
-			end := -1
-			for _, name := range want {
-				a, b := strings.Index(body, name+" · A"), strings.Index(body, name+" · B")
-				if a <= end || b <= a {
-					t.Fatalf("pair order %s: %.500s", name, body)
-				}
-				end = b
-			}
-			if (flag == "surge" || flag == "surfboard") && strings.Contains(body, "cdn-V") {
-				t.Fatal("unsupported CDN emitted")
-			}
-		})
-	}
-}
-
-func TestAllPairsNeverFallsBackOnMissingOrMalformedMaterial(t *testing.T) {
-	for _, fault := range []string{"normal-map", "cdn-map", "same-index", "sni", "token", "config", "scope-absent", "scope-invalid", "scope-cdn"} {
-		t.Run(fault, func(t *testing.T) {
-			cfg, rows := allPairsFixture()
-			subject := entrysalt.Subject{Token: "example"}
-			switch fault {
-			case "scope-absent":
-				delete(cfg.EntryPairScopes, rows[0].Host)
-			case "scope-invalid":
-				cfg.EntryPairScopes[rows[0].Host] = "unknown"
-			case "scope-cdn":
-				cfg.EntryPairScopes[cdnTestHost] = "network"
-			case "normal-map":
-				cfg.AlternateBuckets = nil
-			case "cdn-map":
-				cfg.CDNAlternateBuckets = nil
-			case "same-index":
-				cfg.AlternateBuckets[rows[0].Host] = []int{0, 1}
-			case "sni":
-				rows[0].Settings["tls"] = map[string]any{}
-			case "token":
-				subject.Token = ""
-			case "config":
-				cfg = nil
-			}
-			if _, _, err := projectEntryEndpoints(cfg, subject, rows, true); err == nil {
-				t.Fatal("bad pair publication accepted")
-			}
-		})
-	}
-	for _, value := range []string{"", "true", "2", "\"1\""} {
-		m := entryTestModule(t, "", "")
-		m.settings = settings.NewStatic(map[string]string{"subscribe_entry_pairs_required": value})
-		if _, _, err := m.entryProjectionConfig(context.Background()); err == nil {
-			t.Fatalf("invalid flag accepted: %q", value)
-		}
-	}
-}
-
-// 2026-10-12: after the fleet-wide A/B publish turned all_native_pairs_required
-// on, an expired/banned account's line-status tips (127.0.0.1:9) failed the
-// whole subscription with "visible native entry pair scope unavailable".
-func TestAllNativePairsKeepLineStatusTipsForUnusableAccounts(t *testing.T) {
-	cfg, _ := allPairsFixture()
-	tips := tipToRows(&TipServer{Name: "套餐到期", Password: "tip"})
-	projected, _, err := projectEntryEndpoints(cfg, entrysalt.Subject{Token: "example"}, tips, true)
-	if err != nil {
-		t.Fatalf("tips must project under required pairs: %v", err)
-	}
-	if len(projected) != len(tips) {
-		t.Fatalf("tips must not be paired or dropped: %d -> %d", len(tips), len(projected))
-	}
-	for i, row := range projected {
-		if row.Host != "127.0.0.1" || row.Port != 9 || row.Name != tips[i].Name {
-			t.Fatalf("tip row changed: %+v", row)
-		}
-	}
-	// A real product without a scope is still refused.
-	_, rows := allPairsFixture()
-	rows[0].Host = "unscoped.example.net"
-	if _, _, err := projectEntryEndpoints(cfg, entrysalt.Subject{Token: "example"}, append(tips, rows[0]), true); err == nil {
-		t.Fatal("unscoped real product must still be refused")
-	}
-}
diff --git a/internal/modules/subscribe/cdn_canary_test.go b/internal/modules/subscribe/cdn_canary_test.go
deleted file mode 100644
index da104401..00000000
--- a/internal/modules/subscribe/cdn_canary_test.go
+++ /dev/null
@@ -1,187 +0,0 @@
-package subscribe
-
-import (
-	"bytes"
-	"context"
-	"encoding/json"
-	"fmt"
-	"net/http/httptest"
-	"os"
-	"path/filepath"
-	"reflect"
-	"strings"
-	"testing"
-	"time"
-
-	"github.com/onesyue/yueboard/internal/platform/entrysalt"
-	"github.com/onesyue/yueboard/internal/platform/settings"
-)
-
-func canaryToken(cfg *endpointSaltConfig) string {
-	for i := 0; ; i++ {
-		token := fmt.Sprint("anonymous-fixture-", i)
-		if cdnCanarySelected(cfg.Secret, token, 100) {
-			return token
-		}
-	}
-}
-
-func canaryFixture(enabled bool) (*endpointSaltConfig, []*serverRow) {
-	cfg, rows := allPairsFixture()
-	rows[2].ID = 171
-	rows[2].Settings = cloneMap(rows[2].Settings)
-	rows[2].Settings["cdn_entry_canary"] = map[string]any{"enabled": enabled, "basis_points": 100, "address": cdnCanaryAddress, "starts_at": "2026-10-13T00:00:00Z", "expires_at": "2026-10-16T00:00:00Z"}
-	return cfg, rows
-}
-
-func TestCDNCanaryIdentityAndBounds(t *testing.T) {
-	cfg, rows := canaryFixture(false)
-	token := canaryToken(cfg)
-	projected, _, err := projectEntryEndpoints(cfg, entrysalt.Subject{Token: token}, rows, true)
-	if err != nil {
-		t.Fatal(err)
-	}
-	// Enable only after the baseline projection, so this test is clock independent.
-	projected[4].Settings = cloneMap(projected[4].Settings)
-	projected[4].Settings["cdn_entry_canary"] = map[string]any{"enabled": true, "basis_points": 100, "address": cdnCanaryAddress, "starts_at": "2026-10-13T00:00:00Z", "expires_at": "2026-10-16T00:00:00Z"}
-	before, _ := json.Marshal(projected)
-	at := time.Date(2026, 10, 14, 0, 0, 0, 0, time.UTC)
-	out := appendCDNCanaryAt(cfg, entrysalt.Subject{Token: token}, projected, at)
-	if len(out) != 7 {
-		t.Fatalf("want original 6 + C, got %d", len(out))
-	}
-	after, _ := json.Marshal(out[:6])
-	if !bytes.Equal(before, after) {
-		t.Fatal("A/B mutated")
-	}
-	c := *out[6]
-	c.Host = projected[4].Host
-	c.Name = projected[4].Name
-	if !reflect.DeepEqual(&c, projected[4]) {
-		t.Fatal("C changed identity, credentials or TLS/WS settings")
-	}
-	if out[6].Host != cdnCanaryAddress || out[6].Name != "cdn-V · C" {
-		t.Fatal("wrong C address/name")
-	}
-	for _, when := range []time.Time{at.Add(-48 * time.Hour), at.Add(48 * time.Hour)} {
-		if len(appendCDNCanaryAt(cfg, entrysalt.Subject{Token: token}, projected, when)) != 6 {
-			t.Fatal("outside experiment window")
-		}
-	}
-	if len(appendCDNCanaryAt(cfg, entrysalt.Subject{Token: token, Quarantine: true}, projected, at)) != 6 {
-		t.Fatal("quarantine included")
-	}
-	projected[4].ID = 173
-	if len(appendCDNCanaryAt(cfg, entrysalt.Subject{Token: token}, projected, at)) != 6 {
-		t.Fatal("non SG171 included")
-	}
-}
-
-func TestCDNCanaryFixedAnonymousCohort(t *testing.T) {
-	cfg, _ := canaryFixture(false)
-	count := 0
-	for i := 0; i < 100000; i++ {
-		token := fmt.Sprint("anonymous-fixture-", i)
-		a := cdnCanarySelected(cfg.Secret, token, 100)
-		if a != cdnCanarySelected(cfg.Secret, token, 100) {
-			t.Fatal("unstable cohort")
-		}
-		if a {
-			count++
-		}
-		if cdnCanarySelected(cfg.Secret, token, 101) || cdnCanarySelected(cfg.Secret, token, 0) {
-			t.Fatal("over 1% or zero accepted")
-		}
-	}
-	if count < 850 || count > 1150 {
-		t.Fatalf("unexpected deterministic fixture distribution: %d", count)
-	}
-	if cdnCanarySelected("", "token", 100) || cdnCanarySelected("s", "", 100) {
-		t.Fatal("empty identity admitted")
-	}
-}
-
-func TestCDNCanaryDefaultOffSnapshots(t *testing.T) {
-	for _, flag := range []string{"general", "clashmeta", "clash", "stash", "sing-box", "loon", "surge", "surfboard", "quantumultx"} {
-		t.Run(flag, func(t *testing.T) {
-			var baseline []byte
-			for _, configured := range []bool{false, true} {
-				cfg, rows := canaryFixture(false)
-				if !configured {
-					delete(rows[2].Settings, "cdn_entry_canary")
-				}
-				raw, _ := json.Marshal(cfg)
-				m := entryTestModule(t, "", "")
-				m.settings = settings.NewStatic(map[string]string{subscribeEndpointSaltKey: string(raw), "subscribe_entry_pairs_required": "1"})
-				for _, key := range []string{"clashmeta", "clash", "stash"} {
-					m.tmpls[key] = tmplEntry{content: "proxies: []\nproxy-groups:\n  - name: 悦 · 节点选择\n    type: select\n    proxies: [DIRECT]\nrules:\n  - MATCH,悦 · 节点选择\n", at: time.Now()}
-				}
-				m.tmpls["singbox"] = tmplEntry{content: `{"outbounds":[{"type":"selector","tag":"悦 · 节点选择","outbounds":["auto"]},{"type":"direct","tag":"direct"}]}`, at: time.Now()}
-				m.tmpls["surge"] = tmplEntry{content: defaultSurgeTemplate, at: time.Now()}
-				m.tmpls["surfboard"] = tmplEntry{content: defaultSurfboardTemplate, at: time.Now()}
-				req := httptest.NewRequest("GET", "https://sub.example/s/tok?flag="+flag, nil)
-				w := httptest.NewRecorder()
-				m.deliver(context.Background(), w, req, entrySubUser(), rows, 0, "uuid-test", canaryToken(cfg))
-				if w.Code != 200 {
-					t.Fatalf("status %d", w.Code)
-				}
-				body := w.Body.Bytes()
-				if configured && !bytes.Equal(body, baseline) {
-					t.Fatal("disabled configuration changes output")
-				}
-				baseline = append([]byte(nil), body...)
-			}
-			// Preserve the immutable pre-canary snapshot while allowing exactly
-			// the independently tested cached-refresh policy correction.
-			if flag == "surge" || flag == "surfboard" {
-				header, rest, ok := strings.Cut(string(baseline), "\n")
-				if !ok || !strings.HasPrefix(header, "#!MANAGED-CONFIG ") || !strings.HasSuffix(header, " interval=43200 strict=false") {
-					t.Fatalf("unexpected current managed header %q", header)
-				}
-				baseline = []byte(strings.TrimSuffix(header, "strict=false") + "strict=true\n" + rest)
-			}
-			path := filepath.Join("testdata", "cdn_canary_off_"+flag+".golden")
-			if os.Getenv("I_UPDATE_CANARY_SNAPSHOTS") == "1" {
-				if err := os.WriteFile(path, baseline, 0644); err != nil {
-					t.Fatal(err)
-				}
-			}
-			want, err := os.ReadFile(path)
-			if err != nil {
-				t.Fatal(err)
-			}
-			if !bytes.Equal(want, baseline) {
-				t.Fatal("default-off output differs from pre-canary G23 master snapshot")
-			}
-		})
-	}
-}
-
-func TestCDNCanaryProjectionWiringAndFailClosed(t *testing.T) {
-	for _, tc := range []struct {
-		name string
-		edit func(map[string]any)
-		want int
-	}{
-		{"enabled", func(m map[string]any) {}, 7},
-		{"disabled", func(m map[string]any) { m["enabled"] = false }, 6},
-		{"over-one-percent", func(m map[string]any) { m["basis_points"] = 101 }, 6},
-		{"fraction", func(m map[string]any) { m["basis_points"] = 0.5 }, 6},
-		{"arbitrary-address", func(m map[string]any) { m["address"] = "203.0.113.9" }, 6},
-		{"overlong", func(m map[string]any) { m["expires_at"] = time.Now().Add(96 * time.Hour).Format(time.RFC3339) }, 6},
-		{"expired", func(m map[string]any) { m["expires_at"] = time.Now().Add(-time.Minute).Format(time.RFC3339) }, 6},
-		{"unknown-field", func(m map[string]any) { m["credentials"] = "not-accepted" }, 6},
-	} {
-		t.Run(tc.name, func(t *testing.T) {
-			cfg, rows := canaryFixture(true)
-			conf := rows[2].Settings["cdn_entry_canary"].(map[string]any)
-			conf["starts_at"] = time.Now().Add(-time.Hour).Format(time.RFC3339)
-			conf["expires_at"] = time.Now().Add(time.Hour).Format(time.RFC3339)
-			tc.edit(conf)
-			result, _, err := projectEntryEndpoints(cfg, entrysalt.Subject{Token: canaryToken(cfg)}, rows, true)
-			if err != nil || len(result) != tc.want {
-				t.Fatalf("projection got %d, error %v", len(result), err)
-			}
-		})
-	}
-}
diff --git a/internal/modules/subscribe/delivery_reason_test.go b/internal/modules/subscribe/delivery_reason_test.go
index 4872a424..6ca4ca5d 100644
--- a/internal/modules/subscribe/delivery_reason_test.go
+++ b/internal/modules/subscribe/delivery_reason_test.go
@@ -175,7 +175,9 @@ func TestEntryProjectionFailureClearsNoticeHeaders(t *testing.T) {
 			m.settings = settings.NewStatic(map[string]string{
 				subscribeEndpointSaltKey: string(raw), "subscribe_entry_pairs_required": "1",
 			})
-			rows = append(rows[:2], saltableHY2("203.0.113.7"))
+			rows = rows[:1]
+			rows[0].Settings = admittedHY2Settings()
+			rows[0].Host = "unregistered.example.net"
 			w := httptest.NewRecorder()
 			setDeliveryNotice(w.Header(), clientnotice.KindDeviceLimit, 2, 2)
 			r := httptest.NewRequest(http.MethodGet, "https://sub.example/s/tok", nil)
diff --git a/internal/modules/subscribe/endpoint_ip_literal_delivery_test.go b/internal/modules/subscribe/endpoint_ip_literal_delivery_test.go
index 61be6ef3..bc47970c 100644
--- a/internal/modules/subscribe/endpoint_ip_literal_delivery_test.go
+++ b/internal/modules/subscribe/endpoint_ip_literal_delivery_test.go
@@ -120,55 +120,41 @@ func TestDeliverFleetIPLiteralPrivacyAcrossNineRenderers(t *testing.T) {
 	}
 }
 
-func TestDeliverFleetIPLiteralRequiredPairsFailClosed(t *testing.T) {
+func TestSingleServerPerFormat(t *testing.T) {
 	for _, consumer := range privacyConsumers {
 		t.Run(consumer.renderer, func(t *testing.T) {
-			for _, bad := range []bool{false, true} {
-				cfg, rows := allPairsFixture()
-				// CDN behavior already has actual-deliver coverage in
-				// TestDeliverCDNRewriteSurvivesSafetyFilter; use native pairs here.
-				rows = rows[:2]
-				if bad {
-					row := saltableHY2("203.0.113.7")
-					row.Name = "privacy-unscoped-native"
-					rows = append(rows, row)
+			cfg, rows := allPairsFixture()
+			rows = rows[:2]
+			for _, row := range rows {
+				path := admittedHY2Settings()["entry_path"].(map[string]any)
+				path["backup_required"] = true
+				path["node_id"], path["entry_host"], path["ports"] = row.ID, row.Host, strconv.Itoa(row.Port)
+				if row.Type == "hysteria" {
+					path["tls_server_name"] = gs(row.Settings, "tls.server_name")
+				} else {
+					path["tls_server_name"] = gs(row.Settings, "reality_settings.server_name")
+					row.Settings["network_settings"] = map[string]any{"acceptProxyProtocol": true}
 				}
-				w := privacyDeliver(t, cfg, true, consumer.renderer, consumer.ua, false, rows)
-				if bad {
-					if w.Code != http.StatusInternalServerError || w.Body.Len() != 0 {
-						t.Fatalf("bad native row: status=%d bytes=%d", w.Code, w.Body.Len())
-					}
-					for _, key := range []string{headerHappNewURL, headerHappFallbackURL, headerYueFallbackURLs, "announce", "support-url", "profile-web-page-url", "subscription-userinfo"} {
-						if w.Header().Get(key) != "" {
-							t.Errorf("failed delivery leaked success header %s", key)
-						}
-					}
+				row.Settings["entry_path"] = path
+			}
+			w := privacyDeliver(t, cfg, true, consumer.renderer, consumer.ua, false, rows)
+			if w.Code != http.StatusOK {
+				t.Fatalf("status %d", w.Code)
+			}
+			got := privacyEndpoints(t, consumer.renderer, w.Body.Bytes())
+			count := 0
+			for _, row := range rows {
+				if !privacyEmits(consumer.renderer, row) {
 					continue
 				}
-				if w.Code != http.StatusOK {
-					t.Fatalf("valid pair control status %d", w.Code)
-				}
-				got := privacyEndpoints(t, consumer.renderer, w.Body.Bytes())
-				wantCount := 0
-				for _, row := range rows {
-					if !privacyEmits(consumer.renderer, row) {
-						continue
-					}
-					for _, alternate := range []bool{false, true} {
-						name, host := row.Name+" · A", entrysalt.SaltedHost(cfg, entrysalt.Subject{Token: "privacy-token"}, row.Host)
-						if alternate {
-							name, host = row.Name+" · B", entrysalt.AlternateSaltedHost(cfg, entrysalt.Subject{Token: "privacy-token"}, row.Host)
-						}
-						if endpoint, ok := got[name]; !ok || endpoint.host != host {
-							t.Errorf("valid pair %q missing or wrong host", name)
-						}
-						wantCount++
-					}
-				}
-				if wantCount == 0 || len(got) != wantCount {
-					t.Fatalf("valid control endpoints=%d, want nonzero %d", len(got), wantCount)
+				count++
+				if _, ok := got[row.Name]; !ok {
+					t.Fatalf("missing original name %q", row.Name)
 				}
 			}
+			if len(got) != count {
+				t.Fatalf("nodes=%d want=%d", len(got), count)
+			}
 		})
 	}
 }
diff --git a/internal/modules/subscribe/endpoint_salt_pin_test.go b/internal/modules/subscribe/endpoint_salt_pin_test.go
index 0e90421b..9d0b4a2a 100644
--- a/internal/modules/subscribe/endpoint_salt_pin_test.go
+++ b/internal/modules/subscribe/endpoint_salt_pin_test.go
@@ -34,35 +34,28 @@ func TestSaltSubjectCarriesTheAccountIntoThePinList(t *testing.T) {
 		t.Fatalf("subject = %+v, want account %d in the stable tier", subject, account)
 	}
 	_, rows := allPairsFixture()
-	projected, _, err := projectEntryEndpoints(cfg, subject, rows, true)
+	projected, _, err := projectEntryEndpoints(cfg, subject, rows)
 	if err != nil {
 		t.Fatal(err)
 	}
 	pinKey := cfg.HostBuckets[host][pinBucket]
-	altKey := cfg.HostBuckets[host][cfg.AlternateBuckets[host][pinBucket]]
-	if !strings.Contains(projected[0].Host, pinKey) || !strings.Contains(projected[1].Host, altKey) {
-		t.Fatalf("pair hosts %q %q, want keys %s and %s", projected[0].Host, projected[1].Host, pinKey, altKey)
-	}
-	if projected[0].Host == projected[1].Host || len(projected) != 6 {
-		t.Fatalf("pair projection = %d rows, first hosts %q %q", len(projected), projected[0].Host, projected[1].Host)
-	}
-	if !strings.Contains(projected[2].Host, pinKey) || !strings.Contains(projected[3].Host, altKey) {
-		t.Fatalf("second direct pair %q %q, want keys %s and %s", projected[2].Host, projected[3].Host, pinKey, altKey)
+	if len(projected) != 3 || !strings.Contains(projected[0].Host, pinKey) || !strings.Contains(projected[1].Host, pinKey) {
+		t.Fatal("pin lost")
 	}
 	bareCDN, _ := allPairsFixture()
 	cdnBare, okA := entrysalt.CDNEntryHost(bareCDN, subject, cdnTestHost, false)
 	cdnHere, okB := entrysalt.CDNEntryHost(cfg, subject, cdnTestHost, false)
-	if !okA || !okB || cdnHere != cdnBare || projected[4].Host != cdnHere {
-		t.Fatalf("CDN name moved: projected %q with pin %q without pin %q", projected[4].Host, cdnHere, cdnBare)
+	if !okA || !okB || cdnHere != cdnBare || projected[2].Host != cdnHere {
+		t.Fatalf("CDN name moved: projected %q with pin %q without pin %q", projected[2].Host, cdnHere, cdnBare)
 	}
 
 	_, crowdRows := allPairsFixture()
-	crowd, _, err := projectEntryEndpoints(cfg, entrysalt.Subject{Token: token, UserID: account + 1}, crowdRows, true)
+	crowd, _, err := projectEntryEndpoints(cfg, entrysalt.Subject{Token: token, UserID: account + 1}, crowdRows)
 	if err != nil {
 		t.Fatal(err)
 	}
 	bareCfg, bareRows := allPairsFixture()
-	bare, _, err := projectEntryEndpoints(bareCfg, entrysalt.Subject{Token: token, UserID: account + 1}, bareRows, true)
+	bare, _, err := projectEntryEndpoints(bareCfg, entrysalt.Subject{Token: token, UserID: account + 1}, bareRows)
 	if err != nil {
 		t.Fatal(err)
 	}
diff --git a/internal/modules/subscribe/endpoint_salt_wiring_test.go b/internal/modules/subscribe/endpoint_salt_wiring_test.go
index 2a386940..3a8ac5f2 100644
--- a/internal/modules/subscribe/endpoint_salt_wiring_test.go
+++ b/internal/modules/subscribe/endpoint_salt_wiring_test.go
@@ -22,7 +22,7 @@ func TestEndpointSaltIsCalledFromDeliverAtTheRightPosition(t *testing.T) {
 	// （少一个锚点 = 少判一条顺序）。见 packagesource_test.go。
 	body := subscribeFuncBody(t, "deliver")
 
-	call := strings.Index(body, "projectEntryEndpoints(saltCfg, saltSubject, servers, requireAllPairs)")
+	call := strings.Index(body, "projectEntryEndpoints(saltCfg, saltSubject, servers, requireEntry)")
 	if call < 0 {
 		t.Fatal("deliver() 里找不到 projectEntryEndpoints 调用 —— 共享加盐投影不可绕过")
 	}
diff --git a/internal/modules/subscribe/entry_path_test.go b/internal/modules/subscribe/entry_path_test.go
index 7f9aafec..c9ddd3d7 100644
--- a/internal/modules/subscribe/entry_path_test.go
+++ b/internal/modules/subscribe/entry_path_test.go
@@ -4,8 +4,6 @@ import (
 	"context"
 	"encoding/base64"
 	"encoding/json"
-	"fmt"
-	"github.com/onesyue/yueboard/internal/platform/entrysalt"
 	"github.com/onesyue/yueboard/internal/platform/settings"
 	"net/http/httptest"
 	"strings"
@@ -91,51 +89,7 @@ func TestDBPortOverrideCannotEscapeEntryLease(t *testing.T) {
 	}
 }
 
-func TestDualActiveExpansionKeepsABOrderAndSpreadsPrimaryBuckets(t *testing.T) {
-	cfg := &endpointSaltConfig{Enabled: true, Zone: "salt.example.net", Secret: "test",
-		HostBuckets:      map[string][]string{"entry.example.net": {"aaaa1111", "bbbb2222"}},
-		AlternateBuckets: map[string][]int{"entry.example.net": {1, 0}}}
-	source := &serverRow{ID: 43, Name: "香港", Type: "hysteria", Host: "entry.example.net", Port: 41000, Ports: "41000-41511", Settings: admittedHY2Settings()}
-	source.Settings["entry_path"].(map[string]any)["backup_required"] = true
-	first := map[int]int{}
-	for i := 0; i < 100; i++ {
-		subject := entrysalt.Subject{Token: fmt.Sprint(i)}
-		expanded, err := expandEntryAlternates(cfg, subject, []*serverRow{source})
-		if err != nil || len(expanded) != 2 {
-			t.Fatalf("dual entry missing: %v", err)
-		}
-		if expanded[0].entryAlternate || !expanded[1].entryAlternate || !strings.HasSuffix(expanded[0].Name, " · A") || !strings.HasSuffix(expanded[1].Name, " · B") {
-			t.Fatal("pair is not adjacent A then B")
-		}
-		bucket, ok := entrysalt.BucketIndex(cfg, subject, source.Host)
-		if !ok {
-			t.Fatal("primary bucket missing")
-		}
-		first[bucket]++
-		if expanded[0].Name == expanded[1].Name || source.Name != "香港" || expanded[0] == source {
-			t.Fatal("mutated cached origin or collapsed names")
-		}
-		if expanded[0].ID != 43 || expanded[1].ID != 43 || expanded[0].Ports != expanded[1].Ports {
-			t.Fatal("alternate changed billing identity or port lease")
-		}
-		if applyEndpointSaltFor(cfg, subject, expanded) != 2 || expanded[0].Host == expanded[1].Host {
-			t.Fatal("alternate did not reach distinct consumer dial host")
-		}
-		again, _ := expandEntryAlternates(cfg, subject, []*serverRow{source})
-		if again[0].entryAlternate != expanded[0].entryAlternate {
-			t.Fatal("preference changes on refresh")
-		}
-	}
-	if first[0] < 20 || first[1] < 20 {
-		t.Fatalf("one entry is idle: %v", first)
-	}
-	delete(cfg.AlternateBuckets, "entry.example.net")
-	if _, err := expandEntryAlternates(cfg, entrysalt.Subject{Token: "one"}, []*serverRow{source}); err == nil {
-		t.Fatal("published route silently lost required second entry")
-	}
-}
-
-func TestDualActivePathsReachEverySupportedRenderer(t *testing.T) {
+func TestSingleEntryReachesEverySupportedRenderer(t *testing.T) {
 	cfg := &endpointSaltConfig{Enabled: true, Zone: "salt.example.net", Secret: "test",
 		HostBuckets:      map[string][]string{"entry.example.net": {"aaaa1111", "bbbb2222"}},
 		AlternateBuckets: map[string][]int{"entry.example.net": {1, 0}}}
@@ -182,7 +136,7 @@ func TestDualActivePathsReachEverySupportedRenderer(t *testing.T) {
 				}
 				body = string(decoded)
 			}
-			if w.Code != 200 || !strings.Contains(body, ".aaaa1111.salt.example.net") || !strings.Contains(body, ".bbbb2222.salt.example.net") || strings.Contains(body, "entry.example.net") {
+			if w.Code != 200 || strings.Contains(body, " · A") || strings.Contains(body, " · B") || strings.Contains(body, "entry.example.net") {
 				t.Fatalf("renderer lost a live path: status=%d body=%.400s", w.Code, body)
 			}
 			if h.Host != "entry.example.net" || v.Host != h.Host || strings.Contains(h.Name, " · ") {
@@ -191,3 +145,30 @@ func TestDualActivePathsReachEverySupportedRenderer(t *testing.T) {
 		})
 	}
 }
+
+func TestSubscriptionIgnoresLegacyAlternateMetadata(t *testing.T) {
+	raw, err := json.Marshal(saltTestCfg())
+	if err != nil {
+		t.Fatal(err)
+	}
+	var document map[string]any
+	if err := json.Unmarshal(raw, &document); err != nil {
+		t.Fatal(err)
+	}
+	document["alternate_buckets"] = map[string]any{"obsolete.example": []int{999}}
+	document["cdn_alternate_buckets"] = map[string]any{"obsolete.example": []int{-1}}
+	raw, _ = json.Marshal(document)
+	for _, lastGood := range []bool{false, true} {
+		values := map[string]string{subscribeEndpointSaltKey: string(raw)}
+		if lastGood {
+			values[subscribeEndpointSaltKey] = "broken"
+			values[subscribeEndpointSaltLastGoodKey] = string(raw)
+		}
+		m := entryTestModule(t, "", "")
+		m.settings = settings.NewStatic(values)
+		cfg := m.endpointSalt(context.Background())
+		if cfg == nil || len(cfg.AlternateBuckets) != 0 || len(cfg.CDNAlternateBuckets) != 0 {
+			t.Fatal("legacy alternates affected subscription parsing")
+		}
+	}
+}
diff --git a/internal/modules/subscribe/info_rows_unreachable_test.go b/internal/modules/subscribe/info_rows_unreachable_test.go
index 7ace91f5..75439a17 100644
--- a/internal/modules/subscribe/info_rows_unreachable_test.go
+++ b/internal/modules/subscribe/info_rows_unreachable_test.go
@@ -33,7 +33,7 @@ func TestInfoRowsCannotCarryTraffic(t *testing.T) {
 			if s.Host != "127.0.0.1" || s.Port != 9 || s.Ports != "" {
 				t.Fatalf("info row %q still routes to %s:%d (ports %q)", s.Name, s.Host, s.Port, s.Ports)
 			}
-			if s.entryAlternate || s.cdnOriginHost != "" {
+			if s.cdnOriginHost != "" {
 				t.Fatalf("info row %q keeps entry identity", s.Name)
 			}
 		}
diff --git a/internal/modules/subscribe/pair_gate_parity_test.go b/internal/modules/subscribe/pair_gate_parity_test.go
deleted file mode 100644
index e5f850d4..00000000
--- a/internal/modules/subscribe/pair_gate_parity_test.go
+++ /dev/null
@@ -1,48 +0,0 @@
-package subscribe
-
-import (
-	"fmt"
-	"math/rand/v2"
-	"testing"
-
-	"github.com/onesyue/yueboard/internal/platform/entrysalt"
-	"github.com/onesyue/yueboard/internal/platform/nativeproto"
-)
-
-// 2026-10-11 复核 B-11：自动显示的门（entrysalt.PairDeliverable，nodesync 的
-// requireVisibleEntryPairs 用它）放行的产品，交付在 required=1 下对**任意**订阅都必须能出
-// A/B 两条——否则门放行之后，能看到它的整份订阅 fail-closed。反向：门拒绝没有显式 SNI 的产品。
-func TestPairDeliverableImpliesDeliveryForEverySubject(t *testing.T) {
-	cfg, rows := allPairsFixture()
-	r := rand.New(rand.NewPCG(20261011, 11))
-	for _, row := range rows {
-		cdn := row.Type == "vless" && nativeproto.IsCDNWebSocketVless(row.Settings)
-		if err := entrysalt.PairDeliverable(cfg, row.Host, cdn, hasExplicitSNI(row)); err != nil {
-			t.Fatalf("%s: gate refused a deliverable fixture: %v", row.Name, err)
-		}
-		for i := range 500 {
-			subject := entrysalt.Subject{Token: fmt.Sprintf("tok-%d-%d", i, r.Uint64()), Quarantine: r.IntN(2) == 0}
-			if _, _, err := projectEntryEndpoints(cfg, subject, []*serverRow{row}, true); err != nil {
-				t.Fatalf("%s: gate passed but delivery failed for %+v: %v", row.Name, subject, err)
-			}
-		}
-	}
-	// 没有显式 SNI 的 HY2：门必须拒绝，因为交付一定失败。
-	noSNI := *rows[0]
-	noSNI.Settings = map[string]any{"version": 2, "tls": map[string]any{}}
-	if entrysalt.PairDeliverable(cfg, noSNI.Host, false, hasExplicitSNI(&noSNI)) == nil {
-		t.Fatal("gate admitted a product without an explicit server name")
-	}
-	if _, _, err := projectEntryEndpoints(cfg, entrysalt.Subject{Token: "x"}, []*serverRow{&noSNI}, true); err == nil {
-		t.Fatal("fixture: delivery should fail without an explicit server name")
-	}
-	// scope 在，但该命名空间的 alternate 投影缺失：门拒绝（交付同样失败）。
-	partial := *cfg
-	partial.AlternateBuckets = map[string][]int{}
-	if entrysalt.PairDeliverable(&partial, rows[0].Host, false, true) == nil {
-		t.Fatal("gate admitted a host without an alternate projection")
-	}
-	if entrysalt.PairDeliverable(cfg, "unscoped.example.net", false, true) != entrysalt.ErrPairScopeAbsent {
-		t.Fatal("missing scope must report ErrPairScopeAbsent")
-	}
-}
diff --git a/internal/modules/subscribe/region_ai_test.go b/internal/modules/subscribe/region_ai_test.go
deleted file mode 100644
index 031afe0c..00000000
--- a/internal/modules/subscribe/region_ai_test.go
+++ /dev/null
@@ -1,90 +0,0 @@
-package subscribe
-
-import (
-	"encoding/json"
-	"reflect"
-	"strings"
-	"testing"
-
-	"github.com/onesyue/yueboard/internal/platform/settings"
-	"go.yaml.in/yaml/v3"
-)
-
-// Exercise delivery so both feature settings and format-specific ordering apply.
-func TestRegionSingleAICompatibility(t *testing.T) {
-	for _, client := range []string{"clashmeta", "clash", "stash", "sing-box", "surge", "surfboard"} {
-		t.Run(client, func(t *testing.T) {
-			rows := []*serverRow{hy2Server(), realityServer(), hy2Server(), realityServer()}
-			for i, row := range rows {
-				row.Password = regionTestUUID
-				row.Name = []string{"🇺🇸 US AI H", "🇯🇵 JP AI V", "🇸🇬 H", "🇸🇬 V"}[i]
-			}
-			render := func(ai, region string) []byte {
-				m := aiModule(t, ai)
-				m.settings = settings.NewStatic(map[string]string{singleAIGroupSetting: ai, regionEntrySetting: region})
-				return deliverTransport(t, m, client, rows)
-			}
-			if string(render("", "1")) != string(render("0", "1")) {
-				t.Fatal("default-off AI changed regional output")
-			}
-			baseline, combined := render("1", "0"), render("1", "1")
-			if client == "surge" || client == "surfboard" {
-				aiLine := func(body []byte) string {
-					for _, line := range strings.Split(string(body), "\n") {
-						if strings.HasPrefix(line, "AI =") {
-							return line
-						}
-					}
-					t.Fatal("missing AI group")
-					return ""
-				}
-				if aiLine(baseline) != aiLine(combined) {
-					t.Fatal("regional selection changed AI group")
-				}
-				if !strings.Contains(string(combined), "🇸🇬 = select,") {
-					t.Fatal("missing manual region")
-				}
-				return
-			}
-			decode := func(body []byte) []any {
-				cfg := map[string]any{}
-				if client == "sing-box" {
-					if err := json.Unmarshal(body, &cfg); err != nil {
-						t.Fatal(err)
-					}
-					return cfg["outbounds"].([]any)
-				}
-				if err := yaml.Unmarshal(body, &cfg); err != nil {
-					t.Fatal(err)
-				}
-				return cfg["proxy-groups"].([]any)
-			}
-			nameKey, manual := "name", "select"
-			if client == "sing-box" {
-				nameKey, manual = "tag", "selector"
-			}
-			find := func(groups []any, name string) map[string]any {
-				for _, raw := range groups {
-					g := raw.(map[string]any)
-					if g[nameKey] == name {
-						return g
-					}
-				}
-				return nil
-			}
-			before, after := decode(baseline), decode(combined)
-			if !reflect.DeepEqual(find(before, "AI"), find(after, "AI")) {
-				t.Fatal("regional selection changed AI group")
-			}
-			if client != "clash" {
-				if find(after, "AI") == nil {
-					t.Fatal("missing AI group")
-				}
-				region := find(after, "🇸🇬")
-				if region == nil || region["type"] != manual {
-					t.Fatal("missing manual region")
-				}
-			}
-		})
-	}
-}
diff --git a/internal/modules/subscribe/region_entry_test.go b/internal/modules/subscribe/region_entry_test.go
deleted file mode 100644
index f3af6c80..00000000
--- a/internal/modules/subscribe/region_entry_test.go
+++ /dev/null
@@ -1,690 +0,0 @@
-package subscribe
-
-import (
-	"bytes"
-	"context"
-	"encoding/base64"
-	"encoding/json"
-	"fmt"
-	"net/http/httptest"
-	"net/url"
-	"os"
-	"path/filepath"
-	"strings"
-	"testing"
-	"time"
-
-	"github.com/google/uuid"
-	"github.com/onesyue/yueboard/internal/platform/settings"
-	"gopkg.in/yaml.v3"
-)
-
-const regionTestUUID = "12345678-1234-4234-8234-123456789abc"
-
-var regionTestFormats = []string{"general", "clashmeta", "clash", "stash", "sing-box", "loon", "surge", "surfboard", "quantumultx"}
-
-func regionTestDelivery(t *testing.T, flag, auto, credential string, enabled bool) *httptest.ResponseRecorder {
-	t.Helper()
-	cfg, rows := allPairsFixture()
-	for i, s := range rows {
-		s.Name = []string{"悦·🇸🇬新加坡1", "悦·🇸🇬新加坡2", "悦·🇸🇬新加坡CF"}[i]
-		s.Password = credential
-		if s.Type == "vless" && i == 1 {
-			s.Settings = checkableRealityServer().Settings
-		}
-	}
-	raw, err := json.Marshal(cfg)
-	if err != nil {
-		t.Fatal(err)
-	}
-	m := entryTestModule(t, "", "")
-	value := "0"
-	if enabled {
-		value = "1"
-	}
-	m.settings = settings.NewStatic(map[string]string{subscribeEndpointSaltKey: string(raw), "subscribe_entry_pairs_required": "1", regionEntrySetting: value})
-	for _, key := range []string{"clashmeta", "clash", "stash"} {
-		m.tmpls[key] = tmplEntry{content: "proxies: []\nproxy-groups:\n  - name: Proxy\n    type: select\n    proxies: []\nrules:\n  - MATCH,Proxy\n", at: time.Now()}
-	}
-	m.tmpls["singbox"] = tmplEntry{content: `{"outbounds":[{"type":"selector","tag":"Proxy","outbounds":[]},{"type":"direct","tag":"direct"}],"route":{"final":"Proxy"}}`, at: time.Now()}
-	for _, key := range []string{"surge", "surfboard"} {
-		m.tmpls[key] = tmplEntry{content: "#!MANAGED-CONFIG $subs_link interval=43200 strict=false\n[Proxy]\n$proxies\n[Proxy Group]\nProxy = select, $proxy_group\n[Rule]\nFINAL,Proxy\n", at: time.Now()}
-	}
-	request := httptest.NewRequest("GET", "https://sub.example/s/test?flag="+flag+"&auto%5Fselect="+auto, nil)
-	w := httptest.NewRecorder()
-	m.deliver(context.Background(), w, request, entrySubUser(), rows, 0, credential, "synthetic-region-test")
-	return w
-}
-
-func TestRegionEntryAllFormats(t *testing.T) {
-	for _, flag := range regionTestFormats {
-		for _, auto := range []string{"", "0", "1", "true"} {
-			t.Run(flag+"/auto="+auto, func(t *testing.T) {
-				w := regionTestDelivery(t, flag, auto, regionTestUUID, true)
-				if w.Code != 200 {
-					t.Fatalf("delivery status %d", w.Code)
-				}
-				body := w.Body.Bytes()
-				if flag == "clash" {
-					if bytes.Contains(body, []byte(regionTestUUID)) || !bytes.Contains(body, []byte("旧客户端")) {
-						t.Fatal("legacy Clash capability gate changed")
-					}
-					return
-				}
-				switch flag {
-				case "clashmeta", "clash", "stash", "sing-box":
-					cfg := map[string]any{}
-					groupKey, nameKey, memberKey, manual := "proxy-groups", "name", "proxies", "select"
-					if flag == "sing-box" {
-						if err := json.Unmarshal(body, &cfg); err != nil {
-							t.Fatal(err)
-						}
-						groupKey, nameKey, memberKey, manual = "outbounds", "tag", "outbounds", "selector"
-					} else if err := yaml.Unmarshal(body, &cfg); err != nil {
-						t.Fatal(err)
-					}
-					assertRegionOutputUUIDs(t, cfg)
-					groups, _ := cfg[groupKey].([]any)
-					count := 0
-					for _, raw := range groups {
-						g := raw.(map[string]any)
-						if g[nameKey] == "Proxy" {
-							members := omitShareSubscriptionNotice(regionStrings(g[memberKey]))
-							if len(members) != 1 || members[0] != "🇸🇬" || g["type"] != manual {
-								t.Fatalf("top-level choice is not one manual region: %v", members)
-							}
-						}
-						if g[nameKey] != "🇸🇬" {
-							continue
-						}
-						count++
-						if g["type"] != manual {
-							t.Fatal("wrong region selection mode")
-						}
-						members := regionStrings(g[memberKey])
-						if len(members) != 6 || !strings.Contains(members[0], "新加坡1 · A") || !strings.Contains(members[1], "新加坡1 · B") || !strings.Contains(members[4], "CF · A") {
-							t.Fatal("region lost paired transport order")
-						}
-						if g["tolerance"] != nil || g["url"] != nil || g["interval"] != nil {
-							t.Fatal("regional selector retains probe settings")
-						}
-						if flag == "sing-box" && g["default"] != members[0] {
-							t.Fatal("primary not default")
-						}
-					}
-					if count != 1 {
-						t.Fatalf("got %d region groups", count)
-					}
-					if !bytes.Contains(body, []byte(regionTestUUID)) {
-						t.Fatal("UUID missing")
-					}
-				case "surge", "surfboard":
-					mode := "select"
-					text := string(body)
-					if !strings.Contains(text, "🇸🇬 = "+mode+", 悦·🇸🇬新加坡1 · A, 悦·🇸🇬新加坡1 · B") || !strings.Contains(text, "Proxy = select, 🇸🇬") {
-						t.Fatal("incorrect supported regional group")
-					}
-					if strings.Contains(text, "新加坡2") || strings.Contains(text, "新加坡CF") {
-						t.Fatal("unsupported protocol emitted")
-					}
-					if strings.Contains(text, "tolerance=80") {
-						t.Fatal("regional selector retains probe settings")
-					}
-				default:
-					if flag != "loon" {
-						var err error
-						body, err = base64.StdEncoding.DecodeString(string(body))
-						if err != nil {
-							t.Fatal(err)
-						}
-					}
-					if bytes.Count(body, []byte(regionTestUUID)) != 1 {
-						t.Fatalf("flat resource contains %d entries", len(strings.Split(strings.TrimSpace(string(body)), "\n")))
-					}
-					if !bytes.Contains(body, []byte(regionTestUUID)) {
-						t.Fatal("UUID lost")
-					}
-					if flag == "quantumultx" && !bytes.Contains(body, []byte("vless=")) {
-						t.Fatal("QX did not select supported primary")
-					}
-					if flag == "general" && !bytes.HasPrefix(body, []byte("hysteria2://")) {
-						t.Fatal("general did not prefer HY2")
-					}
-				}
-			})
-		}
-	}
-}
-
-func TestRegionEntryInvalidUUIDAllFormats(t *testing.T) {
-	for _, flag := range regionTestFormats {
-		for _, invalid := range []string{"uuid-test", "12345678123442348234123456789abc", "00000000-0000-0000-0000-000000000000", "12345678-1234-4234-8234-123456789abz", "{12345678-1234-4234-8234-123456789abc}"} {
-			t.Run(flag, func(t *testing.T) {
-				w := regionTestDelivery(t, flag, "", invalid, true)
-				if w.Code != 500 || w.Body.Len() != 0 {
-					t.Fatal("invalid UUID not rejected without response details")
-				}
-			})
-		}
-	}
-}
-
-func TestRegionEntrySwitchDominatesParameter(t *testing.T) {
-	for _, flag := range regionTestFormats {
-		a := regionTestDelivery(t, flag, "", regionTestUUID, false)
-		b := regionTestDelivery(t, flag, "1", regionTestUUID, false)
-		if a.Code != 200 || b.Code != 200 || !bytes.Equal(a.Body.Bytes(), b.Body.Bytes()) {
-			t.Fatalf("%s: auto parameter changes disabled output", flag)
-		}
-	}
-}
-
-func TestRegionEntryBoundaries(t *testing.T) {
-	a := hy2Row()
-	a.Name = "悦·🇸🇬新加坡1"
-	a.Password = regionTestUUID
-	b := *a
-	b.Name = "悦·🇯🇵日本1"
-	c := *a
-	c.Name = "translated"
-	c.SourceName = a.Name
-	external := *a
-	external.external = true
-	groups := makeRegionMembers([]*serverRow{a, &b, &c, &external}, []string{"a", "b", "c", "external"}, []string{"🇸🇬"})
-	if len(groups) != 2 || groups[0].name == "🇸🇬" || len(groups[0].members) != 2 {
-		t.Fatal("region identity, collision or external isolation failed")
-	}
-	got := collapseRegionMembers([]string{"a", "b"}, groups)
-	if len(got) != 2 || got[0] != "a" || got[1] != groups[1].name {
-		t.Fatal("partial capability set widened")
-	}
-	if err := validateRegionCredentials([]*serverRow{a}); err != nil {
-		t.Fatal("valid UUID rejected")
-	}
-}
-
-// Optional export is synthetic only; it never reads database or subscription URLs.
-func TestRegionExportCoreFixtures(t *testing.T) {
-	dir := os.Getenv("YUEBOARD_REGION_FIXTURE_DIR")
-	if dir == "" {
-		t.Skip("fixture export not requested")
-	}
-	for _, flag := range regionTestFormats {
-		for _, mode := range []string{"off", "manual", "ignored"} {
-			auto := ""
-			if mode == "ignored" {
-				auto = "1"
-			}
-			w := regionTestDelivery(t, flag, auto, regionTestUUID, mode != "off")
-			if w.Code != 200 {
-				t.Fatal("fixture rendering failed")
-			}
-			if err := os.WriteFile(filepath.Join(dir, flag+"-"+mode+".conf"), w.Body.Bytes(), 0600); err != nil {
-				t.Fatal(err)
-			}
-		}
-	}
-}
-
-func TestRegionTemplateAliasesAndDefaults(t *testing.T) {
-	a := hy2Row()
-	a.Name = "悦·🇸🇬新加坡1"
-	a.Password = regionTestUUID
-	b := *a
-	b.Name = "悦·🇸🇬新加坡1 · B"
-	b.entryAlternate = true
-	b.defaultGroupHeld = true
-	for _, sb := range []bool{false, true} {
-		nameKey, memberKey, manual, auto := "name", "proxies", "select", "url-test"
-		if sb {
-			nameKey, memberKey, manual, auto = "tag", "outbounds", "selector", "urltest"
-		}
-		groups := []any{
-			map[string]any{nameKey: "Proxy", "type": manual, memberKey: []any{"auto", "🇸🇬 Singapore", "🇸🇬 Alias", a.Name, b.Name}, "include-all": true},
-			map[string]any{nameKey: "auto", "type": auto, memberKey: []any{a.Name}},
-			map[string]any{nameKey: "🇸🇬 Singapore", "type": auto, memberKey: []any{a.Name, b.Name}},
-			map[string]any{nameKey: "🇸🇬 Alias", "type": manual, memberKey: []any{a.Name, b.Name}},
-			map[string]any{nameKey: "Domestic", "type": manual, memberKey: []any{"Proxy", "direct"}, "default": "direct"},
-		}
-		ctx := context.WithValue(context.Background(), regionEntryKey{}, regionEntryOptions{enabled: true})
-		result := applyRegionGroups(ctx, groups, []*serverRow{a, &b}, []string{a.Name, b.Name}, sb)
-		regionCount := 0
-		for _, raw := range result {
-			g := raw.(map[string]any)
-			switch g[nameKey] {
-			case "Proxy":
-				members := regionStrings(g[memberKey])
-				if len(members) != 2 || members[0] != "🇸🇬 Singapore" || g["include-all"] != nil {
-					t.Fatal("legacy default or alias survived")
-				}
-			case "Domestic":
-				if sb && g["default"] != "direct" {
-					t.Fatal("unrelated explicit default changed")
-				}
-			case "🇸🇬 Alias":
-				t.Fatal("duplicate regional alias is still visible")
-			case "🇸🇬 Singapore":
-				regionCount++
-				if g["type"] != manual || !sameRegionMembers(regionStrings(g[memberKey]), []string{a.Name, b.Name}) {
-					t.Fatal("manual region lost selectable members")
-				}
-			}
-		}
-		if regionCount != 1 {
-			t.Fatal("duplicate canonical region")
-		}
-	}
-}
-
-func TestRegionEmbeddedSurgeDefault(t *testing.T) {
-	for _, format := range []string{"surge", "surfboard"} {
-		m := entryTestModule(t, format, "")
-		m.settings = settings.NewStatic(map[string]string{})
-		row := hy2Row()
-		row.Name = "悦·🇸🇬新加坡1"
-		row.Password = regionTestUUID
-		ctx := context.WithValue(context.Background(), regionEntryKey{}, regionEntryOptions{enabled: true})
-		r := httptest.NewRequest("GET", "https://sub.example/s/test", nil)
-		var body []byte
-		if format == "surge" {
-			body = m.renderSurge(ctx, r, entrySubUser(), []*serverRow{row}, "https://sub.example/s/test")
-		} else {
-			body = m.renderSurfboard(ctx, r, entrySubUser(), []*serverRow{row}, "https://sub.example/s/test")
-		}
-		if !bytes.Contains(body, []byte("Proxy = select, 🇸🇬,")) || !bytes.Contains(body, []byte("🇸🇬 = select, 悦·🇸🇬新加坡1")) {
-			t.Fatalf("%s embedded template does not default to regional primary", format)
-		}
-	}
-}
-
-func TestRegionMigrationIgnoresRetiredPreference(t *testing.T) {
-	m := fallbackModule("https://backup.example")
-	m.settings = settings.NewStatic(map[string]string{regionEntrySetting: "1"})
-	r := httptest.NewRequest("GET", "https://sub.example/s/test?auto%5Fselect=1&burn=1", nil)
-	w := httptest.NewRecorder()
-	m.setSubscriptionFallbackHeaders(w, r, "synthetic")
-	for _, value := range []string{w.Header().Get(headerHappNewURL), m.verifiedSubscriptionURL(r, "synthetic")} {
-		parsed, err := url.Parse(value)
-		if err != nil || len(parsed.Query()) != 1 || parsed.Query().Get("burn") != "1" {
-			t.Fatal("migration or refresh must preserve only burn")
-		}
-	}
-}
-
-func TestRegionProductionSingBoxTemplates(t *testing.T) {
-	for _, name := range []string{"subscribe_templates-1-zh-CN.json", "subscribe_templates-9-en.json"} {
-		m := entryTestModule(t, "singbox", loadProdSingBoxTemplate(t, name))
-		a := hy2Row()
-		a.Name = "悦·🇸🇬新加坡1"
-		a.Password = regionTestUUID
-		b := checkableRealityServer()
-		b.Name = "悦·🇸🇬新加坡2"
-		b.Password = regionTestUUID
-		ctx := context.WithValue(context.Background(), regionEntryKey{}, regionEntryOptions{enabled: true})
-		data, err := m.renderSingBox(ctx, []*serverRow{a, b})
-		if err != nil {
-			t.Fatal(err)
-		}
-		cfg := map[string]any{}
-		if err = json.Unmarshal(data, &cfg); err != nil {
-			t.Fatal(err)
-		}
-		groups := map[string]map[string]any{}
-		for _, raw := range cfg["outbounds"].([]any) {
-			g := raw.(map[string]any)
-			groups[g["tag"].(string)] = g
-		}
-		canonical := ""
-		for tag, g := range groups {
-			members := regionStrings(g["outbounds"])
-			if len(members) == 2 && members[0] == a.Name && members[1] == b.Name {
-				if canonical != "" {
-					t.Fatal("duplicate regional node selectors")
-				}
-				canonical = tag
-				if g["type"] != "selector" || g["default"] != a.Name {
-					t.Fatal("regional primary default lost")
-				}
-			}
-			for _, member := range members {
-				if groups[member] == nil {
-					t.Fatal("dangling outbound reference")
-				}
-			}
-		}
-		if canonical == "" {
-			t.Fatal("production template lost regional group")
-		}
-		referenced := false
-		for tag, g := range groups {
-			if tag != canonical && strings.Contains(tag, "节点选择") || tag == "Yue · Node Selection" {
-				referenced = referenced || strings.Contains(strings.Join(regionStrings(g["outbounds"]), "|"), canonical)
-			}
-		}
-		// Templates may localize the root label; every canonical region must be
-		// reachable from at least one non-regional parent, regardless of its label.
-		if !referenced {
-			for tag, g := range groups {
-				if tag != canonical {
-					for _, member := range regionStrings(g["outbounds"]) {
-						if member == canonical {
-							referenced = true
-						}
-					}
-				}
-			}
-		}
-		if !referenced {
-			t.Fatal("region is not selectable")
-		}
-	}
-}
-
-func TestRegionStrictNamedSubsetAndServicePolicy(t *testing.T) {
-	a := hy2Row()
-	a.Name = "悦·🇸🇬新加坡1"
-	b := vlessRealityRow()
-	b.Name = "悦·🇸🇬新加坡2"
-	ctx := context.WithValue(context.Background(), regionEntryKey{}, regionEntryOptions{enabled: true})
-	groups := []any{
-		map[string]any{"name": "Proxy", "type": "select", "proxies": []any{"🇸🇬 Direct", a.Name, b.Name}},
-		map[string]any{"name": "🇸🇬 Direct", "type": "url-test", "proxies": []any{a.Name}},
-	}
-	rewrites := map[string]string{}
-	result := applyRegionGroups(ctx, groups, []*serverRow{a, b}, []string{a.Name, b.Name}, false, regionGroupExtras{rewrites: rewrites})
-	if rewrites["🇸🇬 Direct"] != a.Name {
-		t.Fatal("restricted regional policy was widened")
-	}
-	for _, raw := range result {
-		g := raw.(map[string]any)
-		if g["name"] == "Proxy" && len(regionStrings(g["proxies"])) != 1 {
-			t.Fatal("root exposes duplicate region choice")
-		}
-		if g["name"] == "🇸🇬 Direct" {
-			t.Fatal("restricted regional helper remains visible")
-		}
-	}
-	const service = "Service = fallback, Proxy, DIRECT, url=https://example.test/check, interval=60"
-	profile := "[Proxy Group]\nProxy = select, " + a.Name + "\n" + service + "\n[Rule]\nFINAL,Proxy\n"
-	out := applyRegionINI(ctx, profile, []*serverRow{a})
-	if !strings.Contains(out, service+"\n") || strings.Contains(out, "region-ini-original") {
-		t.Fatal("unrelated INI service policy changed")
-	}
-}
-
-func assertRegionOutputUUIDs(t *testing.T, value any) {
-	t.Helper()
-	switch v := value.(type) {
-	case map[string]any:
-		for key, child := range v {
-			if key == "uuid" {
-				text, ok := child.(string)
-				if !ok {
-					t.Fatal("non-string emitted UUID")
-				}
-				parsed, err := uuid.Parse(text)
-				if err != nil || len(text) != 36 || parsed == uuid.Nil || !strings.EqualFold(parsed.String(), text) {
-					t.Fatal("noncanonical emitted UUID")
-				}
-			} else {
-				assertRegionOutputUUIDs(t, child)
-			}
-		}
-	case []any:
-		for _, child := range v {
-			assertRegionOutputUUIDs(t, child)
-		}
-	}
-}
-
-func TestRegionNestedAutomaticSelection(t *testing.T) {
-	for _, singbox := range []bool{false, true} {
-		t.Run(fmt.Sprint(singbox), func(t *testing.T) {
-			a, b := hy2Row(), vlessRealityRow()
-			a.Name, b.Name = "悦·🇸🇬 HY2", "悦·🇸🇬 VLESS"
-			nk, mk, auto, manual := "name", "proxies", "url-test", "select"
-			if singbox {
-				nk, mk, auto, manual = "tag", "outbounds", "urltest", "selector"
-			}
-			groups := []any{
-				map[string]any{nk: "Root", "type": auto, mk: []any{"HY2", "VLESS"}},
-				map[string]any{nk: "HY2", "type": manual, mk: []any{a.Name}},
-				map[string]any{nk: "VLESS", "type": manual, mk: []any{b.Name}},
-				map[string]any{nk: "Service", "type": "fallback", mk: []any{"Root", "DIRECT"}},
-			}
-			ctx := context.WithValue(context.Background(), regionEntryKey{}, regionEntryOptions{enabled: true})
-			for _, raw := range applyRegionGroups(ctx, groups, []*serverRow{a, b}, []string{a.Name, b.Name}, singbox) {
-				g := raw.(map[string]any)
-				if g[nk] == "Root" && g["type"] != manual {
-					t.Fatal("nested protocol choices remain automatic")
-				}
-				if g[nk] == "Service" && g["type"] != "fallback" {
-					t.Fatal("service recovery changed")
-				}
-			}
-		})
-	}
-}
-
-func TestRegionINIDynamicMembership(t *testing.T) {
-	for _, format := range []string{"surge", "surfboard"} {
-		t.Run(format, func(t *testing.T) {
-			a := hy2Row()
-			a.Name = "悦·🇸🇬 Singapore"
-			a.Password = regionTestUUID
-			m := entryTestModule(t, format, "[Proxy]\n$proxies\n[Proxy Group]\nProxy = select, 🇸🇬 Singapore, 🇭🇰 Hong Kong, $proxy_group\n🇸🇬 Singapore = url-test, include-all-proxies=true, policy-regex-filter=🇸🇬, url=https://example.test/check\n🇭🇰 Hong Kong = url-test, include-all-proxies=true, policy-regex-filter=🇭🇰, url=https://example.test/check\n[Rule]\nDOMAIN-SUFFIX,hk.example,🇭🇰 Hong Kong\nFINAL,Proxy\n")
-			ctx := context.WithValue(context.Background(), regionEntryKey{}, regionEntryOptions{enabled: true})
-			r := httptest.NewRequest("GET", "https://sub.example", nil)
-			var body []byte
-			if format == "surge" {
-				body = m.renderSurge(ctx, r, entrySubUser(), []*serverRow{a}, "https://sub.example")
-			} else {
-				body = m.renderSurfboard(ctx, r, entrySubUser(), []*serverRow{a}, "https://sub.example")
-			}
-			text := string(body)
-			if strings.Contains(text, "🇭🇰") || strings.Contains(text, "url-test") || strings.Contains(text, "include-all-proxies") {
-				t.Fatal("dynamic or unavailable region remains")
-			}
-			if !strings.Contains(text, "Proxy = select, 🇸🇬 Singapore\n") || !strings.Contains(text, "🇸🇬 Singapore = select, "+a.Name+"\n") {
-				t.Fatal("region is not the sole manual entry")
-			}
-			if !strings.Contains(text, "DOMAIN-SUFFIX,hk.example,REJECT") {
-				t.Fatal("unavailable region route did not fail closed")
-			}
-		})
-	}
-}
-
-func TestRegionPairedOpsTemplates(t *testing.T) {
-	root := os.Getenv("YUEBOARD_REGION_OPS_TEMPLATES")
-	if root == "" {
-		t.Skip("paired Ops regional templates not supplied")
-	}
-	for _, locale := range []string{"zh", "en"} {
-		for _, format := range []string{"clashmeta", "clash", "stash", "singbox", "surge", "surfboard"} {
-			t.Run(locale+"/"+format, func(t *testing.T) {
-				ext := ".yaml"
-				if format == "singbox" {
-					ext = ".json"
-				} else if format == "surge" || format == "surfboard" {
-					ext = ".conf"
-				}
-				template, err := os.ReadFile(filepath.Join(root, locale, format+ext))
-				if err != nil {
-					t.Fatal(err)
-				}
-				m := entryTestModule(t, format, string(template))
-				m.settings = settings.NewStatic(map[string]string{regionEntrySetting: "1"})
-				a, b := hy2Row(), checkableRealityServer()
-				a.Name, b.Name = "悦·🇸🇬新加坡1", "悦·🇸🇬新加坡2"
-				a.Password, b.Password = regionTestUUID, regionTestUUID
-				flag := format
-				if format == "singbox" {
-					flag = "sing-box"
-				}
-				if format == "clash" {
-					flag = "clash-compatible"
-				}
-				r := httptest.NewRequest("GET", "https://sub.example/s/test?flag="+flag, nil)
-				r.Header.Set("User-Agent", "mihomo/1.19.31")
-				w := httptest.NewRecorder()
-				m.deliver(context.Background(), w, r, entrySubUser(), []*serverRow{a, b}, 0, regionTestUUID, "test")
-				if w.Code != 200 {
-					t.Fatalf("delivery status %d", w.Code)
-				}
-				var groups []any
-				nk, mk, manual, main := "name", "proxies", "select", ""
-				if format == "singbox" {
-					cfg := map[string]any{}
-					if err := json.Unmarshal(w.Body.Bytes(), &cfg); err != nil {
-						t.Fatal(err)
-					}
-					groups = cfg["outbounds"].([]any)
-					nk, mk, manual = "tag", "outbounds", "selector"
-					main = cfg["route"].(map[string]any)["final"].(string)
-				} else if ext == ".yaml" {
-					cfg := map[string]any{}
-					if err := yaml.Unmarshal(w.Body.Bytes(), &cfg); err != nil {
-						t.Fatal(err)
-					}
-					groups = cfg["proxy-groups"].([]any)
-					main = groups[0].(map[string]any)["name"].(string)
-				} else {
-					inGroups := false
-					for _, line := range strings.Split(w.Body.String(), "\n") {
-						line = strings.TrimSpace(line)
-						if strings.HasPrefix(line, "[") {
-							inGroups = line == "[Proxy Group]"
-							continue
-						}
-						if !inGroups || strings.HasPrefix(line, "#") {
-							continue
-						}
-						name, body, ok := strings.Cut(line, "=")
-						if !ok {
-							continue
-						}
-						fields := splitINIGroupParameters(body)
-						members := []any{}
-						for _, f := range fields[1:] {
-							if !strings.Contains(f, "=") {
-								members = append(members, strings.TrimSpace(f))
-							}
-						}
-						groups = append(groups, map[string]any{nk: strings.TrimSpace(name), "type": strings.TrimSpace(fields[0]), mk: members})
-					}
-					main = "Proxy"
-				}
-				canonical := ""
-				for _, raw := range groups {
-					g := raw.(map[string]any)
-					if g[mk] == nil {
-						continue
-					}
-					name := g[nk].(string)
-					region := regionGroupRegion(name)
-					if region != "" {
-						if region != "🇸🇬" {
-							t.Fatalf("unavailable region group %s", name)
-						}
-						if canonical != "" {
-							t.Fatalf("duplicate region groups %s and %s", canonical, name)
-						}
-						canonical = name
-						if g["type"] != manual {
-							t.Fatal("regional group is automatic")
-						}
-						want := 2
-						if ext == ".conf" {
-							want = 1
-						}
-						if len(regionStrings(g[mk])) != want {
-							t.Fatal("supported manual protocol choice lost")
-						}
-					}
-				}
-				if canonical == "" {
-					t.Fatal("missing regional entry")
-				}
-				for _, raw := range groups {
-					g := raw.(map[string]any)
-					if g[nk] != main {
-						continue
-					}
-					count := 0
-					for _, member := range regionStrings(g[mk]) {
-						if member == canonical {
-							count++
-						}
-						if member == a.Name || member == b.Name {
-							t.Fatal("main exposes raw protocol entries")
-						}
-					}
-					if count != 1 {
-						t.Fatal("main does not expose exactly one regional entry")
-					}
-				}
-			})
-		}
-	}
-}
-
-func TestRegionExternalGroupAndINICapability(t *testing.T) {
-	a := hy2Row()
-	a.Name, a.external = "🇭🇰 External node", true
-	ctx := context.WithValue(context.Background(), regionEntryKey{}, regionEntryOptions{enabled: true})
-	groups := []any{map[string]any{"name": "🇭🇰 External", "type": "url-test", "proxies": []any{a.Name}}}
-	got := applyRegionGroups(ctx, groups, []*serverRow{a}, []string{a.Name}, false)
-	if len(got) != 1 || got[0].(map[string]any)["type"] != "url-test" {
-		t.Fatal("third-party policy changed")
-	}
-	a.external, a.Type = false, "vless"
-	profile := "[Proxy Group]\n🇭🇰 = select, " + a.Name + "\n[Rule]\nFINAL,🇭🇰\n"
-	out := applyRegionINI(ctx, profile, []*serverRow{a})
-	if strings.Contains(out, a.Name) || !strings.Contains(out, "FINAL,REJECT") {
-		t.Fatal("INI admitted an unsupported proxy")
-	}
-}
-
-func TestRegionAliasRuleReferences(t *testing.T) {
-	aliases := map[string]string{"🇸🇬 Alias": "🇸🇬 Singapore", "🇸🇬 Restricted": "HY2"}
-	rules := map[string]any{"rules": []any{"DOMAIN,alias.example,🇸🇬 Alias", "IP-CIDR,example,🇸🇬 Restricted,no-resolve"}, "sub-rules": map[string]any{"nested": []any{"MATCH,🇸🇬 Alias"}}}
-	rewriteRegionClashRules(rules, aliases)
-	if rules["rules"].([]any)[0] != "DOMAIN,alias.example,🇸🇬 Singapore" || rules["rules"].([]any)[1] != "IP-CIDR,example,HY2,no-resolve" || rules["sub-rules"].(map[string]any)["nested"].([]any)[0] != "MATCH,🇸🇬 Singapore" {
-		t.Fatal("Clash policy references lost")
-	}
-	cfg := map[string]any{"route": map[string]any{"final": "🇸🇬 Alias", "rules": []any{map[string]any{"outbound": "🇸🇬 Restricted", "domain": []any{"🇸🇬 Alias"}}}}, "dns": map[string]any{"detour": "🇸🇬 Alias"}}
-	rewriteRegionSingBoxRefs(cfg, aliases)
-	route := cfg["route"].(map[string]any)
-	rule := route["rules"].([]any)[0].(map[string]any)
-	if route["final"] != "🇸🇬 Singapore" || rule["outbound"] != "HY2" || rule["domain"].([]any)[0] != "🇸🇬 Alias" || cfg["dns"].(map[string]any)["detour"] != "🇸🇬 Singapore" {
-		t.Fatal("sing-box policy references or predicates changed")
-	}
-}
-
-func TestRegionINIAliasServiceParameters(t *testing.T) {
-	a := hy2Row()
-	a.Name = "悦·🇸🇬 HY2"
-	ctx := context.WithValue(context.Background(), regionEntryKey{}, regionEntryOptions{enabled: true})
-	profile := "[Proxy Group]\n🇸🇬 Primary = select, " + a.Name + "\n🇸🇬 Alias = select, " + a.Name + "\nService = fallback, 🇸🇬 Alias, DIRECT, url=https://example.test/check, interval=60, timeout=5\n[Rule]\nFINAL,Service\n"
-	out := applyRegionINI(ctx, profile, []*serverRow{a})
-	if strings.Contains(out, "🇸🇬 Alias") || !strings.Contains(out, "Service = fallback, 🇸🇬 Primary, DIRECT, url=https://example.test/check, interval=60, timeout=5") {
-		t.Fatal("service alias lost recovery parameters")
-	}
-}
-
-func TestRegionTemplateProxyAvailability(t *testing.T) {
-	ctx := context.WithValue(context.Background(), regionEntryKey{}, regionEntryOptions{enabled: true})
-	groups := []any{map[string]any{"name": "🇭🇰 Custom", "type": "select", "proxies": []any{"static"}}}
-	if got := applyRegionGroups(ctx, groups, nil, nil, false, regionGroupExtras{templateNames: []string{"static"}}); len(got) != 1 {
-		t.Fatal("Clash template proxy group omitted")
-	}
-	groups = []any{map[string]any{"tag": "🇭🇰 Custom", "type": "selector", "outbounds": []any{"static"}}, map[string]any{"tag": "static", "type": "socks"}}
-	if got := applyRegionGroups(ctx, groups, nil, nil, true); len(got) != 2 {
-		t.Fatal("sing-box template proxy group omitted")
-	}
-	groups = []any{map[string]any{"tag": "🇭🇰 Missing", "type": "selector", "outbounds": []any{"unavailable"}}, map[string]any{"tag": "unavailable", "type": "socks", "server": "127.0.0.1", "server_port": 9}}
-	if got := applyRegionGroups(ctx, groups, nil, nil, true); len(got) != 1 || got[0].(map[string]any)["tag"] != "unavailable" {
-		t.Fatal("notice makes missing region available")
-	}
-}
diff --git a/internal/modules/subscribe/region_fallback_test.go b/internal/modules/subscribe/region_fallback_test.go
deleted file mode 100644
index f91dcfd9..00000000
--- a/internal/modules/subscribe/region_fallback_test.go
+++ /dev/null
@@ -1,67 +0,0 @@
-package subscribe
-
-import (
-	"bytes"
-	"context"
-	"encoding/json"
-	"net/http/httptest"
-	"os"
-	"path/filepath"
-	"strings"
-	"testing"
-	"time"
-
-	"github.com/onesyue/yueboard/internal/platform/settings"
-)
-
-func TestRegionFallbackDefaultOffSnapshots(t *testing.T) {
-	for _, flag := range []string{"general", "clashmeta", "clash", "stash", "sing-box", "loon", "surge", "surfboard", "quantumultx"} {
-		t.Run(flag, func(t *testing.T) {
-			var baseline []byte
-			for _, configured := range []bool{false, true} {
-				cfg, rows := canaryFixture(false)
-
-				raw, _ := json.Marshal(cfg)
-				m := entryTestModule(t, "", "")
-				m.settings = settings.NewStatic(map[string]string{subscribeEndpointSaltKey: string(raw), "subscribe_entry_pairs_required": "1"})
-				if configured {
-					m.settings = settings.NewStatic(map[string]string{subscribeEndpointSaltKey: string(raw), "subscribe_entry_pairs_required": "1", "subscribe_region_fallback_enabled": "0"})
-				}
-				for _, key := range []string{"clashmeta", "clash", "stash"} {
-					m.tmpls[key] = tmplEntry{content: "proxies: []\nproxy-groups:\n  - name: 悦 · 节点选择\n    type: select\n    proxies: [DIRECT]\nrules:\n  - MATCH,悦 · 节点选择\n", at: time.Now()}
-				}
-				m.tmpls["singbox"] = tmplEntry{content: `{"outbounds":[{"type":"selector","tag":"悦 · 节点选择","outbounds":["auto"]},{"type":"direct","tag":"direct"}]}`, at: time.Now()}
-				m.tmpls["surge"] = tmplEntry{content: defaultSurgeTemplate, at: time.Now()}
-				m.tmpls["surfboard"] = tmplEntry{content: defaultSurfboardTemplate, at: time.Now()}
-				req := httptest.NewRequest("GET", "https://sub.example/s/tok?flag="+flag, nil)
-				w := httptest.NewRecorder()
-				m.deliver(context.Background(), w, req, entrySubUser(), rows, 0, "uuid-test", canaryToken(cfg))
-				if w.Code != 200 {
-					t.Fatalf("status %d", w.Code)
-				}
-				body := w.Body.Bytes()
-				if configured && !bytes.Equal(body, baseline) {
-					t.Fatal("disabled configuration changes output")
-				}
-				baseline = append([]byte(nil), body...)
-			}
-			// Preserve the immutable pre-canary snapshot while allowing exactly
-			// the independently tested cached-refresh policy correction.
-			if flag == "surge" || flag == "surfboard" {
-				header, rest, ok := strings.Cut(string(baseline), "\n")
-				if !ok || !strings.HasPrefix(header, "#!MANAGED-CONFIG ") || !strings.HasSuffix(header, " interval=43200 strict=false") {
-					t.Fatal("unexpected current managed header")
-				}
-				baseline = []byte(strings.TrimSuffix(header, "strict=false") + "strict=true\n" + rest)
-			}
-			path := filepath.Join("testdata", "cdn_canary_off_"+flag+".golden")
-			want, err := os.ReadFile(path)
-			if err != nil {
-				t.Fatal(err)
-			}
-			if !bytes.Equal(want, baseline) {
-				t.Fatal("default-off output differs from pre-canary G23 master snapshot")
-			}
-		})
-	}
-}
diff --git a/internal/modules/subscribe/single_entry_protection_test.go b/internal/modules/subscribe/single_entry_protection_test.go
new file mode 100644
index 00000000..56624534
--- /dev/null
+++ b/internal/modules/subscribe/single_entry_protection_test.go
@@ -0,0 +1,117 @@
+package subscribe
+
+import (
+	"context"
+	"encoding/json"
+	"testing"
+
+	"github.com/onesyue/yueboard/internal/platform/entrysalt"
+	"github.com/onesyue/yueboard/internal/platform/settings"
+)
+
+func TestSingleEntryProtection(t *testing.T) {
+	for _, mode := range []string{"valid", "no alternate", "missing scope", "missing SNI", "missing salt", "missing token", "unregistered host"} {
+		t.Run(mode, func(t *testing.T) {
+			cfg, rows := allPairsFixture()
+			subject := entrysalt.Subject{Token: "single-entry-test"}
+			switch mode {
+			case "no alternate":
+				cfg.AlternateBuckets = nil
+				cfg.CDNAlternateBuckets = nil
+			case "missing scope":
+				delete(cfg.EntryPairScopes, rows[0].Host)
+			case "missing SNI":
+				rows[0].Settings = map[string]any{"version": 2, "tls": map[string]any{}}
+			case "missing salt":
+				cfg = nil
+			case "missing token":
+				subject.Token = ""
+			case "unregistered host":
+				rows[0].Host = "unregistered.example.net"
+				cfg.EntryPairScopes[rows[0].Host] = "shared"
+			}
+			got, _, err := projectEntryEndpoints(cfg, subject, rows, true)
+			valid := mode == "valid" || mode == "no alternate"
+			if !valid {
+				if err == nil {
+					t.Fatal("unsafe entry accepted")
+				}
+				return
+			}
+			if err != nil {
+				t.Fatal(err)
+			}
+			if len(got) != len(rows) {
+				t.Fatal("single entry cardinality changed")
+			}
+			for i, row := range got {
+				if row.Name != rows[i].Name || row.Host == rows[i].Host {
+					t.Fatal("entry renamed or canonical host escaped")
+				}
+			}
+		})
+	}
+}
+
+func TestSingleEntryStrictRequirement(t *testing.T) {
+	cfg, _ := allPairsFixture()
+	raw, err := json.Marshal(cfg)
+	if err != nil {
+		t.Fatal(err)
+	}
+	for _, value := range []string{"", "true", "2", "\"1\"", "0", "1"} {
+		t.Run(value, func(t *testing.T) {
+			m := &Module{settings: settings.NewStatic(map[string]string{subscribeEndpointSaltKey: string(raw), "subscribe_entry_pairs_required": value})}
+			parsed, required, err := m.entryProjectionConfig(context.Background())
+			if value != "0" && value != "1" {
+				if err == nil {
+					t.Fatal("malformed requirement accepted")
+				}
+				return
+			}
+			if err != nil || parsed == nil || required != (value == "1") {
+				t.Fatal("canonical requirement rejected or changed")
+			}
+		})
+	}
+}
+
+func TestSingleEntryIncompleteScopeCannotPoisonRecovery(t *testing.T) {
+	cfg, rows := allPairsFixture()
+	cfg.Hosts = nil
+	raw, err := json.Marshal(cfg)
+	if err != nil {
+		t.Fatal(err)
+	}
+	good := string(raw)
+	snapshot := map[string]string{subscribeEndpointSaltKey: good, subscribeEndpointSaltLastGoodKey: good, "subscribe_entry_pairs_required": "1"}
+	m := &Module{}
+	if m.endpointSaltFromSnapshot(context.Background(), snapshot) == nil {
+		t.Fatal("valid scope rejected")
+	}
+	delete(cfg.EntryPairScopes, rows[0].Host)
+	raw, err = json.Marshal(cfg)
+	if err != nil {
+		t.Fatal(err)
+	}
+	snapshot[subscribeEndpointSaltKey] = string(raw)
+	incomplete := m.endpointSaltFromSnapshot(context.Background(), snapshot)
+	if _, _, err := projectEntryEndpoints(incomplete, entrysalt.Subject{Token: "test"}, rows, true); err == nil {
+		t.Fatal("visible missing scope accepted")
+	}
+	// The CDN remains visible when the normal pool is hidden, but the incomplete
+	// document must not become a recovery generation.
+	if _, _, err := projectEntryEndpoints(incomplete, entrysalt.Subject{Token: "test"}, rows[2:], true); err != nil {
+		t.Fatal(err)
+	}
+	if hit := m.endpointSaltParsed.Load(); hit == nil || hit.raw != good {
+		t.Fatal("incomplete hidden scope poisoned warm cache")
+	}
+	snapshot[subscribeEndpointSaltKey] = "broken"
+	for _, consumer := range []*Module{m, {}} {
+		recovered := consumer.endpointSaltFromSnapshot(context.Background(), snapshot)
+		if _, _, err := projectEntryEndpoints(recovered, entrysalt.Subject{Token: "test"}, rows, true); err != nil {
+			t.Fatal("verified recovery lost", err)
+		}
+	}
+}
diff --git a/test/integration/entry_intelligence_integration_test.go b/test/integration/entry_intelligence_integration_test.go
index e362e25a..ce5ba289 100644
--- a/test/integration/entry_intelligence_integration_test.go
+++ b/test/integration/entry_intelligence_integration_test.go
@@ -161,8 +161,8 @@ func TestEntryIntelligenceMatchesDualEntryAndDirectEntitlements(t *testing.T) {
 				}
 				delivered = append(delivered, independentFingerprintV2(proxy))
 			}
-			if counts[relay] != 2 || len(hosts) != 2 || len(counts) != len(tc.direct)+1 {
-				t.Fatalf("incorrect A/B or entitlement projection: counts=%v hosts=%v", counts, hosts)
+			if counts[relay] != 1 || len(hosts) != 1 || len(counts) != len(tc.direct)+1 {
+				t.Fatalf("incorrect single-entry or entitlement projection: counts=%v hosts=%v", counts, hosts)
 			}
 			for host := range hosts {
 				if !strings.HasSuffix(host, ".salt.example.net") {
@@ -176,11 +176,19 @@ func TestEntryIntelligenceMatchesDualEntryAndDirectEntitlements(t *testing.T) {
 			}
 			sort.Strings(delivered)
 			sort.Strings(served)
-			if len(delivered) != len(tc.direct)+2 || strings.Join(delivered, ",") != strings.Join(served, ",") {
+			if len(delivered) != len(tc.direct)+1 || strings.Join(delivered, ",") != strings.Join(served, ",") {
 				t.Fatalf("real HTTP fingerprint mismatch: delivered=%v intelligence=%v", delivered, served)
 			}
 		})
 	}
+	t.Run("single entry without alternate metadata", func(t *testing.T) {
+		yocExec(t, `UPDATE users SET group_id=1 WHERE id=2`)
+		yocExec(t, `UPDATE settings SET value=(value::jsonb-'alternate_buckets')::text WHERE name='subscribe_endpoint_salt'`)
+		subStatus, proxies, intelStatus, served := fetch(t)
+		if subStatus != 200 || intelStatus != 200 || len(proxies) != 2 || len(served) != 2 {
+			t.Fatalf("single-entry publication unavailable: sub=%d intel=%d proxies=%d fingerprints=%d", subStatus, intelStatus, len(proxies), len(served))
+		}
+	})
 	yocExec(t, `UPDATE users SET group_id=1 WHERE id=2`)
 	policyRaw, err := json.Marshal(policy)
 	if err != nil {
@@ -204,7 +212,6 @@ func TestEntryIntelligenceMatchesDualEntryAndDirectEntitlements(t *testing.T) {
 	}{
 		{"malformed policy", "{", salt},
 		{"missing salt", string(policyRaw), ""},
-		{"missing alternate", string(policyRaw), `{"enabled":true,"zone":"salt.example.net","secret":"test","host_buckets":{"entry.example.net":["aaaa1111","bbbb2222"]}}`},
 	} {
 		t.Run(tc.name, func(t *testing.T) {
 			yocExec(t, `UPDATE settings SET value=$1 WHERE name='subscribe_entry_policy'`, tc.policy)
diff --git a/test/integration/entry_pairs_publication_integration_test.go b/test/integration/entry_pairs_publication_integration_test.go
index 07598ee4..23728069 100644
--- a/test/integration/entry_pairs_publication_integration_test.go
+++ b/test/integration/entry_pairs_publication_integration_test.go
@@ -23,6 +23,7 @@ import (
 	"github.com/onesyue/yueboard/internal/modules/subscribe"
 	pb "github.com/onesyue/yueboard/internal/noderpc/gen/yuenode/v1"
 	"github.com/onesyue/yueboard/internal/platform/settings"
+	"go.yaml.in/yaml/v3"
 	"google.golang.org/protobuf/proto"
 )
 
@@ -177,12 +178,7 @@ func TestEntryPairsNativeCASLostResponseAndRights(t *testing.T) {
 	}
 	got := pairFreshSubscription(t)
 	got.mustOK(t, "fresh native delivery")
-	if strings.Contains(string(got.body), "pair-private") || !strings.Contains(string(got.body), "pair-direct · A") || !strings.Contains(string(got.body), "pair-direct · B") || !strings.Contains(string(got.body), "pair-cdn · A") || !strings.Contains(string(got.body), "pair-cdn · B") {
-		t.Fatal("entry pairs lost order/products or crossed group permissions")
-	}
-	if strings.Index(string(got.body), "pair-direct · A") > strings.Index(string(got.body), "pair-direct · B") {
-		t.Fatal("normal pair order reversed")
-	}
+	assertSinglePublishedEntries(t, got.body, "pair-direct", "pair-cdn")
 	// Config corruption after activation must use the atomic durable projection;
 	// if both copies disappear a fresh process refuses instead of publishing A.
 	wrExec(t, `UPDATE settings SET value='broken' WHERE name='subscribe_endpoint_salt'`)
@@ -457,11 +453,7 @@ func TestEntryPairsTemporarilyHiddenPoolKeepsOwnedAlternates(t *testing.T) {
 			wrExec(t, `UPDATE servers SET show=true WHERE id=ANY($1::bigint[])`, hidden)
 			got := pairFreshSubscription(t)
 			got.mustOK(t, "show recovery retains all required pairs")
-			for _, name := range []string{"pair-direct · A", "pair-direct · B", "pair-cdn · A", "pair-cdn · B"} {
-				if !strings.Contains(string(got.body), name) {
-					t.Fatal("temporarily hidden pool lost entry pair after restore")
-				}
-			}
+			assertSinglePublishedEntries(t, got.body, "pair-direct", "pair-cdn")
 		})
 	}
 }
@@ -637,9 +629,7 @@ func TestEntryPairsMissingExplicitServerNameCannotActivate(t *testing.T) {
 			yotPost(t, pairPublishPath, pairBody(t, ids), internalControlToken).mustOK(t, "explicit handshake target activates safely")
 			got := pairFreshSubscription(t)
 			got.mustOK(t, "fresh subscription with explicit handshake target")
-			if !strings.Contains(string(got.body), "pair-direct · B") {
-				t.Fatal("positive control omitted alternate")
-			}
+			assertSinglePublishedEntries(t, got.body, "pair-direct", "pair-cdn")
 		})
 	}
 }
@@ -763,3 +753,36 @@ func TestEntryPairsIncompleteScopeNeverPoisonsWarmRecovery(t *testing.T) {
 	wrExec(t, `UPDATE settings SET value=$1 WHERE name='subscribe_endpoint_salt'`, original)
 	pairFreshSubscription(t).mustOK(t, "repair only current value recovers fresh consumer")
 }
+
+// Assert exact names, order, cardinality and group isolation on decoded output.
+// Account notice rows are not panel servers and retain their separate contract.
+func assertSinglePublishedEntries(t *testing.T, body []byte, want ...string) {
+	t.Helper()
+	var profile struct {
+		Proxies []struct {
+			Name     string `yaml:"name"`
+			ServerID int64  `yaml:"server_id"`
+			Server   string `yaml:"server"`
+			Port     int    `yaml:"port"`
+		} `yaml:"proxies"`
+	}
+	if err := yaml.Unmarshal(body, &profile); err != nil {
+		t.Fatal(err)
+	}
+	var got []string
+	for _, proxy := range profile.Proxies {
+		if strings.Contains(proxy.Name, "pair-private") {
+			t.Fatal("private product crossed group permissions")
+		}
+		if proxy.ServerID == 0 {
+			if proxy.Server != "127.0.0.1" || proxy.Port != 9 || !strings.Contains(proxy.Name, "请勿分享订阅链接") {
+				t.Fatal("unexpected synthetic proxy in single-entry inventory")
+			}
+			continue
+		}
+		got = append(got, proxy.Name)
+	}
+	if !reflect.DeepEqual(got, want) {
+		t.Fatalf("single-entry inventory/order mismatch: got=%v want=%v", got, want)
+	}
+}
diff --git a/test/integration/entry_x4b_admission_integration_test.go b/test/integration/entry_x4b_admission_integration_test.go
index c73c72a8..84d627ab 100644
--- a/test/integration/entry_x4b_admission_integration_test.go
+++ b/test/integration/entry_x4b_admission_integration_test.go
@@ -145,9 +145,7 @@ func TestX4BStagedPairAdoptShowAndOrdinaryAdmission(t *testing.T) {
 		t.Fatal("admission rewrote the topology-bound policy")
 	}
 	body := string(pairFreshSubscription(t).mustOK(t, "ordinary after admission").body)
-	if !strings.Contains(body, "pair-x4b · A") || !strings.Contains(body, "pair-x4b · B") || strings.Contains(body, "pair-private") {
-		t.Fatal("admitted X4B product missing its A/B pair, or group isolation crossed")
-	}
+	assertSinglePublishedEntries(t, []byte(body), "pair-direct", "pair-cdn", "pair-x4b")
 
 	// With only the ordinary group, the product is publishable scope solely via
 	// the exception: the pair publisher must prove the same visible set.

codex
The diff removes A/B expansion and region merging, and replaces several pair-based assertions with single-entry checks. I’m checking whether those replacements retain the entry-protection coverage.
exec
/bin/zsh -lc 'git diff 08bf94184af24ebcc9f4af036cd7027fbf397cdb 6d5bcf0dfa16294bc4d7a9a06525a41a915ea641 -- internal/modules/subscribe/endpoint_ip_literal_delivery_test.go internal/modules/subscribe/endpoint_salt_pin_test.go internal/modules/subscribe/endpoint_salt_wiring_test.go internal/modules/subscribe/entry_path_test.go internal/modules/subscribe/info_rows_unreachable_test.go internal/modules/subscribe/pair_gate_parity_test.go; git log --format=fuller 08bf94184af24ebcc9f4af036cd7027fbf397cdb..6d5bcf0dfa16294bc4d7a9a06525a41a915ea641' in /Users/j/codex-runs/mh1105/yb-138
 succeeded in 0ms:
diff --git a/internal/modules/subscribe/endpoint_ip_literal_delivery_test.go b/internal/modules/subscribe/endpoint_ip_literal_delivery_test.go
index 61be6ef3..bc47970c 100644
--- a/internal/modules/subscribe/endpoint_ip_literal_delivery_test.go
+++ b/internal/modules/subscribe/endpoint_ip_literal_delivery_test.go
@@ -120,55 +120,41 @@ func TestDeliverFleetIPLiteralPrivacyAcrossNineRenderers(t *testing.T) {
 	}
 }
 
-func TestDeliverFleetIPLiteralRequiredPairsFailClosed(t *testing.T) {
+func TestSingleServerPerFormat(t *testing.T) {
 	for _, consumer := range privacyConsumers {
 		t.Run(consumer.renderer, func(t *testing.T) {
-			for _, bad := range []bool{false, true} {
-				cfg, rows := allPairsFixture()
-				// CDN behavior already has actual-deliver coverage in
-				// TestDeliverCDNRewriteSurvivesSafetyFilter; use native pairs here.
-				rows = rows[:2]
-				if bad {
-					row := saltableHY2("203.0.113.7")
-					row.Name = "privacy-unscoped-native"
-					rows = append(rows, row)
+			cfg, rows := allPairsFixture()
+			rows = rows[:2]
+			for _, row := range rows {
+				path := admittedHY2Settings()["entry_path"].(map[string]any)
+				path["backup_required"] = true
+				path["node_id"], path["entry_host"], path["ports"] = row.ID, row.Host, strconv.Itoa(row.Port)
+				if row.Type == "hysteria" {
+					path["tls_server_name"] = gs(row.Settings, "tls.server_name")
+				} else {
+					path["tls_server_name"] = gs(row.Settings, "reality_settings.server_name")
+					row.Settings["network_settings"] = map[string]any{"acceptProxyProtocol": true}
 				}
-				w := privacyDeliver(t, cfg, true, consumer.renderer, consumer.ua, false, rows)
-				if bad {
-					if w.Code != http.StatusInternalServerError || w.Body.Len() != 0 {
-						t.Fatalf("bad native row: status=%d bytes=%d", w.Code, w.Body.Len())
-					}
-					for _, key := range []string{headerHappNewURL, headerHappFallbackURL, headerYueFallbackURLs, "announce", "support-url", "profile-web-page-url", "subscription-userinfo"} {
-						if w.Header().Get(key) != "" {
-							t.Errorf("failed delivery leaked success header %s", key)
-						}
-					}
+				row.Settings["entry_path"] = path
+			}
+			w := privacyDeliver(t, cfg, true, consumer.renderer, consumer.ua, false, rows)
+			if w.Code != http.StatusOK {
+				t.Fatalf("status %d", w.Code)
+			}
+			got := privacyEndpoints(t, consumer.renderer, w.Body.Bytes())
+			count := 0
+			for _, row := range rows {
+				if !privacyEmits(consumer.renderer, row) {
 					continue
 				}
-				if w.Code != http.StatusOK {
-					t.Fatalf("valid pair control status %d", w.Code)
-				}
-				got := privacyEndpoints(t, consumer.renderer, w.Body.Bytes())
-				wantCount := 0
-				for _, row := range rows {
-					if !privacyEmits(consumer.renderer, row) {
-						continue
-					}
-					for _, alternate := range []bool{false, true} {
-						name, host := row.Name+" · A", entrysalt.SaltedHost(cfg, entrysalt.Subject{Token: "privacy-token"}, row.Host)
-						if alternate {
-							name, host = row.Name+" · B", entrysalt.AlternateSaltedHost(cfg, entrysalt.Subject{Token: "privacy-token"}, row.Host)
-						}
-						if endpoint, ok := got[name]; !ok || endpoint.host != host {
-							t.Errorf("valid pair %q missing or wrong host", name)
-						}
-						wantCount++
-					}
-				}
-				if wantCount == 0 || len(got) != wantCount {
-					t.Fatalf("valid control endpoints=%d, want nonzero %d", len(got), wantCount)
+				count++
+				if _, ok := got[row.Name]; !ok {
+					t.Fatalf("missing original name %q", row.Name)
 				}
 			}
+			if len(got) != count {
+				t.Fatalf("nodes=%d want=%d", len(got), count)
+			}
 		})
 	}
 }
diff --git a/internal/modules/subscribe/endpoint_salt_pin_test.go b/internal/modules/subscribe/endpoint_salt_pin_test.go
index 0e90421b..9d0b4a2a 100644
--- a/internal/modules/subscribe/endpoint_salt_pin_test.go
+++ b/internal/modules/subscribe/endpoint_salt_pin_test.go
@@ -34,35 +34,28 @@ func TestSaltSubjectCarriesTheAccountIntoThePinList(t *testing.T) {
 		t.Fatalf("subject = %+v, want account %d in the stable tier", subject, account)
 	}
 	_, rows := allPairsFixture()
-	projected, _, err := projectEntryEndpoints(cfg, subject, rows, true)
+	projected, _, err := projectEntryEndpoints(cfg, subject, rows)
 	if err != nil {
 		t.Fatal(err)
 	}
 	pinKey := cfg.HostBuckets[host][pinBucket]
-	altKey := cfg.HostBuckets[host][cfg.AlternateBuckets[host][pinBucket]]
-	if !strings.Contains(projected[0].Host, pinKey) || !strings.Contains(projected[1].Host, altKey) {
-		t.Fatalf("pair hosts %q %q, want keys %s and %s", projected[0].Host, projected[1].Host, pinKey, altKey)
-	}
-	if projected[0].Host == projected[1].Host || len(projected) != 6 {
-		t.Fatalf("pair projection = %d rows, first hosts %q %q", len(projected), projected[0].Host, projected[1].Host)
-	}
-	if !strings.Contains(projected[2].Host, pinKey) || !strings.Contains(projected[3].Host, altKey) {
-		t.Fatalf("second direct pair %q %q, want keys %s and %s", projected[2].Host, projected[3].Host, pinKey, altKey)
+	if len(projected) != 3 || !strings.Contains(projected[0].Host, pinKey) || !strings.Contains(projected[1].Host, pinKey) {
+		t.Fatal("pin lost")
 	}
 	bareCDN, _ := allPairsFixture()
 	cdnBare, okA := entrysalt.CDNEntryHost(bareCDN, subject, cdnTestHost, false)
 	cdnHere, okB := entrysalt.CDNEntryHost(cfg, subject, cdnTestHost, false)
-	if !okA || !okB || cdnHere != cdnBare || projected[4].Host != cdnHere {
-		t.Fatalf("CDN name moved: projected %q with pin %q without pin %q", projected[4].Host, cdnHere, cdnBare)
+	if !okA || !okB || cdnHere != cdnBare || projected[2].Host != cdnHere {
+		t.Fatalf("CDN name moved: projected %q with pin %q without pin %q", projected[2].Host, cdnHere, cdnBare)
 	}
 
 	_, crowdRows := allPairsFixture()
-	crowd, _, err := projectEntryEndpoints(cfg, entrysalt.Subject{Token: token, UserID: account + 1}, crowdRows, true)
+	crowd, _, err := projectEntryEndpoints(cfg, entrysalt.Subject{Token: token, UserID: account + 1}, crowdRows)
 	if err != nil {
 		t.Fatal(err)
 	}
 	bareCfg, bareRows := allPairsFixture()
-	bare, _, err := projectEntryEndpoints(bareCfg, entrysalt.Subject{Token: token, UserID: account + 1}, bareRows, true)
+	bare, _, err := projectEntryEndpoints(bareCfg, entrysalt.Subject{Token: token, UserID: account + 1}, bareRows)
 	if err != nil {
 		t.Fatal(err)
 	}
diff --git a/internal/modules/subscribe/endpoint_salt_wiring_test.go b/internal/modules/subscribe/endpoint_salt_wiring_test.go
index 2a386940..3a8ac5f2 100644
--- a/internal/modules/subscribe/endpoint_salt_wiring_test.go
+++ b/internal/modules/subscribe/endpoint_salt_wiring_test.go
@@ -22,7 +22,7 @@ func TestEndpointSaltIsCalledFromDeliverAtTheRightPosition(t *testing.T) {
 	// （少一个锚点 = 少判一条顺序）。见 packagesource_test.go。
 	body := subscribeFuncBody(t, "deliver")
 
-	call := strings.Index(body, "projectEntryEndpoints(saltCfg, saltSubject, servers, requireAllPairs)")
+	call := strings.Index(body, "projectEntryEndpoints(saltCfg, saltSubject, servers, requireEntry)")
 	if call < 0 {
 		t.Fatal("deliver() 里找不到 projectEntryEndpoints 调用 —— 共享加盐投影不可绕过")
 	}
diff --git a/internal/modules/subscribe/entry_path_test.go b/internal/modules/subscribe/entry_path_test.go
index 7f9aafec..c9ddd3d7 100644
--- a/internal/modules/subscribe/entry_path_test.go
+++ b/internal/modules/subscribe/entry_path_test.go
@@ -4,8 +4,6 @@ import (
 	"context"
 	"encoding/base64"
 	"encoding/json"
-	"fmt"
-	"github.com/onesyue/yueboard/internal/platform/entrysalt"
 	"github.com/onesyue/yueboard/internal/platform/settings"
 	"net/http/httptest"
 	"strings"
@@ -91,51 +89,7 @@ func TestDBPortOverrideCannotEscapeEntryLease(t *testing.T) {
 	}
 }
 
-func TestDualActiveExpansionKeepsABOrderAndSpreadsPrimaryBuckets(t *testing.T) {
-	cfg := &endpointSaltConfig{Enabled: true, Zone: "salt.example.net", Secret: "test",
-		HostBuckets:      map[string][]string{"entry.example.net": {"aaaa1111", "bbbb2222"}},
-		AlternateBuckets: map[string][]int{"entry.example.net": {1, 0}}}
-	source := &serverRow{ID: 43, Name: "香港", Type: "hysteria", Host: "entry.example.net", Port: 41000, Ports: "41000-41511", Settings: admittedHY2Settings()}
-	source.Settings["entry_path"].(map[string]any)["backup_required"] = true
-	first := map[int]int{}
-	for i := 0; i < 100; i++ {
-		subject := entrysalt.Subject{Token: fmt.Sprint(i)}
-		expanded, err := expandEntryAlternates(cfg, subject, []*serverRow{source})
-		if err != nil || len(expanded) != 2 {
-			t.Fatalf("dual entry missing: %v", err)
-		}
-		if expanded[0].entryAlternate || !expanded[1].entryAlternate || !strings.HasSuffix(expanded[0].Name, " · A") || !strings.HasSuffix(expanded[1].Name, " · B") {
-			t.Fatal("pair is not adjacent A then B")
-		}
-		bucket, ok := entrysalt.BucketIndex(cfg, subject, source.Host)
-		if !ok {
-			t.Fatal("primary bucket missing")
-		}
-		first[bucket]++
-		if expanded[0].Name == expanded[1].Name || source.Name != "香港" || expanded[0] == source {
-			t.Fatal("mutated cached origin or collapsed names")
-		}
-		if expanded[0].ID != 43 || expanded[1].ID != 43 || expanded[0].Ports != expanded[1].Ports {
-			t.Fatal("alternate changed billing identity or port lease")
-		}
-		if applyEndpointSaltFor(cfg, subject, expanded) != 2 || expanded[0].Host == expanded[1].Host {
-			t.Fatal("alternate did not reach distinct consumer dial host")
-		}
-		again, _ := expandEntryAlternates(cfg, subject, []*serverRow{source})
-		if again[0].entryAlternate != expanded[0].entryAlternate {
-			t.Fatal("preference changes on refresh")
-		}
-	}
-	if first[0] < 20 || first[1] < 20 {
-		t.Fatalf("one entry is idle: %v", first)
-	}
-	delete(cfg.AlternateBuckets, "entry.example.net")
-	if _, err := expandEntryAlternates(cfg, entrysalt.Subject{Token: "one"}, []*serverRow{source}); err == nil {
-		t.Fatal("published route silently lost required second entry")
-	}
-}
-
-func TestDualActivePathsReachEverySupportedRenderer(t *testing.T) {
+func TestSingleEntryReachesEverySupportedRenderer(t *testing.T) {
 	cfg := &endpointSaltConfig{Enabled: true, Zone: "salt.example.net", Secret: "test",
 		HostBuckets:      map[string][]string{"entry.example.net": {"aaaa1111", "bbbb2222"}},
 		AlternateBuckets: map[string][]int{"entry.example.net": {1, 0}}}
@@ -182,7 +136,7 @@ func TestDualActivePathsReachEverySupportedRenderer(t *testing.T) {
 				}
 				body = string(decoded)
 			}
-			if w.Code != 200 || !strings.Contains(body, ".aaaa1111.salt.example.net") || !strings.Contains(body, ".bbbb2222.salt.example.net") || strings.Contains(body, "entry.example.net") {
+			if w.Code != 200 || strings.Contains(body, " · A") || strings.Contains(body, " · B") || strings.Contains(body, "entry.example.net") {
 				t.Fatalf("renderer lost a live path: status=%d body=%.400s", w.Code, body)
 			}
 			if h.Host != "entry.example.net" || v.Host != h.Host || strings.Contains(h.Name, " · ") {
@@ -191,3 +145,30 @@ func TestDualActivePathsReachEverySupportedRenderer(t *testing.T) {
 		})
 	}
 }
+
+func TestSubscriptionIgnoresLegacyAlternateMetadata(t *testing.T) {
+	raw, err := json.Marshal(saltTestCfg())
+	if err != nil {
+		t.Fatal(err)
+	}
+	var document map[string]any
+	if err := json.Unmarshal(raw, &document); err != nil {
+		t.Fatal(err)
+	}
+	document["alternate_buckets"] = map[string]any{"obsolete.example": []int{999}}
+	document["cdn_alternate_buckets"] = map[string]any{"obsolete.example": []int{-1}}
+	raw, _ = json.Marshal(document)
+	for _, lastGood := range []bool{false, true} {
+		values := map[string]string{subscribeEndpointSaltKey: string(raw)}
+		if lastGood {
+			values[subscribeEndpointSaltKey] = "broken"
+			values[subscribeEndpointSaltLastGoodKey] = string(raw)
+		}
+		m := entryTestModule(t, "", "")
+		m.settings = settings.NewStatic(values)
+		cfg := m.endpointSalt(context.Background())
+		if cfg == nil || len(cfg.AlternateBuckets) != 0 || len(cfg.CDNAlternateBuckets) != 0 {
+			t.Fatal("legacy alternates affected subscription parsing")
+		}
+	}
+}
diff --git a/internal/modules/subscribe/info_rows_unreachable_test.go b/internal/modules/subscribe/info_rows_unreachable_test.go
index 7ace91f5..75439a17 100644
--- a/internal/modules/subscribe/info_rows_unreachable_test.go
+++ b/internal/modules/subscribe/info_rows_unreachable_test.go
@@ -33,7 +33,7 @@ func TestInfoRowsCannotCarryTraffic(t *testing.T) {
 			if s.Host != "127.0.0.1" || s.Port != 9 || s.Ports != "" {
 				t.Fatalf("info row %q still routes to %s:%d (ports %q)", s.Name, s.Host, s.Port, s.Ports)
 			}
-			if s.entryAlternate || s.cdnOriginHost != "" {
+			if s.cdnOriginHost != "" {
 				t.Fatalf("info row %q keeps entry identity", s.Name)
 			}
 		}
diff --git a/internal/modules/subscribe/pair_gate_parity_test.go b/internal/modules/subscribe/pair_gate_parity_test.go
deleted file mode 100644
index e5f850d4..00000000
--- a/internal/modules/subscribe/pair_gate_parity_test.go
+++ /dev/null
@@ -1,48 +0,0 @@
-package subscribe
-
-import (
-	"fmt"
-	"math/rand/v2"
-	"testing"
-
-	"github.com/onesyue/yueboard/internal/platform/entrysalt"
-	"github.com/onesyue/yueboard/internal/platform/nativeproto"
-)
-
-// 2026-10-11 复核 B-11：自动显示的门（entrysalt.PairDeliverable，nodesync 的
-// requireVisibleEntryPairs 用它）放行的产品，交付在 required=1 下对**任意**订阅都必须能出
-// A/B 两条——否则门放行之后，能看到它的整份订阅 fail-closed。反向：门拒绝没有显式 SNI 的产品。
-func TestPairDeliverableImpliesDeliveryForEverySubject(t *testing.T) {
-	cfg, rows := allPairsFixture()
-	r := rand.New(rand.NewPCG(20261011, 11))
-	for _, row := range rows {
-		cdn := row.Type == "vless" && nativeproto.IsCDNWebSocketVless(row.Settings)
-		if err := entrysalt.PairDeliverable(cfg, row.Host, cdn, hasExplicitSNI(row)); err != nil {
-			t.Fatalf("%s: gate refused a deliverable fixture: %v", row.Name, err)
-		}
-		for i := range 500 {
-			subject := entrysalt.Subject{Token: fmt.Sprintf("tok-%d-%d", i, r.Uint64()), Quarantine: r.IntN(2) == 0}
-			if _, _, err := projectEntryEndpoints(cfg, subject, []*serverRow{row}, true); err != nil {
-				t.Fatalf("%s: gate passed but delivery failed for %+v: %v", row.Name, subject, err)
-			}
-		}
-	}
-	// 没有显式 SNI 的 HY2：门必须拒绝，因为交付一定失败。
-	noSNI := *rows[0]
-	noSNI.Settings = map[string]any{"version": 2, "tls": map[string]any{}}
-	if entrysalt.PairDeliverable(cfg, noSNI.Host, false, hasExplicitSNI(&noSNI)) == nil {
-		t.Fatal("gate admitted a product without an explicit server name")
-	}
-	if _, _, err := projectEntryEndpoints(cfg, entrysalt.Subject{Token: "x"}, []*serverRow{&noSNI}, true); err == nil {
-		t.Fatal("fixture: delivery should fail without an explicit server name")
-	}
-	// scope 在，但该命名空间的 alternate 投影缺失：门拒绝（交付同样失败）。
-	partial := *cfg
-	partial.AlternateBuckets = map[string][]int{}
-	if entrysalt.PairDeliverable(&partial, rows[0].Host, false, true) == nil {
-		t.Fatal("gate admitted a host without an alternate projection")
-	}
-	if entrysalt.PairDeliverable(cfg, "unscoped.example.net", false, true) != entrysalt.ErrPairScopeAbsent {
-		t.Fatal("missing scope must report ErrPairScopeAbsent")
-	}
-}
commit 6d5bcf0dfa16294bc4d7a9a06525a41a915ea641
Merge: d6b9bc57 08bf9418
Author:     onesyue <47652916+onesyue@users.noreply.github.com>
AuthorDate: Thu Nov 5 01:07:26 2026 +0800
Commit:     onesyue <47652916+onesyue@users.noreply.github.com>
CommitDate: Thu Nov 5 01:07:26 2026 +0800

    Merge remote-tracking branch 'origin/master' into codex/1104c-region-single

commit d6b9bc57d0a8068d502bd504fded87095c0e819c
Author:     onesyue <47652916+onesyue@users.noreply.github.com>
AuthorDate: Thu Nov 5 01:07:26 2026 +0800
Commit:     onesyue <47652916+onesyue@users.noreply.github.com>
CommitDate: Thu Nov 5 01:07:26 2026 +0800

    region single-node: rewrite A/B-only entry-pair/x4b assertions to one-node-per-server; keep and restore entry protection guards

commit 15cca4b42a788795eb0db2f1a076a1bbb8ab1212
Author:     onesyue <47652916+onesyue@users.noreply.github.com>
AuthorDate: Wed Nov 4 23:15:40 2026 +0800
Commit:     onesyue <47652916+onesyue@users.noreply.github.com>
CommitDate: Wed Nov 4 23:15:40 2026 +0800

    subscribe: one panel server = one node in every format; remove A/B alternates and region merge
    
    Owner decision 11-04: industry-standard (Xboard-style) delivery. Removes
    expandEntryAlternates, the '· A'/'· B' split, region merge (region_entry.go,
    subscribe_region_fallback_enabled) and the CDN canary extra node (batch-1 item 10).
    Legacy entry_path.backup_required (60 prod rows) and alternate_buckets in
    subscribe_endpoint_salt are still parsed and ignored; no migration.

exec
/bin/zsh -lc 'git diff 08bf94184af24ebcc9f4af036cd7027fbf397cdb 6d5bcf0dfa16294bc4d7a9a06525a41a915ea641 -- internal/modules/subscribe/region_entry.go internal/modules/subscribe/cdn_canary.go internal/modules/subscribe/REGION-VALIDATION.md' in /Users/j/codex-runs/mh1105/yb-138
 succeeded in 0ms:
diff --git a/internal/modules/subscribe/REGION-VALIDATION.md b/internal/modules/subscribe/REGION-VALIDATION.md
deleted file mode 100644
index 3cc3e8a7..00000000
--- a/internal/modules/subscribe/REGION-VALIDATION.md
+++ /dev/null
@@ -1,84 +0,0 @@
-# Regional subscription validation
-
-The existing `subscribe_region_fallback_enabled` server setting is an opt-in
-rollout switch: only `1` enables the feature. Its default is `0`. No migration
-or user database column is needed. Regional selection is always manual under the
-2026-11-04 17:27 owner decision. Retired request preferences are ignored and are
-not forwarded by managed refresh or migration URLs. Disabling the switch restores
-the old rendering path byte for byte, including when a retired parameter is present.
-
-Regional identity uses the two regional-indicator characters in the original
-canonical node name (before localization). Unknown labels and third-party
-products remain independent; no hostname or endpoint is guessed as a region.
-Within a region the stable order is HY2 A/B, Reality A/B, then CF A/B. Filters
-and protocol capabilities apply before grouping. General and Loon remain node
-resources, as does Quantumult X: these formats get one supported primary per
-region, with HY2 preferred where supported. Original Clash retains its existing
-upgrade-only behavior for unsupported native transports.
-
-Full profiles use native manual selectors. Existing regional template names
-are reused; equivalent aliases are removed and policy references are redirected
-to the canonical selector. Restricted regional helpers are inlined to their
-first eligible member, preserving their policy without another visible group.
-Existing restricted parents retain only the first eligible member when
-referencing a full regional group would widen their transport/direct/hold
-policy. The unrestricted region selector retains all manually selectable paths.
-Cross-region groups also become manual. Cached client selections can override first
-import defaults: verify with a fresh profile as well as a profile update.
-
-## Automated checks
-
-```sh
-GOCACHE=/tmp/yb-region-go-cache go test ./internal/modules/subscribe -count=1
-GOCACHE=/tmp/yb-region-go-cache go vet ./internal/modules/subscribe
-bash scripts/check-region-cores.sh
-```
-
-The script renders synthetic fixtures in a private temporary directory, checks
-both disabled and enabled/manual/ignored-preference profiles, and deletes all temporary
-files. It never fetches a subscription or starts a tunnel. Supply already
-installed, independently digest-verified official binaries on PATH or via
-`YUEBOARD_MIHOMO_BIN` and `YUEBOARD_SINGBOX_BIN`. It records the executable digest;
-record the release version and its verified release digest alongside the run.
-Exit 2 means missing cores, not a successful validation. Exit 1 means rendering
-or parser failure. Raw core diagnostics are withheld because these tools can
-print entire proxy objects. No paid dependencies or automated downloads exist.
-
-For Linux parity, run the same package tests and vet in the project's pinned Go
-Linux environment with UTC and the normal test concurrency. A Darwin run or
-cross-compilation does not establish Linux runtime parity.
-
-## Application and behavior checks
-
-Use synthetic local upstreams only, with valid canonical UUIDs and test
-certificates/Reality keys. Export fixtures by setting `YUEBOARD_REGION_FIXTURE_DIR`
-to an existing private directory and running `TestRegionExportCoreFixtures`.
-Do not use real account URLs, credentials or production servers.
-
-- Import manual and ignored-preference fixtures into supported Stash, Surge, Surfboard,
-  sing-box and mihomo clients. Inspect one region choice in the main selector,
-  HY2 A as the initial choice, and all supported A/B protocol choices inside it.
-- In manual mode, stop the selected synthetic upstream: the client must retain
-  the selection. Select B/Reality/CF manually and verify that traffic changes.
-- Import QX, Loon and general resources as node resources, not full profiles;
-  expect one supported primary per region and no strategy group syntax.
-- Repeat profile refresh and migration with the retired parameter. Verify both
-  present and missing parameters return manual groups and disabling the server switch
-  returns the established nine-format output.
-
-Parser success proves syntax only. App import, local traffic behavior and Linux
-parity must be reported separately; unavailable checks remain UNKNOWN.
-
-Native field references:
-[sing-box selector](https://sing-box.sagernet.org/configuration/outbound/selector/),
-[mihomo select](https://wiki.metacubex.one/en/config/proxy-groups/select/).
-
-INI dynamic proxy inclusion is expanded on the server from emitted HY2 rows.
-Unavailable regional groups and their parent choices are omitted; INI rules
-that targeted them reject traffic rather than selecting another region. Nested
-automatic protocol selectors become manual. The service-to-DIRECT recovery
-policy and independent third-party groups retain their existing semantics.
-
-Run `TestRegionPairedOpsTemplates` with `YUEBOARD_REGION_OPS_TEMPLATES` set to
-the sibling Ops `scripts/subscribe-templates` directory to verify both locales
-and all six full-profile templates. Missing paired inputs are a skip, not proof.
diff --git a/internal/modules/subscribe/cdn_canary.go b/internal/modules/subscribe/cdn_canary.go
deleted file mode 100644
index 2b041055..00000000
--- a/internal/modules/subscribe/cdn_canary.go
+++ /dev/null
@@ -1,77 +0,0 @@
-package subscribe
-
-import (
-	"crypto/hmac"
-	"crypto/sha256"
-	"encoding/binary"
-	"encoding/json"
-	"strings"
-	"time"
-
-	"github.com/onesyue/yueboard/internal/platform/entrysalt"
-	"github.com/onesyue/yueboard/internal/platform/nativeproto"
-)
-
-// This experiment only changes the CF connection address. SNI, WS Host, origin,
-// account credentials and original A/B rows remain those already projected.
-const cdnCanaryAddress = "104.21.45.158"
-
-type cdnCanaryConfig struct {
-	Enabled     bool      `json:"enabled"`
-	BasisPoints int       `json:"basis_points"`
-	Address     string    `json:"address"`
-	StartsAt    time.Time `json:"starts_at"`
-	ExpiresAt   time.Time `json:"expires_at"`
-}
-
-func cdnCanarySelected(secret, token string, basisPoints int) bool {
-	if secret == "" || token == "" || basisPoints < 1 || basisPoints > 100 {
-		return false
-	}
-	mac := hmac.New(sha256.New, []byte(secret))
-	mac.Write([]byte("cdn-entry-canary/sg171/v1\x00"))
-	mac.Write([]byte(token))
-	// Fixed anonymous cohort; <= 1% of the HMAC output space, not a promise
-	// that precisely 1% of a small finite subscriber population will qualify.
-	return binary.BigEndian.Uint64(mac.Sum(nil)[:8]) < (^uint64(0)/10000)*uint64(basisPoints)
-}
-
-func appendCDNCanary(cfg *endpointSaltConfig, subject entrysalt.Subject, rows []*serverRow) []*serverRow {
-	return appendCDNCanaryAt(cfg, subject, rows, time.Now())
-}
-
-func appendCDNCanaryAt(cfg *endpointSaltConfig, subject entrysalt.Subject, rows []*serverRow, now time.Time) []*serverRow {
-	if cfg == nil || !cfg.Enabled || subject.Quarantine {
-		return rows
-	}
-	for _, source := range rows {
-		if source == nil || source.ID != 171 || source.external || source.entryAlternate || source.Type != "vless" || source.Port != 443 || source.cdnOriginHost == "" || !nativeproto.IsCDNWebSocketVless(source.Settings) {
-			continue
-		}
-		raw, ok := source.Settings["cdn_entry_canary"]
-		if !ok {
-			return rows
-		}
-		data, err := json.Marshal(raw)
-		if err != nil {
-			return rows
-		}
-		var experiment cdnCanaryConfig
-		decoder := json.NewDecoder(strings.NewReader(string(data)))
-		decoder.DisallowUnknownFields()
-		if decoder.Decode(&experiment) != nil || !experiment.Enabled || experiment.Address != cdnCanaryAddress || experiment.StartsAt.IsZero() || now.Before(experiment.StartsAt) || !now.Before(experiment.ExpiresAt) || experiment.ExpiresAt.Sub(experiment.StartsAt) > 72*time.Hour || !cdnCanarySelected(cfg.Secret, subject.Token, experiment.BasisPoints) {
-			return rows
-		}
-		// A has already passed the existing salt gate. Never invent a TLS identity.
-		if gs(source.Settings, "tls_settings.server_name") != source.Host || gs(source.Settings, "network_settings.headers.Host") != source.Host {
-			return rows
-		}
-		extra := *source
-		extra.Host = experiment.Address
-		extra.Name = strings.TrimSuffix(source.Name, " · A") + " · C"
-		out := make([]*serverRow, len(rows), len(rows)+1)
-		copy(out, rows)
-		return append(out, &extra)
-	}
-	return rows
-}
diff --git a/internal/modules/subscribe/region_entry.go b/internal/modules/subscribe/region_entry.go
deleted file mode 100644
index 33832d97..00000000
--- a/internal/modules/subscribe/region_entry.go
+++ /dev/null
@@ -1,703 +0,0 @@
-package subscribe
-
-import (
-	"context"
-	"errors"
-	"fmt"
-	"slices"
-	"strings"
-	"unicode"
-
-	"github.com/google/uuid"
-	"github.com/onesyue/yueboard/internal/platform/nativeproto"
-)
-
-const regionEntrySetting = "subscribe_region_fallback_enabled"
-
-type regionEntryKey struct{}
-type regionEntryOptions struct {
-	enabled    bool
-	preserveAI bool
-}
-
-func regionOptions(ctx context.Context) regionEntryOptions {
-	o, _ := ctx.Value(regionEntryKey{}).(regionEntryOptions)
-	return o
-}
-
-// Region identity comes from the flag in the canonical source name, never a
-// connection hostname. Unknown and third-party products remain independent.
-func entryRegion(s *serverRow) string {
-	if s == nil || entryPairExempt(s) || s.placeholder {
-		return ""
-	}
-	name := firstNonEmpty(s.SourceName, s.Name)
-	runes := []rune(name)
-	for i := 0; i+1 < len(runes); i++ {
-		if runes[i] >= 0x1f1e6 && runes[i] <= 0x1f1ff && runes[i+1] >= 0x1f1e6 && runes[i+1] <= 0x1f1ff {
-			return string(runes[i : i+2])
-		}
-	}
-	return ""
-}
-
-// INI templates use unflagged regional labels in both supported locales.
-// Match exact template labels, never infer a node's region from free text.
-func regionGroupRegion(name string) string {
-	if flag := entryRegion(&serverRow{Name: name}); flag != "" {
-		return flag
-	}
-	for _, region := range []struct{ flag, zh, en string }{
-		{"🇭🇰", "香港聚合", "Hong Kong"}, {"🇹🇼", "台湾聚合", "Taiwan"},
-		{"🇯🇵", "日本聚合", "Japan"}, {"🇸🇬", "新加坡聚合", "Singapore"},
-		{"🇰🇷", "韩国聚合", "Korea"}, {"🇺🇸", "美国聚合", "USA"},
-		{"🇬🇧", "英国聚合", "UK"}, {"🇩🇪", "德国聚合", "Germany"},
-		{"🇳🇱", "荷兰聚合", "Netherlands"}, {"🇨🇦", "加拿大聚合", "Canada"},
-		{"🇦🇺", "澳大利亚聚合", "Australia"},
-	} {
-		if name == region.zh || name == region.en {
-			return region.flag
-		}
-	}
-	return ""
-}
-
-func validateRegionCredentials(rows []*serverRow) error {
-	for _, s := range rows {
-		if s == nil || s.placeholder || (s.Host == "127.0.0.1" && s.Port == 9) {
-			continue
-		}
-		if s.external && s.Type != "vless" {
-			continue
-		}
-		id, err := uuid.Parse(s.Password)
-		if err != nil || id == uuid.Nil || len(s.Password) != 36 || !strings.EqualFold(id.String(), s.Password) {
-			return errors.New("invalid regional entry UUID")
-		}
-	}
-	return nil
-}
-
-func regionRank(s *serverRow) int {
-	rank := 4
-	if s.Type == "hysteria" {
-		rank = 0
-	} else if !nativeproto.IsCDNWebSocketVless(s.Settings) {
-		rank = 2
-	}
-	if s.entryAlternate {
-		rank++
-	}
-	return rank
-}
-
-// Flat resources cannot carry policy groups. Select after renderer capability
-// filtering so a HY2-only primary never empties a VLESS-only resource.
-func regionFlatRows(rows []*serverRow, emits func(*serverRow) bool) []*serverRow {
-	ordered := slices.Clone(rows)
-	slices.SortStableFunc(ordered, func(a, b *serverRow) int { return regionRank(a) - regionRank(b) })
-	seen := map[string]bool{}
-	out := make([]*serverRow, 0, len(rows))
-	for _, s := range ordered {
-		if !emits(s) {
-			continue
-		}
-		region := entryRegion(s)
-		if region == "" {
-			out = append(out, s)
-			continue
-		}
-		if seen[region] {
-			continue
-		}
-		seen[region] = true
-		copy := *s
-		copy.Name = region
-		out = append(out, &copy)
-	}
-	return out
-}
-
-type regionMembers struct {
-	name    string
-	members []string
-}
-
-// Build only from successfully emitted, finally deduplicated names.
-func makeRegionMembers(rows []*serverRow, names []string, reserved []string) []regionMembers {
-	groups := []regionMembers{}
-	positions := map[string]int{}
-	order := make([]int, len(rows))
-	for i := range order {
-		order[i] = i
-	}
-	slices.SortStableFunc(order, func(a, b int) int { return regionRank(rows[a]) - regionRank(rows[b]) })
-	for _, i := range order {
-		region := entryRegion(rows[i])
-		if region == "" {
-			continue
-		}
-		pos, ok := positions[region]
-		if !ok {
-			pos = len(groups)
-			positions[region] = pos
-			groups = append(groups, regionMembers{name: region})
-		}
-		groups[pos].members = append(groups[pos].members, names[i])
-	}
-	labels := make([]string, len(groups))
-	for i, g := range groups {
-		labels[i] = g.name
-	}
-	labels = uniqueNames(labels, append(slices.Clone(reserved), names...), nil)
-	for i := range groups {
-		groups[i].name = labels[i]
-	}
-	return groups
-}
-
-// A transport-restricted parent must not acquire forbidden members through a
-// nested regional group. Full sets reference the regional selector; partial
-// sets retain only their first eligible primary, preserving the template gate.
-func collapseRegionMembers(members []string, regions []regionMembers) []string {
-	replacements := map[string]string{}
-	for _, g := range regions {
-		eligible := []string{}
-		for _, name := range g.members {
-			if slices.Contains(members, name) {
-				eligible = append(eligible, name)
-			}
-		}
-		if len(eligible) == 0 {
-			continue
-		}
-		target := eligible[0]
-		if len(eligible) == len(g.members) {
-			target = g.name
-		}
-		for _, name := range eligible {
-			replacements[name] = target
-		}
-	}
-	out := []string{}
-	for _, name := range members {
-		if target, ok := replacements[name]; ok {
-			name = target
-		}
-		if !slices.Contains(out, name) {
-			out = append(out, name)
-		}
-	}
-	return out
-}
-
-func regionStrings(v any) []string {
-	out := []string{}
-	switch values := v.(type) {
-	case []string:
-		return values
-	case []any:
-		for _, v := range values {
-			if s, ok := v.(string); ok {
-				out = append(out, s)
-			}
-		}
-	}
-	return out
-}
-
-type regionGroupExtras struct {
-	rewrites      map[string]string
-	templateNames []string
-}
-
-func applyRegionGroups(ctx context.Context, groups []any, rows []*serverRow, names []string, singbox bool, extras ...regionGroupExtras) []any {
-	options := regionOptions(ctx)
-	if !options.enabled {
-		return groups
-	}
-	rewrites := map[string]string{}
-	if len(extras) > 0 && extras[0].rewrites != nil {
-		rewrites = extras[0].rewrites
-	}
-	nameKey, membersKey, manual := "name", "proxies", "select"
-	if singbox {
-		nameKey, membersKey, manual = "tag", "outbounds", "selector"
-	}
-	reserved := []string{}
-	for _, raw := range groups {
-		if g, ok := raw.(map[string]any); ok {
-			if n, ok := g[nameKey].(string); ok {
-				reserved = append(reserved, n)
-			}
-		}
-	}
-	regions := makeRegionMembers(rows, names, reserved)
-	aliases := map[string]string{}
-	oldAutomatic := map[string]bool{}
-	for _, raw := range groups {
-		g, ok := raw.(map[string]any)
-		if !ok {
-			continue
-		}
-		name, _ := g[nameKey].(string)
-		kind, _ := g["type"].(string)
-		oldAutomatic[name] = kind == "url-test" || kind == "urltest" || kind == "fallback" || kind == "smart" || kind == "load-balance"
-	}
-	// Reuse the first template region name. Other aliases remain addressable
-	// by rules but disappear from parent choice lists.
-	for i := range regions {
-		flag := regionGroupRegion(regions[i].name)
-		canonical := ""
-		for _, raw := range groups {
-			g, ok := raw.(map[string]any)
-			if !ok || g[membersKey] == nil {
-				continue
-			}
-			name, _ := g[nameKey].(string)
-			if regionGroupRegion(name) != flag || !sameRegionMembers(regionStrings(g[membersKey]), regions[i].members) {
-				continue
-			}
-			if canonical == "" {
-				canonical = name
-			}
-			aliases[name] = canonical
-		}
-		if canonical != "" {
-			regions[i].name = canonical
-		}
-	}
-	// Follow nested selectors as well as direct node references. Otherwise an
-	// outer url-test can still switch between HY2-only and VLESS-only helpers.
-	reaches := map[string]bool{}
-	available := map[string]bool{}
-	if len(extras) > 0 {
-		for _, name := range extras[0].templateNames {
-			available[name] = true
-		}
-	}
-	if singbox {
-		for _, raw := range groups {
-			g, ok := raw.(map[string]any)
-			if !ok {
-				continue
-			}
-			kind, _ := g["type"].(string)
-			if g["server"] == "127.0.0.1" && fmt.Sprint(g["server_port"]) == "9" {
-				continue
-			}
-			if g[membersKey] == nil && kind != "direct" && kind != "block" && kind != "dns" && kind != "selector" && kind != "urltest" {
-				if name, ok := g[nameKey].(string); ok {
-					available[name] = true
-				}
-			}
-		}
-	}
-	for i, name := range names {
-		if !rows[i].placeholder && !(rows[i].Host == "127.0.0.1" && rows[i].Port == 9) {
-			available[name] = true
-		}
-		if entryRegion(rows[i]) != "" {
-			reaches[name] = true
-		}
-	}
-	for changed := true; changed; {
-		changed = false
-		for _, raw := range groups {
-			g, ok := raw.(map[string]any)
-			if !ok {
-				continue
-			}
-			name, _ := g[nameKey].(string)
-			for _, member := range regionStrings(g[membersKey]) {
-				if reaches[member] && !reaches[name] {
-					reaches[name], changed = true, true
-				}
-				if available[member] && !available[name] {
-					available[name], changed = true, true
-				}
-			}
-		}
-	}
-	removed := map[string]bool{}
-	for _, raw := range groups {
-		g, ok := raw.(map[string]any)
-		if !ok || g[membersKey] == nil {
-			continue
-		}
-		name, _ := g[nameKey].(string)
-		if regionGroupRegion(name) != "" && !available[name] {
-			removed[name] = true
-		}
-	}
-	result := make([]any, 0, len(groups)+len(regions))
-	for _, raw := range groups {
-		g, ok := raw.(map[string]any)
-		if !ok {
-			result = append(result, raw)
-			continue
-		}
-		members, exists := g[membersKey]
-		if !exists {
-			result = append(result, g)
-			continue
-		}
-		name, _ := g[nameKey].(string)
-		if removed[name] {
-			continue
-		}
-		if target, ok := aliases[name]; ok && target == name {
-			continue
-		}
-		original := regionStrings(members)
-		affected := reaches[name] || aliases[name] != ""
-		for _, member := range original {
-			if reaches[member] || aliases[member] != "" {
-				affected = true
-			}
-		}
-		// Preserve only the independent proxy-then-DIRECT service policy.
-		service := len(original) == 2 && (slices.Contains(original, "DIRECT") || slices.Contains(original, "direct"))
-		if service {
-			for _, member := range original {
-				if slices.Contains(names, member) {
-					service = false
-				}
-			}
-		}
-		// Service policies such as proxy-then-DIRECT fallback do not choose
-		// regional lines. Preserve their independent semantics and defaults.
-		// The explicitly enabled AI policy retains its own URL-test members.
-		// Default-off rendering still applies the original regional policy.
-		if !affected || service || (options.preserveAI && aiGroupName.MatchString(name)) {
-			result = append(result, g)
-			continue
-		}
-		collapsed := collapseRegionMembers(original, regions)
-		for i, member := range collapsed {
-			if target, ok := aliases[member]; ok {
-				collapsed[i] = target
-			}
-		}
-		// If this parent already admits the complete region, do not offer a
-		// second region entry via a narrower legacy group. The narrower group
-		// itself remains intact for rules and parents that need its policy.
-		for _, region := range regions {
-			if !slices.Contains(collapsed, region.name) {
-				continue
-			}
-			flag := regionGroupRegion(region.name)
-			kept := make([]string, 0, len(collapsed))
-			for _, member := range collapsed {
-				redundant := member != region.name && slices.Contains(reserved, member) && regionGroupRegion(member) == flag
-				if !redundant {
-					kept = append(kept, member)
-				}
-			}
-			collapsed = kept
-		}
-		collapsed = uniqueRegionChoices(collapsed)
-		if target, ok := aliases[name]; ok {
-			rewrites[name] = target
-			continue
-		}
-		// A restricted regional helper already collapsed to one eligible node.
-		// Inline that exact target instead of displaying a second region group.
-		if len(collapsed) == 1 {
-			for _, region := range regions {
-				if name != region.name && regionGroupRegion(name) == regionGroupRegion(region.name) {
-					rewrites[name] = collapsed[0]
-				}
-			}
-			if rewrites[name] != "" {
-				continue
-			}
-		}
-		// A legacy automatic global default must not mask the primary region.
-		if len(original) > 0 && oldAutomatic[original[0]] {
-			for _, region := range regions {
-				if slices.Contains(collapsed, region.name) {
-					collapsed = append([]string{region.name}, removeRegionChoice(collapsed, region.name)...)
-					break
-				}
-			}
-		}
-		defaultName, _ := g["default"].(string)
-		if target, ok := aliases[defaultName]; ok {
-			defaultName = target
-		}
-		if !slices.Contains(collapsed, defaultName) || oldAutomatic[defaultName] {
-			defaultName = ""
-		}
-		g[membersKey] = toAnySlice(collapsed)
-		g["type"] = manual
-		if !singbox {
-			delete(g, "region-ini-original")
-			delete(g, "region-ini-params")
-		}
-		for _, key := range []string{"url", "interval", "tolerance", "lazy", "strategy", "expected-status", "max-failed-times", "idle_timeout", "default", "include-all", "include-all-proxies", "include-all-providers", "use", "filter", "exclude-filter"} {
-			delete(g, key)
-		}
-		if singbox && len(collapsed) > 0 {
-			if defaultName == "" {
-				defaultName = collapsed[0]
-			}
-			g["default"] = defaultName
-		}
-		result = append(result, g)
-	}
-	for _, region := range regions {
-		members := region.members
-		g := map[string]any{nameKey: region.name, "type": manual, membersKey: toAnySlice(members)}
-		if singbox {
-			g["default"] = members[0]
-		}
-		result = append(result, g)
-	}
-	for _, raw := range result {
-		g, ok := raw.(map[string]any)
-		if !ok || g[membersKey] == nil {
-			continue
-		}
-		members := regionStrings(g[membersKey])
-		for i, member := range members {
-			if target := rewrites[member]; target != "" {
-				members[i] = target
-				delete(g, "region-ini-original")
-			}
-		}
-		g[membersKey] = toAnySlice(uniqueRegionChoices(members))
-		if def, ok := g["default"].(string); ok && rewrites[def] != "" {
-			g["default"] = rewrites[def]
-		}
-	}
-	// Removing a region must also remove its choices from every parent. Keep
-	// empty groups until the format's existing fail-closed rule cleanup runs.
-	for changed := true; changed; {
-		changed = false
-		for _, raw := range result {
-			g, ok := raw.(map[string]any)
-			if !ok || g[membersKey] == nil {
-				continue
-			}
-			name, _ := g[nameKey].(string)
-			kept := []string{}
-			for _, member := range regionStrings(g[membersKey]) {
-				if !removed[member] {
-					kept = append(kept, member)
-				}
-			}
-			g[membersKey] = toAnySlice(kept)
-			if len(kept) == 0 && !removed[name] {
-				removed[name], changed = true, true
-			}
-			if def, ok := g["default"].(string); ok && !slices.Contains(kept, def) {
-				delete(g, "default")
-			}
-			if original, ok := g["region-ini-original"].(string); ok {
-				for ref := range removed {
-					if strings.Contains(original, ref) {
-						delete(g, "region-ini-original")
-						break
-					}
-				}
-			}
-		}
-	}
-	kept := []any{}
-	for _, raw := range result {
-		g, ok := raw.(map[string]any)
-		if ok {
-			if name, _ := g[nameKey].(string); removed[name] {
-				continue
-			}
-		}
-		kept = append(kept, raw)
-	}
-	return kept
-}
-
-func sameRegionMembers(a, b []string) bool {
-	a = uniqueRegionChoices(a)
-	if len(a) != len(b) {
-		return false
-	}
-	for _, name := range b {
-		if !slices.Contains(a, name) {
-			return false
-		}
-	}
-	return true
-}
-
-func uniqueRegionChoices(names []string) []string {
-	out := []string{}
-	for _, name := range names {
-		if !slices.Contains(out, name) {
-			out = append(out, name)
-		}
-	}
-	return out
-}
-func removeRegionChoice(names []string, name string) []string {
-	out := []string{}
-	for _, candidate := range names {
-		if candidate != name {
-			out = append(out, candidate)
-		}
-	}
-	return out
-}
-
-func applyRegionINI(ctx context.Context, profile string, rows []*serverRow) string {
-	if !regionOptions(ctx).enabled {
-		return profile
-	}
-	names := []string{}
-	emitted := []*serverRow{}
-	for _, s := range rows {
-		if s.Type == "hysteria" && surgeHysteria(s) != "" {
-			names = append(names, iniSafeNodeName(s.Name))
-			emitted = append(emitted, s)
-		}
-	}
-	groups := []any{}
-	lines := strings.Split(profile, "\n")
-	inGroups := false
-	indexes := []int{}
-	for i, line := range lines {
-		trimmed := strings.TrimSpace(line)
-		if strings.HasPrefix(trimmed, "[") {
-			inGroups = strings.EqualFold(trimmed, "[Proxy Group]")
-			continue
-		}
-		if !inGroups || trimmed == "" || strings.HasPrefix(trimmed, "#") || strings.HasPrefix(trimmed, ";") {
-			continue
-		}
-		name, body, ok := strings.Cut(line, "=")
-		if !ok {
-			continue
-		}
-		fields := splitINIGroupParameters(body)
-		if len(fields) < 2 {
-			continue
-		}
-		members := []string{}
-		params := []string{}
-		for _, field := range fields[1:] {
-			field = strings.TrimSpace(field)
-			if strings.Contains(field, "=") {
-				params = append(params, field)
-			}
-			if field != "" && !strings.Contains(field, "=") {
-				members = append(members, field)
-			}
-		}
-		// Resolve native dynamic inclusion against successfully emitted nodes.
-		// Client-side expansion would bypass manual regional normalization.
-		all, filter := false, ""
-		for _, field := range fields[1:] {
-			key, value, _ := strings.Cut(strings.TrimSpace(field), "=")
-			if key == "include-all-proxies" {
-				all = strings.TrimSpace(value) == "true"
-			}
-			if key == "policy-regex-filter" {
-				filter = strings.Trim(strings.TrimSpace(value), "\"'")
-			}
-		}
-		if all {
-			members = append(members, names...)
-		}
-		if filter != "" {
-			filtered := []string{}
-			for _, member := range members {
-				if matchRegex("/"+filter+"/", member) {
-					filtered = append(filtered, member)
-				}
-			}
-			members = filtered
-		}
-		groups = append(groups, map[string]any{"name": strings.TrimSpace(name), "type": strings.TrimSpace(fields[0]), "proxies": toAnySlice(members), "region-ini-original": line, "region-ini-params": params})
-		indexes = append(indexes, i)
-	}
-	oldNames := map[string]bool{}
-	for _, raw := range groups {
-		oldNames[raw.(map[string]any)["name"].(string)] = true
-	}
-	rewrites := map[string]string{}
-	groups = applyRegionGroups(ctx, groups, emitted, names, false, regionGroupExtras{rewrites: rewrites})
-	for _, raw := range groups {
-		delete(oldNames, raw.(map[string]any)["name"].(string))
-	}
-	rendered := []string{}
-	for _, raw := range groups {
-		g := raw.(map[string]any)
-		if original, ok := g["region-ini-original"].(string); ok {
-			rendered = append(rendered, original)
-			continue
-		}
-		line := g["name"].(string) + " = " + g["type"].(string) + ", " + strings.Join(append(regionStrings(g["proxies"]), regionStrings(g["region-ini-params"])...), ", ")
-		rendered = append(rendered, line)
-	}
-	if len(indexes) == 0 {
-		return profile
-	}
-	for _, i := range indexes {
-		lines[i] = ""
-	}
-	lines[indexes[0]] = strings.Join(rendered, "\n")
-	out := strings.TrimRightFunc(strings.Join(lines, "\n"), unicode.IsSpace) + "\n"
-	for name, target := range rewrites {
-		out = repointSurgeRules(out, map[string]bool{name: true}, target)
-		delete(oldNames, name)
-	}
-	return repointSurgeRules(out, oldNames, "REJECT")
-}
-
-// Rewrite only policy references, never node payloads or match predicates.
-func rewriteRegionSingBoxRefs(value any, aliases map[string]string) {
-	switch v := value.(type) {
-	case map[string]any:
-		for key, child := range v {
-			switch key {
-			case "outbound", "detour", "download_detour", "final", "default":
-				if name, ok := child.(string); ok && aliases[name] != "" {
-					v[key] = aliases[name]
-				}
-			}
-			rewriteRegionSingBoxRefs(child, aliases)
-		}
-	case []any:
-		for _, child := range v {
-			rewriteRegionSingBoxRefs(child, aliases)
-		}
-	}
-}
-
-func rewriteRegionClashRules(value any, aliases map[string]string) {
-	switch v := value.(type) {
-	case map[string]any:
-		for _, child := range v {
-			rewriteRegionClashRules(child, aliases)
-		}
-	case []any:
-		for i, child := range v {
-			line, ok := child.(string)
-			if !ok {
-				continue
-			}
-			fields := strings.Split(line, ",")
-			for j := len(fields) - 1; j >= 1; j-- {
-				name := strings.TrimSpace(fields[j])
-				if clashRuleTrailingOptions[strings.ToLower(name)] {
-					continue
-				}
-				if target := aliases[name]; target != "" {
-					fields[j] = target
-					v[i] = strings.Join(fields, ",")
-				}
-				break
-			}
-		}
-	}
-}

exec
/bin/zsh -lc 'git diff -U130 08bf94184af24ebcc9f4af036cd7027fbf397cdb 6d5bcf0dfa16294bc4d7a9a06525a41a915ea641 -- internal/modules/subscribe/endpoint_salt.go internal/modules/subscribe/entry_projection.go' in /Users/j/codex-runs/mh1105/yb-138
 succeeded in 0ms:
diff --git a/internal/modules/subscribe/endpoint_salt.go b/internal/modules/subscribe/endpoint_salt.go
index dc89f08c..3d8e79c3 100644
--- a/internal/modules/subscribe/endpoint_salt.go
+++ b/internal/modules/subscribe/endpoint_salt.go
@@ -1,382 +1,387 @@
 package subscribe
 
 import (
 	"context"
+	"encoding/json"
 	"errors"
 	"log/slog"
 	"maps"
 	"strings"
 	"time"
 
-	"github.com/onesyue/yueboard/internal/platform/entrypath"
 	"github.com/onesyue/yueboard/internal/platform/entrysalt"
 	"github.com/onesyue/yueboard/internal/platform/metrics"
 	"github.com/onesyue/yueboard/internal/platform/nativeproto"
 )
 
 // 入口主机名按订阅加盐，降低稳定名称的可枚举性，并支持按桶轮换。
 // 历史日志曾观察到不同名字的封锁差异；它不能证明只封精确 FQDN、
 // 共享父域永远安全，或同一 IP 上的其他桶不会受影响。DNS、IP、端口、
 // 协议与 SNI 是不同故障维度，当前抗干扰效果仍需真实用户路径测量。
 // 盐名不得包含规范主机名，不用 CNAME 暴露后端；它不是 IP 隐身机制。
 
 // endpointSaltConfig 存在 settings 里（键 subscribeEndpointSaltKey），形如：
 //
 //	{"enabled":true,"zone":"e.yuetong.online","secret":"<base64>",
 //	 "hosts":{"v4.yuetoto.net":"7f3a9c21", "gw-fe7d4070.yuetong.online":"c40b18de"},
 //	 "host_buckets":{"v4.yuetoto.net":["k0","k1",…]}, "quarantine_buckets":64,
 //	 "pinned_buckets":{"v4.yuetoto.net":{"bucket":0,"user_ids":[…]}}}
 //
 // pinned_buckets is an account→bucket override. Listed accounts are served the
 // salted name of that existing bucket; every other account keeps the HMAC name.
 // Account IDs come only from this setting.
 //
 // hosts 是**白名单**：只有在这里登记了 hostkey（= 已经开好 *.hostkey.zone 通配 A 记录）
 // 的主机名才会被加盐。没登记的原样输出。这让上线可以一台一台来，
 // 而不是一次性把全队推进一个没验证过的解析路径。
 // host_buckets / quarantine_buckets 的语义见 platform/entrysalt（分桶与新号隔离区）。
 //
 // 另有 `"cdn_hosts":{"cdn.example.com":{"zone":"fernwoodapps.com","buckets":["a3f9c1d2",…]}}`：
 // CDN 保底行的主机走 `<bucketkey>.<zone>` 单标签名（见 entrysalt.CDNSaltedHost），
 // 且连同 SNI 与 ws Host 头一起改写（rewriteCDNRow）。
 type endpointSaltConfig = entrysalt.Config
 
 const subscribeEndpointSaltKey = "subscribe_endpoint_salt"
 const subscribeEndpointSaltLastGoodKey = "subscribe_endpoint_salt_last_good"
 
 func (m *Module) endpointSalt(ctx context.Context) *endpointSaltConfig {
 	snapshot, err := m.settings.RawSnapshot(ctx)
 	if err != nil {
 		return nil
 	}
 	return m.endpointSaltFromSnapshot(ctx, snapshot)
 }
 
-// One successful settings snapshot binds pair requirements to the salt material.
-// A cold database error must never become the legacy "pairs disabled" default.
+// Load salt material from one consistent settings snapshot.
 func (m *Module) entryProjectionConfig(ctx context.Context) (*endpointSaltConfig, bool, error) {
 	snapshot, err := m.settings.RawSnapshot(ctx)
 	if err != nil {
 		return nil, false, err
 	}
 	required, present := snapshot["subscribe_entry_pairs_required"]
 	if present && required != "0" && required != "1" {
-		return nil, false, errors.New("invalid entry pair requirement")
+		return nil, false, errors.New("invalid entry protection requirement")
 	}
 	cfg := m.endpointSaltFromSnapshot(ctx, snapshot)
 	if required == "1" && cfg == nil {
-		return nil, true, errors.New("required entry pair configuration unavailable")
+		return nil, true, errors.New("required entry configuration unavailable")
 	}
 	return cfg, required == "1", nil
 }
 
 func (m *Module) endpointSaltFromSnapshot(ctx context.Context, snapshot map[string]string) *endpointSaltConfig {
 	raw := snapshot[subscribeEndpointSaltKey]
 	hit := m.endpointSaltParsed.Load()
 	if hit != nil && hit.raw == raw && hit.cfg != nil &&
 		(m.pool == nil || hit.persisted || time.Since(hit.attempt) < 30*time.Second) {
 		return hit.cfg
 	}
-	cfg, err := entrysalt.Parse(raw)
+	cfg, err := parseSubscriptionSalt(raw)
 	if err != nil {
 		// Do not expose canonical names on a corrupt/missing configuration.
 		// Prefer this process's last accepted generation, then the durable copy.
 		metrics.Event("subscribe.entry_salt.invalid")
 		if hit != nil && hit.cfg != nil {
 			return hit.cfg
 		}
-		cfg, err = entrysalt.Parse(snapshot[subscribeEndpointSaltLastGoodKey])
+		cfg, err = parseSubscriptionSalt(snapshot[subscribeEndpointSaltLastGoodKey])
 		if err != nil {
 			return nil
 		}
 		return cfg
 	}
-	// Legacy salt documents may omit fault-domain metadata. Once pairs are
-	// required, such a document must not replace the last verified recovery
-	// material or poison this process's cache. Return it for the shared visible-
-	// product gate; hidden products do not enlarge that user's required scope.
-	if snapshot["subscribe_entry_pairs_required"] == "1" {
-		for _, namespace := range []map[string][]int{cfg.AlternateBuckets, cfg.CDNAlternateBuckets} {
-			for host := range namespace {
-				if cfg.EntryPairScopes[host] == "" {
-					return cfg
-				}
-			}
-		}
+	// Incomplete scope must not replace verified recovery material. Visible
+	// rows are checked by projectEntryEndpoints; hidden rows cannot widen access.
+	if snapshot["subscribe_entry_pairs_required"] == "1" && !completeEntryScopes(cfg) {
+		return cfg
 	}
 	// The Board owns this setting. Persist only while the source row is still
 	// the exact snapshot we parsed; a concurrent rotation must not be rolled
 	// back by a delayed subscription request. Lock the source before taking the
 	// backup row lock: a plain SELECT can keep its pre-publication MVCC snapshot
 	// while ON CONFLICT waits, then overwrite the newly published backup. This
 	// ordering also matches the native publisher (source, then last-good).
 	// Never log the config or secret.
 	persisted := false
 	if m.pool != nil {
 		snapshot, loadErr := m.settings.RawSnapshot(ctx)
 		if loadErr == nil && snapshot[subscribeEndpointSaltKey] == raw {
 			tag, saveErr := m.pool.Exec(ctx, `INSERT INTO settings(name,value,created_at,updated_at)
 				SELECT $1,value,now(),now() FROM settings WHERE name=$2 AND value=$3 FOR SHARE
 				ON CONFLICT(name) DO UPDATE SET value=EXCLUDED.value,updated_at=now()
 				WHERE settings.value IS DISTINCT FROM EXCLUDED.value`,
 				subscribeEndpointSaltLastGoodKey, subscribeEndpointSaltKey, snapshot[subscribeEndpointSaltKey])
 			if saveErr != nil {
 				metrics.Event("subscribe.entry_salt.persist_error")
 			} else {
 				persisted = tag.RowsAffected() == 1 || m.settings.Get(ctx, subscribeEndpointSaltLastGoodKey, "") == raw
 			}
 		}
 	}
 	m.endpointSaltParsed.Store(&endpointSaltParse{raw: raw, cfg: cfg, persisted: persisted, attempt: time.Now()})
 	return cfg
 }
 
 // endpointSaltParse 按**原串**缓存加盐配置的解析结果（2026-10-04）：每次订阅交付都会
 // 读它，此前每次重新 JSON 解析 + 校验。键是 settings 原文本，配置一改原串即变，缓存
 // 自然失效；解析失败保留上一份合法配置，并尝试耐久备份。返回的 *Config 由本模块请求
 // 共享，调用方只读（entrysalt.Config 在本包内从不被写）。
 type endpointSaltParse struct {
 	raw       string
 	cfg       *endpointSaltConfig
 	persisted bool
 	attempt   time.Time
 }
 
 // hasExplicitSNI 判断这个节点在**所有**渲染器里是否都会带上显式的 SNI/servername。
 //
 // 🚨 这是加盐能不能做的前提，不是可选项。每个渲染器都写成
 // `if sn := gs(ps, "..."); sn != ""` —— 拿不到就不输出，客户端于是拿**连接地址**
 // 当 SNI。加盐之后连接地址是一个随机名字，证书上没有它，握手直接失败。
 // 生产上 42 个 hysteria 全部设了 server_name 且 allow_insecure=false，所以今天是安全的；
 // 但只要有人以后加了一个没设的节点，加盐就会静默打挂它。因此这里**逐节点判定**，
 // 没有显式 SNI 的节点一律不加盐（保持规范主机名，行为完全不变）。
 //
 // 反向的安全佐证：生产 42 个 hysteria 里已有 28 个在跑 sni != host，
 // 也就是说「连接地址与 SNI 分离」不是本次引入的新模式。
 func hasExplicitSNI(s *serverRow) bool {
 	return nativeproto.HasExplicitServerName(s.Type, s.Settings)
 }
 
 // saltedHost 算出这份订阅在这个主机名上专属的入口名（稳定区身份）。
 // 计算核在 platform/entrysalt，这里只是 subscribe 侧的薄封装；测试沿用此签名。
 func saltedHost(cfg *endpointSaltConfig, token, canonicalHost string) string {
 	return entrysalt.SaltedHost(cfg, entrysalt.Subject{Token: token}, canonicalHost)
 }
 
 // saltSubjectFor 把「这份订阅属于哪一层」算出来：无付费史或账号不足 30 天 → 隔离区。
 func saltSubjectFor(u *subUser, token string, now time.Time) entrysalt.Subject {
 	var quarantineUntil int64
 	if u.EntryQuarantineUntil != nil {
 		quarantineUntil = *u.EntryQuarantineUntil
 	}
 	quarantine := entrysalt.EffectiveQuarantineTier(
 		u.Paid, u.CreatedAt, quarantineUntil, now.Unix(),
 	)
 	return entrysalt.Subject{Token: token, UserID: u.ID, Quarantine: quarantine}
 }
 
 // applyEndpointSalt：测试与旧调用点用的稳定区形态。
 func applyEndpointSalt(cfg *endpointSaltConfig, token string, servers []*serverRow) int {
 	return applyEndpointSaltFor(cfg, entrysalt.Subject{Token: token}, servers)
 }
 
 // applyEndpointSaltFor 就地把每个节点的连接主机名换成该订阅专属的加盐名。
 //
 // 普通主机只动 serverRow.Host —— 那是所有渲染器（Clash/Surge/Loon/QX/sing-box/
 // Surfboard/general 链接）共用的连接地址字段。SNI/servername 一律来自 Settings，
 // **不碰**，所以证书校验路径完全不变。
 //
 // CDN 保底行（vless tls=1 + ws，主机登记在 cdn_hosts）是唯一的例外：CDN 边缘按
 // SNI/Host 头路由到回源，所以连接地址、tls_settings.server_name 与
 // network_settings.headers.Host 三者必须一起改成同一个 `<bucketkey>.<zone>`
 // （rewriteCDNRow，对 Settings 写时复制）。它先于普通路径判定，且只对 CDN 形状的行
 // 生效——登记在 cdn_hosts 的主机上若挂着一条 Reality 行，那条行按普通路径处理。
 //
 // 返回实际加盐的节点数，供调用方做可观测（0 是有意义的信号，不是无事发生）。
 func applyEndpointSaltFor(cfg *endpointSaltConfig, subject entrysalt.Subject, servers []*serverRow) int {
 	if cfg == nil || subject.Token == "" {
 		return 0
 	}
 	n := 0
 	for _, s := range servers {
 		if s == nil || s.Host == "" {
 			continue
 		}
 		// IP 字面量没有可枚举的域名，加盐反而制造一个解析不到的名字。
 		if strings.ContainsAny(s.Host, ":") || isIPv4Literal(s.Host) {
 			continue
 		}
 		if s.Type == "vless" && nativeproto.IsCDNWebSocketVless(s.Settings) {
 			// 🚨 CDN 形状的行只有两种合法结局：三处字段（Host / tls_settings.server_name /
 			// network_settings.headers.Host）**一起**换成同一个 `<bucketkey>.<zone>`，
 			// 或者整行原样不动。这里必须无条件 continue —— 掉进下面的普通路径会只换
 			// s.Host，把 SNI 与 ws Host 头留在**真实回源域名**上，正好复刻 2026-09-02
 			// 那次「订阅 sni 字段是可解析域名 → 45/45 节点真实 IP 外泄」的形态，而且
 			// 更隐蔽：连接地址看起来已经加过盐了。
 			//
 			// 可达条件是「主机登记在 hosts/host_buckets 但不在 cdn_hosts」——CDN 源站
 			// 上线是九道门的多步过程（见 cdn-origin-onboarding-traps），部分登记是已知
 			// 的常态中间状态。2026-09-04 只读核对生产：4 台 cdn-*.fernwoodapps.com 当前
 			// 只在 cdn_hosts 里（hosts/host_buckets 均无），所以尚未真实触发。
 			originHost := s.cdnOriginHost
 			if originHost == "" {
 				originHost = s.Host
 			}
-			if salted, ok := entrysalt.CDNEntryHost(cfg, subject, originHost, s.entryAlternate); ok {
+			if salted, ok := entrysalt.CDNEntryHost(cfg, subject, originHost, false); ok {
 				s.cdnOriginHost = originHost
 				rewriteCDNRow(s, salted)
 				n++
 			}
 			continue
 		}
 		if !hasExplicitSNI(s) {
 			continue
 		}
 		salted := entrysalt.SaltedHost(cfg, subject, s.Host)
-		if s.entryAlternate {
-			salted = entrysalt.AlternateSaltedHost(cfg, subject, s.Host)
-		}
 		if salted == "" {
 			continue
 		}
 		s.Host = salted
 		n++
 	}
 	return n
 }
 
 // dropUnsaltableCDNRows 剔掉拿不到加盐名的 CDN 保底行。
 //
 // endpointSalt 优先使用当前合法配置，失败使用上一份合法配置。首次没有合法配置时，
 // 已纳入路径模型的线路拒绝发布；CDN 下方还有逐行可解析性保护。
 // 对 CDN 保底行**不成立**——那条车道的设计就是「回源名不进公共 DNS，只有桶名解析」。
 // 2026-09-04 从 bastion（本机在 fake-ip 代理后，1.1.1.1 的结果全是 198.18.0.0/15，
 // 不可用作判据）实测：
 //
 //	cdn-{sg,jp,nl,us}.fernwoodapps.com  → NXDOMAIN
 //	9c2011bf.fernwoodapps.com（桶名）    → 104.21.45.157 / 172.67.216.104（CF）
 //
 // 也就是说 fail-open 一旦触发，四条保底行就变成四个**永远解析不到**的节点，
 // 混在 urltest/selector 里被选中即失败，而所有指标与测试都不会变。发一个死节点
 // 不比不发好；不发至少是诚实的，而且是自愈的——加盐配置一修好它们立刻回来。
 //
 // 覆盖全部五条 fail-open 路径（这是一族，不是一处）：配置缺失/关闭/解析失败、
 // 主机未登记进 cdn_hosts、桶名或 zone 为空、名字越界、以及 applyEndpointSaltFor
 // 里任何一条 continue。判据统一走 CDNSaltedHost 本身，不复述它的内部条件。
 func dropUnsaltableCDNRows(cfg *endpointSaltConfig, subject entrysalt.Subject, servers []*serverRow) []*serverRow {
 	kept := servers[:0:0]
 	for _, s := range servers {
 		// node_ext 并进来的第三方 VLESS+WS+TLS 节点形状相同，但它们不是舰队的 CDN 保底行、
 		// 主机名本来就公开可解析——此前加盐一开就被每次请求整批丢掉并各打一条 Warn
 		// （2026-09-21 审计）。
 		if s == nil || s.external || s.Type != "vless" || !nativeproto.IsCDNWebSocketVless(s.Settings) {
 			kept = append(kept, s)
 			continue
 		}
 		if cfg != nil && subject.Token != "" && s.cdnOriginHost != "" {
 			// applyEndpointSaltFor has already replaced Host. Look up the
 			// canonical identity and require the actual three-field rewrite;
 			// merely recognizing a bucket suffix would admit unverified rows.
-			if salted, ok := entrysalt.CDNEntryHost(cfg, subject, s.cdnOriginHost, s.entryAlternate); ok &&
+			if salted, ok := entrysalt.CDNEntryHost(cfg, subject, s.cdnOriginHost, false); ok &&
 				s.Host == salted && gs(s.Settings, "tls_settings.server_name") == salted &&
 				gs(s.Settings, "network_settings.headers.Host") == salted {
 				kept = append(kept, s)
 				continue
 			}
 		}
 		metrics.Event("subscribe.endpoint_salt.cdn_row_dropped")
 		slog.Warn("dropped CDN fallback row without a salted entry name (its origin host does not resolve publicly)",
 			"server_id", s.ID, "server_name", s.Name, "host", s.Host, "salt_configured", cfg != nil)
 	}
 	return kept
 }
 
 // rewriteCDNRow 把 CDN 保底行的连接地址、SNI 与 ws Host 头改成同一个加盐名。
 //
 // Settings 写时复制：serverRow.Settings 可能与缓存（nodeext 的导入结果、模块内的
 // 行缓存）共享同一个 map，就地改会把这份订阅的专属名字漏进下一份订阅。只复制
 // 被改到的三层（顶层 / tls_settings / network_settings.headers），其余子树共享。
 func rewriteCDNRow(s *serverRow, salted string) {
 	ps := cloneMap(s.Settings)
 	tlsSettings := cloneMap(asMap(ps["tls_settings"]))
 	tlsSettings["server_name"] = salted
 	ps["tls_settings"] = tlsSettings
 	networkSettings := cloneMap(asMap(ps["network_settings"]))
 	headers := cloneMap(asMap(networkSettings["headers"]))
 	headers["Host"] = salted
 	networkSettings["headers"] = headers
 	ps["network_settings"] = networkSettings
 	s.Settings = ps
 	s.Host = salted
 }
 
 func asMap(v any) map[string]any {
 	m, _ := v.(map[string]any)
 	return m
 }
 
 func cloneMap(m map[string]any) map[string]any {
 	out := make(map[string]any, len(m)+1)
 	maps.Copy(out, m)
 	return out
 }
 
 func isIPv4Literal(h string) bool {
 	parts := strings.Split(h, ".")
 	if len(parts) != 4 {
 		return false
 	}
 	for _, p := range parts {
 		if p == "" || len(p) > 3 {
 			return false
 		}
 		for _, c := range p {
 			if c < '0' || c > '9' {
 				return false
 			}
 		}
 	}
 	return true
 }
 
-// expandEntryAlternates preserves product identity, credentials and permissions.
-// A is always followed by B; primary-bucket HMAC still distributes users across
-// the admitted pool. Display order is not a claim of independent failure domains.
-func expandEntryAlternates(cfg *endpointSaltConfig, subject entrysalt.Subject, servers []*serverRow, requireAll ...bool) ([]*serverRow, error) {
-	all := len(requireAll) != 0 && requireAll[0]
-	out := make([]*serverRow, 0, len(servers)*2)
-	for _, s := range servers {
-		if s == nil {
-			return nil, errors.New("nil entry product")
-		}
-		path, err := entrypath.Parse(s.Settings)
-		if err != nil {
+// Legacy alternate metadata belongs to node synchronization, not subscriptions.
+func parseSubscriptionSalt(raw string) (*endpointSaltConfig, error) {
+	var fields map[string]json.RawMessage
+	if err := json.Unmarshal([]byte(raw), &fields); err != nil {
+		return nil, err
+	}
+	rawScopes, hasScopes := fields["entry_pair_scopes"]
+	delete(fields, "alternate_buckets")
+	delete(fields, "cdn_alternate_buckets")
+	delete(fields, "entry_pair_scopes")
+	clean, err := json.Marshal(fields)
+	if err != nil {
+		return nil, err
+	}
+	cfg, err := entrysalt.Parse(string(clean))
+	if err != nil || cfg == nil {
+		return cfg, err
+	}
+	// Keep safety metadata independently of obsolete alternate assignments.
+	if hasScopes {
+		if err := json.Unmarshal(rawScopes, &cfg.EntryPairScopes); err != nil {
 			return nil, err
 		}
-		required := (path != nil && path.BackupRequired) || (all && !entryPairExempt(s))
-		if !required {
-			out = append(out, s)
-			continue
+		for host, scope := range cfg.EntryPairScopes {
+			_, normal := cfg.HostBuckets[host]
+			_, static := cfg.Hosts[host]
+			_, cdn := cfg.CDNHosts[host]
+			if (!normal && !static && !cdn) || (scope != "network" && scope != "machine" && scope != "shared") || (cdn && scope != "shared") {
+				return nil, errors.New("invalid entry scope")
+			}
 		}
-		if cfg == nil || subject.Token == "" {
-			return nil, errors.New("verified alternate entry unavailable")
+	}
+	return cfg, nil
+}
+
+// Every registered pool, including hidden pools, needs declared scope before
+// the document is eligible to replace verified recovery material.
+func completeEntryScopes(cfg *endpointSaltConfig) bool {
+	if cfg == nil {
+		return false
+	}
+	for host := range cfg.HostBuckets {
+		if cfg.EntryPairScopes[host] == "" {
+			return false
 		}
-		var primary, alternate string
-		if s.Type == "vless" && nativeproto.IsCDNWebSocketVless(s.Settings) {
-			primary, _ = entrysalt.CDNEntryHost(cfg, subject, s.Host, false)
-			alternate, _ = entrysalt.CDNEntryHost(cfg, subject, s.Host, true)
-		} else if hasExplicitSNI(s) {
-			primary = entrysalt.SaltedHost(cfg, subject, s.Host)
-			alternate = entrysalt.AlternateSaltedHost(cfg, subject, s.Host)
+	}
+	for host := range cfg.Hosts {
+		if cfg.EntryPairScopes[host] == "" {
+			return false
 		}
-		if primary == "" || alternate == "" || primary == alternate {
-			return nil, errors.New("verified distinct entry pair unavailable")
+	}
+	for host := range cfg.CDNHosts {
+		if cfg.EntryPairScopes[host] == "" {
+			return false
 		}
-		a, b := *s, *s
-		a.Name += " · A"
-		b.Name += " · B"
-		b.entryAlternate = true
-		out = append(out, &a, &b)
 	}
-	return out, nil
+	return true
 }
diff --git a/internal/modules/subscribe/entry_projection.go b/internal/modules/subscribe/entry_projection.go
index bbbc448d..1987f923 100644
--- a/internal/modules/subscribe/entry_projection.go
+++ b/internal/modules/subscribe/entry_projection.go
@@ -1,127 +1,159 @@
 package subscribe
 
 import (
 	"context"
 	"errors"
 	"log/slog"
 	"strings"
 
 	"github.com/onesyue/yueboard/internal/platform/entrypath"
 	"github.com/onesyue/yueboard/internal/platform/entrysalt"
 	"github.com/onesyue/yueboard/internal/platform/metrics"
+	"github.com/onesyue/yueboard/internal/platform/nativeproto"
 )
 
 // publishedServers is the shared visibility gate for subscription delivery and
 // per-user node intelligence. Both consume the same publication generation.
 func (m *Module) publishedServers(ctx context.Context, u *subUser, servers []*serverRow) ([]*serverRow, error) {
 	policy, err := entrypath.ParsePolicy(m.settings.Get(ctx, entrypath.PolicySetting, ""))
 	if err != nil {
 		return nil, err
 	}
 	if policy != nil {
 		policy = policy.WithX4B(m.x4bAdmission(ctx))
 		group := int64(0)
 		if u.GroupID != nil {
 			group = *u.GroupID
 		}
 		servers = filterIngressServers(policy, group, servers)
 	}
 	return filterNativeServers(servers), nil
 }
 
 // x4bAdmission reads the separately versioned ordinary exception. Damaged
 // state only ever narrows delivery back to the default (no exception): the
 // exception widens visibility, so ignoring it can never expose a product the
 // topology policy did not already admit. The writer validates every change,
 // so this branch is reached only through out-of-band edits; it is logged.
 func (m *Module) x4bAdmission(ctx context.Context) *entrypath.X4BAdmission {
 	if m.settings == nil {
 		return nil
 	}
 	admission, err := entrypath.ParseX4BAdmission(m.settings.Get(ctx, entrypath.X4BAdmissionSetting, ""))
 	if err != nil {
 		slog.WarnContext(ctx, "subscribe: X4B admission invalid; exception ignored", "err", err)
 		return nil
 	}
 	return admission
 }
 
 func validateEntrySalt(cfg *endpointSaltConfig, subject entrysalt.Subject, servers []*serverRow) error {
 	for _, s := range servers {
 		if _, admitted := s.Settings["entry_path"]; admitted &&
 			(cfg == nil || entrysalt.SaltedHost(cfg, subject, s.Host) == "") {
 			return errors.New("admitted entry publication unavailable")
 		}
 	}
 	return nil
 }
 
 // projectEntryEndpoints is the common, side-effect-free publication pipeline.
 // Callers supply per-request rows; cached rows must never acquire account salts.
 // Risk/HWID recording stays in subscription delivery, outside this projection.
-func projectEntryEndpoints(cfg *endpointSaltConfig, subject entrysalt.Subject, servers []*serverRow, requireAll ...bool) ([]*serverRow, int, error) {
-	if len(requireAll) != 0 && requireAll[0] {
-		if cfg == nil {
-			return nil, 0, errors.New("required entry pair configuration unavailable")
-		}
-		if err := entrysalt.ValidateAlternates(cfg); err != nil {
-			return nil, 0, err
-		}
-		for _, server := range servers {
-			if server != nil && !entryPairExempt(server) && cfg.EntryPairScopes[server.Host] == "" {
-				return nil, 0, errors.New("visible native entry pair scope unavailable")
-			}
-		}
+func projectEntryEndpoints(cfg *endpointSaltConfig, subject entrysalt.Subject, servers []*serverRow, requireEntry ...bool) ([]*serverRow, int, error) {
+	strict := len(requireEntry) != 0 && requireEntry[0]
+	if err := validateSingleEntryProtection(cfg, subject, servers, strict); err != nil {
+		return nil, 0, err
 	}
 	if err := validateEntrySalt(cfg, subject, servers); err != nil {
 		return nil, 0, err
 	}
+	cloned := make([]*serverRow, len(servers))
+	for i, source := range servers {
+		row := *source
+		cloned[i] = &row
+	}
+	servers = cloned
 	salted := 0
-	if cfg != nil || len(requireAll) != 0 && requireAll[0] {
-		var err error
-		servers, err = expandEntryAlternates(cfg, subject, servers, requireAll...)
-		if err != nil {
-			return nil, 0, err
-		}
+	if cfg != nil {
 		salted = applyEndpointSaltFor(cfg, subject, servers)
 	}
 	servers = dropIPLiteralFleetRows(cfg, servers)
-	return appendCDNCanary(cfg, subject, dropUnsaltableCDNRows(cfg, subject, servers)), salted, nil
+	return dropUnsaltableCDNRows(cfg, subject, servers), salted, nil
 }
 
 // dropIPLiteralFleetRows enforces "no IP literal in any render" (plan W3.5)
 // once entry salting is configured. Salting skips IP literals (there is no
 // name to salt), so before this a fleet row whose host is an address was
 // published verbatim — the exact enumeration the salt exists to prevent.
 // With pairs required such a row already fails the whole delivery (no pair
 // scope); without pairs it leaked. Dropping it is the honest middle: the row is
 // unpublishable until it gets a registered entry name, and the drop is counted
 // and logged. Exempt rows (node_ext third-party rows, 127.0.0.1:9 notice rows)
 // are not fleet entries and keep their addresses. Live inventory 2026-10-17:
 // 0 of 100 deliverable rows use an IP literal; all 25 hosts are registered.
 func dropIPLiteralFleetRows(cfg *endpointSaltConfig, servers []*serverRow) []*serverRow {
 	if cfg == nil {
 		return servers
 	}
 	kept := servers[:0:0]
 	for _, s := range servers {
 		if s != nil && !entryPairExempt(s) && (isIPv4Literal(s.Host) || strings.Contains(s.Host, ":")) {
 			metrics.Event("subscribe.endpoint_salt.ip_literal_dropped")
 			slog.Warn("dropped fleet row published under an IP literal; give it a registered entry name",
 				"server_id", s.ID, "server_name", s.Name)
 			continue
 		}
 		kept = append(kept, s)
 	}
 	return kept
 }
 
 // entryPairExempt reports rows that never carry a native entry pair: third-party
 // node_ext rows, and display-only rows (line-status tips for unusable accounts,
 // account-info rows) rendered at the client's own closed discard port
 // 127.0.0.1:9. With all native pairs required, an exempt row must not fail the
 // whole subscription — 2026-10-12: expired/banned accounts lost their renewal
 // tips and got an error after the fleet-wide A/B publish.
 func entryPairExempt(s *serverRow) bool {
 	return s.external || (s.Host == "127.0.0.1" && s.Port == 9)
 }
+
+// Strict publication still requires a verified primary entry. Retired alternate
+// assignments never determine whether that single entry is publishable.
+func validateSingleEntryProtection(cfg *endpointSaltConfig, subject entrysalt.Subject, servers []*serverRow, strict bool) error {
+	if strict && cfg == nil {
+		return errors.New("required entry configuration unavailable")
+	}
+	for _, s := range servers {
+		if s == nil {
+			return errors.New("nil entry product")
+		}
+		path, err := entrypath.Parse(s.Settings)
+		if err != nil {
+			return err
+		}
+		if entryPairExempt(s) {
+			continue
+		}
+		if strict && cfg.EntryPairScopes[s.Host] == "" {
+			return errors.New("visible native entry scope unavailable")
+		}
+		if !strict && path == nil {
+			continue
+		}
+		if cfg == nil || subject.Token == "" || !hasExplicitSNI(s) {
+			return errors.New("verified entry unavailable")
+		}
+		primary := ""
+		if s.Type == "vless" && nativeproto.IsCDNWebSocketVless(s.Settings) {
+			primary, _ = entrysalt.CDNEntryHost(cfg, subject, s.Host, false)
+		} else {
+			primary = entrysalt.SaltedHost(cfg, subject, s.Host)
+		}
+		if primary == "" {
+			return errors.New("verified entry unavailable")
+		}
+	}
+	return nil
+}

exec
/bin/zsh -lc 'git diff --summary 08bf94184af24ebcc9f4af036cd7027fbf397cdb 6d5bcf0dfa16294bc4d7a9a06525a41a915ea641; git diff 08bf94184af24ebcc9f4af036cd7027fbf397cdb 6d5bcf0dfa16294bc4d7a9a06525a41a915ea641 -- internal/modules/subscribe/region_entry_test.go internal/modules/subscribe/region_ai_test.go' in /Users/j/codex-runs/mh1105/yb-138
 succeeded in 0ms:
 delete mode 100644 internal/modules/subscribe/REGION-VALIDATION.md
 delete mode 100644 internal/modules/subscribe/cdn_canary.go
 delete mode 100644 internal/modules/subscribe/cdn_canary_test.go
 delete mode 100644 internal/modules/subscribe/pair_gate_parity_test.go
 delete mode 100644 internal/modules/subscribe/region_ai_test.go
 delete mode 100644 internal/modules/subscribe/region_entry.go
 delete mode 100644 internal/modules/subscribe/region_entry_test.go
 delete mode 100644 internal/modules/subscribe/region_fallback_test.go
 create mode 100644 internal/modules/subscribe/single_entry_protection_test.go
 delete mode 100644 internal/modules/subscribe/testdata/cdn_canary_off_clash.golden
 delete mode 100644 internal/modules/subscribe/testdata/cdn_canary_off_clashmeta.golden
 delete mode 100644 internal/modules/subscribe/testdata/cdn_canary_off_general.golden
 delete mode 100644 internal/modules/subscribe/testdata/cdn_canary_off_loon.golden
 delete mode 100644 internal/modules/subscribe/testdata/cdn_canary_off_quantumultx.golden
 delete mode 100644 internal/modules/subscribe/testdata/cdn_canary_off_sing-box.golden
 delete mode 100644 internal/modules/subscribe/testdata/cdn_canary_off_stash.golden
 delete mode 100644 internal/modules/subscribe/testdata/cdn_canary_off_surfboard.golden
 delete mode 100644 internal/modules/subscribe/testdata/cdn_canary_off_surge.golden
diff --git a/internal/modules/subscribe/region_ai_test.go b/internal/modules/subscribe/region_ai_test.go
deleted file mode 100644
index 031afe0c..00000000
--- a/internal/modules/subscribe/region_ai_test.go
+++ /dev/null
@@ -1,90 +0,0 @@
-package subscribe
-
-import (
-	"encoding/json"
-	"reflect"
-	"strings"
-	"testing"
-
-	"github.com/onesyue/yueboard/internal/platform/settings"
-	"go.yaml.in/yaml/v3"
-)
-
-// Exercise delivery so both feature settings and format-specific ordering apply.
-func TestRegionSingleAICompatibility(t *testing.T) {
-	for _, client := range []string{"clashmeta", "clash", "stash", "sing-box", "surge", "surfboard"} {
-		t.Run(client, func(t *testing.T) {
-			rows := []*serverRow{hy2Server(), realityServer(), hy2Server(), realityServer()}
-			for i, row := range rows {
-				row.Password = regionTestUUID
-				row.Name = []string{"🇺🇸 US AI H", "🇯🇵 JP AI V", "🇸🇬 H", "🇸🇬 V"}[i]
-			}
-			render := func(ai, region string) []byte {
-				m := aiModule(t, ai)
-				m.settings = settings.NewStatic(map[string]string{singleAIGroupSetting: ai, regionEntrySetting: region})
-				return deliverTransport(t, m, client, rows)
-			}
-			if string(render("", "1")) != string(render("0", "1")) {
-				t.Fatal("default-off AI changed regional output")
-			}
-			baseline, combined := render("1", "0"), render("1", "1")
-			if client == "surge" || client == "surfboard" {
-				aiLine := func(body []byte) string {
-					for _, line := range strings.Split(string(body), "\n") {
-						if strings.HasPrefix(line, "AI =") {
-							return line
-						}
-					}
-					t.Fatal("missing AI group")
-					return ""
-				}
-				if aiLine(baseline) != aiLine(combined) {
-					t.Fatal("regional selection changed AI group")
-				}
-				if !strings.Contains(string(combined), "🇸🇬 = select,") {
-					t.Fatal("missing manual region")
-				}
-				return
-			}
-			decode := func(body []byte) []any {
-				cfg := map[string]any{}
-				if client == "sing-box" {
-					if err := json.Unmarshal(body, &cfg); err != nil {
-						t.Fatal(err)
-					}
-					return cfg["outbounds"].([]any)
-				}
-				if err := yaml.Unmarshal(body, &cfg); err != nil {
-					t.Fatal(err)
-				}
-				return cfg["proxy-groups"].([]any)
-			}
-			nameKey, manual := "name", "select"
-			if client == "sing-box" {
-				nameKey, manual = "tag", "selector"
-			}
-			find := func(groups []any, name string) map[string]any {
-				for _, raw := range groups {
-					g := raw.(map[string]any)
-					if g[nameKey] == name {
-						return g
-					}
-				}
-				return nil
-			}
-			before, after := decode(baseline), decode(combined)
-			if !reflect.DeepEqual(find(before, "AI"), find(after, "AI")) {
-				t.Fatal("regional selection changed AI group")
-			}
-			if client != "clash" {
-				if find(after, "AI") == nil {
-					t.Fatal("missing AI group")
-				}
-				region := find(after, "🇸🇬")
-				if region == nil || region["type"] != manual {
-					t.Fatal("missing manual region")
-				}
-			}
-		})
-	}
-}
diff --git a/internal/modules/subscribe/region_entry_test.go b/internal/modules/subscribe/region_entry_test.go
deleted file mode 100644
index f3af6c80..00000000
--- a/internal/modules/subscribe/region_entry_test.go
+++ /dev/null
@@ -1,690 +0,0 @@
-package subscribe
-
-import (
-	"bytes"
-	"context"
-	"encoding/base64"
-	"encoding/json"
-	"fmt"
-	"net/http/httptest"
-	"net/url"
-	"os"
-	"path/filepath"
-	"strings"
-	"testing"
-	"time"
-
-	"github.com/google/uuid"
-	"github.com/onesyue/yueboard/internal/platform/settings"
-	"gopkg.in/yaml.v3"
-)
-
-const regionTestUUID = "12345678-1234-4234-8234-123456789abc"
-
-var regionTestFormats = []string{"general", "clashmeta", "clash", "stash", "sing-box", "loon", "surge", "surfboard", "quantumultx"}
-
-func regionTestDelivery(t *testing.T, flag, auto, credential string, enabled bool) *httptest.ResponseRecorder {
-	t.Helper()
-	cfg, rows := allPairsFixture()
-	for i, s := range rows {
-		s.Name = []string{"悦·🇸🇬新加坡1", "悦·🇸🇬新加坡2", "悦·🇸🇬新加坡CF"}[i]
-		s.Password = credential
-		if s.Type == "vless" && i == 1 {
-			s.Settings = checkableRealityServer().Settings
-		}
-	}
-	raw, err := json.Marshal(cfg)
-	if err != nil {
-		t.Fatal(err)
-	}
-	m := entryTestModule(t, "", "")
-	value := "0"
-	if enabled {
-		value = "1"
-	}
-	m.settings = settings.NewStatic(map[string]string{subscribeEndpointSaltKey: string(raw), "subscribe_entry_pairs_required": "1", regionEntrySetting: value})
-	for _, key := range []string{"clashmeta", "clash", "stash"} {
-		m.tmpls[key] = tmplEntry{content: "proxies: []\nproxy-groups:\n  - name: Proxy\n    type: select\n    proxies: []\nrules:\n  - MATCH,Proxy\n", at: time.Now()}
-	}
-	m.tmpls["singbox"] = tmplEntry{content: `{"outbounds":[{"type":"selector","tag":"Proxy","outbounds":[]},{"type":"direct","tag":"direct"}],"route":{"final":"Proxy"}}`, at: time.Now()}
-	for _, key := range []string{"surge", "surfboard"} {
-		m.tmpls[key] = tmplEntry{content: "#!MANAGED-CONFIG $subs_link interval=43200 strict=false\n[Proxy]\n$proxies\n[Proxy Group]\nProxy = select, $proxy_group\n[Rule]\nFINAL,Proxy\n", at: time.Now()}
-	}
-	request := httptest.NewRequest("GET", "https://sub.example/s/test?flag="+flag+"&auto%5Fselect="+auto, nil)
-	w := httptest.NewRecorder()
-	m.deliver(context.Background(), w, request, entrySubUser(), rows, 0, credential, "synthetic-region-test")
-	return w
-}
-
-func TestRegionEntryAllFormats(t *testing.T) {
-	for _, flag := range regionTestFormats {
-		for _, auto := range []string{"", "0", "1", "true"} {
-			t.Run(flag+"/auto="+auto, func(t *testing.T) {
-				w := regionTestDelivery(t, flag, auto, regionTestUUID, true)
-				if w.Code != 200 {
-					t.Fatalf("delivery status %d", w.Code)
-				}
-				body := w.Body.Bytes()
-				if flag == "clash" {
-					if bytes.Contains(body, []byte(regionTestUUID)) || !bytes.Contains(body, []byte("旧客户端")) {
-						t.Fatal("legacy Clash capability gate changed")
-					}
-					return
-				}
-				switch flag {
-				case "clashmeta", "clash", "stash", "sing-box":
-					cfg := map[string]any{}
-					groupKey, nameKey, memberKey, manual := "proxy-groups", "name", "proxies", "select"
-					if flag == "sing-box" {
-						if err := json.Unmarshal(body, &cfg); err != nil {
-							t.Fatal(err)
-						}
-						groupKey, nameKey, memberKey, manual = "outbounds", "tag", "outbounds", "selector"
-					} else if err := yaml.Unmarshal(body, &cfg); err != nil {
-						t.Fatal(err)
-					}
-					assertRegionOutputUUIDs(t, cfg)
-					groups, _ := cfg[groupKey].([]any)
-					count := 0
-					for _, raw := range groups {
-						g := raw.(map[string]any)
-						if g[nameKey] == "Proxy" {
-							members := omitShareSubscriptionNotice(regionStrings(g[memberKey]))
-							if len(members) != 1 || members[0] != "🇸🇬" || g["type"] != manual {
-								t.Fatalf("top-level choice is not one manual region: %v", members)
-							}
-						}
-						if g[nameKey] != "🇸🇬" {
-							continue
-						}
-						count++
-						if g["type"] != manual {
-							t.Fatal("wrong region selection mode")
-						}
-						members := regionStrings(g[memberKey])
-						if len(members) != 6 || !strings.Contains(members[0], "新加坡1 · A") || !strings.Contains(members[1], "新加坡1 · B") || !strings.Contains(members[4], "CF · A") {
-							t.Fatal("region lost paired transport order")
-						}
-						if g["tolerance"] != nil || g["url"] != nil || g["interval"] != nil {
-							t.Fatal("regional selector retains probe settings")
-						}
-						if flag == "sing-box" && g["default"] != members[0] {
-							t.Fatal("primary not default")
-						}
-					}
-					if count != 1 {
-						t.Fatalf("got %d region groups", count)
-					}
-					if !bytes.Contains(body, []byte(regionTestUUID)) {
-						t.Fatal("UUID missing")
-					}
-				case "surge", "surfboard":
-					mode := "select"
-					text := string(body)
-					if !strings.Contains(text, "🇸🇬 = "+mode+", 悦·🇸🇬新加坡1 · A, 悦·🇸🇬新加坡1 · B") || !strings.Contains(text, "Proxy = select, 🇸🇬") {
-						t.Fatal("incorrect supported regional group")
-					}
-					if strings.Contains(text, "新加坡2") || strings.Contains(text, "新加坡CF") {
-						t.Fatal("unsupported protocol emitted")
-					}
-					if strings.Contains(text, "tolerance=80") {
-						t.Fatal("regional selector retains probe settings")
-					}
-				default:
-					if flag != "loon" {
-						var err error
-						body, err = base64.StdEncoding.DecodeString(string(body))
-						if err != nil {
-							t.Fatal(err)
-						}
-					}
-					if bytes.Count(body, []byte(regionTestUUID)) != 1 {
-						t.Fatalf("flat resource contains %d entries", len(strings.Split(strings.TrimSpace(string(body)), "\n")))
-					}
-					if !bytes.Contains(body, []byte(regionTestUUID)) {
-						t.Fatal("UUID lost")
-					}
-					if flag == "quantumultx" && !bytes.Contains(body, []byte("vless=")) {
-						t.Fatal("QX did not select supported primary")
-					}
-					if flag == "general" && !bytes.HasPrefix(body, []byte("hysteria2://")) {
-						t.Fatal("general did not prefer HY2")
-					}
-				}
-			})
-		}
-	}
-}
-
-func TestRegionEntryInvalidUUIDAllFormats(t *testing.T) {
-	for _, flag := range regionTestFormats {
-		for _, invalid := range []string{"uuid-test", "12345678123442348234123456789abc", "00000000-0000-0000-0000-000000000000", "12345678-1234-4234-8234-123456789abz", "{12345678-1234-4234-8234-123456789abc}"} {
-			t.Run(flag, func(t *testing.T) {
-				w := regionTestDelivery(t, flag, "", invalid, true)
-				if w.Code != 500 || w.Body.Len() != 0 {
-					t.Fatal("invalid UUID not rejected without response details")
-				}
-			})
-		}
-	}
-}
-
-func TestRegionEntrySwitchDominatesParameter(t *testing.T) {
-	for _, flag := range regionTestFormats {
-		a := regionTestDelivery(t, flag, "", regionTestUUID, false)
-		b := regionTestDelivery(t, flag, "1", regionTestUUID, false)
-		if a.Code != 200 || b.Code != 200 || !bytes.Equal(a.Body.Bytes(), b.Body.Bytes()) {
-			t.Fatalf("%s: auto parameter changes disabled output", flag)
-		}
-	}
-}
-
-func TestRegionEntryBoundaries(t *testing.T) {
-	a := hy2Row()
-	a.Name = "悦·🇸🇬新加坡1"
-	a.Password = regionTestUUID
-	b := *a
-	b.Name = "悦·🇯🇵日本1"
-	c := *a
-	c.Name = "translated"
-	c.SourceName = a.Name
-	external := *a
-	external.external = true
-	groups := makeRegionMembers([]*serverRow{a, &b, &c, &external}, []string{"a", "b", "c", "external"}, []string{"🇸🇬"})
-	if len(groups) != 2 || groups[0].name == "🇸🇬" || len(groups[0].members) != 2 {
-		t.Fatal("region identity, collision or external isolation failed")
-	}
-	got := collapseRegionMembers([]string{"a", "b"}, groups)
-	if len(got) != 2 || got[0] != "a" || got[1] != groups[1].name {
-		t.Fatal("partial capability set widened")
-	}
-	if err := validateRegionCredentials([]*serverRow{a}); err != nil {
-		t.Fatal("valid UUID rejected")
-	}
-}
-
-// Optional export is synthetic only; it never reads database or subscription URLs.
-func TestRegionExportCoreFixtures(t *testing.T) {
-	dir := os.Getenv("YUEBOARD_REGION_FIXTURE_DIR")
-	if dir == "" {
-		t.Skip("fixture export not requested")
-	}
-	for _, flag := range regionTestFormats {
-		for _, mode := range []string{"off", "manual", "ignored"} {
-			auto := ""
-			if mode == "ignored" {
-				auto = "1"
-			}
-			w := regionTestDelivery(t, flag, auto, regionTestUUID, mode != "off")
-			if w.Code != 200 {
-				t.Fatal("fixture rendering failed")
-			}
-			if err := os.WriteFile(filepath.Join(dir, flag+"-"+mode+".conf"), w.Body.Bytes(), 0600); err != nil {
-				t.Fatal(err)
-			}
-		}
-	}
-}
-
-func TestRegionTemplateAliasesAndDefaults(t *testing.T) {
-	a := hy2Row()
-	a.Name = "悦·🇸🇬新加坡1"
-	a.Password = regionTestUUID
-	b := *a
-	b.Name = "悦·🇸🇬新加坡1 · B"
-	b.entryAlternate = true
-	b.defaultGroupHeld = true
-	for _, sb := range []bool{false, true} {
-		nameKey, memberKey, manual, auto := "name", "proxies", "select", "url-test"
-		if sb {
-			nameKey, memberKey, manual, auto = "tag", "outbounds", "selector", "urltest"
-		}
-		groups := []any{
-			map[string]any{nameKey: "Proxy", "type": manual, memberKey: []any{"auto", "🇸🇬 Singapore", "🇸🇬 Alias", a.Name, b.Name}, "include-all": true},
-			map[string]any{nameKey: "auto", "type": auto, memberKey: []any{a.Name}},
-			map[string]any{nameKey: "🇸🇬 Singapore", "type": auto, memberKey: []any{a.Name, b.Name}},
-			map[string]any{nameKey: "🇸🇬 Alias", "type": manual, memberKey: []any{a.Name, b.Name}},
-			map[string]any{nameKey: "Domestic", "type": manual, memberKey: []any{"Proxy", "direct"}, "default": "direct"},
-		}
-		ctx := context.WithValue(context.Background(), regionEntryKey{}, regionEntryOptions{enabled: true})
-		result := applyRegionGroups(ctx, groups, []*serverRow{a, &b}, []string{a.Name, b.Name}, sb)
-		regionCount := 0
-		for _, raw := range result {
-			g := raw.(map[string]any)
-			switch g[nameKey] {
-			case "Proxy":
-				members := regionStrings(g[memberKey])
-				if len(members) != 2 || members[0] != "🇸🇬 Singapore" || g["include-all"] != nil {
-					t.Fatal("legacy default or alias survived")
-				}
-			case "Domestic":
-				if sb && g["default"] != "direct" {
-					t.Fatal("unrelated explicit default changed")
-				}
-			case "🇸🇬 Alias":
-				t.Fatal("duplicate regional alias is still visible")
-			case "🇸🇬 Singapore":
-				regionCount++
-				if g["type"] != manual || !sameRegionMembers(regionStrings(g[memberKey]), []string{a.Name, b.Name}) {
-					t.Fatal("manual region lost selectable members")
-				}
-			}
-		}
-		if regionCount != 1 {
-			t.Fatal("duplicate canonical region")
-		}
-	}
-}
-
-func TestRegionEmbeddedSurgeDefault(t *testing.T) {
-	for _, format := range []string{"surge", "surfboard"} {
-		m := entryTestModule(t, format, "")
-		m.settings = settings.NewStatic(map[string]string{})
-		row := hy2Row()
-		row.Name = "悦·🇸🇬新加坡1"
-		row.Password = regionTestUUID
-		ctx := context.WithValue(context.Background(), regionEntryKey{}, regionEntryOptions{enabled: true})
-		r := httptest.NewRequest("GET", "https://sub.example/s/test", nil)
-		var body []byte
-		if format == "surge" {
-			body = m.renderSurge(ctx, r, entrySubUser(), []*serverRow{row}, "https://sub.example/s/test")
-		} else {
-			body = m.renderSurfboard(ctx, r, entrySubUser(), []*serverRow{row}, "https://sub.example/s/test")
-		}
-		if !bytes.Contains(body, []byte("Proxy = select, 🇸🇬,")) || !bytes.Contains(body, []byte("🇸🇬 = select, 悦·🇸🇬新加坡1")) {
-			t.Fatalf("%s embedded template does not default to regional primary", format)
-		}
-	}
-}
-
-func TestRegionMigrationIgnoresRetiredPreference(t *testing.T) {
-	m := fallbackModule("https://backup.example")
-	m.settings = settings.NewStatic(map[string]string{regionEntrySetting: "1"})
-	r := httptest.NewRequest("GET", "https://sub.example/s/test?auto%5Fselect=1&burn=1", nil)
-	w := httptest.NewRecorder()
-	m.setSubscriptionFallbackHeaders(w, r, "synthetic")
-	for _, value := range []string{w.Header().Get(headerHappNewURL), m.verifiedSubscriptionURL(r, "synthetic")} {
-		parsed, err := url.Parse(value)
-		if err != nil || len(parsed.Query()) != 1 || parsed.Query().Get("burn") != "1" {
-			t.Fatal("migration or refresh must preserve only burn")
-		}
-	}
-}
-
-func TestRegionProductionSingBoxTemplates(t *testing.T) {
-	for _, name := range []string{"subscribe_templates-1-zh-CN.json", "subscribe_templates-9-en.json"} {
-		m := entryTestModule(t, "singbox", loadProdSingBoxTemplate(t, name))
-		a := hy2Row()
-		a.Name = "悦·🇸🇬新加坡1"
-		a.Password = regionTestUUID
-		b := checkableRealityServer()
-		b.Name = "悦·🇸🇬新加坡2"
-		b.Password = regionTestUUID
-		ctx := context.WithValue(context.Background(), regionEntryKey{}, regionEntryOptions{enabled: true})
-		data, err := m.renderSingBox(ctx, []*serverRow{a, b})
-		if err != nil {
-			t.Fatal(err)
-		}
-		cfg := map[string]any{}
-		if err = json.Unmarshal(data, &cfg); err != nil {
-			t.Fatal(err)
-		}
-		groups := map[string]map[string]any{}
-		for _, raw := range cfg["outbounds"].([]any) {
-			g := raw.(map[string]any)
-			groups[g["tag"].(string)] = g
-		}
-		canonical := ""
-		for tag, g := range groups {
-			members := regionStrings(g["outbounds"])
-			if len(members) == 2 && members[0] == a.Name && members[1] == b.Name {
-				if canonical != "" {
-					t.Fatal("duplicate regional node selectors")
-				}
-				canonical = tag
-				if g["type"] != "selector" || g["default"] != a.Name {
-					t.Fatal("regional primary default lost")
-				}
-			}
-			for _, member := range members {
-				if groups[member] == nil {
-					t.Fatal("dangling outbound reference")
-				}
-			}
-		}
-		if canonical == "" {
-			t.Fatal("production template lost regional group")
-		}
-		referenced := false
-		for tag, g := range groups {
-			if tag != canonical && strings.Contains(tag, "节点选择") || tag == "Yue · Node Selection" {
-				referenced = referenced || strings.Contains(strings.Join(regionStrings(g["outbounds"]), "|"), canonical)
-			}
-		}
-		// Templates may localize the root label; every canonical region must be
-		// reachable from at least one non-regional parent, regardless of its label.
-		if !referenced {
-			for tag, g := range groups {
-				if tag != canonical {
-					for _, member := range regionStrings(g["outbounds"]) {
-						if member == canonical {
-							referenced = true
-						}
-					}
-				}
-			}
-		}
-		if !referenced {
-			t.Fatal("region is not selectable")
-		}
-	}
-}
-
-func TestRegionStrictNamedSubsetAndServicePolicy(t *testing.T) {
-	a := hy2Row()
-	a.Name = "悦·🇸🇬新加坡1"
-	b := vlessRealityRow()
-	b.Name = "悦·🇸🇬新加坡2"
-	ctx := context.WithValue(context.Background(), regionEntryKey{}, regionEntryOptions{enabled: true})
-	groups := []any{
-		map[string]any{"name": "Proxy", "type": "select", "proxies": []any{"🇸🇬 Direct", a.Name, b.Name}},
-		map[string]any{"name": "🇸🇬 Direct", "type": "url-test", "proxies": []any{a.Name}},
-	}
-	rewrites := map[string]string{}
-	result := applyRegionGroups(ctx, groups, []*serverRow{a, b}, []string{a.Name, b.Name}, false, regionGroupExtras{rewrites: rewrites})
-	if rewrites["🇸🇬 Direct"] != a.Name {
-		t.Fatal("restricted regional policy was widened")
-	}
-	for _, raw := range result {
-		g := raw.(map[string]any)
-		if g["name"] == "Proxy" && len(regionStrings(g["proxies"])) != 1 {
-			t.Fatal("root exposes duplicate region choice")
-		}
-		if g["name"] == "🇸🇬 Direct" {
-			t.Fatal("restricted regional helper remains visible")
-		}
-	}
-	const service = "Service = fallback, Proxy, DIRECT, url=https://example.test/check, interval=60"
-	profile := "[Proxy Group]\nProxy = select, " + a.Name + "\n" + service + "\n[Rule]\nFINAL,Proxy\n"
-	out := applyRegionINI(ctx, profile, []*serverRow{a})
-	if !strings.Contains(out, service+"\n") || strings.Contains(out, "region-ini-original") {
-		t.Fatal("unrelated INI service policy changed")
-	}
-}
-
-func assertRegionOutputUUIDs(t *testing.T, value any) {
-	t.Helper()
-	switch v := value.(type) {
-	case map[string]any:
-		for key, child := range v {
-			if key == "uuid" {
-				text, ok := child.(string)
-				if !ok {
-					t.Fatal("non-string emitted UUID")
-				}
-				parsed, err := uuid.Parse(text)
-				if err != nil || len(text) != 36 || parsed == uuid.Nil || !strings.EqualFold(parsed.String(), text) {
-					t.Fatal("noncanonical emitted UUID")
-				}
-			} else {
-				assertRegionOutputUUIDs(t, child)
-			}
-		}
-	case []any:
-		for _, child := range v {
-			assertRegionOutputUUIDs(t, child)
-		}
-	}
-}
-
-func TestRegionNestedAutomaticSelection(t *testing.T) {
-	for _, singbox := range []bool{false, true} {
-		t.Run(fmt.Sprint(singbox), func(t *testing.T) {
-			a, b := hy2Row(), vlessRealityRow()
-			a.Name, b.Name = "悦·🇸🇬 HY2", "悦·🇸🇬 VLESS"
-			nk, mk, auto, manual := "name", "proxies", "url-test", "select"
-			if singbox {
-				nk, mk, auto, manual = "tag", "outbounds", "urltest", "selector"
-			}
-			groups := []any{
-				map[string]any{nk: "Root", "type": auto, mk: []any{"HY2", "VLESS"}},
-				map[string]any{nk: "HY2", "type": manual, mk: []any{a.Name}},
-				map[string]any{nk: "VLESS", "type": manual, mk: []any{b.Name}},
-				map[string]any{nk: "Service", "type": "fallback", mk: []any{"Root", "DIRECT"}},
-			}
-			ctx := context.WithValue(context.Background(), regionEntryKey{}, regionEntryOptions{enabled: true})
-			for _, raw := range applyRegionGroups(ctx, groups, []*serverRow{a, b}, []string{a.Name, b.Name}, singbox) {
-				g := raw.(map[string]any)
-				if g[nk] == "Root" && g["type"] != manual {
-					t.Fatal("nested protocol choices remain automatic")
-				}
-				if g[nk] == "Service" && g["type"] != "fallback" {
-					t.Fatal("service recovery changed")
-				}
-			}
-		})
-	}
-}
-
-func TestRegionINIDynamicMembership(t *testing.T) {
-	for _, format := range []string{"surge", "surfboard"} {
-		t.Run(format, func(t *testing.T) {
-			a := hy2Row()
-			a.Name = "悦·🇸🇬 Singapore"
-			a.Password = regionTestUUID
-			m := entryTestModule(t, format, "[Proxy]\n$proxies\n[Proxy Group]\nProxy = select, 🇸🇬 Singapore, 🇭🇰 Hong Kong, $proxy_group\n🇸🇬 Singapore = url-test, include-all-proxies=true, policy-regex-filter=🇸🇬, url=https://example.test/check\n🇭🇰 Hong Kong = url-test, include-all-proxies=true, policy-regex-filter=🇭🇰, url=https://example.test/check\n[Rule]\nDOMAIN-SUFFIX,hk.example,🇭🇰 Hong Kong\nFINAL,Proxy\n")
-			ctx := context.WithValue(context.Background(), regionEntryKey{}, regionEntryOptions{enabled: true})
-			r := httptest.NewRequest("GET", "https://sub.example", nil)
-			var body []byte
-			if format == "surge" {
-				body = m.renderSurge(ctx, r, entrySubUser(), []*serverRow{a}, "https://sub.example")
-			} else {
-				body = m.renderSurfboard(ctx, r, entrySubUser(), []*serverRow{a}, "https://sub.example")
-			}
-			text := string(body)
-			if strings.Contains(text, "🇭🇰") || strings.Contains(text, "url-test") || strings.Contains(text, "include-all-proxies") {
-				t.Fatal("dynamic or unavailable region remains")
-			}
-			if !strings.Contains(text, "Proxy = select, 🇸🇬 Singapore\n") || !strings.Contains(text, "🇸🇬 Singapore = select, "+a.Name+"\n") {
-				t.Fatal("region is not the sole manual entry")
-			}
-			if !strings.Contains(text, "DOMAIN-SUFFIX,hk.example,REJECT") {
-				t.Fatal("unavailable region route did not fail closed")
-			}
-		})
-	}
-}
-
-func TestRegionPairedOpsTemplates(t *testing.T) {
-	root := os.Getenv("YUEBOARD_REGION_OPS_TEMPLATES")
-	if root == "" {
-		t.Skip("paired Ops regional templates not supplied")
-	}
-	for _, locale := range []string{"zh", "en"} {
-		for _, format := range []string{"clashmeta", "clash", "stash", "singbox", "surge", "surfboard"} {
-			t.Run(locale+"/"+format, func(t *testing.T) {
-				ext := ".yaml"
-				if format == "singbox" {
-					ext = ".json"
-				} else if format == "surge" || format == "surfboard" {
-					ext = ".conf"
-				}
-				template, err := os.ReadFile(filepath.Join(root, locale, format+ext))
-				if err != nil {
-					t.Fatal(err)
-				}
-				m := entryTestModule(t, format, string(template))
-				m.settings = settings.NewStatic(map[string]string{regionEntrySetting: "1"})
-				a, b := hy2Row(), checkableRealityServer()
-				a.Name, b.Name = "悦·🇸🇬新加坡1", "悦·🇸🇬新加坡2"
-				a.Password, b.Password = regionTestUUID, regionTestUUID
-				flag := format
-				if format == "singbox" {
-					flag = "sing-box"
-				}
-				if format == "clash" {
-					flag = "clash-compatible"
-				}
-				r := httptest.NewRequest("GET", "https://sub.example/s/test?flag="+flag, nil)
-				r.Header.Set("User-Agent", "mihomo/1.19.31")
-				w := httptest.NewRecorder()
-				m.deliver(context.Background(), w, r, entrySubUser(), []*serverRow{a, b}, 0, regionTestUUID, "test")
-				if w.Code != 200 {
-					t.Fatalf("delivery status %d", w.Code)
-				}
-				var groups []any
-				nk, mk, manual, main := "name", "proxies", "select", ""
-				if format == "singbox" {
-					cfg := map[string]any{}
-					if err := json.Unmarshal(w.Body.Bytes(), &cfg); err != nil {
-						t.Fatal(err)
-					}
-					groups = cfg["outbounds"].([]any)
-					nk, mk, manual = "tag", "outbounds", "selector"
-					main = cfg["route"].(map[string]any)["final"].(string)
-				} else if ext == ".yaml" {
-					cfg := map[string]any{}
-					if err := yaml.Unmarshal(w.Body.Bytes(), &cfg); err != nil {
-						t.Fatal(err)
-					}
-					groups = cfg["proxy-groups"].([]any)
-					main = groups[0].(map[string]any)["name"].(string)
-				} else {
-					inGroups := false
-					for _, line := range strings.Split(w.Body.String(), "\n") {
-						line = strings.TrimSpace(line)
-						if strings.HasPrefix(line, "[") {
-							inGroups = line == "[Proxy Group]"
-							continue
-						}
-						if !inGroups || strings.HasPrefix(line, "#") {
-							continue
-						}
-						name, body, ok := strings.Cut(line, "=")
-						if !ok {
-							continue
-						}
-						fields := splitINIGroupParameters(body)
-						members := []any{}
-						for _, f := range fields[1:] {
-							if !strings.Contains(f, "=") {
-								members = append(members, strings.TrimSpace(f))
-							}
-						}
-						groups = append(groups, map[string]any{nk: strings.TrimSpace(name), "type": strings.TrimSpace(fields[0]), mk: members})
-					}
-					main = "Proxy"
-				}
-				canonical := ""
-				for _, raw := range groups {
-					g := raw.(map[string]any)
-					if g[mk] == nil {
-						continue
-					}
-					name := g[nk].(string)
-					region := regionGroupRegion(name)
-					if region != "" {
-						if region != "🇸🇬" {
-							t.Fatalf("unavailable region group %s", name)
-						}
-						if canonical != "" {
-							t.Fatalf("duplicate region groups %s and %s", canonical, name)
-						}
-						canonical = name
-						if g["type"] != manual {
-							t.Fatal("regional group is automatic")
-						}
-						want := 2
-						if ext == ".conf" {
-							want = 1
-						}
-						if len(regionStrings(g[mk])) != want {
-							t.Fatal("supported manual protocol choice lost")
-						}
-					}
-				}
-				if canonical == "" {
-					t.Fatal("missing regional entry")
-				}
-				for _, raw := range groups {
-					g := raw.(map[string]any)
-					if g[nk] != main {
-						continue
-					}
-					count := 0
-					for _, member := range regionStrings(g[mk]) {
-						if member == canonical {
-							count++
-						}
-						if member == a.Name || member == b.Name {
-							t.Fatal("main exposes raw protocol entries")
-						}
-					}
-					if count != 1 {
-						t.Fatal("main does not expose exactly one regional entry")
-					}
-				}
-			})
-		}
-	}
-}
-
-func TestRegionExternalGroupAndINICapability(t *testing.T) {
-	a := hy2Row()
-	a.Name, a.external = "🇭🇰 External node", true
-	ctx := context.WithValue(context.Background(), regionEntryKey{}, regionEntryOptions{enabled: true})
-	groups := []any{map[string]any{"name": "🇭🇰 External", "type": "url-test", "proxies": []any{a.Name}}}
-	got := applyRegionGroups(ctx, groups, []*serverRow{a}, []string{a.Name}, false)
-	if len(got) != 1 || got[0].(map[string]any)["type"] != "url-test" {
-		t.Fatal("third-party policy changed")
-	}
-	a.external, a.Type = false, "vless"
-	profile := "[Proxy Group]\n🇭🇰 = select, " + a.Name + "\n[Rule]\nFINAL,🇭🇰\n"
-	out := applyRegionINI(ctx, profile, []*serverRow{a})
-	if strings.Contains(out, a.Name) || !strings.Contains(out, "FINAL,REJECT") {
-		t.Fatal("INI admitted an unsupported proxy")
-	}
-}
-
-func TestRegionAliasRuleReferences(t *testing.T) {
-	aliases := map[string]string{"🇸🇬 Alias": "🇸🇬 Singapore", "🇸🇬 Restricted": "HY2"}
-	rules := map[string]any{"rules": []any{"DOMAIN,alias.example,🇸🇬 Alias", "IP-CIDR,example,🇸🇬 Restricted,no-resolve"}, "sub-rules": map[string]any{"nested": []any{"MATCH,🇸🇬 Alias"}}}
-	rewriteRegionClashRules(rules, aliases)
-	if rules["rules"].([]any)[0] != "DOMAIN,alias.example,🇸🇬 Singapore" || rules["rules"].([]any)[1] != "IP-CIDR,example,HY2,no-resolve" || rules["sub-rules"].(map[string]any)["nested"].([]any)[0] != "MATCH,🇸🇬 Singapore" {
-		t.Fatal("Clash policy references lost")
-	}
-	cfg := map[string]any{"route": map[string]any{"final": "🇸🇬 Alias", "rules": []any{map[string]any{"outbound": "🇸🇬 Restricted", "domain": []any{"🇸🇬 Alias"}}}}, "dns": map[string]any{"detour": "🇸🇬 Alias"}}
-	rewriteRegionSingBoxRefs(cfg, aliases)
-	route := cfg["route"].(map[string]any)
-	rule := route["rules"].([]any)[0].(map[string]any)
-	if route["final"] != "🇸🇬 Singapore" || rule["outbound"] != "HY2" || rule["domain"].([]any)[0] != "🇸🇬 Alias" || cfg["dns"].(map[string]any)["detour"] != "🇸🇬 Singapore" {
-		t.Fatal("sing-box policy references or predicates changed")
-	}
-}
-
-func TestRegionINIAliasServiceParameters(t *testing.T) {
-	a := hy2Row()
-	a.Name = "悦·🇸🇬 HY2"
-	ctx := context.WithValue(context.Background(), regionEntryKey{}, regionEntryOptions{enabled: true})
-	profile := "[Proxy Group]\n🇸🇬 Primary = select, " + a.Name + "\n🇸🇬 Alias = select, " + a.Name + "\nService = fallback, 🇸🇬 Alias, DIRECT, url=https://example.test/check, interval=60, timeout=5\n[Rule]\nFINAL,Service\n"
-	out := applyRegionINI(ctx, profile, []*serverRow{a})
-	if strings.Contains(out, "🇸🇬 Alias") || !strings.Contains(out, "Service = fallback, 🇸🇬 Primary, DIRECT, url=https://example.test/check, interval=60, timeout=5") {
-		t.Fatal("service alias lost recovery parameters")
-	}
-}
-
-func TestRegionTemplateProxyAvailability(t *testing.T) {
-	ctx := context.WithValue(context.Background(), regionEntryKey{}, regionEntryOptions{enabled: true})
-	groups := []any{map[string]any{"name": "🇭🇰 Custom", "type": "select", "proxies": []any{"static"}}}
-	if got := applyRegionGroups(ctx, groups, nil, nil, false, regionGroupExtras{templateNames: []string{"static"}}); len(got) != 1 {
-		t.Fatal("Clash template proxy group omitted")
-	}
-	groups = []any{map[string]any{"tag": "🇭🇰 Custom", "type": "selector", "outbounds": []any{"static"}}, map[string]any{"tag": "static", "type": "socks"}}
-	if got := applyRegionGroups(ctx, groups, nil, nil, true); len(got) != 2 {
-		t.Fatal("sing-box template proxy group omitted")
-	}
-	groups = []any{map[string]any{"tag": "🇭🇰 Missing", "type": "selector", "outbounds": []any{"unavailable"}}, map[string]any{"tag": "unavailable", "type": "socks", "server": "127.0.0.1", "server_port": 9}}
-	if got := applyRegionGroups(ctx, groups, nil, nil, true); len(got) != 1 || got[0].(map[string]any)["tag"] != "unavailable" {
-		t.Fatal("notice makes missing region available")
-	}
-}

codex
- No blocking correctness or security issues identified in the specified diff.
- Changes match the stated intent: one entry per server, removing A/B expansion, region merging, and CDN canaries.
- Nonblocking coverage loss: replacement renderer tests omit the previous exact salted-host assertions and invalid-row rejection checks across all formats.
- Static review only; tests were not run.

VERDICT: approve
tokens used
67,647
- No blocking correctness or security issues identified in the specified diff.
- Changes match the stated intent: one entry per server, removing A/B expansion, region merging, and CDN canaries.
- Nonblocking coverage loss: replacement renderer tests omit the previous exact salted-host assertions and invalid-row rejection checks across all formats.
- Static review only; tests were not run.

VERDICT: approve
Finished: 2026-11-05T03:07:08Z exit=0
