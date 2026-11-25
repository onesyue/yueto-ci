"""A partial actions/cache restore is a miss, not a job failure.

2026-11-25: run 45649770105 failed validate-yueops-reference-ordinary-000
when actions/cache reported tar exit 2. Run 45651087036 passed the same
yueops SHA 97abfa28. Restore steps may continue; install, pytest and
publish stay strict, and every action pin stays on its reviewed SHA.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"
CACHE_PIN = "actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9 # v6.1.0"
RESTORE_STEPS = (
    "Restore npm cache (yueops frontends)",
    "Restore pnpm store (yueboard frontends)",
    "Restore Go modules",
    "Restore and refresh Go compiler cache",
    "Restore verified public UA core archives",
)
# Steps that install or execute tests. A restore miss must not make these optional.
STRICT_STEPS = {
    "Install yueops dependencies": 2,
    "Execute owned Ops pytest selection": 1,
    "Run service-owned pytest selection": 1,
    "Validate yueops backend": 1,
    "Set up uv": 2,
}
# Exact `uses:` lines in build.yml. A bump, a dropped version comment, or a
# floating ref changes this map.
ACTION_PINS = {
    "actions/attest-build-provenance@4d101475d8b20a2381f78447822ac1eab6504dd8 # v4.2.2": 1,
    "actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9 # v6.1.0": 5,
    "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1": 1,
    "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1": 15,
    "actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1 # v3.2.0": 8,
    "actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333": 2,
    "actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333 # v8": 5,
    "actions/setup-go@b7ad1dad31e06c5925ef5d2fc7ad053ef454303e # v7.0.0": 2,
    "actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7.0.0": 1,
    "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0": 1,
    "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a": 2,
    "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1": 9,
    "aquasecurity/trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25 # v0.36.0": 2,
    "astral-sh/setup-uv@bec219d24cd3e171d82865faccec33120bb574f4 # v10.1.0": 2,
    "bufbuild/buf-action@85aebf73123b5c15fd5528aaecbf9129cddf7fa7 # v1.6.0": 1,
    "docker/build-push-action@53b7df96c91f9c12dcc8a07bcb9ccacbed38856a # v7.3.0": 2,
    "docker/login-action@dbcb813823bdd20940b903addbd779551569679f # v4.6.0": 4,
    "docker/setup-buildx-action@37fe631027851001ddb9b187196cc803df7f5f0e # v4.3.0": 2,
    "docker/setup-qemu-action@1f40c72289eff860ee54a304f1438e3cff362e0a # v4.3.0": 1,
}
PIN_LINE = re.compile(
    r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}(?: # v\d+(?:\.\d+){0,2})?$"
)
STEP_RE = re.compile(
    r"^      - name: (?P<name>.+)\n(?P<body>(?:(?!^      - |^  [a-z]).*\n)*)",
    re.M,
)


def named_steps(text: str) -> list[tuple[str, str]]:
    return [(match.group("name"), match.group("body")) for match in STEP_RE.finditer(text)]


def action_pins(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for line in re.findall(r"(?m)^ +uses: (.+)$", text):
        counts[line] = counts.get(line, 0) + 1
    return counts


def assert_cache_restore_contract(case: unittest.TestCase, text: str) -> None:
    steps = named_steps(text)
    restores = [
        (name, body)
        for name, body in steps
        if re.search(r"(?m)^        uses: actions/cache@", body)
    ]
    case.assertEqual([name for name, _body in restores], list(RESTORE_STEPS))
    for name, body in restores:
        case.assertEqual(body.count("        continue-on-error: true\n"), 1, name)
        case.assertIn("        uses: " + CACHE_PIN + "\n", body, name)
        case.assertNotRegex(body, r"(?m)^        run:", name)
    counts: dict[str, int] = {}
    for name, body in steps:
        counts[name] = counts.get(name, 0) + 1
        if name not in RESTORE_STEPS:
            case.assertNotIn("continue-on-error", body, name)
    for name, expected in STRICT_STEPS.items():
        case.assertEqual(counts.get(name), expected, name)
    publish = text.split("\n  publish:\n", 1)[1].split("\n  abort-on-build-failure:\n", 1)[0]
    case.assertNotIn("continue-on-error", publish)
    residual = text
    for _name, body in restores:
        residual = residual.replace(body, body.replace("        continue-on-error: true\n", "", 1), 1)
    case.assertNotIn("continue-on-error", residual)
    pins = action_pins(text)
    case.assertEqual(pins, ACTION_PINS)
    for pin in pins:
        case.assertRegex(pin, PIN_LINE)
    case.assertIn("45649770105", text)
    case.assertIn("45651087036", text)
    case.assertIn("97abfa28", text)


class CacheRestoreFlakeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_restore_miss_keeps_install_pytest_and_publish_strict(self) -> None:
        assert_cache_restore_contract(self, self.text)

    def test_dropping_the_restore_miss_or_loosening_a_gate_fails(self) -> None:
        npm = "      - name: Restore npm cache (yueops frontends)\n"
        pytest_step = "      - name: Execute owned Ops pytest selection\n"
        install = "      - name: Install yueops dependencies\n"
        owned = "      - name: Run service-owned pytest selection\n"
        mutations = {
            "npm restore fails the job": self.text.replace(
                "        continue-on-error: true\n", "", 1),
            "cache pin floats": self.text.replace(CACHE_PIN, "actions/cache@main", 1),
            "cache version comment dropped": self.text.replace(
                CACHE_PIN, CACHE_PIN.replace(" # v6.1.0", ""), 1),
            "pytest continues after failure": self.text.replace(
                pytest_step, pytest_step + "        continue-on-error: true\n", 1),
            "install continues after failure": self.text.replace(
                install, install + "        continue-on-error: true\n", 1),
            "owned pytest continues after failure": self.text.replace(
                owned, owned + "        continue-on-error: true\n", 1),
            "publish continues after failure": self.text.replace(
                "\n  publish:\n", "\n  publish:\n    continue-on-error: true\n", 1),
            "npm restore renamed out of the miss set": self.text.replace(
                npm, "      - name: Save npm cache\n", 1),
        }
        for label, mutated in mutations.items():
            with self.subTest(label=label):
                self.assertNotEqual(mutated, self.text)
                with self.assertRaises(AssertionError):
                    assert_cache_restore_contract(self, mutated)
