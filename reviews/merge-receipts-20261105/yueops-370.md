# yueops #370 review at afee5980662fa189e13490f0a7bf803c44861097

VERDICT: approve   (or VERDICT: changes)
followed by concise bullet findings with file:line.
codex
I’ll review the exact diff and repository guidance, focusing on auth, data exposure, and API/DB behavior parity. I won’t modify files.
exec
/bin/zsh -lc 'pwd; git status --short; git rev-parse HEAD; cat CLAUDE.md; for f in ../AGENTS.md ../CLAUDE.md; do if [ -f "$f" ]; then cat "$f"; fi; done' in /Users/j/codex-runs/1104d/yueops
 succeeded in 0ms:
/Users/j/codex-runs/1104d/yueops
error: fsmonitor_ipc__send_query: unspecified error on '/Users/j/Projects/yueto/yueops/.git/worktrees/yueops5/fsmonitor--daemon.ipc'
afee5980662fa189e13490f0a7bf803c44861097
# CLAUDE.md

> **Runbook:** `docs/RUNBOOK.md`. The reviewed, signed and pushed Git revision is authoritative. The former node documentation distribution entry point is retired; do not maintain per-host copies. **Topology source:** `docs/live-deployment-topology.md`. **Baseline tag:** `baseline-20260528`.
> Consult memory (`MEMORY.md` index) for historical, dated details. This file retains durable constraints and architecture guidance. Dated observations below are not fresh production measurements.

## Overview

YueOps has five components: Python CLI, FastAPI web service, modular React frontend, Telegram Bot (yue), and YueLink Checkin API. User interfaces support Simplified Chinese and English. Python ≥3.10; React 19 + TypeScript (rewritten from Vue 3 in v4.0). The active protocols are **HY2 + Reality**; AnyTLS, ShadowTLS and SS2022 are retired.

**Do not use this document as the fleet count.** Direct hosts, serving assignments and unique enabled nodes come from `scripts/node-control-auth-migrate.py --baseline-check`, production inventory and the applicable canonical rollout evidence. Documents are projections that expire; a stale handwritten count can make a guard assert a false production fact and still pass. Historical explicit baseline reviews, including dates, SIDs and reasons for changes to all three counts, are preserved in the `yueops-agent-deploy` skill's fleet review history.

## Skills loaded on demand (`.claude/skills/`)


| Skill | Coverage |
|---|---|
| `yueops-agent-deploy` | Host agent `scripts/agent.sh`, deploy_mode, per-VPS Docker layout |
| `yueops-host-hardening` | Three-stage inspection/hardening/recovery, memory and hang prevention, sysctl/kernel safety, automation levels L0–L3 |
| `yueops-deploy-gotchas` | Platform and deployment incidents |
| `yueops-panel-db-gotchas` | YueBoard panel and shared database incidents |
| `yueops-business-gotchas` | Business rules and database retention |
| `yueops-emby` | Emby media service |
| `yueops-ai-support` | Xiaoyue AI support |
| `yueops-telegram` | Telegram Bot, known issues and Mini App |
| `yueops-business-features` | Checkin/Play/UNO, fair-use audit, referral VIP rebates, invite aliases, prediction v8 and YueLink conventions |

Workspace skills include `guard-authoring`, `release-chain`, `node-lifecycle`, `fleet-diagnose`, `pg-safety`, `generated-blocks` and `round-closeout`. **Read `guard-authoring` before changing guards, `release-chain` before releases, and `pg-safety` before migrations or GRANT statements.**

## Commands

