"""Ratchet for tunable, host-path, domain and port literals in scripts/*.py.

The classes match the yueops literal lint: numeric literals on timeout,
interval, ttl, retry, delay, limit, threshold, budget, batch, worker, max
and min names; numeric literals passed to sleep; absolute host paths;
http(s) URLs and yue.to / yuetong / yuetoto domains; and port literals.

``scripts/lib/ci_constants.py`` is the config module and is outside
``scripts/*.py``. ``scripts/brand_literals.py`` is the brand projection.
``scripts/pytest-shards.py`` belongs to the shard-split lane and is not
scanned. Counts in ``policy/literal-classes.json`` may only go down.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "policy" / "literal-classes.json"
CONSTANTS_PATH = ROOT / "scripts" / "lib" / "ci_constants.py"
CLASSES = ("tunable", "host-path", "domain", "port")
SKIPPED = {
    "scripts/brand_literals.py": "brand projection; domains are defined there",
    "scripts/pytest-shards.py": "owned by the shard-split lane",
}
TUNABLE_NAME = re.compile(
    r"timeout|interval|ttl|retries|retry|delay|threshold|budget|batch|workers|limit|max|min",
    re.I,
)
PORT_NAME = re.compile(r"(?:^|_)port(?:$|_)", re.I)
HOST_PREFIXES = ("/etc/", "/var/lib/", "/opt/", "/run/", "/usr/local/")
URL_RE = re.compile(r"https?://[A-Za-z0-9]")
BRAND_RE = re.compile(
    r"(?<![A-Za-z0-9.-])(?:[A-Za-z0-9-]+\.)*(?:yue\.to|yuetong\.[A-Za-z0-9.-]+|yuetoto\.[A-Za-z0-9.-]+)",
    re.I,
)
PORT_TEXT_RE = re.compile(
    r"(?:(?:\d{1,3}\.){3}\d{1,3}|localhost|postgres):(\d{2,5})(?=/|:|$|\?|\s)"
    r"|:(\d{2,5})/"
)
SKIP_NUMBERS = {0, 1, -1}


def _load_constants():
    spec = importlib.util.spec_from_file_location("ci_constants", CONSTANTS_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {CONSTANTS_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _call_name(func: ast.expr) -> str:
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _number(node: ast.expr) -> int | float | None:
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        if node.value in SKIP_NUMBERS:
            return None
        return node.value
    return None


def _host_path(text: str) -> bool:
    for prefix in HOST_PREFIXES:
        start = 0
        while True:
            found = text.find(prefix, start)
            if found < 0:
                break
            if found == 0 or not (text[found - 1].isalnum() or text[found - 1] in "._-"):
                return True
            start = found + len(prefix)
    return False


class _Scanner(ast.NodeVisitor):
    def __init__(self) -> None:
        self.hits = {name: 0 for name in CLASSES}
        self.notes: list[str] = []

    def _add(self, kind: str, line: int, detail: object) -> None:
        self.hits[kind] += 1
        self.notes.append(f"L{line} {kind} {detail!r}"[:180])

    def _tunable(self, node: ast.expr, line: int, detail: str) -> None:
        if _number(node) is not None:
            self._add("tunable", line, detail)

    def _port_number(self, node: ast.expr, line: int, detail: str) -> None:
        if _number(node) is not None:
            self._add("port", line, detail)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            if _host_path(node.value):
                self._add("host-path", node.lineno, node.value[:80])
            if URL_RE.search(node.value) or BRAND_RE.search(node.value):
                self._add("domain", node.lineno, node.value[:80])
            if PORT_TEXT_RE.search(node.value):
                self._add("port", node.lineno, node.value[:80])
        self.generic_visit(node)

    def visit_keyword(self, node: ast.keyword) -> None:
        if node.arg and TUNABLE_NAME.search(node.arg):
            self._tunable(node.value, node.lineno, node.arg)
        if node.arg and PORT_NAME.search(node.arg):
            self._port_number(node.value, node.lineno, node.arg)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if TUNABLE_NAME.search(name):
                self._tunable(node.value, node.lineno, name)
            if PORT_NAME.search(name):
                self._port_number(node.value, node.lineno, name)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name) and node.value is not None:
            name = node.target.id
            if TUNABLE_NAME.search(name):
                self._tunable(node.value, node.lineno, name)
            if PORT_NAME.search(name):
                self._port_number(node.value, node.lineno, name)
        self.generic_visit(node)

    def _defaults(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        positional = node.args.posonlyargs + node.args.args
        for arg, default in zip(positional[-len(node.args.defaults):], node.args.defaults):
            if TUNABLE_NAME.search(arg.arg):
                self._tunable(default, default.lineno, arg.arg)
            if PORT_NAME.search(arg.arg):
                self._port_number(default, default.lineno, arg.arg)
        for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
            if default is None:
                continue
            if TUNABLE_NAME.search(arg.arg):
                self._tunable(default, default.lineno, arg.arg)
            if PORT_NAME.search(arg.arg):
                self._port_number(default, default.lineno, arg.arg)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._defaults(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._defaults(node)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if _call_name(node.func) == "sleep":
            for arg in node.args:
                self._tunable(arg, getattr(arg, "lineno", node.lineno), "sleep")
        self.generic_visit(node)


def scan() -> dict[str, dict[str, int]]:
    found: dict[str, dict[str, int]] = {}
    notes: list[str] = []
    for path in sorted((ROOT / "scripts").glob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        if relative in SKIPPED:
            continue
        scanner = _Scanner()
        scanner.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        positive = {kind: count for kind, count in scanner.hits.items() if count}
        if positive:
            found[relative] = positive
            notes.extend(f"{relative} {note}" for note in scanner.notes)
    scan.notes = notes  # type: ignore[attr-defined]
    return found


def _positive(files: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    cleaned: dict[str, dict[str, int]] = {}
    for path, counts in files.items():
        kept = {kind: int(counts.get(kind, 0)) for kind in CLASSES if int(counts.get(kind, 0))}
        if kept:
            cleaned[path] = kept
    return cleaned


def _head_baseline() -> dict[str, dict[str, int]] | None:
    result = subprocess.run(
        ["git", "show", "HEAD:policy/literal-classes.json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    payload = json.loads(result.stdout)
    return _positive(payload.get("files", {}))


class LiteralClassRatchetTest(unittest.TestCase):
    def test_current_counts_match_baseline(self) -> None:
        current = scan()
        payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(list(payload["classes"]), list(CLASSES))
        baseline = _positive(payload["files"])
        if current != baseline:
            self.fail(
                "literal counts drifted\ncurrent "
                + json.dumps(current, sort_keys=True)
                + "\nbaseline "
                + json.dumps(baseline, sort_keys=True)
                + "\n"
                + "\n".join(getattr(scan, "notes", []))
            )

    def test_baseline_counts_only_go_down(self) -> None:
        previous = _head_baseline()
        if previous is None:
            return
        payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        current = _positive(payload["files"])
        for path in set(previous) | set(current):
            for kind in CLASSES:
                before = previous.get(path, {}).get(kind, 0)
                after = current.get(path, {}).get(kind, 0)
                self.assertLessEqual(
                    after,
                    before,
                    f"{path} {kind} rose from {before} to {after}",
                )

    def test_constants_keep_the_previous_values(self) -> None:
        constants = _load_constants()
        expected = {
            "GITHUB_HTTPS_ORIGIN": "https://github.com",
            "GITHUB_API_ORIGIN": "https://api.github.com",
            "GITHUB_ONESYUE_PREFIX": "https://github.com/onesyue/",
            "GHCR_ORIGIN": "https://ghcr.io",
            "ACTIONS_OIDC_ISSUER": "https://token.actions.githubusercontent.com",
            "SLSA_PROVENANCE_PREDICATE": "https://slsa.dev/provenance/v1",
            "IN_TOTO_STATEMENT_V01": "https://in-toto.io/Statement/v0.1",
            "CYCLONEDX_BOM_PREDICATE": "https://cyclonedx.org/bom",
            "SPDX_DOCUMENT_PREDICATE": "https://spdx.dev/Document",
            "GITHUB_HTTP_TIMEOUT_SECONDS": 30,
            "GH_API_TIMEOUT_SECONDS": 60,
            "GH_ATTESTATION_TIMEOUT_SECONDS": 180,
            "GIT_COMMAND_TIMEOUT_SECONDS": 20,
            "GIT_REV_PARSE_SHORT_TIMEOUT_SECONDS": 15,
            "GIT_REV_PARSE_TIMEOUT_SECONDS": 30,
            "GIT_OBJECT_TIMEOUT_SECONDS": 60,
            "GPGV_TIMEOUT_SECONDS": 30,
            "DOCKER_INSPECT_TIMEOUT_SECONDS": 30,
            "DOCKER_HOSTED_CLEANUP_TIMEOUT_SECONDS": 60,
            "DOCKER_LIFECYCLE_TIMEOUT_SECONDS": 120,
            "DOCKER_WAIT_TIMEOUT_SECONDS": 7200,
            "NODE_SUBPROCESS_TIMEOUT_SECONDS": 10,
            "PROCESS_WAIT_TIMEOUT_SECONDS": 10,
            "PROCESS_GROUP_JOIN_SECONDS": 5,
            "PROCESS_GROUP_SETTLE_SECONDS": 0.5,
            "PROCESS_GROUP_POLL_SECONDS": 0.05,
            "ARTIFACT_RETRY_DELAY_SECONDS": 2,
            "RUN_DISCOVERY_POLL_SECONDS": 5,
            "RUN_DISCOVERY_DEADLINE_SECONDS": 180,
            "SCAN_COMMAND_TIMEOUT_SECONDS": 600,
            "COREPACK_ENABLE_TIMEOUT_SECONDS": 60,
            "COREPACK_PREPARE_TIMEOUT_SECONDS": 180,
            "RATE_LIMIT_BACKOFF_SECONDS": 60,
            "RATE_LIMIT_RETRY_CEILING_SECONDS": 300,
            "LOG_HEADER_BYTE_LIMIT": 65536,
            "VALIDATION_IMAGE_WORKERS": 5,
            "CI_FAILURE_CLUSTER_WORKERS": 4,
            "POSTGRES_HEALTH_ATTEMPTS": 60,
            "MAX_VERSION_PAGES": 100,
            "NODE_CONFIG_MIN_FILES": 5,
            "NODE_CONTROLPLANE_MIN_FILES": 5,
            "NODE_SERVICE_MIN_FILES": 8,
            "NODE_SERVICE_TEST_MIN_FILES": 3,
            "NODE_MODEL_MIN_FILES": 8,
            "NODE_XRAY_MIN_FILES": 20,
            "NODE_XRAY_TEST_MIN_FILES": 10,
            "NODE_HYSTERIA_MIN_FILES": 8,
            "NODE_HYSTERIA_TEST_MIN_FILES": 10,
            "OPS_DEPLOY_MIN_FILES": 5,
            "BOARD_NODESYNC_MIN_FILES": 30,
            "BOARD_SUBSCRIBE_MIN_FILES": 10,
            "BOARD_DEVICE_IDENTITY_MIN_FILES": 2,
            "BOARD_MODULE_MIN_FILES": 100,
            "BOARD_WEB_MIN_FILES": 50,
            "DEADCODE_MIN_CONFIDENCE": 100,
            "COMPLEXITY_CCN_LIMIT": 30,
            "COMPLEXITY_NLOC_LIMIT": 200,
            "NODE_IMAGE_BIN_COPY": (
                "COPY --from=builder /build/yue-node* /usr/local/bin/"
            ),
            "NODE_ENTRYPOINT_NEEDLE": (
                'entrypoint: ["{BIN_YUE_NODE_PREFIX}{role}"]'
            ),
            "NODE_EXPECTED_PATH_NEEDLE": (
                'expected_path = f"{BIN_YUE_NODE_PREFIX}{role}"'
            ),
            "POSTGRES_PORT": 5432,
            "BOARD_E2E_PUBLISHED_POSTGRES_PORT": 55434,
        }
        for name, value in expected.items():
            self.assertEqual(getattr(constants, name), value, name)

    def test_rendered_endpoints_match_the_previous_bytes(self) -> None:
        constants = _load_constants()
        origin = constants.GITHUB_HTTPS_ORIGIN
        onesyue = constants.GITHUB_ONESYUE_PREFIX
        api = constants.GITHUB_API_ORIGIN
        ghcr = constants.GHCR_ORIGIN
        port = constants.POSTGRES_PORT
        published = constants.BOARD_E2E_PUBLISHED_POSTGRES_PORT
        self.assertEqual(f"{origin}/onesyue/yueto-ci", "https://github.com/onesyue/yueto-ci")
        self.assertEqual(f"{onesyue}yueto-ci.git", "https://github.com/onesyue/yueto-ci.git")
        self.assertEqual(
            "http." + origin + "/.extraheader",
            "http.https://github.com/.extraheader",
        )
        self.assertEqual(f"{api}/repos/onesyue/yueto-ci", "https://api.github.com/repos/onesyue/yueto-ci")
        self.assertEqual(
            f"{api}/users/onesyue/packages/container/yueops/versions",
            "https://api.github.com/users/onesyue/packages/container/yueops/versions",
        )
        self.assertEqual(
            f"{ghcr}/token?scope=repository:onesyue/yueops:pull&service=ghcr.io",
            "https://ghcr.io/token?scope=repository:onesyue/yueops:pull&service=ghcr.io",
        )
        self.assertEqual(f"{ghcr}/v2/onesyue/yueops/manifests/latest", "https://ghcr.io/v2/onesyue/yueops/manifests/latest")
        self.assertEqual(
            f"postgres://postgres:ci@postgres:{port}/yueboard_test",
            "postgres://postgres:ci@postgres:5432/yueboard_test",
        )
        self.assertEqual(f"127.0.0.1:{port}:{port}", "127.0.0.1:5432:5432")
        self.assertEqual(f":{port}/", ":5432/")
        self.assertEqual(f":{published}/", ":55434/")
        self.assertEqual(
            f"@postgres:{port}/".replace(f"@postgres:{port}/", f"@127.0.0.1:{port}/", 1),
            "@127.0.0.1:5432/",
        )


if __name__ == "__main__":
    current = scan()
    print(json.dumps(current, indent=2, sort_keys=True))
    print("\n".join(getattr(scan, "notes", [])))
