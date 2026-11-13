#!/usr/bin/env bash
# Install the YueBoard quality binaries without `go run`.
#
# Versions and existing artifact digests come from lint-tool-versions.sh.
# Prefer exact installed versions; otherwise install authenticated Linux tools.
set -euo pipefail
unset CDPATH
unset LINT_TOOL_VERSIONS_READY
# shellcheck source=scripts/lint-tool-versions.sh
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/lint-tool-versions.sh"
[ "${LINT_TOOL_VERSIONS_READY:-}" = 1 ] || { echo 'missing lint tool version authority' >&2; exit 2; }

dest="${1:?usage: install-board-quality-tools.sh DEST}"
mkdir -p "$dest"
dest="$(cd -- "$dest" && pwd)"

version_ok() {
  command -v govulncheck >/dev/null 2>&1 \
    && command -v golangci-lint >/dev/null 2>&1 \
    && govulncheck -version | grep -qF "$GOVULNCHECK_VERSION" \
    && golangci-lint version | grep -qF "$GOLANGCI_LINT_VERSION"
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
  "https://github.com/golangci/golangci-lint/releases/download/v${GOLANGCI_LINT_VERSION}/golangci-lint-${GOLANGCI_LINT_VERSION}-linux-amd64.tar.gz"
echo "$GOLANGCI_LINT_SHA256  $lint_tar" \
  | sha256sum --check --strict
tar -C "$tmp" -xzf "$lint_tar"
install -m 0755 "$tmp/golangci-lint-${GOLANGCI_LINT_VERSION}-linux-amd64/golangci-lint" "$dest/golangci-lint"
"$dest/golangci-lint" version | grep -qF "$GOLANGCI_LINT_VERSION"

GOBIN="$dest" GOTOOLCHAIN=local GOPROXY='https://proxy.golang.org,direct' \
  go install "golang.org/x/vuln/cmd/govulncheck@$GOVULNCHECK_VERSION"
"$dest/govulncheck" -version | grep -qF "$GOVULNCHECK_VERSION"
