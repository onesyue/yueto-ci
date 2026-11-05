# yueto #113 review at e65cba164f8858da9ac1a62016676c77343e31a0

Reviewed range: 738b27d41d763eb28d7531e656354f346f968666..e65cba164f8858da9ac1a62016676c77343e31a0 (post-merge backfill; codex on mac-5f08d00f, read-only sandbox)
Started: 2026-11-05T03:44:46Z

Reading additional input from stdin...
OpenAI Codex v0.166.0
--------
workdir: /Users/j/codex-runs/mh1105/yt-113
model: gpt-6-astra
provider: openai
approval: never
sandbox: read-only
reasoning effort: medium
reasoning summaries: none
session id: 01a1a9cf-24c9-7d63-ad0d-4d3528a114b3
--------
user
You are reviewing merged PR onesyue/yueto #113 at exact head e65cba164f8858da9ac1a62016676c77343e31a0. Review ONLY the diff: git diff 738b27d41d763eb28d7531e656354f346f968666 e65cba164f8858da9ac1a62016676c77343e31a0 (and git log 738b27d41d763eb28d7531e656354f346f968666..e65cba164f8858da9ac1a62016676c77343e31a0). Do not modify files. Check correctness, regressions, weakened/removed tests, security, and that the change matches its title/intent. Output a final line exactly 'VERDICT: approve' or 'VERDICT: changes' followed by concise bullet findings.
2026-11-05T03:44:52.287841Z ERROR codex_models_manager::manager: failed to refresh available models: request timed out
hook: SessionStart
hook: SessionStart Completed
codex
我会只审查指定提交区间的 diff 和提交日志，检查正确性、回归、测试削弱及安全问题，不修改文件。
hook: PreToolUse
hook: PreToolUse Completed
exec
/bin/zsh -lc 'cat CLAUDE.md' in /Users/j/codex-runs/mh1105/yt-113
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
/bin/zsh -lc 'git log --format=fuller 738b27d41d763eb28d7531e656354f346f968666..e65cba164f8858da9ac1a62016676c77343e31a0; git diff --stat 738b27d41d763eb28d7531e656354f346f968666 e65cba164f8858da9ac1a62016676c77343e31a0; git diff 738b27d41d763eb28d7531e656354f346f968666 e65cba164f8858da9ac1a62016676c77343e31a0' in /Users/j/codex-runs/mh1105/yt-113
 succeeded in 0ms:
commit e65cba164f8858da9ac1a62016676c77343e31a0
Author:     onesyue <47652916+onesyue@users.noreply.github.com>
AuthorDate: Thu Nov 5 11:20:55 2026 +0800
Commit:     onesyue <47652916+onesyue@users.noreply.github.com>
CommitDate: Thu Nov 5 11:20:55 2026 +0800

    fix(ship): keep observed CI terminal proof when closing failed preparation

commit e1fe6cb13c431e3ecbed733f2724c2aaf237a43f
Author:     onesyue <47652916+onesyue@users.noreply.github.com>
AuthorDate: Thu Nov 5 08:54:54 2026 +0800
Commit:     onesyue <47652916+onesyue@users.noreply.github.com>
CommitDate: Thu Nov 5 09:08:27 2026 +0800

    fix(ship): close failed preparation without clearing mutation evidence

commit 64435e44cbd8e157b88c12efcbbfe25b56709792
Author:     onesyue <47652916+onesyue@users.noreply.github.com>
AuthorDate: Thu Nov 5 08:48:09 2026 +0800
Commit:     onesyue <47652916+onesyue@users.noreply.github.com>
CommitDate: Thu Nov 5 09:08:26 2026 +0800

    fix(ship): retry authority reads only for transient transport errors

commit 24ea45375f63c66dd9e71c96d328c143861175f7
Author:     onesyue <47652916+onesyue@users.noreply.github.com>
AuthorDate: Thu Nov 5 08:47:06 2026 +0800
Commit:     onesyue <47652916+onesyue@users.noreply.github.com>
CommitDate: Thu Nov 5 09:08:26 2026 +0800

    fix(ship): reuse verified authority bindings for existing roots
 docs/release-chain-runbook.md         |  8 +++++
 scripts/lib/ship-panel-native.sh      | 18 ++++++++---
 scripts/release-lock.py               | 17 ++++++++--
 scripts/ship-sshd-authority.py        |  6 ++--
 scripts/ship.sh                       | 29 +++++++++++++++--
 scripts/test-release-lock.py          | 45 ++++++++++++++++++++++++++
 scripts/test-ship-errexit-and-lock.py | 54 +++++++++++++++++++++++++++++++
 scripts/test-ship-schema-recovery.py  | 16 +++++++---
 scripts/test-ship-sshd-authority.py   | 60 +++++++++++++++++++++++++++++++++--
 9 files changed, 230 insertions(+), 23 deletions(-)
diff --git a/docs/release-chain-runbook.md b/docs/release-chain-runbook.md
index 9e3471d1..cc302ab2 100644
--- a/docs/release-chain-runbook.md
+++ b/docs/release-chain-runbook.md
@@ -79,6 +79,14 @@ Deployment proof still requires the checked final readback. Missing CI or deploy
 proof retains the lock, prints the release refusal, and produces a nonzero exit;
 TTL, a dead PID, and publish-job success alone never authorize release.
 
+Before a deployment command is launched, ship records `deploy-preflight`.
+On failure, `pre-mutation-failed` closes only that preparation operation and
+preserves all pending CI evidence. `cutover-started` atomically replaces it with
+`deploy` before the remote command; any failure or lost reply thereafter still
+requires deployment readback. Panel configuration projection (including
+`--prepare-only`) is conservatively treated as the mutation boundary. An inherited
+lock receives failure evidence but remains owned by its original caller.
+
 ### Optional jump host, authority budgets, and release-root bytecode
 
 `ship.sh` always connects to `BASTION` (`${YUETO_BASTION:-bastion}`). That alias is the production host that runs the containers, the database, and the deploy root. `YUETO_SSH_PROXY_JUMP` is optional and is passed only as OpenSSH `ProxyJump` on that outer connection. The documented alias is `bastion-via-la`. Unset or empty is the direct-connection rollback. The inner `ssh -n` from the production host to the panel does not receive `ProxyJump`.
diff --git a/scripts/lib/ship-panel-native.sh b/scripts/lib/ship-panel-native.sh
index 18007cb0..5fc5409a 100644
--- a/scripts/lib/ship-panel-native.sh
+++ b/scripts/lib/ship-panel-native.sh
@@ -59,7 +59,7 @@ release_scp() {
 
 # BEGIN mint_release_root
 mint_release_root() {
-  local rev=$1 out attempt fetched=false
+  local rev=$1 out attempt fetched=false existing=false
   # Dynamically scoped only to mint SSH calls; all other transports stay unchanged.
   local SHIP_REMOTE_STEP="铸干净签名根 / mint_release_root"
   [[ "$rev" =~ ^[0-9a-f]{40}$ ]] || { printf '%s\n' "refusing to mint a non-revision"; return 1; }
@@ -78,7 +78,7 @@ mint_release_root() {
   case "$out" in
     "/var/lib/yueops-release-roots/$rev") root=$out ;;
     *"refusing to overwrite an existing strict root: /var/lib/yueops-release-roots/"$rev)
-      root=/var/lib/yueops-release-roots/$rev ;;
+      root=/var/lib/yueops-release-roots/$rev; existing=true ;;
     *) printf '%s\n' "$out"; return 1 ;;
   esac
   # 🚨 2026-09-15 实测：MATERIALIZE 中途失败会**留下一个只含 .git 的半成品目录**，
@@ -100,9 +100,17 @@ mint_release_root() {
     || { printf '%s\n' "$root 是半成品根（缺判据文件）——先把它挪走再重铸，别拿它部署"; return 1; }
   # The native authority signs host evidence separately from this release binding.
   # Missing/broken active authority cannot fall back to the legacy bootstrap gate.
-  python3 -B "$ROOT/scripts/ship-sshd-authority.py" --repository "$ROOT/yueops" \
-    --revision "$rev" --bastion "$BASTION" --apply >&2 \
-    || { echo "FATAL: mint_release_root authority binding failed" >&2; return 1; }
+  # Check verifies the current generations and their signed bindings, as well
+  # as the complete root. Never cache success across an authority change.
+  if $existing && python3 -B "$ROOT/scripts/ship-sshd-authority.py" --repository "$ROOT/yueops" \
+      --revision "$rev" --bastion "$BASTION" --check >&2; then
+    echo "mint_release_root: existing root authority check passed; reuse without signing" >&2
+  else
+    echo "mint_release_root: new root or authority check refused; apply bindings" >&2
+    python3 -B "$ROOT/scripts/ship-sshd-authority.py" --repository "$ROOT/yueops" \
+      --revision "$rev" --bastion "$BASTION" --apply >&2 \
+      || { echo "FATAL: mint_release_root authority binding failed" >&2; return 1; }
+  fi
   printf '%s\n' "$root"
 }
 
diff --git a/scripts/release-lock.py b/scripts/release-lock.py
index c65126b3..25851d2a 100644
--- a/scripts/release-lock.py
+++ b/scripts/release-lock.py
@@ -576,7 +576,7 @@ def owned_process(lock: dict, owner=None) -> bool:
 def terminal_proven(lock: dict) -> bool:
     evidence = lock.get('terminal_evidence')
     return (isinstance(evidence, dict) and evidence.get('state') in
-            {'ci-concluded', 'deploy-readback'} and isinstance(evidence.get('proof'), str)
+            {'ci-concluded', 'deploy-readback', 'pre-mutation-failed'} and isinstance(evidence.get('proof'), str)
             and bool(evidence['proof'].strip())
             and _valid_timestamp(evidence.get('at')) and not lock.get('pending_operations'))
 
@@ -611,7 +611,18 @@ def cmd_evidence(args: argparse.Namespace) -> int:
             continue
         payload = {k: v for k, v in lock.items() if not k.startswith('_') and k != 'stale'}
         pending = payload.setdefault('pending_operations', {})
-        if args.state == 'pending':
+        if args.state in {'pre-mutation-failed', 'cutover-started'}:
+            expected_key = 'deploy-preflight' if args.state == 'pre-mutation-failed' else 'deploy'
+            if args.key != expected_key or (args.state == 'pre-mutation-failed' and 'deploy' in pending):
+                print('REFUSED: deployment may have mutated services; retain pending evidence', file=sys.stderr)
+                return 1
+        if args.state == 'cutover-started':
+            # Atomically replace the read-only preparation with possible mutation.
+            # A lost remote reply can never turn this back into preflight evidence.
+            pending.pop('deploy-preflight', None)
+            pending['deploy'] = args.proof
+            payload.pop('terminal_evidence', None)
+        elif args.state == 'pending':
             pending[args.key] = args.proof
             payload.pop('terminal_evidence', None)
         else:
@@ -1008,7 +1019,7 @@ def main(argv: list[str] | None = None) -> int:
     p.set_defaults(func=cmd_release)
 
     p = sub.add_parser('evidence', help='Record terminal proof or a pending remote operation')
-    p.add_argument('--state', choices=('pending', 'ci-concluded', 'deploy-readback'), required=True)
+    p.add_argument('--state', choices=('pending', 'ci-concluded', 'deploy-readback', 'pre-mutation-failed', 'cutover-started'), required=True)
     p.add_argument('--key', required=True)
     p.add_argument('--proof', required=True)
     p.add_argument('--expect-sha256', type=record_sha256)
diff --git a/scripts/ship-sshd-authority.py b/scripts/ship-sshd-authority.py
index afbc35a0..9b78b345 100755
--- a/scripts/ship-sshd-authority.py
+++ b/scripts/ship-sshd-authority.py
@@ -74,10 +74,8 @@ def proxy_jump() -> str:
 
 
 def readonly_retryable(reason: str) -> bool:
-    """Transport and steal timeouts only. Signature and native refusals are not retried."""
-    if reason.startswith("command_failed_255"):
-        return True
-    return reason in {"command_failed_124:timeout", "command_failed_78:TimeoutExpired"}
+    """Retry only classified transient SSH failures, never native refusals."""
+    return reason in {"command_failed_255:" + code for code in _TRANSIENT_TRANSPORT}
 PRIMARY = "D9D3C6E59E7465BD07C2177142239A996FDA9F55"
 VERIFIER = "scripts/verify-signed-release-root-20260822.py"
 VERIFIER_SHA = "acab35cc20d9d21698f0b2c3869686297c15f3822ed62290a84c86b367153bbe"
diff --git a/scripts/ship.sh b/scripts/ship.sh
index 5477e0a6..b47f4c70 100755
--- a/scripts/ship.sh
+++ b/scripts/ship.sh
@@ -451,9 +451,10 @@ LOCK_REPOS="$COMPONENT,yueto-ci"
 # 面板部署与舰队滚动互斥（进程围栏 4 分钟 vs 排空门 30 秒），release-lock 用 fleet 表达它。
 if [ "$COMPONENT" = yueboard ] && $DEPLOY; then LOCK_REPOS="$LOCK_REPOS,fleet"; fi
 declare -A LOCK_CI_RUNS=()
+LOCK_CI_TERMINAL_PROOF=""
 release_ship_lock() {
   local rc=$? attempt key
-  $LOCK_HELD_BY_US || return "$rc"
+  local release_owned_lock=$LOCK_HELD_BY_US
   LOCK_HELD_BY_US=false
   # Publishing can finish before asynchronous validation. Reconcile the whole
   # run before release, including --no-deploy and --prepare-only exits. On an
@@ -469,6 +470,14 @@ release_ship_lock() {
     log "等待 CI 终态证据后释放发版锁（${attempt}/${attempts}）"
     sleep "${POLL_SECONDS:-30}"
   done
+  if [ "$rc" -ne 0 ]; then
+    # This closes only preparation. The lock refuses this evidence if a remote
+    # deploy may have started, and never clears outstanding CI operations.
+    python3 "$RELEASE_LOCK_PY" evidence --state pre-mutation-failed \
+      --key deploy-preflight --proof "ship exited before service mutation rc=$rc${LOCK_CI_TERMINAL_PROOF:+; $LOCK_CI_TERMINAL_PROOF}" \
+      || log "保留部署未完成证据：服务可能已开始变更"
+  fi
+  $release_owned_lock || return "$rc"
   if ! python3 "$RELEASE_LOCK_PY" release; then
     echo "⚠ 发版在途锁释放失败——保留未完成证据；检查 scripts/release-lock.py status" >&2
     [ "$rc" -ne 0 ] || rc=1
@@ -505,6 +514,9 @@ lock_ci_concluded() {
   case "$conclusion" in
     success|failure|cancelled|timed_out|action_required|neutral|skipped|stale|startup_failure)
       lock_evidence ci-concluded "ci:$key" "onesyue/yueto-ci run=$run status=completed conclusion=$conclusion"
+      # Retain observed proof when exit cleanup closes failed preparation,
+      # even if subsequent CI reads are unavailable. Pending keys still fence release.
+      LOCK_CI_TERMINAL_PROOF+="onesyue/yueto-ci run=$run status=completed conclusion=$conclusion; "
       unset 'LOCK_CI_RUNS[$key]' ;;
   esac
 }
@@ -516,7 +528,12 @@ lock_heartbeat() {
 lock_rc=0
 lock_out=$(python3 "$RELEASE_LOCK_PY" holds --repos "$LOCK_REPOS" 2>&1) || lock_rc=$?
 case "$lock_rc" in
-  0) log "发版在途锁：本会话已持有 ${LOCK_REPOS}（${lock_out}）——沿用，退出时不释放" ;;
+  0)
+    log "发版在途锁：本会话已持有 ${LOCK_REPOS}（${lock_out}）——沿用，退出时不释放"
+    trap 'exit 130' INT
+    trap 'exit 143' TERM HUP
+    trap release_ship_lock EXIT ;;
+
   3)
     # 信号转成 exit，EXIT trap 才会跑（被 kill/Ctrl-C 时锁不能留成 3 小时后才 stale 的死锁）。
     trap 'exit 130' INT
@@ -1133,7 +1150,9 @@ log "投影 release.yaml 到 bastion（fleet-reconcile 的期望副本）"
 publish_release_yaml_to_bastion
 
 if [ "$PREPARE_ONLY" = true ]; then
+  lock_evidence cutover-started deploy "panel preparation may mutate configuration"
   ship_panel_prepare
+  lock_evidence deploy-readback deploy "signed panel preparation completed with exact-byte readback"
   log "PANEL_PREPARE_ONLY_OK: signed inputs and recovery images prepared; no migration or deployment performed"
   exit 0
 fi
@@ -1146,7 +1165,7 @@ fi
 
 # ── 6. 部署 ────────────────────────────────────────────────────────────────
 lock_heartbeat
-lock_evidence pending deploy "component=$COMPONENT revision=$REV"
+lock_evidence pending deploy-preflight "component=$COMPONENT revision=$REV"
 case "$COMPONENT" in
   yueops)
     # 坑 A：/opt/yueops 结构上过不了 signed-release-root 断言（带 ignored 条目），
@@ -1159,6 +1178,7 @@ case "$COMPONENT" in
       --revision "$REV" --bastion "$BASTION" --check \
       || die "SSH authority release preflight failed before Ops deployment"
     log "部署三服务（同 revision 签名 digest 门）"
+    lock_evidence cutover-started deploy "component=$COMPONENT revision=$REV remote deploy may mutate services"
     release_ssh "$BASTION" \
       "env -i PATH=/usr/bin:/bin:/usr/local/bin HOME=/root PYTHONDONTWRITEBYTECODE=1 /bin/bash -p '$RROOT/scripts/deploy-yueops-digests.sh' \
          --source-revision $REV \
@@ -1186,6 +1206,8 @@ case "$COMPONENT" in
       || log "  ⚠ 未能启动 yueops-auto-pull（部署已完成）；手工：ssh $BASTION systemctl start --no-block yueops-auto-pull.service"
     ;;
   yueboard)
+    # Preparation can project service configuration; mark conservatively before it.
+    lock_evidence cutover-started deploy "component=$COMPONENT revision=$REV panel preparation may mutate configuration"
     ship_panel_prepare
     ship_panel_deploy
     ;;
@@ -1221,4 +1243,5 @@ else
   log "完成：${COMPONENT} 的源代码、pin、promote 与生产版本已对齐。"
 fi
 
+lock_evidence deploy-readback deploy-preflight "preparation completed"
 lock_evidence deploy-readback deploy "$FINAL_STATE"
diff --git a/scripts/test-release-lock.py b/scripts/test-release-lock.py
index 2c31a972..9794ee6b 100644
--- a/scripts/test-release-lock.py
+++ b/scripts/test-release-lock.py
@@ -912,3 +912,48 @@ def test_actually_invoking_a_release_script_still_fires(tmp_path: Path) -> None:
 
 if __name__ == "__main__":
     raise SystemExit(pytest.main([__file__, "-q"]))
+
+
+@pytest.mark.parametrize('pending,key,accepted', [
+    ({'deploy-preflight': 'root check'}, 'deploy-preflight', True),
+    ({'deploy': 'remote started'}, 'deploy-preflight', False),
+    ({'ci:yueops': 'unknown'}, 'ci:yueops', False),
+    ({'ci:yueops': 'unknown', 'deploy-preflight': 'root check'}, 'deploy-preflight', True),
+])
+def test_pre_mutation_failure_cannot_clear_mutation_or_ci(tmp_path, monkeypatch, pending, key, accepted):
+    from types import SimpleNamespace
+    module = load_module(tmp_path)
+    path = tmp_path / 'owned.json'
+    record = {'owner': 'fixture', 'pending_operations': pending}
+    path.write_text(json.dumps(record))
+    monkeypatch.setattr(module, 'load_locks', lambda **kwargs: [{**record, '_path': str(path)}])
+    monkeypatch.setattr(module, 'owned_process', lambda _: True)
+    monkeypatch.setattr(module, '_require_inventory_inode', lambda: None)
+    args = SimpleNamespace(state='pre-mutation-failed', key=key, proof='failed before remote launch', expect_sha256=None)
+    assert module.cmd_evidence(args) == (0 if accepted else 1)
+    updated = json.loads(path.read_text())
+    if accepted:
+        assert 'deploy-preflight' not in updated['pending_operations']
+        assert module.terminal_proven(updated) == ('ci:yueops' not in pending)
+        if 'ci:yueops' in pending:
+            assert updated['pending_operations']['ci:yueops'] == 'unknown'
+    else:
+        assert updated == record
+
+
+def test_cutover_atomically_replaces_preflight_and_preserves_ci(tmp_path, monkeypatch):
+    from types import SimpleNamespace
+    module = load_module(tmp_path)
+    path = tmp_path / 'owned.json'
+    record = {'owner': 'fixture', 'pending_operations': {'deploy-preflight': 'root', 'ci:yueops': 'unknown'},
+              'terminal_evidence': {'state': 'pre-mutation-failed', 'proof': 'old', 'at': 1}}
+    path.write_text(json.dumps(record))
+    monkeypatch.setattr(module, 'load_locks', lambda **kwargs: [{**record, '_path': str(path)}])
+    monkeypatch.setattr(module, 'owned_process', lambda _: True)
+    monkeypatch.setattr(module, '_require_inventory_inode', lambda: None)
+    args = SimpleNamespace(state='cutover-started', key='deploy', proof='remote launch', expect_sha256=None)
+    assert module.cmd_evidence(args) == 0
+    updated = json.loads(path.read_text())
+    assert updated['pending_operations'] == {'deploy': 'remote launch', 'ci:yueops': 'unknown'}
+    assert 'terminal_evidence' not in updated
+    assert not module.terminal_proven(updated)
diff --git a/scripts/test-ship-errexit-and-lock.py b/scripts/test-ship-errexit-and-lock.py
index 14efe859..4c54a324 100644
--- a/scripts/test-ship-errexit-and-lock.py
+++ b/scripts/test-ship-errexit-and-lock.py
@@ -1583,3 +1583,57 @@ def test_online_runner_dispatch_is_explicit(tmp_path):
     result, _, dispatched = _exec_workflow_dispatch(tmp_path)
     assert result.returncode == 0, result.stderr
     assert "runner=yue-local-release" in dispatched
+
+
+@pytest.mark.parametrize('cutover,ci_pending', [(False, False), (False, True), (True, False), (True, True)])
+def test_pre_mutation_failure_closes_only_preparation(tmp_path, cutover, ci_pending):
+    tail = 'lock_evidence pending deploy-preflight "preparing signed root"\n'
+    if ci_pending:
+        tail += 'lock_evidence pending ci:yueops "run still unknown"\n'
+    if cutover:
+        tail += 'lock_evidence cutover-started deploy "remote may mutate services"\n'
+    result = _exec_lock(tmp_path, tail + 'die "injected failure"\n')
+    assert result.returncode == 1
+    assert bool(_locks(tmp_path)) == (cutover or ci_pending)
+    records = _locks(tmp_path) or [json.loads(p.read_text()) for p in (tmp_path / 'locks/.retired').glob('*.record')]
+    assert records
+    for record in records:
+        pending = record.get('pending_operations', {})
+        assert ('deploy' in pending) == cutover
+        assert ('ci:yueops' in pending) == ci_pending
+        assert 'deploy-preflight' not in pending
+        if not cutover:
+            assert record['terminal_evidence']['state'] == 'pre-mutation-failed'
+
+
+def test_deploy_consumers_record_cutover_before_remote_mutation():
+    text = SHIP.read_text()
+    deploy = text.split('# ── 6. 部署', 1)[1].split('# ── 7.', 1)[0]
+    ops, panel = deploy.split('  yueboard)', 1)
+    assert ops.index('lock_evidence cutover-started deploy') < ops.index('release_ssh "$BASTION"')
+    assert panel.index('lock_evidence cutover-started deploy') < panel.index('ship_panel_prepare')
+
+
+@pytest.mark.parametrize('inherited', [False, True])
+def test_failed_ship_records_evidence_but_releases_only_own_lock(tmp_path, inherited):
+    trace = tmp_path / 'calls'
+    stub = '''python3() {
+  printf '%s\\n' "$*" >> "$TRACE"
+  case "$*" in *" holds "*) return "$HOLDS_RC";; esac
+  return 0
+}
+'''
+    script = ('set -Eeuo pipefail\n' + header() + stub
+              + f'ROOT="{ROOT}"; COMPONENT=yueops; DEPLOY=true\n'
+              + _lock_block() + '\ndie "injected failure"\n')
+    result = run_bash(script, env={'TRACE': str(trace), 'HOLDS_RC': '0' if inherited else '3'})
+    assert result.returncode == 1
+    calls = trace.read_text().splitlines()
+    assert any('evidence --state pre-mutation-failed --key deploy-preflight' in call for call in calls)
+    assert any(call.endswith(' release') for call in calls) != inherited
+
+
+def test_prepare_only_marks_mutation_and_closes_only_after_preparation():
+    text = SHIP.read_text().split('if [ "$PREPARE_ONLY" = true ]; then\n', 1)[1].split('\nfi', 1)[0]
+    assert text.index('lock_evidence cutover-started deploy') < text.index('ship_panel_prepare')
+    assert text.index('ship_panel_prepare') < text.index('lock_evidence deploy-readback deploy')
diff --git a/scripts/test-ship-schema-recovery.py b/scripts/test-ship-schema-recovery.py
index ee55774c..3600f648 100644
--- a/scripts/test-ship-schema-recovery.py
+++ b/scripts/test-ship-schema-recovery.py
@@ -803,14 +803,20 @@ def test_public_cli_refuses_invalid_preparation_before_detach(args):
     assert '已 detach' not in p.stdout
 
 
-def test_prepare_only_executes_preparation_and_exits_before_deploy():
+@pytest.mark.parametrize('failure', [False, True])
+def test_prepare_only_executes_preparation_and_exits_before_deploy(failure):
     script = (ROOT / 'scripts/ship.sh').read_text()
-    start = script.index('if [ "$PREPARE_ONLY" = true ]; then\n  ship_panel_prepare')
+    start = script.index('if [ "$PREPARE_ONLY" = true ]; then\n')
     end = script.index('\n# ── 6.', start)
-    p = bash('PREPARE_ONLY=true\nship_panel_prepare() { echo PREPARED; }\nlog() { echo "$*"; }\n'
+    prepare = 'echo PREPARED; return ' + ('1' if failure else '0')
+    p = bash('PREPARE_ONLY=true\nship_panel_prepare() { ' + prepare + '; }\n'
+             + 'lock_evidence() { echo "EVIDENCE $*"; }\nlog() { echo "$*"; }\n'
              + script[start:end] + '\necho DEPLOYED\n')
-    assert p.returncode == 0
-    assert 'PREPARED' in p.stdout and 'PREPARE_ONLY_OK' in p.stdout and 'DEPLOYED' not in p.stdout
+    assert p.returncode == (1 if failure else 0)
+    assert p.stdout.index('EVIDENCE cutover-started deploy') < p.stdout.index('PREPARED')
+    assert ('EVIDENCE deploy-readback deploy' in p.stdout) != failure
+    assert ('PREPARE_ONLY_OK' in p.stdout) != failure
+    assert 'DEPLOYED' not in p.stdout
 
 
 @pytest.mark.skipif(os.geteuid() != 0, reason='actual protected root-owned remote filesystem')
diff --git a/scripts/test-ship-sshd-authority.py b/scripts/test-ship-sshd-authority.py
index bfe32880..aaef7c8e 100644
--- a/scripts/test-ship-sshd-authority.py
+++ b/scripts/test-ship-sshd-authority.py
@@ -108,6 +108,20 @@ def native_ship_text():
     return text
 
 
+@pytest.mark.parametrize('code', sorted(m._TRANSIENT_TRANSPORT))
+def test_all_classified_transient_transport_errors_retry(monkeypatch, code):
+    calls = []
+    def fake_run(argv, **kwargs):
+        calls.append(argv)
+        if len(calls) == 1:
+            raise m.Refused('command_failed_255:' + code)
+        return subprocess.CompletedProcess(argv, 0, m.canonical(state()), b'')
+    monkeypatch.setattr(m, 'run', fake_run)
+    monkeypatch.setattr(m.time, 'sleep', lambda _: None)
+    assert _release_for_remote().remote('status') == state()
+    assert len(calls) == 2
+
+
 def test_active_signs_both_generations_and_exact_raw_bytes(tmp_path):
     release = Release(tmp_path)
     assert release.execute(True)['bindings_verified'] is True
@@ -445,6 +459,9 @@ def test_readonly_retry_budget_exhaustion_does_not_start_another_attempt(monkeyp
     'command_failed_78:native_command_failed',
     'command_failed_78:source_verification_failed',
     'command_failed_1',
+    'command_failed_255',
+    'command_failed_255:ssh_unknown',
+    'command_failed_255:ssh_server_alive_timeout',
 ])
 def test_readonly_remote_refusal_is_not_retried(monkeypatch, reason):
     calls = []
@@ -828,7 +845,7 @@ def _release_for_remote():
 
 
 @pytest.mark.parametrize("reason", ["command_failed_124:timeout", "command_failed_78:TimeoutExpired"])
-def test_readonly_steal_timeout_retries_then_succeeds(monkeypatch, reason):
+def test_readonly_native_timeout_is_not_retried(monkeypatch, reason):
     calls = []
 
     def fake_run(argv, *, data=None, timeout=90):
@@ -840,8 +857,9 @@ def test_readonly_steal_timeout_retries_then_succeeds(monkeypatch, reason):
     phase_seen = ["status"]
     monkeypatch.setattr(m.time, "sleep", lambda _seconds: None)
     monkeypatch.setattr(m, "run", fake_run)
-    assert _release_for_remote().remote("status") == state()
-    assert calls == ["status", "status"]
+    with pytest.raises(m.Refused, match=reason):
+        _release_for_remote().remote("status")
+    assert calls == ["status"]
 
 
 @pytest.mark.parametrize("phase", ["request", "install"])
@@ -1076,3 +1094,39 @@ def test_local_refusal_metadata_is_sanitized_again(monkeypatch):
     with pytest.raises(m.Refused) as caught:
         m.run(['fixture'])
     assert caught.value.detail == 'psql rc=3: <redacted>'
+
+
+@pytest.mark.parametrize('existing,check_rc,apply_rc,expected', [
+    (True, 0, 99, ['--check']),
+    (True, 78, 0, ['--check', '--apply']),
+    (True, 78, 78, ['--check', '--apply']),
+    (False, 99, 0, ['--apply']),
+])
+def test_mint_reuses_only_current_verified_authority(tmp_path, existing, check_rc, apply_rc, expected):
+    native = (ROOT / 'scripts/lib/ship-panel-native.sh').read_text()
+    mint = native.split('# BEGIN mint_release_root\n')[1].split('# END mint_release_root')[0]
+    trace = tmp_path / 'authority-calls'
+    output = '/var/lib/yueops-release-roots/' + REV
+    if existing:
+        output = 'make-release-root: refusing to overwrite an existing strict root: ' + output
+    script = '''set -eu
+release_ssh() {
+  case "$*" in *make-release-root*) printf '%s\\n' "$MINT_OUTPUT";; esac
+}
+python3() {
+  local mode="${@: -1}"
+  printf '%s\\n' "$mode" >> "$TRACE"
+  if [ "$mode" = --check ]; then return "$CHECK_RC"; fi
+  return "$APPLY_RC"
+}
+''' + mint + '\nroot=$(mint_release_root "$REV") || exit 91\nprintf "%s\\n" "$root"\n'
+    result = subprocess.run(['/bin/bash', '-c', script], capture_output=True, text=True,
+                            env={**os.environ, 'ROOT': str(ROOT), 'BASTION': 'fixture',
+                                 'REV': REV, 'TRACE': str(trace), 'MINT_OUTPUT': output,
+                                 'CHECK_RC': str(check_rc), 'APPLY_RC': str(apply_rc)})
+    assert trace.read_text().splitlines() == expected
+    success = check_rc == 0 if existing and check_rc == 0 else apply_rc == 0
+    assert result.returncode == (0 if success else 91)
+    if success:
+        assert result.stdout.strip() == '/var/lib/yueops-release-roots/' + REV
+    assert ('reuse without signing' if expected == ['--check'] else 'apply bindings') in result.stderr

hook: PreToolUse
hook: PreToolUse Completed
exec
/bin/zsh -lc 'git log --oneline 738b27d41d763eb28d7531e656354f346f968666..e65cba164f8858da9ac1a62016676c77343e31a0; git diff --stat 738b27d41d763eb28d7531e656354f346f968666 e65cba164f8858da9ac1a62016676c77343e31a0; git diff 738b27d41d763eb28d7531e656354f346f968666 e65cba164f8858da9ac1a62016676c77343e31a0 -- scripts/lib/ship-panel-native.sh scripts/release-lock.py' in /Users/j/codex-runs/mh1105/yt-113
 succeeded in 0ms:
e65cba16 fix(ship): keep observed CI terminal proof when closing failed preparation
e1fe6cb1 fix(ship): close failed preparation without clearing mutation evidence
64435e44 fix(ship): retry authority reads only for transient transport errors
24ea4537 fix(ship): reuse verified authority bindings for existing roots
 docs/release-chain-runbook.md         |  8 +++++
 scripts/lib/ship-panel-native.sh      | 18 ++++++++---
 scripts/release-lock.py               | 17 ++++++++--
 scripts/ship-sshd-authority.py        |  6 ++--
 scripts/ship.sh                       | 29 +++++++++++++++--
 scripts/test-release-lock.py          | 45 ++++++++++++++++++++++++++
 scripts/test-ship-errexit-and-lock.py | 54 +++++++++++++++++++++++++++++++
 scripts/test-ship-schema-recovery.py  | 16 +++++++---
 scripts/test-ship-sshd-authority.py   | 60 +++++++++++++++++++++++++++++++++--
 9 files changed, 230 insertions(+), 23 deletions(-)
diff --git a/scripts/lib/ship-panel-native.sh b/scripts/lib/ship-panel-native.sh
index 18007cb0..5fc5409a 100644
--- a/scripts/lib/ship-panel-native.sh
+++ b/scripts/lib/ship-panel-native.sh
@@ -59,7 +59,7 @@ release_scp() {
 
 # BEGIN mint_release_root
 mint_release_root() {
-  local rev=$1 out attempt fetched=false
+  local rev=$1 out attempt fetched=false existing=false
   # Dynamically scoped only to mint SSH calls; all other transports stay unchanged.
   local SHIP_REMOTE_STEP="铸干净签名根 / mint_release_root"
   [[ "$rev" =~ ^[0-9a-f]{40}$ ]] || { printf '%s\n' "refusing to mint a non-revision"; return 1; }
@@ -78,7 +78,7 @@ mint_release_root() {
   case "$out" in
     "/var/lib/yueops-release-roots/$rev") root=$out ;;
     *"refusing to overwrite an existing strict root: /var/lib/yueops-release-roots/"$rev)
-      root=/var/lib/yueops-release-roots/$rev ;;
+      root=/var/lib/yueops-release-roots/$rev; existing=true ;;
     *) printf '%s\n' "$out"; return 1 ;;
   esac
   # 🚨 2026-09-15 实测：MATERIALIZE 中途失败会**留下一个只含 .git 的半成品目录**，
@@ -100,9 +100,17 @@ mint_release_root() {
     || { printf '%s\n' "$root 是半成品根（缺判据文件）——先把它挪走再重铸，别拿它部署"; return 1; }
   # The native authority signs host evidence separately from this release binding.
   # Missing/broken active authority cannot fall back to the legacy bootstrap gate.
-  python3 -B "$ROOT/scripts/ship-sshd-authority.py" --repository "$ROOT/yueops" \
-    --revision "$rev" --bastion "$BASTION" --apply >&2 \
-    || { echo "FATAL: mint_release_root authority binding failed" >&2; return 1; }
+  # Check verifies the current generations and their signed bindings, as well
+  # as the complete root. Never cache success across an authority change.
+  if $existing && python3 -B "$ROOT/scripts/ship-sshd-authority.py" --repository "$ROOT/yueops" \
+      --revision "$rev" --bastion "$BASTION" --check >&2; then
+    echo "mint_release_root: existing root authority check passed; reuse without signing" >&2
+  else
+    echo "mint_release_root: new root or authority check refused; apply bindings" >&2
+    python3 -B "$ROOT/scripts/ship-sshd-authority.py" --repository "$ROOT/yueops" \
+      --revision "$rev" --bastion "$BASTION" --apply >&2 \
+      || { echo "FATAL: mint_release_root authority binding failed" >&2; return 1; }
+  fi
   printf '%s\n' "$root"
 }
 
diff --git a/scripts/release-lock.py b/scripts/release-lock.py
index c65126b3..25851d2a 100644
--- a/scripts/release-lock.py
+++ b/scripts/release-lock.py
@@ -576,7 +576,7 @@ def owned_process(lock: dict, owner=None) -> bool:
 def terminal_proven(lock: dict) -> bool:
     evidence = lock.get('terminal_evidence')
     return (isinstance(evidence, dict) and evidence.get('state') in
-            {'ci-concluded', 'deploy-readback'} and isinstance(evidence.get('proof'), str)
+            {'ci-concluded', 'deploy-readback', 'pre-mutation-failed'} and isinstance(evidence.get('proof'), str)
             and bool(evidence['proof'].strip())
             and _valid_timestamp(evidence.get('at')) and not lock.get('pending_operations'))
 
@@ -611,7 +611,18 @@ def cmd_evidence(args: argparse.Namespace) -> int:
             continue
         payload = {k: v for k, v in lock.items() if not k.startswith('_') and k != 'stale'}
         pending = payload.setdefault('pending_operations', {})
-        if args.state == 'pending':
+        if args.state in {'pre-mutation-failed', 'cutover-started'}:
+            expected_key = 'deploy-preflight' if args.state == 'pre-mutation-failed' else 'deploy'
+            if args.key != expected_key or (args.state == 'pre-mutation-failed' and 'deploy' in pending):
+                print('REFUSED: deployment may have mutated services; retain pending evidence', file=sys.stderr)
+                return 1
+        if args.state == 'cutover-started':
+            # Atomically replace the read-only preparation with possible mutation.
+            # A lost remote reply can never turn this back into preflight evidence.
+            pending.pop('deploy-preflight', None)
+            pending['deploy'] = args.proof
+            payload.pop('terminal_evidence', None)
+        elif args.state == 'pending':
             pending[args.key] = args.proof
             payload.pop('terminal_evidence', None)
         else:
@@ -1008,7 +1019,7 @@ def main(argv: list[str] | None = None) -> int:
     p.set_defaults(func=cmd_release)
 
     p = sub.add_parser('evidence', help='Record terminal proof or a pending remote operation')
-    p.add_argument('--state', choices=('pending', 'ci-concluded', 'deploy-readback'), required=True)
+    p.add_argument('--state', choices=('pending', 'ci-concluded', 'deploy-readback', 'pre-mutation-failed', 'cutover-started'), required=True)
     p.add_argument('--key', required=True)
     p.add_argument('--proof', required=True)
     p.add_argument('--expect-sha256', type=record_sha256)

codex
改动集中在复用 SSH authority 签名、限制只读重试，以及区分部署准备失败和已开始变更的锁证据。我会继续检查退出清理与锁状态转换；测试没有删除，但超时重试测试的预期发生了变化。此次涉及守卫覆盖审查，我会使用 `guard-authoring` 技能。
hook: PreToolUse
hook: PreToolUse Completed
exec
/bin/zsh -lc 'cat .agents/skills/guard-authoring/SKILL.md; cat .claude/rules/guard-scripts.md' in /Users/j/codex-runs/mh1105/yt-113
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

hook: PreToolUse
hook: PreToolUse Completed
exec
/bin/zsh -lc 'git diff -U65 738b27d41d763eb28d7531e656354f346f968666 e65cba164f8858da9ac1a62016676c77343e31a0 -- scripts/ship.sh scripts/release-lock.py scripts/ship-sshd-authority.py docs/release-chain-runbook.md' in /Users/j/codex-runs/mh1105/yt-113
 succeeded in 0ms:
diff --git a/docs/release-chain-runbook.md b/docs/release-chain-runbook.md
index 9e3471d1..cc302ab2 100644
--- a/docs/release-chain-runbook.md
+++ b/docs/release-chain-runbook.md
@@ -17,130 +17,138 @@ Follow this order under the registered release owner:
    `scripts/heavy-run.sh --exclusive bash scripts/gauntlet.sh`. Direct gauntlet
    invocation exits 2; `--fast` is not release evidence. Heavy-run admission
    waits at most 600 seconds by default (`--wait-seconds` selects a finite budget)
    and returns 75 without starting the command if admission expires. This is
    separate from an admitted job's runtime and the central build queue.
 2. Verify the signed `release.yaml` baseline and reviewed candidate inputs;
    use `yueto-ci` for signed server builds/promotion and `yuelink-ci` for client
    delivery. Private-repository Actions are not release acceptance evidence.
 3. After promotion, run `scripts/ship.sh <product> --from-promoted --foreground` for each
    authorized server product. The driver verifies immutable artifacts, writes
    and seals the resulting desired state, publishes it and performs that
    product's deployment step. A newly promoted digest can only be recorded
    after promotion; the signed baseline before the build is not its receipt.
 4. Finish the explicit Node rollout when applicable, then route-sync, required
    signed Board migrations, and panel deployment. Defer
    `scripts/ship.sh yueboard --from-promoted --foreground` until those prerequisites finish:
    it deploys the panel immediately. Node ship only publishes desired state;
    it does not roll the fleet. Keep panel deployment and fleet rollout serial.
 5. Read back signed desired state, promoted identity, actual running digest and
    revision, readiness and the affected business results. Preserve the native
    release rollback and interrupted-transaction recovery paths.
 
 Non-interactive and recognized agent invocations detach by default. Use
 `--foreground` (or `--no-detach`) whenever a following command depends on the
 release exit status. An explicit `--detach` returns zero only after startup;
 read the printed `<log>.run.json` and require a numeric `exit_code` of zero before
 starting dependent rollout or deployment steps. `exit_code: null` is pending,
 not success; an absent or unreadable receipt is unknown. Inspect the existing
 log and receipt before retrying an unacknowledged launch.
 
 Backup creation/verification, off-site copies, PITR/disaster-restore drills and
 backup retirement are canceled by the owner's 2026-10-20 decision
 ([current plan, R4.2b](2026-10-17-whole-estate-execution-plan.md#r42b-owner-canceled-backup-and-restore-scope--2026-10-20)).
 They are not release prerequisites. This does not authorize changing installed
 schedules, deleting stored data or abandoning release rollback, live replication
 or interrupted transactions. Do not clear `report-outbox`, contact `yue-tw`,
 change its host-key trust, or hide Taiwan subscription nodes 47/49.
 
 ## 0. 先问「现在在哪儿」
 
 ```bash
 scripts/release-state.py            # 四个真相并排：HEAD / 评审 pin / 已 promote / 生产在跑
 scripts/release-state.py --fleet -v # additionally 扫每台直连机的实际 revision（慢）
 ```
 
 这一步以前要 ~15 条命令加一次 SSH 全队扫描。**够不到的行报 UNKNOWN，永远不报 OK。**
 
 2026-09-27 起（深审 R4/R5）：production 列不再只看容器的 revision 标签——面板与三服务容器
 必须 `State.Status=running` 且运行镜像的 RepoDigests 含签名 desired 的 digest；没在跑 / digest
 不符记 DRIFT，读不到记 UNKNOWN。`--fleet` / `--packages` 普查逐台按 yueops
 `select_ssh_management_host` 选管理地址（management-host 标签 / DDNS 域名 / IPv6 走 domain
 的唯一 A 记录 / 多值 ip 取第一个），并保持 `HostKeyAlias=<sid>`。
 
 `scripts/ship.sh` holds `<component>,yueto-ci` release locks (plus `fleet` for
 panel deployment). Each invocation establishes a distinct
 `YUETO_RELEASE_LOCK_OWNER=ship.sh:<host>:<launcher-pid>` before detaching;
 the child inherits that identity and binds the lock to its own live PID/start time.
 A successful publish job can overlap asynchronous validation, but exit waits for
 whole-run terminal evidence before releasing: at most `SHIP_POLL_MAX` observations
 (default 200), separated by `SHIP_POLL_SECONDS` (default 30), with each status or
 conclusion query capped at 45 seconds. Error exits attempt one final observation.
 Deployment proof still requires the checked final readback. Missing CI or deployment
 proof retains the lock, prints the release refusal, and produces a nonzero exit;
 TTL, a dead PID, and publish-job success alone never authorize release.
 
+Before a deployment command is launched, ship records `deploy-preflight`.
+On failure, `pre-mutation-failed` closes only that preparation operation and
+preserves all pending CI evidence. `cutover-started` atomically replaces it with
+`deploy` before the remote command; any failure or lost reply thereafter still
+requires deployment readback. Panel configuration projection (including
+`--prepare-only`) is conservatively treated as the mutation boundary. An inherited
+lock receives failure evidence but remains owned by its original caller.
+
 ### Optional jump host, authority budgets, and release-root bytecode
 
 `ship.sh` always connects to `BASTION` (`${YUETO_BASTION:-bastion}`). That alias is the production host that runs the containers, the database, and the deploy root. `YUETO_SSH_PROXY_JUMP` is optional and is passed only as OpenSSH `ProxyJump` on that outer connection. The documented alias is `bastion-via-la`. Unset or empty is the direct-connection rollback. The inner `ssh -n` from the production host to the panel does not receive `ProxyJump`.
 
 Authority checks stay fail-closed. `YUETO_AUTHORITY_STEP_TIMEOUT` (default 600, ceiling 3600), `YUETO_AUTHORITY_CONNECT_TIMEOUT` (default 12, ceiling 300), `YUETO_AUTHORITY_ATTEMPTS` (default 3, ceiling 8), and `YUETO_AUTHORITY_BACKOFF_SECONDS` (default 2, ceiling 60) bound read-only status/preflight retries and the SSH master handshake. `0`, a non-numeric value, or a value above the ceiling refuses the run; it does not disable the limit. Signature failures and `request`/`install` are single-attempt. Deploy-root Python runs with `python3 -B` and `PYTHONDONTWRITEBYTECODE=1`. After mint, only real `__pycache__` directories inside that strict root are removed. Signature and hash checks still read every remaining file.
 
 YueOps 构建显式传 `migration_base`：`ship.sh` 从验签成功的旧 desired 取整批变更起点，
 中央 SQL 门验证完整 SHA 存在且是候选祖先，并拒绝删除/重命名迁移。手工 `build.yml`
 （含 `service=all`）也必须传此参数；不能用 `HEAD^` 或候选自身猜上一版本。poll 则从
 已验证 master provenance 的发布镜像取祖先基线，无法证明就报错并留待下轮。
 
 ## 1. Release gate and central CI
 
 Local release acceptance always requires the full exclusive gauntlet, regardless
 of private Actions billing status. A zero-step private run proves no tests ran;
 fixing billing does not replace the signed public delivery chain.
 
 `yueto-ci`'s `poll-sources` is scheduled every 20 minutes (actual dispatch can be
 delayed). It dispatches missing builds with `promote=false`; building is not
 promotion or deployment. Use the central workflow's validation and signed
 promotion receipts, then the `--from-promoted` path above. Do not repeatedly
 dispatch a queued build merely because its result is not yet available.
 
 本地 YueLink 检查也校验实际执行的 SDK：`yuelink-toolchain` 从客户端 CI 的
 `FLUTTER_VERSION` 读取版本，并核对 PATH 上 Flutter、Dart 的同一 SDK 根及实际版本。
 `gauntlet.sh` 自动寻找并核验已安装的准确版本：当前 Flutter 实际所在 SDK、
 `~/.cache/yueto/flutter-<pin>`、`~/sdk/flutter-<pin>`，将同一 `bin` 放在所有子进程的
 PATH 首位；不下载工具链、不放宽 pin，找不到则拒绝。单独检查可运行
 `scripts/check-flutter-toolchain.py --resolve-bin`。只用绝对路径调用 Flutter 不够，
 native-assets 子进程仍可能拾取旧 Dart。2026-10-07 首轮实际发现默认3.47.5与发行
 pin3.47.6错位；自动选择准确SDK后重新执行完整门，旧版运行不算发版证据。
 
 单独运行客户端工具或推送标签（会触发 Git hook）时，统一通过
 `scripts/with-release-sdk.sh <command> [arguments...]`；例如
 `scripts/with-release-sdk.sh git -C yuelink push origin refs/tags/v1.3.119`。
 包装器复用同一 SDK 校验器，同时设置 PATH 和 FLUTTER_ROOT，并原样保留子命令退出码。
 仅 gauntlet 内选对 SDK 不会改变外层终端环境；10/07 标签钩子实际复现过这个边界。
 
 ## 2. yue-node（舰队）
 
 `ship.sh` build completion polling defaults to 200 rounds at 30-second intervals;
 API request time is additional. Dispatch association initially allows 180 seconds
 and can extend to a 6,000-second cap when a new queued run is observed.
 
 `SHIP_POLL_MAX` / `SHIP_POLL_SECONDS` 可显式调整。2026-10-05 实测 Ops 完整后端验证
 需要约32分钟，原30分钟轮询预算可能先到期。等待截止或状态不可读不代表构建失败，
 也不代表所有镜像尚未推广。先核对日志内的原 run，全部成功后使用 `--from-promoted`
 继续验签和部署，不重复触发构建；有真实失败时保留原失败及部分推广事实。
 
 ```bash
 # After central signed build/promotion: verify and publish signed desired state.
 scripts/ship.sh yue-node --from-promoted --detach
 ```
 
 这一步只发布镜像与 pin，**不会滚动舰队**。等待它完成并确认根仓签名 release.yaml 提交已推送，然后从新的 yueops 签名发布根执行下述显式滚动。
 `release.yaml` 是唯一发布真源，旧 image sidecar 已删除，也不从 build 层日志猜 digest。
 
 ### 坑 A：`/opt/yueops` 永远过不了 signed-release-root 断言
 
 `rollout-yue-node-image.sh` 要求一个**只含这一个签名 revision、连 ignored 文件都没有**的
 checkout。`/opt/yueops` 是运维工作目录，带着 `.env`、`data/`、`__pycache__` 等 ~58 个
 ignored 条目，**结构上不可能通过**。以前它只回一句
 `FATAL: manual rollout requires one clean exact signed origin/master checkout`，不说是哪一条
 不满足，于是每次发版都要重新排查一遍。
 
diff --git a/scripts/release-lock.py b/scripts/release-lock.py
index c65126b3..25851d2a 100644
--- a/scripts/release-lock.py
+++ b/scripts/release-lock.py
@@ -514,166 +514,177 @@ def live_releases(rows=None) -> list[dict]:
         elif rollout_repo(name):
             repos = [rollout_repo(name), 'fleet']
         if repos:
             identity = dict(row.get('_identity', {}))
             try:
                 # Only retain coordination fields, never expose the process environment.
                 for item in Path(f"/proc/{row['pid']}/environ").read_bytes().split(b'\0'):
                     key, _, value = item.partition(b'=')
                     if key.decode(errors="replace") in {"YT_LANE", *_STABLE_IDENTITY_VARS, "CLAUDE_PID"}:
                         identity[key.decode()] = value.decode(errors='replace')
             except OSError:
                 pass
             result.append({k: v for k, v in row.items() if k not in {'argv', '_identity'}} | dict(
                 repos=repos, owner=f"process:{row['pid']}", host=socket.gethostname(),
                 lane=identity.get('YT_LANE', '<legacy/unknown>'),
                 process_owner=next((identity[k] for k in _STABLE_IDENTITY_VARS if identity.get(k)),
                                    f"{socket.gethostname()}:{identity['CLAUDE_PID']}" if identity.get('CLAUDE_PID') else None), kind='ship' if name.startswith('ship') else 'rollout',
                 reason=name, live_process=True))
     return result
 
 
 def owned_process(lock: dict, owner=None) -> bool:
     """Only the caller or its ancestors with the exported identity may reenter."""
     if lock.get('_unknown'):
         return False
     rows = process_table()
     if 'process_start' in lock:
         live = next((row for row in rows if row['pid'] == lock.get('pid')), None)
         if live is None or live.get('process_start') != lock['process_start']:
             return False
     parents = {r['pid']: r['ppid'] for r in rows}
     def descends(pid, ancestor):
         seen = set()
         while pid > 1 and pid not in seen:
             if pid == ancestor:
                 return True
             seen.add(pid)
             pid = parents.get(pid, 0)
         return False
     if not lock.get('live_process'):
         if lock.get('owner') != (owner or _identity()):
             return False
         # Legacy records have no PID. New records require actual ancestry.
         return not lock.get('pid') or (lock.get('host') == socket.gethostname()
                                       and descends(os.getpid(), lock['pid']))
     owner_pid = os.environ.get('YUETO_RELEASE_LOCK_PID', '')
     if not owner_pid:
         # Old ship exports only owner. /proc/environ cannot see assignments made
         # after bash started, so also recognize its exact historical fallback.
         prefix = 'ship-ui' if lock.get('reason') == 'ship-ui.sh' else 'ship.sh'
         expected = lock.get('process_owner') or f"{prefix}:{socket.gethostname().split('.')[0]}:{lock['pid']}"
         return (lock.get('kind') == 'ship' and descends(os.getpid(), lock['pid'])
                 and (owner or _identity()) == expected)
     if not owner_pid.isdigit() or not os.environ.get('YUETO_RELEASE_LOCK_OWNER'):
         return False
     return (descends(os.getpid(), int(owner_pid))
             and (lock['pid'] == int(owner_pid)
                  or (descends(lock['pid'], int(owner_pid))
                      and (lock.get('process_owner') == os.environ['YUETO_RELEASE_LOCK_OWNER']
                           or any(row['pid'] == int(owner_pid) for row in live_releases(rows))))))
 
 
 def terminal_proven(lock: dict) -> bool:
     evidence = lock.get('terminal_evidence')
     return (isinstance(evidence, dict) and evidence.get('state') in
-            {'ci-concluded', 'deploy-readback'} and isinstance(evidence.get('proof'), str)
+            {'ci-concluded', 'deploy-readback', 'pre-mutation-failed'} and isinstance(evidence.get('proof'), str)
             and bool(evidence['proof'].strip())
             and _valid_timestamp(evidence.get('at')) and not lock.get('pending_operations'))
 
 
 def dead_local(lock: dict, rows: dict) -> bool:
     pid = lock.get('pid')
     if lock.get('host') != socket.gethostname() or type(pid) is not int or pid <= 1:
         return False
     live = rows.get(pid)
     if live and live.get('_birth_unavailable'):
         return False
     return not live or bool(lock.get('process_start') and live['process_start'] != lock['process_start'])
 
 
 def cmd_evidence(args: argparse.Namespace) -> int:
     """Record proof, or invalidate old proof BEFORE starting a remote operation.
 
     Recovery uses the original owner and an exact inspected hash; the operator
     must supply the terminal run/conclusion or completed deployment readback.
     """
     if not args.proof.strip():
         print('REFUSED: terminal evidence must not be empty', file=sys.stderr)
         return 1
     found = False
     for lock in load_locks(strict=True):
         recovery = (args.expect_sha256 and lock.get('_sha256') == args.expect_sha256
                     and lock.get('owner') == _identity()
                     and dead_local(lock, {r['pid']: r for r in process_table()}))
         if not (owned_process(lock) or recovery) or lock.get('_unknown'):
             continue
         if args.expect_sha256 and lock.get('_sha256') != args.expect_sha256:
             continue
         payload = {k: v for k, v in lock.items() if not k.startswith('_') and k != 'stale'}
         pending = payload.setdefault('pending_operations', {})
-        if args.state == 'pending':
+        if args.state in {'pre-mutation-failed', 'cutover-started'}:
+            expected_key = 'deploy-preflight' if args.state == 'pre-mutation-failed' else 'deploy'
+            if args.key != expected_key or (args.state == 'pre-mutation-failed' and 'deploy' in pending):
+                print('REFUSED: deployment may have mutated services; retain pending evidence', file=sys.stderr)
+                return 1
+        if args.state == 'cutover-started':
+            # Atomically replace the read-only preparation with possible mutation.
+            # A lost remote reply can never turn this back into preflight evidence.
+            pending.pop('deploy-preflight', None)
+            pending['deploy'] = args.proof
+            payload.pop('terminal_evidence', None)
+        elif args.state == 'pending':
             pending[args.key] = args.proof
             payload.pop('terminal_evidence', None)
         else:
             pending.pop(args.key, None)
             payload['terminal_evidence'] = dict(state=args.state, proof=args.proof, at=_now())
         path = Path(lock['_path'])
         tmp = path.with_suffix('.json.tmp')
         tmp.write_text(json.dumps(payload))
         _require_inventory_inode()
         tmp.replace(path)
         found = True
     if not found:
         print('REFUSED: no matching owned record for terminal evidence', file=sys.stderr)
         return 1
     return 0
 
 
 def retire_dead_locks() -> None:
     """Called only under inventory_transaction; preserve evidence before unlink."""
     rows = {r['pid']: r for r in process_table()}
     for lock in load_locks(strict=True):
         if lock.get('_legacy') or lock.get('_unknown'):
             continue
         pid = lock.get('pid')
         if lock.get('host') != socket.gethostname() or type(pid) is not int or pid <= 1:
             continue
         if not _valid_timestamp(lock.get('started_at')):
             continue
         if not dead_local(lock, rows):
             continue
         if not terminal_proven(lock):
             continue
         path = Path(lock['_path'])
         archive = LOCK_DIR / '.retired'
         archive.mkdir(exist_ok=True)
         _require_inventory_inode()
         (archive / f"dead-{uuid.uuid4().hex}.record").write_bytes(path.read_bytes())
         with (LOCK_DIR / 'audit.log').open('a') as out:
             out.write(json.dumps(dict(event='dead-pid-release', at=_now(), record=lock)) + '\n')
             out.flush()
             os.fsync(out.fileno())
         path.unlink()
         print(f"AUTO-RELEASE dead local pid={pid} repo={','.join(lock['repos'])}", file=sys.stderr)
 
 
 def blocking_locks(repos=None, *, allow_owner=True, ttl=DEFAULT_TTL_SECONDS, owner=None):
     locks = load_locks(ttl, strict=True) + live_releases()
     return [lock for lock in locks if not (allow_owner and owned_process(lock, owner))
             and (repos is None or _lock_conflict(set(repos), set(lock['repos']) | set(lock.get('op_repos', [])),
                 '' if 'op_repos' in lock else lock.get('reason', '')))]
 
 
 def conflicts(repos: list[str], owner: str, ttl: int = DEFAULT_TTL_SECONDS) -> list[dict]:
     """Conflicts include TTL-stale records and live unregistered processes."""
     return blocking_locks(repos, ttl=ttl, owner=owner)
 
 
 def _describe(lock: dict) -> str:
     age = int(_now() - float(lock.get("started_at") or 0)) if _valid_timestamp(lock.get("started_at")) else 0
     mark = " [STALE]" if lock.get("stale") else ""
     if dead_local(lock, {r['pid']: r for r in process_table()}) and not terminal_proven(lock):
         mark += ' [stale-unproven: record terminal proof with evidence --expect-sha256; then release/check]'
     if lock.get('_unknown'):
         mark += f" [UNKNOWN: {lock['_unknown']}]"
     return (
@@ -946,106 +957,106 @@ def cmd_status(args: argparse.Namespace) -> int:
                 "repos": lock.get("repos"),
                 "stale": lock.get("stale", False),
                 "unknown": lock.get("_unknown"),
                 "state": 'stale-unproven' if dead_local(lock, {r['pid']: r for r in process_table()}) and not terminal_proven(lock) else 'held',
                 "pending_operations": lock.get('pending_operations', {}),
                 "terminal_evidence": lock.get('terminal_evidence'),
                 "age_seconds": int(_now() - float(lock.get("started_at") or 0)) if _valid_timestamp(lock.get("started_at")) else None,
                 "reason": lock.get("reason") or "-",
             } for lock in locks],
         }, ensure_ascii=False))
         return 0
     print(f"me: {me} (identity from {source})")
     if source == "unstable-ppid":
         print("⚠️ 这个身份跨调用会变；冲突判定会出现假阳性。")
     if not locks:
         print("no release locks")
         return 0
     print(f"{len(locks)} release lock(s):")
     for lock in locks:
         print(_describe(lock))
     if any(lock.get("stale") for lock in locks):
         print("\nSTALE is not terminal evidence. The registered owner must close its "
               "operation, then use release --expect-sha256 from status --json. "
               "TTL and dead local PIDs never prove completion. Use evidence --state ci-concluded or deploy-readback --key <operation> --proof <run-id/conclusion or readback receipt> --expect-sha256 <record hash> with the original owner, then check/release.")
     return 0
 
 
 def cmd_check(args: argparse.Namespace) -> int:
     repos = [r.strip() for r in args.repos.split(",") if r.strip()]
     owner = _identity()
     # 钩子在每次 push / 发版动作上都会调到这里 —— 那就是最诚实的生命迹象，
     # 顺带把自己那把锁的心跳刷新。查别人的锁是只读的，只有自己的会被刷。
     _touch_own_lock(owner)
     clash = blocking_locks(repos, allow_owner=not args.all_owners, ttl=args.ttl)
     if not clash:
         return 0
     print("CONFLICT: a release lock covers " + ",".join(repos))
     for lock in clash:
         print(_describe(lock))
     if any(lock.get("stale") for lock in clash):
         print("\nSTALE is not terminal evidence. The registered owner must close its "
               "operation, then use release --expect-sha256 from status --json. "
               "TTL and dead local PIDs never prove completion. Use evidence --state ci-concluded or deploy-readback --key <operation> --proof <run-id/conclusion or readback receipt> --expect-sha256 <record hash> with the original owner, then check/release.")
     return 1
 
 
 def main(argv: list[str] | None = None) -> int:
     parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
     parser.add_argument("--ttl", type=int, default=DEFAULT_TTL_SECONDS)
     sub = parser.add_subparsers(dest="cmd", required=True)
 
     p = sub.add_parser("acquire", help="声明一次发版在途")
     p.add_argument("--repos", required=True, help="逗号分隔；fleet 表示舰队滚动/面板部署")
     p.add_argument("--reason", default="", help="一句话：在发什么")
     p.add_argument("--force", action="store_true", help="deprecated; never bypasses conflicts")
     p.add_argument("--lane")
     p.add_argument("--worktree", default=str(ROOT))
     p.add_argument("--kind", choices=("ship", "rollout"), default="ship")
     p.set_defaults(func=cmd_acquire)
 
     p = sub.add_parser("release", help="Release the registered owner after closing its operation")
     p.add_argument("--expect-sha256", type=record_sha256, help="Require this exact raw record SHA-256 from status --json")
     p.set_defaults(func=cmd_release)
 
     p = sub.add_parser('evidence', help='Record terminal proof or a pending remote operation')
-    p.add_argument('--state', choices=('pending', 'ci-concluded', 'deploy-readback'), required=True)
+    p.add_argument('--state', choices=('pending', 'ci-concluded', 'deploy-readback', 'pre-mutation-failed', 'cutover-started'), required=True)
     p.add_argument('--key', required=True)
     p.add_argument('--proof', required=True)
     p.add_argument('--expect-sha256', type=record_sha256)
     p.set_defaults(func=cmd_evidence)
 
     p = sub.add_parser("heartbeat", help="长发版每跑完一步刷一次，证明自己还活着")
     p.set_defaults(func=cmd_heartbeat)
 
     p = sub.add_parser("holds", help="0=自己的锁已覆盖这些仓 / 1=有锁但不覆盖 / 3=没有锁（ship.sh 用）")
     p.add_argument("--repos", required=True)
     p.set_defaults(func=cmd_holds)
 
     p = sub.add_parser("status", help="列出当前所有锁")
     p.add_argument("--json", action="store_true", help="emit a read-only versioned snapshot")
     p.set_defaults(func=cmd_status)
 
     p = sub.add_parser("check", help="退出码 1 = 有冲突（钩子用）")
     p.add_argument("--repos", required=True)
     p.add_argument("--all-owners", action="store_true")
     p.set_defaults(func=cmd_check)
 
     args = parser.parse_args(argv)
     # Atomic rename protects readers from partial JSON, but cannot prevent two
     # acquirers passing the same conflict check or a heartbeat reviving a release.
     # All mutations use one short local transaction; status/holds stay read-only.
     if args.cmd in {"acquire", "heartbeat", "release", "check", "evidence"}:
         try:
             with inventory_transaction():
                 if args.cmd in {"acquire", "check"}:
                     retire_dead_locks()
                 return args.func(args)
         except (OSError, RuntimeError, ValueError, OverflowError) as exc:
             print(f"UNKNOWN: release lock transaction unavailable ({type(exc).__name__})",
                   file=sys.stderr)
             return 75
     return args.func(args)
 
 
 if __name__ == "__main__":
     sys.exit(main())
diff --git a/scripts/ship-sshd-authority.py b/scripts/ship-sshd-authority.py
index afbc35a0..9b78b345 100755
--- a/scripts/ship-sshd-authority.py
+++ b/scripts/ship-sshd-authority.py
@@ -12,134 +12,132 @@ import base64
 import hashlib
 import json
 import os
 import re
 import shutil
 import signal
 import stat
 import subprocess
 import sys
 import tempfile
 import time
 from contextlib import contextmanager
 from pathlib import Path, PurePosixPath
 
 sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
 from ship_remote import PROGRESS_SECONDS, remote_budget, report, run_remote
 
 SIGNER = "CEF96E9A4ECB741C78329CA3FE2659E6AC769954"
 # Under heavy hypervisor CPU steal (2026-10-11: 65-78%) the signed-root
 # verification plus one native call exceeded the old 300s/420s budget.  Each
 # remote step gets REMOTE_STEP_TIMEOUT; the ssh budget covers both sequential
 # steps plus transport. SHIP_REMOTE_TIMEOUT_SECONDS additionally caps each SSH
 # call (default 900s), with progress and a diagnostic if it expires first.
 REMOTE_STEP_TIMEOUT = 600
 REMOTE_BUDGET = 2 * REMOTE_STEP_TIMEOUT + 120
 _TRANSIENT_TRANSPORT = {"ssh_timeout", "ssh_reset", "ssh_kex", "ssh_closed", "ssh_pipe"}
 
 
 def positive_bound(name: str, default: int, ceiling: int) -> int:
     """Read one positive integer. Zero and non-numeric values refuse; they do not disable the limit."""
     raw = os.environ.get(name)
     if raw is None or str(raw).strip() == "":
         return default
     text = str(raw).strip()
     if re.fullmatch(r"[1-9][0-9]*", text) is None:
         raise Refused("invalid_" + name)
     value = int(text)
     if value > ceiling:
         raise Refused("invalid_" + name)
     return value
 
 
 def authority_limits() -> tuple[int, int, int, int]:
     step = positive_bound("YUETO_AUTHORITY_STEP_TIMEOUT", REMOTE_STEP_TIMEOUT, 3600)
     connect = positive_bound("YUETO_AUTHORITY_CONNECT_TIMEOUT", 12, 300)
     attempts = positive_bound("YUETO_AUTHORITY_ATTEMPTS", 3, 8)
     backoff = positive_bound("YUETO_AUTHORITY_BACKOFF_SECONDS", 2, 60)
     return step, connect, attempts, backoff
 
 
 def authority_budget(step: int) -> int:
     return 2 * step + 120
 
 
 def proxy_jump() -> str:
     """Optional SSH config alias. Empty keeps a direct connection to the production host."""
     text = os.environ.get("YUETO_SSH_PROXY_JUMP", "").strip()
     if text == "":
         return ""
     if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,252}", text) is None:
         raise Refused("invalid_proxy_jump")
     return text
 
 
 def readonly_retryable(reason: str) -> bool:
-    """Transport and steal timeouts only. Signature and native refusals are not retried."""
-    if reason.startswith("command_failed_255"):
-        return True
-    return reason in {"command_failed_124:timeout", "command_failed_78:TimeoutExpired"}
+    """Retry only classified transient SSH failures, never native refusals."""
+    return reason in {"command_failed_255:" + code for code in _TRANSIENT_TRANSPORT}
 PRIMARY = "D9D3C6E59E7465BD07C2177142239A996FDA9F55"
 VERIFIER = "scripts/verify-signed-release-root-20260822.py"
 VERIFIER_SHA = "acab35cc20d9d21698f0b2c3869686297c15f3822ed62290a84c86b367153bbe"
 ENTRY = "scripts/converge-sshd-boundary-authority.sh"
 LIBRARY = "scripts/lib/sshd-startup-boundary-consumer-20260822.sh"
 CONTROLLER = "scripts/converge-cloudflared-sshd-startup-boundary-20260822.sh"
 HEX40 = re.compile(r"[0-9a-f]{40}\Z")
 HEX64 = re.compile(r"[0-9a-f]{64}\Z")
 STATUS_KEYS = {"schema", "status", "mode", "source_revision", "runtime_id",
                "active_generation", "last_good_generation", "native_bootstrap_verified", "bindings_verified"}
 
 
 # Identical sanitizer bytes run locally and in the isolated remote program.
 DIAGNOSTICS = r'''
 import re
 def safe_detail(value):
     if not isinstance(value, str) or not value:
         return ""
     line = value.splitlines()[0]
     # Drop the remainder at credential/connection markers: quoted values may
     # contain spaces and malformed connection strings must still fail closed.
     line = re.sub(r"(?i)(?:password|passwd|pwd|secret|token|(?:host|hostaddr|user|username|dbname|database|port|sslmode)\s*=|[a-z][a-z0-9+.-]*://).*", "<redacted>", line)
     # Quoted paths can contain whitespace; redact the whole quoted value.
     line = re.sub(r"([\"'])(?:(?!\1).)*[/\\](?:(?!\1).)*\1", "<redacted>", line)
     line = re.sub(r"[^\s\"'<>]*[/\\][^\s\"'<>]*", "<redacted>", line)
     line = re.sub(r"(?<![\w])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![\w])", "<redacted>", line)
     line = re.sub(r"(?i)(?<![\w])(?:[0-9a-f]*:){2,}[0-9a-f:.]*(?:%[\w.-]+)?", "<redacted>", line)
     line = ''.join(c if 32 <= ord(c) < 127 else '?' for c in line)
     return line[:200]
 
 def safe_step(value):
     return value if value in ('status', 'preflight', 'request', 'install') else ''
 '''
 exec(DIAGNOSTICS)
 
 
 class Refused(ValueError):
     def __init__(self, reason, *, step="", detail=""):
         super().__init__(reason)
         self.step = safe_step(step)
         self.detail = safe_detail(detail)
 
 
 def require(value, reason):
     if not value:
         raise Refused(reason)
 
 
 def canonical(value):
     return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")
 
 
 def decode(raw):
     def unique(pairs):
         result = {}
         for key, value in pairs:
             require(key not in result, "duplicate_json_key")
             result[key] = value
         return result
     require(0 < len(raw) <= 2 * 1024 * 1024, "response_size")
     value = json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(Refused("nonfinite_json")))
     require(isinstance(value, dict), "response_shape")
     return value
 
 def transport_code(stderr: str) -> str:
diff --git a/scripts/ship.sh b/scripts/ship.sh
index 5477e0a6..b47f4c70 100755
--- a/scripts/ship.sh
+++ b/scripts/ship.sh
@@ -389,196 +389,213 @@ if [ "$UI_MODE" = true ]; then
   [ "$DEPLOY" = false ] && ui_args+=(--no-deploy)
   [ "$FROM_PROMOTED" = true ] && ui_args+=(--from-promoted)
   [ "$PREVIEW" = true ] && ui_args+=(--preview)
   [ "$ROLLBACK" = true ] && ui_args+=(--rollback)
   [ -n "$EXPLICIT_DIGEST" ] && ui_args+=(--digest "$EXPLICIT_DIGEST")
   exec bash "$ui_driver" "${ui_args[@]}"
 fi
 
 # ── 0. 现在在哪儿 ────────────────────────────────────────────────────────────
 log "读四真相 (release-state)"
 [ -f "$ROOT/scripts/release-state.py" ] || die "ROOT 在运行中消失: ${ROOT}（调用方删掉了它？YUETO_ROOT=${YUETO_ROOT:-unset}）"
 # release-state 的退出码是**判据**不是健康度：0=四真相全齐，1=有 DRIFT 或 UNKNOWN。
 # 曾经这里写成 `|| die`，于是 ship.sh 在**真有东西要发的时候永远起不来**——
 # 唯一能跑通的场景是「没什么要发」。判「跑起来了没有」只能看它有没有产出表头。
 if [ "$COMPONENT" = auto ]; then
   # Automatic decisions need measured fleet state. Without --fleet this row
   # is always UNKNOWN, so an aligned workspace could never finish unattended.
   STATE=$(cd "$ROOT" && uv run python scripts/release-state.py --fleet 2>&1) || true
 else
   STATE=$(cd "$ROOT" && uv run python scripts/release-state.py 2>&1) || true
 fi
 echo "$STATE"
 grep -q '^component  *HEAD  *pin' <<<"$STATE" || die "release-state 没有产出四真相表（真的跑挂了）：$STATE"
 
 if [ "$COMPONENT" = auto ]; then
   # Missing/duplicate rows are failed observations, not an empty work queue.
   for state_component in yueboard yue-node yueops; do
     awk -v component="$state_component" '
       $1 == component { count++; if ($6 !~ /^(OK|DRIFT|UNKNOWN)$/) invalid=1 }
       END { exit (count != 1 || invalid) }
     ' <<<"$STATE" || die "--auto 拒绝判定：${state_component} 的状态行缺失、重复或无效"
   done
   UNKNOWN_ROWS=$(awk '$6 == "UNKNOWN" && $1 ~ /^(yueops|yueboard|yue-node)$/ {print $1}' <<<"$STATE" | tr '\n' ' ')
   if [ -n "${UNKNOWN_ROWS// /}" ]; then
     die "--auto 拒绝判定：这些行是 UNKNOWN 而不是 OK —— ${UNKNOWN_ROWS}。全队扫描未能完成测量。"
   fi
   COMPONENT=$(awk '/DRIFT/ && $1 ~ /^(yueops|yueboard|yue-node)$/ {print $1; exit}' <<<"$STATE" || true)
   if [ -z "$COMPONENT" ]; then
     log "四真相已对齐，没有要发的东西。"; exit 0
   fi
   log "--auto 判定：$COMPONENT 需要发版"
 fi
 
 REPO_DIR="$ROOT/$COMPONENT"
 [ -d "$REPO_DIR/.git" ] || die "找不到仓库 $REPO_DIR"
 
 # ── 发版在途锁（2026-09-27 深审 R3）─────────────────────────────────────────
 # release-lock.py 早就有了，但 ship.sh 从来不取它——于是「此刻有人在发 X」这个事实只在
 # 操作者记得手工 acquire 时才存在，而最需要它的正是 ship.sh 这种一跑 15-30 分钟、中途
 # 任何一次推送都会作废 promote 的长链。现在：
 #   · 本会话已持有覆盖这些仓的锁 → 沿用，退出时**不**释放（不是我取的）；
 #   · 本会话有锁但不覆盖 → 停下（acquire 会整份覆盖那把锁，抹掉会话已声明的其它仓）；
 #   · 没有 → 自己取，EXIT trap 释放；每个阶段刷一次心跳（stale 由心跳决定）。
 # --detach：锁在这里取，也就是**子进程**取（父进程在上面已经 exit 0 了），子进程的
 # The launcher identity survives detach; the verified lifetime PID belongs to
 # the executing child, never the short-lived launcher or command substitution.
 RELEASE_LOCK_PY="$ROOT/scripts/release-lock.py"
 LOCK_HELD_BY_US=false
 # Each ship is its own operation, even when one agent starts two ships.
 export YUETO_RELEASE_LOCK_OWNER="${YUETO_RELEASE_LOCK_OWNER:-ship.sh:$(hostname):$$}"
 export YUETO_RELEASE_LOCK_PID=$$
 LOCK_REPOS="$COMPONENT,yueto-ci"
 # 面板部署与舰队滚动互斥（进程围栏 4 分钟 vs 排空门 30 秒），release-lock 用 fleet 表达它。
 if [ "$COMPONENT" = yueboard ] && $DEPLOY; then LOCK_REPOS="$LOCK_REPOS,fleet"; fi
 declare -A LOCK_CI_RUNS=()
+LOCK_CI_TERMINAL_PROOF=""
 release_ship_lock() {
   local rc=$? attempt key
-  $LOCK_HELD_BY_US || return "$rc"
+  local release_owned_lock=$LOCK_HELD_BY_US
   LOCK_HELD_BY_US=false
   # Publishing can finish before asynchronous validation. Reconcile the whole
   # run before release, including --no-deploy and --prepare-only exits. On an
   # error, make one final observation; never invent proof for an interrupted run.
   local attempts=1
   [ "$rc" -ne 0 ] || attempts=${POLL_MAX:-200}
   for ((attempt=1; attempt<=attempts; attempt++)); do
     for key in "${!LOCK_CI_RUNS[@]}"; do
       lock_ci_concluded "$key" "${LOCK_CI_RUNS[$key]}"
     done
     [ "${#LOCK_CI_RUNS[@]}" -gt 0 ] || break
     [ "$attempt" -lt "$attempts" ] || break
     log "等待 CI 终态证据后释放发版锁（${attempt}/${attempts}）"
     sleep "${POLL_SECONDS:-30}"
   done
+  if [ "$rc" -ne 0 ]; then
+    # This closes only preparation. The lock refuses this evidence if a remote
+    # deploy may have started, and never clears outstanding CI operations.
+    python3 "$RELEASE_LOCK_PY" evidence --state pre-mutation-failed \
+      --key deploy-preflight --proof "ship exited before service mutation rc=$rc${LOCK_CI_TERMINAL_PROOF:+; $LOCK_CI_TERMINAL_PROOF}" \
+      || log "保留部署未完成证据：服务可能已开始变更"
+  fi
+  $release_owned_lock || return "$rc"
   if ! python3 "$RELEASE_LOCK_PY" release; then
     echo "⚠ 发版在途锁释放失败——保留未完成证据；检查 scripts/release-lock.py status" >&2
     [ "$rc" -ne 0 ] || rc=1
   fi
   return "$rc"
 }
 lock_evidence() {
   python3 "$RELEASE_LOCK_PY" evidence --state "$1" --key "$2" --proof "$3"     || die "Cannot persist release terminal evidence"
 }
 lock_ci_read() {
   # Bound each observation as well as the overall retry count.
   python3 - "$1" "$2" <<'PYTHON'
 import subprocess
 import sys
 
 try:
     result = subprocess.run(
         ["gh", "run", "view", sys.argv[1], "-R", "onesyue/yueto-ci",
          "--json", sys.argv[2], "-q", "." + sys.argv[2]],
         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=45)
 except (OSError, subprocess.TimeoutExpired):
     sys.exit(1)
 sys.stdout.buffer.write(result.stdout)
 sys.exit(result.returncode)
 PYTHON
 }
 lock_ci_concluded() {
   local key=$1 run=$2 status=${3:-} conclusion=${4:-}
   case "$key" in yueops-web|yue-bot|checkin-api) key=yueops ;; esac
   LOCK_CI_RUNS[$key]=$run
   [ -n "$status" ] || status=$(lock_ci_read "$run" status) || return 0
   [ "$status" = completed ] || return 0
   [ -n "$conclusion" ] || conclusion=$(lock_ci_read "$run" conclusion) || return 0
   case "$conclusion" in
     success|failure|cancelled|timed_out|action_required|neutral|skipped|stale|startup_failure)
       lock_evidence ci-concluded "ci:$key" "onesyue/yueto-ci run=$run status=completed conclusion=$conclusion"
+      # Retain observed proof when exit cleanup closes failed preparation,
+      # even if subsequent CI reads are unavailable. Pending keys still fence release.
+      LOCK_CI_TERMINAL_PROOF+="onesyue/yueto-ci run=$run status=completed conclusion=$conclusion; "
       unset 'LOCK_CI_RUNS[$key]' ;;
   esac
 }
 lock_heartbeat() {
   python3 "$RELEASE_LOCK_PY" heartbeat >/dev/null 2>&1 \
     || log "  ⚠ 发版在途锁心跳失败（锁可能被判 stale；不影响本次发版继续）"
 }
 [ -f "$RELEASE_LOCK_PY" ] || die "找不到 ${RELEASE_LOCK_PY}——不取锁就不发版"
 lock_rc=0
 lock_out=$(python3 "$RELEASE_LOCK_PY" holds --repos "$LOCK_REPOS" 2>&1) || lock_rc=$?
 case "$lock_rc" in
-  0) log "发版在途锁：本会话已持有 ${LOCK_REPOS}（${lock_out}）——沿用，退出时不释放" ;;
+  0)
+    log "发版在途锁：本会话已持有 ${LOCK_REPOS}（${lock_out}）——沿用，退出时不释放"
+    trap 'exit 130' INT
+    trap 'exit 143' TERM HUP
+    trap release_ship_lock EXIT ;;
+
   3)
     # 信号转成 exit，EXIT trap 才会跑（被 kill/Ctrl-C 时锁不能留成 3 小时后才 stale 的死锁）。
     trap 'exit 130' INT
     trap 'exit 143' TERM HUP
     trap release_ship_lock EXIT
     lock_out=$(python3 "$RELEASE_LOCK_PY" acquire --repos "$LOCK_REPOS" \
                  --reason "scripts/ship.sh $COMPONENT (pid $$)" 2>&1) \
       || die "取不到发版在途锁（${LOCK_REPOS}）——有别人正在发，先协调：$lock_out"
     LOCK_HELD_BY_US=true
     log "发版在途锁：${lock_out}" ;;
   1) die "本会话持有的发版锁不覆盖 ${LOCK_REPOS}（${lock_out}）——acquire 会整份覆盖它；先 scripts/release-lock.py acquire --repos <原有>,${LOCK_REPOS} 扩展再跑" ;;
   *) die "判不了发版在途锁（release-lock.py holds 退出 ${lock_rc}）：$lock_out" ;;
 esac
 
 # mint_release_root <revision> —— 铸一个只含该签名 revision 的干净根，**已存在就复用**。
 #
 # 2026-09-03 实测：make-release-root.sh 对已存在的严格根按设计拒绝覆盖，打印
 #   make-release-root: refusing to overwrite an existing strict root: /var/lib/…/<rev>
 # 而 ship.sh 把任何非路径输出一律当成"铸根失败"，于是**同一个 revision 已经铸过根**
 # （比如先手工跑过 schema 迁移、或上一次发版在部署前中断）就会让整条链在
 # 镜像已 promote、已验签之后停住——一个纯粹的重入问题，不是真失败。
 # 拒绝信息里带着那个根的绝对路径，直接复用它：根的内容由 revision 唯一决定。
 # ── 1. 源头必须干净且 == origin HEAD（promote 门的前置，早失败早省时间）──────
 predispatch_read source-fetch "$REPO_DIR" || die "$COMPONENT: git fetch origin 失败——没有新鲜的 origin/master 就判不了 HEAD == origin"
 # 2026-11-02 19:43 实测：本地检出落后 origin/master 一次就让发版白跑。fetch 之后若当前在
 # master 且严格落后（无本地提交），就地 fast-forward；分叉/非 master 照旧由下面的门拒绝。
 if [ "$(git -C "$REPO_DIR" symbolic-ref -q --short HEAD)" = master ] \
    && [ "$(git -C "$REPO_DIR" rev-list --count origin/master..HEAD)" = 0 ] \
    && [ "$(git -C "$REPO_DIR" rev-list --count HEAD..origin/master)" != 0 ]; then
   git -C "$REPO_DIR" merge --ff-only -q origin/master \
     && log "$COMPONENT 本地检出已 fast-forward 到 origin/master" \
     || die "$COMPONENT: fast-forward 到 origin/master 失败（工作树改动冲突？）"
 fi
 REV=$(git -C "$REPO_DIR" rev-parse HEAD) || die "$COMPONENT: 读不到 HEAD"
 ORIGIN=$(git -C "$REPO_DIR" rev-parse origin/master) || die "$COMPONENT: 读不到 origin/master"
 # 镜像烧的是 **GitHub 上那个 revision** 的字节（yueto-ci 自己 checkout），本地工作树
 # 的**任何**状态都不参与构建。硬判据只有下面那条 HEAD == origin/master。
 # 所以脏工作树是**警告**不是门：这个工作区里并发会话是常态，2026-08-31 实测一个
 # 并发会话在 yueops/web/ 下的在途改动就把整条发版链挡死了两次，而它对镜像零影响。
 DIRTY=$(git -C "$REPO_DIR" status --porcelain) || die "$COMPONENT: git status 失败"
 if [ -n "$DIRTY" ]; then
   log "⚠ $COMPONENT 工作树有在途改动——**它们不会进本次镜像**（镜像烧的是 GitHub 上的 $COMPONENT revision）："
   sed 's/^/      /' <<<"$DIRTY"
 fi
 [ "$REV" = "$ORIGIN" ] || die "$COMPONENT HEAD($REV) != origin/master($ORIGIN)——先推送；promote 门只认默认分支 HEAD"
 log "$COMPONENT revision=${REV}（== origin/master ✓）"
 lock_heartbeat
 
 # P2 #11 / §7.4（2026-09-24）：记下开始时的 desired generation。promote 之后写 release.yaml
 # 时若它已被别的写者推进（别人在这次发版期间批准了更新的 desired），release-yaml.py write
 # 拒绝让本次（可能更旧的）候选晚到覆盖它。
 DESIRED_GEN0=$(python3 "$ROOT/scripts/release-yaml.py" generation) \
   || die "读不到 release.yaml 的 desired generation（release.yaml 坏了？）——先修它"
 [[ "$DESIRED_GEN0" =~ ^[0-9]+$ ]] || die "desired generation 形状不对：$DESIRED_GEN0"
 log "desired generation（开始时）= ${DESIRED_GEN0}"
 
 # 并发推送会让整批镜像作废（一次 build 要 11-15 分钟）。先看最近一次推送多久以前。
 LAST_PUSH_AGO=$(git -C "$REPO_DIR" log -1 --format=%cr origin/master) || LAST_PUSH_AGO="（读不到）"
 log "origin/master 最近一次提交：$LAST_PUSH_AGO —— 构建期间**不要再推** $COMPONENT/yueto-ci"
 
 # SERVICES = 要拿 digest / 验签 / 部署的镜像；DISPATCH = 触发 build.yml 用的 service 输入。
 # yueops 三镜像同属 services.json 的 group "yueops"：**一次**按 group 派发就跑一次
 # validate-yueops + 三个 build 矩阵项、同一个并发组。此前这里逐服务派发三次，等于并行
 # 跑三遍同一份 13 分钟的 validate-yueops（2026-09-14 中央 CI 审计实测），纯浪费且互相
 # 抢并发组。group 派发时三个服务共用同一个 run id，digest 按 job 名前缀区分（见 §4）。
@@ -1071,154 +1088,160 @@ record_release_yaml() {
   fi
   $changed || return 0
   branch=$(git -C "$ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "?")
   if [ "$branch" != master ]; then
     log "  ⚠ 根仓不在 master（在 ${branch}）——release.yaml 已写入但不提交；请自行提交推送"
     return 0
   fi
   # 只提交这两个路径（release.yaml + 它的 detached 签名）：根仓里常有别的会话的在途改动，
   # 逐路径提交不碰它们。提交由 commit.gpgsign=true 自动签名（工作区硬规则）。
   local -a root_paths=(release.yaml)
   [ -f "$ROOT/release.yaml.asc" ] && root_paths+=(release.yaml.asc)
   git -C "$ROOT" add -- "${root_paths[@]}"
   git -C "$ROOT" commit -q -m "release: record ${COMPONENT} ${REV:0:12} promote in release.yaml" \
     -m "Written by scripts/ship.sh after promote + signature/SBOM/provenance verification." \
     -- "${root_paths[@]}" \
     || { log "  ⚠ 根仓提交失败（签名？）——release.yaml 已写入未提交，请手工提交推送"; return 0; }
   log "  已提交 $(git -C "$ROOT" rev-parse --short HEAD)"
   # 🚨 git push 是**分支级**的：逐路径 add 只防暂存面，推送会把别的会话已 commit 未 push
   # 的提交一并推走（2026-09-09 一天三次）。判据 = 推前看 origin/master..HEAD 是不是只有
   # 我这一条；不是就不推，把提交列出来交给人。
   git -C "$ROOT" fetch -q origin master || { log "  ⚠ fetch 失败，不推；本地已提交"; return 0; }
   behind=$(git -C "$ROOT" rev-list --count HEAD..origin/master)
   if [ "$behind" -gt 0 ]; then
     git -C "$ROOT" pull -q --rebase --autostash origin master \
       || { log "  ⚠ 根仓落后 origin ${behind} 条且 rebase 失败——本地已提交未推送，请手工处理"; return 0; }
   fi
   ahead=$(git -C "$ROOT" rev-list --count origin/master..HEAD)
   if [ "$ahead" -eq 1 ]; then
     if git -C "$ROOT" push -q origin master; then
       log "  release.yaml 已推送 origin/master ($(git -C "$ROOT" rev-parse --short HEAD))"
     else
       log "  ⚠ 推送失败——本地已提交，请手工 git push"
     fi
   else
     log "  ⚠ 根仓有 ${ahead} 条未推送提交（不只我这一条）——push 是分支级的，会把别人的一并推走，不推："
     git -C "$ROOT" log --oneline origin/master..HEAD | sed 's/^/        /'
   fi
 }
 log "记录 promote 到 release.yaml"
 lock_heartbeat
 record_release_yaml
 # ── 5b. 把 release.yaml 送到 bastion：fleet-reconcile 的期望副本 ──────────────
 # yueops 的 scripts/fleet-reconcile.service 把期望状态钉在
 #   Environment=YUEOPS_RELEASE_YAML=/var/lib/yueops/fleet-reconcile/release.yaml
 # 副本缺席时它退回 /opt/yueops/scripts/yue-node.image(+.revision)；**陈旧的副本比缺席更糟**
 # ——它优先于回退，会让 reconciler 拿上一次的期望去比这一次的舰队，而且什么都不会报错。
 # 所以每次 promote 记录之后都无条件重投一份并逐字节验收；投不上去就停在这里（promote
 # 已成、镜像已验签、release.yaml 已记录，修好后 --from-promoted 可续）。三个组件都做：
 # reconciler 读的是整份文件，不只 yue-node 那一段。面板部署也从这份副本转投影到面板机。
 # Read by publish_release_yaml_to_bastion() in sourced lib/ship-panel-native.sh.
 # shellcheck disable=SC2034
 RECONCILE_RELEASE_YAML=/var/lib/yueops/fleet-reconcile/release.yaml
 # Read by ship_panel_prepare() in sourced lib/ship-panel-native.sh.
 # shellcheck disable=SC2034
 RELEASE_YAML_SHA=""
 # release.yaml.asc 的 sha256。A3 起必须有签名（publish_release_yaml_to_bastion 在没有时 die），
 # none 只剩下「还没发布」这个初值。
 # Read by publish_release_yaml_to_bastion() and ship_panel_prepare() in sourced lib/ship-panel-native.sh.
 # shellcheck disable=SC2034
 RELEASE_YAML_ASC_SHA=none
 file_sha256() { python3 -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$1"; }
 log "投影 release.yaml 到 bastion（fleet-reconcile 的期望副本）"
 publish_release_yaml_to_bastion
 
 if [ "$PREPARE_ONLY" = true ]; then
+  lock_evidence cutover-started deploy "panel preparation may mutate configuration"
   ship_panel_prepare
+  lock_evidence deploy-readback deploy "signed panel preparation completed with exact-byte readback"
   log "PANEL_PREPARE_ONLY_OK: signed inputs and recovery images prepared; no migration or deployment performed"
   exit 0
 fi
 
 if ! $DEPLOY; then
   log "--no-deploy：到此为止。digest 已就绪且已验签："
   for svc in "${SERVICES[@]}"; do echo "  $svc  ghcr.io/onesyue/$svc@${DIGEST[$svc]}"; done
   exit 0
 fi
 
 # ── 6. 部署 ────────────────────────────────────────────────────────────────
 lock_heartbeat
-lock_evidence pending deploy "component=$COMPONENT revision=$REV"
+lock_evidence pending deploy-preflight "component=$COMPONENT revision=$REV"
 case "$COMPONENT" in
   yueops)
     # 坑 A：/opt/yueops 结构上过不了 signed-release-root 断言（带 ignored 条目），
     # 必须先铸一个只含这一个签名 revision 的干净根，再从根跑部署器。
     log "铸干净签名根 @ $REV"
     RROOT=$(mint_release_root "$REV") || die "铸根失败: $RROOT"
     [[ "$RROOT" == /var/lib/yueops-release-roots/* ]] || die "铸根失败: $RROOT"
     log "根 = $RROOT"
     python3 -B "$ROOT/scripts/ship-sshd-authority.py" --repository "$ROOT/yueops" \
       --revision "$REV" --bastion "$BASTION" --check \
       || die "SSH authority release preflight failed before Ops deployment"
     log "部署三服务（同 revision 签名 digest 门）"
+    lock_evidence cutover-started deploy "component=$COMPONENT revision=$REV remote deploy may mutate services"
     release_ssh "$BASTION" \
       "env -i PATH=/usr/bin:/bin:/usr/local/bin HOME=/root PYTHONDONTWRITEBYTECODE=1 /bin/bash -p '$RROOT/scripts/deploy-yueops-digests.sh' \
          --source-revision $REV \
          --yueops-web ghcr.io/onesyue/yueops-web@${DIGEST[yueops-web]} \
          --checkin-api ghcr.io/onesyue/checkin-api@${DIGEST[checkin-api]} \
          --yue-bot ghcr.io/onesyue/yue-bot@${DIGEST[yue-bot]}" || die "yueops 部署失败"
     log "yueops 部署完成"
     # 2026-09-24：客服浮窗修复部署成功而用户看到的仍是旧版——面板主题 custom_html
     # 还引用 chat-widget.js?v=52，CDN 命中旧 build。面板引用必须随 widget build 前进，
     # 所以它是发版步骤而不是一次性 SQL：从同一签名根取 WIDGET_BUILD，先证实刚部署的
     # checkin-api 已在提供该 build，再以 app_yueboard 行锁 + 精确 CAS 只改版本号（拒降级、
     # 拒多处引用）。失败不回滚已完成的部署，但必须响亮：面板仍在引用旧 build。
     log "面板客服浮窗引用收敛到本次 widget build"
     release_ssh "$BASTION" \
       "env -i PATH=/usr/bin:/bin:/usr/local/bin HOME=/root PYTHONDONTWRITEBYTECODE=1 /bin/bash -p '$RROOT/scripts/converge-panel-chat-widget-version.sh' --apply" \
       || die "yueops 已部署，但面板主题的 chat-widget 引用未收敛（用户仍会加载旧 build）——修复后单独重跑：ssh $BASTION $RROOT/scripts/converge-panel-chat-widget-version.sh --apply"
     # 2026-10-17 W0.6: the bastion checkout follows only after the images it
     # needs are running, so start auto-pull now instead of waiting for its
     # daily timer. reset-failed clears an exhausted start limit from an earlier
     # deferral burst. --no-block: auto-pull never gates or delays ship.sh, and a
     # failure to start is reported, not fatal (its own unit alerts on failure).
     log "启动 bastion yueops-auto-pull（不阻塞）"
     release_ssh "$BASTION" \
       "systemctl reset-failed yueops-auto-pull.service 2>/dev/null; systemctl start --no-block yueops-auto-pull.service" \
       || log "  ⚠ 未能启动 yueops-auto-pull（部署已完成）；手工：ssh $BASTION systemctl start --no-block yueops-auto-pull.service"
     ;;
   yueboard)
+    # Preparation can project service configuration; mark conservatively before it.
+    lock_evidence cutover-started deploy "component=$COMPONENT revision=$REV panel preparation may mutate configuration"
     ship_panel_prepare
     ship_panel_deploy
     ;;
   yue-node)
     # P2 §4 A3：节点镜像的期望身份只在签名的 release.yaml desired（上面已写入、seal、并投影到
     # bastion 的 /var/lib/yueops/fleet-reconcile/release.yaml(+.asc)）。滚动器（签名根与每周
     # runtime bundle 里）经 lib/release-yaml.sh 读那份副本——**不需要**任何 yueops 提交。
     # 滚动本身仍是显式动作（会重建全队容器），不在这里自动触发。
     log "节点镜像 desired 已签名并投影到 bastion。滚动是显式动作（不需要提交 yueops）："
     echo "  cd \$(ssh $BASTION 'env PYTHONDONTWRITEBYTECODE=1 bash /opt/yueops/scripts/make-release-root.sh --strict <yueops-rev>')"
     echo "  CONCURRENCY=4 bash scripts/rollout-yue-node-image.sh --source-revision <yueops-rev>   # detach 跑，日志在 /var/log/yueops-rollout/"
     ;;
 esac
 
 # ── 7. 收口：回读四真相 ────────────────────────────────────────────────────
 lock_heartbeat
 log "回读四真相"
 FINAL_STATE=$(cd "$ROOT" && uv run python scripts/release-state.py 2>&1) || true
 echo "$FINAL_STATE"
 grep -q '^component  *HEAD  *pin' <<<"$FINAL_STATE" || die "部署后未取得四真相表，不能确认完成"
 if [ "$COMPONENT" = yue-node ]; then
   log "节点镜像发布与签名 desired 更新完成；舰队滚动尚未执行。"
 else
   # Other components may be UNKNOWN (notably an unswept fleet). Only the
   # deployed component must be measured, aligned, and still at this candidate.
   # HEAD may advance during the build, but both signed desired and observed
   # production must still name this candidate. An input-equivalent older live
   # revision is not proof that this deployment reached the intended revision.
   awk -v component="$COMPONENT" -v revision="$REV" '
     $1 == component { count++; r = substr(revision, 1, 12); if ($6 != "OK" || $3 != r || $5 != r) invalid=1 }
     END { exit (count != 1 || invalid) }
   ' <<<"$FINAL_STATE" || die "${COMPONENT} 部署后未确认候选版本四真相对齐，不能确认完成"
   log "完成：${COMPONENT} 的源代码、pin、promote 与生产版本已对齐。"
 fi
 
+lock_evidence deploy-readback deploy-preflight "preparation completed"
 lock_evidence deploy-readback deploy "$FINAL_STATE"

hook: PreToolUse
hook: PreToolUse Completed
exec
/bin/zsh -lc 'git diff -U30 738b27d41d763eb28d7531e656354f346f968666 e65cba164f8858da9ac1a62016676c77343e31a0 -- scripts/release-lock.py scripts/ship-sshd-authority.py' in /Users/j/codex-runs/mh1105/yt-113
 succeeded in 0ms:
diff --git a/scripts/release-lock.py b/scripts/release-lock.py
index c65126b3..25851d2a 100644
--- a/scripts/release-lock.py
+++ b/scripts/release-lock.py
@@ -549,96 +549,107 @@ def owned_process(lock: dict, owner=None) -> bool:
                 return True
             seen.add(pid)
             pid = parents.get(pid, 0)
         return False
     if not lock.get('live_process'):
         if lock.get('owner') != (owner or _identity()):
             return False
         # Legacy records have no PID. New records require actual ancestry.
         return not lock.get('pid') or (lock.get('host') == socket.gethostname()
                                       and descends(os.getpid(), lock['pid']))
     owner_pid = os.environ.get('YUETO_RELEASE_LOCK_PID', '')
     if not owner_pid:
         # Old ship exports only owner. /proc/environ cannot see assignments made
         # after bash started, so also recognize its exact historical fallback.
         prefix = 'ship-ui' if lock.get('reason') == 'ship-ui.sh' else 'ship.sh'
         expected = lock.get('process_owner') or f"{prefix}:{socket.gethostname().split('.')[0]}:{lock['pid']}"
         return (lock.get('kind') == 'ship' and descends(os.getpid(), lock['pid'])
                 and (owner or _identity()) == expected)
     if not owner_pid.isdigit() or not os.environ.get('YUETO_RELEASE_LOCK_OWNER'):
         return False
     return (descends(os.getpid(), int(owner_pid))
             and (lock['pid'] == int(owner_pid)
                  or (descends(lock['pid'], int(owner_pid))
                      and (lock.get('process_owner') == os.environ['YUETO_RELEASE_LOCK_OWNER']
                           or any(row['pid'] == int(owner_pid) for row in live_releases(rows))))))
 
 
 def terminal_proven(lock: dict) -> bool:
     evidence = lock.get('terminal_evidence')
     return (isinstance(evidence, dict) and evidence.get('state') in
-            {'ci-concluded', 'deploy-readback'} and isinstance(evidence.get('proof'), str)
+            {'ci-concluded', 'deploy-readback', 'pre-mutation-failed'} and isinstance(evidence.get('proof'), str)
             and bool(evidence['proof'].strip())
             and _valid_timestamp(evidence.get('at')) and not lock.get('pending_operations'))
 
 
 def dead_local(lock: dict, rows: dict) -> bool:
     pid = lock.get('pid')
     if lock.get('host') != socket.gethostname() or type(pid) is not int or pid <= 1:
         return False
     live = rows.get(pid)
     if live and live.get('_birth_unavailable'):
         return False
     return not live or bool(lock.get('process_start') and live['process_start'] != lock['process_start'])
 
 
 def cmd_evidence(args: argparse.Namespace) -> int:
     """Record proof, or invalidate old proof BEFORE starting a remote operation.
 
     Recovery uses the original owner and an exact inspected hash; the operator
     must supply the terminal run/conclusion or completed deployment readback.
     """
     if not args.proof.strip():
         print('REFUSED: terminal evidence must not be empty', file=sys.stderr)
         return 1
     found = False
     for lock in load_locks(strict=True):
         recovery = (args.expect_sha256 and lock.get('_sha256') == args.expect_sha256
                     and lock.get('owner') == _identity()
                     and dead_local(lock, {r['pid']: r for r in process_table()}))
         if not (owned_process(lock) or recovery) or lock.get('_unknown'):
             continue
         if args.expect_sha256 and lock.get('_sha256') != args.expect_sha256:
             continue
         payload = {k: v for k, v in lock.items() if not k.startswith('_') and k != 'stale'}
         pending = payload.setdefault('pending_operations', {})
-        if args.state == 'pending':
+        if args.state in {'pre-mutation-failed', 'cutover-started'}:
+            expected_key = 'deploy-preflight' if args.state == 'pre-mutation-failed' else 'deploy'
+            if args.key != expected_key or (args.state == 'pre-mutation-failed' and 'deploy' in pending):
+                print('REFUSED: deployment may have mutated services; retain pending evidence', file=sys.stderr)
+                return 1
+        if args.state == 'cutover-started':
+            # Atomically replace the read-only preparation with possible mutation.
+            # A lost remote reply can never turn this back into preflight evidence.
+            pending.pop('deploy-preflight', None)
+            pending['deploy'] = args.proof
+            payload.pop('terminal_evidence', None)
+        elif args.state == 'pending':
             pending[args.key] = args.proof
             payload.pop('terminal_evidence', None)
         else:
             pending.pop(args.key, None)
             payload['terminal_evidence'] = dict(state=args.state, proof=args.proof, at=_now())
         path = Path(lock['_path'])
         tmp = path.with_suffix('.json.tmp')
         tmp.write_text(json.dumps(payload))
         _require_inventory_inode()
         tmp.replace(path)
         found = True
     if not found:
         print('REFUSED: no matching owned record for terminal evidence', file=sys.stderr)
         return 1
     return 0
 
 
 def retire_dead_locks() -> None:
     """Called only under inventory_transaction; preserve evidence before unlink."""
     rows = {r['pid']: r for r in process_table()}
     for lock in load_locks(strict=True):
         if lock.get('_legacy') or lock.get('_unknown'):
             continue
         pid = lock.get('pid')
         if lock.get('host') != socket.gethostname() or type(pid) is not int or pid <= 1:
             continue
         if not _valid_timestamp(lock.get('started_at')):
             continue
         if not dead_local(lock, rows):
             continue
@@ -981,61 +992,61 @@ def cmd_check(args: argparse.Namespace) -> int:
         return 0
     print("CONFLICT: a release lock covers " + ",".join(repos))
     for lock in clash:
         print(_describe(lock))
     if any(lock.get("stale") for lock in clash):
         print("\nSTALE is not terminal evidence. The registered owner must close its "
               "operation, then use release --expect-sha256 from status --json. "
               "TTL and dead local PIDs never prove completion. Use evidence --state ci-concluded or deploy-readback --key <operation> --proof <run-id/conclusion or readback receipt> --expect-sha256 <record hash> with the original owner, then check/release.")
     return 1
 
 
 def main(argv: list[str] | None = None) -> int:
     parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
     parser.add_argument("--ttl", type=int, default=DEFAULT_TTL_SECONDS)
     sub = parser.add_subparsers(dest="cmd", required=True)
 
     p = sub.add_parser("acquire", help="声明一次发版在途")
     p.add_argument("--repos", required=True, help="逗号分隔；fleet 表示舰队滚动/面板部署")
     p.add_argument("--reason", default="", help="一句话：在发什么")
     p.add_argument("--force", action="store_true", help="deprecated; never bypasses conflicts")
     p.add_argument("--lane")
     p.add_argument("--worktree", default=str(ROOT))
     p.add_argument("--kind", choices=("ship", "rollout"), default="ship")
     p.set_defaults(func=cmd_acquire)
 
     p = sub.add_parser("release", help="Release the registered owner after closing its operation")
     p.add_argument("--expect-sha256", type=record_sha256, help="Require this exact raw record SHA-256 from status --json")
     p.set_defaults(func=cmd_release)
 
     p = sub.add_parser('evidence', help='Record terminal proof or a pending remote operation')
-    p.add_argument('--state', choices=('pending', 'ci-concluded', 'deploy-readback'), required=True)
+    p.add_argument('--state', choices=('pending', 'ci-concluded', 'deploy-readback', 'pre-mutation-failed', 'cutover-started'), required=True)
     p.add_argument('--key', required=True)
     p.add_argument('--proof', required=True)
     p.add_argument('--expect-sha256', type=record_sha256)
     p.set_defaults(func=cmd_evidence)
 
     p = sub.add_parser("heartbeat", help="长发版每跑完一步刷一次，证明自己还活着")
     p.set_defaults(func=cmd_heartbeat)
 
     p = sub.add_parser("holds", help="0=自己的锁已覆盖这些仓 / 1=有锁但不覆盖 / 3=没有锁（ship.sh 用）")
     p.add_argument("--repos", required=True)
     p.set_defaults(func=cmd_holds)
 
     p = sub.add_parser("status", help="列出当前所有锁")
     p.add_argument("--json", action="store_true", help="emit a read-only versioned snapshot")
     p.set_defaults(func=cmd_status)
 
     p = sub.add_parser("check", help="退出码 1 = 有冲突（钩子用）")
     p.add_argument("--repos", required=True)
     p.add_argument("--all-owners", action="store_true")
     p.set_defaults(func=cmd_check)
 
     args = parser.parse_args(argv)
     # Atomic rename protects readers from partial JSON, but cannot prevent two
     # acquirers passing the same conflict check or a heartbeat reviving a release.
     # All mutations use one short local transaction; status/holds stay read-only.
     if args.cmd in {"acquire", "heartbeat", "release", "check", "evidence"}:
         try:
             with inventory_transaction():
                 if args.cmd in {"acquire", "check"}:
                     retire_dead_locks()
diff --git a/scripts/ship-sshd-authority.py b/scripts/ship-sshd-authority.py
index afbc35a0..9b78b345 100755
--- a/scripts/ship-sshd-authority.py
+++ b/scripts/ship-sshd-authority.py
@@ -47,64 +47,62 @@ def positive_bound(name: str, default: int, ceiling: int) -> int:
         raise Refused("invalid_" + name)
     value = int(text)
     if value > ceiling:
         raise Refused("invalid_" + name)
     return value
 
 
 def authority_limits() -> tuple[int, int, int, int]:
     step = positive_bound("YUETO_AUTHORITY_STEP_TIMEOUT", REMOTE_STEP_TIMEOUT, 3600)
     connect = positive_bound("YUETO_AUTHORITY_CONNECT_TIMEOUT", 12, 300)
     attempts = positive_bound("YUETO_AUTHORITY_ATTEMPTS", 3, 8)
     backoff = positive_bound("YUETO_AUTHORITY_BACKOFF_SECONDS", 2, 60)
     return step, connect, attempts, backoff
 
 
 def authority_budget(step: int) -> int:
     return 2 * step + 120
 
 
 def proxy_jump() -> str:
     """Optional SSH config alias. Empty keeps a direct connection to the production host."""
     text = os.environ.get("YUETO_SSH_PROXY_JUMP", "").strip()
     if text == "":
         return ""
     if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,252}", text) is None:
         raise Refused("invalid_proxy_jump")
     return text
 
 
 def readonly_retryable(reason: str) -> bool:
-    """Transport and steal timeouts only. Signature and native refusals are not retried."""
-    if reason.startswith("command_failed_255"):
-        return True
-    return reason in {"command_failed_124:timeout", "command_failed_78:TimeoutExpired"}
+    """Retry only classified transient SSH failures, never native refusals."""
+    return reason in {"command_failed_255:" + code for code in _TRANSIENT_TRANSPORT}
 PRIMARY = "D9D3C6E59E7465BD07C2177142239A996FDA9F55"
 VERIFIER = "scripts/verify-signed-release-root-20260822.py"
 VERIFIER_SHA = "acab35cc20d9d21698f0b2c3869686297c15f3822ed62290a84c86b367153bbe"
 ENTRY = "scripts/converge-sshd-boundary-authority.sh"
 LIBRARY = "scripts/lib/sshd-startup-boundary-consumer-20260822.sh"
 CONTROLLER = "scripts/converge-cloudflared-sshd-startup-boundary-20260822.sh"
 HEX40 = re.compile(r"[0-9a-f]{40}\Z")
 HEX64 = re.compile(r"[0-9a-f]{64}\Z")
 STATUS_KEYS = {"schema", "status", "mode", "source_revision", "runtime_id",
                "active_generation", "last_good_generation", "native_bootstrap_verified", "bindings_verified"}
 
 
 # Identical sanitizer bytes run locally and in the isolated remote program.
 DIAGNOSTICS = r'''
 import re
 def safe_detail(value):
     if not isinstance(value, str) or not value:
         return ""
     line = value.splitlines()[0]
     # Drop the remainder at credential/connection markers: quoted values may
     # contain spaces and malformed connection strings must still fail closed.
     line = re.sub(r"(?i)(?:password|passwd|pwd|secret|token|(?:host|hostaddr|user|username|dbname|database|port|sslmode)\s*=|[a-z][a-z0-9+.-]*://).*", "<redacted>", line)
     # Quoted paths can contain whitespace; redact the whole quoted value.
     line = re.sub(r"([\"'])(?:(?!\1).)*[/\\](?:(?!\1).)*\1", "<redacted>", line)
     line = re.sub(r"[^\s\"'<>]*[/\\][^\s\"'<>]*", "<redacted>", line)
     line = re.sub(r"(?<![\w])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![\w])", "<redacted>", line)
     line = re.sub(r"(?i)(?<![\w])(?:[0-9a-f]*:){2,}[0-9a-f:.]*(?:%[\w.-]+)?", "<redacted>", line)
     line = ''.join(c if 32 <= ord(c) < 127 else '?' for c in line)
     return line[:200]
 

codex
- 已审查指定区间的 diff 与 4 个提交，未发现需阻断合并的正确性、回归或安全问题。
- 改动符合提交意图；新增测试覆盖准备失败、变更边界及继承锁，超时测试调整与重试策略一致。
- 仅静态审查，未运行测试或验证生产状态。

VERDICT: approve
tokens used
40,205
- 已审查指定区间的 diff 与 4 个提交，未发现需阻断合并的正确性、回归或安全问题。
- 改动符合提交意图；新增测试覆盖准备失败、变更边界及继承锁，超时测试调整与重试策略一致。
- 仅静态审查，未运行测试或验证生产状态。

VERDICT: approve
Finished: 2026-11-05T03:45:53Z exit=0
