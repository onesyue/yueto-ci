from __future__ import annotations

import base64
import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "scripts/verify-sbom-attestations.py"
IMAGE = "ghcr.io/onesyue/yueboard"
DIGEST = "sha256:" + "a" * 64


def document(architecture: str | None, *, image: str = IMAGE) -> dict[str, str]:
    properties = []
    if architecture is not None:
        properties.append(
            {"name": "syft:metadata:architecture", "value": architecture}
        )
    statement = {
        "_type": "https://in-toto.io/Statement/v0.1",
        "predicateType": "https://cyclonedx.org/bom",
        "subject": [
            {"name": image, "digest": {"sha256": DIGEST.removeprefix("sha256:")}}
        ],
        "predicate": {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "metadata": {
                "component": {
                    "type": "container",
                    "name": image,
                    "version": DIGEST,
                }
            },
            "components": [{"name": "service", "properties": properties}],
        },
    }
    encoded = base64.b64encode(
        json.dumps(statement, separators=(",", ":")).encode()
    ).decode()
    return {"payload": encoded}


def run_verifier(documents: list[dict[str, str]], expected: str) -> subprocess.CompletedProcess[str]:
    raw = "\n".join(json.dumps(item) for item in documents)
    return subprocess.run(
        [
            sys.executable,
            str(VERIFIER),
            "--image",
            IMAGE,
            "--digest",
            DIGEST,
            "--expected-architectures",
            expected,
        ],
        input=raw,
        text=True,
        capture_output=True,
        check=False,
    )


class SbomAttestationPolicyTests(unittest.TestCase):
    def test_distinct_amd64_and_arm64_predicates_pass(self) -> None:
        result = run_verifier([document("amd64"), document("arm64")], "amd64,arm64")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_duplicate_amd64_predicates_cannot_stand_in_for_arm64(self) -> None:
        result = run_verifier([document("amd64"), document("amd64")], "amd64,arm64")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("arm64", result.stderr)

    def test_old_empty_predicate_does_not_hide_a_valid_current_platform(self) -> None:
        result = run_verifier([document(None), document("amd64")], "amd64")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unexpected_architecture_is_rejected_for_single_arch_image(self) -> None:
        result = run_verifier(
            [document("amd64"), document("arm64")],
            "amd64",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unexpected=arm64", result.stderr)

    def test_subject_and_digest_are_bound(self) -> None:
        result = run_verifier(
            [document("amd64", image="ghcr.io/onesyue/not-yueboard")], "amd64"
        )
        self.assertNotEqual(result.returncode, 0)

    def test_malformed_dsse_fails_closed(self) -> None:
        result = run_verifier([{"payload": "not-base64!"}], "amd64")
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
