"""YueBoard native contract validator."""

from __future__ import annotations

import sys
from pathlib import Path as _ConstantsPath
_CI_LIB = str(_ConstantsPath(__file__).resolve().parents[1] / "lib")
if _CI_LIB not in sys.path:
    sys.path.insert(0, _CI_LIB)
from ci_constants import BOARD_DEVICE_IDENTITY_MIN_FILES, BOARD_MODULE_MIN_FILES, BOARD_NODESYNC_MIN_FILES, BOARD_SUBSCRIBE_MIN_FILES, BOARD_WEB_MIN_FILES

from pathlib import Path

from .fragments import (
    forbid,
    forbid_paths,
    read,
    read_package,
    read_tree,
    require,
    rpc_name,
    validate_managed_subscription_catalogue,
)


def _read_yueboard_inputs(root: Path) -> dict[str, object]:
    proto = read(root / "proto/yuenode/v1/yuenode.proto")
    # 2026-09-20：connectrpc.go 与 builders.go 各被拆成 4–5 个同包文件。
    # 两者都改读整个 nodesync 包（下面的 require/forbid 原本就是对
    # connectrpc+builders 的并集做的，并集换成整包只会更严，不会更松）。
    nodesync_pkg = read_package(
        root / "internal/modules/nodesync", "*.go", min_files=BOARD_NODESYNC_MIN_FILES,
        exclude_suffixes=("_test.go",),
    )
    connectrpc = nodesync_pkg
    builders = nodesync_pkg
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
        min_files=BOARD_SUBSCRIBE_MIN_FILES,
        exclude_suffixes=("_test.go",),
    )
    device_identity_runtime = read_package(
        root / "internal/platform/deviceidentity",
        "*.go",
        min_files=BOARD_DEVICE_IDENTITY_MIN_FILES,
        exclude_suffixes=("_test.go",),
    )
    module_runtime = read_tree(
        root / "internal/modules",
        ("*.go",),
        min_files=BOARD_MODULE_MIN_FILES,
        exclude_suffixes=("_test.go",),
    )
    web_runtime = read_tree(
        root / "web/src",
        ("*.ts", "*.tsx"),
        min_files=BOARD_WEB_MIN_FILES,
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
    return {
        "proto": proto,
        "nodesync_pkg": nodesync_pkg,
        "connectrpc": connectrpc,
        "builders": builders,
        "routes": routes,
        "capabilities": capabilities,
        "rollout": rollout,
        "rollout_test": rollout_test,
        "presence_migration": presence_migration,
        "composition": composition,
        "plugin_api": plugin_api,
        "user_handler": user_handler,
        "subscribe_runtime": subscribe_runtime,
        "device_identity_runtime": device_identity_runtime,
        "module_runtime": module_runtime,
        "web_runtime": web_runtime,
        "handoff": handoff,
        "subscription_client": subscription_client,
        "subscription_client_test": subscription_client_test,
        "retirement_migration_56": retirement_migration_56,
        "retirement_migration_57": retirement_migration_57,
        "retirement_test": retirement_test,
        "migration": migration,
        "raw_floor": raw_floor,
    }


def _validate_yueboard_proto(contract: dict, sources: dict[str, object]) -> None:
    proto = sources["proto"]
    connectrpc = sources["connectrpc"]
    builders = sources["builders"]
    routes = sources["routes"]
    raw_floor = sources["raw_floor"]
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


def _validate_yueboard_rollout(root: Path, contract: dict, sources: dict[str, object]) -> None:
    capabilities = sources["capabilities"]
    rollout = sources["rollout"]
    rollout_test = sources["rollout_test"]
    presence_migration = sources["presence_migration"]
    composition = sources["composition"]
    subscribe_runtime = sources["subscribe_runtime"]
    device_identity_runtime = sources["device_identity_runtime"]
    module_runtime = sources["module_runtime"]
    handoff = sources["handoff"]
    presence = contract["presence"]
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


def _validate_yueboard_accounts(root: Path, sources: dict[str, object]) -> None:
    plugin_api = sources["plugin_api"]
    user_handler = sources["user_handler"]
    web_runtime = sources["web_runtime"]
    subscription_client = sources["subscription_client"]
    subscription_client_test = sources["subscription_client_test"]
    # The device list is now the observed-identity projection. It never
    # enumerated enrolled credential rows again after yueboard 9580485, so the
    # count is max(identities, network lines) -- adding them would double-count
    # the same machine, which is the inflation this whole surface removes.
    require(
        plugin_api,
        [
            'r.Get("/user/devices", m.paDevicesList)',
            'r.Post("/user/devices/reset-all", m.paDevicesResetAll)',
            '"shared_online":  sharedOnline',
            '"presence_source": presenceSource',
            '"identities":     identities,',
            '"confidence":     result.Confidence,',
            "result = m.DeviceCount(uid, fallback)",
            'presenceSource = "database_projection"',
            '"applied_user_ids":    []int64{uid}',
        ],
        "YueBoard public device identity API",
    )
    # 2026-09-23: the count is the single authoritative devicecount result
    # shared by /user/devices, users.online_count and the yueops internal
    # counts endpoint; the max-rather-than-add invariant now lives there.
    # 2026-10-10: tagged devices are now ADDED to the untagged identities
    # (a tag and an address are different devices; max dropped real devices).
    # The dual-stack invariant is unchanged: v4/v6 and HWID-vs-network stay max.
    require(
        read(root / "internal/platform/devicecount/devicecount.go"),
        [
            "dual stack combined with max",
            "(never added — one dual-stack device is observed on both families).",
            "untagged := max(int64(len(online)), network)",
            "result.Count = int64(len(tags)) + untagged",
            "count := max(v4, v6)",
        ],
        "YueBoard authoritative device count",
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
    # The export must reject URL fragments; either spelling is equivalent
    # (rawURL.includes("#") also rejects an empty trailing "#").
    if 'parsed.hash !== ""' not in subscription_client and 'rawURL.includes("#")' not in subscription_client:
        raise RuntimeError(
            "YueBoard mainstream-client subscription import is missing a URL fragment guard"
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
    # 2026-09-24: Shadowrocket must not enter the managed-profile catalogue.
    # 2026-11-23: the owner approved Shadowrocket/Quantumult X one-click node
    # subscription import (yueboard #291), so shadowrocket:// is no longer a
    # retired fragment; the export still has to pass requireSubscriptionURL.
    validate_managed_subscription_catalogue(subscription_client)
    require(
        subscription_client,
        ["export function shadowrocketSubscriptionURL(", "new URL(requireSubscriptionURL(rawURL))"],
        "YueBoard validated manual node-list exports",
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


def _validate_yueboard_retirement(sources: dict[str, object]) -> None:
    retirement_migration_56 = sources["retirement_migration_56"]
    retirement_migration_57 = sources["retirement_migration_57"]
    retirement_test = sources["retirement_test"]
    migration = sources["migration"]
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


def validate_yueboard(root: Path, contract: dict) -> None:
    """Check one YueBoard checkout against the central native contract."""
    sources = _read_yueboard_inputs(root)
    _validate_yueboard_proto(contract, sources)
    _validate_yueboard_rollout(root, contract, sources)
    _validate_yueboard_accounts(root, sources)
    _validate_yueboard_retirement(sources)
