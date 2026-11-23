#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

mode=${1:-quick}
if [[ $# -gt 1 || ( "$mode" != quick && "$mode" != ci ) ]]; then
  echo 'usage: scripts/check-policy.sh [quick|ci]' >&2
  exit 2
fi

for tool in python3 go shellcheck actionlint; do
  command -v "$tool" >/dev/null || { echo "policy requires $tool on PATH" >&2; exit 2; }
done
source scripts/lint-tool-versions.sh
version=$(actionlint -version) && version=${version#v} && [[ ${version%%$'\n'*} == "$ACTIONLINT_VERSION" ]] || {
  echo "policy requires actionlint $ACTIONLINT_VERSION on PATH" >&2
  exit 2
}
python3 scripts/run-policy-tests.py --check-tools

if [[ "$mode" == ci ]]; then
  python3 scripts/run-policy-tests.py
  python3 -m compileall -q scripts tests
  for script in scripts/*.sh; do
    bash -n "$script"
  done
  shellcheck --severity=warning scripts/*.sh
else
  python3 scripts/run-policy-tests.py --changed
fi
actionlint .github/workflows/*.yml
