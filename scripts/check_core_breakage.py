#!/usr/bin/env python3
"""Fail when a carried document reintroduces removed core config keys.

The lists below are the only copies of those key names. Tests import them.

sing-box keys already gone by 1.14.0 come from the upstream deprecated list
and migration notes: legacy DNS server fields (removed in 1.14.0), GeoIP and
Geosite rule-database fields (removed in 1.12.0), and inet4-style TUN fields
(removed in 1.12.0). sing-box 1.16.0 removals are the fields deprecated in
1.14.0/1.15.0: inline ``tls.acme``, Hysteria v1 window and MTU tunables, and
the DNS-rule leftovers named in that deprecation list. Xray 26.x keys are the
config fields the 26.1.23 and 26.2.6 release notes remove, plus the transports
and legacy XTLS value that v26.11.9 still rejects with PrintRemovedFeatureError.

Sibling subscribe and clientconfig coverage waits for a pin (R2-05 #483).
This checker scans JSON and YAML documents already in the checkout. It does
not clone yueboard, yuelink, or yue-node.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

# Removed by sing-box 1.14.0 (legacy DNS) or already removed in 1.12.0 and
# still rejected by the 1.14 line the fleet pins (GeoIP, Geosite, inet4 TUN).
SINGBOX_114_REMOVED_KEYS = (
    "address_resolver",
    "address_strategy",
    "inet4_address",
    "inet6_address",
    "inet4_route_address",
    "inet6_route_address",
    "inet4_route_exclude_address",
    "inet6_route_exclude_address",
    "geoip",
    "geosite",
    "source_geoip",
    "source_geosite",
)

# Announced for removal in sing-box 1.16.0. ``strategy`` is also the legacy
# DNS-server field removed with the 1.14 server format; one spelling.
SINGBOX_DNS_STRATEGY = "strategy"
SINGBOX_DNS_RULE_OUTBOUND = "outbound"
SINGBOX_116_ANNOUNCED_KEYS = (
    "recv_window_conn",
    "recv_window",
    "recv_window_client",
    "max_conn_client",
    "disable_mtu_discovery",
    "rule_set_ip_cidr_accept_empty",
    "independent_cache",
    "store_rdrc",
    "download_detour",
)
SINGBOX_116_DNS_RULE_KEYS = (
    SINGBOX_DNS_RULE_OUTBOUND,
    SINGBOX_DNS_STRATEGY,
)
SINGBOX_116_DNS_ADDRESS_FILTER_KEYS = (
    "ip_cidr",
    "ip_is_private",
)
SINGBOX_116_MATCH_RESPONSE = "match_response"
SINGBOX_116_TLS_PARENT = "tls"
SINGBOX_116_TLS_ACME = "acme"

# Legacy DNS server object. ``type`` is the 1.14 server discriminator.
SINGBOX_114_DNS_SERVER_ADDRESS = "address"
SINGBOX_114_DNS_SERVER_TYPE = "type"
SINGBOX_114_DNS_SERVER_DETOUR = "detour"

# Xray-core 26.x. Transport and security checks compare values, not new keys.
XRAY_26_REMOVED_KEYS = (
    "allowInsecure",
    "pinnedPeerCertificateChainSha256",
    "pinnedPeerCertificatePublicKeySha256",
    "proxySettings",
)
XRAY_26_STREAM_SETTINGS = "streamSettings"
XRAY_26_NETWORK = "network"
XRAY_26_REMOVED_TRANSPORTS = (
    "http",
    "quic",
)
XRAY_26_SECURITY = "security"
XRAY_26_REMOVED_SECURITY = "xtls"

CATALOG_114 = "singbox_114_removed"
CATALOG_116 = "singbox_116_announced"
CATALOG_XRAY = "xray_26_removed"

DOCUMENT_SUFFIXES = (
    ".json",
    ".yaml",
    ".yml",
)
SKIP_DIRECTORIES = (
    ".git",
    ".lane",
    "__pycache__",
)

UNAMBIGUOUS = {
    key: CATALOG_114 for key in SINGBOX_114_REMOVED_KEYS
}
UNAMBIGUOUS.update({key: CATALOG_116 for key in SINGBOX_116_ANNOUNCED_KEYS})
UNAMBIGUOUS.update({key: CATALOG_XRAY for key in XRAY_26_REMOVED_KEYS})


class ScanError(Exception):
    """A carried document could not be parsed, so the check cannot pass."""


@dataclass(frozen=True)
class Finding:
    path: str
    pointer: str
    key: str
    catalog: str

    def format(self) -> str:
        return f"{self.path}:{self.pointer} {self.key} {self.catalog}"


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _is_dns_server(pointer: str) -> bool:
    if not pointer.startswith("/dns/servers/"):
        return False
    rest = pointer.removeprefix("/dns/servers/")
    return rest.isdigit()


def _is_dns_rule(pointer: str) -> bool:
    if not pointer.startswith("/dns/rules/"):
        return False
    rest = pointer.removeprefix("/dns/rules/")
    return rest.isdigit()


def _under_tls(pointer: str) -> bool:
    return pointer == f"/{SINGBOX_116_TLS_PARENT}" or pointer.endswith(
        f"/{SINGBOX_116_TLS_PARENT}"
    )


def _under_stream_settings(pointer: str) -> bool:
    parent = XRAY_26_STREAM_SETTINGS
    return pointer == f"/{parent}" or pointer.endswith(f"/{parent}")


def match_object(node: dict, pointer: str, relpath: str) -> list[Finding]:
    """Return removed keys on this object. Nested objects are separate calls."""
    found: list[Finding] = []
    for key in node:
        catalog = UNAMBIGUOUS.get(key)
        if catalog is not None:
            found.append(Finding(relpath, f"{pointer}/{_escape(key)}", key, catalog))

    if _is_dns_server(pointer):
        legacy = SINGBOX_114_DNS_SERVER_TYPE not in node
        if SINGBOX_114_DNS_SERVER_ADDRESS in node:
            found.append(Finding(
                relpath,
                f"{pointer}/{SINGBOX_114_DNS_SERVER_ADDRESS}",
                SINGBOX_114_DNS_SERVER_ADDRESS,
                CATALOG_114,
            ))
        if legacy and SINGBOX_DNS_STRATEGY in node:
            found.append(Finding(
                relpath,
                f"{pointer}/{SINGBOX_DNS_STRATEGY}",
                SINGBOX_DNS_STRATEGY,
                CATALOG_114,
            ))
        if (
            legacy
            and SINGBOX_114_DNS_SERVER_ADDRESS in node
            and SINGBOX_114_DNS_SERVER_DETOUR in node
        ):
            found.append(Finding(
                relpath,
                f"{pointer}/{SINGBOX_114_DNS_SERVER_DETOUR}",
                SINGBOX_114_DNS_SERVER_DETOUR,
                CATALOG_114,
            ))

    if _under_tls(pointer) and SINGBOX_116_TLS_ACME in node:
        found.append(Finding(
            relpath,
            f"{pointer}/{SINGBOX_116_TLS_ACME}",
            SINGBOX_116_TLS_ACME,
            CATALOG_116,
        ))

    if _is_dns_rule(pointer):
        for key in SINGBOX_116_DNS_RULE_KEYS:
            if key in node:
                found.append(Finding(relpath, f"{pointer}/{key}", key, CATALOG_116))
        if node.get(SINGBOX_116_MATCH_RESPONSE) is not True:
            for key in SINGBOX_116_DNS_ADDRESS_FILTER_KEYS:
                if key in node:
                    found.append(Finding(relpath, f"{pointer}/{key}", key, CATALOG_116))

    if _under_stream_settings(pointer):
        network = node.get(XRAY_26_NETWORK)
        if isinstance(network, str) and network in XRAY_26_REMOVED_TRANSPORTS:
            found.append(Finding(
                relpath,
                f"{pointer}/{XRAY_26_NETWORK}",
                XRAY_26_NETWORK,
                CATALOG_XRAY,
            ))

    if node.get(XRAY_26_SECURITY) == XRAY_26_REMOVED_SECURITY:
        found.append(Finding(
            relpath,
            f"{pointer}/{XRAY_26_SECURITY}",
            XRAY_26_SECURITY,
            CATALOG_XRAY,
        ))
    return found


def findings_in(node: object, pointer: str, relpath: str) -> list[Finding]:
    found: list[Finding] = []
    if isinstance(node, dict):
        found.extend(match_object(node, pointer, relpath))
        for key, value in node.items():
            found.extend(findings_in(value, f"{pointer}/{_escape(str(key))}", relpath))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(findings_in(value, f"{pointer}/{index}", relpath))
    return found


def iter_documents(path: Path) -> Iterator[object]:
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return
    suffix = path.suffix.lower()
    try:
        if suffix == ".json":
            yield json.loads(text)
            return
        yield from yaml.safe_load_all(text)
    except (json.JSONDecodeError, yaml.YAMLError, UnicodeError) as error:
        raise ScanError(f"{path}: {error}") from error


def scan_root(root: Path) -> tuple[list[Finding], int]:
    findings: list[Finding] = []
    documents = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in SKIP_DIRECTORIES]
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if path.suffix.lower() not in DOCUMENT_SUFFIXES:
                continue
            relpath = path.relative_to(root).as_posix()
            for document in iter_documents(path):
                if document is None:
                    continue
                documents += 1
                findings.extend(findings_in(document, "", relpath))
    return findings, documents


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) > 1:
        print("usage: check_core_breakage.py [ROOT]", file=sys.stderr)
        return 2
    root = Path(args[0]) if args else ROOT
    try:
        findings, documents = scan_root(root)
    except ScanError as error:
        print(str(error), file=sys.stderr)
        return 1
    if findings:
        for item in findings:
            print(item.format(), file=sys.stderr)
        print(f"core breakage: {len(findings)} removed keys", file=sys.stderr)
        return 1
    print(
        f"core breakage ok: documents={documents} "
        f"keys={len(UNAMBIGUOUS)} findings=0"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
