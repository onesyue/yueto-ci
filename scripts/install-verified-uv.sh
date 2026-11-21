#!/usr/bin/env bash
# Policy-owned uv bootstrap. Version matches the toolchain image; the
# archive digest is the existing images/yueops-ci-toolchain/uv.sha256 pin.
set -euo pipefail
unset CDPATH
unset SCANNER_TOOL_VERSIONS_READY
# shellcheck source=scripts/scanner-tool-versions.sh
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/scanner-tool-versions.sh"
[ "${SCANNER_TOOL_VERSIONS_READY:-}" = 1 ] || { echo 'missing scanner tool version authority' >&2; exit 2; }
# shellcheck source=scripts/ci-retry.sh
source "$(dirname "${BASH_SOURCE[0]}")/ci-retry.sh"
umask 077

fail() { echo "::error::$*" >&2; exit 1; }
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] ||
  fail 'uv artifact is reviewed only for Linux x86_64 runners'
[[ -n "${RUNNER_TEMP:-}" && -d "$RUNNER_TEMP" ]] ||
  fail 'RUNNER_TEMP must identify an existing runner temporary directory'
[[ -n "${GITHUB_PATH:-}" ]] ||
  fail 'GITHUB_PATH is required to hand the verified uv to later steps'

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
pin_file="$root/images/yueops-ci-toolchain/uv.sha256"
[[ -f "$pin_file" ]] || fail 'uv.sha256 pin file is missing'
UV_ARCHIVE_SHA256=$(tr -d '[:space:]' < "$pin_file")
[[ "$UV_ARCHIVE_SHA256" =~ ^[0-9a-f]{64}$ ]] || fail 'uv.sha256 must be 64 hex digits'

scratch=$(mktemp -d "$RUNNER_TEMP/yueto-uv.XXXXXXXX")
trap 'rm -rf -- "$scratch"' EXIT
archive="$scratch/uv.tar.gz"
release_url="https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-x86_64-unknown-linux-gnu.tar.gz"
if ! ci_download 4 --fail --location --silent --show-error \
  --proto '=https' --proto-redir '=https' --tlsv1.2 \
  --connect-timeout 10 --max-time 180 \
  "$release_url" \
  --output "$archive"; then
  echo "GitHub release front failed; using the asset API" >&2
  rm -f -- "$archive"
  ci_release_asset_api 4 "$archive" "$release_url"
fi
printf '%s  %s\n' "$UV_ARCHIVE_SHA256" "$archive" | sha256sum --check --strict
tar --extract --gzip --file "$archive" --directory "$scratch" --no-same-owner
install_dir="$RUNNER_TEMP/uv-bin"
install -d -m 0755 "$install_dir"
install -m 0755 "$scratch/uv-x86_64-unknown-linux-gnu/uv" "$install_dir/uv"
resolved=$(PATH="$install_dir:$PATH" command -v uv)
[[ "$resolved" == "$install_dir/uv" ]] ||
  fail "PATH resolved an unexpected uv: $resolved"
actual=$("$resolved" --version)
printf '%s\n' "$actual"
printf '%s\n' "$actual" | grep -F "$UV_VERSION" >/dev/null ||
  fail "verified uv reported an unexpected version: $actual"
printf '%s\n' "$install_dir" >>"$GITHUB_PATH"
printf 'verified uv %s at %s\n' "$UV_VERSION" "$resolved"
