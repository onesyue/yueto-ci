import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/build.yml"
INSTALLER = ROOT / "scripts/ops-validation-node-toolchain.sh"


class ValidateToolchainPins(unittest.TestCase):
    def assert_pinned(self, jobs, node):
        self.assertRegex(node, r"^24\.[0-9]+\.[0-9]+$")
        for job in ("validate", "ops-service-selection"):
            for step in jobs[job]["steps"]:
                action = step.get("uses", "").partition("@")[0]
                if action == "actions/setup-node":
                    inputs = step["with"]
                    self.assertNotIn("node-version", inputs)
                    self.assertEqual(inputs["node-version-file"], ".ci-policy/.node-version")
                elif action == "actions/setup-python":
                    self.assertRegex(step["with"]["python-version"], r"^3\.13\.[0-9]+$")

    def test_validation_and_selection_use_exact_versions(self):
        jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
        self.assert_pinned(jobs, (ROOT / ".node-version").read_text().strip())

    def test_floating_selectors_fail(self):
        jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
        node = (ROOT / ".node-version").read_text().strip()
        for selector in ("latest", "24.x", "24"):
            with self.subTest(selector=selector), self.assertRaises(AssertionError):
                self.assert_pinned(jobs, selector)
        step = next(s for s in jobs["validate"]["steps"] if s.get("name") == "Set up Node")
        step["with"]["node-version"] = "24"
        with self.assertRaises(AssertionError):
            self.assert_pinned(jobs, node)
        del step["with"]["node-version"]
        step = next(s for s in jobs["validate"]["steps"] if s.get("name") == "Set up Python for host Board e2e")
        step["with"]["python-version"] = "3.13"
        with self.assertRaises(AssertionError):
            self.assert_pinned(jobs, node)

    def test_ops_downloads_only_the_pinned_release_and_checks_its_hash(self):
        # Use a different patch to prove the installer actually reads the pin.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # macOS installs GNU sha256sum under a prefixed name.
            if checksum := shutil.which("gsha256sum"):
                (root / "sha256sum").symlink_to(checksum)
            policy = root / ".ci-policy"
            (policy / "scripts").mkdir(parents=True)
            (policy / ".node-version").write_text("24.0.1\n")
            dist = root / "dist"
            package = "node-v24.0.1-linux-x64"
            binary = dist / package / "bin/node"
            binary.parent.mkdir(parents=True)
            binary.write_text("#!/bin/sh\necho v24.0.1\n")
            binary.chmod(0o755)
            archive = dist / (package + ".tar.xz")
            subprocess.run(["tar", "-cJf", archive, "-C", dist, package], check=True)
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            (dist / "SHASUMS256.txt").write_text(f"{digest}  {archive.name}\n")
            (policy / "scripts/ci-retry.sh").write_text(
                'ci_download() {\n'
                '  while [[ $# -gt 3 ]]; do shift; done\n'
                '  [[ "$1" == "https://nodejs.org/dist/v24.0.1/${1##*/}" && "$2" == --output ]] || return 1\n'
                '  cp "$GITHUB_WORKSPACE/dist/${1##*/}" "$3"\n'
                '}\n'
            )
            for intact in (True, False):
                run = root / ("valid" if intact else "corrupt")
                if not intact:
                    # A different valid tarball would extract successfully without the check.
                    binary.write_text("#!/bin/sh\necho unexpected\n")
                    subprocess.run(["tar", "-cJf", archive, "-C", dist, package], check=True)
                path_file = run / "path"
                result = subprocess.run(
                    ["bash", INSTALLER], capture_output=True, text=True,
                    env={"PATH": os.pathsep.join((directory, os.environ["PATH"])),
                         "GITHUB_WORKSPACE": directory,
                         "RUNNER_TEMP": str(run), "GITHUB_PATH": str(path_file)},
                )
                if intact:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(path_file.read_text().strip(), str(run / "node-toolchain" / package / "bin"))
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse((run / "node-toolchain" / package).exists())
                    self.assertFalse(path_file.exists())
