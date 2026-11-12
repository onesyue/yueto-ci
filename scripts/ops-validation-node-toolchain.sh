#!/bin/bash
# The same Node 24 resolver runs locally and in the hosted toolchain container.
set -euo pipefail
root=${RUNNER_TEMP:?}/node-toolchain
mkdir -p "$root"
source "${GITHUB_WORKSPACE:?}/.ci-policy/scripts/ci-retry.sh"
ci_download 5 --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
  https://nodejs.org/dist/latest-v24.x/SHASUMS256.txt --output "$root/SHASUMS256.txt"
archive=$(awk '$2 ~ /^node-v24\.[0-9]+\.[0-9]+-linux-x64\.tar\.xz$/ {print $2}' "$root/SHASUMS256.txt")
[[ "$archive" =~ ^node-v24\.[0-9]+\.[0-9]+-linux-x64\.tar\.xz$ ]] || {
  echo 'Node 24 release metadata must select exactly one Linux x64 archive' >&2
  exit 1
}
ci_download 5 --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
  "https://nodejs.org/dist/latest-v24.x/$archive" --output "$root/$archive"
(cd "$root" && awk -v name="$archive" '$2 == name' SHASUMS256.txt | sha256sum --check --strict)
tar -xJf "$root/$archive" -C "$root"
bin="$root/${archive%.tar.xz}/bin"
"$bin/node" --version
printf '%s\n' "$bin" >> "${GITHUB_PATH:?}"
