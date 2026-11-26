"""Pinned clients, protocols, and TEST-NET addresses for the interop matrix.

Asset digests are the GitHub release asset digests for those exact tags.
The mihomo fork pin is the reviewed fork head the client ledger records.
"""

from __future__ import annotations

from dataclasses import dataclass

LISTEN_HOST = "192.0.2.10"
PROBE_HOST = "203.0.113.10"
REALITY_DEST_HOST = "192.0.2.1"
SERVER_NAME = "example.com"
PROBE_PORT = 18080
PROBE_PATH = "/ready"
PROBE_BODY = "ok"
LOCAL_SOCKS_HOST = "127.0.0.1"
LOCAL_SOCKS_PORT = 17890
HOP_PORT_FIRST = 20000
HOP_PORT_LAST = 20007
HOP_INTERVAL_SECONDS = 30
XHTTP_PATH = "/matrix"
XHTTP_MODE = "auto"
REALITY_FLOW = "xtls-rprx-vision"
KEY_SHARE_HYBRID = "X25519MLKEM768"
KEY_SHARE_CLASSICAL = "X25519"
XRAY_FINGERPRINT_HYBRID = "hellochrome_155"
XRAY_FINGERPRINT_CLASSICAL = "hellochrome_120"
SING_BOX_FINGERPRINT = "chrome"
NFT_TABLE = "yueto_matrix"
READY_TIMEOUT_SECONDS = 20
DIAL_TIMEOUT_SECONDS = 15
REF_LENGTH = 40

HY2_SALAMANDER_PORT = 2443
HY2_GECKO_PORT = 2444
HY2_HOP_PORT = 2445
REALITY_PORT = 2446
XHTTP_PORT = 2448

NODE_PROFILE_HY2 = "hy2"
NODE_PROFILE_VLESS = "vless"
NODE_KERNEL_HY2 = "hysteria"
NODE_KERNEL_VLESS = "xray"
PROTOCOL_HYSTERIA2 = "hysteria2"
PROTOCOL_VLESS = "vless"
OBFS_SALAMANDER = "salamander"
OBFS_GECKO = "gecko"
NETWORK_TCP = "tcp"
NETWORK_XHTTP = "xhttp"
TLS_ON = 1
TLS_REALITY = 2
INSTANCE_ID = "matrix"
CERT_MODE_SELF = "self"
HEALTH_PORT_DISABLED = 0

PROTOCOL_HY2_SALAMANDER = "hy2-salamander"
PROTOCOL_HY2_GECKO = "hy2-gecko"
PROTOCOL_HY2_PORT_HOP = "hy2-port-hop"
PROTOCOL_REALITY_HYBRID = "vless-reality-hybrid"
PROTOCOL_REALITY_CLASSICAL = "vless-reality-classical"
PROTOCOL_XHTTP = "xhttp"

PROTOCOLS = (
    PROTOCOL_HY2_SALAMANDER,
    PROTOCOL_HY2_GECKO,
    PROTOCOL_HY2_PORT_HOP,
    PROTOCOL_REALITY_HYBRID,
    PROTOCOL_REALITY_CLASSICAL,
    PROTOCOL_XHTTP,
)

STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class ClientPin:
    client_id: str
    version: str
    repository: str
    commit: str
    asset: str
    sha256: str
    archive: str
    binary_name: str
    speaks_hy2: bool
    speaks_reality: bool
    speaks_xhttp: bool

    @property
    def source_built(self) -> bool:
        return self.archive == "source"

    @property
    def download_url(self) -> str:
        if self.source_built:
            return ""
        return (
            f"https://github.com/{self.repository}/releases/download/"
            f"{self.version}/{self.asset}"
        )


CLIENTS = (
    ClientPin(
        client_id="sing-box",
        version="v1.14.4",
        repository="SagerNet/sing-box",
        commit="c005f35300ce76427dc285481ec5695f5b179cd2",
        asset="sing-box-1.14.4-linux-amd64.tar.gz",
        sha256="699a1b510aa4396b2176d32d1181920399ebf1e267835da6f3b598d0f7c24968",
        archive="tar.gz",
        binary_name="sing-box",
        speaks_hy2=True,
        speaks_reality=True,
        speaks_xhttp=False,
    ),
    ClientPin(
        client_id="mihomo",
        version="v1.19.34",
        repository="MetaCubeX/mihomo",
        commit="0455d0d28c4526937380505153e65a843d8612e8",
        asset="mihomo-linux-amd64-v1.19.34.gz",
        sha256="223fab877e5795ce780ba39902e5f0b1113c1256ae244a7160f1165e017e9ccc",
        archive="gz",
        binary_name="mihomo",
        speaks_hy2=True,
        speaks_reality=True,
        speaks_xhttp=True,
    ),
    ClientPin(
        client_id="xray",
        version="v26.11.9",
        repository="XTLS/Xray-core",
        commit="676eaf66f8f05d4d558ee7a74b4736623d3feeb9",
        asset="Xray-linux-64.zip",
        sha256="b651f7e1d9966ee2c1b1ee1bf8b52c72771824d3065dce96bbc8bcc19ed95f82",
        archive="zip",
        binary_name="xray",
        speaks_hy2=False,
        speaks_reality=True,
        speaks_xhttp=True,
    ),
    ClientPin(
        client_id="yue-mihomo",
        version="b6ea58108a90e4c710cc431d5a3a4f376284302f",
        repository="onesyue/mihomo",
        commit="b6ea58108a90e4c710cc431d5a3a4f376284302f",
        asset="",
        sha256="",
        archive="source",
        binary_name="yue-mihomo",
        speaks_hy2=True,
        speaks_reality=True,
        speaks_xhttp=True,
    ),
)

CLIENTS_BY_ID = {pin.client_id: pin for pin in CLIENTS}


def is_commit_ref(value: str) -> bool:
    if len(value) != REF_LENGTH:
        return False
    return all(character in "0123456789abcdef" for character in value)


def client_speaks(pin: ClientPin, protocol: str) -> bool:
    if protocol in {PROTOCOL_HY2_SALAMANDER, PROTOCOL_HY2_GECKO, PROTOCOL_HY2_PORT_HOP}:
        return pin.speaks_hy2
    if protocol in {PROTOCOL_REALITY_HYBRID, PROTOCOL_REALITY_CLASSICAL}:
        return pin.speaks_reality
    if protocol == PROTOCOL_XHTTP:
        return pin.speaks_xhttp
    return False


def listen_endpoint(protocol: str) -> tuple[str, int, str]:
    """Return listen host, port, and socket kind for one matrix protocol."""

    if protocol == PROTOCOL_HY2_SALAMANDER:
        return LISTEN_HOST, HY2_SALAMANDER_PORT, "udp"
    if protocol == PROTOCOL_HY2_GECKO:
        return LISTEN_HOST, HY2_GECKO_PORT, "udp"
    if protocol == PROTOCOL_HY2_PORT_HOP:
        return LISTEN_HOST, HY2_HOP_PORT, "udp"
    if protocol in {PROTOCOL_REALITY_HYBRID, PROTOCOL_REALITY_CLASSICAL}:
        return LISTEN_HOST, REALITY_PORT, "tcp"
    if protocol == PROTOCOL_XHTTP:
        return LISTEN_HOST, XHTTP_PORT, "tcp"
    raise KeyError(protocol)


def node_profile(protocol: str) -> str:
    if protocol in {PROTOCOL_HY2_SALAMANDER, PROTOCOL_HY2_GECKO, PROTOCOL_HY2_PORT_HOP}:
        return NODE_PROFILE_HY2
    return NODE_PROFILE_VLESS


def node_group(protocol: str) -> str:
    if protocol in {PROTOCOL_REALITY_HYBRID, PROTOCOL_REALITY_CLASSICAL}:
        return "vless-reality"
    return protocol


def address_commands() -> tuple[tuple[str, ...], ...]:
    return (
        ("ip", "addr", "replace", f"{LISTEN_HOST}/32", "dev", "lo"),
        ("ip", "addr", "replace", f"{PROBE_HOST}/32", "dev", "lo"),
    )


def hop_commands(listen_port: int) -> tuple[tuple[str, ...], ...]:
    port_range = f"{HOP_PORT_FIRST}-{HOP_PORT_LAST}"
    return (
        ("nft", "delete", "table", "ip", NFT_TABLE),
        ("nft", "add", "table", "ip", NFT_TABLE),
        (
            "nft",
            "add",
            "chain",
            "ip",
            NFT_TABLE,
            "output",
            "{",
            "type",
            "nat",
            "hook",
            "output",
            "priority",
            "dstnat",
            ";",
            "}",
        ),
        (
            "nft",
            "add",
            "rule",
            "ip",
            NFT_TABLE,
            "output",
            "ip",
            "daddr",
            LISTEN_HOST,
            "udp",
            "dport",
            port_range,
            "redirect",
            "to",
            f":{listen_port}",
        ),
    )


def client_argv(binary: str, client_id: str, config_path: str) -> tuple[str, ...]:
    if client_id == "sing-box":
        return (binary, "run", "-c", config_path)
    if client_id in {"mihomo", "yue-mihomo"}:
        return (binary, "-f", config_path)
    if client_id == "xray":
        return (binary, "run", "-c", config_path)
    raise KeyError(client_id)


def node_argv(binary: str, config_path: str) -> tuple[str, ...]:
    return (binary, "-c", config_path)
