"""Validate runs in the pinned toolchain image and does not apt."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"
IMAGE = ROOT / "images" / "yueops-ci-toolchain"
RETIRED = (
    "scripts/install-yueops-pg18-toolchain.sh",
    "scripts/activate-yueops-pg18-toolchain.sh",
    "scripts/pg18-toolchain-roundtrip.sh",
    "tests/test_native_postgres_toolchain.py",
)


class CiToolchainImageTest(unittest.TestCase):
    def test_retired_apt_installer_is_gone(self) -> None:
        for relative in RETIRED:
            with self.subTest(path=relative):
                self.assertFalse((ROOT / relative).exists(), relative)

    def test_validate_pins_the_image_and_does_not_apt(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        validate = workflow.split("\n  validate:\n", 1)[1].split(
            "\n  validation-evidence:\n", 1
        )[0]
        self.assertRegex(
            validate,
            r"image: ghcr\.io/onesyue/yueops-ci-toolchain@sha256:[0-9a-f]{64}\n",
        )
        self.assertNotIn("DIGEST_PLACEHOLDER", workflow)
        self.assertNotIn("apt-get", validate)
        self.assertNotIn("install-yueops-pg18", validate)
        self.assertNotIn("install-native-nginx.sh", validate)
        self.assertIn("sing-box-1.14 version", validate)

    def test_image_build_pins_uv_and_the_runtime_tools(self) -> None:
        digest = (IMAGE / "uv.sha256").read_text(encoding="utf-8").strip()
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        dockerfile = (IMAGE / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("ARG UV_SHA256", dockerfile)
        self.assertIn('echo "$UV_SHA256  /tmp/uv.tgz" | sha256sum -c', dockerfile)
        for needle in (
            "postgresql-18 postgresql-client-18",
            "plpgsql.so",
            "dict_snowball.so",
            "sing-box-1.14",
            "go1.27.4",
            "uv python install 3.13",
            "USER runner",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, dockerfile)
        rebuild = (ROOT / ".github" / "workflows" / "ci-toolchain.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("images/yueops-ci-toolchain/uv.sha256", rebuild)
        self.assertRegex(
            rebuild,
            re.compile(r"uses: docker/(?:login|build-push)-action@[0-9a-f]{40}"),
        )
        self.assertIn("provenance: false", rebuild)
        self.assertIn("yueops-ci-toolchain-selfcheck", rebuild)


if __name__ == "__main__":
    unittest.main()
