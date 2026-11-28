"""Resolve the alert-chain deadman address from the native panel_host_public role.

YueOps ``config/hosts.json`` is the inventory. This receiver does not keep a
second copy. ``--project`` prints the generated ``YUEOPS_HOST_PANEL_HOST_PUBLIC``
line. ``--check`` fails when the observer contract's ``host_role`` is not this
role, or when a leftover ``transport.host`` is not that role's current address.
``YUEOPS_HOST_PANEL_HOST_PUBLIC`` overrides the address used for the receipt
read. Historic names are rejected.
"""

from __future__ import annotations

import ipaddress
import json
import os
import sys
from pathlib import Path

ROLE = "panel_host_public"
ENV_NAME = "YUEOPS_HOST_" + ROLE.upper()
HISTORIC_NAMES = frozenset({
    "bastion",
    "bastion-tailnet",
    "panel",
    "panel-tailnet",
    "pg-primary",
    "wg-hub",
    "emby-store",
    "emby-server",
})
_ROW_KEYS = frozenset({"name", "kind", "current"})
_ROW_KEYS_INCOMING = frozenset({"name", "kind", "current", "incoming"})
_CANONICAL = Path(__file__).resolve().parents[1]
CONTRACT = _CANONICAL / "config" / "alert-chain-deadman-observer-contract.json"


def _ipv4(value: str) -> str:
    try:
        address = ipaddress.IPv4Address(value.strip())
    except ipaddress.AddressValueError as exc:
        raise SystemExit(f"{ROLE} must be an IPv4 address") from exc
    return str(address)


def _role_current(inventory: Path) -> str:
    if not inventory.is_file():
        raise SystemExit(f"{ENV_NAME} is unset and the host inventory is absent")
    payload = json.loads(inventory.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != 1
        or set(payload) - {"schema_version", "roles", "anchors"}
    ):
        raise SystemExit("historic host inventory")
    roles = payload.get("roles")
    if not isinstance(roles, list):
        raise SystemExit(f"host inventory has no {ROLE} role")
    for row in roles:
        if not isinstance(row, dict):
            raise SystemExit("historic host inventory")
        keys = set(row)
        if keys != _ROW_KEYS and keys != _ROW_KEYS_INCOMING:
            raise SystemExit("historic host inventory")
        name = row.get("name")
        if name in HISTORIC_NAMES:
            raise SystemExit("historic host name")
    matches = [row for row in roles if row.get("name") == ROLE]
    if len(matches) != 1:
        raise SystemExit(f"host inventory has no {ROLE} role")
    row = matches[0]
    if row.get("kind") != "ipv4" or not isinstance(row.get("current"), str):
        raise SystemExit(f"{ROLE} must be an IPv4 address")
    return _ipv4(row["current"])


def _contract_role_and_host(contract: Path) -> tuple[str | None, str | None]:
    """Return ``(host_role, transport.host)`` when the contract file exists.

    Official contracts pin ``host_role`` and omit a baked address. A leftover
    ``transport.host`` is still accepted so a test fixture can check drift.
    A ``host_name`` alias is rejected.
    """
    if not contract.is_file():
        return None, None
    payload = json.loads(contract.read_text(encoding="utf-8"))
    transport = payload.get("transport")
    if not isinstance(transport, dict) or "host_name" in transport:
        raise SystemExit("deadman transport uses a historic host name")
    role = transport.get("host_role")
    if role is not None and role != ROLE:
        raise SystemExit(f"observer contract drifted from {ROLE}")
    host = transport.get("host")
    if host is None and role is None:
        raise SystemExit(f"deadman transport.host is not {ROLE}")
    if host is not None and not isinstance(host, str):
        raise SystemExit(f"deadman transport.host is not {ROLE}")
    return (role if isinstance(role, str) else None, _ipv4(host) if isinstance(host, str) else None)


def _contract_host(contract: Path) -> str | None:
    """Return ``transport.host`` when present (legacy baked address)."""
    _role, host = _contract_role_and_host(contract)
    return host


def project_ops_host_public(inventory: Path) -> str:
    """One generated projection line, with no environment override."""
    return f"{ENV_NAME}={_role_current(inventory)}\n"


def check_ops_host_public(inventory: Path, contract: Path | None = None) -> None:
    """Fail when the contract does not describe the panel_host_public projection."""
    contract_path = CONTRACT if contract is None else contract
    if not contract_path.is_file():
        raise SystemExit("observer contract is absent")
    role, pinned = _contract_role_and_host(contract_path)
    projected = project_ops_host_public(inventory).split("=", 1)[1].strip()
    if role is not None and role != ROLE:
        raise SystemExit(f"observer contract drifted from {ROLE}")
    if pinned is not None and projected != pinned:
        raise SystemExit(f"observer contract drifted from {ROLE}")
    if pinned is None and role is None:
        raise SystemExit(f"deadman transport.host is not {ROLE}")


def resolve_ops_host_public(
    inventory: Path | None = None,
    contract: Path | None = None,
    env: dict[str, str] | None = None,
) -> str:
    """Return the panel_host_public IPv4 the observer probes."""
    environment = os.environ if env is None else env
    pinned = _contract_host(CONTRACT if contract is None else contract)
    override = environment.get(ENV_NAME, "").strip()
    if override:
        return _ipv4(override)
    if inventory is None or not inventory.is_file():
        raise SystemExit(f"{ENV_NAME} is unset and the host inventory is absent")
    current = _role_current(inventory)
    if pinned is not None and current != pinned:
        raise SystemExit(f"observer contract drifted from {ROLE}")
    return current


def _parse_args(argv: list[str]) -> tuple[str, Path | None, Path | None]:
    mode = "resolve"
    inventory: Path | None = None
    contract: Path | None = None
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in {"--check", "--project"}:
            if mode != "resolve":
                raise SystemExit("pass only one of --check or --project")
            mode = arg[2:]
        elif arg in {"--inventory", "--contract"}:
            index += 1
            if index >= len(argv):
                raise SystemExit(f"missing {arg} value")
            target = Path(argv[index])
            if arg == "--inventory":
                inventory = target
            else:
                contract = target
        else:
            raise SystemExit(f"unknown argument {arg}")
        index += 1
    if mode != "resolve" and inventory is None:
        raise SystemExit(f"--{mode} requires --inventory")
    return mode, inventory, contract


def main(argv: list[str] | None = None) -> int:
    mode, inventory, contract = _parse_args(list(sys.argv[1:] if argv is None else argv))
    if mode == "project":
        assert inventory is not None
        sys.stdout.write(project_ops_host_public(inventory))
        return 0
    if mode == "check":
        assert inventory is not None
        check_ops_host_public(inventory, CONTRACT if contract is None else contract)
        return 0
    sys.stdout.write(
        resolve_ops_host_public(inventory=inventory, contract=contract) + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
