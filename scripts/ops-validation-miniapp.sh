#!/bin/bash
# Shared by build.yml and ci-check --local; run from the source checkout.
set -euo pipefail
npm run lint
npm run build
audit_gate="$GITHUB_WORKSPACE/scripts/npm-audit-gate.py"
[ -f "$audit_gate" ] || {
  echo "::error::source-owned npm audit gate is missing: scripts/npm-audit-gate.py"
  exit 1
}
"$YUE_CI_PYTHON" "$audit_gate" \
  "$GITHUB_WORKSPACE/telegram-bot/yue/miniapp"
