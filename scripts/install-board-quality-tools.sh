#!/usr/bin/env bash
# Install the YueBoard quality binaries without `go run`.
#
# golangci-lint v2.14.0 is the reviewed GitHub release tarball.
# govulncheck v1.8.0 publishes no release binary, so `go install` builds it
# once into DEST. The YueOps/YueBoard toolchain image should run this script
# at image build. A later quality job then finds both binaries on PATH and
# only copies them.
set -euo pipefail

dest="${1:?usage: install-board-quality-tools.sh DEST}"
mkdir -p "$dest"
dest="$(cd -- "$dest" && pwd)"

version_ok() {
  command -v govulncheck >/dev/null 2>&1 \
    && command -v golangci-lint >/dev/null 2>&1 \
    && govulncheck -version | grep -qF 'v1.8.0' \
    && golangci-lint version | grep -qF '2.14.0'
}

copy_tool() {
  name="$1"
  source="$(command -v "$name")"
  if [ "$source" != "$dest/$name" ]; then
    cp "$source" "$dest/$name"
    chmod 0755 "$dest/$name"
  fi
}

if version_ok; then
  copy_tool govulncheck
  copy_tool golangci-lint
  exit 0
fi

[ "$(uname -s)" = Linux ] && [ "$(uname -m)" = x86_64 ] || {
  echo "::error::YueBoard quality tool binaries are pinned for linux/amd64" >&2
  exit 1
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
lint_tar="$tmp/golangci-lint.tar.gz"
curl --fail --location --silent --show-error \
  --proto '=https' --proto-redir '=https' --tlsv1.2 \
  --connect-timeout 10 --max-time 180 \
  --retry 4 --retry-all-errors \
  --output "$lint_tar" \
  https://github.com/golangci/golangci-lint/releases/download/v2.14.0/golangci-lint-2.14.0-linux-amd64.tar.gz
echo "ab90aeb7b066f92a33415b638a50fe5344bbb75a0d32ad30cc248d88f81032ab  $lint_tar" \
  | sha256sum --check --strict
tar -C "$tmp" -xzf "$lint_tar"
install -m 0755 "$tmp/golangci-lint-2.14.0-linux-amd64/golangci-lint" "$dest/golangci-lint"
"$dest/golangci-lint" version | grep -qF '2.14.0'

GOBIN="$dest" GOTOOLCHAIN=local GOPROXY='https://proxy.golang.org,direct' \
  go install golang.org/x/vuln/cmd/govulncheck@v1.8.0
"$dest/govulncheck" -version | grep -qF 'v1.8.0'
