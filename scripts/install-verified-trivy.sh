#!/usr/bin/env bash
# CI scanner only: installs a reviewed Trivy binary for this job and puts it
# first on PATH for the following steps. No daemon, package or builder change.
#
# Why (C6, 2026-09-27): trivy-action's own setup (aquasecurity/setup-trivy)
# downloads Trivy at run time and checks it only against a checksum file from
# the same release -- a same-origin check. The build job that runs the scan
# also holds `id-token: write` (Sigstore keyless signing) and
# `packages: write`, so the scanner binary executes next to the production
# signing identity. Pin its bytes exactly like Buildx and actionlint: one
# reviewed version, one reviewed sha256, verified before the first execution.
#
# Published 2026-08-14T11:29:11Z. The GitHub release asset digest and the
# release's trivy_0.74.0_checksums.txt agree on the value below (read
# 2026-09-27).
set -euo pipefail
umask 077
readonly TRIVY_VERSION='0.74.0'
readonly TRIVY_ARCHIVE_SHA256='2ae6fe3ee734b7fdf11335663e18c75ea12dccc76062f09f164a3b0f8be4371a'

fail() { echo "::error::$*" >&2; exit 1; }
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] ||
  fail 'Trivy artifact is reviewed only for Linux x86_64 runners'
[[ -n "${RUNNER_TEMP:-}" && -d "$RUNNER_TEMP" ]] ||
  fail 'RUNNER_TEMP must identify an existing runner temporary directory'
[[ -n "${GITHUB_PATH:-}" ]] ||
  fail 'GITHUB_PATH is required to hand the verified Trivy to later steps'

install_dir=$(mktemp -d "$RUNNER_TEMP/yueto-trivy.XXXXXXXX")
archive="$install_dir/trivy.tar.gz"
curl --fail --location --silent --show-error \
  --proto '=https' --proto-redir '=https' --tlsv1.2 \
  --connect-timeout 10 --max-time 180 --retry 3 --retry-all-errors \
  "https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}/trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz" \
  --output "$archive"
printf '%s  %s\n' "$TRIVY_ARCHIVE_SHA256" "$archive" | sha256sum --check --strict
mkdir -m 0700 "$install_dir/bin"
tar --extract --gzip --file "$archive" --directory "$install_dir/bin" --no-same-owner trivy
rm -f -- "$archive"
[[ -f "$install_dir/bin/trivy" && ! -L "$install_dir/bin/trivy" ]] ||
  fail 'verified archive did not contain a regular trivy binary'
chmod 0755 "$install_dir/bin" "$install_dir/bin/trivy"

# Check what later steps will actually resolve: GITHUB_PATH prepends, so the
# verified copy must win over any trivy already on the runner's PATH.
resolved=$(PATH="$install_dir/bin:$PATH" command -v trivy)
[[ "$resolved" == "$install_dir/bin/trivy" ]] ||
  fail "PATH resolved an unexpected trivy: $resolved"
actual=$("$resolved" --version | sed -n '1p')
[[ "$actual" == "Version: $TRIVY_VERSION" ]] ||
  fail "verified Trivy reported an unexpected version: $actual"
printf '%s\n' "$install_dir/bin" >>"$GITHUB_PATH"
printf 'verified trivy %s at %s\n' "$TRIVY_VERSION" "$resolved"
