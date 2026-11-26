#!/usr/bin/env bash
# Policy-owned govulncheck bootstrap. The module zip is pinned; go then
# builds cmd/govulncheck from those verified bytes.
set -euo pipefail
unset CDPATH
unset LINT_TOOL_VERSIONS_READY
# shellcheck source=scripts/lint-tool-versions.sh
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/lint-tool-versions.sh"
[ "${LINT_TOOL_VERSIONS_READY:-}" = 1 ] || { echo 'missing lint tool version authority' >&2; exit 2; }
# shellcheck source=scripts/ci-retry.sh
source "$(dirname "${BASH_SOURCE[0]}")/ci-retry.sh"
umask 077

fail() { echo "::error::$*" >&2; exit 1; }
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] ||
  fail 'govulncheck artifact is reviewed only for Linux x86_64 runners'
[[ -n "${RUNNER_TEMP:-}" && -d "$RUNNER_TEMP" ]] ||
  fail 'RUNNER_TEMP must identify an existing runner temporary directory'
[[ -n "${GITHUB_PATH:-}" ]] ||
  fail 'GITHUB_PATH is required to hand the verified govulncheck to later steps'
command -v go >/dev/null 2>&1 || fail 'go is required to build pinned govulncheck'
command -v python3 >/dev/null 2>&1 || fail 'python3 is required to extract the module zip'

scratch=$(mktemp -d "$RUNNER_TEMP/yueto-govulncheck.XXXXXXXX")
trap 'rm -rf -- "$scratch"' EXIT
archive="$scratch/vuln.zip"
zip_url="https://proxy.golang.org/golang.org/x/vuln/@v/${GOVULNCHECK_VERSION}.zip"
ci_download 4 --fail --location --silent --show-error \
  --proto '=https' --proto-redir '=https' --tlsv1.2 \
  --connect-timeout 10 --max-time 180 \
  "$zip_url" \
  --output "$archive"
printf '%s  %s\n' "$GOVULNCHECK_ZIP_SHA256" "$archive" | sha256sum --check --strict
proxy="$scratch/goproxy"
mod_base="$proxy/golang.org/x/vuln/@v"
install -d -m 0755 "$mod_base"
install -m 0644 "$archive" "$mod_base/${GOVULNCHECK_VERSION}.zip"
python3 - "$archive" "$mod_base" "$GOVULNCHECK_VERSION" <<'PY'
import json
import sys
import zipfile
from pathlib import Path

archive, dest, version = sys.argv[1:]
dest_path = Path(dest)
member = f"golang.org/x/vuln@{version}/go.mod"
with zipfile.ZipFile(archive) as bundle:
    try:
        module_file = bundle.read(member)
    except KeyError:
        raise SystemExit(f"verified module zip did not contain {member}") from None
(dest_path / f"{version}.mod").write_bytes(module_file)
(dest_path / f"{version}.info").write_text(
    json.dumps({"Version": version, "Time": "2026-01-01T00:00:00Z"}),
    encoding="utf-8",
)
PY
install_dir="$RUNNER_TEMP/govulncheck-bin"
install -d -m 0755 "$install_dir"
# go install from the verified zip is what stamps Main.Version. A local
# go build of the extracted tree reports govulncheck@v0.0.0 and fails the pin.
GOBIN="$install_dir" \
GOPROXY="file://${proxy}" \
GOSUMDB='sum.golang.org' \
GOTOOLCHAIN=local \
  go install "golang.org/x/vuln/cmd/govulncheck@${GOVULNCHECK_VERSION}"
chmod 0755 "$install_dir/govulncheck"
resolved=$(PATH="$install_dir:$PATH" command -v govulncheck)
[[ "$resolved" == "$install_dir/govulncheck" ]] ||
  fail "PATH resolved an unexpected govulncheck: $resolved"
actual=$("$resolved" -version)
printf '%s\n' "$actual"
printf '%s\n' "$actual" | grep -F "$GOVULNCHECK_VERSION" >/dev/null ||
  fail "verified govulncheck reported an unexpected version: $actual"
printf '%s\n' "$install_dir" >>"$GITHUB_PATH"
printf 'verified govulncheck %s at %s\n' "$GOVULNCHECK_VERSION" "$resolved"
