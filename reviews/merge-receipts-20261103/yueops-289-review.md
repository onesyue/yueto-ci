# Codex review: yueops #289 at merged head 5a5201b2044f7ed2c9112ae5825e59d5d36af831

Codex reviewed git diff 8585daa3..5a5201b2 at the exact head and approved it.

## Parity note

- In a clean worktree at 5a5201b2, the CI-equivalent venv passes: 34 passed.
- The local dev venv (extra packages) fails test_plan_apply_preserves_loadshed_and_rolls_back_on_drift with SimpleNamespace st_size. That test was the cause.
- The test patched os.fstat globally. Fixed test-only in yueops #291 (merged 549e1568, Codex approve). After the fix, 34 pass in the dev venv too.

VERDICT: approve   (or VERDICT: changes)
followed by concise bullet findings with file:line.
codex
I’ll read the repository guidance, then review the specified diff and relevant context without modifying files or printing secrets.
exec
/bin/bash -lc 'pwd; cat CLAUDE.md; cat ../AGENTS.md; cat ../CLAUDE.md' in /home/box/Projects/yueto/yueops
 succeeded in 0ms:
/home/box/Projects/yueto/yueops
# CLAUDE.md

> **Runbook:** `docs/RUNBOOK.md`. The reviewed, signed and pushed Git revision is authoritative. The former node documentation distribution entry point is retired; do not maintain per-host copies. **Topology source:** `docs/live-deployment-topology.md`. **Baseline tag:** `baseline-20260528`.
> Consult memory (`MEMORY.md` index) for historical, dated details. This file retains durable constraints and architecture guidance. Dated observations below are not fresh production measurements.

## Overview

YueOps has five components: Python CLI, FastAPI web service, modular React frontend, Telegram Bot (yue), and YueLink Checkin API. User interfaces support Simplified Chinese and English. Python ≥3.10; React 19 + TypeScript (rewritten from Vue 3 in v4.0). The active protocols are **HY2 + Reality**; AnyTLS, ShadowTLS and SS2022 are retired.

**Do not use this document as the fleet count.** Direct hosts, serving assignments and unique enabled nodes come from `scripts/node-control-auth-migrate.py --baseline-check`, production inventory and the applicable canonical rollout evidence. Documents are projections that expire; a stale handwritten count can make a guard assert a false production fact and still pass. Historical explicit baseline reviews, including dates, SIDs and reasons for changes to all three counts, are preserved in the `yueops-agent-deploy` skill's fleet review history.

## Skills loaded on demand (`.claude/skills/`)

This file is persistent session context. A 2026-08-29 measurement found it consumed about 33k tokens by itself. Domain-specific knowledge was moved verbatim to `.claude/skills/` at that time; load the relevant skill before working in its domain. Skills are also linked under `~/.claude/skills/` for discovery from other directories. Only their approximately 100-token frontmatter is loaded at startup.

| Skill | Coverage |
|---|---|
