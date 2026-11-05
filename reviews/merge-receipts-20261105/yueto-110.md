# yueto #110 review at f7da2118e1b6668a1bc65ee4400e1168d790c967

Reviewed range: e26b58600120ebb24a162f3f71fcf3ff2c25d4ff..f7da2118e1b6668a1bc65ee4400e1168d790c967 (post-merge backfill; codex on mac-5f08d00f, read-only sandbox)
Started: 2026-11-05T03:05:06Z

Reading additional input from stdin...
OpenAI Codex v0.166.0
--------
workdir: /Users/j/codex-runs/mh1105/yt-110
model: gpt-6-astra
provider: openai
approval: never
sandbox: read-only
reasoning effort: medium
reasoning summaries: none
session id: 01a1a9aa-d18f-7bc1-90bf-09c279627f18
--------
user
You are reviewing merged PR onesyue/yueto #110 at exact head f7da2118e1b6668a1bc65ee4400e1168d790c967. Review ONLY the diff: git diff e26b58600120ebb24a162f3f71fcf3ff2c25d4ff f7da2118e1b6668a1bc65ee4400e1168d790c967 (and git log e26b58600120ebb24a162f3f71fcf3ff2c25d4ff..f7da2118e1b6668a1bc65ee4400e1168d790c967). Do not modify files. Check correctness, regressions, weakened/removed tests, security, and that the change matches its title/intent. Output a final line exactly 'VERDICT: approve' or 'VERDICT: changes' followed by concise bullet findings.
2026-11-05T03:05:11.679382Z ERROR codex_models_manager::manager: failed to refresh available models: request timed out
hook: SessionStart
hook: SessionStart Completed
codex
我会只检查指定提交区间的 diff 和日志，不修改文件，并据此判断回归、安全性及测试变化。

hook: PreToolUse
hook: PreToolUse Completed
exec
/bin/zsh -lc 'cat CLAUDE.md' in /Users/j/codex-runs/mh1105/yt-110
 succeeded in 0ms:
# CLAUDE.md

@AGENTS.md

Shared workspace guidance for Claude Code and Codex (`AGENTS.md` loads this file).

**All owner-facing replies must be in Chinese**, including progress updates,
tables and final reports. Keep code identifiers, commands and SHAs unchanged.
Repository engineering documentation and explanatory comments use English.

This is the **`yue.to` workspace root** — an umbrella over a family of independent git repos that together make up a privatized (from-Xboard) VPN/proxy service: panel, node fleet, client apps, and ops. It is NOT a monorepo. Each subdirectory is its own repository; the root repo tracks nine directories — `docs/`, `scripts/`, `design/`, `i18n/`, `schedule/`, `help/`, `.claude/` (skills/rules/agents/hooks/settings only; `worktrees/`/`projects/`/`state/` stay ignored), `.agents/` (Codex skill links), `.grok/` (Grok rules, LSP, and three skill overrides; estate skills stay in `.claude/skills/`) — plus `.codex/hooks.json` and a few top-level files: `yueto.code-workspace`, `.gitleaksignore`, and the signed release desired state `release.yaml` + `release.yaml.asc` (`.gitignore` is `/*/` + allowlist, so root *files* are not ignored). Root `reports/` is a local, untracked scratch area — never commit it or cite it as current state. Most real work happens **inside** a component repo, each of which has its own richer `CLAUDE.md` — read that one too when working in it.

## Where the knowledge lives: this file, skills, rules

This file is **always-loaded context** and is kept under the official ~200-line target. Everything
else has a home that loads on demand — that is the whole design, not a filing convenience:

- **`.claude/skills/` — workspace skills**, symlinked into `~/.claude/skills/` so they load
  through `.agents/skills/` for Codex and installed for both agents by `scripts/sync-agent-skills.py --apply --user`. Procedural knowledge: worthless most of the time, and must be
  word-for-word correct the rest of the time.
- **`.claude/rules/` — path-scoped rules** (`paths:` frontmatter). A rule enters context only when
  a file it names is read. Use it for "this *file class* has a trap", never for prose.
- **`.claude/agents/` — project subagents**: `component-worker` (edits a component repo from its own
  worktree under root `.claude/worktrees/` — never `isolation: worktree`) and `readonly-investigator`.

| Skill (routes by **domain**) | Load it when |
|---|---|
| `guard-authoring` | changing/reviewing guard coverage, contract checks, CI assertions or probes; diagnosing test import/fixture leakage; ordinary fixes that only run existing checks do not trigger it |
| `release-chain` | planning or running any release, image roll, promote or production deploy |
| `node-lifecycle` | classifying maintenance/retirement or supplier-quota availability; provisioning, cloning, rebuilding or hard-deleting a fleet node |
| `fleet-diagnose` | diagnosing node/fleet/network/latency/loss/resource problems, **before** changing production |
| `pg-safety` | writing a Postgres migration, GRANT/role manifest, cross-ownership table access, erasure change, or a spend/eligibility query |
| `generated-blocks` | changing design tokens, user-facing strings/translations, help articles, or any recurring job |
| `round-closeout` | closing out an audit / optimization / incident round |
| `yueto-orchestration` | running an authorized multi-session round under the current coordinator (Claude or Codex): one release exit, side-branch candidates, inbox, release train and shutdown; no fixed-model approval prerequisite |

| Skill (routes by **action**) | Load it when |
|---|---|
| `yueto-agent-maintenance` | equipping, configuring or diagnosing coding-agent capabilities for this workspace |
| `evidence-discipline` | interpreting operational measurements or asserting production/fleet health or runtime improvement; match the claim to its evidence |
| `landed-not-written` | installing executable scripts/configuration/automation or claiming an installed change took effect; verify the actual consumer |
| `change-blast-radius` | removing a boundary, renaming, moving a file, zeroing a parameter, dropping a wait, or touching a constant other code pins |
| `concurrent-git-safety` | committing/pushing, spawning concurrent agents into one repo, or editing anything while a long-running script executes |
| `patrol` | routine read-only patrol of failed units, DNS sentinel receipts, relay-pool evidence and local workload admission; never changes production |
| `readonly-reconcile` | read-only balance/points reconciliation or release accounting comparisons; never repairs data |
| `release-readback` | after a signed release: reconcile promoted, desired and running images, migration receipts and before/after accounting evidence |

Select skills by the actual change and claim. Related-skill links are conditional,
not a recursive reading list. Reuse loaded guidance and read only relevant reference sections.

Component repos use the same mechanism: **yueops** nine (`yueops-agent-deploy`, `-host-hardening`, `-deploy-gotchas`,
`-panel-db-gotchas`, `-business-gotchas`, `-emby`, `-ai-support`, `-telegram`, `-business-features`) and **yuelink**
five (`yuelink-platform-gotchas`, `-core-ffi`, `-panel-api`, `-environment`, `-release-ci`), moved **verbatim** from each `CLAUDE.md`.

**Measure before proposing another split** (`wc -l` + tokens over the real byte/CJK mix, same unit on
both sides; dated readings live in `round-closeout`). **yueboard and yue-node are at target — do not split them.**
🚨 Moving doc text into a skill silently shrinks the scan surface of **negative** doc-truth guards
("must no longer say Y") while they stay green. 📎 `change-blast-radius`.

`.claude/hooks/` (wired in `settings.json`, tests beside them): `yueto-notice.py` reminds, never
blocks, on a `git push` touching yueboard or an edit to a generated token file, `schedule/registry.yaml`
or an i18n catalog; `session-status.py` (SessionStart) injects any side branch / dirty tree / unpushed
commit / pin mismatch / release lock — UNKNOWN, never "clean". `defaultMode: "bypassPermissions"` is
the owner's 2026-08-31 decision: **zero permission prompts** (`ask-gate.py` is deliberately un-wired;
don't re-wire it); 2026-10-13 extended to subagents (`permissionMode` + a `PermissionRequest` auto-allow). The one
blocking hook is `secret-read-guard.py` (2026-10-17: denies unredacted secret-file/container-env reads); else reminders, rules, guards.

**Owner decision — 2026-09-10:** never run local download-and-verify acceptance after YueLink
releases; CI package/runtime checks, artifact verification, signed provenance and the promotion result suffice.

## Workspace commands (root scope)

```bash
scripts/status-all.sh          # branch / dirty / unpushed for every component repo (+ yuelink/core/mihomo)
scripts/pull-all.sh            # git pull --ff-only across all; repos with local changes fetch-only
scripts/check-all-contracts.sh # run every cross-cutting guard, print one summary (--list to see them)
scripts/gauntlet-launch.sh     # clean login environment, fail-fast admission, exclusive log
                               # THE pre-release gate: every private repo's own CI stages + all contracts
                               # (run it only under heavy-run; a direct scripts/gauntlet.sh exits 2)
scripts/release-state.py       # read-only: source HEAD vs reviewed pin vs promoted image vs production
scripts/ship.sh <yueops|yueboard|yue-node> [--auto|--no-deploy|--detach|--from-promoted]
                               # the whole release chain unattended: build → promote → verify → deploy
scripts/kick-builds.sh [--dry-run]     # trigger yueto-ci poll-sources now instead of waiting for its cron
scripts/scan-workspace-secrets.sh      # yueops' secret scanner over ALL private repos + root (in gauntlet)
scripts/run-yueboard-pg18-gauntlet.sh  # release-only yueboard integration gate on a disposable PG18
scripts/linux-lens-gate.sh             # yueops full suite in the central-CI Linux lens; proves darwin-skipped tests ran
scripts/disk-hygiene.sh --check|--apply  # the ONLY sanctioned worktree/docker/cache cleanup (keep-list + safety criteria)
scripts/heavy-run.sh / new-session.sh  # orchestration entry points (semaphore, Codex sessions) 📎 `yueto-orchestration`
```

The root's own tests are the guard self-tests (`scripts/test-*.py`, `.claude/hooks/test_*.py`), run
from the workspace venv `~/.venvs/yueto` (3.13 + pytest + pyyaml; system `python3` is 3.9 with neither).
Hyphenated `test-*.py` names escape pytest discovery — `pytest scripts` silently collects nothing:

```bash
~/.venvs/yueto/bin/python -m pytest -q scripts/test-root-doc-truth.py                        # one guard's tests
~/.venvs/yueto/bin/python -m pytest -q scripts/test-schedule-registry.py -k baseline_is_green # one case
~/.venvs/yueto/bin/python -m pytest -q scripts/test-*.py .claude/hooks                        # all root self-tests
```

- `ship.sh` only chains the audited per-step scripts, scraping digests from the *promote* step's log
  (never the build's). 📎 constraints: **`release-chain`**; commands: `docs/release-chain-runbook.md`.
- `release-state.py` names the next action per row; `--fleet`/`--packages` sweep the fleet, where an
  unreachable row is **UNKNOWN, never OK**. 📎 `release-chain`.
- `gauntlet.sh` is the only fail-closed "did everything actually run" gate; `--fast` drops the
  network stages and **does not qualify for a release**. 📎 `guard-authoring`.
- `status-all.sh`/`pull-all.sh` also cover `yuelink/core/mihomo`, a *separate* repo inside `yuelink`.

🚨 **Before believing a red guard or a four-truths mismatch, run `scripts/status-all.sh`.** Cross-repo
guards read each repo's **main checkout**, so whatever branch it is on is a hidden input (2026-09-06:
one repo left on a side branch → 8 red contracts, 6 pure artifacts). 📎 `concurrent-git-safety`.

`check-all-contracts.sh` is the one place that knows the **full** guard set (`--list`; never copy the
count). Every comparator that reads two repos at once runs **here and nowhere else** — single-repo CI
lacks the sibling checkout. 📎 `guard-authoring` (incl. the `guard-ci-claims` meta-guard).

## The cross-repo sources of truth the root repo itself owns

Four small root directories are the **single upstream** for values duplicated across five surfaces
and four runtimes — so an edit inside a component repo to any generated block is a regression, not a fix.

- **`design/tokens/yue.tokens.json`** — the design scale. `node design/build-tokens.mjs` regenerates
  one fenced block per surface plus the scale tables in `docs/yue-visual-language-2026.md` §2.
- **`i18n/catalog/*.json`** — the zh-CN → en catalog; `scripts/i18n/CONTRACT.md` is the one binding spec.
- **`schedule/registry.yaml`** — the generated inventory of every recurring job across six layers,
  from `scripts/schedule/extract.py --write`.
- **`help/articles/*.md`** — the unified help center (`help/CONTRACT.md`); UIs reference `help:<slug>`.

📎 **Before touching any of these, read the `generated-blocks` skill** (generated vs. hand-written,
fence rules, never-translate set, ratchets).

## The system: four planes

Data flows **panel → subscription → client**, and **panel ⇄ node** for control.

| Repo | Plane | Stack | Role |
|---|---|---|---|
| **yueboard** | Control (panel) | Go (chi + sqlc + goose + pgx/PG, ConnectRPC) | Native panel backend for user/admin APIs, login, **subscription generation**, and the only node control-plane server. The former REST/WS node protocol and fallback proxy are gone. Native admin/user SPAs (React 19) are embedded with `go:embed`; `my.yue.to` runs this. |
| **yue-node** | Data (nodes) | Go (`cmd/` + `internal/…`, kernels as adapters) | Native node agent on the anti-GFW fleet, with direct hosts and shared relays. **Never restate the fleet size from memory or from this file**: the three counts (direct hosts / serving assignments / unique enabled nodes) come only from the live inventory (`servers` where `deploy_mode='direct'`; 📎 `.claude/rules/fleet-baseline.md`); `docs/yue-product-surface-inventory-2026.md` carries only a **dated snapshot** (dated, self-consistent, pointing at the live source — a second hand-copy caused the 2026-08-18 guard that *refused* to let a stale fact be corrected). Runs Reality/VLESS and Hysteria2 and talks to yueboard only through machine-scoped ConnectRPC. `/home/yue-node` on each machine. |
| **yuelink** | Client | Flutter UI + mihomo (Clash.Meta) Go core via FFI | The Yue.to cross-platform app (Android/iOS/macOS/Windows/Linux, id `com.yueto.yuelink`). The server template is authoritative; the client adds only bounded compatibility defaults and seeds bundled `.mrs` rule sets for offline startup. |
| **yueops** | Ops / services | Python (FastAPI, python-telegram-bot, RAG) monorepo | Supporting services: `checkin-api` (check-in), `yue-bot`/yubot (Telegram) + TG mini-app, AI support (Xiaoyue; RAG uses API embeddings and in-process NumPy cosine similarity, not pgvector), DNS/Cloudflare automation, telemetry ingest. Deployed as containers on the bastion. |

Supporting repos: **yuelink-ci** / **yueto-ci** are public build-only CI repos (they began as a workaround for the private-repo Actions billing freeze, which comes and goes — see the CI section — but `yueto-ci` has since become load-bearing for a supply-chain reason that holds regardless); **hysteria**, **Xray-core** and **quic-go** are the maintained data-plane kernel forks (yue-node's HY2 and Reality/VLESS engines plus HY2's QUIC dependency — each carries real yue-specific fixes, so "just track upstream" is wrong there); **clash-verge-rev / ClashMetaForAndroid / clashmi** are historical Yue product forks, frozen migration-only and no longer checked out in this workspace (status: `docs/yue-product-surface-inventory-2026.md`). **yuetube-video** is the private Remotion project that renders the Yue.to QA promo video (Node 24 / Remotion pinned, `src/data/video-script.json` is the single source for copy, subtitles, shot lengths and audio SHA-256; `npm run verify` gates supply chain + assets + `tsc`). It ships no runtime and is coupled to nothing else here. The old PHP panel and its local repository are retired and must not be reintroduced as a runtime, build, template, or fallback dependency.

## Cross-repo coupling that isn't visible in any single repo

- **Subscription generation is a contract between yueboard and every client family.** `yueboard/internal/modules/subscribe/` renders Clash Meta, Surge, Loon, Quantumult X, Surfboard, sing-box, and general links from native templates. There is no `?yl=1` or device-specific server branch. When one client fails, render its exact User-Agent and compare fields against a working renderer before changing the fleet.
- **The server template is the YueLink source of truth.** YueLink no longer inlines `GeoIP.dat`/`GeoSite.dat`; it seeds the exact bundled `.mrs` set and preserves server routing. Keep client transforms bounded to compatibility defaults, and use the reference clients to justify any divergence.
- **The schema is native; remaining cross-service reads are explicit migration debt.** Tables use native names, `numeric` amounts, `jsonb`, and `timestamptz`. YueBoard owns panel-domain writes. Any temporary YueOps read must be catalogued and moved behind a scoped native internal API before its DB credential is removed.
- **Panel↔node control is ConnectRPC only.** The protobuf contract is shared by yueboard and yue-node. Every physical host must use a machine-scoped credential and exact assignment; a fleet-wide token, REST polling, or WS push is a migration regression.
- **🚨 Never rebuild a node by copying another node's `/home/yue-node` wholesale.** The runtime tree
  contains `node-*/data/report-outbox`, which is the machine's **billing identity**. Cloning it either
  double-bills or wedges the node forever on `report sequence gap`, which has no recovery path. This
  has now happened twice (2026-08-01, 2026-08-11). **Wipe `node-*/data/report-outbox` before first
  start** — the in-code owner guard only protects hosts already running yue-node `4bf9ada` or newer.
  📎 Full provisioning / cloning / retiring / hard-delete procedure: the **`node-lifecycle`** skill.

## Authoritative planning docs (read before large work)

Start with `docs/README.md` for task-oriented navigation.

- **`docs/2026-10-17-whole-estate-execution-plan.md`** is the sole production plan.
  Use current r4 control and its backlog; update it in place. The 10-16 plan retains acceptance contracts only.
- **The newest relevant closeout/handoff** supplies dated evidence and supersession
  links. Verify its revision against current source and production; it cannot override the current plan.
  Removing a report never closes an obligation;
  preserve Git recovery records per `docs/2026-10-16-repository-cleanup.md`.
- **`docs/release-chain-runbook.md`** supplies procedures; `release-chain` supplies
  planning constraints. Dated examples do not authorize old targets or new owners.
- **`docs/2026-endgame-plan.md`** is a historical obligation map and guard input.
  Its predecessor `docs/2026-master-plan.md` was deleted; recover it with
  `git show 2ac56121:docs/2026-master-plan.md`. Neither is a current plan.
- **`docs/tech-stack-2026.md`** records choices and rejected alternatives.
  Database contracts: `docs/v2-shared-db-decoupling-map.md`, `docs/v2-timestamp-decoupling-roadmap.md`.
Raw build logs, `.exit`/`.stderr` files and per-run samples do not belong in `docs/`.
Use private/temporary evidence or component performance storage; see `docs/performance/README.md`.

## Release / CI: what is true in every session

Four things must name the same commit: the reviewed **pin**, the source repo **HEAD**, the
**promoted** image, and what **production** actually runs. `release-state.py` prints all four.
- **2026-10-12: SSH authority is ACTIVE.** Every new yueops revision needs auto-pull + `make-release-root.sh
  --strict` + `scripts/ship-sshd-authority.py --apply` before Ops/panel deploys or A/B publishing (ship.sh chains them).
- **2026-10-11: bastion is CPU-steal-bound** (60–78%): no heavy tests there; check `vmstat` st first. 📎 `release-chain`.

**Before pushing `yueboard/master`, establish its effect on the active release.**
Promotion requires default-branch ancestry, inputs identical to HEAD and a candidate
not older than `:latest`. A changed input can invalidate a running release.
When inputs change, the integration owner must complete these steps:

1. Read the revision labels off the **running production** panel image and node fleet, then run
   `scripts/converge-yueboard-release-pin.py --from-head --deployed-board-revision <prod-board>
   --deployed-node-revision <prod-node>`. Both are explicit because reviewed candidates may never
   have been deployed. It updates yueto-ci's two copies atomically and **derives** the schema
   floor from `git show <rev>:schema-floor.txt`; since P2 §4 A3 it no longer writes yueops.
2. Coordinate the required rebuild and panel deployment with the release owner.
   The desired state yueops deploys from is the **signed** root `release.yaml`
   (ship.sh writes + seals it; no pin is committed back into yueops). 📎 `release-chain`.

Promote, `release-state.py` and the schema-migrator contract accept a descendant
with unchanged native image inputs and the same schema floor while retaining the
reviewed pin. Use the actual input comparator: a Markdown or test filename alone
does not establish equivalence. Changed or unknown inputs retain the normal pin
convergence and release requirements. Preserve each active writer's source custody.

🚨 **The private repos' Actions billing freeze comes and goes** — measure it (wall-clock + step count,
job annotation decisive) before reading any red run; the local `gauntlet.sh` is the real gate either way.
Builds are **pulled** by `yueto-ci/poll-sources.yml` (**build only, never promote**; GitHub throttles
its cron, hence `kick-builds.sh`), and `yueto-ci` is **load-bearing**: every production digest is
cosign-signed under its workflow identity. 📎 criterion, cadence and trust anchor: `release-chain`.

hook: PreToolUse
hook: PreToolUse Completed
exec
/bin/zsh -lc 'git diff --stat e26b58600120ebb24a162f3f71fcf3ff2c25d4ff f7da2118e1b6668a1bc65ee4400e1168d790c967 && git log --oneline e26b58600120ebb24a162f3f71fcf3ff2c25d4ff..f7da2118e1b6668a1bc65ee4400e1168d790c967' in /Users/j/codex-runs/mh1105/yt-110
 succeeded in 0ms:
 scripts/kick-builds.sh                |  7 ++-
 scripts/lib/ci-runner.sh              | 40 ++++++++++++++++
 scripts/ship.sh                       | 11 ++---
 scripts/test-selfrun-dispatch.py      | 89 ++++++++++++++++++++++++++++++++++-
 scripts/test-ship-errexit-and-lock.py |  4 +-
 5 files changed, 138 insertions(+), 13 deletions(-)
f7da2118 ship: hosted CI only for a verified-public CI repo; self-hosted opt-in (YUETO_CI_RUNNER)

hook: PreToolUse
hook: PreToolUse Completed
exec
/bin/zsh -lc 'git diff e26b58600120ebb24a162f3f71fcf3ff2c25d4ff f7da2118e1b6668a1bc65ee4400e1168d790c967' in /Users/j/codex-runs/mh1105/yt-110
 succeeded in 0ms:
diff --git a/scripts/kick-builds.sh b/scripts/kick-builds.sh
index f07e0fb5..6f99d95c 100755
--- a/scripts/kick-builds.sh
+++ b/scripts/kick-builds.sh
@@ -33,10 +33,9 @@ command -v gh >/dev/null 2>&1 || {
 }
 
 die() { echo "FATAL: $*" >&2; exit 1; }
-runner_status=$(gh api --paginate repos/onesyue/yueto-ci/actions/runners \
-  --jq '.runners[] | select(.status == "online" and any(.labels[]; .name == "yue-local-release")) | .status') \
-  || die "Cannot verify yue-local-release runner availability"
-grep -qx online <<<"$runner_status" || die "No online yue-local-release runner; refusing dispatch"
+# shellcheck source=scripts/lib/ci-runner.sh
+. "$(dirname "${BASH_SOURCE[0]}")/lib/ci-runner.sh"
+ci_poll_dispatch_allowed onesyue/yueto-ci || die "No permitted CI runner; refusing dispatch"
 
 if ! gh workflow run poll-sources.yml -R onesyue/yueto-ci -f dry_run="$DRY"; then
   echo "FATAL: 触发 poll-sources 失败（见上方 gh 报错）。常见原因：gh 未登录/凭据过期" >&2
diff --git a/scripts/lib/ci-runner.sh b/scripts/lib/ci-runner.sh
new file mode 100644
index 00000000..1c545cbb
--- /dev/null
+++ b/scripts/lib/ci-runner.sh
@@ -0,0 +1,40 @@
+#!/usr/bin/env bash
+# Hosted dispatch is permitted only after an exact runtime visibility check.
+ci_repo_visibility() {
+  local repo=$1 visibility attempt
+  for ((attempt = 1; attempt <= 3; attempt++)); do
+    if visibility=$(gh api "repos/$repo" --jq .visibility 2>/dev/null) &&
+       [[ "$visibility" == public ]]; then
+      printf '%s\n' public
+      return 0
+    fi
+  done
+  return 1
+}
+
+ci_local_runner_online() {
+  local status
+  status=$(gh api --paginate "repos/$1/actions/runners" \
+    --jq '.runners[] | select(.status == "online" and any(.labels[]; .name == "yue-local-release")) | .status' 2>/dev/null) || return 1
+  grep -qx online <<<"$status"
+}
+
+ci_select_runner() {
+  local repo=$1
+  if [[ "${YUETO_CI_RUNNER:-}" == yue-local-release ]] && ci_local_runner_online "$repo"; then
+    printf '%s\n' yue-local-release
+  elif ci_repo_visibility "$repo" >/dev/null; then
+    printf '%s\n' ubuntu-24.04
+  else
+    echo "FATAL: CI repo is private or visibility is unknown; hosted dispatch refused. Set YUETO_CI_RUNNER=yue-local-release with an online runner to use self-hosted CI." >&2
+    return 1
+  fi
+}
+
+# poll-sources has no runner input; only gate its dispatch here.
+ci_poll_dispatch_allowed() {
+  ci_repo_visibility "$1" >/dev/null || ci_local_runner_online "$1" || {
+    echo "FATAL: CI repo is private or visibility is unknown and no verified online yue-local-release runner is available; refusing dispatch." >&2
+    return 1
+  }
+}
diff --git a/scripts/ship.sh b/scripts/ship.sh
index 319ebc39..5477e0a6 100755
--- a/scripts/ship.sh
+++ b/scripts/ship.sh
@@ -685,15 +685,14 @@ else
     log "触发 build+promote: $svc @ $REV"
     # Promotion trusts this workflow branch; make it explicit to avoid gh's
     # redundant default-branch lookup. The source revision remains a separate input.
-    # Fail closed before recording a pending dispatch; never fall back to hosted.
-    runner_status=$(gh api --paginate repos/onesyue/yueto-ci/actions/runners \
-      --jq '.runners[] | select(.status == "online" and any(.labels[]; .name == "yue-local-release")) | .status') \
-      || die "Cannot verify yue-local-release runner availability"
-    grep -qx online <<<"$runner_status" || die "No online yue-local-release runner; refusing dispatch"
+    # Default to hosted only for a verified public repository; self-hosted is opt-in.
+    # shellcheck source=scripts/lib/ci-runner.sh
+    . "$ROOT/scripts/lib/ci-runner.sh"
+    ci_runner=$(ci_select_runner onesyue/yueto-ci) || die "No permitted CI runner; refusing dispatch"
     triggered_at=$(date -u +%s)
     lock_evidence pending "ci:$svc" "dispatch service=$svc revision=$REV triggered_at=$triggered_at"
     gh workflow run build.yml -R onesyue/yueto-ci --ref master \
-       -f service="$svc" -f ref="$REV" -f promote=true -f runner=yue-local-release "${migration_args[@]}" >/dev/null \
+       -f service="$svc" -f ref="$REV" -f promote=true -f runner="$ci_runner" "${migration_args[@]}" >/dev/null \
       || die "$svc 的 build+promote 触发失败（gh workflow run）"
     # 等这一次触发产生的新 run 出现（GitHub 排队通常 2-8 秒）
     got=""
diff --git a/scripts/test-selfrun-dispatch.py b/scripts/test-selfrun-dispatch.py
index 0bec586b..90374db3 100644
--- a/scripts/test-selfrun-dispatch.py
+++ b/scripts/test-selfrun-dispatch.py
@@ -8,7 +8,7 @@ import subprocess
 import pytest
 
 ROOT = Path(__file__).resolve().parents[1]
-PATHS = ["scripts/ship.sh", "scripts/lib/ship-ui.sh", "scripts/kick-builds.sh"]
+PATHS = ["scripts/lib/ship-ui.sh"]
 
 
 def boundary(path):
@@ -75,4 +75,89 @@ def test_every_local_build_dispatch_is_pinned():
         commands.extend(line for line in text.splitlines()
                         if not line.lstrip().startswith('#') and 'gh workflow run build.yml ' in line)
     assert len(commands) == 2
-    assert all('-f runner=yue-local-release' in command for command in commands)
+    assert all('-f runner=yue-local-release' in command or '-f runner="$ci_runner"' in command
+               for command in commands)
+
+
+@pytest.mark.parametrize('path', ['scripts/ship.sh', 'scripts/kick-builds.sh'])
+@pytest.mark.parametrize('visibility', ['public', 'private', 'internal', '', 'unknown', 'Public', 'public extra', 'error', 'partial-error', 'recover'])
+@pytest.mark.parametrize('online', [False, True])
+@pytest.mark.parametrize('opt_in', ['', 'yue-local-release', 'other'])
+def test_hosted_gate(tmp_path, path, visibility, online, opt_in):
+    gh = tmp_path / 'gh'
+    gh.write_text('''#!/bin/bash
+if [ "$1" = api ]; then
+  if [ "$2" = --paginate ]; then
+    [ "$3" = repos/onesyue/yueto-ci/actions/runners ] || exit 92
+    [ "$ONLINE" = true ] && echo online
+    exit 0
+  fi
+  [ "$2" = repos/onesyue/yueto-ci ] || exit 93
+  [ "$3" = --jq ] && [ "$4" = .visibility ] || exit 94
+  echo attempt >> "$ATTEMPTS"
+  case "$VISIBILITY" in
+    error) echo synthetic-sensitive-error >&2; exit 1 ;;
+    partial-error) echo public; exit 1 ;;
+    recover) [ "$(wc -l < "$ATTEMPTS")" -ge 3 ] || exit 1; echo public ;;
+    *) printf '%s\\n' "$VISIBILITY" ;;
+  esac
+else
+  printf '%s\\n' "$@" > "$TRACE"
+fi
+''')
+    gh.chmod(0o755)
+    trace = tmp_path / 'dispatch'
+    attempts = tmp_path / 'attempts'
+    env = {**os.environ, 'PATH': str(tmp_path)+os.pathsep+os.environ['PATH'],
+           'ROOT': str(ROOT), 'VISIBILITY': visibility, 'ONLINE': str(online).lower(),
+           'YUETO_CI_RUNNER': opt_in, 'TRACE': str(trace), 'ATTEMPTS': str(attempts)}
+    if path.endswith('kick-builds.sh'):
+        command = ['bash', str(ROOT / path)]
+    else:
+        text = (ROOT / path).read_text()
+        start = text.index('    # Default to hosted only')
+        end = text.index('    # 等这一次触发产生的新 run', start)
+        script = '''set -euo pipefail
+die() { echo "FATAL: $*" >&2; exit 1; }
+lock_evidence() { :; }
+svc=yueboard
+REV=1111111111111111111111111111111111111111
+migration_args=()
+''' + text[start:end]
+        command = ['bash', '-c', script]
+    result = subprocess.run(command, env=env, text=True, capture_output=True, timeout=10)
+    local = online and (opt_in == 'yue-local-release' or path.endswith('kick-builds.sh'))
+    allowed = visibility in ('public', 'recover') or local
+    assert (result.returncode == 0) == allowed, result.stderr
+    assert trace.exists() == allowed
+    assert 'synthetic-sensitive-error' not in result.stdout + result.stderr
+    if not allowed:
+        assert 'FATAL' in result.stderr
+    if allowed and path.endswith('ship.sh'):
+        args = trace.read_text().splitlines()
+        assert ('runner=yue-local-release' if local else 'runner=ubuntu-24.04') in args
+    if allowed and path.endswith('kick-builds.sh'):
+        assert not any(arg.startswith('runner=') for arg in trace.read_text().splitlines())
+    if not (path.endswith('ship.sh') and local):
+        assert len(attempts.read_text().splitlines()) == (1 if visibility == 'public' else 3)
+
+
+def test_hosted_gate_rejects_fail_open_mutation(tmp_path, monkeypatch):
+    """A private repo must not dispatch if the exact visibility check is weakened."""
+    import shutil
+
+    mutated = tmp_path / 'mutated'
+    (mutated / 'scripts/lib').mkdir(parents=True)
+    for path in ('scripts/ship.sh', 'scripts/kick-builds.sh', 'scripts/lib/ci-runner.sh'):
+        shutil.copyfile(ROOT / path, mutated / path)
+    helper = mutated / 'scripts/lib/ci-runner.sh'
+    original = helper.read_text()
+    broken = original.replace('[[ "$visibility" == public ]]', '[[ -n "$visibility" ]]')
+    assert broken != original
+    helper.write_text(broken)
+    monkeypatch.setitem(globals(), 'ROOT', mutated)
+    for path in ('scripts/ship.sh', 'scripts/kick-builds.sh'):
+        case_dir = tmp_path / Path(path).stem
+        case_dir.mkdir()
+        with pytest.raises(AssertionError):
+            test_hosted_gate(case_dir, path, 'private', False, '')
diff --git a/scripts/test-ship-errexit-and-lock.py b/scripts/test-ship-errexit-and-lock.py
index 05e9614a..14efe859 100644
--- a/scripts/test-ship-errexit-and-lock.py
+++ b/scripts/test-ship-errexit-and-lock.py
@@ -120,7 +120,8 @@ if [ "$svc" = yueops ]; then
   migration_args=(-f migration_base=2222222222222222222222222222222222222222)
 fi
 ''' + dispatch + '\nprintf "association-ready:%s\\n" "$before"\n'
-    result = run_bash(script, env={**environment, "DISPATCH_SERVICE": service})
+    result = run_bash(script, env={**environment, "DISPATCH_SERVICE": service, "ROOT": str(ROOT),
+                                 "YUETO_CI_RUNNER": "yue-local-release"})
     def arguments(name):
         path = tmp_path / name
         return [arg.decode() for arg in path.read_bytes().split(b"\0")[:-1]] if path.exists() else []
@@ -1389,6 +1390,7 @@ sleep() {{ ticks=$((ticks + 1)); if ((ticks == 1)); then SECONDS=60; else SECOND
 ''' + dispatch + '\necho ASSOCIATED\n')
     result = run_bash(script, env={"PATH": f"{binary}:{os.environ['PATH']}",
                                  "REJECTION_FIXTURE": str(tmp_path), "REJECTION_CASE": case,
+                                 "YUETO_CI_RUNNER": "yue-local-release",
                                  **_lock_env(tmp_path, "terminal-test")})
     unproven = case not in ("rejected-read-unavailable", "success", "validation", "diagnostic-unreadable", "failure", "cancelled")
     assert bool(_locks(tmp_path)) == unproven

codex
指定 diff 新增了严格的公开仓库检查和组合测试；我会按 `guard-authoring` 技能核对被替换测试的覆盖范围，重点检查失败时是否仍拒绝派发。

hook: PreToolUse
hook: PreToolUse Completed
exec
/bin/zsh -lc 'cat .claude/skills/guard-authoring/SKILL.md' in /Users/j/codex-runs/mh1105/yt-110
 succeeded in 0ms:
---
name: guard-authoring
description: 'Use when changing Yue.to guards, contract checks, CI assertions or probes, reviewing their coverage, or diagnosing test import/fixture leakage. Ordinary fixes that only run existing checks do not trigger it.'
---

# Guard authoring (Yue.to)

The expensive failure is a green guard protecting nothing. The linked incident examples
occurred in actual production work.

Apply the checklist to the guard's actual inputs, dependencies and claimed
coverage. Running an existing check does not require redesigning it. A changed
assertion, scan boundary or success/failure classification does require this skill.
For import/fixture leakage, load [test isolation](references/test-isolation.md)
first; use the guard checklist only if guard coverage changes.

Before adding an invariant, establish which consumer needs it and check its
actual semantics. Challenge it with one realistic counterexample at that boundary:
subprocess execution for locks, a write failure for persistence, or raw single-target
output for collectors. Matching strings or unrelated runner-image labels cannot
establish those properties. Reuse the recorded interpreter/image, user and mounts;
classify failures as startup, collection or assertion before editing product code.

## Establish three facts before accepting green

1. Did this run reach the target? Zero executions is not a pass.
2. Did the scan cover the intended objects? Zero matches is not universal success.
3. Is the guarded layer the layer users and production actually encounter?

A negative answer makes the green result meaningless.

## Load only the relevant incident reference

Keep the common criteria and checklist below for guard changes. Read a reference
only when its failure class applies; the catalog is retained evidence, not an
extra audit assignment.

| Observed problem | Reference |
|---|---|
| A check never executes, scans nothing, targets the wrong layer, hides failure, or has no legitimate success path | [Coverage failures](references/coverage-failures.md), numbered incidents 1–9 |
| Wrong interpreter or checkout, SSH stdin, toolchain drift, signed installation closure, systemd results, incomplete pagination or runtime budgets | [Execution boundaries](references/execution-boundaries.md) |
| Import/fixture pollution, swallowed real I/O timeouts, fork deadlocks or teardown order | [Test isolation](references/test-isolation.md) |

## Required guard-delivery checklist

- [ ] Remove/rename/delete the protected object in an isolated mutation: the
  guard must fail, not mistake missing input for correctness.
- [ ] Exercise dependency failures the guard can encounter: wrong credentials
  for authenticated probes, network failure for remote probes, and permission
  failure for protected inputs. Verify their visible classifications.
- [ ] For scans, require a minimum target count; for a single target, prove arrival.
- [ ] Before counting negative observations, prove target-handler arrival and
  run controls protecting legitimate behavior.
- [ ] Register cross-repository guards in `scripts/check-all-contracts.sh`.
  `<path>` must name the sibling file actually read, not the guard script itself;
  otherwise missing-repository SKIP is unreachable. `guard-ci-claims` enforces it.
- [ ] Enumerate every criterion dimension, such as status × amount × ownership.
- [ ] Never duplicate live fleet counts. Since 2026-09-14, derive them from
  `servers.deploy_mode='direct'`; node-control-auth-migrate.py EXPECTED baselines
  no longer exist. Documentation may retain dated snapshots. Only mechanically
  enforced authoritative projections and date-anchored observations are exceptions.

## Workspace-only guards

`scripts/check-all-contracts.sh` alone knows the complete cross-repository guard
set. Single-repo CI cannot see all private siblings; a green component does not
establish a shared contract. The registry explicitly states whether a component
CI consumer exists.

A 2026-08-02 isolated Ops checkout showed whole tests skipped in ci-backend.yml:
`panel-deep-links` (2), `idempotency-catalog` (5, module-level pytestmark),
`registry-links` (2), and cross-surface design-token-gate cases. These and the
root scripts-level comparators run only in the workspace. Run the contract script
before pushing cross-repository changes.

`guard-ci-claims` (`scripts/check-guard-ci-claims.py`) fails when sibling-dependent
entries lack workspace-only marking or claimed component CI lacks a workflow
execution path. Missing repositories must report SKIP; `<path>` identifies the
actual sibling input, never the guard itself, so missing input cannot appear PASS.

`scripts/gauntlet.sh` similarly turns a former verbal pre-release promise into
execution: missing tools/repos are SKIP, never PASS, and too few actually executed
stages fail the gate.

hook: PreToolUse
hook: PreToolUse Completed
exec
/bin/zsh -lc 'git log --format=fuller e26b58600120ebb24a162f3f71fcf3ff2c25d4ff..f7da2118e1b6668a1bc65ee4400e1168d790c967 && git diff --check e26b58600120ebb24a162f3f71fcf3ff2c25d4ff f7da2118e1b6668a1bc65ee4400e1168d790c967' in /Users/j/codex-runs/mh1105/yt-110
 succeeded in 0ms:
commit f7da2118e1b6668a1bc65ee4400e1168d790c967
Author:     onesyue <47652916+onesyue@users.noreply.github.com>
AuthorDate: Thu Nov 5 03:31:51 2026 +0800
Commit:     onesyue <47652916+onesyue@users.noreply.github.com>
CommitDate: Thu Nov 5 03:31:51 2026 +0800

    ship: hosted CI only for a verified-public CI repo; self-hosted opt-in (YUETO_CI_RUNNER)

codex
VERDICT: approve

- 指定 diff 未发现可确认的正确性、安全性或回归问题，改动符合提交意图。
- 原有固定 runner 断言改为动态选择检查，并新增可见性异常、显式选择及失败放行变异测试，未见明显测试弱化。
- `git diff --check` 通过；本次仅静态审阅，未执行测试。
tokens used
34,234
VERDICT: approve

- 指定 diff 未发现可确认的正确性、安全性或回归问题，改动符合提交意图。
- 原有固定 runner 断言改为动态选择检查，并新增可见性异常、显式选择及失败放行变异测试，未见明显测试弱化。
- `git diff --check` 通过；本次仅静态审阅，未执行测试。
Finished: 2026-11-05T03:06:41Z exit=0
