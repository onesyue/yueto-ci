"""YueOps native contract validator."""

from __future__ import annotations

import sys
from pathlib import Path as _ConstantsPath
_CI_LIB = str(_ConstantsPath(__file__).resolve().parents[1] / "lib")
if _CI_LIB not in sys.path:
    sys.path.insert(0, _CI_LIB)
from ci_constants import NODE_ENTRYPOINT_NEEDLE, NODE_EXPECTED_PATH_NEEDLE, NODE_SUBPROCESS_TIMEOUT_SECONDS, OPS_DEPLOY_MIN_FILES

import hashlib
import json
import re
import subprocess
from pathlib import Path

from .fragments import forbid, read, read_bytes, read_package, require


def validate_widget_identity_artifact(widget: str) -> None:
    """Execute the identity model extracted from the shipped artifact, offline."""
    start, end = "function scDeviceIdentityModel(dv)", "var SC_RESET_OPERATION_PREFIX"
    if widget.count(start) != 1 or widget.count(end) != 1:
        raise RuntimeError("published widget identity model boundaries drifted")
    model = widget[widget.index(start):widget.index(end)]
    if not 0 < len(model) <= 16384:
        raise RuntimeError("published widget identity model is not bounded")
    # No require/process/browser objects enter the VM. Both the VM and its
    # parent process are bounded; the input is the actual public artifact.
    script = r"""
const vm = require('node:vm');
const fs = require('node:fs');
const model = fs.readFileSync(0, 'utf8');
for (const [input, expected] of [
  [{identities:[{online:true,source:'hwid'},{online:false,source:'manual'}],
    ips:['a','b','c','a'],count:4}, [2,1,3,3]],
  [{identities:[],ips:['a','b'],count:2}, [0,0,2,2]],
]) {
  const sandbox = Object.create(null);
  const result = vm.runInNewContext(
    'const input=' + JSON.stringify(input) + ';function T(a,b){return b;}\n' + model +
    '\nJSON.stringify(scDeviceIdentityModel(input))', sandbox,
    {timeout:1000,codeGeneration:{strings:false,wasm:false}});
  const value = JSON.parse(result);
  const actual = [value.rows.length,value.onlineIdentities,value.sharedIps.length,value.unmatchedOnline];
  if (JSON.stringify(actual) !== JSON.stringify(expected) || value.rows.some(row=>row.kind!=='identity'))
    throw new Error('published widget combines network projection with identity rows');
}
"""
    try:
        subprocess.run(["node", "-e", script], input=model, text=True,
                       capture_output=True, check=True, timeout=NODE_SUBPROCESS_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("published widget identity behavior failed") from exc


def validate_widget_projection(root: Path) -> str:
    """Bind the readable inputs, manifest and both public consumers."""
    widget = read_bytes(root / "checkin-api/static/chat-widget.js")
    if widget != read_bytes(root / "nginx/html/assets/chat-widget.js"):
        raise RuntimeError("published widget API/site bytes diverged")
    manifest = json.loads(read(root / "site/published.json"))
    if manifest.get("files", {}).get("assets/chat-widget.js") != hashlib.sha256(widget).hexdigest():
        raise RuntimeError("published widget digest differs from generated manifest")
    # Reuse the generator's own input list and hashing, not another source list.
    script = "import { inputsDigest } from './site/scripts/lib.mjs'; process.stdout.write(await inputsDigest());"
    try:
        result = subprocess.run(["node", "--input-type=module", "-e", script],
                                cwd=root, capture_output=True, text=True, check=True, timeout=NODE_SUBPROCESS_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("published widget input digest could not be verified") from exc
    if manifest.get("inputs_sha256") != result.stdout:
        raise RuntimeError("published widget readable inputs drifted from generated manifest")
    public = widget.decode("utf-8")
    validate_widget_identity_artifact(public)
    return public


def validate_board_schema_input(yueboard_contract_root: Path) -> None:
    # The selected Board owns its schema generation. Native ACL/schema tests
    # execute its real fixture; central numeric equality cannot establish compatibility.
    board_floor = read(yueboard_contract_root / "schema-floor.txt").strip()
    if re.fullmatch(r"[1-9][0-9]*", board_floor) is None:
        raise RuntimeError("admitted YueBoard schema floor must be a positive integer")
    fixture = yueboard_contract_root / "test/fixtures/schema.sql"
    if fixture.is_symlink() or not read(fixture).strip():
        raise RuntimeError("admitted YueBoard schema fixture must be a nonempty regular file")



def _read_yueops_inputs(
    root: Path, contract: dict, yueboard_contract_root: Path | None
) -> dict[str, object]:
    if yueboard_contract_root is None:
        raise RuntimeError(
            "YueOps validation requires the admitted YueBoard contract checkout"
        )
    validate_board_schema_input(yueboard_contract_root)
    # 2026-09-20：deploy.py 3004 → 513 行 + 8 个 deploy_*.py。片段的主语是**部署生成器
    # 这个模块族**，不是那一个文件。地板让"glob 写错扫到空气"不能被当成通过。
    deploy = read_package(root / "yueops", "deploy*.py", min_files=OPS_DEPLOY_MIN_FILES)
    nodeauth = read(root / "yueops/nodeauth.py")
    agent = read(root / "scripts/agent.sh")
    guard = read(root / "scripts/assert-node-recreate-safe.sh")
    rollout = read(root / "scripts/rollout-yue-node-image.sh")
    rollout_finalizer = read(root / "scripts/finalize-yue-node-rollout-runtime.sh")
    rollout_verifier = read(root / "scripts/verify-yue-node-rollout-control-plane.py")
    internal_api = read(root / "scripts/lib/yueboard-internal-api.sh")
    rollout_tests = read(root / "tests/test_yue_node_rollout_control_plane_20260730.py")
    watchdog = read(
        root / "scripts/yueops-tuning/files/usr/local/sbin/node-watchdog.sh"
    )
    migrator = read(root / "scripts/node-control-auth-migrate.py")
    self_heal = read(root / "scripts/yueops-self-heal.py")
    digest_deployer = read(root / "scripts/deploy-yueops-digests.sh")
    telemetry_ingest = read(root / "checkin-api/telemetry/ingest.py")
    telemetry_dashboard = read(root / "checkin-api/telemetry/dashboard.py")
    ai_runtime = read(root / "telegram-bot/yue/yue_ai_runtime.py")
    widget = validate_widget_projection(root)
    widget_source = read(root / "checkin-api/src/chat-widget.js")
    widget_test = read(root / "tests/test_chat_widget_device_identity_20260730.py")
    account_api = read(root / "checkin-api/api/account.py")
    layout = contract["layout"]
    control = contract["control"]
    presence = contract["presence"]
    identity = contract["device_identity"]
    if presence.get("rollout_order") != [
        "yueboard_control_plane_locked",
        "yue_node_fleet",
        "credential_consumers",
    ]:
        raise RuntimeError("native rollout order must bootstrap locked YueBoard first")
    return {
        "deploy": deploy,
        "nodeauth": nodeauth,
        "agent": agent,
        "guard": guard,
        "rollout": rollout,
        "rollout_finalizer": rollout_finalizer,
        "rollout_verifier": rollout_verifier,
        "internal_api": internal_api,
        "rollout_tests": rollout_tests,
        "watchdog": watchdog,
        "migrator": migrator,
        "self_heal": self_heal,
        "digest_deployer": digest_deployer,
        "telemetry_ingest": telemetry_ingest,
        "telemetry_dashboard": telemetry_dashboard,
        "ai_runtime": ai_runtime,
        "widget": widget,
        "widget_source": widget_source,
        "widget_test": widget_test,
        "account_api": account_api,
        "layout": layout,
        "control": control,
        "presence": presence,
        "identity": identity,
    }


def _validate_yueops_rollout(contract: dict, sources: dict[str, object]) -> None:
    deploy = sources["deploy"]
    nodeauth = sources["nodeauth"]
    agent = sources["agent"]
    guard = sources["guard"]
    rollout = sources["rollout"]
    rollout_verifier = sources["rollout_verifier"]
    internal_api = sources["internal_api"]
    layout = sources["layout"]
    control = sources["control"]
    presence = sources["presence"]
    presence = contract["presence"]
    require(
        deploy,
        [
            '"yue-node-1": ("hy2", True)',
            '"yue-node-2": ("vless", False)',
            f'expected_kernel = {{1: "{layout["node-1"]["kernel"]}", 2: "{layout["node-2"]["kernel"]}"}}',
            "kernel aliases and role swaps are retired",
            "panel.url must be a root YueBoard ConnectRPC base URL",
            NODE_ENTRYPOINT_NEEDLE,
        ],
        "YueOps deployment generator",
    )
    require(
        nodeauth,
        [control["deployment_probe_rpc"], "GET_CONFIG_PROCEDURE"],
        "YueOps deployment authorization",
    )
    if "LIST_MACHINE_NODES_PROCEDURE" in nodeauth:
        raise RuntimeError("YueOps deployment still depends on retired discovery")
    require(
        agent,
        [
            control["machine_status_rpc"],
            control["credential_file"],
            'cmp -s "$credential1" "$credential2"',
        ],
        "YueOps machine status authority",
    )
    require(
        guard + rollout,
        [layout["node-1"]["artifact"], layout["node-2"]["artifact"]],
        "YueOps recreation/rollout gates",
    )
    require(
        internal_api,
        [
            "X-Control-Token",
            "yueboard_internal_control_token",
            "yueboard_internal_request",
            "curl --config",
        ],
        "YueOps protected YueBoard internal client",
    )
    require(
        rollout,
        [
            presence["rollout_proof_endpoint"],
            "yue-node-control-pre.",
            "yue-node-control-post.",
            "--print-machine-id",
            "verify-yue-node-rollout-control-plane.py",
            "finalize_remote_transaction commit",
            "finalize_remote_transaction rollback",
            "--action '$action'",
            "BOOTSTRAP_LEGACY_NODES=${BOOTSTRAP_LEGACY_NODES:-0}",
            "--allow-missing-predecessors",
            "CONTROL_PROOF_TIMEOUT",
        ],
        "YueOps two-phase control-plane rollout",
    )
    require(
        rollout_verifier,
        [
            # The Node binary still advertises the retired credential flag to
            # predecessor Boards during Release A.  The pinned Board filters
            # that transition-only flag from its negotiated serving proof, so
            # YueOps must verify the steady-state capabilities here.  Reusing
            # release_a_rollout_capabilities for both sides made the central
            # contract reject the exact proof shape emitted in production.
            *[f'"{capability}"' for capability in presence["required_capabilities"]],
            f"EXPECTED_LEASE_SECONDS = {presence['process_lease_seconds']}",
            'process.get("process_instance_id")',
            'process.get("lease_state") == "active"',
            # 2026-08-01：这里原本钉的是「replacement 的 applied_*_generation
            # 必须等于 desired_*」。那条要求**结构上不可满足**，已按实测撤下：
            # device generation 会因舰队里任何一个 assignment 的 fanout 变更而
            # 前进，节点按定义追不上「查看那一刻的最新代际」——78~85 个活跃进程、
            # 两分半内七次采样，generations_applied 每次都是 0 个 true。
            # 钉着它等于让 post-proof 永远通不过、舰队镜像永远对不齐。
            #
            # 换上的证据更强且可满足（对齐 xDS 的 ACK 语义：ACK 携带客户端
            # **成功处理过的**版本，而非服务端当前最新版本）：
            #   · 每个 assignment 恰好一个活跃进程；
            #   · 前任实例已越过 durable fence；
            #   · 能力集逐项精确相等；
            #   · last_seen / last_reported / last_applied **三者都晚于 rollout 栅栏**
            #     —— 这才是「这次 rollout 之后确实完成了一次控制面往返」的证明，
            #     也正是节点本地 HEALTH 检查证明不了的那一件事。
            'for field in ("last_seen_unix", "last_reported_at_unix", "last_applied_at_unix")',
            "is not newer than the rollout fence",
            "post proof must identify exactly one serving process per assignment",
            "post process lacks the exact serving capabilities",
            "pre-fence process remained active after rollout",
            "predecessor process has not crossed its durable fence",
        ],
        "YueOps durable rollout proof verifier",
    )


def _validate_yueops_runtime(root: Path, sources: dict[str, object]) -> None:
    deploy = sources["deploy"]
    rollout_finalizer = sources["rollout_finalizer"]
    rollout_tests = sources["rollout_tests"]
    watchdog = sources["watchdog"]
    self_heal = sources["self_heal"]
    digest_deployer = sources["digest_deployer"]
    telemetry_ingest = sources["telemetry_ingest"]
    telemetry_dashboard = sources["telemetry_dashboard"]
    require(
        rollout_finalizer,
        [
            "OLD_IMAGE_REF_",
            "OLD_IMAGE_ID_",
            "--pull never",
            "verify-yue-node-rollout-runtime.sh",
            "transaction retained",
        ],
        "YueOps exact predecessor rollback",
    )
    require(
        rollout_tests,
        [
            "test_exact_new_process_capability_generation_and_fence_proof_passes",
            "test_ambiguous_or_stale_control_plane_proof_fails_closed",
            "test_rollout_source_keeps_recovery_armed_until_bastion_proof",
        ],
        "YueOps rollout proof regression tests",
    )
    if (root / "scripts/rollout-image-upgrade.sh").exists():
        raise RuntimeError(
            "retired image rollout compatibility entrypoint still exists"
        )
    require(
        deploy,
        [
            "native_healthy",
            "/readyz",
            NODE_EXPECTED_PATH_NEEDLE,
        ],
        "YueOps native status",
    )
    forbid(
        deploy,
        ["sync stream connected", "sync stream disconnected"],
        "YueOps native status",
    )
    require(
        watchdog,
        ["1:hysteria", "2:xray", "native_role_drift"],
        "YueOps native watchdog",
    )
    forbid(
        watchdog,
        ["hysteria2|singbox", "docker-compose.yml", "docker restart"],
        "YueOps native watchdog",
    )
    forbid(
        self_heal,
        ["systemctl restart sing-box", "sing-box.service.d"],
        "YueOps self-heal",
    )
    forbid(
        digest_deployer,
        ["legacy_health_url", "allow_legacy"],
        "YueOps native digest deployment",
    )
    require(
        telemetry_ingest,
        ["_native_event_violation", 'frozenset({"node_urltest"})'],
        "YueLink native telemetry ingress",
    )
    forbid(
        telemetry_ingest + telemetry_dashboard,
        [
            "_normalize_native_server_id",
            "_aggregate_legacy_urltest_rows",
            "def stats_node_health",
        ],
        "YueLink native telemetry runtime",
    )


def _validate_yueops_account(root: Path, sources: dict[str, object]) -> None:
    migrator = sources["migrator"]
    ai_runtime = sources["ai_runtime"]
    widget = sources["widget"]
    widget_source = sources["widget_source"]
    widget_test = sources["widget_test"]
    account_api = sources["account_api"]
    identity = sources["identity"]
    require(
        ai_runtime,
        ['raise RuntimeError("yue_ai cursor provider is not configured")'],
        "Yue AI runtime dependency injection",
    )
    require(
        widget_source,
        [
            "function scParseDevices(response)",
            "var countFloor = Math.max(onlineRows, data.shared_online ? 1 : 0);",
            identity["devices_endpoint"],
            identity["reset_endpoint"],
            identity["reset_identity_field"],
            "data.applied_user_ids.length === 1",
            "data.applied_user_ids[0] === expectedUserId",
            "/api/client/account/overview",
        ],
        "YueOps account widget device identity boundary",
    )
    require(
        re.sub(r"\s+", "", widget),
        [re.sub(r"\s+", "", fragment) for fragment in (
            "function scParseDevices(response)",
            "var countFloor = Math.max(onlineRows, data.shared_online ? 1 : 0);",
            identity["devices_endpoint"], identity["reset_endpoint"], identity["reset_identity_field"],
            "data.applied_user_ids.length === 1", "data.applied_user_ids[0] === expectedUserId",
            "/api/client/account/overview",
        )],
        "YueOps published widget device identity boundary",
    )
    require(
        widget_test,
        [
            "test_identity_rows_and_network_projection_are_not_added_together",
            "test_network_projection_is_authoritative_and_identities_contract_is_strict",
            "test_widget_loads_only_the_credential_free_account_projection",
        ],
        "YueOps account widget identity regression tests",
    )
    require(
        account_api,
        [
            "immutable_user_id = user.get('id')",
            "immutable_user_id != user_id",
            "'user_id':                  immutable_user_id",
        ],
        "YueOps immutable account projection",
    )
    forbid(
        ai_runtime,
        ["from config.db_connect import get_cursor as _fallback"],
        "Yue AI runtime dependency injection",
    )
    require(
        migrator,
        ['nodes[1]["kernel"] != "hysteria"'],
        "YueOps credential inventory",
    )
    forbid(
        migrator,
        ['add_parser("gates")', "CHANGE_NODE_AUTH_GATES", "WAIVE-NODE-LEGACY"],
        "YueOps credential hard cut",
    )
    # P2 §4 A3 (2026-09-24): the three-stage deployer is retired and frozen at its
    # last reviewed pin; panel-deploy.sh reads the signed release.yaml desired
    # state instead.  Require the retirement marker so the frozen floor can never
    # be mistaken for (or silently re-promoted to) the live schema contract.
    floor = read(root / "scripts/deploy-yueboard-panel.sh")
    require(floor, ["RETIRED (P2 §4 A3"], "YueOps retired YueBoard deployer")
    if (root / "scripts/yueboard-schema-release.env").exists():
        raise RuntimeError(
            "YueOps scripts/yueboard-schema-release.env is retired (P2 §4 A3)"
        )


def validate_yueops(
    root: Path, contract: dict, yueboard_contract_root: Path | None
) -> None:
    """Check one YueOps checkout against the central native contract."""
    sources = _read_yueops_inputs(root, contract, yueboard_contract_root)
    _validate_yueops_rollout(contract, sources)
    _validate_yueops_runtime(root, sources)
    _validate_yueops_account(root, sources)
