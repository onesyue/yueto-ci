#!/usr/bin/env bash
# Policy-owned Dart SDK bootstrap for the weekly YueLink `dart pub outdated` scan.
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
  fail 'Dart SDK artifact is reviewed only for Linux x86_64 runners'
[[ -n "${RUNNER_TEMP:-}" && -d "$RUNNER_TEMP" ]] ||
  fail 'RUNNER_TEMP must identify an existing runner temporary directory'
[[ -n "${GITHUB_PATH:-}" ]] ||
  fail 'GITHUB_PATH is required to hand the verified dart to later steps'
command -v python3 >/dev/null 2>&1 || fail 'python3 is required to extract the Dart SDK'

scratch=$(mktemp -d "$RUNNER_TEMP/yueto-dart.XXXXXXXX")
trap 'rm -rf -- "$scratch"' EXIT
archive="$scratch/dartsdk.zip"
release_url="https://storage.googleapis.com/dart-archive/channels/stable/release/${DART_SDK_VERSION}/sdk/dartsdk-linux-x64-release.zip"
ci_download 4 --fail --location --silent --show-error \
  --proto '=https' --proto-redir '=https' --tlsv1.2 \
  --connect-timeout 10 --max-time 180 \
  "$release_url" \
  --output "$archive"
printf '%s  %s\n' "$DART_SDK_SHA256" "$archive" | sha256sum --check --strict
python3 -m zipfile -e "$archive" "$scratch"
sdk_bin="$scratch/dart-sdk/bin"
[[ -f "$sdk_bin/dart" && ! -L "$sdk_bin/dart" ]] ||
  fail 'verified Dart archive did not contain a regular dart binary'
chmod 0755 "$sdk_bin/dart"
resolved=$(PATH="$sdk_bin:$PATH" command -v dart)
[[ "$resolved" == "$sdk_bin/dart" ]] ||
  fail "PATH resolved an unexpected dart: $resolved"
actual=$("$resolved" --version)
printf '%s\n' "$actual"
printf '%s\n' "$actual" | grep -F "$DART_SDK_VERSION" >/dev/null ||
  fail "verified dart reported an unexpected version: $actual"
printf '%s\n' "$sdk_bin" >>"$GITHUB_PATH"
# Keep the extracted SDK for the rest of the job; dart reads sibling files.
trap - EXIT
printf 'verified dart %s at %s\n' "$DART_SDK_VERSION" "$resolved"
