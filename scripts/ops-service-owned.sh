#!/usr/bin/env bash
# Run the pytest modules owned by one YueOps service. An empty selection fails.
set -euo pipefail

: "${SERVICE:?SERVICE is required}"
OPS_SOURCE="${OPS_SOURCE:-$PWD}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
policy_root="$(cd -- "$script_dir/.." && pwd)"

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

python3 "$policy_root/scripts/ops-service-scope.py" owned-modules \
  --service "$SERVICE" \
  --source "$OPS_SOURCE" >"$tmp"

modules=()
while IFS= read -r line || [ -n "$line" ]; do
  [ -n "$line" ] || continue
  modules+=("$line")
done <"$tmp"
rm -f "$tmp"

if [ "${#modules[@]}" -eq 0 ]; then
  echo "owned selection is empty" >&2
  exit 1
fi

cd -- "$OPS_SOURCE"
policy_quarantine="$policy_root/ci/quarantine.yaml"
if [[ -e tests/quarantine.json || -L tests/quarantine.json || "${YUETO_SHARED_SELECTION:-[]}" != '[]' || -f "$policy_quarantine" ]]; then
  export YUETO_OPS_TEST_SOURCE="$PWD"
  export YUETO_CI_QUARANTINE="$policy_quarantine"
  export PYTEST_PLUGINS=ops_quarantine
  export PYTHONPATH="$script_dir${PYTHONPATH:+:$PYTHONPATH}"
fi
exec .venv/bin/python -m pytest "${modules[@]}"
