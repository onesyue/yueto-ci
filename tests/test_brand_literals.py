"""Brand literals stay in one module, and sealed skip bytes stay put.

The scanner is the guard. A live tree that pastes a literal outside
scripts/brand_literals.py fails. A const home that drops an assignment
fails. An empty scan fails. The sealed baseline is not rewritten and is
not part of the live scan.
"""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONST_HOME = Path("scripts/brand_literals.py")
LIVE_ROOTS = ("scripts", "tests", ".github")
MIN_LIVE_FILES = 40
REQUIRED_NAMES = (
    "PANEL_URL",
    "PANEL_HOST",
    "WIDGET_URL",
    "WIDGET_HOST",
    "TELEGRAM_BOT",
    "PANEL_MIRROR_PRIMARY_URL",
    "PANEL_MIRROR_PRIMARY_HOST",
    "PANEL_MIRROR_ALTERNATE_URL",
    "PANEL_MIRROR_ALTERNATE_HOST",
    "RETIRED_MINI_PRIMARY_HOST",
    "RETIRED_MINI_ALTERNATE_HOST",
)
ASSIGNMENT = re.compile(r'(?m)^([A-Z][A-Z0-9_]*) = "([^"\n]*)"\s*$')
REACHED = (
    "scripts/brand_literals.py",
    "scripts/pytest-shards.py",
    "tests/test_brand_literals.py",
    ".github/workflows/image-rescan.yml",
    ".github/workflows/ci-toolchain.yml",
    ".github/workflows/build.yml",
)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def literal_assignments(text: str) -> dict[str, str]:
    return {name: value for name, value in ASSIGNMENT.findall(text) if value}


def live_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for base in LIVE_ROOTS:
        directory = root / base
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            found.append(path)
    return found


def scan_brand_literals(root: Path) -> tuple[list[Path], list[str]]:
    """Return scanned files and violations. Zero files is a violation."""
    files = live_files(root)
    violations: list[str] = []
    if not files:
        return files, ["scanned no live files"]
    home = root / CONST_HOME
    if not home.is_file():
        return files, ["const home missing: scripts/brand_literals.py"]
    found = literal_assignments(home.read_text(encoding="utf-8"))
    missing = [name for name in REQUIRED_NAMES if name not in found]
    if missing:
        violations.append("const home lost brand literal assignments: " + ", ".join(missing))
    needles = [found[name] for name in REQUIRED_NAMES if name in found]
    if not needles:
        violations.append("const home has no brand literal assignments")
    home_resolved = home.resolve()
    for path in files:
        if path.resolve() == home_resolved:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for needle in needles:
            if needle in text:
                violations.append(f"{path.relative_to(root).as_posix()} contains a brand literal")
                break
    return files, violations


class BrandLiterals(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.brand = _load("ci_brand_literals_under_test", ROOT / CONST_HOME)
        cls.shards = _load("pytest_shards_brand_under_test", ROOT / "scripts/pytest-shards.py")

    def test_runtime_values_match_the_const_home_literals(self):
        found = literal_assignments((ROOT / CONST_HOME).read_text(encoding="utf-8"))
        self.assertEqual(set(found), set(REQUIRED_NAMES))
        for name, value in found.items():
            self.assertEqual(getattr(self.brand, name), value)
        self.assertEqual(self.brand.TELEGRAM_BOT_HANDLE, "@" + self.brand.TELEGRAM_BOT)
        self.assertEqual(self.brand.TELEGRAM_BOT_URL, "https://t.me/" + self.brand.TELEGRAM_BOT)
        self.assertEqual(self.brand._host(self.brand.PANEL_URL), self.brand.PANEL_HOST)
        self.assertEqual(self.brand._domain(self.brand.RETIRED_MINI_PRIMARY_HOST),
                         self.brand._domain(self.brand.PANEL_MIRROR_PRIMARY_HOST))
        self.assertEqual(self.brand._domain(self.brand.RETIRED_MINI_ALTERNATE_HOST),
                         self.brand._domain(self.brand.PANEL_MIRROR_ALTERNATE_HOST))

    def test_pytest_shards_composes_sealed_ids_from_the_constants(self):
        shards = self.shards
        brand = self.brand
        self.assertEqual(len(shards.RETIRED_HOST_IDS), 3)
        self.assertEqual(len(shards.RETIRED_HOST_SECOND_IDS), 3)
        self.assertTrue(all(nodeid.endswith("[" + brand.RETIRED_MINI_PRIMARY_HOST + "]")
                            for nodeid in shards.RETIRED_HOST_IDS))
        self.assertTrue(all(nodeid.endswith("[" + brand.RETIRED_MINI_ALTERNATE_HOST + "]")
                            for nodeid in shards.RETIRED_HOST_SECOND_IDS))
        self.assertEqual(shards.RETIRED_HOST_PRIOR_SHA256,
                         "927f711ddbdd4aa14012ccb687183e969610922e0c9b17b55eef06545ec86e91")
        self.assertEqual(shards.RETIRED_HOST_BEFORE_BLOB, "812e3509c7213cf16f507271f5a1d4f8c0cefe29")
        self.assertEqual(shards.RETIRED_HOST_AFTER_BLOB, "ba19e043309d0805710e0a2d3fc9cc76ea6ce55f")
        self.assertEqual(shards.RETIRED_HOST_TRANSITION_SHA256,
                         "961fa6fd314c9d292e766e1cea5b8571f0d97b489adbebb63d4f35d16af6d7b0")
        self.assertEqual(shards.RETIRED_HOST_SECOND_AFTER_BLOB,
                         "6c3e8eca2a185a9b89aedbc3abec63c7cc2eb2fd")
        baseline = json.loads((ROOT / "ops-pytest-skip-baseline.json").read_text(encoding="utf-8"))
        hosts: list[object] = []

        def walk(obj: object) -> None:
            if isinstance(obj, dict):
                if obj.get("prior_baseline_sha256") == shards.RETIRED_HOST_PRIOR_SHA256:
                    hosts.append(obj.get("host"))
                for value in obj.values():
                    walk(value)
            elif isinstance(obj, list):
                for value in obj:
                    walk(value)

        walk(baseline)
        self.assertEqual(hosts, [brand.RETIRED_MINI_PRIMARY_HOST])
        sealed = (ROOT / "ops-pytest-skip-baseline.json").read_text(encoding="utf-8")
        for nodeid in shards.RETIRED_HOST_IDS | shards.RETIRED_HOST_SECOND_IDS:
            self.assertIn(nodeid, sealed)

    def test_live_tree_keeps_brand_literals_in_the_const_home(self):
        files, violations = scan_brand_literals(ROOT)
        self.assertEqual(violations, [])
        self.assertGreaterEqual(len(files), MIN_LIVE_FILES)
        relative = {path.relative_to(ROOT).as_posix() for path in files}
        for required in REACHED:
            self.assertIn(required, relative)
        per_root = {base: 0 for base in LIVE_ROOTS}
        for path in files:
            per_root[path.relative_to(ROOT).parts[0]] += 1
        for base, count in per_root.items():
            self.assertGreaterEqual(count, 1, base)

    def test_pasting_a_literal_outside_the_const_home_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "scripts", root / "scripts")
            needle = literal_assignments((ROOT / CONST_HOME).read_text(encoding="utf-8"))[
                "RETIRED_MINI_PRIMARY_HOST"]
            leak = root / "scripts" / "leak.py"
            leak.write_text(f"HOST = {needle!r}\n", encoding="utf-8")
            _files, violations = scan_brand_literals(root)
            self.assertTrue(any(item.startswith("scripts/leak.py") for item in violations), violations)

    def test_removing_a_const_home_assignment_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "scripts"
            home.mkdir()
            text = (ROOT / CONST_HOME).read_text(encoding="utf-8")
            mutated = re.sub(r'(?m)^PANEL_URL = "[^"\n]*"\n', "", text, count=1)
            self.assertNotEqual(mutated, text)
            (home / "brand_literals.py").write_text(mutated, encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "test_touched.py").write_text("def test_ok():\n    pass\n", encoding="utf-8")
            _files, violations = scan_brand_literals(root)
            self.assertTrue(any("PANEL_URL" in item for item in violations), violations)

    def test_empty_scan_is_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            files, violations = scan_brand_literals(Path(directory))
            self.assertEqual(files, [])
            self.assertEqual(violations, ["scanned no live files"])


if __name__ == "__main__":
    unittest.main()
