#!/usr/bin/env bash
# Shared credential-free Linux Node profile body; admission and fork auth stay outside.
set -euo pipefail
unset CDPATH
fail() { echo "node-validation: $*" >&2; exit 2; }
[ "$#" -eq 2 ] || fail 'usage: node-validation.sh PROFILE SOURCE'
NODE_PROFILE=$1
case "$NODE_PROFILE" in hy2|vless) ;; *) fail 'invalid yue-node validation profile' ;; esac
[ -d "$2" ] && [ -f "$2/go.mod" ] || fail 'source directory with go.mod is required'
for secret in GH_TOKEN GITHUB_TOKEN GH_ENTERPRISE_TOKEN GITHUB_ENTERPRISE_TOKEN YUETO_FORK_READ_TOKEN; do
  [ -z "${!secret:-}" ] || fail "credential environment is not allowed: $secret"
done
# Reject inherited command-scoped Git auth/config rather than pass it to source code.
for variable in ${!GIT_CONFIG@}; do
  [ -z "${!variable:-}" ] || fail "Git configuration environment is not allowed: $variable"
done
[ "${GOFLAGS:-}" = '-mod=vendor' ] || fail 'GOFLAGS=-mod=vendor is required'
export NODE_PROFILE
cd -- "$2"
[ "$(go env CGO_ENABLED)" = "1" ] || {
  echo "::error::Go race validation requires CGO_ENABLED=1"
  exit 1
}
[ -f vendor/modules.txt ] || {
  echo "::error::yue-node must stay vendored: the credential-free test step cannot fetch private forks"
  exit 1
}
# Two independent Linux jobs run the same race suite and Linux-only
# data-path subset that `make test` previously ran sequentially.
# The signed fork gate ran in the step above; keep the
# dependency-closure gate in both jobs.
make check-profile-deps
bash scripts/test-check-vulnerabilities.sh
common_tags='with_quic with_utls with_wireguard with_clash_api'
go test -race -count=1 -timeout 30m \
  -tags "$common_tags yue_profile_$NODE_PROFILE" ./...
case "$NODE_PROFILE" in
  hy2)
    go test -race -count=1 -timeout 30m \
      -tags "$common_tags yue_profile_hy2" \
      ./internal/kernel/hysteria/compatobfs/
    ;;
  vless)
    go test -race -count=1 -timeout 30m \
      -tags "$common_tags yue_profile_vless" \
      -run 'Splice|VendoredVisionReality' ./internal/kernel/xray/
    ;;
esac
if [ "$NODE_PROFILE" = vless ]; then
  # One job verifies the exact selector + dependency-pruned bundle
  # and both vulnerability views after both source suites complete.
  make build
  bash scripts/check-vulnerabilities.sh
fi
