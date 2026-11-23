#!/usr/bin/env bash
set -euo pipefail
# The source gate checks workspace membership or each legacy lockfile.
if [ -f pnpm-workspace.yaml ]; then
  manifest=./package.json
else
  manifest=./web/package.json
fi
pin=$(node -p 'require(process.argv[1]).packageManager || ""' "$manifest")
[ -n "$pin" ]
corepack enable
corepack install --global "$pin"
audit_gate="scripts/ci/pnpm-audit-gate.mjs"
[ -f "$audit_gate" ] || { echo "missing source-owned $audit_gate" >&2; exit 1; }
node "$audit_gate" web web-admin
node "$audit_gate" test/a11y test/e2e
