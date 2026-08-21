#!/usr/bin/env python3
"""Verify the semantic platform set inside cosign-verified CycloneDX DSSE.

Cryptographic verification remains cosign's responsibility. This second gate
parses cosign's JSON-lines output and proves that the requested image digest
has a platform-specific Syft SBOM for every expected production architecture.
Counting attestations is insufficient because retries and rebuilds can append
duplicates, and an old/empty predicate must not stand in for a missing arch.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from typing import Any


ALLOWED_ARCHITECTURES = frozenset({"amd64", "arm64"})
STATEMENT_TYPE = "https://in-toto.io/Statement/v0.1"
PREDICATE_TYPE = "https://cyclonedx.org/bom"


def _json_documents(raw: str) -> list[Any]:
    decoder = json.JSONDecoder()
    documents: list[Any] = []
    offset = 0
    while True:
        while offset < len(raw) and raw[offset].isspace():
            offset += 1
        if offset == len(raw):
            return documents
        document, offset = decoder.raw_decode(raw, offset)
        documents.extend(document if isinstance(document, list) else [document])


def _decode_statement(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict) or not isinstance(document.get("payload"), str):
        raise ValueError("cosign output document is not a DSSE object with payload")
    payload = base64.b64decode(document["payload"], validate=True)
    statement = json.loads(payload)
    if not isinstance(statement, dict):
        raise ValueError("DSSE payload is not an in-toto statement object")
    return statement


def _statement_architectures(
    statement: dict[str, Any], image: str, digest: str
) -> frozenset[str] | None:
    if statement.get("_type") != STATEMENT_TYPE:
        return None
    if statement.get("predicateType") != PREDICATE_TYPE:
        return None

    subject = statement.get("subject")
    if not isinstance(subject, list) or len(subject) != 1:
        return None
    expected_hex = digest.removeprefix("sha256:")
    if subject[0] != {"name": image, "digest": {"sha256": expected_hex}}:
        return None

    predicate = statement.get("predicate")
    if not isinstance(predicate, dict):
        return None
    if predicate.get("bomFormat") != "CycloneDX":
        return None
    if not isinstance(predicate.get("specVersion"), str) or not predicate["specVersion"]:
        return None
    metadata = predicate.get("metadata")
    component = metadata.get("component") if isinstance(metadata, dict) else None
    if not isinstance(component, dict):
        return None
    platform_digest = component.get("version")
    if (
        component.get("type") != "container"
        or component.get("name") != image
        or not isinstance(platform_digest, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", platform_digest) is None
    ):
        return None

    properties = component.get("properties")
    if not isinstance(properties, list):
        return frozenset()
    subject_digests = {
        prop.get("value")
        for prop in properties
        if isinstance(prop, dict)
        and prop.get("name") == "onesyue:sbom:subject:digest"
    }
    if subject_digests != {digest}:
        return frozenset()
    architectures = {
        prop.get("value")
        for prop in properties
        if isinstance(prop, dict)
        and prop.get("name") == "onesyue:sbom:platform:architecture"
        and prop.get("value") in ALLOWED_ARCHITECTURES
    }
    return frozenset(architectures)


def verify(raw: str, image: str, digest: str, expected: frozenset[str]) -> None:
    if not re.fullmatch(r"ghcr\.io/onesyue/[a-z0-9][a-z0-9._-]*", image):
        raise ValueError("image must be an exact onesyue GHCR repository")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("digest must be canonical sha256:<64 lowercase hex>")
    if not expected or not expected <= ALLOWED_ARCHITECTURES:
        raise ValueError("expected architectures must be amd64 and/or arm64")

    documents = _json_documents(raw)
    if not documents:
        raise ValueError("cosign returned no attestation documents")
    observed: set[str] = set()
    matched = 0
    for document in documents:
        architectures = _statement_architectures(
            _decode_statement(document), image, digest
        )
        if architectures is None:
            continue
        matched += 1
        # A platform scan must describe one native architecture. A combined
        # or empty predicate cannot satisfy either platform requirement.
        if len(architectures) == 1:
            observed.update(architectures)

    missing = sorted(expected - observed)
    unexpected = sorted(observed - expected)
    if missing or unexpected:
        raise ValueError(
            "verified CycloneDX set does not equal the expected platforms"
            f" (missing={','.join(missing) or '-'};"
            f" unexpected={','.join(unexpected) or '-'})"
        )
    print(
        "verified CycloneDX architectures: "
        f"{','.join(sorted(expected))} ({matched}/{len(documents)} matching statements)"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--digest", required=True)
    parser.add_argument("--expected-architectures", required=True)
    args = parser.parse_args()
    expected = frozenset(
        architecture.strip()
        for architecture in args.expected_architectures.split(",")
        if architecture.strip()
    )
    try:
        verify(sys.stdin.read(), args.image, args.digest, expected)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"SBOM attestation policy rejected input: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
