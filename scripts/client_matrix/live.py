"""Fetch pinned clients and dial one yue-node group at a time."""

from __future__ import annotations

import gzip
import hashlib
import hmac
import io
import os
import signal
import socket
import subprocess
import tarfile
import threading
import time
import zipfile
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from client_matrix.catalog import (
    CLIENTS_BY_ID,
    DIAL_TIMEOUT_SECONDS,
    LOCAL_SOCKS_HOST,
    LOCAL_SOCKS_PORT,
    NFT_TABLE,
    PROBE_BODY,
    PROBE_HOST,
    PROBE_PATH,
    PROBE_PORT,
    PROTOCOL_HY2_PORT_HOP,
    PROTOCOLS,
    READY_TIMEOUT_SECONDS,
    STATUS_FAIL,
    STATUS_PASS,
    address_commands,
    client_argv,
    hop_commands,
    listen_endpoint,
    node_argv,
    node_group,
    node_profile,
)
from client_matrix.configs import config_suffix, render_client, render_node
from client_matrix.material import Material
from client_matrix.runner import CellPlan, redact

Opener = Callable[[str], object]


class FetchError(Exception):
    pass


def read_https(url: str, opener: Opener) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc == "":
        raise FetchError("download must use https")
    with opener(url) as response:
        payload = response.read()
    if not isinstance(payload, (bytes, bytearray)) or not payload:
        raise FetchError("download was empty")
    return bytes(payload)


def verify_digest(client_id: str, expected: str, payload: bytes) -> None:
    digest = hashlib.sha256(payload).hexdigest()
    if not hmac.compare_digest(digest, expected):
        raise FetchError(f"digest mismatch for {client_id}")


def extract_binary(archive: str, binary_name: str, payload: bytes, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / binary_name
    if archive == "gz":
        try:
            payload = gzip.decompress(payload)
        except gzip.BadGzipFile as exc:
            raise FetchError("archive could not be read") from exc
        _write_executable(target, payload)
        return target
    data = _archive_member(archive, binary_name, payload)
    _write_executable(target, data)
    return target


def resolve_client(client_id: str, cache: Path, source_path: str, opener: Opener) -> Path:
    pin = CLIENTS_BY_ID[client_id]
    if pin.source_built:
        path = Path(source_path)
        if source_path == "" or not path.is_file():
            raise FetchError(f"missing source build for {client_id}")
        return path
    dest_dir = cache / client_id
    binary = dest_dir / pin.binary_name
    stamp = dest_dir / "sha256"
    if binary.is_file() and stamp.is_file() and stamp.read_text(encoding="utf-8").strip() == pin.sha256:
        return binary
    payload = read_https(pin.download_url, opener)
    verify_digest(pin.client_id, pin.sha256, payload)
    extracted = extract_binary(pin.archive, pin.binary_name, payload, dest_dir)
    stamp.write_text(pin.sha256 + "\n", encoding="utf-8")
    return extracted


class LiveDialer:
    """One node process per server group. Unsupported plans never reach dial."""

    def __init__(
        self,
        node_bins: dict[str, Path],
        client_bins: dict[str, Path],
        material: Material,
        work: Path,
    ) -> None:
        self._node_bins = node_bins
        self._client_bins = client_bins
        self._material = material
        self._work = work
        self._group = ""
        self._ready = False
        self._detail = ""
        self._node: subprocess.Popen[str] | None = None
        self._client: subprocess.Popen[str] | None = None
        self._node_log: Path | None = None
        self._client_log: Path | None = None
        self._host_error = ""
        self._host_ready = False
        self._httpd: ThreadingHTTPServer | None = None

    def dial(self, plan: CellPlan) -> tuple[str, str]:
        self._ensure(plan.group)
        if not self._ready:
            return STATUS_FAIL, self._detail
        return self._dial_client(plan)

    def close(self) -> None:
        self._stop_process(self._client, self._client_log)
        self._client = None
        self._stop_process(self._node, self._node_log)
        self._node = None
        self._delete_nft()
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    def _ensure(self, group: str) -> None:
        if self._group == group:
            return
        self._stop_process(self._client, self._client_log)
        self._client = None
        self._stop_process(self._node, self._node_log)
        self._node = None
        if self._group == PROTOCOL_HY2_PORT_HOP:
            self._delete_nft()
        self._group = group
        self._prepare_host()
        if self._host_error:
            self._ready = False
            self._detail = self._host_error
            return
        self._start_node(group)

    def _prepare_host(self) -> None:
        if self._host_ready or self._host_error:
            return
        try:
            for command in address_commands():
                _checked(command)
            self._start_probe()
        except (OSError, subprocess.CalledProcessError) as exc:
            self._host_error = redact(str(exc), self._material.secret_values())
            return
        self._host_ready = True

    def _start_probe(self) -> None:
        server = ThreadingHTTPServer((PROBE_HOST, PROBE_PORT), _ReadyHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self._httpd = server

    def _start_node(self, group: str) -> None:
        try:
            self._spawn_node(group)
        except (OSError, subprocess.CalledProcessError) as exc:
            self._ready = False
            self._detail = redact(str(exc), self._material.secret_values())

    def _spawn_node(self, group: str) -> None:
        protocol = next(item for item in PROTOCOLS if node_group(item) == group)
        directory = self._work / group
        directory.mkdir(parents=True, exist_ok=True)
        config_dir = directory / "state"
        config_dir.mkdir(exist_ok=True)
        config_path = directory / "node.yml"
        config_path.write_text(
            render_node(protocol, self._material, config_dir.as_posix()),
            encoding="utf-8",
        )
        if group == PROTOCOL_HY2_PORT_HOP:
            _host, port, _kind = listen_endpoint(protocol)
            self._apply_hop(port)
        binary = self._node_bins[node_profile(protocol)]
        self._node_log = directory / "node.err"
        self._node = _spawn(node_argv(str(binary), str(config_path)), self._node_log)
        self._ready, self._detail = self._wait_node(protocol)

    def _wait_node(self, protocol: str) -> tuple[bool, str]:
        host, port, kind = listen_endpoint(protocol)
        deadline = time.monotonic() + READY_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if self._node is not None and self._node.poll() is not None:
                return False, self._tail(self._node_log, "node exited")
            if kind == "tcp" and _port_open(host, port):
                return True, "listening"
            if kind == "udp" and self._node is not None and self._node.poll() is None:
                time.sleep(1)
                if self._node.poll() is None:
                    return True, "listening"
            time.sleep(0.2)
        return False, self._tail(self._node_log, "node did not stay up")

    def _dial_client(self, plan: CellPlan) -> tuple[str, str]:
        text, reason = render_client(plan.client_id, plan.protocol, self._material)
        if text is None:
            return STATUS_FAIL, reason or "missing client config"
        directory = self._work / plan.group
        config_path = directory / f"{plan.client_id}-{plan.protocol}{config_suffix(plan.client_id)}"
        config_path.write_text(text, encoding="utf-8")
        self._client_log = directory / f"{plan.client_id}.err"
        binary = self._client_bins[plan.client_id]
        self._client = _spawn(client_argv(str(binary), plan.client_id, str(config_path)), self._client_log)
        if not self._wait_socks():
            detail = self._tail(self._client_log, "client did not open socks")
            self._stop_process(self._client, self._client_log)
            self._client = None
            return STATUS_FAIL, detail
        status, detail = self._curl()
        self._stop_process(self._client, self._client_log)
        self._client = None
        return status, detail

    def _wait_socks(self) -> bool:
        deadline = time.monotonic() + READY_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if self._client is not None and self._client.poll() is not None:
                return False
            if _port_open(LOCAL_SOCKS_HOST, LOCAL_SOCKS_PORT):
                return True
            time.sleep(0.2)
        return False

    def _curl(self) -> tuple[str, str]:
        url = f"http://{PROBE_HOST}:{PROBE_PORT}{PROBE_PATH}"
        command = (
            "curl",
            "--silent",
            "--show-error",
            "--max-time",
            str(DIAL_TIMEOUT_SECONDS),
            "--socks5-hostname",
            f"{LOCAL_SOCKS_HOST}:{LOCAL_SOCKS_PORT}",
            url,
        )
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=DIAL_TIMEOUT_SECONDS + 5,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return STATUS_FAIL, redact(str(exc), self._material.secret_values())
        body = completed.stdout.strip()
        if completed.returncode == 0 and body == PROBE_BODY:
            return STATUS_PASS, "ready"
        detail = completed.stderr.strip() or body or f"curl exit {completed.returncode}"
        return STATUS_FAIL, redact(detail, self._material.secret_values())

    def _apply_hop(self, port: int) -> None:
        commands = hop_commands(port)
        _run(_privileged(commands[0]), check=False)
        for command in commands[1:]:
            _checked(command)

    def _delete_nft(self) -> None:
        _run(_privileged(("nft", "delete", "table", "ip", NFT_TABLE)), check=False)

    def _tail(self, path: Path | None, fallback: str) -> str:
        if path is None or not path.is_file():
            return fallback
        text = path.read_text(encoding="utf-8", errors="replace")[-1500:]
        cleaned = redact(text, self._material.secret_values()).strip()
        return cleaned or fallback

    def _stop_process(self, proc: subprocess.Popen[str] | None, log_path: Path | None) -> None:
        _stop(proc)
        del log_path


class _ReadyHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != PROBE_PATH:
            self.send_error(404)
            return
        body = PROBE_BODY.encode("ascii")
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        del fmt, args


def _archive_member(archive: str, binary_name: str, payload: bytes) -> bytes:
    if archive == "tar.gz":
        return _tar_member(binary_name, payload)
    if archive == "zip":
        return _zip_member(binary_name, payload)
    raise FetchError(f"unsupported archive {archive}")


def _tar_member(binary_name: str, payload: bytes) -> bytes:
    try:
        archive = tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz")
    except tarfile.TarError as exc:
        raise FetchError("archive could not be read") from exc
    with archive:
        matches = [item for item in archive.getmembers() if _name_is_binary(item.name, binary_name)]
        if len(matches) != 1 or not matches[0].isfile():
            raise FetchError("archive has no client binary")
        extracted = archive.extractfile(matches[0])
        if extracted is None:
            raise FetchError("archive has no client binary")
        return extracted.read()


def _zip_member(binary_name: str, payload: bytes) -> bytes:
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise FetchError("archive could not be read") from exc
    with archive:
        matches = [name for name in archive.namelist() if _name_is_binary(name, binary_name)]
        if len(matches) != 1 or matches[0].endswith("/"):
            raise FetchError("archive has no client binary")
        return archive.read(matches[0])


def _name_is_binary(name: str, binary_name: str) -> bool:
    if name.startswith("/") or name.startswith("\\"):
        return False
    parts = PurePosixPath(name).parts
    if ".." in parts or not parts:
        return False
    return parts[-1] == binary_name


def _write_executable(path: Path, payload: bytes) -> None:
    path.write_bytes(payload)
    path.chmod(0o755)


def _privileged(command: tuple[str, ...]) -> tuple[str, ...]:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return command
    return ("sudo", "-n", *command)


def _checked(command: tuple[str, ...]) -> None:
    _run(_privileged(command), check=True)


def _run(command: tuple[str, ...], check: bool) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=check,
        capture_output=True,
        text=True,
        timeout=20,
    )


def _spawn(command: tuple[str, ...], log_path: Path) -> subprocess.Popen[str]:
    log_file = log_path.open("w", encoding="utf-8")
    try:
        return subprocess.Popen(
            command,
            stdout=log_file,
            stderr=log_file,
            text=True,
            start_new_session=True,
        )
    finally:
        log_file.close()


def _stop(proc: subprocess.Popen[str] | None) -> None:
    if proc is None:
        return
    if proc.poll() is None:
        _signal_group(proc, signal.SIGTERM)
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            _signal_group(proc, signal.SIGKILL)
            proc.wait(timeout=3)
    else:
        proc.wait(timeout=3)


def _signal_group(proc: subprocess.Popen[str], sig: int) -> None:
    try:
        os.killpg(proc.pid, sig)
    except ProcessLookupError:
        return


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.3):
            return True
    except OSError:
        return False
