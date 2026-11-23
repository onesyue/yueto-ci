#!/bin/bash
# Local and hosted validation read the same release from the policy checkout.
set -euo pipefail
root=${RUNNER_TEMP:?}/node-toolchain
policy=${GITHUB_WORKSPACE:?}/.ci-policy
version=$(<"$policy/.node-version")
[[ "$version" =~ ^24\.[0-9]+\.[0-9]+$ ]] || {
  echo 'Expected an exact Node 24 release in .node-version' >&2
  exit 1
}
release="https://nodejs.org/dist/v$version"
archive="node-v$version-linux-x64.tar.xz"
mkdir -p "$root"
source "$policy/scripts/ci-retry.sh"
ci_download 5 --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
  "$release/SHASUMS256.txt" --output "$root/SHASUMS256.txt"
ci_download 5 --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
  "$release/$archive" --output "$root/$archive"
(cd "$root" && awk -v name="$archive" '$2 == name' SHASUMS256.txt | sha256sum --check --strict)
tar -xJf "$root/$archive" -C "$root"
bin="$root/${archive%.tar.xz}/bin"
"$bin/node" --version
printf '%s\n' "$bin" >> "${GITHUB_PATH:?}"
