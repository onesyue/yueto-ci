# Codex review — yueops #231 @ af53fb7e8884e8edacf675956e7c5c6abc386e96

Box `codex exec -s read-only`, prompt scoped to `git diff <merge-base> af53fb7e8884e8edacf675956e7c5c6abc386e96`. Reviewed 2026-11-02T16:56:39Z.
Parity: docker build --target debbuild/acmebuild/verifytools of services/yueops-web/Dockerfile at exact head on the box, log `yueops-231.log` (sha256 69c4e4c2820c954a8c3dc64d1cc59f26da6d7f018d516aa1ff0e49478eb8fb95). The two changed FROM lines (alpine:3.24 digest) are in debbuild and acmebuild; verifytools (gh module sum check) also passed on the box, so the earlier Mac gh-sum failure was environmental. Final python:3.13-slim stages not built (box apt network), unchanged by this PR. Pins checked against sum.golang.org/proxy.golang.org for gh v2.96.0: match.
Admission: check-shared-input-seal.py on simulated merge with origin/master: SHARED_INPUTS_UNCHANGED. Owner rules: no rule affected (base image digest only).

```
I’ll read the repository guidance and review the exact diff, using surrounding code where needed to check for regressions. I won’t modify files or print secret values.
exec
/bin/bash -lc 'cat CLAUDE.md ../AGENTS.md ../CLAUDE.md' in /home/box/Projects/yueto/yueops
 succeeded in 0ms:
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

```bash
pip install -e .                                   # CLI; requirements.txt installs all backend dependencies
docker restart yueops-web                         # production; development: uvicorn web.app:app :8010 -w1
cd frontend && npm install && npm run dev           # :5173; build: TS7 tsc -b && vite build; typecheck/lint/test scripts also exist
yueops init|deploy|status|update|cert|nft|rebuild|migrate|route [-s SERVER | -t TAG | -a]
docker restart checkin-api                         # production; development: uvicorn main:app :8011

# Tests / CI gate (.github/workflows/ci-backend.yml)
TZ=UTC bash scripts/run-pytest-parallel.sh           # full suite; central CI also sets YUEOPS_PYTEST_SERIAL=1; +08 results are not equivalent
pytest tests/test_chicken_box.py -q                 # file-level debugging; conftest supplies sqlite:/// and fake credentials
pytest tests/test_safety_fake_email.py::test_xxx     # individual case; use pytest -k 'fake_email' across files
python3 -m compileall -q web checkin-api telegram-bot/yue
python3 scripts/check-design-tokens.py              # shared scale across five surfaces, including Mini App inline styles
# Source: ../docs/yue-visual-language-2026.md; pytest coverage: tests/test_design_token_consistency_20260728.py
# Mini App .tsx must use var(--yt-fs-*) / var(--yt-r-*), never bare fontSize/borderRadius numbers.
# Full cross-repository gate: ../scripts/check-all-contracts.sh
bash scripts/security_scan.sh --json                # secret/DSN gate; nonzero FAIL blocks; allowlist: scripts/security_scan.allowlist
# Migration gate (sql-migration-lint / Squawk): changed *.sql only; reject DDL that locks or rewrites existing tables.
python3 -m venv "$TMPDIR/sq" && "$TMPDIR/sq/bin/pip" install 'squawk-cli==2.60.0'
# Match central CI. Avoid npx: failed downloads mean the check did not run; postinstall bytes are not pinned.
"$TMPDIR/sq/bin/squawk" --pg-version=15.0 --assume-in-transaction --exclude=prefer-robust-stmts,prefer-text-field,prefer-identity,require-timeout-settings <changed.sql>
```

- **Bastion CLI invocation requires every input below.** There is no wrapper; the bastion venv has no `yueops` console script, and the three groups of runtime facts are not populated in the environment. Missing inputs fail closed:
  ```bash
  set -a; . /etc/yueops-fleet-inventory.env; set +a          # read-only per-machine inventory DB role
  export YUEOPS_GH_ATTESTATION_TOKEN_FILE=/etc/yueops/gh-attestation-token  # default /run/secrets/... is absent here
  export YUEOPS_RUNTIME_GID=65532                            # token file ownership is root:65532
  export YUEOPS_CERT_DIR=/opt/yueops/certs                   # actual certificates; servers.yaml's config/certs/ does not exist here
  cd /opt/yueops && PYTHONPATH=/opt/yueops venv/bin/python -m yueops.cli deploy -s <sid>
  ```
  Omitting `YUEOPS_CERT_DIR` caused an outage on 2026-08-02: `yue-tw` discovered the missing certificate path only after quiesce and `docker rm`. Both containers were gone, compose had not started, the maintenance lease remained open and :443 was unavailable. `require_local_hy2_certificate_material` now checks readability in the host-read-only phase; the other three inputs remain mandatory.
- **Inventory consistency is a deployment prerequisite, and DDNS can break it.** `load_native_server_configs()` fails closed across DB rows, per-machine credential bundles and SSH trust. A mismatch prevents loading the entire fleet, rather than skipping one host; `yueops deploy` then cannot deploy any machine. Residential dynamic-IP hosts (`yue-tw`/`-2`/`-premium-2`) update `servers.ip` through `yueops-ddns.sh`; historically nothing updated bundle `canonical_ip` under `/var/lib/yueops/node-control-auth/<sid>.json`. Since 2026-08-02 (`b7c62260`), `node-control-auth-inventory-converge.timer` reconciles every two minutes. It was not in automation-2026/install.sh's UNITS; its unit comment required manual installation, so rebuilding the bastion lost it. CLI redials also retained a ≤2-minute gap. A new `servers` row does not create a bundle (`yue-hk-1` lacked one from 07-31). **Restore consistency; never relax the loader.** Recover a missing bundle from the machine's installed credentials with `run-node-control-auth-migrate.sh recover-remote-bundle --sid <sid> --apply --ack RECOVER_PINNED_REMOTE_MACHINE_BUNDLE` (no rotation or restart). Rebind IP metadata with `rebind-inventory --sid <sid> --apply --ack REBIND_MACHINE_INVENTORY_METADATA`. Monitor `full-audit.sh`'s `fleet_inventory_bundle_drift`; the former audit read only `direct-node-inventory.sql`, leaving this broken chain green for a week.
- **The actual production compose file is `/opt/yueops-stack/compose.yaml`**, established from Docker labels. `/opt/yueops/services/compose.yaml` is a stale copy. Run `docker compose up -d --force-recreate <svc>` in the owning project directory (`docker inspect --format Labels.compose.project.working_dir`).
- Bastion systemd units `yueops-web`, `yue` and `checkin-api` were removed; all three use Docker. Change PG hosts through `/etc/yueops-secrets.env`.
- Root `scripts/ship.sh yueops` drives all three services through `scripts/deploy-yueops-digests.sh`, which requires signed image digests at the same revision. Frontend and shared AI/RAG code ship in images. Single-service rsync/recreate and legacy deployment entry points were removed.
- **yue-bot/checkin-api code is baked into images** (`/app/`; only migrations are bind-mounted). Changes require the workspace release gates → `yueto-ci` signed build/promotion → signed `release.yaml` → `scripts/ship.sh yueops --from-promoted` → readback (workspace I07). Private-repository Actions are not release evidence. `docker cp` hot patches do not persist. The 2026-07-06 section 5.12 closeout fixed three code-mount defects: checkin-api's `/telegram-bot` mount was removed and the AI core baked in. **yueops-web fleet scripts are also baked in**: since 2026-09-24 P2 C3, its Dockerfile copies only `services/yueops-web/runtime-scripts.json`, checked by `scripts/generate-web-runtime-scripts-inventory.py --check`. The `/app/scripts` host mount was removed. Script changes require push, web rebuild and deployment; editing `/opt/yueops/scripts` alone no longer installs them. `/opt/yueops` was reconciled to a clean pinned checkout, replacing the former 40 dirty paths.
- **Do not relay large manual image pushes through the panel.** A 2026-07-23 incident saturated the panel/Tailscale link, causing roughly two minutes of timeouts in the panel-hosted YueOps database and amplifying metrics/telemetry 500s. Restore private CI billing or give a non-production build host a separate least-privilege `write:packages` credential. The panel pulls images; it is not a registry push relay.

## Production topology

This is recorded topology guidance, not a new measurement. Consult the topology source and runtime evidence before operations.

| Service | Host | Port | DB |
|---------|------|------|-----|
| YueOps Web | `23.80.91.14` | 8010 | `100.85.165.26:5432/yueops` (tailnet) |
| Checkin API | `23.80.91.14` | 8011 | `198.52.244.237:6432/yue-to` (PgBouncer) |
| Telegram Bot (yue) | `23.80.91.14` | 8001 | `198.52.244.237:6432/yue-to` (PgBouncer) |
| YueBoard Panel | `66.55.76.208` | container 8080 / nginx 443 | `198.52.244.237:5432/yue-to` |
| **PG primary** | `198.52.244.237` | 5432 | **yue-to 1.1GB** (LA 2c/4G) |
| **PG standby** | `23.80.91.14` | 5432 | streaming replication, replay_lag <10ms, repmgr promote |

**Restart PG primary only with `systemctl restart postgresql@18-main`, never `pg_ctl restart`.** On 2026-08-03 at 19:41, `pg_ctl restart -m fast -w` was held by an SSH session that a simultaneous bastion restart terminated. Shutdown completed (11:41:37, "database system is shut down"), but startup never executed; the `sudo` session closed at 11:41:35. PG stayed down until a manual start at 20:56. The panel crash-looped for 75 minutes (`yueboard` restartCount 41→61), with no alerts.

The old claim that a failed systemctl/pg_ctlcluster redirect leaves PG running **does not apply to this host**: `postgresql@.service` ExecStart uses `--skip-systemctl-redirect`. A recorded `systemctl restart postgresql@18-main` completed in nine seconds (14:14:28→14:14:37) with a new postmaster PID.

Companion safeguards installed on `.237`:

- `postgresql@18-main.service.d/override.conf`: `Restart=always`, `RestartSec=10`. **Do not use `Restart=on-failure`**: fast shutdown exits 0, so that setting misses this failure. A recorded external `pg_ctl -m fast stop` recovered automatically in 12 seconds, PID 637053→644886.
- `pg-watchdog.timer` (60s) covers a stuck start: the unit has `TimeoutStartSec=infinity`, so it can remain activating forever without triggering `Restart=`. Use `pg_isready` exit codes: `2` means no response and allows intervention; `1` means rejecting connections, potentially crash recovery, which must not be interrupted.
- Planned shutdown uses `systemctl stop postgresql@18-main` or `touch /etc/postgresql-maintenance.lock`; the watchdog yields to the lock.

## Backup/recovery scope

Backup and recovery work is canceled by workspace I01
(`reports/PLAN-2026-10-28.md`, canceled-items section), including backup-alert
PR #69. Do not schedule backups, restore drills or recovery work from older
runbooks. Retained scripts/units and historical receipts do not establish a
current operating requirement or prove that installed timers were disabled.
See `docs/runbook/yueops-backup.md` for the withdrawn procedure boundary.

- **Point-in-time recovery (PITR):** Historical contract evidence only: the
  2026-09-11 record in `docs/runbook/pg-data-tools-20260821.md` reports
  pgBackRest 2.59.1, pgvector 0.8.6 and full backup `20260911-025207F`
  (`reference=none`), restored at `03:16:24Z`. This dated receipt does not
  reinstate the canceled backup/recovery work.
  Coexisting standby PG17 stayed inactive; a separate PGDG transaction at
  `04:53:55Z` updated its server/client to 17.11 and pgvector to 0.8.6 without
  changing its cluster/configuration (same dated record).

## Architecture

```text
React19 (Ant Design v6 + zustand) → Axios+JWT → FastAPI :8010
  ├── PG yueops @ 100.85.165.26:5432 (tailnet)
  ├── SSH (Paramiko) → 15 parallel threads
  ├── Scheduler → metric cleanup (>48h hourly) + stuck task reaper (>30min 60s)
  └── PG yue-to @ 198.52.244.237 → servers → yue-node node-1(hy2 apernet-hysteria)+node-2(reality xray)
       Agent (scripts/agent.sh) → POST /api/metrics/{sid}
```

### Modular frontend (v4.0 — React)

**v4.0 (2026-06) rewrote the site from Vue3 + Element Plus + Pinia to React + TypeScript + Ant Design + zustand** in one cutover, without changing the backend `/api` contract; see `frontend/CLAUDE.md`. Stack corrected against package.json on 2026-09-21: React19, react-router-dom v7 (`BrowserRouter`, HTML5 history), **antd v6** (native React19; no v5 patch), `@ant-design/icons`, zustand (auth/theme), axios, `@tanstack/react-query`, i18next + react-i18next (zh-CN keys → English; `../scripts/i18n/CONTRACT.md`), lazy `@xterm/xterm`, Motion (`motion/react`), lucide-react, Tailwind v4, Vite8, TS7 (`typescript7` alias), ESLint flat config, and `@yueops/web-kit` (`packages/yue-web-kit`, shared with Mini App).

```text
frontend/src/
├── core/  api/index.ts components/*.tsx hooks/{useTask,useTheme}.ts layouts/Shell.tsx i18n/
│         stores/auth.ts(zustand) theme/AntdProvider.tsx styles/tokens.css views/*.tsx registry.ts types.ts
├── modules/{yue-node,quality,emby,support,gambling,chicken,antispam,operations}/{index.ts,views/*.tsx}
├── App.tsx     # Routes merge core and registry.collectRoutes, with RequireAuth
└── main.tsx    # Imports register modules, then mount AntdProvider/BrowserRouter
```

URLs: `/login`, `/status` (301 → `https://status.yue.to/`), `/admin/{dashboard,servers,quality,emby,support,gambling,chicken,antispam,liveops,telemetry,tasks,settings}`. **antispam** is the Telegram moderation case ledger (false-positive rate, judge/rules split and appeals). **operations** owns `/admin/liveops` for activity orchestration and `/admin/telemetry` for anonymous YueLink experience signals. To add a module, implement `ModuleDefinition` in `modules/X/index.ts` (`routes:[{path,Component}]`, `navItems:[{path,label,icon,order}]`) and import it in `main.tsx`.

Use antd v6 for UI components. Obtain theme-aware `message`/`modal` through `App.useApp()`, not static imports. Each view/component has a same-name, non-scoped `.css` imported at the top. Tokens live in `core/styles/tokens.css`; dark mode uses `.dark` on `<html>` and Tailwind v4 `@variant dark`. The API baseURL is already `/api`; call `api.get('/servers')`, without another `/api` prefix. Build is `tsc -b && vite build` with the `typescript7` alias; `vite.config.ts` splits React/antd vendor bundles.

### Backend modules

- `yueops/deploy.py`: Docker/config/compose/cert/nft/migration/route; `BASE_DIR="/home/yue-node"`.
- `yueops/panel.py`: YueBoard shared-DB node operations. Use `update_node_host(node_id, new_host)`, never match by host value.
- `yueops/ssh.py`: Paramiko; distinguish `AuthenticationException` from connection errors.
- `yueops/dns.py`: two providers, chosen by domain suffix. `DNSPOD_DOMAINS frozenset={yuetong.online, yuetoto.net, kp-link.site, mxtn.net}`; otherwise Cloudflare.
- `web/task_runner/`: package split from a 1587-line file on 2026-09-20. `ThreadPoolExecutor(max_workers=15)`. Actions: init/deploy/deploy_direct/status/update/cert/nft/rebuild/migrate/route/switch_domain/add_ip/remove_ip/replace_ip/reinstall/reinstall_raw/prepare.
- `web/api/*`: metrics fixed routes must precede dynamic `/{sid}`. Public status routes `/api/status/{public,uptime,incidents,nodes}` require no authentication and redact to region level without IPs. `public` includes `healthy/blocked`: blocked nodes still send agent heartbeats, so online/quality alone can falsely imply health; consult `ip_status=blocked`. The 90-day uptime comes from actual incident durations. `web/static/status.html` is served by nginx `status.yue.to`, with `/api/status/` proxied to8010, Cloudflare proxy + cloudflared for access from China; other paths return404 and do not expose the admin app. Other modules: panel_nodes (`/api/panel/*`, read-only v2_server), node_doctor (`/api/internal/*`, only127.0.0.1/::1, limits30min/server and5/h globally; repair choices: cert≤5→cert, containers==0→rebuild, uptime<600→nft, otherwise→rebuild), dashboard/settings/emby/edge_roster.
- `web/ws_ticket.py`: 10-second ticket, `POST /api/tasks/ws-ticket` → WS `Sec-WebSocket-Protocol: ticket.<value>`.
- `web/scheduler.py`: import path `web.scheduler`.

### Observability (OTel traces + Langfuse; `docs/adr/0003`)

- Use **`opentelemetry-instrument` automatic instrumentation**. All three Dockerfile CMDs include it, but compose `command:` overrides CMD and must retain that prefix. Apps use host networking and loopback `OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318`. Force-recreate after OTEL environment changes.
- Collector on `.14` (`otelcol-contrib` systemd): loopback `otlp` receiver, traces pipeline to Grafana Cloud. **`send_failed_*` misses partial-success quota rejection**, as measured on2026-08-03. Grafana rejected excess series with **HTTP200 + partial success**; the exporter marked the request sent and `send_failed_metric_points` remained0 while logs rejected thousands of series. Commit7ca79c06 expanded checks from spans alone to both counters, but neither counter detects this case. Inspect partial-success logs: `journalctl -u otelcol-contrib --since '10 min ago' | grep -c 'series were rejected'` (panel: `docker logs otel-collector`); the count must be0. Also inspect `receiver_accepted - exporter_sent` in `curl 127.0.0.1:8888/metrics` to check filtering. The old `grep _spans` command missed metric429 losses (`err-mimir-max-active-series`, quota15000): on2026-08-02 traces were0 while metrics lost460,000 points unnoticed. `filter/cardinality` now bounds metrics cardinality; see `services/otel-collector.production.yaml`. Before adding a source, measure its series (`curl <exporter>/metrics | grep -vE '^#|^$' | wc -l`). Validate with `otelcol-contrib validate` before restarting.
- Export traces only: `OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none`, sampling10% with `parentbased_traceidratio`.
- **Disable httpx instrumentation in yue-bot**: `OTEL_PYTHON_DISABLED_INSTRUMENTATIONS=httpx,requests,urllib3,aiohttp-client`; outbound Telegram URLs contain the bot token.
- **Langfuse v4 needs an isolated `tracer_provider`** (`support_core/langfuse_obs.py`); defaults contaminate Tempo and Langfuse in both directions. The `langfuse` package is required. checkin-api's AI core (support_core/ai_gateway/adapters/tools/ticketing) is baked into its image: 2026-07-06 section5.12 removed `/opt/yueops/telegram-bot`, uses `pip install -e /telegram-bot/yue` (`yue-ai` editable package), and imports baked `support_core` without sys.path.insert. yue-bot also uses baked code. **Shared AI core changes require rebuilding both yue-bot and checkin-api**, not ff-pull + rsync.
- All three services use image-entrypoint `opentelemetry-instrument`. Do not modify application `sys.path` to import host helpers. Corresponding pipelines in `/etc/otelcol-contrib/config.yaml` receive and forward OTLP traces/metrics/logs.

### Two-stage rollout for check-in traffic settlement

The panel_ledger ACK consumer reads the original byte-allocation plan in reward-anchor `metadata.traffic_settlement_v1`. It validates subject, reference, idempotency key and actual receipt range, then updates every row and marks the outbox done in one transaction. Invalid plans must not fall back to single-row allocation. The plan is server-only, excluded from Board wire and user responses; existing single-row semantics for other producers stay unchanged.

Release consumer-only first, keeping the old check-in producer. Read back the images for checkin-api's resident worker and yue-bot's watch consumer, including exit of the old processes, before releasing the producer. Native service order is web → checkin → bot; **do not skip the intermediate consumer-only release**. Producer rollback must target consumer-only. While new-format work is unfinished, do not downgrade to an old consumer that cannot process it.

The producer creates all reward rows in one transaction, then links `outbox.reward_ledger_id` to the first traffic row. Plan-request bytes and Board payload use the same integer. Four-decimal GB amounts use differences between cumulative actual values; `metadata.applied_bytes` retains exact bytes.

### Database

- **YueOps:** `postgresql+psycopg://root:<pwd>@100.85.165.26:5432/yueops` (tailnet). 18 models: User(`must_change_password`)/Server(`deploy_mode`)/ServerNode(type hy2|reality)/Task/TaskTarget/Setting/ServerMetric(>48h cleanup)/NodeQualitySummary/ProbeResult/AuditLog/Incident/OpsAlertOutbox/OpsAlertBatch/OpsMetricHourly/ServerEgressHourly/ServerPeakDaily/StatusDaily/SupportLoadDaily.
  Alert outbox/immutable batches/hourly metrics: alembic0020. StatusDaily: daily public status history,0021. SupportLoadDaily/SSO mapping/public notification receipts:0022. ServerEgressHourly: per-host hourly outbound aggregates, retained400days and written by the hourly scheduler before48h cleanup,0024. ServerPeakDaily: per-host China-peak (20:00–23:00 +08) nightly summary, same writer pattern,0025. CfProfile/SniRotation/SniHealthCheck were retired with CF-SNI routing on2026-07-31 (0011/0012).
- **Shared business DB** (yue/checkin-api/YueBoard): primary `198.52.244.237:5432/yue-to`. Runtime verification on2026-09-15 found yue-bot/checkin-api using colocated **PgBouncer6432**; do not mistake the primary's direct port for those containers' actual connection port. Roles: `app_yueops/app_yue_bot/app_checkin/app_yueboard/app_exporter`. Panel role cutover, dual-role observation and old-login removal must follow `docs/runbook/yueboard-db-role-native-cutover.md`. `.14` is hot standby.
- **Least privilege after the2026-07-23 table rename:** `app_checkin`/`app_yue_bot` may write only their respective keep sets. Actual names come from `scripts/sql/pg-least-privilege-yue-to.sql` and permission tests. `v2_*` descriptions apply only before migration00010; do not derive new GRANT statements from them.
- Root `alembic/` owns only yueops. `telegram-bot/yue/migrations/*.sql` owns only yue-to. Do not mix them.
- **Shared DSN environment `/etc/yueops-secrets.env`:** `YUEOPS_PG_HOST=100.85.165.26 .../yueops/app_yueops` (tailnet), `YUETO_PG_HOST=198.52.244.237 .../yue-to/root` (direct, bypassing PgBouncer). Legacy `PG_HOST=/DB_HOST=` defaults to yue-to. Timer scripts source `[ -r /etc/yueops-secrets.env ] && . /etc/yueops-secrets.env`. `env.setdefault` is first-wins; source secrets first when overriding defaults.
- PG15+ public schema owner is pg_database_owner. app_* roles lack CREATE; use root for that operation.

### Auth API

- **Two-factor login is mandatory (2026-09-26).** Primary entry: YueBoard admin's YueOps console item → `/sso/board` → `POST /auth/board-sso`; Board TOTP/passkey supplies the second factor. Public `POST /auth/login` password validation is only the first factor and returns `{second_factor_required:true, second_factor:"board_sso"}`, **without issuing a session**. Accounts without `board_user_id` return403 `second_factor_unavailable`. Bastion loopback with no `CF-Connecting-IP` is the password-only emergency entry, returning `{access_token, must_change_password}`. `POST /auth/change-password` accepts `{old_password,new_password}` (≥8 characters).
- WS `/api/tasks/{id}/ws` accepts the token only in `Sec-WebSocket-Protocol`, never the query string.
- Trust X-Forwarded-For only when `request.client.host` is127.0.0.1 or`::1`.

## Known issues

The original domain-specific incident guidance was moved into skills: platform/deployment → `yueops-deploy-gotchas`; YueBoard/shared DB → `yueops-panel-db-gotchas`; business rules → `yueops-business-gotchas`; Telegram → `yueops-telegram`; memory/hang prevention/sysctl/kernel → `yueops-host-hardening`. These are required reading before touching the relevant domain; each rule comes from a production incident.

## Conventions

- Secrets (`servers.yaml`, `certs/`, `data/`) are ignored by Git. Do not document the default administrator password. The live password was rotated and must-change enabled. VPS base is `/home/yue-node/`, root, SSH22.
- Domains: `yuetong.online` (DNSPod, wildcard certificate) for direct nodes; `yuetoto.net` (DNSPod international) for relays. The recorded active relay pool is the multi-A endpoint `edge-874f3eba.yuetoto.net`, with two Japanese dynamic residential entries. The old `v4.yuetoto.net` name from before2026-09-02 is NXDOMAIN. Scripts must read `V4_RELAY_PUBLIC_NAME` from `/etc/default/yueops-entry-pools`, never hard-code it. Read membership only from `.v4_relays`; do not reconstruct it from old TW/HK/KR/JP relay history.
- Node types: `hy2` (`node-1/`, native apernet-hysteria) and `reality` (`node-2/`, xray).
- **HY2 certificates:** active direct hosts share the yuetong.online wildcard. `yueops-cert-renew.timer` runs on the1st/15th monthly; ≤30days remaining triggers acme.sh and full distribution.

## Protocol architecture

| Role | Protocol | Applicability |
|---|---|---|
| Primary performance | HY2 (apernet-hysteria node-1/) | All A/B direct hosts |
| Primary stability | VLESS-Reality (xray node-2/) | All A/B direct hosts |

A flagship regions: HK/TW/JP/US/SG. B coverage: KR/TH/MY/IN/AE/TR/UK/ES/SE/BR/AU/VN/NG. Former C long-tail IPv6 destinations retired on2026-07-09. A `parent_id` child shares its parent's process and has no separate container/directory. The container's `node_id` is the ID of the parent whose `parent_id IS NULL`.

## Operations SOP index

Sources: `docs/ops/00_inventory.md` (subsystems/deployments/timer matrix/data flows/manual checklist) and `docs/RUNBOOK.md` (incidents).

- **Alerts use the same durable spool on three hosts:** bastion, storage `.97`, Emby `.198` (the latter two added2026-08-12). `yue-tg-notify.sh` is a thin client submitting to `/run/yue-tg-notify/submit.sock`; socket-activated `yue-tg-notify-submit@` persists requests under `/var/lib/yue-tg-notify/pending`. Only `yue-tg-notify-drain.timer` (15s) reads `/etc/yue-tg-notify.env` and sends externally. **Never scp only `yue-tg-notify.sh`:** its initial `[[ -x $HELPER && ! -L $HELPER ]] || exit 2` makes missing helpers/sockets silence the entire host. Install all seven files (`yue-tg-notify-spool.py`, `yue-tg-notify.sh`, five units) under `/opt/yueops/scripts/usr-local-sbin/`, then run `scripts/converge-yue-tg-notify.sh`. It verifies credentials and the old spool, installs worker/socket/timer, runs a real probe and synchronous drain, and only then atomically replaces the thin client. Earlier failure restores previous bytes and activation state. See `docs/runbook/telegram-notification-spool.md`. `validate-spool` atomically archives old root-owned32-hex0644 empty markers (`.97` had44) into `legacy-v0/`; they never suppress new alerts. Existing64-hex0600 v1 markers remain effective in place.
- **Automatic notifications:** admin Telegram, five-minute cooldown, `/usr/local/sbin/yue-tg-notify.sh "title" "body"`; silence with `touch /etc/yue-tg-notify.silent`. Triggers include disk80% warning/90% emergency vacuum; ticket backlog>20 or single-ticket age>24h; AI ticket storms/faithfulness<0.8/eval-regression failure; abuser-ban rollback(6h); v4 relay traffic anomalies; low OpenRouter balance/watchdog restart; panel subscription delivery failures (≥5 failDelivery or subscription-route5xx in10minutes, or5xx ratio>2%, read from panel counters by `payment-reconcile-watch`).
- `ai-quality-weekly-report` sends the admin Telegram report Sundays09:00.
- New automation requires a script `scripts/<name>.{py,sh}`, systemd service/timer, an entry in `00_inventory.md` section3, notifications through yue-tg-notify.sh, and PR classification L0–L3 with rollback command.
# Yue.to workspace

Read [CLAUDE.md](CLAUDE.md) before working here, then the target component's
`CLAUDE.md`. This root contains independent repositories, not a monorepo.
The same instructions and skills apply to Codex and Claude; current user
authorization takes precedence over historical plans and permission reminders.

Owner decision (2026-10-20): acceptance contracts for large items must still be
recorded before implementation, but no Claude-specific or fixed-model approval
is required. The currently authorized main session owns coordination and proceeds
within the owner's scope without redundant coordinator sign-off. Claude's absence
is not a blocker. Independent review, risk-proportional gates, release ownership,
production readback and rollback remain required where applicable. Escalate only
unresolved owner-level decisions or work outside existing authorization; never
weaken acceptance silently. See R4.12's coordination-authority amendment in the
sole execution plan. This decision supersedes conflicting inherited instructions.

Owner decision (2026-10-20): choose and adjust parallel lanes for every task from
its independent work, dependencies, available agents/resources and review/release
capacity. Three lanes, a prior session layout or a template is never a fixed
quota or ceiling. Use fewer lanes for coupled work and more for ready independent
work when capacity permits. Prefer durable asynchronous waits; reuse or release
idle workers without abandoning their recorded jobs, evidence or leases. Preserve
one source writer per repository, independent review and actual resource limits.

Owner decision (2026-10-23): execution plans must require no human participation
or future cooperation. Retain only concrete AI-accessible work with available
inputs, finite machine-verifiable acceptance, an automatic failure exit and
applicable rollback. Withdraw human-dependent, unavailable and unbounded work
from scheduling; preserve historical unmet evidence without claiming success.
Independent review may be performed by another AI agent. This does not authorize
bypassing permissions, financial/authentication invariants or release gates,
abandoning in-flight recovery, or deleting installed schedules or stored data.
The sole plan's R4.2h and current R4.12 control define the executable scope.

Canonical skills live in `.claude/skills/`; `.agents/skills/` exposes the same
files to Codex through relative links. Do not maintain a second copy.
`scripts/sync-agent-skills.py --check` checks project discovery;
`--apply --user` also installs the workspace and component skills for both
agents in this user's local skill directories without overwriting other skills.

Agent setup and verified commands: [docs/agent-tooling.md](docs/agent-tooling.md).
Claude loads `.claude/rules/` by path. Codex must read the applicable rule file
explicitly: `generated-blocks.md` for generated sources, `guard-scripts.md` for
guards, `release-pins.md` for release inputs, and `fleet-baseline.md` for inventory.
The root Codex SessionStart hook shares the read-only snapshot implementation;
hook availability depends on the client's native trust and configuration.

Use the newest dated closeout as a starting point, then independently read
source, tests and production. Keep historical observations dated. A missing
measurement is UNKNOWN; removing an unsupported task is not proof it passed.
Run `scripts/status-all.sh` before interpreting cross-repository checks and
`scripts/heavy-run.sh --exclusive bash scripts/gauntlet.sh` before release (direct `scripts/gauntlet.sh` exits 2). Follow the existing signed release chain.

## Execution discipline (owner feedback, 2026-10-12: "slow, divergent, repeats work")

Evidence rules above set the *standard*, not the *volume*. Scale verification to
risk (docs/copy/tests: targeted tests; service code: module suite + the CI lens,
i.e. the Linux container; money/auth/migrations/prod/fleet: full gate + prod
read-back). Land a verified batch at least every 90 minutes. Every action maps to a
checklist item; out-of-scope findings go to a one-line "Parked" list unless P0.
Reuse evidence already recorded in the round doc for the same object and
revision; do not re-measure or re-read unchanged material. One lane per question,
and a darwin-skipped test is not a passed test.

The following owner rules are tracked here so a fresh checkout does not depend
on a workstation-only `~/.codex/AGENTS.md`:

- Deliver a small, single-topic, verifiable batch within 90 minutes. If blocked,
  record the blocker and expected resolution in the round log. Ready fixes do
  not wait for wider audits.
- Name the checklist item for each action. Only P0 incidents (production outage,
  data loss or an actively exploited vulnerability) may interrupt the scope.
- Reuse evidence for the same object and revision. Remeasure only when the
  object changes, evidence exceeds 24 hours, or evidence conflicts. Do not reread
  whole files already read in the session. After two identical command failures,
  investigate the cause or change approach before retrying.
- Report status changes: what changed, where the evidence is, and what is next.
  Close an item once its acceptance criteria are met; do not keep polishing it.
- Use exact-path staging in each independent repository. Do not overwrite
  another session's work or change an executing script's bytes.
- Preserve owner-opened interactive sessions. Coordination, takeover, an idle
  screen or a release-lock conflict does not authorize signaling, closing or
  injecting input into the owner's Grok, Codex, Claude or terminal session.
  Stop only a worker this session created, or one explicitly transferred to
  this session, with a verified receipt (session ID, PID and start time); an
  owner instruction to stop the specific session also authorizes it. Reading
  another lane's receipt does not transfer ownership. Otherwise record the
  conflict in the existing inbox and keep independent work moving. See
  `yueto-orchestration` for the process-ownership boundary.
- Repository documentation, including historical audit and release narratives,
  and explanatory comments use English. Preserve product translations, exact
  test inputs, protocol values and original evidence identifiers. Reply to the
  owner in Chinese unless requested otherwise.
- The sole production execution entry is
  `docs/2026-10-17-whole-estate-execution-plan.md`, starting at its current r4
  control section and linked production backlog. Update that plan in place;
  do not create a competing master plan. The 10-16 focused plan supplies inherited
  acceptance contracts, not current scheduling. Agent maintenance is recorded in
  `docs/2026-10-16-agent-maintenance-round.md`; the English backlog remains in
  `docs/2026-10-16-english-cleanup-round.md` and its existing CSV.

- Owner decision (2026-10-20): backup creation/verification, off-site backup
  work, PITR/disaster-restore drills, and backup-retirement planning are canceled
  from current and future work. Do not reintroduce them as tasks, observation
  waits or admission prerequisites from inherited plans, skills or old findings
  unless the owner explicitly reverses this decision. See R4.2b in the sole
  execution plan. Preserve historical evidence. This planning exclusion does
  not cancel release rollback, interrupted-transaction recovery, live replication
  or client connection recovery; it does not authorize deleting stored data or
  changing installed production schedules.
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

exec
/bin/bash -lc 'git diff --stat b49ac9278431e20daf126089328237901f0b6cb7 af53fb7e8884e8edacf675956e7c5c6abc386e96' in /home/box/Projects/yueto/yueops
 succeeded in 0ms:
 services/yueops-web/Dockerfile | 4 ++--
 1 file changed, 2 insertions(+), 2 deletions(-)

exec
/bin/bash -lc 'cat .agents/skills/yueops-deploy-gotchas/SKILL.md' in /home/box/Projects/yueto/yueops
 succeeded in 0ms:
---
name: yueops-deploy-gotchas
description: 'yueops 平台与部署层的已知坑清单——镜像/compose/nginx/证书/DNS/入口/CI 这一层。改部署链、动 compose 或 nginx、排查"部署了但没生效/502/证书/入口 404"时先读它。Use when deploying yueops services or debugging platform-level breakage.'
---

# yueops-deploy-gotchas

> 本文逐字取自 `yueops/CLAUDE.md`，**内容一字未改**——只是从「每次会话都加载」
> 换成「相关时才加载」。这些事实全部来自真实生产事故，删改前先确认它已经不成立。

### 平台/部署

- **datetime** naive UTC `datetime.utcnow()`。
- **🚨 一大批 systemd 单元同时 `status=226/NAMESPACE` → 先看 `/dev/null` 还是不是字符设备**（2026-08-02 bastion 实测）。`ls -l /dev/null` 若是 regular file，则所有带 `PrivateDevices=`/`ProtectSystem=strict` 的单元一律起不来（日志 `Failed to set up mount namespacing: /dev: Inappropriate ioctl for device`，systemd 另有一行 `/dev/null is not a device.`），本次一次性打掉 17 个单元，其中包括 `yue-tg-notify-drain`（**告警自己也发不出去**）和 `direct-pool-dns-reconciler`。修复 `rm -f /dev/null && mknod -m 666 /dev/null c 1 3`（已打开旧 inode 的进程不受影响，无需重启）。**别看文件内容找元凶**：任何 `cmd > /dev/null` 都会把它 truncate 重写，内容只反映最后一个写者（本次是 4 字节 `nvm\n`，纯噪音）。判据是 `stat -c %w`（birth）。
  - **🔎 元凶已定位（2026-08-02 复盘）= `install -m0755 <src> /dev/null`**，root 经 SSH 跑的一条临时运维命令，birth `14:05:52.83` 与它的下发时刻 `14:05:52.228` 相差 0.6s，且全量会话记录里这是唯一一次把 `/dev/null` 放在**目的位**。**机理已在同一台机、同一个 devtmpfs 上复现**：`install` 会先 `unlink` 目的路径再新建常规文件，**默认模式恰好是 0755**——与现场的 `regular file / 0755` 逐位吻合。同类危险动词还有 `mv`、`cp --remove-destination`、`rsync`（都换 inode）；而 `install -m0600 /dev/null "$f"`（`/dev/null` 在**源位**）是安全且常用的建空文件写法，两者只差参数顺序。
  - ⚠️ **owner 那一位没查实**：现场是 uid 65532/gid root，但 `install` 在本机复现出来的是 `0:0`，且 14:05:53–14:25:51 之间找不到任何 chown 到 65532 的东西（ctime 已被 14:27 的 `cp -a ... 2>/dev/null` 覆盖，时刻不可考）。**不要把 uid 65532 当成「容器干的」的证据**——它没有被解释，仅此而已。
  - **守卫 `dev-null-integrity-guard.timer`（5min）**：`stat -c "%F %a %t:%T"` 不等于 `character special file 666 1:3` 即告警 + 自动 `mknod` 修复 + 落凭据 `/var/log/yueops-dev-null-guard.log`；另抓「成片 226/NAMESPACE」这一指纹。🚨 **它的 unit 故意不带任何 mount-namespace 加固项，脚本里也一个 `> /dev/null` 都不许有**——两者都会让守卫和被守护对象一起死；`tests/test_dev_null_integrity_guard.py` 会在被「顺手加固」时让 CI 变红，并顺带禁止全仓再出现把 `/dev/null` 当目的位的写法。
- **NFT**：`nft delete table ... || true`（不用 destroy）；防火墙现由 `yueops-tuning` .deb 拥有（canonical `/etc/nftables.conf` 模板，UDP hop 固定 20000-40000；生成器 `vps_opt_nft.sh` 2026-07-16 已删）。watchdog 内任何 `docker inspect` 必 `timeout 3`（防 nft-boot Before=docker 循环依赖死锁 [[feedback_vps_opt_nft_deadlock]]）。每台必 `nft-boot.service` enabled（现 .deb 包拥有）。
- **🚨 xray geodata 必须单文件挂载** `/home/yue-node/geodata/geoip.dat:/usr/local/bin/geoip.dat:ro`（目录挂载会覆盖二进制）。
- **节点 config.yml 错配**：部署后 `grep -E 'type:|node_id' node-*/config.yml`。容器内 `node_id` 必填 `parent_id IS NULL` 父节点 id。
- **🚨 config.yml 是 instances-only schema（2026-07-29 全队硬切，yue-node `f53cfa6` 起）**：根键白名单只有 `{instances,kernel,cert,log,node,runtime,sync}`，顶层 `panel:` 会被**直接拒绝加载**（容器反复重启，日志 `top-level field "panel" is not allowed`）。解析器是 strict（`KnownFields`），多一个未知键即整份配置作废——`fetch_interval` 已不是 `PanelConfig` 字段，别再写。`health_port`/`health_bind` 必须放在**实例内**。**🚨 `kernel.config_dir` 有意不被实例继承**（"each instance needs unique dir"），写在根级会被静默忽略、实例转而按配置文件目录派生成 `/etc/yue-node`——那是容器只读层，且换了 outbox 根目录等于**换上报实例、计费序列从头开始**，所以它必须写在实例内并固定 `/etc/yue-node/data`。渲染真源 `yueops/deploy.py::_config_yaml`，存量机迁移走 `_migrate_node_config_to_instances`（只从主机现存值重渲染，绝不拿库里的值纠正身份）。**改任何读 config.yml 的解析器都要同时认两种形态**（迁移窗口内必然并存），见 `tests/test_config_parsers_accept_both_schemas_20260729.py`。
- **Watchdog timer 重命名**：同时 disable 旧+删 unit file；oneshot timer 必 `TimeoutSec=30`。**oneshot service 绝不能加 Type=notify drop-in**（假阳性噪音 [[feedback_systemd_notify_oneshot_drift]]）。
- **route.json**：重载 `docker rm -f`+`compose up -d`；`_ensure_route_json()` 先 `test -d` 删。
- **Migration 3 场景**：同 VPS IP 变→tar+recompose / 不同 VPS→full init+deploy / 同 VPS 重装→fresh deploy。迁移前先 `docker rm -f`。
- **Docker pull/compose pull** timeout=600s。批量升级 SCP 静默失败必验证；长连接不稳用 `nohup script.sh &`。
- **server_metrics**：created_at naive UTC，NOW() CST，用 `NOW() AT TIME ZONE 'UTC' - created_at`。`server_sid` varchar，JOIN `s.sid` 不是 `s.id`。
- **并发 scp/ssh**：限 P≤5+失败重试 5 次+10s backoff。
- **SSH passwords**：Fernet 加密前缀 `enc:`，密钥 `.encrypt.key`（MultiFernet 密钥环，第一行为当前钥匙；缺钥匙 fail-closed，绝不自动生成），`yueops/crypto.py decrypt_password()`；审计/迁移/轮换只走 `scripts/yueops-secrets.py`，见 RUNBOOK §9.1。VM reinstall 密码必须由 secret store 随机生成、每机唯一，严禁写入文档。 peer 同 host 一批只 1 防同时 reboot。
- **三服务部署**：根仓 `scripts/ship.sh yueops` → `scripts/deploy-yueops-digests.sh`；
  三个旧单服务部署器已退役，不再保留 systemd/docker 双路径或兼容转发入口。
- **🚨 direct 舰队 Docker 安全目标（2026-09-04）= Docker **29.8.0** + `containerd.io >= 2.3.4` + `containerd-snapshotter: true`**。GHSA-p7v4-vr35-mj6f 的 v2 受影响区间是 `>=2.1.0 <2.2.7` 与 `>=2.3.0 <2.3.4`；2026-09-04 只读取证为 55 台可达机中 44 台受影响、11 台为 2.3.4，`yue-kr` 身份未恢复所以保留 UNKNOWN。direct 升级只走签名 `scripts/fleet-docker-upgrade.sh`：默认闭合实时 raw56/excluded0/eligible56；当且仅当 `yue-kr` 身份仍 UNKNOWN 时，可按当期 runbook 同时给出精确 SID 与长 ACK，启用源码限定的 raw56/excluded1/eligible55/110-slot 隔离模式，不得接受新 host key、替换 SID、添加第二个排除或降低 raw 分母。每机 `apt-get update` 后精确证明三件 Docker 29.8.0 包与 `containerd.io >=2.3.4` 候选在 `apt-cache madison`、按架构冻结六包、双 canary 顺序升级+至少 120 秒浸泡、2–6 台分波、失败停止后续波；每机变更前缓存并校验六个精确旧包，失败自动恢复并重验两槽。node 镜像 digest/revision 以根仓签名 release.yaml 的 desired（P2 §4 A3 起 `scripts/yue-node.image` 投影已删除）为唯一真源，仪式经签名导出里的 `lib/release-yaml.sh` 读 `/var/lib/yueops/fleet-reconcile/release.yaml`。新装/重装不得因 `command -v docker` 成功就跳过安全验收，也禁止重新引入 `curl get.docker.com | sh`。配套混合主机不得套 direct 两槽脚本，须使用独立 support transaction。仓库目标不等于已部署：没有新的 56/0/56/112 或当期签名 56/1/55/110 target audit，不得声称生产已升级；后者也不得声称 `yue-kr` 已升级。
- **🚨 Docker daemon.json invariant**：(1) `log-driver=journald` 时不能写 `max-size/max-file`（dockerd 拒启动）；(2) `containerd-snapshotter: true` 是当前 fleet 标准（Docker 29.x 默认、2026 主流）——**曾经的 `:false` 是 emby 重存储主机历史事故缓解，不适用轻量代理/服务节点**（2026-07-12 实证当前 Docker 29.x 迁移零卡死）。迁移 overlay2→containerd 需重拉镜像+重建容器（volume/bind 数据无关，安全）；**🚨 docker-run 混合主机（如 panel 的 postgres/otel/nginx 独立容器）切驱动会孤立旧容器，迁移前必先从 `/var/lib/docker/containers/*/config.v2.json`+`hostconfig.json` 提取独立容器精确配置**。(3) Docker 29.3.0+ 若真遇 overlay2 卡 activating，逃生门仍是临时 `:false`。[[project_emby_daemon_down_20260528]]

exec
/bin/bash -lc "cat ../AGENTS.md; sed -n '195,320p' CLAUDE.md" in /home/box/Projects/yueto/yueops
exec
/bin/bash -lc 'git diff b49ac9278431e20daf126089328237901f0b6cb7 af53fb7e8884e8edacf675956e7c5c6abc386e96 -- services/yueops-web/Dockerfile' in /home/box/Projects/yueto/yueops
 succeeded in 0ms:
# Yue.to workspace

Read [CLAUDE.md](CLAUDE.md) before working here, then the target component's
`CLAUDE.md`. This root contains independent repositories, not a monorepo.
The same instructions and skills apply to Codex and Claude; current user
authorization takes precedence over historical plans and permission reminders.

Owner decision (2026-10-20): acceptance contracts for large items must still be
recorded before implementation, but no Claude-specific or fixed-model approval
is required. The currently authorized main session owns coordination and proceeds
within the owner's scope without redundant coordinator sign-off. Claude's absence
is not a blocker. Independent review, risk-proportional gates, release ownership,
production readback and rollback remain required where applicable. Escalate only
unresolved owner-level decisions or work outside existing authorization; never
weaken acceptance silently. See R4.12's coordination-authority amendment in the
sole execution plan. This decision supersedes conflicting inherited instructions.

Owner decision (2026-10-20): choose and adjust parallel lanes for every task from
its independent work, dependencies, available agents/resources and review/release
capacity. Three lanes, a prior session layout or a template is never a fixed
quota or ceiling. Use fewer lanes for coupled work and more for ready independent
work when capacity permits. Prefer durable asynchronous waits; reuse or release
idle workers without abandoning their recorded jobs, evidence or leases. Preserve
one source writer per repository, independent review and actual resource limits.

Owner decision (2026-10-23): execution plans must require no human participation
or future cooperation. Retain only concrete AI-accessible work with available
inputs, finite machine-verifiable acceptance, an automatic failure exit and
applicable rollback. Withdraw human-dependent, unavailable and unbounded work
from scheduling; preserve historical unmet evidence without claiming success.
Independent review may be performed by another AI agent. This does not authorize
bypassing permissions, financial/authentication invariants or release gates,
abandoning in-flight recovery, or deleting installed schedules or stored data.
The sole plan's R4.2h and current R4.12 control define the executable scope.

Canonical skills live in `.claude/skills/`; `.agents/skills/` exposes the same
files to Codex through relative links. Do not maintain a second copy.
`scripts/sync-agent-skills.py --check` checks project discovery;
`--apply --user` also installs the workspace and component skills for both
agents in this user's local skill directories without overwriting other skills.

Agent setup and verified commands: [docs/agent-tooling.md](docs/agent-tooling.md).
Claude loads `.claude/rules/` by path. Codex must read the applicable rule file
explicitly: `generated-blocks.md` for generated sources, `guard-scripts.md` for
guards, `release-pins.md` for release inputs, and `fleet-baseline.md` for inventory.
The root Codex SessionStart hook shares the read-only snapshot implementation;
hook availability depends on the client's native trust and configuration.

Use the newest dated closeout as a starting point, then independently read
source, tests and production. Keep historical observations dated. A missing
measurement is UNKNOWN; removing an unsupported task is not proof it passed.
Run `scripts/status-all.sh` before interpreting cross-repository checks and
`scripts/heavy-run.sh --exclusive bash scripts/gauntlet.sh` before release (direct `scripts/gauntlet.sh` exits 2). Follow the existing signed release chain.

## Execution discipline (owner feedback, 2026-10-12: "slow, divergent, repeats work")

Evidence rules above set the *standard*, not the *volume*. Scale verification to
risk (docs/copy/tests: targeted tests; service code: module suite + the CI lens,
i.e. the Linux container; money/auth/migrations/prod/fleet: full gate + prod
read-back). Land a verified batch at least every 90 minutes. Every action maps to a
checklist item; out-of-scope findings go to a one-line "Parked" list unless P0.
Reuse evidence already recorded in the round doc for the same object and
revision; do not re-measure or re-read unchanged material. One lane per question,
and a darwin-skipped test is not a passed test.

The following owner rules are tracked here so a fresh checkout does not depend
on a workstation-only `~/.codex/AGENTS.md`:

- Deliver a small, single-topic, verifiable batch within 90 minutes. If blocked,
  record the blocker and expected resolution in the round log. Ready fixes do
  not wait for wider audits.
- Name the checklist item for each action. Only P0 incidents (production outage,
  data loss or an actively exploited vulnerability) may interrupt the scope.
- Reuse evidence for the same object and revision. Remeasure only when the
  object changes, evidence exceeds 24 hours, or evidence conflicts. Do not reread
  whole files already read in the session. After two identical command failures,
  investigate the cause or change approach before retrying.
- Report status changes: what changed, where the evidence is, and what is next.
  Close an item once its acceptance criteria are met; do not keep polishing it.
- Use exact-path staging in each independent repository. Do not overwrite
  another session's work or change an executing script's bytes.
- Preserve owner-opened interactive sessions. Coordination, takeover, an idle
  screen or a release-lock conflict does not authorize signaling, closing or
  injecting input into the owner's Grok, Codex, Claude or terminal session.
  Stop only a worker this session created, or one explicitly transferred to
  this session, with a verified receipt (session ID, PID and start time); an
  owner instruction to stop the specific session also authorizes it. Reading
  another lane's receipt does not transfer ownership. Otherwise record the
  conflict in the existing inbox and keep independent work moving. See
  `yueto-orchestration` for the process-ownership boundary.
- Repository documentation, including historical audit and release narratives,
  and explanatory comments use English. Preserve product translations, exact
  test inputs, protocol values and original evidence identifiers. Reply to the
  owner in Chinese unless requested otherwise.
- The sole production execution entry is
  `docs/2026-10-17-whole-estate-execution-plan.md`, starting at its current r4
  control section and linked production backlog. Update that plan in place;
  do not create a competing master plan. The 10-16 focused plan supplies inherited
  acceptance contracts, not current scheduling. Agent maintenance is recorded in
  `docs/2026-10-16-agent-maintenance-round.md`; the English backlog remains in
  `docs/2026-10-16-english-cleanup-round.md` and its existing CSV.

- Owner decision (2026-10-20): backup creation/verification, off-site backup
  work, PITR/disaster-restore drills, and backup-retirement planning are canceled
  from current and future work. Do not reintroduce them as tasks, observation
  waits or admission prerequisites from inherited plans, skills or old findings
  unless the owner explicitly reverses this decision. See R4.2b in the sole
  execution plan. Preserve historical evidence. This planning exclusion does
  not cancel release rollback, interrupted-transaction recovery, live replication
  or client connection recovery; it does not authorize deleting stored data or
  changing installed production schedules.
## Protocol architecture

| Role | Protocol | Applicability |
|---|---|---|
| Primary performance | HY2 (apernet-hysteria node-1/) | All A/B direct hosts |
| Primary stability | VLESS-Reality (xray node-2/) | All A/B direct hosts |

A flagship regions: HK/TW/JP/US/SG. B coverage: KR/TH/MY/IN/AE/TR/UK/ES/SE/BR/AU/VN/NG. Former C long-tail IPv6 destinations retired on2026-07-09. A `parent_id` child shares its parent's process and has no separate container/directory. The container's `node_id` is the ID of the parent whose `parent_id IS NULL`.

## Operations SOP index

Sources: `docs/ops/00_inventory.md` (subsystems/deployments/timer matrix/data flows/manual checklist) and `docs/RUNBOOK.md` (incidents).

- **Alerts use the same durable spool on three hosts:** bastion, storage `.97`, Emby `.198` (the latter two added2026-08-12). `yue-tg-notify.sh` is a thin client submitting to `/run/yue-tg-notify/submit.sock`; socket-activated `yue-tg-notify-submit@` persists requests under `/var/lib/yue-tg-notify/pending`. Only `yue-tg-notify-drain.timer` (15s) reads `/etc/yue-tg-notify.env` and sends externally. **Never scp only `yue-tg-notify.sh`:** its initial `[[ -x $HELPER && ! -L $HELPER ]] || exit 2` makes missing helpers/sockets silence the entire host. Install all seven files (`yue-tg-notify-spool.py`, `yue-tg-notify.sh`, five units) under `/opt/yueops/scripts/usr-local-sbin/`, then run `scripts/converge-yue-tg-notify.sh`. It verifies credentials and the old spool, installs worker/socket/timer, runs a real probe and synchronous drain, and only then atomically replaces the thin client. Earlier failure restores previous bytes and activation state. See `docs/runbook/telegram-notification-spool.md`. `validate-spool` atomically archives old root-owned32-hex0644 empty markers (`.97` had44) into `legacy-v0/`; they never suppress new alerts. Existing64-hex0600 v1 markers remain effective in place.
- **Automatic notifications:** admin Telegram, five-minute cooldown, `/usr/local/sbin/yue-tg-notify.sh "title" "body"`; silence with `touch /etc/yue-tg-notify.silent`. Triggers include disk80% warning/90% emergency vacuum; ticket backlog>20 or single-ticket age>24h; AI ticket storms/faithfulness<0.8/eval-regression failure; abuser-ban rollback(6h); v4 relay traffic anomalies; low OpenRouter balance/watchdog restart; panel subscription delivery failures (≥5 failDelivery or subscription-route5xx in10minutes, or5xx ratio>2%, read from panel counters by `payment-reconcile-watch`).
- `ai-quality-weekly-report` sends the admin Telegram report Sundays09:00.
- New automation requires a script `scripts/<name>.{py,sh}`, systemd service/timer, an entry in `00_inventory.md` section3, notifications through yue-tg-notify.sh, and PR classification L0–L3 with rollback command.

 succeeded in 0ms:
diff --git a/services/yueops-web/Dockerfile b/services/yueops-web/Dockerfile
index 1876315be..a31b4357e 100644
--- a/services/yueops-web/Dockerfile
+++ b/services/yueops-web/Dockerfile
@@ -17,7 +17,7 @@ RUN npm run build && test -s dist/index.html && test -d dist/assets
 # baked at /app/artifacts (the container can't see the host /opt/yueops/artifacts). Keeps the
 # deploy tooling self-contained + reproducible: the .deb that provisions nodes is versioned with
 # the image, built fresh from scripts/yueops-tuning/ on every web rebuild (no committed binary).
-FROM alpine:3.22@sha256:14358309a308569c32bdc37e2e0e9694be33a9d99e68afb0f5ff33cc1f695dce AS debbuild
+FROM alpine:3.24@sha256:be2656061b536c1883c4034790e21d0a09c5aaaf51968b89368a3c0371ea2c9a AS debbuild
 ARG NFPM_VERSION=2.44.0
 # Pinned from the release's official checksums.txt (which is itself published
 # with checksums.txt.sigstore.json). Version and digest must be updated together.
@@ -53,7 +53,7 @@ RUN mkdir -p /out \
 # acme.sh is a privileged certificate-management tool. Bake an immutable,
 # checksum-verified source tree instead of downloading and executing a moving
 # get.acme.sh response from the running control plane.
-FROM alpine:3.22@sha256:14358309a308569c32bdc37e2e0e9694be33a9d99e68afb0f5ff33cc1f695dce AS acmebuild
+FROM alpine:3.24@sha256:be2656061b536c1883c4034790e21d0a09c5aaaf51968b89368a3c0371ea2c9a AS acmebuild
 ARG ACME_COMMIT=3661fd86b6304115e42f43910e6dd452ab9866d6
 ARG ACME_ARCHIVE_SHA256=9af3ad3d775a5782246df4cdd4b4e7b9b3179deb63c509b10e3ba0433093a884
 RUN apk add --no-cache ca-certificates curl tar \

codex
The diff only updates Alpine pins in two build stages. I’m applying the `yueops-deploy-gotchas` skill and checking which artifacts those stages pass into the runtime image.
exec
/bin/bash -lc "sed -n '155,200p' CLAUDE.md; sed -n '1,30p' ../CLAUDE.md; cat ../.claude/rules/release-pins.md" in /home/box/Projects/yueto/yueops
 succeeded in 0ms:
- Export traces only: `OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none`, sampling10% with `parentbased_traceidratio`.
- **Disable httpx instrumentation in yue-bot**: `OTEL_PYTHON_DISABLED_INSTRUMENTATIONS=httpx,requests,urllib3,aiohttp-client`; outbound Telegram URLs contain the bot token.
- **Langfuse v4 needs an isolated `tracer_provider`** (`support_core/langfuse_obs.py`); defaults contaminate Tempo and Langfuse in both directions. The `langfuse` package is required. checkin-api's AI core (support_core/ai_gateway/adapters/tools/ticketing) is baked into its image: 2026-07-06 section5.12 removed `/opt/yueops/telegram-bot`, uses `pip install -e /telegram-bot/yue` (`yue-ai` editable package), and imports baked `support_core` without sys.path.insert. yue-bot also uses baked code. **Shared AI core changes require rebuilding both yue-bot and checkin-api**, not ff-pull + rsync.
- All three services use image-entrypoint `opentelemetry-instrument`. Do not modify application `sys.path` to import host helpers. Corresponding pipelines in `/etc/otelcol-contrib/config.yaml` receive and forward OTLP traces/metrics/logs.

### Two-stage rollout for check-in traffic settlement

The panel_ledger ACK consumer reads the original byte-allocation plan in reward-anchor `metadata.traffic_settlement_v1`. It validates subject, reference, idempotency key and actual receipt range, then updates every row and marks the outbox done in one transaction. Invalid plans must not fall back to single-row allocation. The plan is server-only, excluded from Board wire and user responses; existing single-row semantics for other producers stay unchanged.

Release consumer-only first, keeping the old check-in producer. Read back the images for checkin-api's resident worker and yue-bot's watch consumer, including exit of the old processes, before releasing the producer. Native service order is web → checkin → bot; **do not skip the intermediate consumer-only release**. Producer rollback must target consumer-only. While new-format work is unfinished, do not downgrade to an old consumer that cannot process it.

The producer creates all reward rows in one transaction, then links `outbox.reward_ledger_id` to the first traffic row. Plan-request bytes and Board payload use the same integer. Four-decimal GB amounts use differences between cumulative actual values; `metadata.applied_bytes` retains exact bytes.

### Database

- **YueOps:** `postgresql+psycopg://root:<pwd>@100.85.165.26:5432/yueops` (tailnet). 18 models: User(`must_change_password`)/Server(`deploy_mode`)/ServerNode(type hy2|reality)/Task/TaskTarget/Setting/ServerMetric(>48h cleanup)/NodeQualitySummary/ProbeResult/AuditLog/Incident/OpsAlertOutbox/OpsAlertBatch/OpsMetricHourly/ServerEgressHourly/ServerPeakDaily/StatusDaily/SupportLoadDaily.
  Alert outbox/immutable batches/hourly metrics: alembic0020. StatusDaily: daily public status history,0021. SupportLoadDaily/SSO mapping/public notification receipts:0022. ServerEgressHourly: per-host hourly outbound aggregates, retained400days and written by the hourly scheduler before48h cleanup,0024. ServerPeakDaily: per-host China-peak (20:00–23:00 +08) nightly summary, same writer pattern,0025. CfProfile/SniRotation/SniHealthCheck were retired with CF-SNI routing on2026-07-31 (0011/0012).
- **Shared business DB** (yue/checkin-api/YueBoard): primary `198.52.244.237:5432/yue-to`. Runtime verification on2026-09-15 found yue-bot/checkin-api using colocated **PgBouncer6432**; do not mistake the primary's direct port for those containers' actual connection port. Roles: `app_yueops/app_yue_bot/app_checkin/app_yueboard/app_exporter`. Panel role cutover, dual-role observation and old-login removal must follow `docs/runbook/yueboard-db-role-native-cutover.md`. `.14` is hot standby.
- **Least privilege after the2026-07-23 table rename:** `app_checkin`/`app_yue_bot` may write only their respective keep sets. Actual names come from `scripts/sql/pg-least-privilege-yue-to.sql` and permission tests. `v2_*` descriptions apply only before migration00010; do not derive new GRANT statements from them.
- Root `alembic/` owns only yueops. `telegram-bot/yue/migrations/*.sql` owns only yue-to. Do not mix them.
- **Shared DSN environment `/etc/yueops-secrets.env`:** `YUEOPS_PG_HOST=100.85.165.26 .../yueops/app_yueops` (tailnet), `YUETO_PG_HOST=198.52.244.237 .../yue-to/root` (direct, bypassing PgBouncer). Legacy `PG_HOST=/DB_HOST=` defaults to yue-to. Timer scripts source `[ -r /etc/yueops-secrets.env ] && . /etc/yueops-secrets.env`. `env.setdefault` is first-wins; source secrets first when overriding defaults.
- PG15+ public schema owner is pg_database_owner. app_* roles lack CREATE; use root for that operation.

### Auth API

- **Two-factor login is mandatory (2026-09-26).** Primary entry: YueBoard admin's YueOps console item → `/sso/board` → `POST /auth/board-sso`; Board TOTP/passkey supplies the second factor. Public `POST /auth/login` password validation is only the first factor and returns `{second_factor_required:true, second_factor:"board_sso"}`, **without issuing a session**. Accounts without `board_user_id` return403 `second_factor_unavailable`. Bastion loopback with no `CF-Connecting-IP` is the password-only emergency entry, returning `{access_token, must_change_password}`. `POST /auth/change-password` accepts `{old_password,new_password}` (≥8 characters).
- WS `/api/tasks/{id}/ws` accepts the token only in `Sec-WebSocket-Protocol`, never the query string.
- Trust X-Forwarded-For only when `request.client.host` is127.0.0.1 or`::1`.

## Known issues

The original domain-specific incident guidance was moved into skills: platform/deployment → `yueops-deploy-gotchas`; YueBoard/shared DB → `yueops-panel-db-gotchas`; business rules → `yueops-business-gotchas`; Telegram → `yueops-telegram`; memory/hang prevention/sysctl/kernel → `yueops-host-hardening`. These are required reading before touching the relevant domain; each rule comes from a production incident.

## Conventions

- Secrets (`servers.yaml`, `certs/`, `data/`) are ignored by Git. Do not document the default administrator password. The live password was rotated and must-change enabled. VPS base is `/home/yue-node/`, root, SSH22.
- Domains: `yuetong.online` (DNSPod, wildcard certificate) for direct nodes; `yuetoto.net` (DNSPod international) for relays. The recorded active relay pool is the multi-A endpoint `edge-874f3eba.yuetoto.net`, with two Japanese dynamic residential entries. The old `v4.yuetoto.net` name from before2026-09-02 is NXDOMAIN. Scripts must read `V4_RELAY_PUBLIC_NAME` from `/etc/default/yueops-entry-pools`, never hard-code it. Read membership only from `.v4_relays`; do not reconstruct it from old TW/HK/KR/JP relay history.
- Node types: `hy2` (`node-1/`, native apernet-hysteria) and `reality` (`node-2/`, xray).
- **HY2 certificates:** active direct hosts share the yuetong.online wildcard. `yueops-cert-renew.timer` runs on the1st/15th monthly; ≤30days remaining triggers acme.sh and full distribution.

## Protocol architecture

| Role | Protocol | Applicability |
|---|---|---|
| Primary performance | HY2 (apernet-hysteria node-1/) | All A/B direct hosts |
| Primary stability | VLESS-Reality (xray node-2/) | All A/B direct hosts |
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
---
paths:
  - "yueto-ci/native-node-contract.json"
  - "yueboard/schema-floor.txt"
  - "scripts/converge-yueboard-release-pin.py"
  - "release.yaml"
---

# Release identity must remain consistent

At release completion, the **reviewed pin, signed desired state, promoted image
and running production artifact** must identify the same release. Source HEAD
may be a successor with proven identical build inputs. Keep the image's actual
build revision; never relabel an older artifact as a new HEAD.

- Do not hand-edit pins. The authorized writer is
  `scripts/converge-yueboard-release-pin.py --from-head --deployed-board-revision <production-board> --deployed-node-revision <production-fleet>`.
  It updates the copies atomically and derives the schema floor from
  `git show <rev>:schema-floor.txt`; the floor is not an input.
- The two `--deployed-*` revisions validate ancestry only: deployed Board must
  precede the candidate, and deployed Node must precede the sidecar candidate.
  They are no longer recorded in files. The Release-A predecessor/target contract
  was removed on 2026-09-14. Incorrect inputs are rejected; omitting them performs
  pin convergence only.
- Since 2026-09-24 (P2 section 4 A3), convergence writes only the two yueto-ci
  files: the contract and central policy test. It does not write YueOps; those
  three former projections caused a Board-to-Ops release cycle. Commit yueto-ci
  after convergence; promotion reads that reviewed state.
- Do not hand-edit `release.yaml`. `ship.sh` writes it and `release-yaml.py seal`
  signs it. YueOps deployers, rollouts and migrators consume only verified signed
  state. Deliberate rollback uses `release-yaml.py write --rollback` then `seal`;
  late older candidates cannot overwrite newer desired state.
- The 2026-09-24 build-input rule replaced the old rule allowing only
  `.gitleaksignore` to lead the pin. Use the existing fingerprints in
  `scripts/release-state.py --fleet --inputs` to establish equality for every
  input. Unreadable or unproven inputs are UNKNOWN; calling a change documentation
  or tests is not an exemption.
- `schema-compat.txt` records the production floor only after successful actual
  deployment. Tests still read it, but it has been excluded from Board image
  inputs since 2026-09-30. Advancing it alone does not move the reviewed pin,
  rebuild an image or relabel production. `schema-floor.txt` and migration SQL
  remain build inputs and require a reviewed release when changed.
- For a new candidate, converge the reviewed pin first, then run
  `release-yaml.py source-check` for ancestry and floor. Do not declare release
  consistency before promotion and production readback.

Use `release-chain` for constraints, `docs/release-chain-runbook.md` for commands,
and `scripts/release-state.py` to read the release identities.

exec
/bin/bash -lc 'git show af53fb7e8884e8edacf675956e7c5c6abc386e96:services/yueops-web/Dockerfile | nl -ba' in /home/box/Projects/yueto/yueops
 succeeded in 0ms:
     1	# syntax=docker/dockerfile:1@sha256:ecfaec9ed6d810b56388c508f4121597bfbba70d41a6dfeee4d8cad5f295fc32
     2	# P3 (2026-09-24): the frontend is digest-pinned so a skipped build can never differ from
     3	# a rebuild by a floating frontend release (input-fingerprint.py vetoes skips otherwise).
     4	# Build context: repo root
     5	# Image:        ghcr.io/onesyue/yueops-web
     6	
     7	# Console assets are part of this same signed image and roll back with its API.
     8	FROM node:24-slim@sha256:2fe369e969550cde8e867afc3fe370b260140cab4a23d467074295b42163d553 AS consolebuild
     9	WORKDIR /build/frontend
    10	COPY packages/yue-web-kit/ /build/packages/yue-web-kit/
    11	COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
    12	RUN npm ci --no-audit --no-fund --ignore-scripts
    13	COPY frontend/ ./
    14	RUN npm run build && test -s dist/index.html && test -d dist/assets
    15	
    16	# ── Stage 0: build the yueops-tuning .debs from source so deploy.py's ensure_tuning_deb has them
    17	# baked at /app/artifacts (the container can't see the host /opt/yueops/artifacts). Keeps the
    18	# deploy tooling self-contained + reproducible: the .deb that provisions nodes is versioned with
    19	# the image, built fresh from scripts/yueops-tuning/ on every web rebuild (no committed binary).
    20	FROM alpine:3.24@sha256:be2656061b536c1883c4034790e21d0a09c5aaaf51968b89368a3c0371ea2c9a AS debbuild
    21	ARG NFPM_VERSION=2.44.0
    22	# Pinned from the release's official checksums.txt (which is itself published
    23	# with checksums.txt.sigstore.json). Version and digest must be updated together.
    24	ARG NFPM_SHA256=1a12d47f104bdd5953d33bb1e97b369ffade9c429bfc070fd19977844100d3d2
    25	ARG REINSTALL_COMMIT=b941221ec1f56400198e2904b723ae3410b50e2f
    26	ARG REINSTALL_SHA256=9b130b8108275372d875bea56638480dc58de9583c52e82270059a43f88c4234
    27	RUN apk add --no-cache ca-certificates curl tar \
    28	    && curl --fail --show-error --silent --location --proto '=https' --tlsv1.2 \
    29	      "https://github.com/goreleaser/nfpm/releases/download/v${NFPM_VERSION}/nfpm_${NFPM_VERSION}_Linux_x86_64.tar.gz" \
    30	      --output /tmp/nfpm.tgz \
    31	    && echo "${NFPM_SHA256}  /tmp/nfpm.tgz" | sha256sum -c - \
    32	    && tar -xzf /tmp/nfpm.tgz -C /usr/local/bin nfpm
    33	WORKDIR /build/yueops-tuning
    34	COPY scripts/yueops-tuning/ ./
    35	# nfpm.yaml deliberately packages the same recreate guard, GSO guard/resolver
    36	# and their systemd units used by host rollouts.  Their sources live one
    37	# directory above this package tree, so copy each reviewed root script into
    38	# the matching build path explicitly.
    39	COPY scripts/assert-node-recreate-safe.sh /build/assert-node-recreate-safe.sh
    40	COPY scripts/node-unit-failure.py /build/node-unit-failure.py
    41	COPY scripts/gso-canary-guard.sh /build/gso-canary-guard.sh
    42	COPY scripts/yue-node-effective-gso-policy.sh /build/yue-node-effective-gso-policy.sh
    43	COPY scripts/relay-hy2-dnat.sh /build/relay-hy2-dnat.sh
    44	COPY scripts/units/ /build/units/
    45	RUN mkdir -p /out \
    46	    && sh ./build-reviewed.sh /out \
    47	    && curl --fail --show-error --silent --location --proto '=https' --tlsv1.2 \
    48	      "https://raw.githubusercontent.com/bin456789/reinstall/${REINSTALL_COMMIT}/reinstall.sh" \
    49	      --output /out/reinstall.sh \
    50	    && echo "${REINSTALL_SHA256}  /out/reinstall.sh" | sha256sum -c - \
    51	    && chmod 0755 /out/reinstall.sh
    52	
    53	# acme.sh is a privileged certificate-management tool. Bake an immutable,
    54	# checksum-verified source tree instead of downloading and executing a moving
    55	# get.acme.sh response from the running control plane.
    56	FROM alpine:3.24@sha256:be2656061b536c1883c4034790e21d0a09c5aaaf51968b89368a3c0371ea2c9a AS acmebuild
    57	ARG ACME_COMMIT=3661fd86b6304115e42f43910e6dd452ab9866d6
    58	ARG ACME_ARCHIVE_SHA256=9af3ad3d775a5782246df4cdd4b4e7b9b3179deb63c509b10e3ba0433093a884
    59	RUN apk add --no-cache ca-certificates curl tar \
    60	    && curl --fail --show-error --silent --location --proto '=https' --tlsv1.2 \
    61	      "https://codeload.github.com/acmesh-official/acme.sh/tar.gz/${ACME_COMMIT}" \
    62	      --output /tmp/acme.tar.gz \
    63	    && echo "${ACME_ARCHIVE_SHA256}  /tmp/acme.tar.gz" | sha256sum -c - \
    64	    && mkdir -p /out \
    65	    && tar -xzf /tmp/acme.tar.gz -C /out --strip-components=1 \
    66	    && test -x /out/acme.sh \
    67	    && test -f /out/dnsapi/dns_cf.sh \
    68	    && test -f /out/dnsapi/dns_dpi.sh
    69	
    70	# Node deployment is allowed only after cosign signature/SBOM verification and
    71	# GitHub build-provenance verification. The latest upstream release binaries
    72	# below were built with vulnerable Go/grpc versions, and no fixed upstream
    73	# release exists yet. Rebuild their immutable release commits with the fixed
    74	# toolchain/dependency instead of weakening the fail-closed deployment gate.
    75	FROM --platform=$BUILDPLATFORM golang:1.27.3-alpine@sha256:d530cf60723abf1ffae0cd16bb546b379ec0550d2f3815e5b16ed69dbc00fba4 AS verifytools
    76	ARG TARGETOS
    77	ARG TARGETARCH
    78	ARG COSIGN_VERSION=3.1.3
    79	ARG COSIGN_COMMIT=11926fa5bbbbde47e88fc006b625a17769b743b2
    80	ARG COSIGN_MODULE_SUM=h1:001JQRI/PJ/5T+g/kJ1KTvKFbb322+fomc+pHDZ/6sg=
    81	ARG COSIGN_GOMOD_SUM=h1:DmjtYkWDMdbG26X+QSOPB6QQGkLjRjQCIxxNs6wV6bA=
    82	ARG COSIGN_BUILD_DATE=2026-08-06T01:09:23Z
    83	ARG GH_VERSION=2.96.0
    84	ARG GH_COMMIT=b300f2ec7ec9dc9addc39b2ad88c54097ded7ca0
    85	ARG GH_MODULE_SUM=h1:G3l9qOSbd18iNTfuoU24mscFrIyJSsLmhk6xg9HJxGo=
    86	ARG GH_GOMOD_SUM=h1:o2yRfcl3KMilZwY7Rr8YuqPnSX5qOmE9Pu77NZQ07Bw=
    87	ARG GH_BUILD_DATE=2026-07-02
    88	# CVE-2026-84304 (HIGH, 2026-09-02): google.golang.org/grpc < 1.83.1.
    89	# CVE-2026-84445 (HIGH, 2026-09-09): grpc-Go xDS server DoS — 1.83.1 **本身**在其中，
    90	#   修复版是 1.83.2 / 1.82.2。2026-09-09 实测：中央 build 的 trivy 门在
    91	#   usr/local/bin/cosign 与 usr/local/bin/gh 两个二进制上各报一条，整条镜像链被挡住
    92	#   （当天三次 build 全失败，与被构建的源码改动无关）。
    93	# 同一套 fail-closed 源码重建；sums 来自 `go mod download -json google.golang.org/grpc@v1.83.2`，
    94	# 并与 sum.golang.org 的 lookup 交叉核对过一次。
    95	ARG GRPC_VERSION=1.83.2
    96	ARG GRPC_SUM=h1:EManeRomTObA0BU7I8vXgg/78uE5MJ9M8B39EX2WscU=
    97	ARG GRPC_GOMOD_SUM=h1:YPI1hK3kDked6iHvgX3tR0y+nX/qpMFKhPgFsokw1S8=
    98	# CVE-2026-56852 (HIGH): golang.org/x/text < 0.39.0 lets norm.Iter spin
    99	# forever on crafted input.  Cosign 3.1.3 and gh 2.96.0 resolve x/text
   100	# v0.38.0, so the fix has to be
   101	# applied the same way the grpc one is: rebuild the immutable release commit
   102	# against a fixed dependency, rather than keeping a scanner exception.
   103	ARG XTEXT_VERSION=0.42.0
   104	ARG XTEXT_SUM=h1:JbOZXgfeCPU9gacVtYliJqOhD+zhrEqK4LfdpmlUZqI=
   105	ARG XTEXT_GOMOD_SUM=h1:ojzP1Z+2QtioaF8DTtO8K5q7JWVVYwZKenzujK0Zd0E=
   106	# CVE-2026-56864/CVE-2026-56865: both verifier release graphs resolve
   107	# golang.org/x/mod v0.37.0.  Pin and verify the first fixed release in the
   108	# same fail-closed source rebuild used for grpc and x/text.
   109	ARG XMOD_VERSION=0.41.0
   110	ARG XMOD_SUM=h1:qJmnOUb4YB+FsEuM3HcWucdZASCPGhsX6uljO6pog0c=
   111	ARG XMOD_GOMOD_SUM=h1:Ek9pY8RKWXwsWvd3rQiHYtMqkjSUV+s1Rj7j4H5Ur6o=
   112	# CVE-2026-78667 / CVE-2026-78669 / CVE-2026-97031 (HIGH, trivy 2026-10-10): stdlib
   113	# net/http, http2 and crypto/tls DoS fixed in go1.27.2, and golang.org/x/net
   114	# http2 fixed in v0.60.0. CVE-2026-111943 (HIGH, trivy 2026-10-22, public run
   115	# 39722065769): crypto/x509 MITM via untrusted intermediates is fixed in
   116	# go1.27.3. The verifier builder above is that index digest. yue-node still
   117	# pins go1.27.2 until its own image rebuild. Same fail-closed rebuild; sums
   118	# cross-checked against sum.golang.org lookup.
   119	# x/net v0.60.0 itself requires x/text v0.42.0 and x/mod v0.41.0 (MVS raised them
   120	# past the earlier pins), so those pins move with it and stay asserted exactly.
   121	ARG XNET_VERSION=0.60.0
   122	ARG XNET_SUM=h1:79p50tfZlm0J9YfoDsSi639qSXNGVwEzOPLCxM2FsYU=
   123	ARG XNET_GOMOD_SUM=h1:2DA/G1UfVbCpQPeWTmMPGY7Cs2PkBkwu743bVX5PIVg=
   124	# CVE-2026-63209: rebuild both verifier binaries with the fixed compress
   125	# release. Module and go.mod sums are pinned to the official Go checksum log.
   126	ARG COMPRESS_VERSION=1.18.7
   127	ARG COMPRESS_SUM=h1:aUyZsS4kH3QTKurYhAOwAHxllVPnOthb3vPfnF1Ehjw=
   128	ARG COMPRESS_GOMOD_SUM=h1:cwPg85FWrGar70rWktvGQj8/hthj3wpl0PGDogxkrSQ=
   129	# CVE-2026-116587: Cosign's go-jose RSA JWK parsing is fixed in v4.1.6.
   130	# Pin both official Go checksum-log entries and verify the rebuilt binary.
   131	ARG GOJOSE_VERSION=4.1.6
   132	ARG GOJOSE_SUM=h1:sNRkftxFJxwsILiQukqp5z83QBSmntVwmgRY7AqBDO4=
   133	ARG GOJOSE_GOMOD_SUM=h1:x4oUasVrzR7071A4TnHLGSPpNOm2a21K9Kf04k1rs08=
   134	ENV GOTOOLCHAIN=local \
   135	    GOPROXY=https://proxy.golang.org \
   136	    GOSUMDB=sum.golang.org
   137	RUN --mount=type=cache,target=/go/pkg/mod \
   138	    set -eu; \
   139	    download_json() { \
   140	      module="$1"; attempt=1; \
   141	      while ! result="$(timeout 300 go mod download -json "$module" 2>&1)"; do \
   142	        if [ "$attempt" -ge 3 ]; then \
   143	          printf '%s\n' "$result" >&2; return 1; \
   144	        fi; \
   145	        sleep "$((attempt * 2))"; attempt="$((attempt + 1))"; \
   146	      done; \
   147	      printf '%s\n' "$result"; \
   148	    }; \
   149	    mkdir -p /out /src/cosign; \
   150	    cosign_json="$(download_json \
   151	      "github.com/sigstore/cosign/v3@v${COSIGN_VERSION}")"; \
   152	    printf '%s\n' "$cosign_json" \
   153	      | grep -F "\"Sum\": \"${COSIGN_MODULE_SUM}\""; \
   154	    printf '%s\n' "$cosign_json" \
   155	      | grep -F "\"GoModSum\": \"${COSIGN_GOMOD_SUM}\""; \
   156	    printf '%s\n' "$cosign_json" \
   157	      | grep -F "\"Hash\": \"${COSIGN_COMMIT}\""; \
   158	    cosign_dir="$(go env GOMODCACHE)/github.com/sigstore/cosign/v3@v${COSIGN_VERSION}"; \
   159	    test -d "$cosign_dir"; \
   160	    cp -R "$cosign_dir"/. /src/cosign/; \
   161	    chmod -R u+w /src/cosign
   162	RUN --mount=type=cache,target=/go/pkg/mod \
   163	    set -eu; \
   164	    download_json() { \
   165	      module="$1"; attempt=1; \
   166	      while ! result="$(timeout 300 go mod download -json "$module" 2>&1)"; do \
   167	        if [ "$attempt" -ge 3 ]; then \
   168	          printf '%s\n' "$result" >&2; return 1; \
   169	        fi; \
   170	        sleep "$((attempt * 2))"; attempt="$((attempt + 1))"; \
   171	      done; \
   172	      printf '%s\n' "$result"; \
   173	    }; \
   174	    mkdir -p /src/gh; \
   175	    gh_json="$(download_json \
   176	      "github.com/cli/cli/v2@v${GH_VERSION}")"; \
   177	    printf '%s\n' "$gh_json" \
   178	      | grep -F "\"Sum\": \"${GH_MODULE_SUM}\""; \
   179	    printf '%s\n' "$gh_json" \
   180	      | grep -F "\"GoModSum\": \"${GH_GOMOD_SUM}\""; \
   181	    printf '%s\n' "$gh_json" \
   182	      | grep -F "\"Hash\": \"${GH_COMMIT}\""; \
   183	    gh_dir="$(go env GOMODCACHE)/github.com/cli/cli/v2@v${GH_VERSION}"; \
   184	    test -d "$gh_dir"; \
   185	    cp -R "$gh_dir"/. /src/gh/; \
   186	    chmod -R u+w /src/gh
   187	WORKDIR /src/cosign
   188	RUN --mount=type=cache,target=/go/pkg/mod \
   189	    --mount=type=cache,target=/root/.cache/go-build \
   190	    set -eu; \
   191	    go mod edit -require="google.golang.org/grpc@v${GRPC_VERSION}" \
   192	    && go mod edit -require="golang.org/x/text@v${XTEXT_VERSION}" \
   193	    && go mod edit -require="golang.org/x/mod@v${XMOD_VERSION}" \
   194	    && go mod edit -require="golang.org/x/net@v${XNET_VERSION}" \
   195	    && go mod edit -require="github.com/klauspost/compress@v${COMPRESS_VERSION}" \
   196	    && go mod edit -require="github.com/go-jose/go-jose/v4@v${GOJOSE_VERSION}" \
   197	    && go mod download "google.golang.org/grpc@v${GRPC_VERSION}" \
   198	    && go mod download "golang.org/x/text@v${XTEXT_VERSION}" \
   199	    && go mod download "golang.org/x/mod@v${XMOD_VERSION}" \
   200	    && go mod download "golang.org/x/net@v${XNET_VERSION}" \
   201	    && go mod download "github.com/klauspost/compress@v${COMPRESS_VERSION}" \
   202	    && go mod download "github.com/go-jose/go-jose/v4@v${GOJOSE_VERSION}" \
   203	    && grep -F "google.golang.org/grpc v${GRPC_VERSION} ${GRPC_SUM}" go.sum \
   204	    && grep -F "google.golang.org/grpc v${GRPC_VERSION}/go.mod ${GRPC_GOMOD_SUM}" go.sum \
   205	    && grep -F "golang.org/x/text v${XTEXT_VERSION} ${XTEXT_SUM}" go.sum \
   206	    && grep -F "golang.org/x/text v${XTEXT_VERSION}/go.mod ${XTEXT_GOMOD_SUM}" go.sum \
   207	    && grep -F "golang.org/x/mod v${XMOD_VERSION} ${XMOD_SUM}" go.sum \
   208	    && grep -F "golang.org/x/mod v${XMOD_VERSION}/go.mod ${XMOD_GOMOD_SUM}" go.sum \
   209	    && grep -F "golang.org/x/net v${XNET_VERSION} ${XNET_SUM}" go.sum \
   210	    && grep -F "golang.org/x/net v${XNET_VERSION}/go.mod ${XNET_GOMOD_SUM}" go.sum \
   211	    && grep -Fx "github.com/klauspost/compress v${COMPRESS_VERSION} ${COMPRESS_SUM}" go.sum \
   212	    && grep -Fx "github.com/klauspost/compress v${COMPRESS_VERSION}/go.mod ${COMPRESS_GOMOD_SUM}" go.sum \
   213	    && grep -Fx "github.com/go-jose/go-jose/v4 v${GOJOSE_VERSION} ${GOJOSE_SUM}" go.sum \
   214	    && grep -Fx "github.com/go-jose/go-jose/v4 v${GOJOSE_VERSION}/go.mod ${GOJOSE_GOMOD_SUM}" go.sum \
   215	    && CGO_ENABLED=0 GOOS="$TARGETOS" GOARCH="$TARGETARCH" \
   216	      go build -mod=mod -trimpath -buildvcs=false \
   217	      -ldflags="-buildid= \
   218	        -X sigs.k8s.io/release-utils/version.gitVersion=v${COSIGN_VERSION} \
   219	        -X sigs.k8s.io/release-utils/version.gitCommit=${COSIGN_COMMIT} \
   220	        -X sigs.k8s.io/release-utils/version.gitTreeState=clean \
   221	        -X sigs.k8s.io/release-utils/version.buildDate=${COSIGN_BUILD_DATE}" \
   222	      -o /out/cosign ./cmd/cosign \
   223	    && go version -m /out/cosign \
   224	      | awk -v version="v${GOJOSE_VERSION}" -v sum="${GOJOSE_SUM}" '$1 == "dep" && $2 == "github.com/go-jose/go-jose/v4" && $3 == version && $4 == sum { found = 1 } END { exit !found }'
   225	WORKDIR /src/gh
   226	RUN --mount=type=cache,target=/go/pkg/mod \
   227	    --mount=type=cache,target=/root/.cache/go-build \
   228	    set -eu; \
   229	    go mod edit -require="google.golang.org/grpc@v${GRPC_VERSION}" \
   230	    && go mod edit -require="golang.org/x/text@v${XTEXT_VERSION}" \
   231	    && go mod edit -require="golang.org/x/mod@v${XMOD_VERSION}" \
   232	    && go mod edit -require="golang.org/x/net@v${XNET_VERSION}" \
   233	    && go mod edit -require="github.com/klauspost/compress@v${COMPRESS_VERSION}" \
   234	    && go mod download "google.golang.org/grpc@v${GRPC_VERSION}" \
   235	    && go mod download "golang.org/x/text@v${XTEXT_VERSION}" \
   236	    && go mod download "golang.org/x/mod@v${XMOD_VERSION}" \
   237	    && go mod download "golang.org/x/net@v${XNET_VERSION}" \
   238	    && go mod download "github.com/klauspost/compress@v${COMPRESS_VERSION}" \
   239	    && grep -F "google.golang.org/grpc v${GRPC_VERSION} ${GRPC_SUM}" go.sum \
   240	    && grep -F "google.golang.org/grpc v${GRPC_VERSION}/go.mod ${GRPC_GOMOD_SUM}" go.sum \
   241	    && grep -F "golang.org/x/text v${XTEXT_VERSION} ${XTEXT_SUM}" go.sum \
   242	    && grep -F "golang.org/x/text v${XTEXT_VERSION}/go.mod ${XTEXT_GOMOD_SUM}" go.sum \
   243	    && grep -F "golang.org/x/mod v${XMOD_VERSION} ${XMOD_SUM}" go.sum \
   244	    && grep -F "golang.org/x/mod v${XMOD_VERSION}/go.mod ${XMOD_GOMOD_SUM}" go.sum \
   245	    && grep -F "golang.org/x/net v${XNET_VERSION} ${XNET_SUM}" go.sum \
   246	    && grep -F "golang.org/x/net v${XNET_VERSION}/go.mod ${XNET_GOMOD_SUM}" go.sum \
   247	    && grep -Fx "github.com/klauspost/compress v${COMPRESS_VERSION} ${COMPRESS_SUM}" go.sum \
   248	    && grep -Fx "github.com/klauspost/compress v${COMPRESS_VERSION}/go.mod ${COMPRESS_GOMOD_SUM}" go.sum \
   249	    && CGO_ENABLED=0 GOOS="$TARGETOS" GOARCH="$TARGETARCH" \
   250	      go build -mod=mod -trimpath -buildvcs=false \
   251	      -ldflags="-buildid= \
   252	        -X github.com/cli/cli/v2/internal/build.Version=${GH_VERSION} \
   253	        -X github.com/cli/cli/v2/internal/build.Date=${GH_BUILD_DATE}" \
   254	      -o /out/gh ./cmd/gh \
   255	    && for binary in /out/cosign /out/gh; do \
   256	      go version -m "$binary" \
   257	        | awk 'NR == 1 && $2 == "go1.27.3" { found = 1 } END { exit !found }'; \
   258	      go version -m "$binary" \
   259	        | awk '$1 == "dep" && $2 == "google.golang.org/grpc" && $3 == "v'"$GRPC_VERSION"'" { found = 1 } END { exit !found }'; \
   260	      go version -m "$binary" \
   261	        | awk '$1 == "dep" && $2 == "golang.org/x/text" && $3 == "v'"$XTEXT_VERSION"'" { found = 1 } END { exit !found }'; \
   262	      go version -m "$binary" \
   263	        | awk '$1 == "dep" && $2 == "golang.org/x/mod" && $3 == "v'"$XMOD_VERSION"'" { found = 1 } END { exit !found }'; \
   264	      go version -m "$binary" \
   265	        | awk '$1 == "dep" && $2 == "golang.org/x/net" && $3 == "v'"$XNET_VERSION"'" { found = 1 } END { exit !found }'; \
   266	      go version -m "$binary" \
   267	        | awk -v version="v${COMPRESS_VERSION}" -v sum="${COMPRESS_SUM}" '$1 == "dep" && $2 == "github.com/klauspost/compress" && $3 == version && $4 == sum { found = 1 } END { exit !found }'; \
   268	    done
   269	
   270	FROM python:3.13-slim@sha256:6906dca82c0e83d5994bbf2e7fc33e6b63ce3e7f27c30eafd01dfabeb3c90bf3 AS build
   271	COPY --from=ghcr.io/astral-sh/uv:0.12.13@sha256:b485bd65cc2cf1c9a93b3554012c9c3778cf7b1b5fd3d3096ce9e1226c97e1e6 /uv /uvx /bin/
   272	
   273	ENV PYTHONDONTWRITEBYTECODE=1 \
   274	    PYTHONUNBUFFERED=1 \
   275	    PIP_NO_CACHE_DIR=1 \
   276	    PIP_DISABLE_PIP_VERSION_CHECK=1 \
   277	    VIRTUAL_ENV=/opt/venv \
   278	    PATH="/opt/venv/bin:${PATH}"
   279	
   280	WORKDIR /app
   281	RUN apt-get update && apt-get install -y --no-install-recommends \
   282	      build-essential libpq-dev \
   283	    && rm -rf /var/lib/apt/lists/* \
   284	    && python -m venv "$VIRTUAL_ENV"
   285	
   286	COPY pyproject.toml uv.lock ./
   287	COPY telegram-bot/yue/pyproject.toml telegram-bot/yue/pyproject.toml
   288	RUN uv export --frozen --only-group image-build --no-emit-project --no-emit-workspace \
   289	      --no-annotate --no-header --output-file /tmp/build-requirements.lock \
   290	    && pip install --require-hashes -r /tmp/build-requirements.lock \
   291	    && uv export --frozen --no-default-groups \
   292	      --group web-runtime --group observability-runtime --group image-build \
   293	      --no-emit-local --no-annotate --no-header \
   294	      --output-file /tmp/requirements.lock \
   295	    && pip install --require-hashes --no-build-isolation -r /tmp/requirements.lock
   296	
   297	FROM python:3.13-slim@sha256:6906dca82c0e83d5994bbf2e7fc33e6b63ce3e7f27c30eafd01dfabeb3c90bf3
   298	COPY services/python-security-floor.txt /usr/local/share/yueops/python-security-floor.txt
   299	RUN python -c 'from pathlib import Path; import re, sys; value = Path("/usr/local/share/yueops/python-security-floor.txt").read_text().strip(); assert re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value), value; floor = tuple(map(int, value.split("."))); assert sys.version_info[:2] == floor[:2] and sys.version_info[:3] >= floor, (sys.version_info[:3], floor)'
   300	
   301	ARG DEBIAN_SECURITY_EPOCH=2026-10-15-curl-deb13u7
   302	
   303	ENV PYTHONDONTWRITEBYTECODE=1 \
   304	    PYTHONUNBUFFERED=1 \
   305	    VIRTUAL_ENV=/opt/venv \
   306	    PATH="/opt/venv/bin:${PATH}" \
   307	    PYTHONPATH=/app \
   308	    YUEOPS_STATE_FILE=/app/data/state.json \
   309	    YUEOPS_IMAGE_CACHE_DIR=/app/data/image-cache \
   310	    ACME_HOME=/app/data/acme.sh \
   311	    ACME_BIN=/opt/acme.sh/acme.sh \
   312	    YUEOPS_CERT_DIR=/app/certs
   313	
   314	RUN test -n "${DEBIAN_SECURITY_EPOCH}" \
   315	    && apt-get update && apt-get install -y --no-install-recommends \
   316	    libpq5 ca-certificates curl jq openssl gpgv \
   317	    && dpkg --compare-versions "$(dpkg-query -W -f='${Version}' libpq5)" \
   318	       ge "17.11-0+deb13u1" \
   319	    && dpkg --compare-versions "$(dpkg-query -W -f='${Version}' curl)" \
   320	       ge "8.14.1-2+deb13u7" \
   321	    && dpkg --compare-versions "$(dpkg-query -W -f='${Version}' libcurl4t64)" \
   322	       ge "8.14.1-2+deb13u7" \
   323	    && apt-get install -y --only-upgrade \
   324	    util-linux bsdutils mount login libblkid1 libmount1 libsmartcols1 libuuid1 liblastlog2-2 \
   325	    libssl3t64 openssl openssl-provider-legacy gzip perl-base libpcre2-8-0 libsqlite3-0 \
   326	    libc6 libc-bin base-files bash tzdata libaudit1 libaudit-common libcap2 \
   327	    && dpkg --compare-versions "$(dpkg-query -W -f='${Version}' util-linux)" \
   328	       ge "2.41.5-0+deb13u1" \
   329	    && dpkg --compare-versions "$(dpkg-query -W -f='${Version}' libssl3t64)" \
   330	       ge "3.5.7-1~deb13u3" \
   331	    && dpkg --compare-versions "$(dpkg-query -W -f='${Version}' openssl)" \
   332	       ge "3.5.7-1~deb13u3" \
   333	    && dpkg --compare-versions "$(dpkg-query -W -f='${Version}' openssl-provider-legacy)" \
   334	       ge "3.5.7-1~deb13u3" \
   335	    && dpkg --compare-versions "$(dpkg-query -W -f='${Version}' gzip)" \
   336	       ge "1.13-1+deb13u1" \
   337	    && dpkg --compare-versions "$(dpkg-query -W -f='${Version}' perl-base)" \
   338	       ge "5.40.1-6+deb13u1" \
   339	    && dpkg --compare-versions "$(dpkg-query -W -f='${Version}' libpcre2-8-0)" \
   340	       ge "10.46-1~deb13u2" \
   341	    && dpkg --compare-versions "$(dpkg-query -W -f='${Version}' libsqlite3-0)" \
   342	       ge "3.46.1-7+deb13u2" \
   343	    && rm -rf /var/lib/apt/lists/* \
   344	    && groupadd --system --gid 65532 nonroot \
   345	    && useradd --system --uid 65532 --gid 65532 --no-create-home nonroot
   346	
   347	WORKDIR /app
   348	COPY --from=build /opt/venv /opt/venv
   349	# Runtime images do not install packages. Remove both copies of pip so its
   350	# build-only vendored SBOM is neither runtime attack surface nor vulnerability
   351	# inventory. Keep the independently locked setuptools wheel.
   352	RUN /usr/local/bin/python -m pip uninstall --yes pip \
   353	    && /opt/venv/bin/python -m pip uninstall --yes pip \
   354	    && ! command -v pip \
   355	    && ! command -v pip3 \
   356	    && /usr/local/bin/python -c 'import importlib.util; assert importlib.util.find_spec("pip") is None' \
   357	    && /opt/venv/bin/python -c 'import importlib.metadata as m, importlib.util; assert importlib.util.find_spec("pip") is None; assert m.version("setuptools") == "84.1.0"' \
   358	    && test ! -e /usr/local/lib/python3.13/site-packages/pip/_vendor/bom.cdx.json \
   359	    && test ! -e /opt/venv/lib/python3.13/site-packages/pip/_vendor/bom.cdx.json \
   360	    && extension="$(python -c 'import psycopg, psycopg_c.pq as module; print(module.__file__)')" \
   361	    && ldd "$extension" | grep -F 'libpq.so.5' \
   362	    && python -c 'import psycopg, psycopg_pool; assert psycopg.__version__ == "3.3.6"; assert psycopg.pq.__impl__ == "c"; assert psycopg.pq.version() >= 170011'
   363	
   364	COPY --chown=65532:65532 --from=consolebuild /build/frontend/dist/ ./frontend/dist/
   365	COPY --chown=65532:65532 web/ ./web/
   366	COPY --chown=65532:65532 internal_service_auth.py ./
   367	# yueops/ carries the generated brand constants (yueops/brand_g.py, written by the
   368	# root design/build-sources.mjs). Nothing under /app/config is baked: production
   369	# bind-mounts /opt/yueops/config there read-only (M5 crash-loop, 2026-10-29).
   370	COPY --chown=65532:65532 yueops/ ./yueops/
   371	COPY --chown=65532:65532 yueops_runtime/ ./yueops_runtime/
   372	COPY --chown=65532:65532 alembic/ ./alembic/
   373	COPY --chown=65532:65532 alembic.ini ./
   374	# Runtime documents (help, bot copy, legal). Import-safe: no bot config or ledger.
   375	COPY --chown=65532:65532 telegram-bot/yue/runtime_config/ ./runtime_config/
   376	# 2026-07-06 部署缺陷收口: fleet 运维脚本(agent.sh/manage.sh/route 等)由
   377	# deploy.py SCRIPTS_DIR=/app/scripts 推给节点。历史上只走 host bind mount
   378	# /opt/yueops/scripts → 提交+rebuild 的脚本修复静默不上线(stale)。改为 baked。
   379	# P2 §6 C3 (2026-09-24): bake ONLY the files the web runtime references (was the whole
   380	# ~1240-file tree, so 38/60 Ops commits rebuilt this image for scripts it never reads).
   381	# The list is services/yueops-web/runtime-scripts.json; the guard is
   382	# `scripts/generate-web-runtime-scripts-inventory.py --check` (fails when runtime code
   383	# references a scripts/ file not COPYed here, or a COPYed file nothing references).
   384	# One COPY per target directory keeps the paths without depending on `COPY --parents`.
   385	COPY --chown=65532:65532 \
   386	    scripts/abuse-blocklist.txt \
   387	    scripts/agent.sh \
   388	    scripts/node-unit-failure.py \
   389	    scripts/assert-node-recreate-safe.sh \
   390	    scripts/converge-yue-node-host.sh \
   391	    scripts/endpoint-salt-dns-sync.py \
   392	    scripts/fast-prepare.sh \
   393	    scripts/manage.sh \
   394	    scripts/renewal-allowance.json \
   395	    scripts/route-hysteria.acl \
   396	    scripts/route-xray.json \
   397	    scripts/verify-image-signature.sh \
   398	    scripts/yue-egress6-host.sh \
   399	    scripts/yue-node-effective-gso-policy.sh \
   400	    scripts/yue-node.gso-policy \
   401	    scripts/yue-node.fairshare-policy \
   402	    scripts/yueops-agent.service \
   403	    scripts/yueops-alembic-gate.py \
   404	    ./scripts/
   405	COPY --chown=65532:65532 scripts/config/dns-only-members.json ./scripts/config/
   406	COPY --chown=65532:65532 scripts/units/yue-tg-notify.node@.service ./scripts/units/
   407	COPY --chown=65532:65532 scripts/host-abuse-guard/yueops-host-abuse-guard.service scripts/host-abuse-guard/yueops-host-abuse-guard.sh ./scripts/host-abuse-guard/
   408	COPY --chown=65532:65532 scripts/lib/release_yaml.py scripts/lib/release-signer.gpg scripts/lib/fleet-inventory-env.sh scripts/lib/routing-domain-pin.json ./scripts/lib/
   409	COPY --chown=65532:65532 scripts/yueops-tuning/nfpm-relay.yaml scripts/yueops-tuning/nfpm.yaml ./scripts/yueops-tuning/
   410	COPY --chown=65532:65532 scripts/yueops-tuning/files/usr/local/sbin/node-watchdog.sh scripts/yueops-tuning/files/usr/local/sbin/yueops-memhigh-apply.sh ./scripts/yueops-tuning/files/usr/local/sbin/
   411	COPY --chown=65532:65532 --from=acmebuild /out/ /opt/acme.sh/
   412	COPY --from=verifytools /out/cosign /usr/local/bin/cosign
   413	COPY --from=verifytools /out/gh /usr/local/bin/gh
   414	# Baked yueops-tuning .debs (from stage 0) — deploy.py ensure_tuning_deb reads these in-container
   415	# (container can't reach host /opt/yueops/artifacts). CLI runs from bastion still use the host dir.
   416	COPY --chown=65532:65532 --from=debbuild /out/ ./artifacts/
   417	
   418	EXPOSE 8010
   419	USER 65532:65532
   420	
   421	HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
   422	    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/api/readyz', timeout=5).close()"]
   423	
   424	CMD ["opentelemetry-instrument", "uvicorn", "web.app:app", "--host", "127.0.0.1", "--port", "8010", "--workers", "1"]

exec
/bin/bash -lc "git grep -n -e 'alpine:3.22' -e 'alpine:3.24' -e 'debbuild' af53fb7e8884e8edacf675956e7c5c6abc386e96 -- tests services .github" in /home/box/Projects/yueto/yueops
 succeeded in 0ms:
af53fb7e8884e8edacf675956e7c5c6abc386e96:services/yueops-web/Dockerfile:20:FROM alpine:3.24@sha256:be2656061b536c1883c4034790e21d0a09c5aaaf51968b89368a3c0371ea2c9a AS debbuild
af53fb7e8884e8edacf675956e7c5c6abc386e96:services/yueops-web/Dockerfile:56:FROM alpine:3.24@sha256:be2656061b536c1883c4034790e21d0a09c5aaaf51968b89368a3c0371ea2c9a AS acmebuild
af53fb7e8884e8edacf675956e7c5c6abc386e96:services/yueops-web/Dockerfile:416:COPY --chown=65532:65532 --from=debbuild /out/ ./artifacts/
af53fb7e8884e8edacf675956e7c5c6abc386e96:services/yueops-web/runtime-scripts.json:5:  "debbuild_inputs": [
af53fb7e8884e8edacf675956e7c5c6abc386e96:tests/test_baked_tuning_reproducible_20260905.py:248:    stage = dockerfile.split(" AS debbuild", 1)[1].split("\nFROM ", 1)[0]
af53fb7e8884e8edacf675956e7c5c6abc386e96:tests/test_baked_tuning_reproducible_20260905.py:278:            assert copied.is_file(), f"Docker debbuild omitted {item['src']}"
af53fb7e8884e8edacf675956e7c5c6abc386e96:tests/test_baked_tuning_reproducible_20260905.py:285:    stage = (ROOT / "services/yueops-web/Dockerfile").read_text().split(" AS debbuild", 1)[1].split("\nFROM ", 1)[0]
af53fb7e8884e8edacf675956e7c5c6abc386e96:tests/test_baked_tuning_reproducible_20260905.py:290:    stage = (ROOT / "services/yueops-web/Dockerfile").read_text().split(" AS debbuild", 1)[1].split("\nFROM ", 1)[0]
af53fb7e8884e8edacf675956e7c5c6abc386e96:tests/test_baked_tuning_reproducible_20260905.py:293:    with pytest.raises(AssertionError, match="Docker debbuild omitted ../node-unit-failure.py"):
af53fb7e8884e8edacf675956e7c5c6abc386e96:tests/test_input_equivalence_b1_20260924.py:22:PINNED = "alpine:3.22@sha256:" + "0" * 64
af53fb7e8884e8edacf675956e7c5c6abc386e96:tests/test_input_equivalence_b1_20260924.py:159:    (r / "services/yue-bot/Dockerfile").write_text("FROM alpine:3.22\nCOPY telegram-bot/yue/ /app/\n")
af53fb7e8884e8edacf675956e7c5c6abc386e96:tests/test_tuning_release_20260926.py:7:哈希来自 Dockerfile 同链（linux/amd64 alpine:3.22@14358309 + nfpm 2.44.0 官方 x86_64 包，
af53fb7e8884e8edacf675956e7c5c6abc386e96:tests/test_tuning_release_20260927.py:8:哈希来自 Dockerfile 同链（linux/amd64 alpine:3.22@14358309 + nfpm 2.44.0 官方 x86_64 包，
af53fb7e8884e8edacf675956e7c5c6abc386e96:tests/test_web_runtime_scripts_inventory_20260924.py:198:        "FROM a AS debbuild\nCOPY scripts/units/ /u/\nFROM b\nCOPY web/ ./web/\n" + copies)
af53fb7e8884e8edacf675956e7c5c6abc386e96:tests/test_web_runtime_scripts_inventory_20260924.py:215:    assert out["debbuild_inputs"] == ["scripts/units"]

exec
/bin/bash -lc 'git show af53fb7e8884e8edacf675956e7c5c6abc386e96:scripts/yueops-tuning/build-reviewed.sh' in /home/box/Projects/yueto/yueops
 succeeded in 0ms:
#!/bin/sh
# Shared Docker/local packaging boundary. Only publish the two reviewed bytes;
# each independent profile owns its epoch/version/hash. Never source a manifest.
set -eu
set -f
export LC_ALL=C TZ=UTC

fail() { printf 'FATAL: %s\n' "$*" >&2; exit 78; }
[ "$#" -eq 1 ] || fail 'usage: build-reviewed.sh /absolute/output/directory'
output_dir=$1
case "$output_dir" in /*) ;; *) fail 'output directory must be absolute' ;; esac
[ ! -L "$output_dir" ] || fail 'output directory must not be a symlink'
cd "$(dirname "$0")"
NFPM_BIN=${NFPM_BIN:-nfpm}
tool_report=$("$NFPM_BIN" --version) || fail 'nfpm version command failed'
tool_version=$(printf '%s\n' "$tool_report" | awk '
  $1 == "GitVersion:" { count++; if (NF != 2) bad=1; version=$2 }
  END { if (count != 1 || bad || version !~ /^[0-9]+\.[0-9]+\.[0-9]+$/) exit 78; print version }
') || fail 'nfpm did not report one exact release version'

mkdir -p "$output_dir"
build_stage=$(mktemp -d "$output_dir/.tuning-build.XXXXXX")
trap 'rm -rf -- "$build_stage"' EXIT
trap 'exit 130' HUP INT TERM

for track in direct relay; do
  case "$track" in
    direct) profile=nfpm.yaml; package=yueops-tuning; prefix=release; hash_key=DIRECT_PACKAGE_SHA256 ;;
    relay) profile=nfpm-relay.yaml; package=yueops-tuning-relay; prefix=release-relay; hash_key=RELAY_PACKAGE_SHA256 ;;
  esac
  [ -f "$profile" ] && [ ! -L "$profile" ] || fail "missing regular profile: $profile"
  version=$(awk '
    $1 == "version:" {
      count++
      if ($0 !~ /^version: "[0-9][0-9][0-9][0-9]\.[0-9][0-9]\.[0-9][0-9]\.[0-9]+"$/) bad=1
      value=$2; gsub(/"/, "", value)
    }
    END { if (count != 1 || bad) exit 78; print value }
  ' "$profile") || fail "profile has no unique closed version: $profile"
  manifest="$prefix-$version.env"
  [ -f "$manifest" ] && [ ! -L "$manifest" ] || fail "missing regular reviewed manifest: $manifest"
  # Exact six-line independent-track schema: unknown/duplicate/injected fields
  # fail before either package is built. A caller's SOURCE_DATE_EPOCH cannot
  # silently replace either profile's reviewed timestamp.
  identity=$(awk -F= -v package="$package" -v version="$version" -v hash_key="$hash_key" '
    NF != 2 { bad=1 }
    NR == 1 && $0 != "PACKAGE_NAME=" package { bad=1 }
    NR == 2 && $0 != "PACKAGE_VERSION=" version { bad=1 }
    NR == 3 && $0 != "PACKAGE_ARCH=amd64" { bad=1 }
    NR == 4 {
      if ($1 != "SOURCE_DATE_EPOCH" || $2 !~ /^[1-9][0-9]*$/ || length($2) > 10) bad=1
      epoch=$2
    }
    NR == 5 {
      if ($1 != "NFPM_VERSION" || $2 !~ /^[0-9]+\.[0-9]+\.[0-9]+$/) bad=1
      nfpm=$2
    }
    NR == 6 {
      if ($1 != hash_key || length($2) != 64 || $2 ~ /[^a-f0-9]/) bad=1
      digest=$2
    }
    END { if (NR != 6 || bad) exit 78; print epoch, nfpm, digest }
  ' "$manifest") || fail "manifest is not the closed reviewed identity: $manifest"
  # Intentional split of three already-validated scalar fields; globbing is off.
  # shellcheck disable=SC2086
  set -- $identity
  [ "$#" -eq 3 ] && [ "$2" = "$tool_version" ] || fail "nfpm version differs from $manifest"
  printf '%s %s %s %s %s\n' "$profile" "$package" "$version" "$1" "$3" >"$build_stage/$track.identity"
done

for track in direct relay; do
  read -r profile package version epoch expected <"$build_stage/$track.identity"
  SOURCE_DATE_EPOCH="$epoch" "$NFPM_BIN" package -f "$profile" -p deb -t "$build_stage/$package.deb"
  if command -v sha256sum >/dev/null 2>&1; then
    actual=$(sha256sum "$build_stage/$package.deb" | awk '{print $1}')
  else
    actual=$(shasum -a 256 "$build_stage/$package.deb" | awk '{print $1}')
  fi
  [ "$actual" = "$expected" ] || fail "$package $version bytes differ from the reviewed manifest"
  printf 'TUNING_PACKAGE_VERIFIED package=%s version=%s sha256=%s\n' "$package" "$version" "$actual"
done

# Neither outward artifact is replaced before both independent hashes pass.
for package in yueops-tuning yueops-tuning-relay; do
  [ ! -L "$output_dir/$package.deb" ] || fail 'artifact target must not be a symlink'
  [ ! -e "$output_dir/$package.deb" ] || [ -f "$output_dir/$package.deb" ] || fail 'artifact target must be absent or a regular file'
done
for package in yueops-tuning yueops-tuning-relay; do
  install -m 0644 "$build_stage/$package.deb" "$output_dir/$package.deb"
done

exec
/bin/bash -lc 'git diff --check b49ac9278431e20daf126089328237901f0b6cb7 af53fb7e8884e8edacf675956e7c5c6abc386e96; git show af53fb7e8884e8edacf675956e7c5c6abc386e96:scripts/yueops-tuning/nfpm.yaml | head -65' in /home/box/Projects/yueto/yueops
 succeeded in 0ms:
# yueops-tuning — declarative, drift-proof node network/perf tuning.
# Build:  nfpm package -f nfpm.yaml -p deb -t ./out/
# Ships sysctl.d + systemd .link (NIC offload) + udev RPS rule, superseding the legacy
# oneshot scripts (nic-optimize / rps-tune / nic-offload-guard) that drifted.
name: yueops-tuning
arch: amd64
platform: linux
version: "2026.11.02.1"
section: admin
priority: optional
maintainer: YueOps <onesyue@gmail.com>
homepage: https://github.com/onesyue/yueops
description: |
  YueOps node network/performance tuning (direct proxy profile).
  Declarative & drift-proof: sysctl.d owns kernel tuning, a systemd .link file owns NIC
  offloads (self-heals on every device event via udev), a udev rule owns RPS/RFS.
  Replaces the drift-prone oneshot scripts (nic-optimize.service, yueops-rps-tune.service,
  nic-offload-guard.timer). Kernel stays stock XanMod (BBRv3; measured 2026-08-29).
license: proprietary
depends:
  - ethtool
  - nftables
  - util-linux
  - python3
  # earlyoom is a HARD dependency, not an assumption.  The postinst can only
  # install the policy when earlyoom.service exists; where it does not, that
  # branch prints "policy template staged, not applied" and the host silently
  # ends up with no userspace OOM guard at all.  2026-08-03 fleet survey: 5 of
  # 44 hosts were in exactly that state (yue-tw-2 / -3 / -premium-2 — the three
  # tightest-memory QEMU boxes — plus both v4 relays), and nothing reported it.
  # Declaring it here makes `dpkg -i` fail loudly on such a host instead; every
  # installer therefore resolves deps (dpkg -i → apt-get -f install → retry).
  - earlyoom

# Regular files (not conffiles): dpkg overwrites on upgrade so the package version ALWAYS
# wins = fleet-uniform canonical. `dpkg -V yueops-tuning` still detects manual drift.
contents:
  # 本地扩展点目录（内容不属于本包，由 yueops-shield 推广器按角色渲染；见 nftables.conf 的 include）。
  - src: files/etc/nftables.d/README
    dst: /etc/nftables.d/README
  - src: files/etc/sysctl.d/99-yueops-2026.conf
    dst: /etc/sysctl.d/99-yueops-2026.conf
  - src: files/etc/sysctl.d/99-zz-conntrack.conf
    dst: /etc/sysctl.d/99-zz-conntrack.conf
  - src: files/etc/sysctl.d/99-zzz-yueops-pinned.conf
    dst: /etc/sysctl.d/99-zzz-yueops-pinned.conf
  - src: files/etc/sysctl.d/99-zzz-yueops-proxy.conf
    dst: /etc/sysctl.d/99-zzz-yueops-proxy.conf
  # nf_conntrack preload — the precondition for every conntrack sysctl this package
  # ships. Was previously created only by node-fix.sh / fast-prepare.sh / deploy.py,
  # i.e. unowned: two hosts provisioned 2026-08-03 never got it and ran the whole
  # conntrack profile at kernel defaults while `dpkg -V` stayed clean.
  - src: files/etc/modules-load.d/yueops-conntrack.conf
    dst: /etc/modules-load.d/yueops-conntrack.conf
  # nf_conntrack hash-table size. Sibling of the preload above and the same class of
  # bug: /proc/sys/.../nf_conntrack_buckets is READ-ONLY, so no sysctl.d file this
  # package ships can set it — only a modprobe.d option or a live sysfs write can.
  # It was therefore written solely by node-fix.sh, a manual one-shot, and 2026-08-03
  # found five cloned hosts running a 65536-bucket table (load factor ~0.85 against a
  # 46k-56k steady-state count) plus one host that had the right runtime value with no
  # file, i.e. queued to regress on its next reboot.
  - src: files/etc/modprobe.d/yueops-nf_conntrack.conf
    dst: /etc/modprobe.d/yueops-nf_conntrack.conf
  - src: files/etc/systemd/network/10-yueops.link
    dst: /etc/systemd/network/10-yueops.link

codex
仅审查了指定 diff，未发现可确认的缺陷。未执行镜像构建或验证远端 digest 可用性。

VERDICT: approve

- `services/yueops-web/Dockerfile:20`、`:56`：仅更新构建阶段的 Alpine 固定版本；下载校验、产物哈希检查和运行时基础镜像保持不变，无测试削弱或新增秘密暴露。
tokens used
37,224
仅审查了指定 diff，未发现可确认的缺陷。未执行镜像构建或验证远端 digest 可用性。

VERDICT: approve

- `services/yueops-web/Dockerfile:20`、`:56`：仅更新构建阶段的 Alpine 固定版本；下载校验、产物哈希检查和运行时基础镜像保持不变，无测试削弱或新增秘密暴露。
```
