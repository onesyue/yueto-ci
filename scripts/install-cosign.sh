#!/usr/bin/env bash
# Policy-owned cosign bootstrap: tolerate GitHub Releases 504s without changing
# the reviewed version or weakening verification. Release cosign_checksums.txt
# and GitHub asset digest agree on this SHA-256 (reviewed 2026-11-05).
set -euo pipefail
# shellcheck source=scripts/ci-retry.sh
source "$(dirname "${BASH_SOURCE[0]}")/ci-retry.sh"
umask 077
readonly COSIGN_VERSION='v3.1.3'
readonly COSIGN_SHA256='4629c757b7618056f8ddd7e2625ae9fdd94c0372a65049520bc7d9df9efc7f71'

fail() { echo "::error::$*" >&2; exit 1; }
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] ||
  fail 'Cosign artifact is reviewed only for Linux x86_64 runners'
[[ -n "${RUNNER_TEMP:-}" && -d "$RUNNER_TEMP" ]] ||
  fail 'RUNNER_TEMP must identify an existing runner temporary directory'
[[ -n "${GITHUB_PATH:-}" ]] ||
  fail 'GITHUB_PATH is required to hand the verified cosign to later steps'

scratch=$(mktemp -d "$RUNNER_TEMP/yueto-cosign.XXXXXXXX")
trap 'rm -rf -- "$scratch"' EXIT
binary="$scratch/cosign-linux-amd64"
release_url="https://github.com/sigstore/cosign/releases/download/${COSIGN_VERSION}/cosign-linux-amd64"
if ! ci_download 10 -fsSL --connect-timeout 20 --max-time 120 -o "$binary" \
  "$release_url"; then
  echo "GitHub release front failed; using the asset API" >&2
  rm -f -- "$binary"
  ci_release_asset_api 4 "$binary" "$release_url"
fi
printf '%s  %s\n' "$COSIGN_SHA256" "$binary" | sha256sum --check --strict
install_dir="$RUNNER_TEMP/cosign-bin"
install -d -m 0755 "$install_dir"
install -m 0755 "$binary" "$install_dir/cosign"

resolved=$(PATH="$install_dir:$PATH" command -v cosign)
[[ "$resolved" == "$install_dir/cosign" ]] ||
  fail "PATH resolved an unexpected cosign: $resolved"
actual=$("$resolved" version)
printf '%s\n' "$actual"
printf '%s\n' "$actual" | grep -Eq "^[[:space:]]*GitVersion:[[:space:]]+${COSIGN_VERSION//./\\.}[[:space:]]*$" ||
  fail "verified cosign reported an unexpected version: $actual"
printf '%s\n' "$install_dir" >>"$GITHUB_PATH"
