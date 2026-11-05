# yueto #109 review at e26b58600120ebb24a162f3f71fcf3ff2c25d4ff

Reviewed range: 72de4d87e9a06feff9de8e97e52f27fe19d47880..e26b58600120ebb24a162f3f71fcf3ff2c25d4ff (post-merge backfill; codex on mac-5f08d00f, read-only sandbox)
Started: 2026-11-05T03:05:06Z

Reading additional input from stdin...
OpenAI Codex v0.166.0
--------
workdir: /Users/j/codex-runs/mh1105/yt-109
model: gpt-6-astra
provider: openai
approval: never
sandbox: read-only
reasoning effort: medium
reasoning summaries: none
session id: 01a1a9aa-d1b9-77b1-9fb8-b07d50c829a1
--------
user
You are reviewing merged PR onesyue/yueto #109 at exact head e26b58600120ebb24a162f3f71fcf3ff2c25d4ff. Review ONLY the diff: git diff 72de4d87e9a06feff9de8e97e52f27fe19d47880 e26b58600120ebb24a162f3f71fcf3ff2c25d4ff (and git log 72de4d87e9a06feff9de8e97e52f27fe19d47880..e26b58600120ebb24a162f3f71fcf3ff2c25d4ff). Do not modify files. Check correctness, regressions, weakened/removed tests, security, and that the change matches its title/intent. Output a final line exactly 'VERDICT: approve' or 'VERDICT: changes' followed by concise bullet findings.
2026-11-05T03:05:11.713355Z ERROR codex_models_manager::manager: failed to refresh available models: request timed out
hook: SessionStart
hook: SessionStart Completed
codex
我会只审查指定提交区间的 diff 和提交日志，检查回归、安全、测试变化及意图一致性，不修改文件。
hook: PreToolUse
hook: PreToolUse Completed
exec
/bin/zsh -lc 'cat CLAUDE.md' in /Users/j/codex-runs/mh1105/yt-109
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
/bin/zsh -lc 'git diff --stat 72de4d87e9a06feff9de8e97e52f27fe19d47880 e26b58600120ebb24a162f3f71fcf3ff2c25d4ff
git log --format=fuller 72de4d87e9a06feff9de8e97e52f27fe19d47880..e26b58600120ebb24a162f3f71fcf3ff2c25d4ff
git diff 72de4d87e9a06feff9de8e97e52f27fe19d47880 e26b58600120ebb24a162f3f71fcf3ff2c25d4ff' in /Users/j/codex-runs/mh1105/yt-109
 succeeded in 0ms:
 scripts/kick-builds.sh                |  6 +++
 scripts/lib/ship-ui.sh                |  7 +++-
 scripts/ship.sh                       |  7 +++-
 scripts/test-selfrun-dispatch.py      | 78 +++++++++++++++++++++++++++++++++++
 scripts/test-ship-errexit-and-lock.py | 25 +++++++++--
 5 files changed, 118 insertions(+), 5 deletions(-)
commit e26b58600120ebb24a162f3f71fcf3ff2c25d4ff
Author:     onesyue <47652916+onesyue@users.noreply.github.com>
AuthorDate: Thu Nov 5 02:09:13 2026 +0800
Commit:     onesyue <47652916+onesyue@users.noreply.github.com>
CommitDate: Thu Nov 5 02:09:13 2026 +0800

    ship: always dispatch build.yml on yue-local-release; fail closed without an online self-hosted runner
diff --git a/scripts/kick-builds.sh b/scripts/kick-builds.sh
index 14519a57..f07e0fb5 100755
--- a/scripts/kick-builds.sh
+++ b/scripts/kick-builds.sh
@@ -32,6 +32,12 @@ command -v gh >/dev/null 2>&1 || {
   exit 1
 }
 
+die() { echo "FATAL: $*" >&2; exit 1; }
+runner_status=$(gh api --paginate repos/onesyue/yueto-ci/actions/runners \
+  --jq '.runners[] | select(.status == "online" and any(.labels[]; .name == "yue-local-release")) | .status') \
+  || die "Cannot verify yue-local-release runner availability"
+grep -qx online <<<"$runner_status" || die "No online yue-local-release runner; refusing dispatch"
+
 if ! gh workflow run poll-sources.yml -R onesyue/yueto-ci -f dry_run="$DRY"; then
   echo "FATAL: 触发 poll-sources 失败（见上方 gh 报错）。常见原因：gh 未登录/凭据过期" >&2
   echo "      （gh auth status 查）、或工作站代理下 GitHub 连接抖动——重跑一次即可（poll-sources 有并发组，
diff --git a/scripts/lib/ship-ui.sh b/scripts/lib/ship-ui.sh
index b4133fdd..021927fe 100755
--- a/scripts/lib/ship-ui.sh
+++ b/scripts/lib/ship-ui.sh
@@ -469,10 +469,15 @@ else
   before=$(predispatch_read run-list | tr '\n' ' ') \
     || die "$COMPONENT 触发前读不到 build.yml 的 run 列表——没有集合差就不触发"
   log "触发 build+promote: $COMPONENT @ ${REV:0:12}"
+  # Fail closed before recording a pending dispatch; never fall back to hosted.
+  runner_status=$(gh api --paginate repos/onesyue/yueto-ci/actions/runners \
+    --jq '.runners[] | select(.status == "online" and any(.labels[]; .name == "yue-local-release")) | .status') \
+    || die "Cannot verify yue-local-release runner availability"
+  grep -qx online <<<"$runner_status" || die "No online yue-local-release runner; refusing dispatch"
   triggered_at=$(date -u +%s)
   lock_evidence pending "ci:$COMPONENT" "dispatch revision=$REV triggered_at=$triggered_at"
   gh workflow run build.yml -R onesyue/yueto-ci --ref master \
-     -f "service=${COMPONENT}" -f "ref=${REV}" -f promote=true >/dev/null \
+     -f "service=${COMPONENT}" -f "ref=${REV}" -f promote=true -f runner=yue-local-release >/dev/null \
     || die "$COMPONENT 的 build+promote 触发失败"
   got=""
   association_deadline=$((SECONDS + 180))
diff --git a/scripts/ship.sh b/scripts/ship.sh
index 93f03326..319ebc39 100755
--- a/scripts/ship.sh
+++ b/scripts/ship.sh
@@ -685,10 +685,15 @@ else
     log "触发 build+promote: $svc @ $REV"
     # Promotion trusts this workflow branch; make it explicit to avoid gh's
     # redundant default-branch lookup. The source revision remains a separate input.
+    # Fail closed before recording a pending dispatch; never fall back to hosted.
+    runner_status=$(gh api --paginate repos/onesyue/yueto-ci/actions/runners \
+      --jq '.runners[] | select(.status == "online" and any(.labels[]; .name == "yue-local-release")) | .status') \
+      || die "Cannot verify yue-local-release runner availability"
+    grep -qx online <<<"$runner_status" || die "No online yue-local-release runner; refusing dispatch"
     triggered_at=$(date -u +%s)
     lock_evidence pending "ci:$svc" "dispatch service=$svc revision=$REV triggered_at=$triggered_at"
     gh workflow run build.yml -R onesyue/yueto-ci --ref master \
-       -f service="$svc" -f ref="$REV" -f promote=true "${migration_args[@]}" >/dev/null \
+       -f service="$svc" -f ref="$REV" -f promote=true -f runner=yue-local-release "${migration_args[@]}" >/dev/null \
       || die "$svc 的 build+promote 触发失败（gh workflow run）"
     # 等这一次触发产生的新 run 出现（GitHub 排队通常 2-8 秒）
     got=""
diff --git a/scripts/test-selfrun-dispatch.py b/scripts/test-selfrun-dispatch.py
new file mode 100644
index 00000000..0bec586b
--- /dev/null
+++ b/scripts/test-selfrun-dispatch.py
@@ -0,0 +1,78 @@
+"""Execute each local dispatch boundary with real jq and isolated gh transport."""
+import json
+import os
+from pathlib import Path
+import re
+import subprocess
+
+import pytest
+
+ROOT = Path(__file__).resolve().parents[1]
+PATHS = ["scripts/ship.sh", "scripts/lib/ship-ui.sh", "scripts/kick-builds.sh"]
+
+
+def boundary(path):
+    text = (ROOT / path).read_text()
+    start = text.index('runner_status=$(gh api')
+    end = text.index('\n', text.index('|| die "No online', start))
+    guard = text[start:end]
+    joined = text[end:].replace('\\\n', ' ')
+    command = re.search(r'gh workflow run (?:build|poll-sources)\.yml[^\n]*', joined)[0]
+    if command.endswith('; then'):
+        command = command[:-6]
+    return guard + '\n' + command
+
+
+@pytest.mark.parametrize('path', PATHS)
+@pytest.mark.parametrize('case', ['online', 'busy', 'absent', 'offline', 'wrong-label', 'api-error', 'malformed', 'later-page'])
+def test_dispatch_boundary(tmp_path, path, case):
+    runner = {'status': 'offline' if case == 'offline' else 'online',
+              'busy': case == 'busy', 'labels': [{'name': 'other' if case == 'wrong-label' else 'yue-local-release'}]}
+    data = json.dumps({'runners': [] if case == 'absent' else [runner]})
+    if case == 'malformed':
+        data = 'not json'
+    if case == 'later-page':
+        data = '{"runners": []}\n' + data
+    gh = tmp_path / 'gh'
+    gh.write_text('''#!/bin/bash
+if [ "$1" = api ]; then
+  [ "$2" = --paginate ] || exit 91
+  [ "$3" = repos/onesyue/yueto-ci/actions/runners ] || exit 92
+  [ "$4" = --jq ] || exit 93
+  [ "$CASE" != api-error ] || exit 1
+  printf '%s\\n' "$DATA" | jq -r "$5"
+else
+  printf '%s\\n' "$@" > "$TRACE"
+fi
+''')
+    gh.chmod(0o755)
+    trace = tmp_path / 'dispatch'
+    script = '''set -euo pipefail
+die() { echo "FATAL: $*" >&2; exit 1; }
+svc=yueboard
+COMPONENT=ui-board-web
+REV=1111111111111111111111111111111111111111
+DRY=false
+migration_args=()
+'''+boundary(path)
+    result = subprocess.run(['bash', '-c', script], text=True, capture_output=True,
+                            env={**os.environ, 'PATH': str(tmp_path)+os.pathsep+os.environ['PATH'],
+                                 'DATA': data, 'CASE': case, 'TRACE': str(trace)})
+    if case in ('online', 'busy', 'later-page'):
+        assert result.returncode == 0, result.stderr
+        args = trace.read_text().splitlines()
+        if 'build.yml' in args:
+            assert 'runner=yue-local-release' in args
+    else:
+        assert result.returncode != 0
+        assert not trace.exists()
+
+
+def test_every_local_build_dispatch_is_pinned():
+    commands = []
+    for path in (ROOT / 'scripts').rglob('*.sh'):
+        text = re.sub(r'\\\n\s*', ' ', path.read_text())
+        commands.extend(line for line in text.splitlines()
+                        if not line.lstrip().startswith('#') and 'gh workflow run build.yml ' in line)
+    assert len(commands) == 2
+    assert all('-f runner=yue-local-release' in command for command in commands)
diff --git a/scripts/test-ship-errexit-and-lock.py b/scripts/test-ship-errexit-and-lock.py
index a6d7e254..05e9614a 100644
--- a/scripts/test-ship-errexit-and-lock.py
+++ b/scripts/test-ship-errexit-and-lock.py
@@ -149,7 +149,11 @@ import time
 root = Path(os.environ["DISPATCH_FIXTURE"])
 args = sys.argv[1:]
 if Path(sys.argv[0]).name == "gh":
-    if args[:2] == ["run", "list"]:
+    if args[:2] == ["api", "--paginate"]:
+        assert args[2] == "repos/onesyue/yueto-ci/actions/runners"
+        print(os.environ.get("RUNNER_STATUS", "online"))
+        sys.exit(int(os.environ.get("RUNNER_RC", "0")))
+    elif args[:2] == ["run", "list"]:
         kind = "list"
     elif args[:2] == ["workflow", "run"]:
         kind = "dispatch"
@@ -325,7 +329,7 @@ def test_workflow_dispatch_uses_trusted_branch_and_exact_business_inputs(tmp_pat
     assert listed == ["run", "list", "-R", "onesyue/yueto-ci", "--workflow", "build.yml",
                       "-L", "30", "--json", "databaseId", "-q", ".[].databaseId"]
     expected = ["workflow", "run", "build.yml", "-R", "onesyue/yueto-ci", "--ref", "master",
-                "-f", f"service={service}", "-f", "ref=" + "1" * 40, "-f", "promote=true"]
+                "-f", f"service={service}", "-f", "ref=" + "1" * 40, "-f", "promote=true", "-f", "runner=yue-local-release"]
     if service == "yueops":
         expected += ["-f", "migration_base=" + "2" * 40]
     assert dispatched == expected
@@ -1344,7 +1348,8 @@ root = Path(os.environ["REJECTION_FIXTURE"])
 f = json.loads((root / "fixture.json").read_text())
 a = sys.argv[1:]
 with (root / "calls").open("a") as out: out.write(json.dumps(a) + "\\n")
-if a[:2] == ["workflow", "run"]: pass
+if a[:2] == ["api", "--paginate"]: print("online")
+elif a[:2] == ["workflow", "run"]: pass
 elif a[:2] == ["run", "list"]: print("123:" + f["run"]["status"])
 elif a[:3] == ["run", "view", "123"] and "--json" in a and a[a.index("--json") + 1] in ("status", "conclusion"):
     if os.environ["REJECTION_CASE"].startswith("rejected-"): sys.exit(1)
@@ -1562,3 +1567,17 @@ def test_rejected_run_state_handoff_mutation_is_detected(tmp_path, monkeypatch):
     with pytest.raises(AssertionError):
         test_dispatch_plan_rejection_is_reported_only_for_our_run(
             tmp_path, "rejected-read-unavailable", "backend")
+
+
+@pytest.mark.parametrize("settings", [{"RUNNER_STATUS": ""}, {"RUNNER_STATUS": "offline"}, {"RUNNER_RC": 1}])
+def test_runner_unavailable_prevents_dispatch(tmp_path, settings):
+    result, _, dispatched = _exec_workflow_dispatch(tmp_path, **settings)
+    assert result.returncode != 0
+    assert "FATAL" in result.stderr
+    assert not dispatched
+
+
+def test_online_runner_dispatch_is_explicit(tmp_path):
+    result, _, dispatched = _exec_workflow_dispatch(tmp_path)
+    assert result.returncode == 0, result.stderr
+    assert "runner=yue-local-release" in dispatched

codex
指定 diff 保留了原有断言，并新增离线、错误标签、API 失败和分页场景覆盖。我会按 `guard-authoring` 技能核对这些测试是否真正约束新增派发逻辑。
hook: PreToolUse
hook: PreToolUse Completed
exec
/bin/zsh -lc 'cat .claude/skills/guard-authoring/SKILL.md
cat .claude/rules/guard-scripts.md' in /Users/j/codex-runs/mh1105/yt-109
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
---
paths:
  - "scripts/check-*.py"
  - "scripts/test-*.py"
  - ".claude/hooks/*.py"
  - "scripts/*.sh"
---

# Prove that a guard detects a real failure

Before delivery, establish all three properties:

1. **It fails when the protected fact is broken.** Run a mutation test; without
   this, the guard is not delivered.
2. **It checks the actual consumer.** Importability does not establish execution.
   Removing `if __name__ == "__main__"` can leave importlib-based tests green
   while the actual script silently exits without doing work.
3. **It has a legitimate path to success.** A permanently failing guard with no
   valid remediation is ineffective. Silent `return 1`, single instantaneous
   samples and text-only assertions require particular care.

A missing repository is SKIP, never PASS. Each registered `<path>` must identify
the sibling file actually consumed by the guard. Use `~/.venvs/yueto/bin/python`
for pytest; explicitly select `scripts/test-*.py` because their hyphenated names
are not discovered by pytest's default patterns.

Read `guard-authoring` for the incident patterns and mandatory checklist, and
`change-blast-radius` before removing checks or changing boundaries.

codex
VERDICT: approve

- 指定 diff 未发现明确的正确性、安全或回归问题；变更符合提交意图。
- 原有测试未削弱；新增测试覆盖 runner 不可用、API 失败及分页场景。
- 结论限于 diff 和提交日志的静态审查，未运行测试或验证外部工作流。
tokens used
33,765
VERDICT: approve

- 指定 diff 未发现明确的正确性、安全或回归问题；变更符合提交意图。
- 原有测试未削弱；新增测试覆盖 runner 不可用、API 失败及分页场景。
- 结论限于 diff 和提交日志的静态审查，未运行测试或验证外部工作流。
Finished: 2026-11-05T03:06:16Z exit=0
