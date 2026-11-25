"""Resolve the alert-chain deadman bastion address.

The address lives only in ``deadman/canonical/config/hosts.json`` under the
core-host name ``bastion``. The observer contract references that name.
``YUEOPS_HOST_BASTION`` overrides the JSON default. When that variable is
set, the inventory file may be absent (migration).
"""

from __future__ import annotations

import ipaddress
import json
import os
import sys
from pathlib import Path

HOST_NAME = "bastion"
ENV_NAME = "YUEOPS_HOST_BASTION"
_CANONICAL = Path(__file__).resolve().parents[1]
INVENTORY = _CANONICAL / "config" / "hosts.json"
CONTRACT = _CANONICAL / "config" / "alert-chain-deadman-observer-contract.json"


def _ipv4(value: str) -> str:
    try:
        address = ipaddress.IPv4Address(value.strip())
    except ipaddress.AddressValueError as exc:
        raise SystemExit("bastion host must be an IPv4 address") from exc
    return str(address)


def _require_contract_name(contract: Path) -> None:
    if not contract.is_file():
        return
    payload = json.loads(contract.read_text(encoding="utf-8"))
    transport = payload.get("transport")
    if not isinstance(transport, dict) or transport.get("host_name") != HOST_NAME:
        raise SystemExit("deadman transport host_name is not bastion")


def _inventory_address(inventory: Path) -> str:
    if not inventory.is_file():
        raise SystemExit(f"{ENV_NAME} is unset and the host inventory is absent")
    payload = json.loads(inventory.read_text(encoding="utf-8"))
    hosts = payload.get("hosts")
    if not isinstance(hosts, list):
        raise SystemExit("host inventory has no hosts array")
    matches = [
        row for row in hosts
        if isinstance(row, dict) and row.get("name") == HOST_NAME
    ]
    if len(matches) != 1 or not isinstance(matches[0].get("ip"), str):
        raise SystemExit(
            f"{ENV_NAME} is unset and {HOST_NAME} is absent from the host inventory"
        )
    return _ipv4(matches[0]["ip"])


def resolve_bastion_host(
    inventory: Path | None = None,
    contract: Path | None = None,
    env: dict[str, str] | None = None,
) -> str:
    """Return the bastion IPv4 the observer already probes."""
    environment = os.environ if env is None else env
    _require_contract_name(CONTRACT if contract is None else contract)
    override = environment.get(ENV_NAME, "").strip()
    if override:
        return _ipv4(override)
    return _inventory_address(INVENTORY if inventory is None else inventory)


def main() -> int:
    sys.stdout.write(resolve_bastion_host() + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
