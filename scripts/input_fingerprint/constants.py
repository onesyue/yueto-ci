"""Schema names and identity patterns shared by the fingerprint package."""

from __future__ import annotations

import re
from pathlib import Path

SCHEMA = "yue-input-fingerprint/1"
RECIPE_SCHEMA = "yue-build-recipe/1"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
PINNED_IMAGE = re.compile(r"@sha256:[0-9a-f]{64}$")
ROOT = Path(__file__).resolve().parents[2]

# This advisory schema is deliberately not an Ops shard/admission envelope.
FEEDBACK_SCHEMA = "yue-affected-feedback/1"
FULL_GATES = ["validate", "validation-evidence"]
BUILD_JOB = re.compile(r"(?ms)^  build:[ \t]*\n.*?(?=^  [A-Za-z0-9_-]+:[ \t]*$|\Z)")


class Unknown(Exception):
    """The inputs cannot be proved; callers must treat this as changed."""
