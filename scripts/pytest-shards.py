#!/usr/bin/env python3
"""Plan Ops jobs, execute the source-owned selection and strictly join evidence.

The ordinary corpus verdict alone never supplies complete release acceptance.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from pytest_shards.cli import main

if __name__ == "__main__":
    sys.exit(main())
