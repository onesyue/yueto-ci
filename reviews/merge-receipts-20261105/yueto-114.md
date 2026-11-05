# yueto #114 review at c8e8134ca4e80bdf815a561e44a1bc6d368ac786

Reviewed range: 28c7e9b2e91d2574617d56a2f82d8e1f1d3e1330..c8e8134ca4e80bdf815a561e44a1bc6d368ac786 (post-merge backfill; codex on mac-5f08d00f, read-only sandbox)
Started: 2026-11-05T03:44:46Z

Reading additional input from stdin...
OpenAI Codex v0.166.0
--------
workdir: /Users/j/codex-runs/mh1105/yt-114
model: gpt-6-astra
provider: openai
approval: never
sandbox: read-only
reasoning effort: medium
reasoning summaries: none
session id: 01a1a9cf-24c9-76e2-ac99-c018a164e549
--------
user
You are reviewing merged PR onesyue/yueto #114 at exact head c8e8134ca4e80bdf815a561e44a1bc6d368ac786. Review ONLY the diff: git diff 28c7e9b2e91d2574617d56a2f82d8e1f1d3e1330 c8e8134ca4e80bdf815a561e44a1bc6d368ac786 (and git log 28c7e9b2e91d2574617d56a2f82d8e1f1d3e1330..c8e8134ca4e80bdf815a561e44a1bc6d368ac786). Do not modify files. Check correctness, regressions, weakened/removed tests, security, and that the change matches its title/intent. Output a final line exactly 'VERDICT: approve' or 'VERDICT: changes' followed by concise bullet findings.
2026-11-05T03:44:52.287876Z ERROR codex_models_manager::manager: failed to refresh available models: request timed out
hook: SessionStart
hook: SessionStart Completed
codex
我将只审查指定提交区间的 diff 和提交日志，不修改文件；重点检查正确性、回归、测试削弱、安全性及提交意图的一致性。

hook: PreToolUse
hook: PreToolUse Completed
exec
/bin/zsh -lc 'cat CLAUDE.md' in /Users/j/codex-runs/mh1105/yt-114
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
/bin/zsh -lc 'git diff --stat 28c7e9b2e91d2574617d56a2f82d8e1f1d3e1330 c8e8134ca4e80bdf815a561e44a1bc6d368ac786 && git log --format=fuller 28c7e9b2e91d2574617d56a2f82d8e1f1d3e1330..c8e8134ca4e80bdf815a561e44a1bc6d368ac786' in /Users/j/codex-runs/mh1105/yt-114
 succeeded in 0ms:
 scripts/i18n/data/servers.name_i18n.tsv | 176 ++++++++++++++++++--------------
 scripts/i18n/gen-node-names.py          |  45 ++++++--
 scripts/i18n/test-gen-node-names.py     |  98 ++++++++++++++++++
 3 files changed, 233 insertions(+), 86 deletions(-)
commit c8e8134ca4e80bdf815a561e44a1bc6d368ac786
Author:     onesyue <47652916+onesyue@users.noreply.github.com>
AuthorDate: Thu Nov 5 10:56:36 2026 +0800
Commit:     onesyue <47652916+onesyue@users.noreply.github.com>
CommitDate: Thu Nov 5 10:56:36 2026 +0800

    fix(i18n): accept spaced node names in gen-node-names (R-14)

hook: PreToolUse
hook: PreToolUse Completed
exec
/bin/zsh -lc 'git diff 28c7e9b2e91d2574617d56a2f82d8e1f1d3e1330 c8e8134ca4e80bdf815a561e44a1bc6d368ac786' in /Users/j/codex-runs/mh1105/yt-114
 succeeded in 0ms:
diff --git a/scripts/i18n/data/servers.name_i18n.tsv b/scripts/i18n/data/servers.name_i18n.tsv
index a7287660..daa652cf 100644
--- a/scripts/i18n/data/servers.name_i18n.tsv
+++ b/scripts/i18n/data/servers.name_i18n.tsv
@@ -1,76 +1,100 @@
-3	悦·🇭🇰香港家宽1💎	Yue · 🇭🇰 Hong Kong Residential 1 💎
-5	悦·🇭🇰香港家宽2💎	Yue · 🇭🇰 Hong Kong Residential 2 💎
-7	悦·🇹🇼台湾家宽1💎	Yue · 🇹🇼 Taiwan Residential 1 💎
-9	悦·🇹🇼台湾家宽2💎	Yue · 🇹🇼 Taiwan Residential 2 💎
-11	悦·🇯🇵日本专属1💎	Yue · 🇯🇵 Japan Dedicated 1 💎
-13	悦·🇯🇵日本专属2💎	Yue · 🇯🇵 Japan Dedicated 2 💎
-15	悦·🇺🇸美国专属1💎	Yue · 🇺🇸 USA Dedicated 1 💎
-17	悦·🇺🇸美国专属2💎	Yue · 🇺🇸 USA Dedicated 2 💎
-19	悦·🇸🇬新加坡专属1💎	Yue · 🇸🇬 Singapore Dedicated 1 💎
-21	悦·🇸🇬新加坡专属2💎	Yue · 🇸🇬 Singapore Dedicated 2 💎
-23	悦·🇲🇾马来西亚专属1💎	Yue · 🇲🇾 Malaysia Dedicated 1 💎
-24	悦·🇲🇾马来西亚专属2💎	Yue · 🇲🇾 Malaysia Dedicated 2 💎
-25	悦·🇮🇳印度专属1💎	Yue · 🇮🇳 India Dedicated 1 💎
-26	悦·🇮🇳印度专属2💎	Yue · 🇮🇳 India Dedicated 2 💎
-27	悦·🇬🇧英国专属1💎	Yue · 🇬🇧 UK Dedicated 1 💎
-28	悦·🇬🇧英国专属2💎	Yue · 🇬🇧 UK Dedicated 2 💎
-29	悦·🇯🇵日本家宽1💎	Yue · 🇯🇵 Japan Residential 1 💎
-30	悦·🇯🇵日本家宽2💎	Yue · 🇯🇵 Japan Residential 2 💎
-33	悦·🇰🇷韩国家宽1💎	Yue · 🇰🇷 Korea Residential 1 💎
-34	悦·🇰🇷韩国家宽2💎	Yue · 🇰🇷 Korea Residential 2 💎
-35	悦·🇻🇳越南家宽1💎	Yue · 🇻🇳 Vietnam Residential 1 💎
-36	悦·🇻🇳越南家宽2💎	Yue · 🇻🇳 Vietnam Residential 2 💎
-37	悦·🇺🇸美国AI解锁1💎	Yue · 🇺🇸 USA AI Unlock 1 💎
-38	悦·🇺🇸美国AI解锁2💎	Yue · 🇺🇸 USA AI Unlock 2 💎
-39	悦·🇯🇵日本AI解锁1💎	Yue · 🇯🇵 Japan AI Unlock 1 💎
-40	悦·🇯🇵日本AI解锁2💎	Yue · 🇯🇵 Japan AI Unlock 2 💎
-41	悦·🇸🇬新加坡AI解锁1💎	Yue · 🇸🇬 Singapore AI Unlock 1 💎
-42	悦·🇸🇬新加坡AI解锁2💎	Yue · 🇸🇬 Singapore AI Unlock 2 💎
-43	悦·🇭🇰香港1	Yue · 🇭🇰 Hong Kong 1
-45	悦·🇭🇰香港2	Yue · 🇭🇰 Hong Kong 2
-47	悦·🇹🇼台湾1	Yue · 🇹🇼 Taiwan 1
-49	悦·🇹🇼台湾2	Yue · 🇹🇼 Taiwan 2
-51	悦·🇯🇵日本1	Yue · 🇯🇵 Japan 1
-53	悦·🇯🇵日本2	Yue · 🇯🇵 Japan 2
-55	悦·🇺🇸美国1	Yue · 🇺🇸 USA 1
-57	悦·🇺🇸美国2	Yue · 🇺🇸 USA 2
-59	悦·🇰🇷韩国1	Yue · 🇰🇷 Korea 1
-61	悦·🇰🇷韩国2	Yue · 🇰🇷 Korea 2
-63	悦·🇸🇬新加坡1	Yue · 🇸🇬 Singapore 1
-65	悦·🇸🇬新加坡2	Yue · 🇸🇬 Singapore 2
-67	悦·🇹🇭泰国1	Yue · 🇹🇭 Thailand 1
-69	悦·🇹🇭泰国2	Yue · 🇹🇭 Thailand 2
-71	悦·🇲🇾马来西亚1	Yue · 🇲🇾 Malaysia 1
-73	悦·🇲🇾马来西亚2	Yue · 🇲🇾 Malaysia 2
-75	悦·🇮🇳印度1	Yue · 🇮🇳 India 1
-77	悦·🇮🇳印度2	Yue · 🇮🇳 India 2
-79	悦·🇻🇳越南1	Yue · 🇻🇳 Vietnam 1
-81	悦·🇻🇳越南2	Yue · 🇻🇳 Vietnam 2
-83	悦·🇬🇧英国1	Yue · 🇬🇧 UK 1
-85	悦·🇬🇧英国2	Yue · 🇬🇧 UK 2
-87	悦·🇩🇪德国1	Yue · 🇩🇪 Germany 1
-89	悦·🇩🇪德国2	Yue · 🇩🇪 Germany 2
-91	悦·🇳🇱荷兰1	Yue · 🇳🇱 Netherlands 1
-93	悦·🇳🇱荷兰2	Yue · 🇳🇱 Netherlands 2
-95	悦·🇪🇸西班牙1	Yue · 🇪🇸 Spain 1
-97	悦·🇪🇸西班牙2	Yue · 🇪🇸 Spain 2
-99	悦·🇸🇪瑞典1	Yue · 🇸🇪 Sweden 1
-101	悦·🇸🇪瑞典2	Yue · 🇸🇪 Sweden 2
-103	悦·🇨🇦加拿大1	Yue · 🇨🇦 Canada 1
-105	悦·🇨🇦加拿大2	Yue · 🇨🇦 Canada 2
-107	悦·🇧🇷巴西1	Yue · 🇧🇷 Brazil 1
-109	悦·🇧🇷巴西2	Yue · 🇧🇷 Brazil 2
-111	悦·🇲🇽墨西哥1	Yue · 🇲🇽 Mexico 1
-113	悦·🇲🇽墨西哥2	Yue · 🇲🇽 Mexico 2
-115	悦·🇦🇪阿联酋1	Yue · 🇦🇪 UAE 1
-117	悦·🇦🇪阿联酋2	Yue · 🇦🇪 UAE 2
-119	悦·🇹🇷土耳其1	Yue · 🇹🇷 Turkey 1
-121	悦·🇹🇷土耳其2	Yue · 🇹🇷 Turkey 2
-123	悦·🇦🇺澳大利亚1	Yue · 🇦🇺 Australia 1
-125	悦·🇦🇺澳大利亚2	Yue · 🇦🇺 Australia 2
-127	悦·🇳🇬尼日利亚1	Yue · 🇳🇬 Nigeria 1
-129	悦·🇳🇬尼日利亚2	Yue · 🇳🇬 Nigeria 2
-131	悦·🇳🇿新西兰1	Yue · 🇳🇿 New Zealand 1
-133	悦·🇳🇿新西兰2	Yue · 🇳🇿 New Zealand 2
-135	悦·🇷🇺俄罗斯1	Yue · 🇷🇺 Russia 1
-137	悦·🇷🇺俄罗斯2	Yue · 🇷🇺 Russia 2
+3	悦 · 🇭🇰 香港家宽1💎	Yue · 🇭🇰 Hong Kong Residential 1 💎
+5	悦 · 🇭🇰 香港家宽2💎	Yue · 🇭🇰 Hong Kong Residential 2 💎
+7	悦 · 🇹🇼 台湾家宽1💎	Yue · 🇹🇼 Taiwan Residential 1 💎
+9	悦 · 🇹🇼 台湾家宽2💎	Yue · 🇹🇼 Taiwan Residential 2 💎
+11	悦 · 🇯🇵 日本专属1💎	Yue · 🇯🇵 Japan Dedicated 1 💎
+13	悦 · 🇯🇵 日本专属2💎	Yue · 🇯🇵 Japan Dedicated 2 💎
+15	悦 · 🇺🇸 美国专属1💎	Yue · 🇺🇸 USA Dedicated 1 💎
+17	悦 · 🇺🇸 美国专属2💎	Yue · 🇺🇸 USA Dedicated 2 💎
+19	悦 · 🇸🇬 新加坡专属1💎	Yue · 🇸🇬 Singapore Dedicated 1 💎
+21	悦 · 🇸🇬 新加坡专属2💎	Yue · 🇸🇬 Singapore Dedicated 2 💎
+23	悦 · 🇲🇾 马来西亚专属1💎	Yue · 🇲🇾 Malaysia Dedicated 1 💎
+24	悦 · 🇲🇾 马来西亚专属2💎	Yue · 🇲🇾 Malaysia Dedicated 2 💎
+25	悦 · 🇮🇳 印度专属1💎	Yue · 🇮🇳 India Dedicated 1 💎
+26	悦 · 🇮🇳 印度专属2💎	Yue · 🇮🇳 India Dedicated 2 💎
+27	悦 · 🇬🇧 英国专属1💎	Yue · 🇬🇧 UK Dedicated 1 💎
+28	悦 · 🇬🇧 英国专属2💎	Yue · 🇬🇧 UK Dedicated 2 💎
+29	悦 · 🇯🇵 日本家宽1💎	Yue · 🇯🇵 Japan Residential 1 💎
+30	悦 · 🇯🇵 日本家宽2💎	Yue · 🇯🇵 Japan Residential 2 💎
+33	悦 · 🇰🇷 韩国家宽1💎	Yue · 🇰🇷 Korea Residential 1 💎
+34	悦 · 🇰🇷 韩国家宽2💎	Yue · 🇰🇷 Korea Residential 2 💎
+35	悦 · 🇻🇳 越南家宽1💎	Yue · 🇻🇳 Vietnam Residential 1 💎
+36	悦 · 🇻🇳 越南家宽2💎	Yue · 🇻🇳 Vietnam Residential 2 💎
+37	悦 · 🇺🇸 美国AI解锁1💎	Yue · 🇺🇸 USA AI Unlock 1 💎
+38	悦 · 🇺🇸 美国AI解锁2💎	Yue · 🇺🇸 USA AI Unlock 2 💎
+39	悦 · 🇯🇵 日本AI解锁1💎	Yue · 🇯🇵 Japan AI Unlock 1 💎
+40	悦 · 🇯🇵 日本AI解锁2💎	Yue · 🇯🇵 Japan AI Unlock 2 💎
+41	悦 · 🇸🇬 新加坡AI解锁1💎	Yue · 🇸🇬 Singapore AI Unlock 1 💎
+42	悦 · 🇸🇬 新加坡AI解锁2💎	Yue · 🇸🇬 Singapore AI Unlock 2 💎
+43	悦 · 🇭🇰 香港1	Yue · 🇭🇰 Hong Kong 1
+45	悦 · 🇭🇰 香港2	Yue · 🇭🇰 Hong Kong 2
+47	悦 · 🇹🇼 台湾1	Yue · 🇹🇼 Taiwan 1
+49	悦 · 🇹🇼 台湾2	Yue · 🇹🇼 Taiwan 2
+51	悦 · 🇯🇵 日本1	Yue · 🇯🇵 Japan 1
+53	悦 · 🇯🇵 日本2	Yue · 🇯🇵 Japan 2
+55	悦 · 🇺🇸 美国1	Yue · 🇺🇸 USA 1
+57	悦 · 🇺🇸 美国2	Yue · 🇺🇸 USA 2
+59	悦 · 🇰🇷 韩国1	Yue · 🇰🇷 Korea 1
+61	悦 · 🇰🇷 韩国2	Yue · 🇰🇷 Korea 2
+63	悦 · 🇸🇬 新加坡1	Yue · 🇸🇬 Singapore 1
+65	悦 · 🇸🇬 新加坡2	Yue · 🇸🇬 Singapore 2
+67	悦 · 🇹🇭 泰国1	Yue · 🇹🇭 Thailand 1
+69	悦 · 🇹🇭 泰国2	Yue · 🇹🇭 Thailand 2
+71	悦 · 🇲🇾 马来西亚1	Yue · 🇲🇾 Malaysia 1
+73	悦 · 🇲🇾 马来西亚2	Yue · 🇲🇾 Malaysia 2
+75	悦 · 🇮🇳 印度1	Yue · 🇮🇳 India 1
+77	悦 · 🇮🇳 印度2	Yue · 🇮🇳 India 2
+79	悦 · 🇻🇳 越南1	Yue · 🇻🇳 Vietnam 1
+81	悦 · 🇻🇳 越南2	Yue · 🇻🇳 Vietnam 2
+83	悦 · 🇬🇧 英国1	Yue · 🇬🇧 UK 1
+85	悦 · 🇬🇧 英国2	Yue · 🇬🇧 UK 2
+87	悦 · 🇩🇪 德国1	Yue · 🇩🇪 Germany 1
+89	悦 · 🇩🇪 德国2	Yue · 🇩🇪 Germany 2
+91	悦 · 🇳🇱 荷兰1	Yue · 🇳🇱 Netherlands 1
+93	悦 · 🇳🇱 荷兰2	Yue · 🇳🇱 Netherlands 2
+95	悦 · 🇪🇸 西班牙1	Yue · 🇪🇸 Spain 1
+97	悦 · 🇪🇸 西班牙2	Yue · 🇪🇸 Spain 2
+99	悦 · 🇸🇪 瑞典1	Yue · 🇸🇪 Sweden 1
+101	悦 · 🇸🇪 瑞典2	Yue · 🇸🇪 Sweden 2
+103	悦 · 🇨🇦 加拿大1	Yue · 🇨🇦 Canada 1
+105	悦 · 🇨🇦 加拿大2	Yue · 🇨🇦 Canada 2
+107	悦 · 🇧🇷 巴西1	Yue · 🇧🇷 Brazil 1
+109	悦 · 🇧🇷 巴西2	Yue · 🇧🇷 Brazil 2
+111	悦 · 🇲🇽 墨西哥1	Yue · 🇲🇽 Mexico 1
+113	悦 · 🇲🇽 墨西哥2	Yue · 🇲🇽 Mexico 2
+115	悦 · 🇦🇪 阿联酋1	Yue · 🇦🇪 UAE 1
+117	悦 · 🇦🇪 阿联酋2	Yue · 🇦🇪 UAE 2
+119	悦 · 🇹🇷 土耳其1	Yue · 🇹🇷 Turkey 1
+121	悦 · 🇹🇷 土耳其2	Yue · 🇹🇷 Turkey 2
+123	悦 · 🇦🇺 澳大利亚1	Yue · 🇦🇺 Australia 1
+125	悦 · 🇦🇺 澳大利亚2	Yue · 🇦🇺 Australia 2
+127	悦 · 🇳🇬 尼日利亚1	Yue · 🇳🇬 Nigeria 1
+129	悦 · 🇳🇬 尼日利亚2	Yue · 🇳🇬 Nigeria 2
+135	悦 · 🇷🇺 俄罗斯1	Yue · 🇷🇺 Russia 1
+137	悦 · 🇷🇺 俄罗斯2	Yue · 🇷🇺 Russia 2
+139	悦 · 🇫🇷 法国1	Yue · 🇫🇷 France 1
+141	悦 · 🇫🇷 法国2	Yue · 🇫🇷 France 2
+143	悦 · 🇳🇵 尼泊尔1	Yue · 🇳🇵 Nepal 1
+145	悦 · 🇳🇵 尼泊尔2	Yue · 🇳🇵 Nepal 2
+147	悦 · 🇧🇩 孟加拉1	Yue · 🇧🇩 Bangladesh 1
+149	悦 · 🇧🇩 孟加拉2	Yue · 🇧🇩 Bangladesh 2
+151	悦 · 🇵🇭 菲律宾1	Yue · 🇵🇭 Philippines 1
+153	悦 · 🇵🇭 菲律宾2	Yue · 🇵🇭 Philippines 2
+155	悦 · 🇲🇲 缅甸1	Yue · 🇲🇲 Myanmar 1
+157	悦 · 🇲🇲 缅甸2	Yue · 🇲🇲 Myanmar 2
+159	悦 · 🇦🇷 阿根廷1	Yue · 🇦🇷 Argentina 1
+161	悦 · 🇦🇷 阿根廷2	Yue · 🇦🇷 Argentina 2
+163	悦 · 🇰🇭 柬埔寨1	Yue · 🇰🇭 Cambodia 1
+165	悦 · 🇰🇭 柬埔寨2	Yue · 🇰🇭 Cambodia 2
+167	悦 · 🇮🇩 印度尼西亚1	Yue · 🇮🇩 Indonesia 1
+169	悦 · 🇮🇩 印度尼西亚2	Yue · 🇮🇩 Indonesia 2
+170	悦 · 保底HY2 SG	Yue · Fallback HY2 SG
+171	悦 · 保底 SG	Yue · Fallback SG
+172	悦 · 保底HY2 JP	Yue · Fallback HY2 JP
+173	悦 · 保底 JP	Yue · Fallback JP
+174	悦 · 保底HY2 NL	Yue · Fallback HY2 NL
+175	悦 · 保底 NL	Yue · Fallback NL
+176	悦 · 保底HY2 US	Yue · Fallback HY2 US
+177	悦 · 保底 US	Yue · Fallback US
+178	悦 · 🇺🇸 美国家宽1💎（维护中）	Yue · 🇺🇸 USA Residential 1 💎 (Maintenance)
+179	悦 · 🇺🇸 美国家宽2💎（维护中）	Yue · 🇺🇸 USA Residential 2 💎 (Maintenance)
diff --git a/scripts/i18n/gen-node-names.py b/scripts/i18n/gen-node-names.py
index 2dcec2b5..fed47255 100755
--- a/scripts/i18n/gen-node-names.py
+++ b/scripts/i18n/gen-node-names.py
@@ -67,6 +67,11 @@ COUNTRIES = {
     "芬兰": "Finland",
     "挪威": "Norway",
     "丹麦": "Denmark",
+    "尼泊尔": "Nepal",
+    "孟加拉": "Bangladesh",
+    "缅甸": "Myanmar",
+    "柬埔寨": "Cambodia",
+    "印度尼西亚": "Indonesia",
 }
 
 # 限定词。顺序要紧：先长后短，否则 "AI解锁" 里的 "解锁" 之类会被短的先吃掉。
@@ -90,36 +95,52 @@ class Unrecognized(Exception):
 
 
 def translate_node_name(zh: str) -> str:
-    """`悦·🇭🇰香港家宽1💎` → `Yue · 🇭🇰 Hong Kong Residential 1 💎`"""
+    """Translate compact or spaced names without changing the English layout."""
     rest = zh.strip()
 
     prefix = ""
     if rest.startswith(BRAND_ZH):
         prefix = BRAND_EN
-        rest = rest[len(BRAND_ZH):]
-    rest = rest.lstrip("·・· ")
+        rest = rest[len(BRAND_ZH) :].lstrip()
+    rest = re.sub(r"^[·・\s]+", "", rest)
+
+    maintenance = ""
+    m = re.search(r"（\s*维护中\s*）$", rest)
+    if m:
+        maintenance = "(Maintenance)"
+        rest = rest[: m.start()].rstrip()
 
     flag = ""
     m = FLAG.match(rest)
     if m:
         flag = m.group()
-        rest = rest[m.end():]
+        rest = rest[m.end() :].lstrip()
 
     gem = ""
     if rest.endswith("💎"):
         gem = "💎"
-        rest = rest[:-1]
+        rest = rest[:-1].rstrip()
+
+    # Guaranteed-access nodes use a protocol and region code, not a country name.
+    if rest.startswith("保底"):
+        m = re.fullmatch(r"保底\s*(HY2|vless)?\s*([A-Z]{2})", rest)
+        if not m:
+            raise Unrecognized(f"Unrecognized guaranteed-access node: {zh!r}")
+        body = " ".join(
+            p for p in (flag, "Fallback", m[1], m[2], gem, maintenance) if p
+        )
+        return f"{prefix} · {body}" if prefix else body
 
     m = re.search(r"(\d+)\s*$", rest)
     index = m.group(1) if m else ""
     if m:
-        rest = rest[: m.start()]
+        rest = rest[: m.start()].rstrip()
 
     country_en = ""
     for zh_name, en_name in sorted(COUNTRIES.items(), key=lambda kv: -len(kv[0])):
         if rest.startswith(zh_name):
             country_en = en_name
-            rest = rest[len(zh_name):]
+            rest = rest[len(zh_name) :].lstrip()
             break
     if not country_en:
         raise Unrecognized(f"认不出国家/地区：{zh!r}（剩余 {rest!r}）")
@@ -128,15 +149,19 @@ def translate_node_name(zh: str) -> str:
     for zh_q, en_q in QUALIFIERS:
         if rest.startswith(zh_q):
             qualifier_en = en_q
-            rest = rest[len(zh_q):]
+            rest = rest[len(zh_q) :]
             break
 
     rest = rest.strip()
     if CJK.search(rest):
         raise Unrecognized(f"名字里有没被词典覆盖的中文：{zh!r}（剩余 {rest!r}）")
 
-    parts = [p for p in (prefix, flag, country_en, qualifier_en, rest, index, gem) if p]
-    # 品牌与其余部分之间保留 ` · `，与中文版的 `悦·` 视觉一致
+    parts = [
+        p
+        for p in (prefix, flag, country_en, qualifier_en, rest, index, gem, maintenance)
+        if p
+    ]
+    # Keep the established English brand separator.
     if prefix and len(parts) > 1:
         return parts[0] + " · " + " ".join(parts[1:])
     return " ".join(parts)
diff --git a/scripts/i18n/test-gen-node-names.py b/scripts/i18n/test-gen-node-names.py
new file mode 100644
index 00000000..590a3f87
--- /dev/null
+++ b/scripts/i18n/test-gen-node-names.py
@@ -0,0 +1,98 @@
+"""Offline R-14 parser and command-line regression tests."""
+
+import importlib.util
+import subprocess
+import sys
+from pathlib import Path
+
+import pytest
+
+SCRIPT = Path(__file__).with_name("gen-node-names.py")
+spec = importlib.util.spec_from_file_location("node_names", SCRIPT)
+assert spec and spec.loader
+names = importlib.util.module_from_spec(spec)
+spec.loader.exec_module(names)
+
+
+@pytest.mark.parametrize("separator", ["", " ", "\t", "\u2003"])
+@pytest.mark.parametrize("qualifier,english", [("", ""), *names.QUALIFIERS])
+@pytest.mark.parametrize("gem", ["", "💎"])
+@pytest.mark.parametrize("maintenance", ["", "（维护中）"])
+def test_token_whitespace(separator, qualifier, english, gem, maintenance):
+    tokens = ["悦", "·", "🇹🇼", "台湾", qualifier, "1", gem, maintenance]
+    source = separator + separator.join(t for t in tokens if t) + separator
+    expected = "Yue · 🇹🇼 Taiwan"
+    if english:
+        expected += " " + english
+    expected += " 1"
+    if gem:
+        expected += " 💎"
+    if maintenance:
+        expected += " (Maintenance)"
+    assert names.translate_node_name(source) == expected
+
+
+@pytest.mark.parametrize("separator", ["", " ", "\t", "\u2003"])
+@pytest.mark.parametrize("protocol", ["", "HY2", "vless"])
+def test_fallback_names(separator, protocol):
+    source = separator.join(["悦", "·", "保底", protocol, "SG"])
+    expected = "Yue · Fallback " + (protocol + " " if protocol else "") + "SG"
+    assert names.translate_node_name(source) == expected
+
+
+@pytest.mark.parametrize(
+    "source",
+    [
+        "悦·🇹🇼未知1",
+        "悦 · 🇹🇼 台湾未知1",
+        "悦 · 保底other SG",
+        "悦 · 保底HY2",
+        "悦 · 🇺🇸 美国1（未知）",
+        "unrecognized",
+        "",
+    ],
+)
+def test_unknown_names_raise(source):
+    with pytest.raises(names.Unrecognized):
+        names.translate_node_name(source)
+
+
+def test_generated_data():
+    rows = (
+        SCRIPT.with_name("data")
+        .joinpath("servers.name_i18n.tsv")
+        .read_text()
+        .splitlines()
+    )
+    for row in rows:
+        _, source, expected = row.split("\t")
+        assert source.startswith("悦 · ")
+        assert names.translate_node_name(source) == expected
+        assert names.translate_node_name(source.replace(" ", "")) == expected
+
+
+def test_cli_reports_unknown_and_exits_nonzero(tmp_path):
+    source = tmp_path / "names.tsv"
+    source.write_text("1\t悦 · 🇹🇼 台湾1\n2\t悦 · 未知1\n")
+    result = subprocess.run(
+        [sys.executable, str(SCRIPT), "--from-tsv", str(source)],
+        capture_output=True,
+        text=True,
+        check=False,
+    )
+    assert result.returncode == 1
+    assert result.stdout == "1\t悦 · 🇹🇼 台湾1\tYue · 🇹🇼 Taiwan 1\n"
+    assert "id=2" in result.stderr
+
+
+def test_cli_sql(tmp_path):
+    source = tmp_path / "names.tsv"
+    source.write_text("47\t悦 · 🇹🇼 台湾1\n")
+    result = subprocess.run(
+        [sys.executable, str(SCRIPT), "--from-tsv", str(source), "--sql"],
+        capture_output=True,
+        text=True,
+        check=True,
+    )
+    assert '"en": "Yue · 🇹🇼 Taiwan 1"' in result.stdout
+    assert "WHERE id = 47;" in result.stdout

codex
- 指定 diff 与提交意图一致：支持节点名称中的空白，并补充保底节点及维护状态翻译。
- 未发现可确认的正确性、回归或安全问题；新增测试覆盖紧凑格式兼容、空白变体和错误处理，没有删除或削弱既有测试。
- 仅审查指定 diff 和提交日志，未运行测试，未修改文件。

VERDICT: approve
tokens used
24,949
- 指定 diff 与提交意图一致：支持节点名称中的空白，并补充保底节点及维护状态翻译。
- 未发现可确认的正确性、回归或安全问题；新增测试覆盖紧凑格式兼容、空白变体和错误处理，没有删除或削弱既有测试。
- 仅审查指定 diff 和提交日志，未运行测试，未修改文件。

VERDICT: approve
Finished: 2026-11-05T03:45:37Z exit=0
