"""yue-node native contract validator."""

from __future__ import annotations

import sys
from pathlib import Path as _ConstantsPath
_CI_LIB = str(_ConstantsPath(__file__).resolve().parents[1] / "lib")
if _CI_LIB not in sys.path:
    sys.path.insert(0, _CI_LIB)
from ci_constants import NODE_CONFIG_MIN_FILES, NODE_CONTROLPLANE_MIN_FILES, NODE_HYSTERIA_MIN_FILES, NODE_HYSTERIA_TEST_MIN_FILES, NODE_IMAGE_BIN_COPY, NODE_MODEL_MIN_FILES, NODE_SERVICE_MIN_FILES, NODE_SERVICE_TEST_MIN_FILES, NODE_XRAY_MIN_FILES, NODE_XRAY_TEST_MIN_FILES

import re
from pathlib import Path

from .fragments import forbid, read, read_package, require, rpc_name


def _owned_make_targets(makefile: str, names: set[str]) -> tuple[dict[str, tuple[list[str], list[tuple[int, str]]]], set[str]]:
    """Parse the closed Make subset used by the owned yue-node test chain."""
    targets: dict[str, tuple[list[str], list[tuple[int, str]]]] = {}
    phony: set[str] = set()
    current = None
    depth = 0
    for raw in makefile.splitlines():
        if raw.startswith("\t"):
            if current is not None:
                targets[current][1].append((depth, raw[1:].strip()))
            continue
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if (re.match(r"(?:-?include|sinclude|define|override)\b", line)
                or re.search(r"\$[({]eval\s", line)
                or re.match(r"(?:export\s+)?(?:\.ONESHELL|\.RECIPEPREFIX|\.IGNORE|\.SHELLFLAGS|SHELL|MAKE|MAKEFLAGS|GNUMAKEFLAGS|MFLAGS|MAKEFILES)\s*[:?+!=]", line)):
            raise RuntimeError("yue-node Make test chain uses unsupported control syntax")
        if re.match(r"(?:ifeq|ifneq|ifdef|ifndef)\b", line):
            depth += 1
            continue
        if line == "else" or line.startswith("else "):
            if depth == 0:
                raise RuntimeError("yue-node Make test chain has unmatched conditional")
            continue
        if line == "endif":
            depth -= 1
            if depth < 0:
                raise RuntimeError("yue-node Make test chain has unmatched conditional")
            continue
        current = None
        match = re.fullmatch(r"([^:=]+):([^=].*|)", line)
        if match is None:
            continue
        lhs, rhs = match.groups()
        declared = lhs.split()
        if declared == [".PHONY"] and depth == 0:
            phony.update(rhs.split())
        selected = names.intersection(declared)
        if selected:
            if depth != 0 or len(declared) != 1 or selected.intersection(targets):
                raise RuntimeError("yue-node Make test chain has ambiguous or conditional target")
            current = declared[0]
            targets[current] = (rhs.split(), [])
    if depth != 0:
        raise RuntimeError("yue-node Make test chain has unmatched conditional")
    return targets, phony


def _require_owned_phony(targets, phony, name: str):
    if name not in targets or name not in phony:
        raise RuntimeError(f"yue-node Make test chain lacks owned phony target {name}")
    return targets[name]


def validate_node_test_chain(makefile: str) -> None:
    """Recognize the two reviewed Make test chains without executing Make.

    This is a closed subset for the owned declarations, not a general Make
    evaluator. Detached words/comments, conditional or ambiguous definitions
    cannot authorize the default test entry.
    """
    owned_checks = {
        "check-runtime-constants": [
            (0, 'python3 scripts/sync-host-paths.py --source "$(HOST_PATH_SOURCE)" --check'),
            (0, "python3 scripts/check-runtime-constants.py"),
        ],
        "test-owned-contracts": [(0, "python3 scripts/test_owned_contracts.py")],
    }
    names = {"test", "test-vendored", "verify-fork-tags", "fork-ledger-check", "check-profile-deps", *owned_checks}
    targets, phony = _owned_make_targets(makefile, names)

    def target(name: str) -> tuple[list[str], list[tuple[int, str]]]:
        return _require_owned_phony(targets, phony, name)

    for name, command in (("verify-fork-tags", "bash scripts/verify-fork-tags.sh"),
                          ("check-profile-deps", "sh scripts/check-profile-deps.sh")):
        if target(name) != ([], [(0, command)]):
            raise RuntimeError(f"yue-node Make test chain disconnects {name}")
    fork_ledger_recipe = [(0, "go run ./tools/forkledger --check --release tools/forkledger/release-excerpt.yaml")]
    dependencies, recipe = target("test")
    if dependencies in (["verify-fork-tags"], ["verify-fork-tags", "fork-ledger-check"]):
        if "fork-ledger-check" in dependencies and target("fork-ledger-check") != ([], fork_ledger_recipe):
            raise RuntimeError("yue-node Make test chain disconnects fork-ledger-check")
        if recipe != [(0, "$(MAKE) test-vendored")]:
            raise RuntimeError("yue-node Make test chain lacks required recursive delegation")
        dependencies, recipe = target("test-vendored")
        if owned_checks.keys() & targets.keys():
            if dependencies != ["check-profile-deps", *owned_checks]:
                raise RuntimeError("yue-node Make test chain disconnects owned prerequisites")
            for name, commands in owned_checks.items():
                if target(name) != ([], commands):
                    raise RuntimeError(f"yue-node Make test chain disconnects {name}")
        elif dependencies != ["check-profile-deps"]:
            raise RuntimeError("yue-node Make test chain lacks vendored profile prerequisite")
    elif owned_checks.keys() & targets.keys() or dependencies != ["verify-fork-tags", "check-profile-deps"]:
        raise RuntimeError("yue-node Make test chain lacks verification/profile prerequisites")
    expected = [(0, "bash scripts/test-check-vulnerabilities.sh")] + [
        (0, f'go test -race -count=1 -timeout $(TEST_TIMEOUT) -tags "$(TEST_COMMON_TAGS) yue_profile_{profile}" ./...')
        for profile in ("hy2", "vless")
    ]
    if recipe[:len(expected)] != expected:
        raise RuntimeError("yue-node Make test chain disconnects the required test body")



def _read_node_inputs(root: Path, contract: dict) -> dict[str, object]:
    dockerfile = read(root / "Dockerfile")
    makefile = read(root / "Makefile")
    launcher = read(root / "cmd/yue-node-launcher/main.go")
    dependency_gate = read(root / "scripts/check-profile-deps.sh")
    capability = read(root / "internal/capability/manifest.go")
    # 同 §上：主语是包不是文件。这两个包 2026-09-20 也各被拆成 5–8 个文件。
    config = read_package(
        root / "internal/config", "*.go", min_files=NODE_CONFIG_MIN_FILES, exclude_suffixes=("_test.go",)
    )
    controlplane = read_package(
        root / "internal/controlplane", "*.go", min_files=NODE_CONTROLPLANE_MIN_FILES, exclude_suffixes=("_test.go",)
    )
    proto = read(root / "proto/yuenode/v1/yuenode.proto")
    # The whole package, not one file — see read_package. yue-node's service
    # package is deliberately split by responsibility (service/state/sync/
    # transaction/users/kernel/reporting/observability/devices/validate).
    service = read_package(root / "internal/service", "*.go", min_files=NODE_SERVICE_MIN_FILES)
    service_test = read_package(root / "internal/service", "*_test.go", min_files=NODE_SERVICE_TEST_MIN_FILES)
    # 🚨 2026-09-20：下面四条此前是单文件 read()，而 read_package 的 docstring 里
    # 早就记着同一件事（上一次拆 internal/service/service.go 时这条守卫把
    # credential-generation 边界报成"缺失"）。那次的修法**只应用到了 service**，
    # 这四条没跟上 —— 于是 yue-node 把 dispatcher.go 拆成 dispatcher_{session,devices,
    # limits}.go、hysteria.go 拆成六个文件之后，`local∪global union` 与
    # `canonicalDeviceIP` 又一次被报成缺失（它们现在住在 dispatcher_devices.go /
    # dispatcher_session.go / device_limit.go / traffic_presence.go）。
    # 契约片段的主语是**包**，不是文件；地板负责让"扫到空气"不被当成通过。
    model_types = read_package(
        root / "internal/model", "*.go", min_files=NODE_MODEL_MIN_FILES, exclude_suffixes=("_test.go",)
    )
    xray_dispatcher = read_package(
        root / "internal/kernel/xray", "*.go", min_files=NODE_XRAY_MIN_FILES, exclude_suffixes=("_test.go",)
    )
    xray_test = read_package(root / "internal/kernel/xray", "*_test.go", min_files=NODE_XRAY_TEST_MIN_FILES)
    hysteria = read_package(
        root / "internal/kernel/hysteria", "*.go", min_files=NODE_HYSTERIA_MIN_FILES, exclude_suffixes=("_test.go",)
    )
    hysteria_test = read_package(
        root / "internal/kernel/hysteria", "*_test.go", min_files=NODE_HYSTERIA_TEST_MIN_FILES
    )
    artifacts = [slot["artifact"] for slot in contract["layout"].values()]
    presence = contract["presence"]
    return {
        "dockerfile": dockerfile,
        "makefile": makefile,
        "launcher": launcher,
        "dependency_gate": dependency_gate,
        "capability": capability,
        "config": config,
        "controlplane": controlplane,
        "proto": proto,
        "service": service,
        "service_test": service_test,
        "model_types": model_types,
        "xray_dispatcher": xray_dispatcher,
        "xray_test": xray_test,
        "hysteria": hysteria,
        "hysteria_test": hysteria_test,
        "artifacts": artifacts,
        "presence": presence,
    }


def _check_node_contract(root: Path, contract: dict, sources: dict[str, object]) -> None:
    dockerfile = sources["dockerfile"]
    makefile = sources["makefile"]
    launcher = sources["launcher"]
    dependency_gate = sources["dependency_gate"]
    capability = sources["capability"]
    config = sources["config"]
    controlplane = sources["controlplane"]
    proto = sources["proto"]
    service = sources["service"]
    service_test = sources["service_test"]
    model_types = sources["model_types"]
    xray_dispatcher = sources["xray_dispatcher"]
    xray_test = sources["xray_test"]
    hysteria = sources["hysteria"]
    hysteria_test = sources["hysteria_test"]
    artifacts = sources["artifacts"]
    presence = sources["presence"]
    presence = contract["presence"]
    require(
        dockerfile,
        [
            "ARG BUILD_PROFILE=auto",
            "-o yue-node-hy2 ./cmd/yue-node",
            "-o yue-node-vless ./cmd/yue-node",
            "-o yue-node ./cmd/yue-node-launcher",
            NODE_IMAGE_BIN_COPY,
        ],
        "yue-node Dockerfile",
    )
    require(makefile, ["VALID_BUILD_PROFILES := auto hy2 vless"], "yue-node Makefile")
    validate_node_test_chain(makefile)
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
    # Scan only yue-node's executable/runtime packages.  The central workflow
    # deliberately checks the YueBoard canonical tree out below ``root`` as
    # .ci-yueboard; a repository-wide rglob would then mistake panel RPC
    # handlers for node runtime code and fail on legitimate panel-only names.
    runtime_go = "\n".join(
        read(path)
        for source_dir in (root / "cmd", root / "internal")
        for path in source_dir.rglob("*.go")
    )
    forbid(
        runtime_go,
        ["ReportMachineStatus", "ListMachineNodes", "internal/machine"],
        "yue-node static runtime",
    )


def validate_node(root: Path, contract: dict) -> None:
    """Check one yue-node checkout against the central native contract."""
    sources = _read_node_inputs(root, contract)
    _check_node_contract(root, contract, sources)
