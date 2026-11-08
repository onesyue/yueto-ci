#!/usr/bin/env bash
# Policy-owned Syft bootstrap. The SBOM action's own installer stops on the
# first GitHub Releases 504. This keeps Syft 1.51.1 and checks the archive
# digest GitHub publishes for that asset.
set -euo pipefail
# shellcheck source=scripts/ci-retry.sh
source "$(dirname "${BASH_SOURCE[0]}")/ci-retry.sh"
umask 077
readonly SYFT_VERSION='1.51.1'
readonly SYFT_ARCHIVE_SHA256='8fcb33017a0dc1058298c923c436d19dfa68ae93968e0b423248542e3afb9fc3'

fail() { echo "::error::$*" >&2; exit 1; }
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] ||
  fail 'Syft artifact is reviewed only for Linux x86_64 runners'
[[ -n "${RUNNER_TEMP:-}" && -d "$RUNNER_TEMP" ]] ||
  fail 'RUNNER_TEMP must identify an existing runner temporary directory'
[[ -n "${GITHUB_PATH:-}" ]] ||
  fail 'GITHUB_PATH is required to hand the verified syft to later steps'

scratch=$(mktemp -d "$RUNNER_TEMP/yueto-syft.XXXXXXXX")
trap 'rm -rf -- "$scratch"' EXIT
archive="$scratch/syft.tar.gz"
release_url="https://github.com/anchore/syft/releases/download/v${SYFT_VERSION}/syft_${SYFT_VERSION}_linux_amd64.tar.gz"
if ! ci_download 4 --fail --location --silent --show-error \
  --proto '=https' --proto-redir '=https' --tlsv1.2 \
  --connect-timeout 10 --max-time 180 \
  "$release_url" \
  --output "$archive"; then
  echo "GitHub release front failed; using the asset API" >&2
  rm -f -- "$archive"
  ci_release_asset_api 4 "$archive" "$release_url"
fi
printf '%s  %s\n' "$SYFT_ARCHIVE_SHA256" "$archive" | sha256sum --check --strict
tar --extract --gzip --file "$archive" --directory "$scratch" --no-same-owner syft
install_dir="$RUNNER_TEMP/syft-bin"
install -d -m 0755 "$install_dir"
install -m 0755 "$scratch/syft" "$install_dir/syft"

resolved=$(PATH="$install_dir:$PATH" command -v syft)
[[ "$resolved" == "$install_dir/syft" ]] ||
  fail "PATH resolved an unexpected syft: $resolved"
actual=$("$resolved" version)
printf '%s\n' "$actual"
printf '%s\n' "$actual" | grep -F "$SYFT_VERSION" >/dev/null ||
  fail "verified syft reported an unexpected version: $actual"
printf '%s\n' "$install_dir" >>"$GITHUB_PATH"
