"""Hand-written yue-node and client configs. No panel URL and no second transport name."""

from __future__ import annotations

import json
import re

from client_matrix.catalog import (
    CLIENTS_BY_ID,
    HOP_INTERVAL_SECONDS,
    HOP_PORT_FIRST,
    HOP_PORT_LAST,
    KEY_SHARE_CLASSICAL,
    KEY_SHARE_HYBRID,
    LISTEN_HOST,
    LOCAL_SOCKS_HOST,
    LOCAL_SOCKS_PORT,
    NETWORK_TCP,
    NETWORK_XHTTP,
    NODE_KERNEL_HY2,
    NODE_KERNEL_VLESS,
    NODE_PROFILE_HY2,
    OBFS_GECKO,
    OBFS_SALAMANDER,
    PROTOCOL_HY2_GECKO,
    PROTOCOL_HY2_PORT_HOP,
    PROTOCOL_HY2_SALAMANDER,
    PROTOCOL_HYSTERIA2,
    PROTOCOL_REALITY_HYBRID,
    PROTOCOL_VLESS,
    PROTOCOL_XHTTP,
    REALITY_DEST_HOST,
    REALITY_FLOW,
    SERVER_NAME,
    SING_BOX_FINGERPRINT,
    TLS_ON,
    TLS_REALITY,
    XHTTP_MODE,
    XHTTP_PATH,
    XRAY_FINGERPRINT_CLASSICAL,
    XRAY_FINGERPRINT_HYBRID,
    client_speaks,
    listen_endpoint,
    node_profile,
)
from client_matrix.material import Material, validate_material

_PATH = re.compile(r"^[A-Za-z0-9_./:@-]{1,200}$")


def render_node(protocol: str, material: Material, config_dir: str) -> str:
    validate_material(material)
    if _PATH.fullmatch(config_dir) is None:
        raise ValueError("config dir is not a plain path")
    kernel = NODE_KERNEL_HY2 if node_profile(protocol) == NODE_PROFILE_HY2 else NODE_KERNEL_VLESS
    _host, port, _kind = listen_endpoint(protocol)
    return (
        "instances:\n"
        "  - id: \"matrix\"\n"
        "    kernel:\n"
        f"      type: {_q(kernel)}\n"
        f"      config_dir: {_q(config_dir)}\n"
        "      log_level: \"warn\"\n"
        "    cert:\n"
        "      cert_mode: \"self\"\n"
        f"      domain: {_q(SERVER_NAME)}\n"
        "    log:\n"
        "      level: \"info\"\n"
        "      output: \"stdout\"\n"
        "    health_port: 0\n"
        "    standalone:\n"
        "      enabled: true\n"
        "      node:\n"
        f"{_node_fields(protocol, material, port)}"
        "      users:\n"
        "        - id: 1\n"
        f"          uuid: {_q(material.user_uuid)}\n"
    )


def render_client(client_id: str, protocol: str, material: Material) -> tuple[str | None, str]:
    pin = CLIENTS_BY_ID[client_id]
    validate_material(material)
    if not client_speaks(pin, protocol):
        return None, f"{client_id} does not speak {protocol}"
    if client_id == "sing-box":
        return json.dumps(_sing_box(protocol, material), indent=2) + "\n", ""
    if client_id in {"mihomo", "yue-mihomo"}:
        return _mihomo(protocol, material), ""
    if client_id == "xray":
        return json.dumps(_xray(protocol, material), indent=2) + "\n", ""
    raise KeyError(client_id)


def config_suffix(client_id: str) -> str:
    if client_id in {"mihomo", "yue-mihomo"}:
        return ".yaml"
    return ".json"


def _node_fields(protocol: str, material: Material, port: int) -> str:
    lines = [
        f"        protocol: {_q(_wire_protocol(protocol))}",
        f"        listen_ip: {_q(LISTEN_HOST)}",
        f"        server_port: {port}",
    ]
    if node_profile(protocol) == NODE_PROFILE_HY2:
        lines.append(f"        obfs: {_q(_obfs(protocol))}")
        lines.append(f"        obfs_password: {_q(material.obfs_password)}")
    elif protocol == PROTOCOL_XHTTP:
        lines.extend(_xhttp_fields())
    else:
        lines.extend(_reality_fields(material))
    return "\n".join(lines) + "\n"


def _xhttp_fields() -> list[str]:
    return [
        f"        network: {_q(NETWORK_XHTTP)}",
        f"        tls: {TLS_ON}",
        "        network_settings:",
        f"          path: {_q(XHTTP_PATH)}",
        f"          host: {_q(SERVER_NAME)}",
        f"          mode: {_q(XHTTP_MODE)}",
    ]


def _reality_fields(material: Material) -> list[str]:
    return [
        f"        network: {_q(NETWORK_TCP)}",
        f"        tls: {TLS_REALITY}",
        f"        flow: {_q(REALITY_FLOW)}",
        f"        server_name: {_q(SERVER_NAME)}",
        "        tls_settings:",
        f"          private_key: {_q(material.reality_private_key)}",
        f"          server_name: {_q(SERVER_NAME)}",
        f"          short_id: {_q(material.short_id)}",
        f"          dest: {_q(f'{REALITY_DEST_HOST}:443')}",
    ]


def _sing_box(protocol: str, material: Material) -> dict:
    return {
        "log": {"level": "warn"},
        "inbounds": [_sing_box_socks()],
        "outbounds": [_sing_box_outbound(protocol, material)],
        "route": {"final": "proxy"},
    }


def _sing_box_socks() -> dict:
    return {
        "type": "socks",
        "tag": "socks-in",
        "listen": LOCAL_SOCKS_HOST,
        "listen_port": LOCAL_SOCKS_PORT,
    }


def _sing_box_outbound(protocol: str, material: Material) -> dict:
    if node_profile(protocol) == NODE_PROFILE_HY2:
        return _sing_box_hy2(protocol, material)
    return _sing_box_reality(protocol, material)


def _sing_box_hy2(protocol: str, material: Material) -> dict:
    _host, port, _kind = listen_endpoint(protocol)
    outbound = {
        "type": "hysteria2",
        "tag": "proxy",
        "server": LISTEN_HOST,
        "password": material.user_uuid,
        "obfs": {"type": _obfs(protocol), "password": material.obfs_password},
        "tls": {"enabled": True, "server_name": SERVER_NAME, "insecure": True},
    }
    if protocol == PROTOCOL_HY2_PORT_HOP:
        outbound["server_ports"] = [f"{HOP_PORT_FIRST}:{HOP_PORT_LAST}"]
        outbound["hop_interval"] = f"{HOP_INTERVAL_SECONDS}s"
    else:
        outbound["server_port"] = port
    return outbound


def _sing_box_reality(protocol: str, material: Material) -> dict:
    _host, port, _kind = listen_endpoint(protocol)
    curve = KEY_SHARE_HYBRID if protocol == PROTOCOL_REALITY_HYBRID else KEY_SHARE_CLASSICAL
    return {
        "type": "vless",
        "tag": "proxy",
        "server": LISTEN_HOST,
        "server_port": port,
        "uuid": material.user_uuid,
        "flow": REALITY_FLOW,
        "tls": {
            "enabled": True,
            "server_name": SERVER_NAME,
            "utls": {"enabled": True, "fingerprint": SING_BOX_FINGERPRINT},
            "reality": {
                "enabled": True,
                "public_key": material.reality_public_key,
                "short_id": material.short_id,
            },
            "curve_preferences": [curve],
        },
    }


def _mihomo(protocol: str, material: Material) -> str:
    _host, port, _kind = listen_endpoint(protocol)
    lines = [
        f"socks-port: {LOCAL_SOCKS_PORT}",
        f"bind-address: {_q(LOCAL_SOCKS_HOST)}",
        "allow-lan: false",
        "mode: rule",
        "log-level: warning",
        "proxies:",
        "  - name: matrix",
    ]
    if node_profile(protocol) == NODE_PROFILE_HY2:
        lines.extend(_mihomo_hy2(protocol, material, port))
    else:
        lines.extend(_mihomo_vless(protocol, material, port))
    lines.append("rules:")
    lines.append("  - MATCH,matrix")
    return "\n".join(lines) + "\n"


def _mihomo_hy2(protocol: str, material: Material, port: int) -> list[str]:
    lines = [
        "    type: hysteria2",
        f"    server: {_q(LISTEN_HOST)}",
        f"    port: {port}",
        f"    password: {_q(material.user_uuid)}",
        f"    obfs: {_q(_obfs(protocol))}",
        f"    obfs-password: {_q(material.obfs_password)}",
        f"    sni: {_q(SERVER_NAME)}",
        "    skip-cert-verify: true",
    ]
    if protocol == PROTOCOL_HY2_PORT_HOP:
        lines.append(f"    ports: {_q(f'{HOP_PORT_FIRST}-{HOP_PORT_LAST}')}")
        lines.append(f"    hop-interval: {HOP_INTERVAL_SECONDS}")
    return lines


def _mihomo_vless(protocol: str, material: Material, port: int) -> list[str]:
    lines = [
        "    type: vless",
        f"    server: {_q(LISTEN_HOST)}",
        f"    port: {port}",
        f"    uuid: {_q(material.user_uuid)}",
        "    udp: true",
        "    tls: true",
        f"    servername: {_q(SERVER_NAME)}",
        "    client-fingerprint: chrome",
    ]
    if protocol == PROTOCOL_XHTTP:
        lines.extend(
            [
                f"    network: {_q(NETWORK_XHTTP)}",
                "    skip-cert-verify: true",
                "    xhttp-opts:",
                f"      path: {_q(XHTTP_PATH)}",
                f"      host: {_q(SERVER_NAME)}",
                f"      mode: {_q(XHTTP_MODE)}",
            ]
        )
        return lines
    hybrid = "true" if protocol == PROTOCOL_REALITY_HYBRID else "false"
    lines.extend(
        [
            f"    network: {_q(NETWORK_TCP)}",
            f"    flow: {_q(REALITY_FLOW)}",
            "    reality-opts:",
            f"      public-key: {_q(material.reality_public_key)}",
            f"      short-id: {_q(material.short_id)}",
            f"      support-x25519mlkem768: {hybrid}",
        ]
    )
    return lines


def _xray(protocol: str, material: Material) -> dict:
    _host, port, _kind = listen_endpoint(protocol)
    user: dict[str, str] = {"id": material.user_uuid, "encryption": "none"}
    if protocol != PROTOCOL_XHTTP:
        user["flow"] = REALITY_FLOW
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "listen": LOCAL_SOCKS_HOST,
                "port": LOCAL_SOCKS_PORT,
                "protocol": "socks",
                "settings": {"udp": True},
            }
        ],
        "outbounds": [
            {
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": LISTEN_HOST,
                            "port": port,
                            "users": [user],
                        }
                    ]
                },
                "streamSettings": _xray_stream(protocol, material),
            }
        ],
    }


def _xray_stream(protocol: str, material: Material) -> dict:
    if protocol == PROTOCOL_XHTTP:
        return {
            "network": NETWORK_XHTTP,
            "security": "tls",
            "tlsSettings": {
                "serverName": SERVER_NAME,
                "allowInsecure": True,
                "fingerprint": "chrome",
            },
            "xhttpSettings": {"path": XHTTP_PATH, "host": SERVER_NAME, "mode": XHTTP_MODE},
        }
    fingerprint = (
        XRAY_FINGERPRINT_HYBRID
        if protocol == PROTOCOL_REALITY_HYBRID
        else XRAY_FINGERPRINT_CLASSICAL
    )
    return {
        "network": NETWORK_TCP,
        "security": "reality",
        "realitySettings": {
            "fingerprint": fingerprint,
            "serverName": SERVER_NAME,
            "publicKey": material.reality_public_key,
            "shortId": material.short_id,
        },
    }


def _wire_protocol(protocol: str) -> str:
    if node_profile(protocol) == NODE_PROFILE_HY2:
        return PROTOCOL_HYSTERIA2
    return PROTOCOL_VLESS


def _obfs(protocol: str) -> str:
    if protocol == PROTOCOL_HY2_SALAMANDER:
        return OBFS_SALAMANDER
    if protocol in {PROTOCOL_HY2_GECKO, PROTOCOL_HY2_PORT_HOP}:
        return OBFS_GECKO
    raise KeyError(protocol)


def _q(value: str) -> str:
    return json.dumps(value)
