#!/usr/bin/env python3
"""Validate each source repository against the central native-node ABI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


POLICY_ROOT = Path(__file__).resolve().parents[1]


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"required contract file is unavailable: {path}") from exc


def require(text: str, fragments: list[str], source: str) -> None:
    missing = [fragment for fragment in fragments if fragment not in text]
    if missing:
        raise RuntimeError(
            f"{source} is missing native contract fragments: {missing!r}"
        )


def forbid(text: str, fragments: list[str], source: str) -> None:
    present = [fragment for fragment in fragments if fragment in text]
    if present:
        raise RuntimeError(
            f"{source} contains retired contract fragments: {present!r}"
        )


def rpc_name(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def validate_node(root: Path, contract: dict) -> None:
    dockerfile = read(root / "Dockerfile")
    makefile = read(root / "Makefile")
    launcher = read(root / "cmd/yue-node-launcher/main.go")
    dependency_gate = read(root / "scripts/check-profile-deps.sh")
    capability = read(root / "internal/capability/manifest.go")
    config = read(root / "internal/config/config.go")
    proto = read(root / "proto/yuenode/v1/yuenode.proto")
    artifacts = [slot["artifact"] for slot in contract["layout"].values()]

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
            'case capability.KernelHysteria:',
            'case capability.KernelXray:',
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
        ["ReportMachineStatus", "ListMachineNodes", 'internal/machine'],
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
    watchdog = read(
        root
        / "scripts/yueops-tuning/files/usr/local/sbin/node-watchdog.sh"
    )
    migrator = read(root / "scripts/node-control-auth-migrate.py")
    self_heal = read(root / "scripts/yueops-self-heal.py")
    digest_deployer = read(root / "scripts/deploy-yueops-digests.sh")
    telemetry_ingest = read(root / "checkin-api/telemetry/ingest.py")
    telemetry_dashboard = read(root / "checkin-api/telemetry/dashboard.py")
    ai_runtime = read(root / "telegram-bot/yue/yue_ai_runtime.py")
    layout = contract["layout"]
    control = contract["control"]

    require(
        deploy,
        [
            f'"yue-node-1": ("hy2", True)',
            f'"yue-node-2": ("vless", False)',
            f'expected_kernel = {{1: "{layout["node-1"]["kernel"]}", 2: "{layout["node-2"]["kernel"]}"}}',
            "kernel aliases and role swaps are retired",
            "panel.url must be a root YueBoard ConnectRPC base URL",
            'entrypoint: [\"/usr/local/bin/yue-node-{role}\"]',
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
    if (root / "scripts/rollout-image-upgrade.sh").exists():
        raise RuntimeError("retired image rollout compatibility entrypoint still exists")
    require(
        deploy,
        ["native_healthy", "/readyz", 'expected_path = f"/usr/local/bin/yue-node-{role}"'],
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
        ["_normalize_native_server_id", "_aggregate_legacy_urltest_rows", "def stats_node_health"],
        "YueLink native telemetry runtime",
    )
    require(
        ai_runtime,
        ['raise RuntimeError("yue_ai cursor provider is not configured")'],
        "Yue AI runtime dependency injection",
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
    migration = read(
        root
        / "internal/platform/db/migrations/00037_native_node_inventory_boundary.sql"
    )
    raw_floor = read(root / "schema-floor.txt").strip()
    if raw_floor != str(contract["schema_floor"]):
        raise RuntimeError(
            "YueBoard schema floor does not match the native-node contract"
        )
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
    forbid(
        connectrpc,
        [
            "func (s *connectServer) ListMachineNodes",
            "func (s *connectServer) listMachineNodes",
            "func (s *connectServer) syncMachine",
        ],
        "YueBoard machine discovery boundary",
    )
    handshake = connectrpc.split(
        "func (s *connectServer) Handshake", 1
    )[-1].split("func (s *connectServer) GetConfig", 1)[0]
    require(handshake, ["s.authNode(ctx, auth)"], "YueBoard static Handshake")
    forbid(handshake, ["authMachine"], "YueBoard static Handshake")
    require(
        builders,
        ["validateNativeProtocolSettings(s.Type, s.Settings)"],
        "YueBoard native protocol loader",
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--kind", choices=("yue-node", "yueops", "yueboard"), required=True
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--yueboard-contract-source", type=Path)
    args = parser.parse_args()
    contract = json.loads(read(POLICY_ROOT / "native-node-contract.json"))
    source = args.source.resolve()
    try:
        if args.kind == "yue-node":
            validate_node(source, contract)
        elif args.kind == "yueops":
            contract_source = (
                args.yueboard_contract_source.resolve()
                if args.yueboard_contract_source is not None
                else None
            )
            validate_yueops(source, contract, contract_source)
        else:
            validate_yueboard(source, contract)
    except RuntimeError as exc:
        print(f"native node contract failed: {exc}", file=sys.stderr)
        return 1
    print(f"native node contract v{contract['version']} verified for {args.kind}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
