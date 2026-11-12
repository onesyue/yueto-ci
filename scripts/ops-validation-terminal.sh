#!/bin/bash
# Shared by build.yml and ci-check --local; run from the source checkout.
set -euo pipefail
.venv/bin/python .ci-policy/scripts/pytest-shards.py native-terminal \
  --admission "${RUNNER_TEMP:?}/ops-admission/ops-admission.json" \
  --source "$PWD" --board "$PWD/.ci-yueboard" \
  --output "$RUNNER_TEMP/ops-shard-evidence"
