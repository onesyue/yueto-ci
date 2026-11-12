#!/bin/bash
# Shared by build.yml and ci-check --local; run from the source checkout.
set -euo pipefail
squawk_flags=(
  --pg-version=15.0
  --assume-in-transaction
  "--exclude=prefer-robust-stmts,prefer-text-field,prefer-identity,require-timeout-settings"
)
# Write first, then read: process substitution would hide a failed
# range selector and turn an invalid base into a green empty scan.
migration_list="${RUNNER_TEMP}/yueops-changed-migrations.nul"
python3 .ci-policy/scripts/changed-migrations.py --base "$MIGRATION_BASE" > "$migration_list"
mapfile -d '' -t migrations < "$migration_list"
if [ "${#migrations[@]}" -eq 0 ]; then
  echo "no changed YueOps SQL migrations"
  exit 0
fi
# Do not execute an npm registry package in the privileged release
# validation job. Fetch the upstream release binary at an immutable
# version and authenticate its exact bytes before use.
squawk_bin="${RUNNER_TEMP}/squawk-2.60.0"
curl --fail --location --silent --show-error \
  --proto '=https' --proto-redir '=https' --tlsv1.2 \
  --connect-timeout 10 --max-time 180 \
  --retry 4 --retry-all-errors \
  'https://github.com/sbdchd/squawk/releases/download/v2.60.0/squawk-linux-x64' \
  --output "$squawk_bin"
printf '%s  %s\n' \
  '708d77899e2b43e0d21cb811023dbbcfb3b8220b0c0b7e71c6e73568be7716e5' \
  "$squawk_bin" | sha256sum --check --strict
chmod 0755 "$squawk_bin"
test "$("$squawk_bin" --version)" = 'squawk 2.60.0'
"$squawk_bin" "${squawk_flags[@]}" "${migrations[@]}"
