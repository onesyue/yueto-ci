#!/usr/bin/env bash
# Shared Board prerequisites; hosted setup and optional caches stay outside.
set -euo pipefail
unset CDPATH
fail() { echo "board-preflight: $*" >&2; exit 2; }
[ "$#" -eq 3 ] || fail 'usage: board-validation-preflight.sh PHASE SOURCE POLICY'
phase=$1
case "$phase" in dependencies|contract) ;; *) fail "unsupported phase: $phase" ;; esac
[ -d "$2" ] && [ -f "$2/go.mod" ] || fail 'Board source directory with go.mod is required'
[ -d "$3" ] && [ -f "$3/native-node-contract.json" ] || fail 'policy directory with native contract is required'
for secret in GH_TOKEN GITHUB_TOKEN GH_ENTERPRISE_TOKEN GITHUB_ENTERPRISE_TOKEN; do
  [ -z "${!secret:-}" ] || fail "credential environment is not allowed: $secret"
done
source_dir=$(cd -- "$2" && pwd)
policy=$(cd -- "$3" && pwd)
[ -n "${YUE_CI_PYTHON:-}" ] && [ -x "$YUE_CI_PYTHON" ] || fail 'validated Python interpreter is unavailable'
case "$0" in
  */*) verifier_dir=$(cd -- "${0%/*}" && pwd) ;;
  *) verifier_dir=$PWD ;;
esac
export TZ=UTC
cd -- "$source_dir"
case "$phase" in
  dependencies)
    for tool in bash git buf corepack docker gcc go make node psql; do
      command -v "$tool" >/dev/null 2>&1 || {
        echo "::error::runner is missing required yueboard tool: $tool" >&2
        exit 1
      }
    done
    docker info >/dev/null
    ;;
  contract)
    case "${PROMOTE:-}" in true|false) ;; *) fail 'explicit PROMOTE=true|false is required' ;; esac
    go clean -testcache
    source_sha="$(git rev-parse HEAD)"
    contract_pin="$(jq -r '.yueboard_contract_pin // empty' "$policy/native-node-contract.json")"
    "$YUE_CI_PYTHON" "$verifier_dir/verify-yueboard-commit.py" --source "$source_dir"
    bash "$policy/scripts/authorize-yueboard-promotion.sh" "$source_sha" "$contract_pin" "$PROMOTE"
    "$YUE_CI_PYTHON" "$policy/scripts/validate-native-node-contract.py" --kind yueboard --source .
    ;;
esac
