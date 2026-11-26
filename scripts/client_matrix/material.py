"""Runtime-only dial material. Tests inject Material; nothing here is a secret store."""

from __future__ import annotations

import base64
import re
import secrets
import subprocess
import uuid
from dataclasses import dataclass

_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
_HEX = re.compile(r"^[0-9a-f]+$")
_KEY = re.compile(r"^[A-Za-z0-9_-]{43}$")
_HEX_BYTE = re.compile(r"[0-9a-f]{2}")


@dataclass(frozen=True)
class Material:
    user_uuid: str
    obfs_password: str
    reality_private_key: str
    reality_public_key: str
    short_id: str

    def secret_values(self) -> tuple[str, ...]:
        return (
            self.user_uuid,
            self.obfs_password,
            self.reality_private_key,
            self.reality_public_key,
            self.short_id,
        )


def validate_material(material: Material) -> None:
    if _UUID.fullmatch(material.user_uuid) is None:
        raise ValueError("user uuid is not a lowercase uuid")
    if _HEX.fullmatch(material.obfs_password) is None or len(material.obfs_password) < 16:
        raise ValueError("obfs password is not hex")
    if _KEY.fullmatch(material.reality_private_key) is None:
        raise ValueError("reality private key is not raw url-safe base64")
    if _KEY.fullmatch(material.reality_public_key) is None:
        raise ValueError("reality public key is not raw url-safe base64")
    if _HEX.fullmatch(material.short_id) is None or len(material.short_id) != 16:
        raise ValueError("short id must be 16 hex characters")


def generate_material() -> Material:
    private_key, public_key = _x25519_pair()
    material = Material(
        user_uuid=str(uuid.uuid4()),
        obfs_password=secrets.token_hex(16),
        reality_private_key=private_key,
        reality_public_key=public_key,
        short_id=secrets.token_hex(8),
    )
    validate_material(material)
    return material


def _x25519_pair() -> tuple[str, str]:
    pem = subprocess.check_output(
        ["openssl", "genpkey", "-algorithm", "X25519"],
        text=True,
    )
    text = subprocess.check_output(
        ["openssl", "pkey", "-text", "-noout"],
        input=pem,
        text=True,
    )
    private_raw, public_raw = _split_key_text(text)
    return _raw_url(private_raw), _raw_url(public_raw)


def _split_key_text(text: str) -> tuple[bytes, bytes]:
    private_hex: list[str] = []
    public_hex: list[str] = []
    section = ""
    for line in text.splitlines():
        stripped = line.strip().lower()
        if stripped.startswith("priv:"):
            section = "priv"
            continue
        if stripped.startswith("pub:"):
            section = "pub"
            continue
        if section == "":
            continue
        found = _HEX_BYTE.findall(stripped)
        if section == "priv":
            private_hex.extend(found)
        else:
            public_hex.extend(found)
    private_raw = bytes.fromhex("".join(private_hex))
    public_raw = bytes.fromhex("".join(public_hex))
    if len(private_raw) == 33 and private_raw[0] == 0:
        private_raw = private_raw[1:]
    if len(private_raw) != 32 or len(public_raw) != 32:
        raise RuntimeError("openssl x25519 parse failed")
    return private_raw, public_raw


def _raw_url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
