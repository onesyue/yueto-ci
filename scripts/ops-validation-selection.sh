#!/bin/bash
# Shared by build.yml and ci-check --local; run from the source checkout.
set -euo pipefail
.venv/bin/python .ci-policy/scripts/pytest-shards.py run \
  --admission "${RUNNER_TEMP:?}/ops-admission/ops-admission.json" \
  --source "$PWD" --board "$PWD/.ci-yueboard" --role "$OPS_ROLE" \
  --output "$RUNNER_TEMP/ops-shard-evidence"
