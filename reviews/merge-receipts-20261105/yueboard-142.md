# yueboard #142 review at 2b2acde3ad635c627ddfef68ec51bf29a5c48c42

Reviewed range: 5fbad75602a85bd21c37b73e9b8421d8c6bbfd56..2b2acde3ad635c627ddfef68ec51bf29a5c48c42 (post-merge backfill; codex on mac-5f08d00f, read-only sandbox)
Started: 2026-11-05T03:05:06Z

Reading additional input from stdin...
OpenAI Codex v0.166.0
--------
workdir: /Users/j/codex-runs/mh1105/yb-142
model: gpt-6-astra
provider: openai
approval: never
sandbox: read-only
reasoning effort: medium
reasoning summaries: none
session id: 01a1a9aa-d1b9-7441-98db-a4c46235e9ac
--------
user
You are reviewing merged PR onesyue/yueboard #142 at exact head 2b2acde3ad635c627ddfef68ec51bf29a5c48c42. Review ONLY the diff: git diff 5fbad75602a85bd21c37b73e9b8421d8c6bbfd56 2b2acde3ad635c627ddfef68ec51bf29a5c48c42 (and git log 5fbad75602a85bd21c37b73e9b8421d8c6bbfd56..2b2acde3ad635c627ddfef68ec51bf29a5c48c42). Do not modify files. Check correctness, regressions, weakened/removed tests, security, and that the change matches its title/intent. Output a final line exactly 'VERDICT: approve' or 'VERDICT: changes' followed by concise bullet findings.
2026-11-05T03:05:11.706616Z ERROR codex_models_manager::manager: failed to refresh available models: request timed out
codex
I’ll read the repository review instructions, then inspect only the specified diff and commit log. I won’t modify files.
exec
/bin/zsh -lc 'pwd; cat CLAUDE.md; git log --oneline 5fbad75602a85bd21c37b73e9b8421d8c6bbfd56..2b2acde3ad635c627ddfef68ec51bf29a5c48c42; git diff --stat 5fbad75602a85bd21c37b73e9b8421d8c6bbfd56 2b2acde3ad635c627ddfef68ec51bf29a5c48c42' in /Users/j/codex-runs/mh1105/yb-142
 succeeded in 0ms:
/Users/j/codex-runs/mh1105/yb-142
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
2b2acde3 N8: 订阅节点显示名简化（地区+序号+协议+倍率原样），选择仍按原名
 internal/modules/subscribe/display_name.go      | 549 ++++++++++++++++++++++++
 internal/modules/subscribe/display_name_test.go | 444 +++++++++++++++++++
 internal/modules/subscribe/general.go           |   1 +
 internal/modules/subscribe/loon.go              |   1 +
 internal/modules/subscribe/proxies.go           |   2 +
 internal/modules/subscribe/quantumultx.go       |   1 +
 internal/modules/subscribe/singbox.go           |   1 +
 internal/modules/subscribe/subscribe.go         |   2 +
 internal/modules/subscribe/subscribe_clash.go   |  21 +
 internal/modules/subscribe/surfboard.go         |   1 +
 internal/modules/subscribe/surge.go             |   1 +
 11 files changed, 1024 insertions(+)

exec
/bin/zsh -lc 'for f in ../AGENTS.md ../CLAUDE.md; do if test -f "$f"; then cat "$f"; fi; done; git log --format=fuller 5fbad75602a85bd21c37b73e9b8421d8c6bbfd56..2b2acde3ad635c627ddfef68ec51bf29a5c48c42; git diff 5fbad75602a85bd21c37b73e9b8421d8c6bbfd56 2b2acde3ad635c627ddfef68ec51bf29a5c48c42 -- internal/modules/subscribe/display_name.go' in /Users/j/codex-runs/mh1105/yb-142
 succeeded in 0ms:
commit 2b2acde3ad635c627ddfef68ec51bf29a5c48c42
Author:     onesyue <47652916+onesyue@users.noreply.github.com>
AuthorDate: Thu Nov 5 03:38:18 2026 +0800
Commit:     onesyue <47652916+onesyue@users.noreply.github.com>
CommitDate: Thu Nov 5 03:38:18 2026 +0800

    N8: 订阅节点显示名简化（地区+序号+协议+倍率原样），选择仍按原名
diff --git a/internal/modules/subscribe/display_name.go b/internal/modules/subscribe/display_name.go
new file mode 100644
index 00000000..58d440c8
--- /dev/null
+++ b/internal/modules/subscribe/display_name.go
@@ -0,0 +1,549 @@
+package subscribe
+
+import (
+	"fmt"
+	"regexp"
+	"regexp/syntax"
+	"strings"
+	"unicode"
+	"unicode/utf8"
+)
+
+// Order breaks equal-position ties only when they identify the same region.
+// Empty labels deliberately mark ambiguous geographical tokens.
+var displayRegions = []struct {
+	region string
+	tokens []string
+}{
+	{"香港", []string{"🇭🇰", "香港", "Hong Kong", "HongKong", "HK"}},
+	{"台湾", []string{"🇹🇼", "台湾", "台灣", "台北", "Taiwan", "Taipei", "TW"}},
+	{"日本", []string{"🇯🇵", "日本", "东京", "東京", "大阪", "Japan", "Tokyo", "Osaka", "JP"}},
+	{"新加坡", []string{"🇸🇬", "新加坡", "狮城", "Singapore", "SG"}},
+	{"美国", []string{"🇺🇸", "美国", "美國", "洛杉矶", "纽约", "西雅图", "圣何塞", "United States", "USA", "US", "Los Angeles", "New York", "Seattle", "San Jose"}},
+	{"韩国", []string{"🇰🇷", "韩国", "韓國", "首尔", "Seoul", "South Korea", "KR"}},
+	{"英国", []string{"🇬🇧", "英国", "英國", "伦敦", "United Kingdom", "London", "UK", "GB"}},
+	{"德国", []string{"🇩🇪", "德国", "德國", "法兰克福", "Germany", "Frankfurt", "DE"}},
+	{"法国", []string{"🇫🇷", "法国", "法國", "巴黎", "France", "Paris", "FR"}},
+	{"加拿大", []string{"🇨🇦", "加拿大", "多伦多", "温哥华", "Canada", "Toronto", "Vancouver", "CA"}},
+	{"澳大利亚", []string{"🇦🇺", "澳大利亚", "悉尼", "墨尔本", "Australia", "Sydney", "Melbourne", "AU"}},
+	{"荷兰", []string{"🇳🇱", "荷兰", "阿姆斯特丹", "Netherlands", "Amsterdam", "NL"}},
+	{"印度", []string{"🇮🇳", "印度", "孟买", "India", "Mumbai", "IN"}},
+	{"", []string{"Korea", "刚果", "Congo", "Georgia", "圣何塞", "San Jose"}},
+}
+
+func displayRegion(name string) string {
+	lower := strings.ToLower(name)
+	position, region := len(lower)+1, ""
+	ambiguous := false
+	for _, entry := range displayRegions {
+		for _, token := range entry.tokens {
+			token = strings.ToLower(token)
+			offset := 0
+			for offset <= len(lower) {
+				index := strings.Index(lower[offset:], token)
+				if index < 0 {
+					break
+				}
+				index += offset
+				end := index + len(token)
+				// Latin aliases are whole tokens, with optional numeric node suffixes.
+				latin := token[0] < utf8.RuneSelf
+				before, _ := utf8.DecodeLastRuneInString(lower[:index])
+				after, _ := utf8.DecodeRuneInString(lower[end:])
+				bounded := !latin || (!unicode.IsLetter(before) && !unicode.IsLetter(after))
+				if bounded && index <= position {
+					if index < position {
+						position, region, ambiguous = index, entry.region, entry.region == ""
+					} else if region != entry.region {
+						ambiguous = true
+					}
+				}
+				offset = end
+			}
+		}
+	}
+	// An earlier unrecognized flag is evidence of an unknown region, not
+	// permission to use a later transit/destination token.
+	for index, r := range lower {
+		if r >= '\U0001F1E6' && r <= '\U0001F1FF' && index < position {
+			return ""
+		}
+	}
+	if ambiguous {
+		return ""
+	}
+	return region
+}
+
+// Copy the complete multiplier spelling, including brackets and internal spaces.
+// Never derive, round, or normalize a billing value here.
+var displayMultiplier = regexp.MustCompile(`(?i)(?:[\[【(（][ \t]*)?(?:倍率[ \t]*[:：=]?[ \t]*[0-9]+(?:\.[0-9]+)?|[x×✕*][ \t]*[0-9]+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?(?:[ \t]*倍(?:率)?|[x×✕*]))(?:[ \t]*[\]】)）])?`)
+
+func prepareDisplayNames(servers []*serverRow) {
+	ordinals := map[string]int{}
+	for _, s := range servers {
+		if s == nil || s.placeholder || isSubscriptionNoticeName(s.Name) {
+			continue
+		}
+		region := displayRegion(s.Name)
+		protocol := map[string]string{"vless": "VLESS", "hysteria": "Hysteria2"}[s.Type]
+		if region == "" || protocol == "" {
+			continue
+		}
+		ordinals[region]++
+		multipliers, safe := displayMultipliers(s.Name)
+		if !safe {
+			continue
+		}
+		s.DisplayName = fmt.Sprintf("%s %02d %s", region, ordinals[region], protocol)
+		for _, text := range multipliers {
+			s.DisplayName += " " + text
+		}
+	}
+}
+
+// Used only by renderers without name-dependent template selection.
+func displayRows(servers []*serverRow) []*serverRow {
+	rows := make([]*serverRow, 0, len(servers))
+	for _, s := range servers {
+		if s == nil {
+			continue
+		}
+		copy := *s
+		if copy.DisplayName != "" {
+			copy.Name = copy.DisplayName
+		}
+		rows = append(rows, &copy)
+	}
+	return rows
+}
+
+// Allocate names simultaneously, reserving every unchanged identity. This also
+// prevents a renamed node from shadowing an original name used by a template.
+func displayAliases(rows []*serverRow, originals, reserved []string, key func(string) string) map[string]string {
+	proposed := make([]string, len(originals))
+	reserved = append([]string{}, reserved...)
+	for i, name := range originals {
+		proposed[i] = name
+		if rows[i].DisplayName == "" || rows[i].DisplayName == name {
+			reserved = append(reserved, name)
+		}
+	}
+	changing, indexes := []string{}, []int{}
+	for i := range originals {
+		if rows[i].DisplayName != "" && rows[i].DisplayName != originals[i] {
+			name := rows[i].DisplayName
+			if key != nil {
+				name = key(name)
+			}
+			changing = append(changing, name)
+			indexes = append(indexes, i)
+		}
+	}
+	for i, name := range uniqueNames(changing, reserved, key) {
+		proposed[indexes[i]] = name
+	}
+	aliases := map[string]string{}
+	for i, name := range originals {
+		if proposed[i] != name {
+			aliases[name] = proposed[i]
+		}
+	}
+	return aliases
+}
+
+func displayAlias(name string, aliases map[string]string) string {
+	if renamed, ok := aliases[name]; ok {
+		return renamed
+	}
+	return name
+}
+
+// Reference-only traversal; passwords, endpoints, expressions and group names
+// are not identities and must never be subjected to string replacement.
+func rewriteDisplayReferences(value any, aliases map[string]string) {
+	switch v := value.(type) {
+	case map[string]any:
+		for key, child := range v {
+			switch key {
+			case "default", "final", "outbound", "detour", "download_detour", "dialer-proxy":
+				if name, ok := child.(string); ok {
+					v[key] = displayAlias(name, aliases)
+				}
+			case "proxies", "outbounds":
+				if list, ok := child.([]any); ok {
+					for i, item := range list {
+						if name, ok := item.(string); ok {
+							list[i] = displayAlias(name, aliases)
+						} else {
+							rewriteDisplayReferences(item, aliases)
+						}
+					}
+				}
+			case "sub-rules":
+				if sub, ok := child.(map[string]any); ok {
+					for name, rules := range sub {
+						wrapper := map[string]any{"rules": rules}
+						rewriteDisplayReferences(wrapper, aliases)
+						sub[name] = wrapper["rules"]
+					}
+				}
+			case "rules":
+				if list, ok := child.([]any); ok {
+					for i, item := range list {
+						if rule, ok := item.(string); ok {
+							if strings.HasPrefix(strings.TrimSpace(rule), "SUB-RULE,") {
+								continue
+							}
+							parts := strings.Split(rule, ",")
+							target := len(parts) - 1
+							if target > 0 && strings.TrimSpace(parts[target]) == "no-resolve" {
+								target--
+							}
+							if target > 0 {
+								parts[target] = displayAlias(strings.TrimSpace(parts[target]), aliases)
+								list[i] = strings.Join(parts, ",")
+							}
+						} else {
+							rewriteDisplayReferences(item, aliases)
+						}
+					}
+				}
+			default:
+				rewriteDisplayReferences(child, aliases)
+			}
+		}
+	case []any:
+		for _, child := range v {
+			rewriteDisplayReferences(child, aliases)
+		}
+	}
+}
+
+// Resolve a runtime regex against the original finite identity set. Use a
+// never-matching expression for the empty set, not an empty (match-all) filter.
+func displayFilter(pattern string, names []string, aliases map[string]string) string {
+	matches := []string{}
+	matcher, err := nativeDisplayMatcher(pattern)
+	if err != nil {
+		return pattern
+	}
+	for _, name := range names {
+		if matcher.match(name) {
+			matches = append(matches, regexp.QuoteMeta(displayAlias(name, aliases)))
+		}
+	}
+	if len(matches) == 0 {
+		return "a^"
+	}
+	return "^(?:" + strings.Join(matches, "|") + ")$"
+}
+
+func applySingBoxDisplayNames(cfg map[string]any, proxies []map[string]any, rows []*serverRow) {
+	originals, reserved := []string{}, []string{}
+	for _, p := range proxies {
+		originals = append(originals, p["tag"].(string))
+	}
+	for _, section := range []string{"outbounds", "endpoints"} {
+		items, _ := cfg[section].([]any)
+		for _, item := range items {
+			if obj, ok := item.(map[string]any); ok {
+				if tag, ok := obj["tag"].(string); ok {
+					reserved = append(reserved, tag)
+				}
+			}
+		}
+	}
+	aliases := displayAliases(rows, originals, reserved, nil)
+	for _, p := range proxies {
+		p["tag"] = displayAlias(p["tag"].(string), aliases)
+	}
+	rewriteDisplayReferences(cfg, aliases)
+}
+
+func applyClashDisplayNames(cfg map[string]any, proxies []any, rows []*serverRow) {
+	originals, reserved := []string{}, clashGroupNames(cfg["proxy-groups"])
+	reserved = append(reserved, clashReservedProxyNames...)
+	all, _ := cfg["proxies"].([]any)
+	reserved = append(reserved, clashTemplateProxyNames(all)...)
+	for _, p := range proxies[:len(rows)] {
+		originals = append(originals, p.(map[string]any)["name"].(string))
+	}
+	aliases := displayAliases(rows, originals, reserved, nil)
+	if len(aliases) == 0 {
+		return
+	}
+	groups, _ := cfg["proxy-groups"].([]any)
+	// External providers can introduce unknown names after rendering. Retain
+	// identities for this template rather than change their regex membership.
+	if providers, ok := cfg["proxy-providers"].(map[string]any); ok && len(providers) > 0 {
+		for _, item := range groups {
+			if g, ok := item.(map[string]any); ok && (g["filter"] != nil || g["exclude-filter"] != nil) {
+				return
+			}
+		}
+	}
+	candidates := append(clashTemplateProxyNames(all), clashGroupNames(cfg["proxy-groups"])...)
+	candidates = append(candidates, clashReservedProxyNames...)
+	// A native expression outside the server matcher's supported grammar must
+	// keep the original identities rather than silently become an empty set.
+	for _, item := range groups {
+		if g, ok := item.(map[string]any); ok {
+			for _, field := range []string{"filter", "exclude-filter"} {
+				if pattern, ok := g[field].(string); ok && pattern != "" {
+					if _, err := nativeDisplayMatcher(pattern); err != nil {
+						return
+					}
+				}
+			}
+		}
+	}
+	for _, item := range groups {
+		if g, ok := item.(map[string]any); ok {
+			for _, field := range []string{"filter", "exclude-filter"} {
+				if pattern, ok := g[field].(string); ok && pattern != "" {
+					g[field] = displayFilter(pattern, candidates, aliases)
+				}
+			}
+		}
+	}
+	for _, p := range proxies[:len(rows)] {
+		obj := p.(map[string]any)
+		obj["name"] = displayAlias(obj["name"].(string), aliases)
+	}
+	rewriteDisplayReferences(cfg, aliases)
+}
+
+func applyINIDisplayNames(profile string, rows []*serverRow) string {
+	emitted, originals := []*serverRow{}, []string{}
+	for _, s := range rows {
+		if s.Type == "hysteria" && surgeHysteria(s) != "" {
+			emitted = append(emitted, s)
+			originals = append(originals, iniFamilyNameKey(s.Name))
+		}
+	}
+	reserved := append(append([]string{}, iniFamilyBuiltinPolicies...), iniTemplatePolicyNames(profile)...)
+	aliases := displayAliases(emitted, originals, reserved, iniFamilyNameKey)
+	if len(aliases) == 0 {
+		return profile
+	}
+	lines := strings.Split(profile, "\n")
+	// Remote policy files can change after this response. Their runtime filter
+	// cannot be reduced to the locally known identity set.
+	section := ""
+	for _, line := range lines {
+		trimmed := strings.TrimSpace(line)
+		if strings.HasPrefix(trimmed, "[") {
+			section = strings.ToLower(trimmed)
+			continue
+		}
+		if section != "[proxy group]" {
+			continue
+		}
+		_, rest, ok := strings.Cut(line, "=")
+		if !ok {
+			continue
+		}
+		for _, token := range splitINIGroupParameters(rest) {
+			key, value, _ := strings.Cut(strings.TrimSpace(token), "=")
+			switch strings.TrimSpace(key) {
+			case "policy-path":
+				return profile
+			case "policy-regex-filter":
+				if _, err := nativeDisplayMatcher(iniDisplayPattern(value)); err != nil {
+					return profile
+				}
+			}
+		}
+	}
+	section = ""
+	for i, line := range lines {
+		trimmed := strings.TrimSpace(line)
+		if strings.HasPrefix(trimmed, "[") {
+			section = strings.ToLower(trimmed)
+			continue
+		}
+		if trimmed == "" || strings.HasPrefix(trimmed, "#") || strings.HasPrefix(trimmed, ";") || strings.HasPrefix(trimmed, "//") {
+			continue
+		}
+		switch section {
+		case "[proxy]":
+			name, rest, ok := strings.Cut(line, "=")
+			if ok {
+				lines[i] = displayAlias(strings.TrimSpace(name), aliases) + " =" + rest
+			}
+		case "[proxy group]":
+			name, rest, ok := strings.Cut(line, "=")
+			if !ok {
+				continue
+			}
+			parts := splitINIGroupParameters(rest)
+			for j := 1; j < len(parts); j++ {
+				token := strings.TrimSpace(parts[j])
+				key, value, parameter := strings.Cut(token, "=")
+				if strings.TrimSpace(key) == "policy-regex-filter" {
+					parts[j] = "policy-regex-filter=" + displayFilter(iniDisplayPattern(value), reserved, aliases)
+				} else if !parameter {
+					parts[j] = displayAlias(token, aliases)
+				}
+			}
+			lines[i] = name + "=" + strings.Join(parts, ", ")
+		case "[rule]":
+			parts := strings.Split(line, ",")
+			target := len(parts) - 1
+			if target > 0 && strings.TrimSpace(parts[target]) == "no-resolve" {
+				target--
+			}
+			if target > 0 {
+				parts[target] = displayAlias(strings.TrimSpace(parts[target]), aliases)
+				lines[i] = strings.Join(parts, ",")
+			}
+		}
+	}
+	return strings.Join(lines, "\n")
+}
+
+func hasDisplayNames(rows []*serverRow) bool {
+	for _, s := range rows {
+		if s.DisplayName != "" {
+			return true
+		}
+	}
+	return false
+}
+
+func iniDisplayPattern(value string) string {
+	value = strings.TrimSpace(value)
+	if len(value) >= 2 && (value[0] == '"' || value[0] == '\'') && value[len(value)-1] == value[0] {
+		return value[1 : len(value)-1]
+	}
+	return value
+}
+
+// Preserve whole bracketed expressions, including annotations such as
+// "[倍率:1.5x]". Unrecognized/partial rate syntax keeps the original name.
+func displayMultipliers(name string) ([]string, bool) {
+	spans := displayMultiplier.FindAllStringIndex(name, -1)
+	brackets := map[rune]rune{'[': ']', '【': '】', '(': ')', '（': '）'}
+	for i, span := range spans {
+		start, end := span[0], span[1]
+		if start > 0 && strings.ContainsRune(".,+-/", rune(name[start-1])) {
+			return nil, false
+		}
+		for pos, opener := range name[:end] {
+			closer, ok := brackets[opener]
+			if !ok || pos > start {
+				continue
+			}
+			tail := pos + utf8.RuneLen(opener)
+			closing := strings.IndexRune(name[tail:], closer)
+			if closing < 0 {
+				return nil, false
+			}
+			closing += tail + utf8.RuneLen(closer)
+			if closing >= end {
+				start, end = pos, closing
+				break
+			}
+		}
+		if end < len(name) {
+			r, _ := utf8.DecodeRuneInString(name[end:])
+			if unicode.IsLetter(r) || unicode.IsDigit(r) || strings.ContainsRune("./%", r) {
+				return nil, false
+			}
+		}
+		spans[i] = []int{start, end}
+	}
+	result := []string{}
+	remaining := strings.Builder{}
+	previous := 0
+	for _, span := range spans {
+		if span[0] < previous {
+			continue
+		}
+		remaining.WriteString(name[previous:span[0]])
+		result = append(result, name[span[0]:span[1]])
+		previous = span[1]
+	}
+	remaining.WriteString(name[previous:])
+	if strings.ContainsAny(remaining.String(), "倍×✕") {
+		return nil, false
+	}
+	return result, true
+}
+
+// Native client filters are case-sensitive unless they explicitly opt into i.
+// Board's template matcher intentionally defaults to i and is not suitable here.
+func nativeDisplayMatcher(pattern string) (*sbMatcher, error) {
+	if re, err := regexp.Compile(pattern); err == nil {
+		return &sbMatcher{pos: re}, nil
+	}
+	if displayMultilineFlag.MatchString(pattern) {
+		return nil, fmt.Errorf("unsupported multiline display filter")
+	}
+	body, flags := pattern, ""
+	for strings.HasPrefix(body, "(?") {
+		end := strings.IndexByte(body, ')')
+		if end < 0 {
+			break
+		}
+		option := body[2:end]
+		if option == "" || strings.Trim(option, "imsU-") != "" {
+			break
+		}
+		flags += body[:end+1]
+		body = body[end+1:]
+	}
+	// Only leading anchored negative assertions are supported. Other native
+	// syntax retains the original names, without guessing at its semantics.
+	if !strings.HasPrefix(body, "^(?!") {
+		return nil, fmt.Errorf("unsupported native display filter")
+	}
+	rest := body[1:]
+	negatives := []string{}
+	for strings.HasPrefix(rest, "(?!") {
+		depth, end := 1, 3
+		for ; end < len(rest) && depth > 0; end++ {
+			switch rest[end] {
+			case '\\':
+				end++
+			case '(':
+				depth++
+			case ')':
+				depth--
+			}
+		}
+		if depth != 0 {
+			return nil, fmt.Errorf("unclosed native display filter")
+		}
+		negatives = append(negatives, rest[3:end-1])
+		rest = rest[end:]
+	}
+	tree, err := syntax.Parse(flags+"^"+rest, syntax.Perl)
+	if err != nil {
+		return nil, err
+	}
+	if tree.Op == syntax.OpAlternate {
+		return nil, fmt.Errorf("unsupported alternating display filter")
+	}
+	matcher := &sbMatcher{}
+	for _, negative := range negatives {
+		if negative == "" {
+			matcher.never = true
+			continue
+		}
+		re, err := regexp.Compile(flags + "^(?:" + negative + ")")
+		if err != nil {
+			return nil, err
+		}
+		matcher.neg = append(matcher.neg, re)
+	}
+	re, err := regexp.Compile(flags + "^" + rest)
+	if err != nil {
+		return nil, err
+	}
+	matcher.pos = re
+	return matcher, nil
+}
+
+var displayMultilineFlag = regexp.MustCompile(`\(\?[imsU-]*m`)

exec
/bin/zsh -lc "git diff 5fbad75602a85bd21c37b73e9b8421d8c6bbfd56 2b2acde3ad635c627ddfef68ec51bf29a5c48c42 -- . ':"'!internal/modules/subscribe/display_name.go'"'" in /Users/j/codex-runs/mh1105/yb-142
 succeeded in 0ms:
diff --git a/internal/modules/subscribe/display_name_test.go b/internal/modules/subscribe/display_name_test.go
new file mode 100644
index 00000000..0dfe179b
--- /dev/null
+++ b/internal/modules/subscribe/display_name_test.go
@@ -0,0 +1,444 @@
+package subscribe
+
+import (
+	"context"
+	"encoding/base64"
+	"encoding/json"
+	"net/http/httptest"
+	"net/url"
+	"reflect"
+	"regexp"
+	"strings"
+	"testing"
+
+	"go.yaml.in/yaml/v3"
+)
+
+func TestDisplayRegion(t *testing.T) {
+	for _, tc := range []struct{ name, want string }{
+		{"🇺🇸 美国 AI解锁 Reality x1.5", "美国"}, {"HK01 CDN", "香港"}, {"jp-02 IPLC", "日本"},
+		{"SG relay", "新加坡"}, {"TW 台北", "台湾"}, {"大阪", "日本"}, {"Los Angeles", "美国"},
+		{"香港 日本", "香港"}, {"日本 HK", "日本"}, {"🇧🇷 US", ""}, {"unlisted", ""}, {"RUSH", ""},
+		{"Korea", ""}, {"San Jose", ""}, {"🇺🇸 San Jose", "美国"}, {"🇨🇬 Congo US", ""},
+		{"Tokyo to Singapore", "日本"}, {"United States", "美国"},
+	} {
+		t.Run(tc.name, func(t *testing.T) {
+			if got := displayRegion(tc.name); got != tc.want {
+				t.Fatalf("got %q want %q", got, tc.want)
+			}
+		})
+	}
+}
+
+func TestDisplayNamesNumberingAndMultiplier(t *testing.T) {
+	rows := []*serverRow{
+		{ID: 9, Name: "美国 AI解锁 Reality [x1.50]", Type: "vless"},
+		{ID: 2, Name: "香港 CDN 【2.00倍】", Type: "hysteria"},
+		{ID: 1, Name: "US relay (× 0.50)", Type: "hysteria"},
+		{Name: "Korea x2", Type: "vless"}, {Name: "Unknown x3", Type: "vless"},
+	}
+	originals := []string{}
+	for _, row := range rows {
+		originals = append(originals, row.Name)
+	}
+	prepareDisplayNames(rows)
+	for i, prefix := range []string{"美国 01 VLESS", "香港 01 Hysteria2", "美国 02 Hysteria2"} {
+		if !strings.HasPrefix(rows[i].DisplayName, prefix) {
+			t.Fatalf("ordinal/protocol: %q", rows[i].DisplayName)
+		}
+		if rows[i].Name != originals[i] {
+			t.Fatal("source changed")
+		}
+	}
+	for i, multiplier := range []string{"[x1.50]", "【2.00倍】", "(× 0.50)"} {
+		if !strings.HasSuffix(rows[i].DisplayName, multiplier) {
+			t.Fatalf("multiplier changed: %q", rows[i].DisplayName)
+		}
+	}
+	for _, row := range rows[3:] {
+		if row.DisplayName != "" {
+			t.Fatal("unknown/ambiguous renamed")
+		}
+	}
+	filtered := filterServers(rows, nil, parseFilter("relay"))
+	if len(filtered) != 1 || filtered[0].DisplayName != rows[2].DisplayName {
+		t.Fatal("filter changed or ordinal reassigned")
+	}
+	if got := filterServers(rows, nil, parseFilter("AI解锁")); len(got) != 1 || got[0] != rows[0] {
+		t.Fatal("original-name filter changed")
+	}
+	for _, multiplier := range []string{"x1.5", "X 1.500", "×0.25", "2 倍", "[ 0.50x ]", "【3倍率】", "[倍率：1.50]"} {
+		row := &serverRow{Name: "JP Reality " + multiplier, Type: "vless"}
+		prepareDisplayNames([]*serverRow{row})
+		if !strings.HasSuffix(row.DisplayName, multiplier) {
+			t.Fatalf("lost exact multiplier %q: %q", multiplier, row.DisplayName)
+		}
+	}
+}
+
+func displayTestRows() []*serverRow {
+	a, b, c, d := realityServer(), realityServer(), hy2Server(), hy2Server()
+	a.Name, b.Name, c.Name, d.Name = "美国 AI解锁 Reality x1.5", "美国 Reality x1.0", "美国 AI解锁 HY2 x2.0", "美国 HY2 x3.0"
+	a.ID, b.ID, c.ID, d.ID = 1, 2, 3, 4
+	a.Host, b.Host, c.Host, d.Host = "a.example.test", "b.example.test", "c.example.test", "d.example.test"
+	return []*serverRow{a, b, c, d}
+}
+
+func TestDisplayNamesRendererSelectionAndReferences(t *testing.T) {
+	const pattern = `(?i)^(?!.*AI).*(🇺🇸|美国)`
+	const clash = `proxies: []
+proxy-groups:
+  - {name: All, type: select, proxies: []}
+  - {name: US, type: select, proxies: ['/(?i)^(?!.*AI).*(🇺🇸|美国)/']}
+  - {name: Native, type: select, proxies: [], filter: '美国', exclude-filter: '(?i)AI'}
+rules: [MATCH,All]
+`
+	const sb = `{"outbounds":[{"tag":"direct","type":"direct"},{"tag":"All","type":"selector"},{"tag":"US","type":"selector","include":"(?i)^(?!.*AI).*(🇺🇸|美国)","exclude":"AI"}],"route":{"final":"All"}}`
+	const ini = `[Proxy]
+$proxies
+[Proxy Group]
+All = select, $proxy_group
+US = select, $proxy_group, policy-regex-filter=(?i)^(?!.*AI).*(🇺🇸|美国)
+[Rule]
+FINAL,All
+`
+	for _, format := range []string{"clashmeta", "clash", "stash", "singbox", "surge", "surfboard", "loon", "quantumultx", "general"} {
+		t.Run(format, func(t *testing.T) {
+			template := clash
+			if format == "singbox" {
+				template = sb
+			}
+			if format == "surge" || format == "surfboard" {
+				template = ini
+			}
+			m := entryTestModule(t, format, template)
+			render := func(rows []*serverRow) []byte {
+				t.Helper()
+				ctx := context.Background()
+				var out []byte
+				var err error
+				switch format {
+				case "singbox":
+					out, err = m.renderSingBox(ctx, rows)
+				case "clashmeta", "clash", "stash":
+					out, err = m.renderClashMeta(ctx, "", &subUser{}, rows, 0, format, false, false, connTagScope{})
+				case "surge":
+					out = m.renderSurge(ctx, httptest.NewRequest("GET", "https://example.test", nil), &subUser{}, rows, "https://example.test/sub")
+				case "surfboard":
+					out = m.renderSurfboard(ctx, httptest.NewRequest("GET", "https://example.test", nil), &subUser{}, rows, "https://example.test/sub")
+				case "loon":
+					out = m.renderLoon(rows)
+				case "quantumultx":
+					out = m.renderQuantumultX(rows)
+				case "general":
+					out = m.renderGeneral(rows)
+				}
+				if err != nil {
+					t.Fatal(err)
+				}
+				return out
+			}
+			beforeRows, afterRows := displayTestRows(), displayTestRows()
+			prepareDisplayNames(afterRows)
+			before, after := render(beforeRows), render(afterRows)
+			aliases := map[string]string{}
+			for _, r := range afterRows {
+				aliases[r.DisplayName] = r.Name
+			}
+			switch format {
+			case "clashmeta", "clash", "stash", "singbox":
+				decode := func(raw []byte) map[string]any {
+					cfg := map[string]any{}
+					var err error
+					if format == "singbox" {
+						err = json.Unmarshal(raw, &cfg)
+					} else {
+						err = yaml.Unmarshal(raw, &cfg)
+					}
+					if err != nil {
+						t.Fatal(err)
+					}
+					return cfg
+				}
+				b, a := decode(before), decode(after)
+				listKey, nameKey, groupKey, memberKey := "proxies", "name", "proxy-groups", "proxies"
+				if format == "singbox" {
+					listKey, nameKey, groupKey, memberKey = "outbounds", "tag", "outbounds", "outbounds"
+				}
+				live := map[string]bool{"DIRECT": true, "REJECT": true}
+				for _, key := range []string{listKey, groupKey} {
+					items, _ := a[key].([]any)
+					for _, item := range items {
+						obj := item.(map[string]any)
+						name, _ := obj[nameKey].(string)
+						live[name] = true
+					}
+				}
+				for _, item := range a[groupKey].([]any) {
+					obj := item.(map[string]any)
+					members, _ := obj[memberKey].([]any)
+					for _, member := range members {
+						if !live[member.(string)] {
+							t.Fatalf("dangling group reference %q", member)
+						}
+					}
+				}
+				members := func(cfg map[string]any) map[string][]string {
+					result := map[string][]string{}
+					for _, item := range cfg[groupKey].([]any) {
+						obj := item.(map[string]any)
+						group, _ := obj[nameKey].(string)
+						list, _ := obj[memberKey].([]any)
+						for _, v := range list {
+							name := v.(string)
+							if inc, _ := obj["filter"].(string); inc != "" && !matchRegex("/"+inc+"/", name) {
+								continue
+							}
+							if exc, _ := obj["exclude-filter"].(string); exc != "" && matchRegex("/"+exc+"/", name) {
+								continue
+							}
+							result[group] = append(result[group], displayAlias(name, aliases))
+						}
+					}
+					return result
+				}
+				if !reflect.DeepEqual(members(b), members(a)) {
+					t.Fatalf("membership changed: before=%v after=%v", members(b), members(a))
+				}
+				// Restore names only, then compare connection fields and rule references.
+				for _, item := range a[listKey].([]any) {
+					obj := item.(map[string]any)
+					obj[nameKey] = displayAlias(obj[nameKey].(string), aliases)
+				}
+				rewriteDisplayReferences(a, aliases)
+				if !reflect.DeepEqual(b[listKey], a[listKey]) {
+					t.Fatal("proxy fields or outbound membership changed")
+				}
+			case "surge", "surfboard":
+				names := []string{}
+				for _, r := range beforeRows {
+					if r.Type == "hysteria" {
+						names = append(names, r.Name)
+					}
+				}
+				for _, raw := range []string{string(before), string(after)} {
+					live := map[string]bool{}
+					section := ""
+					for _, line := range strings.Split(raw, "\n") {
+						if strings.HasPrefix(line, "[") {
+							section = line
+							continue
+						}
+						name, rest, ok := strings.Cut(line, "=")
+						if !ok {
+							continue
+						}
+						if section == "[Proxy]" {
+							live[strings.TrimSpace(name)] = true
+						}
+						if section != "[Proxy Group]" {
+							continue
+						}
+						parts := splitINIGroupParameters(rest)
+						filter := ""
+						actual := []string{}
+						for _, part := range parts[1:] {
+							part = strings.TrimSpace(part)
+							if strings.HasPrefix(part, "policy-regex-filter=") {
+								filter = strings.TrimPrefix(part, "policy-regex-filter=")
+							} else if !strings.Contains(part, "=") {
+								if !live[part] {
+									t.Fatalf("dangling INI member %q", part)
+								}
+								actual = append(actual, part)
+							}
+						}
+						selected := []string{}
+						for _, member := range actual {
+							if filter == "" || matchRegex("/"+filter+"/", member) {
+								selected = append(selected, displayAlias(member, aliases))
+							}
+						}
+						want := names
+						if strings.TrimSpace(name) == "US" {
+							want, _ = filterTags(names, pattern, true)
+						}
+						if !reflect.DeepEqual(selected, want) {
+							t.Fatalf("INI membership changed: %v want %v", selected, want)
+						}
+					}
+				}
+			default:
+				// These formats emit nodes only; no policy groups exist. Compare full
+				// connection payloads after restoring the encoded display identity.
+				b, a := string(before), string(after)
+				if format == "general" || format == "quantumultx" {
+					bb, _ := base64.StdEncoding.DecodeString(b)
+					aa, _ := base64.StdEncoding.DecodeString(a)
+					b, a = string(bb), string(aa)
+				}
+				for display, original := range aliases {
+					if format == "general" {
+						display, original = rawURLEncode(display), rawURLEncode(original)
+					}
+					a = strings.ReplaceAll(a, display, original)
+				}
+				if b != a {
+					t.Fatal("node set or connection payload changed")
+				}
+			}
+			// Ensure the regression actually exercises simplified emitted identities.
+			decoded := string(after)
+			if format == "general" || format == "quantumultx" {
+				raw, _ := base64.StdEncoding.DecodeString(decoded)
+				decoded = string(raw)
+			}
+			if format == "general" {
+				decoded, _ = url.PathUnescape(decoded)
+			}
+			if strings.Contains(decoded, "AI解锁") {
+				t.Fatal("display simplification did not run")
+			}
+		})
+	}
+}
+
+func TestDisplayReferencesAndCollisions(t *testing.T) {
+	rows := []*serverRow{{Name: "US Reality", DisplayName: "美国 01 VLESS"}, {Name: "unknown"}}
+	aliases := displayAliases(rows, []string{"US Reality", "unknown"}, []string{"美国 01 VLESS"}, nil)
+	if aliases["US Reality"] != "美国 01 VLESS (2)" || aliases["unknown"] != "" {
+		t.Fatalf("collision/fallback: %v", aliases)
+	}
+	cfg := map[string]any{
+		"sub-rules": map[string]any{"nested": []any{"DOMAIN,example.test,US Reality,no-resolve"}},
+		"rules":     []any{map[string]any{"outbound": "US Reality"}},
+		"default":   "US Reality", "final": "US Reality", "detour": "US Reality", "dialer-proxy": "US Reality",
+		"password": "US Reality", "server": "US Reality",
+	}
+	rewriteDisplayReferences(cfg, aliases)
+	rules := cfg["sub-rules"].(map[string]any)["nested"].([]any)
+	if rules[0] != "DOMAIN,example.test,美国 01 VLESS (2),no-resolve" {
+		t.Fatalf("sub-rule reference: %v", rules)
+	}
+	for _, key := range []string{"default", "final", "detour", "dialer-proxy"} {
+		if cfg[key] != aliases["US Reality"] {
+			t.Fatalf("reference %s", key)
+		}
+	}
+	for _, key := range []string{"password", "server"} {
+		if cfg[key] != "US Reality" {
+			t.Fatalf("connection value changed: %s", key)
+		}
+	}
+}
+
+func TestDisplayRuntimeFilterFallbacks(t *testing.T) {
+	for _, provider := range []bool{false, true} {
+		row := &serverRow{Name: "美国 AI解锁 Reality x1.5", Type: "vless"}
+		prepareDisplayNames([]*serverRow{row})
+		proxy := map[string]any{"name": row.Name}
+		group := map[string]any{"name": "All", "proxies": []any{"DIRECT", row.Name}, "filter": "DIRECT|美国"}
+		cfg := map[string]any{"proxies": []any{proxy}, "proxy-groups": []any{group}}
+		if provider {
+			cfg["proxy-providers"] = map[string]any{"remote": map[string]any{"type": "http"}}
+		}
+		applyClashDisplayNames(cfg, []any{proxy}, []*serverRow{row})
+		if provider {
+			if proxy["name"] != row.Name || group["filter"] != "DIRECT|美国" {
+				t.Fatal("dynamic provider selection changed")
+			}
+		} else {
+			if proxy["name"] != row.DisplayName {
+				t.Fatal("not renamed")
+			}
+			if !matchRegex("/"+group["filter"].(string)+"/", "DIRECT") {
+				t.Fatal("builtin lost from native filter")
+			}
+		}
+	}
+	rows := displayTestRows()[2:]
+	prepareDisplayNames(rows)
+	for _, external := range []bool{false, true} {
+		profile := "[Proxy]\n" + surgeHysteria(rows[0]) + surgeHysteria(rows[1]) + "[Proxy Group]\nUS = select, " + rows[0].Name + ", " + rows[1].Name + ", policy-regex-filter=\"(?i)^(?!.*AI).*美国\""
+		if external {
+			profile += ", policy-path=https://example.test/nodes"
+		}
+		got := applyINIDisplayNames(profile, rows)
+		if external {
+			if got != profile {
+				t.Fatal("remote policy filter changed")
+			}
+			continue
+		}
+		for _, line := range strings.Split(got, "\n") {
+			if !strings.HasPrefix(line, "US =") {
+				continue
+			}
+			_, rest, _ := strings.Cut(line, "=")
+			for _, token := range splitINIGroupParameters(rest) {
+				if pattern, ok := strings.CutPrefix(strings.TrimSpace(token), "policy-regex-filter="); ok {
+					if matchRegex("/"+pattern+"/", rows[0].DisplayName) || !matchRegex("/"+pattern+"/", rows[1].DisplayName) {
+						t.Fatal("quoted filter selection changed")
+					}
+				}
+			}
+		}
+	}
+}
+
+func TestDisplayMultiplierFailSafeAndRuleNamespace(t *testing.T) {
+	for _, text := range []string{"[倍率:1.5x]", "【traffic × 1.50 premium】", "(倍率：2x)", "[x1.5] [2倍]"} {
+		row := &serverRow{Name: "JP Reality " + text, Type: "vless"}
+		prepareDisplayNames([]*serverRow{row})
+		if !strings.HasSuffix(row.DisplayName, text) {
+			t.Fatalf("truncated multiplier %q: %q", text, row.DisplayName)
+		}
+	}
+	for _, text := range []string{"1.5倍流量", "x1/2", "[倍率未知]", ".5x", "1,5x"} {
+		row := &serverRow{Name: "JP Reality " + text, Type: "vless"}
+		prepareDisplayNames([]*serverRow{row})
+		if row.DisplayName != "" {
+			t.Fatalf("unsafe rate syntax renamed: %q", row.DisplayName)
+		}
+	}
+	cfg := map[string]any{"rules": []any{"SUB-RULE,(DOMAIN,example.test),US Reality"}}
+	rewriteDisplayReferences(cfg, map[string]string{"US Reality": "美国 01 VLESS"})
+	if cfg["rules"].([]any)[0] != "SUB-RULE,(DOMAIN,example.test),US Reality" {
+		t.Fatal("sub-rule namespace changed")
+	}
+}
+
+func TestDisplayNativeFilterCase(t *testing.T) {
+	aliases := map[string]string{"美国 AI": "美国 01 VLESS", "美国 ai": "美国 02 VLESS"}
+	names := []string{"美国 AI", "美国 ai"}
+	for _, pattern := range []string{"AI", "(?i)AI", "^(?!.*AI).*美国", "(?i)^(?!.*AI).*美国"} {
+		original, err := nativeDisplayMatcher(pattern)
+		if err != nil {
+			t.Fatal(err)
+		}
+		rewritten, err := regexp.Compile(displayFilter(pattern, names, aliases))
+		if err != nil {
+			t.Fatal(err)
+		}
+		for _, name := range names {
+			if original.match(name) != rewritten.MatchString(aliases[name]) {
+				t.Fatalf("case changed for %q with %q", name, pattern)
+			}
+		}
+	}
+	matcher, err := nativeDisplayMatcher("AI")
+	if err != nil || matcher.match("ai") {
+		t.Fatal("native case sensitivity lost")
+	}
+}
+
+func TestDisplayNativeFilterUnsafeAssertions(t *testing.T) {
+	for _, pattern := range []string{"^(?!AI)US|JP", "(?m)^(?!AI).*US", "美国(?! AI)"} {
+		if _, err := nativeDisplayMatcher(pattern); err == nil {
+			t.Fatalf("unsafe native expression accepted: %s", pattern)
+		}
+	}
+	if _, err := nativeDisplayMatcher("(?i)^(?!.*AI).*(US|JP)"); err != nil {
+		t.Fatal(err)
+	}
+}
diff --git a/internal/modules/subscribe/general.go b/internal/modules/subscribe/general.go
index 48dbc165..3e301c38 100644
--- a/internal/modules/subscribe/general.go
+++ b/internal/modules/subscribe/general.go
@@ -12,6 +12,7 @@ import (
 // 仅输出生产协议 vless(reality)://、hysteria2://。
 
 func (m *Module) renderGeneral(servers []*serverRow) []byte {
+	servers = displayRows(servers)
 	var sb strings.Builder
 	for _, s := range servers {
 		switch s.Type {
diff --git a/internal/modules/subscribe/loon.go b/internal/modules/subscribe/loon.go
index cccb874b..ab229710 100644
--- a/internal/modules/subscribe/loon.go
+++ b/internal/modules/subscribe/loon.go
@@ -22,6 +22,7 @@ func loonEmits(s *serverRow) bool {
 }
 
 func (m *Module) renderLoon(servers []*serverRow) []byte {
+	servers = displayRows(servers)
 	var sb strings.Builder
 	// 清洗后再去重（2026-10-04）：节点名先经 iniSafeNodeName 才写进行首，"a,b" 与 "a b"
 	// 在 Loon 眼里是同一个名字；prependInfoServers 的逐字去重看不见这层碰撞。
diff --git a/internal/modules/subscribe/proxies.go b/internal/modules/subscribe/proxies.go
index 419fd4d5..cf0dd072 100644
--- a/internal/modules/subscribe/proxies.go
+++ b/internal/modules/subscribe/proxies.go
@@ -29,6 +29,8 @@ type serverRow struct {
 	// SourceName 是本地化之前的库内原名。保留它只为一件事：`?filter=` 是按
 	// 用户看到的名字打的，存量书签里是中文，所以过滤要中英两个名字都比对。
 	SourceName string
+	// DisplayName is output-only; Name remains the selection identity.
+	DisplayName string
 	// cdnOriginHost retains the registered CDN identity when Host becomes a
 	// rendered bucket address. It is private and never emitted to clients.
 	cdnOriginHost string
diff --git a/internal/modules/subscribe/quantumultx.go b/internal/modules/subscribe/quantumultx.go
index fcde870f..84280056 100644
--- a/internal/modules/subscribe/quantumultx.go
+++ b/internal/modules/subscribe/quantumultx.go
@@ -16,6 +16,7 @@ import (
 func qxEmits(s *serverRow) bool { return s.Type == "vless" }
 
 func (m *Module) renderQuantumultX(servers []*serverRow) []byte {
+	servers = displayRows(servers)
 	var sb strings.Builder
 	// 清洗后再去重：tag= 用的是 iniSafeNodeName 之后的名字（见 renderLoon 同一说明）。
 	servers = dedupeEmittedININames(servers, qxEmits)
diff --git a/internal/modules/subscribe/singbox.go b/internal/modules/subscribe/singbox.go
index 10cb9407..7258ba15 100644
--- a/internal/modules/subscribe/singbox.go
+++ b/internal/modules/subscribe/singbox.go
@@ -102,6 +102,7 @@ func (m *Module) renderSingBoxForClient(
 	adaptSingBoxTunStack(cfg, core)
 	adaptSingBoxLegacyDNSServers(cfg, core)
 
+	applySingBoxDisplayNames(cfg, proxies, proxyRows)
 	return json.Marshal(cfg)
 }
 
diff --git a/internal/modules/subscribe/subscribe.go b/internal/modules/subscribe/subscribe.go
index 77824b60..7218786c 100644
--- a/internal/modules/subscribe/subscribe.go
+++ b/internal/modules/subscribe/subscribe.go
@@ -267,6 +267,7 @@ func (m *Module) serveSubscription(
 	// 否则英文用户按英文名过滤会一个节点都留不下。localizeServerNames 同时
 	// 保留原始中文名供 filterServers 一并匹配（见那里的注释）。
 	localizeServerNames(servers, i18n.FromContext(ctx))
+	prepareDisplayNames(servers)
 	// 最终协议闸门必须放在 node_ext 合入之后，不能只依赖 DB/插件各自的配置约束。
 	// Hysteria 在系统内统一存为 type=hysteria，须额外钉死 version=2，避免 HY1 或旧协议
 	// 从 local/API/Clash 外挂来源旁路进入任一客户端格式。
@@ -607,6 +608,7 @@ func (m *Module) prependInfoServersFor(ctx context.Context, u *subUser, servers
 	clone := func(name string) *serverRow {
 		c := *tmpl
 		c.Name = name
+		c.DisplayName = ""
 		c.Host = "127.0.0.1"
 		c.Port, c.Ports = resolvePorts("9", "") // fixed port, no hopping range
 		c.cdnOriginHost = ""
diff --git a/internal/modules/subscribe/subscribe_clash.go b/internal/modules/subscribe/subscribe_clash.go
index cc9ae798..a2e139a1 100644
--- a/internal/modules/subscribe/subscribe_clash.go
+++ b/internal/modules/subscribe/subscribe_clash.go
@@ -92,6 +92,7 @@ func (m *Module) renderClashMeta(
 	reserved = append(reserved, clashTemplateProxyNames(base)...)
 	servers = dedupeServerNames(servers, reserved)
 
+	var proxyRows []*serverRow
 	var proxyObjs []any
 	var names []string
 	transportOf := map[string]string{}
@@ -105,6 +106,7 @@ func (m *Module) renderClashMeta(
 				enableRealityMLKEM(p)
 			}
 			connTag.markConnTag(p)
+			proxyRows = append(proxyRows, s)
 			proxyObjs = append(proxyObjs, p)
 			names = append(names, s.Name)
 		}
@@ -157,6 +159,25 @@ func (m *Module) renderClashMeta(
 		}
 	}
 
+	if hasDisplayNames(proxyRows) {
+		display := map[string]any{
+			"proxies": append(base, proxyObjs...), "proxy-groups": pg["proxy-groups"],
+			"rules": rl["rules"], "sub-rules": rl["sub-rules"],
+			"proxy-providers": normalizeYAML(yamlMapGet(root, "proxy-providers")),
+		}
+		applyClashDisplayNames(display, proxyObjs, proxyRows)
+		for _, key := range []string{"proxies", "proxy-groups", "rules", "sub-rules"} {
+			if display[key] != nil {
+				if err := yamlMapSet(root, key, display[key]); err != nil {
+					return nil, err
+				}
+			}
+		}
+		for _, item := range yamlMapValueNode(root, "proxies").Content {
+			item.Style = yaml.FlowStyle
+		}
+	}
+
 	// $app_name is substituted **into the node tree**, not into the marshalled
 	// bytes. Everything above exists to let yaml.Marshal guarantee structure;
 	// rewriting its output afterwards gives that guarantee back. app_name is
diff --git a/internal/modules/subscribe/surfboard.go b/internal/modules/subscribe/surfboard.go
index 9c797cf3..35b076d5 100644
--- a/internal/modules/subscribe/surfboard.go
+++ b/internal/modules/subscribe/surfboard.go
@@ -63,5 +63,6 @@ func (m *Module) renderSurfboard(
 	// 会把视频 QUIC 变成长时间黑洞的目的 UDP/443 拒绝规则。
 	out = stripLegacyDestinationQUICFallback(out)
 	out = ensureINIManagedDirectRules(out)
+	out = applyINIDisplayNames(out, servers)
 	return []byte(out)
 }
diff --git a/internal/modules/subscribe/surge.go b/internal/modules/subscribe/surge.go
index ac93f560..a5628721 100644
--- a/internal/modules/subscribe/surge.go
+++ b/internal/modules/subscribe/surge.go
@@ -75,6 +75,7 @@ func (m *Module) renderSurge(
 	// 旧版保留 REJECT-NO-DROP 规则，避免普通 REJECT 在突发重试后退化为静默丢包。
 	out = configureSurgeQUICFallback(out, surgeSupportsGlobalQUICBlock(r))
 	out = ensureINIManagedDirectRules(out)
+	out = applyINIDisplayNames(out, servers)
 	return []byte(out)
 }
 

codex
The diff only adds tests; none are removed or weakened. I found a reference gap in the INI renderer: it renames proxy definitions and group/rule references but leaves references inside proxy parameters unchanged.
exec
/bin/zsh -lc "git diff --check 5fbad75602a85bd21c37b73e9b8421d8c6bbfd56 2b2acde3ad635c627ddfef68ec51bf29a5c48c42; git diff --unified=0 5fbad75602a85bd21c37b73e9b8421d8c6bbfd56 2b2acde3ad635c627ddfef68ec51bf29a5c48c42 -- internal/modules/subscribe/display_name.go | awk '/"'^'"\\+["'^+]/{n++; if(n>=365 && n<=408) print n ":" substr($0,2)}'"'" in /Users/j/codex-runs/mh1105/yb-142
 succeeded in 0ms:
365:				continue
366:			}
367:			parts := splitINIGroupParameters(rest)
368:			for j := 1; j < len(parts); j++ {
369:				token := strings.TrimSpace(parts[j])
370:				key, value, parameter := strings.Cut(token, "=")
371:				if strings.TrimSpace(key) == "policy-regex-filter" {
372:					parts[j] = "policy-regex-filter=" + displayFilter(iniDisplayPattern(value), reserved, aliases)
373:				} else if !parameter {
374:					parts[j] = displayAlias(token, aliases)
375:				}
376:			}
377:			lines[i] = name + "=" + strings.Join(parts, ", ")
378:		case "[rule]":
379:			parts := strings.Split(line, ",")
380:			target := len(parts) - 1
381:			if target > 0 && strings.TrimSpace(parts[target]) == "no-resolve" {
382:				target--
383:			}
384:			if target > 0 {
385:				parts[target] = displayAlias(strings.TrimSpace(parts[target]), aliases)
386:				lines[i] = strings.Join(parts, ",")
387:			}
388:		}
389:	}
390:	return strings.Join(lines, "\n")
391:}
392:func hasDisplayNames(rows []*serverRow) bool {
393:	for _, s := range rows {
394:		if s.DisplayName != "" {
395:			return true
396:		}
397:	}
398:	return false
399:}
400:func iniDisplayPattern(value string) string {
401:	value = strings.TrimSpace(value)
402:	if len(value) >= 2 && (value[0] == '"' || value[0] == '\'') && value[len(value)-1] == value[0] {
403:		return value[1 : len(value)-1]
404:	}
405:	return value
406:}
407:// Preserve whole bracketed expressions, including annotations such as
408:// "[倍率:1.5x]". Unrecognized/partial rate syntax keeps the original name.

exec
/bin/zsh -lc "git diff --unified=0 5fbad75602a85bd21c37b73e9b8421d8c6bbfd56 2b2acde3ad635c627ddfef68ec51bf29a5c48c42 -- internal/modules/subscribe/display_name.go | awk '/"'^'"\\+\\+\\+/{next} /"'^'"\\+/{n++; if(n>=375 && n<=400) print n \":\" substr("'$0,2)}'"'" in /Users/j/codex-runs/mh1105/yb-142
 succeeded in 0ms:
375:		case "[proxy group]":
376:			name, rest, ok := strings.Cut(line, "=")
377:			if !ok {
378:				continue
379:			}
380:			parts := splitINIGroupParameters(rest)
381:			for j := 1; j < len(parts); j++ {
382:				token := strings.TrimSpace(parts[j])
383:				key, value, parameter := strings.Cut(token, "=")
384:				if strings.TrimSpace(key) == "policy-regex-filter" {
385:					parts[j] = "policy-regex-filter=" + displayFilter(iniDisplayPattern(value), reserved, aliases)
386:				} else if !parameter {
387:					parts[j] = displayAlias(token, aliases)
388:				}
389:			}
390:			lines[i] = name + "=" + strings.Join(parts, ", ")
391:		case "[rule]":
392:			parts := strings.Split(line, ",")
393:			target := len(parts) - 1
394:			if target > 0 && strings.TrimSpace(parts[target]) == "no-resolve" {
395:				target--
396:			}
397:			if target > 0 {
398:				parts[target] = displayAlias(strings.TrimSpace(parts[target]), aliases)
399:				lines[i] = strings.Join(parts, ",")
400:			}

codex
VERDICT: changes

- **P2 — Dangling INI proxy references:** [display_name.go:370](/Users/j/codex-runs/mh1105/yb-142/internal/modules/subscribe/display_name.go:370) renames `[Proxy]` definitions but preserves their parameters verbatim. A template proxy using `underlying-proxy=US HY2` still references that old name after it becomes `美国 01 Hysteria2`, breaking the chain. Rewrite these identity references or retain original names; add regression coverage.
- No existing tests were removed or weakened. Diff whitespace checks passed; runtime tests were not run.
tokens used
51,351
VERDICT: changes

- **P2 — Dangling INI proxy references:** [display_name.go:370](/Users/j/codex-runs/mh1105/yb-142/internal/modules/subscribe/display_name.go:370) renames `[Proxy]` definitions but preserves their parameters verbatim. A template proxy using `underlying-proxy=US HY2` still references that old name after it becomes `美国 01 Hysteria2`, breaking the chain. Rewrite these identity references or retain original names; add regression coverage.
- No existing tests were removed or weakened. Diff whitespace checks passed; runtime tests were not run.
Finished: 2026-11-05T03:07:10Z exit=0
