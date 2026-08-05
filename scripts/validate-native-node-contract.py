#!/usr/bin/env python3
"""Validate each source repository against the central native-node ABI."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


POLICY_ROOT = Path(__file__).resolve().parents[1]
PROTO_RELATIVE_PATH = Path("proto/yuenode/v1/yuenode.proto")
PROTO_DIGEST_PATH = Path("proto/CANONICAL.sha256")


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"required contract file is unavailable: {path}") from exc


def read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise RuntimeError(f"required contract file is unavailable: {path}") from exc


def canonical_digest(node_root: Path) -> str:
    """Read the yue-node mirror pin in its committed sha256sum format."""
    digest_path = node_root / PROTO_DIGEST_PATH
    lines = [line for line in read(digest_path).splitlines() if line.strip()]
    if len(lines) != 1:
        raise RuntimeError(
            f"{PROTO_DIGEST_PATH} must contain exactly one non-empty sha256sum line"
        )
    fields = lines[0].split()
    expected_name = str(PROTO_RELATIVE_PATH.relative_to("proto"))
    if len(fields) != 2 or fields[1] != expected_name:
        raise RuntimeError(
            f"{PROTO_DIGEST_PATH} must pin {expected_name!r} in sha256sum format"
        )
    if re.fullmatch(r"[0-9a-f]{64}", fields[0]) is None:
        raise RuntimeError(f"{PROTO_DIGEST_PATH} does not contain a lowercase SHA-256")
    return fields[0]


def validate_canonical_proto_mirror(node_root: Path, yueboard_root: Path) -> None:
    """Prove the checked-out node mirror equals the real YueBoard authority.

    The yue-node repository already checks its mirror against a digest stored
    in that same repository.  That catches incomplete local updates, but a
    mirror and digest can drift together while remaining internally green.
    Central CI checks out the reviewed YueBoard commit separately and calls
    this gate before any yue-node build, so all three artifacts must agree:
    canonical bytes, mirror bytes, and the committed mirror digest.
    """
    mirror_path = node_root / PROTO_RELATIVE_PATH
    canonical_path = yueboard_root / PROTO_RELATIVE_PATH
    mirror = read_bytes(mirror_path)
    canonical = read_bytes(canonical_path)
    mirror_hash = hashlib.sha256(mirror).hexdigest()
    canonical_hash = hashlib.sha256(canonical).hexdigest()
    pinned_hash = canonical_digest(node_root)

    if mirror != canonical:
        raise RuntimeError(
            "yue-node proto mirror differs byte-for-byte from the checked-out "
            "YueBoard canonical source "
            f"(mirror sha256={mirror_hash}, canonical sha256={canonical_hash}, "
            f"pinned sha256={pinned_hash})"
        )
    if pinned_hash != canonical_hash:
        raise RuntimeError(
            f"{PROTO_DIGEST_PATH} does not pin the checked-out canonical bytes "
            f"(pinned sha256={pinned_hash}, canonical sha256={canonical_hash})"
        )


def read_package(
    directory: Path,
    pattern: str,
    *,
    min_files: int,
    exclude_suffixes: tuple[str, ...] = (),
) -> str:
    """Concatenate every source file of a package.

    Contract fragments are asserted against a PACKAGE, not a file: Go lets a
    package be laid out across as many files as it likes, and a purely
    mechanical split must not read as a contract violation. (It did once —
    splitting yue-node's 2853-line internal/service/service.go moved
    `applyDeviceGeneration` into state.go and this guard reported the
    credential-generation boundary as missing.)

    `min_files` is the floor that keeps this from becoming the opposite
    failure: a glob that matches nothing yields "", every `forbid` passes, and
    only `require` would notice. Fail loudly instead of scanning air.
    """
    if not directory.is_dir():
        raise RuntimeError(f"required contract package is unavailable: {directory}")
    files = sorted(
        p
        for p in directory.glob(pattern)
        if p.is_file() and not p.name.endswith(exclude_suffixes)
    )
    if len(files) < min_files:
        raise RuntimeError(
            f"contract package {directory} matched {len(files)} file(s) for "
            f"{pattern!r} (floor {min_files}) — the scan did not run"
        )
    return "\n".join(p.read_text(encoding="utf-8") for p in files)


def read_tree(
    directory: Path,
    patterns: tuple[str, ...],
    *,
    min_files: int,
    exclude_suffixes: tuple[str, ...] = (),
) -> str:
    """Concatenate a runtime source tree without silently scanning zero files."""
    if not directory.is_dir():
        raise RuntimeError(f"required contract tree is unavailable: {directory}")
    files = sorted(
        {
            path
            for pattern in patterns
            for path in directory.rglob(pattern)
            if path.is_file() and not path.name.endswith(exclude_suffixes)
        }
    )
    if len(files) < min_files:
        raise RuntimeError(
            f"contract tree {directory} matched {len(files)} file(s) "
            f"(floor {min_files}) — the scan did not run"
        )
    return "\n".join(path.read_text(encoding="utf-8") for path in files)


def require(text: str, fragments: list[str], source: str) -> None:
    missing = [fragment for fragment in fragments if fragment not in text]
    if missing:
        raise RuntimeError(
            f"{source} is missing native contract fragments: {missing!r}"
        )


def forbid(text: str, fragments: list[str], source: str) -> None:
    present = [fragment for fragment in fragments if fragment in text]
    if present:
        raise RuntimeError(f"{source} contains retired contract fragments: {present!r}")


def forbid_casefold(text: str, fragments: list[str], source: str) -> None:
    folded = text.casefold()
    present = [fragment for fragment in fragments if fragment.casefold() in folded]
    if present:
        raise RuntimeError(f"{source} contains retired contract fragments: {present!r}")


def forbid_paths(root: Path, paths: list[str], source: str) -> None:
    """Fail if a retired source path is restored.

    Content guards alone do not distinguish a deliberately deleted authority
    implementation from an empty or renamed compatibility shell.  These paths
    were the Portal-installation token minting and beacon delivery surfaces;
    restoring either file is therefore itself a contract violation.
    """
    present = [path for path in paths if (root / path).exists()]
    if present:
        raise RuntimeError(f"{source} contains retired contract paths: {present!r}")


def rpc_name(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def validate_node(root: Path, contract: dict) -> None:
    dockerfile = read(root / "Dockerfile")
    makefile = read(root / "Makefile")
    launcher = read(root / "cmd/yue-node-launcher/main.go")
    dependency_gate = read(root / "scripts/check-profile-deps.sh")
    capability = read(root / "internal/capability/manifest.go")
    config = read(root / "internal/config/config.go")
    controlplane = read(root / "internal/controlplane/connect.go")
    proto = read(root / "proto/yuenode/v1/yuenode.proto")
    # The whole package, not one file — see read_package. yue-node's service
    # package is deliberately split by responsibility (service/state/sync/
    # transaction/users/kernel/reporting/observability/devices/validate).
    service = read_package(root / "internal/service", "*.go", min_files=8)
    service_test = read_package(root / "internal/service", "*_test.go", min_files=3)
    model_types = read(root / "internal/model/types.go")
    xray_dispatcher = read(root / "internal/kernel/xray/dispatcher.go")
    xray_test = read(root / "internal/kernel/xray/dispatcher_test.go")
    hysteria = read(root / "internal/kernel/hysteria/hysteria.go")
    hysteria_test = read(root / "internal/kernel/hysteria/user_device_guard_test.go")
    artifacts = [slot["artifact"] for slot in contract["layout"].values()]
    presence = contract["presence"]

    require(
        dockerfile,
        [
            "ARG BUILD_PROFILE=auto",
            "-o yue-node-hy2 ./cmd/yue-node",
            "-o yue-node-vless ./cmd/yue-node",
            "-o yue-node ./cmd/yue-node-launcher",
            "COPY --from=builder /build/yue-node* /usr/local/bin/",
        ],
        "yue-node Dockerfile",
    )
    require(
        makefile,
        ["VALID_BUILD_PROFILES := auto hy2 vless", "test: check-profile-deps"],
        "yue-node Makefile",
    )
    require(
        launcher,
        [
            "case capability.KernelHysteria:",
            "case capability.KernelXray:",
            'target := filepath.Join(filepath.Dir(executable), "yue-node-"+profile)',
            "syscall.Exec(target",
        ],
        "native role launcher",
    )
    require(
        dependency_gate,
        ["yue_profile_hy2", "yue_profile_vless", "profile dependency violation"],
        "profile dependency gate",
    )
    for artifact in artifacts:
        if Path(artifact).name not in dockerfile:
            raise RuntimeError(f"Dockerfile does not build native artifact {artifact}")
    require(
        proto,
        [f"rpc {rpc_name(path)}(" for path in contract["control"]["static_node_rpcs"]]
        + [f"rpc {rpc_name(contract['control']['machine_status_rpc'])}("],
        "yue-node ConnectRPC mirror",
    )
    forbid(
        proto,
        [f"rpc {rpc_name(path)}(" for path in contract["control"]["retired_rpcs"]]
        + [
            "bool auto_tls = 15;",
            "string domain = 16;",
            "string cipher = 17;",
            "string plugin = 18;",
            "string plugin_opts = 19;",
            "string server_key = 20;",
        ],
        "yue-node ConnectRPC mirror",
    )
    require(proto, ["reserved 15 to 20;"], "yue-node native NodeConfig")
    require(
        proto,
        [f"rpc {rpc_name(presence['report_rpc'])}("],
        "yue-node presence report RPC",
    )
    require(
        controlplane,
        [f'"{capability}"' for capability in presence["release_a_rollout_capabilities"]]
        + [
            '"crypto/rand"',
            "io.ReadFull(entropy, processRaw[:])",
            "ProcessInstanceId: c.processInstanceID",
            "PresenceInstanceId: p.cp.processInstanceID",
            "GetAcknowledgedUserGeneration()",
            "GetAcknowledgedDeviceGeneration()",
        ],
        "yue-node presence capability and receipt boundary",
    )
    require(
        service,
        [
            "s.kernel.UpdateGlobalDevices(users)",
            "DeviceState is an account-ID/IP projection",
            "runtime admission",
        ],
        "yue-node account/IP generation boundary",
    )
    require(
        service_test,
        [
            "TestDeviceGenerationPublishesAccountIPAdmissionPolicy",
            "account/IP generation was rejected",
        ],
        "yue-node account/IP generation regression test",
    )
    forbid(
        model_types + service,
        [
            "SyntheticCredentialIDFloor",
            "CredentialAdmissionLess",
            "UpdateGlobalDeviceCredentials",
            "BillingUserID",
        ],
        "yue-node retired synthetic credential authority",
    )
    require(
        xray_dispatcher + hysteria,
        [
            "local∪global union",
            "canonicalDeviceIP",
        ],
        "yue-node canonical account/IP native kernels",
    )
    require(
        xray_test + hysteria_test,
        [
            "TestLimitDispatcherDeviceLimitUsesDeduplicatedLocalGlobalUnion",
            "TestDeviceLimitDeduplicatesCanonicalLocalGlobalUnion",
        ],
        "yue-node credential/IP regression tests",
    )
    require(
        capability,
        [
            'InboundProtocols:    []string{"vless"}',
            'StructuredOutbounds: []string{"vless", "socks", "http", "wireguard"}',
        ],
        "yue-node native capability manifest",
    )
    forbid(
        capability,
        ['case "hysteria2", "hy2":', '[]string{"vmess", "vless", "trojan"'],
        "yue-node native capability manifest",
    )
    forbid(config, ['case "xray", "hysteria", "hysteria2":'], "yue-node config")
    if any((root / "internal/machine").glob("*.go")):
        raise RuntimeError("retired dynamic machine orchestrator still exists")
    runtime_go = "\n".join(
        read(path)
        for path in root.rglob("*.go")
        if "vendor" not in path.parts and "gen" not in path.parts
    )
    forbid(
        runtime_go,
        ["ReportMachineStatus", "ListMachineNodes", "internal/machine"],
        "yue-node static runtime",
    )


def validate_yueops(
    root: Path, contract: dict, yueboard_contract_root: Path | None
) -> None:
    if yueboard_contract_root is None:
        raise RuntimeError(
            "YueOps validation requires the pinned YueBoard contract checkout"
        )
    pinned_floor = read(yueboard_contract_root / "schema-floor.txt").strip()
    if pinned_floor != str(contract["schema_floor"]):
        raise RuntimeError(
            "pinned YueBoard contract schema floor does not match central policy"
        )
    deploy = read(root / "yueops/deploy.py")
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
    widget = read(root / "checkin-api/static/chat-widget.js")
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

    require(
        deploy,
        [
            '"yue-node-1": ("hy2", True)',
            '"yue-node-2": ("vless", False)',
            f'expected_kernel = {{1: "{layout["node-1"]["kernel"]}", 2: "{layout["node-2"]["kernel"]}"}}',
            "kernel aliases and role swaps are retired",
            "panel.url must be a root YueBoard ConnectRPC base URL",
            'entrypoint: ["/usr/local/bin/yue-node-{role}"]',
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
            'expected_path = f"/usr/local/bin/yue-node-{role}"',
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
    require(
        ai_runtime,
        ['raise RuntimeError("yue_ai cursor provider is not configured")'],
        "Yue AI runtime dependency injection",
    )
    require(
        widget,
        [
            "function scParseDevices(response)",
            "var countFloor = Math.max(onlineRows, data.shared_online ? 1 : 0);",
            "IPs remain diagnostic and never become device rows",
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
    floor = read(root / "scripts/deploy-yueboard-panel.sh")
    require(
        floor,
        [f"MIN_SCHEMA_FLOOR={contract['schema_floor']}"],
        "YueOps YueBoard deployer",
    )


def validate_yueboard(root: Path, contract: dict) -> None:
    proto = read(root / "proto/yuenode/v1/yuenode.proto")
    connectrpc = read(root / "internal/modules/nodesync/connectrpc.go")
    builders = read(root / "internal/modules/nodesync/builders.go")
    routes = read(root / "internal/modules/nodesync/internal.go")
    capabilities = read(root / "internal/modules/nodesync/capabilities.go")
    rollout = read(root / "internal/modules/nodesync/yueops_internal_rollout.go")
    rollout_test = read(root / "test/integration/yueops_rollout_integration_test.go")
    presence_migration = read(
        root / "internal/platform/db/migrations/00045_node_presence_streams.sql"
    )
    composition = read(root / "cmd/yueboard/main.go")
    plugin_api = read(root / "internal/modules/pluginapi/pluginapi.go")
    user_handler = read(root / "internal/modules/user/handler.go")
    subscribe_runtime = read_package(
        root / "internal/modules/subscribe",
        "*.go",
        min_files=10,
        exclude_suffixes=("_test.go",),
    )
    device_identity_runtime = read_package(
        root / "internal/platform/deviceidentity",
        "*.go",
        min_files=2,
        exclude_suffixes=("_test.go",),
    )
    module_runtime = read_tree(
        root / "internal/modules",
        ("*.go",),
        min_files=100,
        exclude_suffixes=("_test.go",),
    )
    web_runtime = read_tree(
        root / "web/src",
        ("*.ts", "*.tsx"),
        min_files=50,
        exclude_suffixes=(".test.ts", ".test.tsx"),
    )
    handoff = read(root / "internal/modules/handoff/handoff.go")
    subscription_client = read(root / "web/src/lib/subscription-client.ts")
    subscription_client_test = read(
        root / "web/src/lib/subscription-client.test.ts"
    )
    retirement_migration_56 = read(
        root
        / "internal/platform/db/migrations/00056_drop_portal_handoff_enrollment_receipts.sql"
    )
    retirement_migration_57 = read(
        root
        / "internal/platform/db/migrations/00057_drop_retired_device_subscription_authorities.sql"
    )
    retirement_test = read(
        root / "internal/platform/db/migrations_00056_57_test.go"
    )
    migration = read(
        root
        / "internal/platform/db/migrations/00037_native_node_inventory_boundary.sql"
    )
    raw_floor = read(root / "schema-floor.txt").strip()
    presence = contract["presence"]
    if presence.get("rollout_order") != [
        "yueboard_control_plane_locked",
        "yue_node_fleet",
        "credential_consumers",
    ]:
        raise RuntimeError("native rollout order must bootstrap locked YueBoard first")
    if raw_floor != str(contract["schema_floor"]):
        raise RuntimeError(
            "YueBoard schema floor does not match the native-node contract"
        )
    identity = contract["device_identity"]
    if identity.get("portal_installation_authority") != "retired":
        raise RuntimeError("Portal installation authority must remain retired")
    if identity.get("synthetic_install_identity") != "retired":
        raise RuntimeError("synthetic install identity must remain retired")
    require(
        proto,
        [f"rpc {rpc_name(path)}(" for path in contract["control"]["static_node_rpcs"]]
        + [f"rpc {rpc_name(contract['control']['machine_status_rpc'])}("],
        "YueBoard ConnectRPC source",
    )
    forbid(
        proto,
        [f"rpc {rpc_name(path)}(" for path in contract["control"]["retired_rpcs"]]
        + [
            "bool auto_tls = 15;",
            "string domain = 16;",
            "string cipher = 17;",
            "string plugin = 18;",
            "string plugin_opts = 19;",
            "string server_key = 20;",
        ],
        "YueBoard ConnectRPC source",
    )
    require(proto, ["reserved 15 to 20;"], "YueBoard native NodeConfig")
    require(
        connectrpc,
        ["func (s *connectServer) ReportMachineStatus", "s.authMachine(ctx"],
        "YueBoard machine status handler",
    )
    require(
        connectrpc,
        [
            "func strictLegacyBasePresencePayload",
            "account user IDs with canonical IPs",
            "if wireID == 0",
            "func isLegacyPresenceRequest",
            "if isLegacyPresenceRequest(req.Msg)",
            "Any half-upgraded/malformed v2 shape is still rejected fail-closed",
        ],
        "YueBoard locked-bootstrap legacy node compatibility",
    )
    forbid(
        connectrpc,
        [
            "func (s *connectServer) ListMachineNodes",
            "func (s *connectServer) listMachineNodes",
            "func (s *connectServer) syncMachine",
        ],
        "YueBoard machine discovery boundary",
    )
    handshake = connectrpc.split("func (s *connectServer) Handshake", 1)[-1].split(
        "func (s *connectServer) GetConfig", 1
    )[0]
    require(handshake, ["s.authNode(ctx, auth)"], "YueBoard static Handshake")
    forbid(handshake, ["authMachine"], "YueBoard static Handshake")
    require(
        builders,
        ["validateNativeProtocolSettings(s.Type, s.Settings)"],
        "YueBoard native protocol loader",
    )
    route_suffix = presence["rollout_proof_endpoint"]
    if route_suffix.startswith("/api/v1"):
        route_suffix = route_suffix[len("/api/v1") :]
    require(
        routes,
        [f'r.Get("{route_suffix}", m.yueOpsNodeRollout)'],
        "YueBoard YueOps rollout route",
    )
    require(
        capabilities,
        [
            *[f'= "{capability}"' for capability in presence["required_capabilities"]],
            f"const nodeProcessFenceAfter = {presence['process_lease_seconds'] // 60} * time.Minute",
            "credential_capable=credential_capable AND",
            'fmt.Sprintf("legacy:%d:%d", serverID, machineID)',
            "applied_user_generation",
            "applied_device_generation",
        ],
        "YueBoard durable process capability fence",
    )
    require(
        rollout,
        [
            "m.yueOpsInternalGate(w, r)",
            'json:"process_instance_id"',
            'json:"lease_state"',
            'json:"desired_user_generation"',
            'json:"desired_device_generation"',
            'json:"applied_user_generation"',
            'json:"applied_device_generation"',
            'json:"generations_applied"',
            'leaseState = "active"',
            "nodeProcessFenceAfter",
        ],
        "YueBoard durable rollout proof",
    )
    # A subscription is account-scoped. Portal installation registration,
    # per-device /d authority and the later synthetic install-beacon identity
    # have all been retired; reintroducing any one of them must break the build.
    forbid(
        module_runtime + composition + device_identity_runtime,
        [
            "m.EnrollmentReady(r.Context())",
            "m.devices.Enroll(r.Context()",
            "pluginAPIMod.EnrollmentReady = nodeMod.CredentialEnrollmentReady",
            '"/user/devices/enroll"',
            '"/user/devices/revoke"',
            '"/d/{authority}"',
            'r.Get("/d/',
            'r.Post("/d/',
            'r.HandleFunc("/d/',
            "func (m *Module) deviceSubscribe(",
            "RecordInstallBeacon",
            "MintInstallToken",
            "TouchInstall",
            "MintInstall",
            "ReportedIdentitySQL",
            "install_token",
            '"/rp/{token}"',
        ],
        "YueBoard retired Portal-installation authority runtime",
    )
    forbid_paths(
        root,
        [
            "internal/modules/subscribe/install_beacon_inject.go",
            "internal/modules/subscribe/presence_beacon.go",
        ],
        "YueBoard retired Portal-installation authority runtime",
    )
    require(
        subscribe_runtime,
        [
            "m.serveSubscription(w, r, u, token, u.UUID)",
            "The subscription renders the account credential",
            "RegisterClientHWID RegisterClientHWIDFunc",
        ],
        "YueBoard account-scoped subscription delivery",
    )
    require(
        device_identity_runtime,
        [
            "Package deviceidentity owns client-declared hardware identities",
            "func (s *Service) RegisterHWID(",
            "func (s *Service) RegisterHWIDForUser(",
            "These records grant no access",
        ],
        "YueBoard native HWID-only identity runtime",
    )
    require(
        handoff,
        [
            "There is no",
            "Portal installation or device enrollment payload",
            "the result is the account subscription",
            "func (m *Module) claimSubscribeCode(",
        ],
        "YueBoard account-scoped handoff",
    )
    require(
        read(root / "internal/modules/nodesync/internal.go"),
        ['r.Post("/internal/yueops/users/subscription", m.yueOpsUserSubscription)'],
        "YueBoard YueOps subscription delegate",
    )
    require(
        presence_migration,
        [
            "CREATE TABLE IF NOT EXISTS public.node_presence_streams",
            "instance_id varchar(32) NOT NULL",
            "credential_capable boolean NOT NULL",
            "applied_user_generation text NOT NULL",
            "applied_device_generation text NOT NULL",
            "PRIMARY KEY (server_id, machine_id, instance_id)",
        ],
        "YueBoard durable presence migration",
    )
    require(
        rollout_test,
        [
            "X-Control-Token",
            'oldInstance = "66666666666666666666666666666666"',
            'newInstance = "77777777777777777777777777777777"',
            'process.LeaseState != "fenced"',
            'process.LeaseState != "active"',
            "GenerationsApplied",
        ],
        "YueBoard rollout proof integration test",
    )
    # The device list is now the observed-identity projection. It never
    # enumerated enrolled credential rows again after yueboard 9580485, so the
    # count is max(identities, network lines) -- adding them would double-count
    # the same machine, which is the inflation this whole surface removes.
    require(
        plugin_api,
        [
            'r.Get("/user/devices", m.paDevicesList)',
            'r.Post("/user/devices/reset-all", m.paDevicesResetAll)',
            '"shared_online":   sharedOnline',
            '"presence_source": presenceSource',
            '"identities":      identities,',
            "if networkLines > liveCount {",
            'presenceSource = "database_projection"',
            '"applied_user_ids":    []int64{uid}',
            "Network presence is the floor for clients that do not report an",
            "so the two are combined with max rather than added",
        ],
        "YueBoard public device identity API",
    )
    forbid(
        plugin_api,
        [
            '"devices":         devices,',
            "func paApplyProjectedDevicePresence(",
        ],
        "YueBoard retired enrolled-device projection",
    )
    require(
        user_handler,
        [
            'r.Get("/user/overview", m.getSubscriptionOverview)',
            "never places account token/uuid/subscribe_url on the browser wire",
        ],
        "YueBoard credential-free account overview",
    )
    # The Portal hands out the account subscription. What still matters here is
    # the client catalogue and the export boundary that validates a URL before
    # handing it to another application through a URI scheme.
    require(
        subscription_client,
        [
            "export function requireSubscriptionURL(",
            'parsed.protocol !== "https:"',
            'parsed.hash !== ""',
            '"clash"',
            '"stash"',
            '"hiddify"',
            '"sing-box"',
            '"surge"',
            '"loon"',
            '"v2rayn"',
            '"quantumult-x"',
        ],
        "YueBoard mainstream-client subscription import",
    )
    forbid(
        web_runtime,
        [
            "open-portal-on-target",
            "getOrCreatePortalDeviceID",
            '"/user/devices/enroll"',
        ],
        "YueBoard retired Portal installation and unsupported client catalogue",
    )
    forbid_casefold(
        web_runtime,
        ["shadowrocket", "小火箭"],
        "YueBoard unsupported client catalogue",
    )
    require(
        subscription_client_test,
        [
            "the export boundary rejects anything that could redirect the receiving app",
            "third-party one-click URI goldens carry the subscription URL unchanged",
            "the portal does not recommend clients without a proven managed profile",
            '"shadowrocket"',
            '"小火箭"',
        ],
        "YueBoard third-party import regression tests",
    )
    require(
        retirement_migration_56,
        [
            "yueops_lifecycle.assert_yueboard_retirement_gate",
            "current_setting('yueboard.retirement_nonce', true), 57, false",
            "DROP COLUMN IF EXISTS completed_device_id",
            "DROP COLUMN IF EXISTS completed_authority_digest",
            "irreversible: 00056 removed retired per-device handoff receipts",
        ],
        "YueBoard floor-56 Portal handoff retirement migration",
    )
    require(
        retirement_migration_57,
        [
            "yueops_lifecycle.assert_yueboard_retirement_gate",
            "current_setting('yueboard.retirement_nonce', true), 57, true",
            "refusing to retire %: % row(s) still exist",
            "DROP TABLE IF EXISTS public.device_subscription_targets",
            "DROP TABLE IF EXISTS public.user_devices",
            "DROP TABLE IF EXISTS public.node_billing_identities",
            "DELETE FROM public.device_identities WHERE kind = 'install'",
            "DROP COLUMN IF EXISTS install_token",
            "DROP COLUMN IF EXISTS kind",
            "ALTER COLUMN hwid SET NOT NULL",
            "CREATE UNIQUE INDEX IF NOT EXISTS device_identities_user_hwid_key",
            "irreversible: 00057 removed retired device subscription authorities",
        ],
        "YueBoard floor-57 Portal-installation authority retirement migration",
    )
    require(
        retirement_test,
        [
            "TestPortalAuthorityRetirementIsLifecycleGatedAndIrreversible",
            "TestFloor57DropsAuthoritiesButKeepsNativeHWIDIdentity",
            "TestRuntimeHasNoSyntheticInstallOrPerDeviceAuthoritySurface",
        ],
        "YueBoard floor-57 Portal retirement regression tests",
    )
    require(
        migration,
        [
            "type IN ('hysteria', 'vless')",
            "managed_by = 'yueops'",
            "migration 00037 is irreversible",
        ],
        "YueBoard native inventory migration",
    )


def validate_yuelink(root: Path, contract: dict) -> None:
    identity = contract["device_identity"]
    device_summary = read(root / "lib/domain/account/device_summary.dart")
    device_summary_test = read(root / "test/domain/account/device_summary_test.dart")
    subscription_reset = read(
        root / "lib/domain/account/subscription_reset_outcome.dart"
    )
    subscription_reset_test = read(
        root / "test/domain/account/subscription_reset_outcome_test.dart"
    )
    panel_api = read(root / "lib/infrastructure/datasources/panel/api.dart")
    repository = read(
        root / "lib/infrastructure/account/account_center_repository.dart"
    )
    provider = read(
        root / "lib/modules/account/providers/account_center_providers.dart"
    )

    # The panel takes the max of observed identities and network lines rather
    # than their sum: the same device is usually visible to both, so adding
    # them is the inflation this projection exists to prevent. The client must
    # accept that shape, and must still refuse a count below what it already
    # knows to be online.
    require(
        device_summary,
        [
            "final floor = onlineIdentities > (sharedOnline ? 1 : 0)",
            "if (count < floor) {",
            "Never infer devices from IP cardinality",
            "shared_online",
            "presence_source",
            "database_projection",
        ],
        "YueLink strict device identity projection",
    )
    forbid(
        device_summary,
        ["onlineDevices + (sharedOnline ? 1 : 0)"],
        "YueLink retired additive device count",
    )
    require(
        device_summary_test,
        [
            "five IP observations still represent only one identity",
            "unattributed presence is explicit even when IPs are empty",
            "an identity and a network line are one device, not two",
        ],
        "YueLink IP-inflation regression tests",
    )
    require(
        subscription_reset + subscription_reset_test,
        [
            identity["reset_identity_field"],
            "rawUserIds.length != 1",
            "jsonToInt(rawUserIds.single) != expectedUserId",
            "device reset response disclosed a secret",
            "no account or device authority is accepted on this boundary",
            "the account-wide reset parser remains the sole public outcome",
        ],
        "YueLink account subscription reset binding",
    )
    # The panel registers this route as GET. v1.2.111 shipped it as POST, which
    # fell through to the anti-GFW decoy (non-JSON) and broke every
    # subscription sync with "数据格式化异常". Pin the verb, not just the path.
    require(
        panel_api,
        [
            "getRawData(\n      '/api/v1/user/getSubscribe'",
        ],
        "YueLink account subscription verb",
    )
    forbid(
        panel_api,
        ["postRawData(\n      '/api/v1/user/getSubscribe'"],
        "YueLink retired account subscription verb",
    )
    require(
        panel_api,
        [
            identity["overview_endpoint"],
            "It deliberately never returns account `token`, `uuid`, or subscription",
            "The account subscription is fetched only at the import boundary",
        ],
        "YueLink credential-free account overview",
    )
    require(
        repository + provider,
        [
            "AccountCenterRepository(this._api, this._token, this._accountId)",
            "expectedUserId: _accountId",
            "accountId == null || accountId <= 0",
        ],
        "YueLink immutable account binding",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--kind", choices=("yue-node", "yueops", "yueboard", "yuelink"), required=True
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--yueboard-contract-source", type=Path)
    args = parser.parse_args()
    contract = json.loads(read(POLICY_ROOT / "native-node-contract.json"))
    source = args.source.resolve()
    try:
        if args.kind == "yue-node":
            if args.yueboard_contract_source is None:
                raise RuntimeError(
                    "yue-node validation requires the separately checked-out "
                    "YueBoard canonical source"
                )
            validate_canonical_proto_mirror(
                source, args.yueboard_contract_source.resolve()
            )
            validate_node(source, contract)
        elif args.kind == "yueops":
            contract_source = (
                args.yueboard_contract_source.resolve()
                if args.yueboard_contract_source is not None
                else None
            )
            validate_yueops(source, contract, contract_source)
        elif args.kind == "yueboard":
            validate_yueboard(source, contract)
        else:
            validate_yuelink(source, contract)
    except RuntimeError as exc:
        print(f"native node contract failed: {exc}", file=sys.stderr)
        return 1
    print(f"native node contract v{contract['version']} verified for {args.kind}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
