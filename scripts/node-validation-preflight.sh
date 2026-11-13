#!/usr/bin/env bash
# Shared credential-free Node prerequisites; caches and fork authentication stay outside.
set -euo pipefail
unset CDPATH
fail() { echo "node-preflight: $*" >&2; exit 2; }
[ "$#" -eq 4 ] || fail 'usage: node-validation-preflight.sh PHASE SOURCE POLICY BOARD'
phase=$1
case "$phase" in dependencies|contract) ;; *) fail "unsupported phase: $phase" ;; esac
[ -d "$2" ] && [ -f "$2/go.mod" ] || fail 'Node source directory with go.mod is required'
[ -d "$3" ] && [ -f "$3/native-node-contract.json" ] || fail 'policy directory with native contract is required'
[ -d "$4" ] || fail 'Board canonical source directory is required'
for secret in GH_TOKEN GITHUB_TOKEN GH_ENTERPRISE_TOKEN GITHUB_ENTERPRISE_TOKEN YUETO_FORK_READ_TOKEN; do
  [ -z "${!secret:-}" ] || fail "credential environment is not allowed: $secret"
done
for variable in ${!GIT_CONFIG@}; do
  [ -z "${!variable:-}" ] || fail "Git configuration environment is not allowed: $variable"
done
source_dir=$(cd -- "$2" && pwd)
policy=$(cd -- "$3" && pwd)
board=$(cd -- "$4" && pwd)
[ -n "${YUE_CI_PYTHON:-}" ] && [ -x "$YUE_CI_PYTHON" ] || fail 'validated Python interpreter is unavailable'
export TZ=UTC
cd -- "$source_dir"
case "$phase" in
  dependencies)
    for tool in bash git base64 docker gcc go gpg jq make; do
      command -v "$tool" >/dev/null 2>&1 || {
        echo "::error::runner is missing required yue-node tool: $tool" >&2
        exit 1
      }
    done
    docker info >/dev/null
    ;;
  contract)
    "$YUE_CI_PYTHON" "$policy/scripts/validate-native-node-contract.py" \
      --kind yue-node --source . --yueboard-contract-source "$board"
    ;;
esac
