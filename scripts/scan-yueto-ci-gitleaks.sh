#!/usr/bin/env bash
# Scan yueto-ci for new secrets.
#
# The current tree is every tracked file plus untracked files that are not
# gitignored. On a pull request or a master push, the commits unique to that
# range are scanned too. Full history is never scanned: a historical live
# token still in git history would fail a full-history scan forever, and
# allowlisting it would hide a real secret.
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"

# shellcheck source=scripts/ci-retry.sh
source "$root/scripts/ci-retry.sh"

readonly GITLEAKS_VERSION='8.30.1'
readonly GITLEAKS_ARCHIVE_SHA256='551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb'
readonly GITLEAKS_RELEASE_URL='https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz'
readonly GITLEAKS_ZERO_SHA='0000000000000000000000000000000000000000'

fail() { echo "::error::$*" >&2; exit 1; }

sha40() { [[ "$1" =~ ^[0-9a-f]{40}$ ]]; }

install_pinned() {
  local temp dest archive
  temp=${RUNNER_TEMP:-${TMPDIR:-/tmp}}
  [[ -d "$temp" ]] || fail 'temporary directory missing'
  dest=$(mktemp -d "$temp/yueto-gitleaks.XXXXXXXX")
  archive="$dest/gitleaks.tar.gz"
  if ! ci_download 4 --fail --location --silent --show-error \
    --proto '=https' --proto-redir '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 180 \
    "$GITLEAKS_RELEASE_URL" \
    --output "$archive"; then
    echo "GitHub release front failed; using the asset API" >&2
    rm -f -- "$archive"
    ci_release_asset_api 4 "$archive" "$GITLEAKS_RELEASE_URL"
  fi
  printf '%s  %s\n' "$GITLEAKS_ARCHIVE_SHA256" "$archive" | sha256sum --check --strict >&2
  tar --extract --gzip --file "$archive" --directory "$dest" --no-same-owner gitleaks
  rm -f -- "$archive"
  [[ -f "$dest/gitleaks" && ! -L "$dest/gitleaks" ]] ||
    fail 'verified archive did not contain a regular gitleaks binary'
  chmod 0755 "$dest/gitleaks"
  [[ "$("$dest/gitleaks" version 2>/dev/null)" == "$GITLEAKS_VERSION" ]] ||
    fail 'pinned gitleaks reported an unexpected version'
  printf '%s\n' "$dest/gitleaks"
}

resolve_gitleaks() {
  local found
  if [[ -n "${GITLEAKS_BIN:-}" ]]; then
    [[ -x "$GITLEAKS_BIN" ]] || fail 'GITLEAKS_BIN is not executable'
    [[ "$("$GITLEAKS_BIN" version 2>/dev/null)" == "$GITLEAKS_VERSION" ]] ||
      fail 'GITLEAKS_BIN is not gitleaks 8.30.1'
    printf '%s\n' "$GITLEAKS_BIN"
    return
  fi
  if [[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]]; then
    install_pinned
    return
  fi
  found=$(command -v gitleaks || true)
  [[ -n "$found" ]] || fail 'gitleaks 8.30.1 is required'
  [[ "$("$found" version 2>/dev/null)" == "$GITLEAKS_VERSION" ]] ||
    fail 'PATH gitleaks is not 8.30.1; Linux x86_64 CI installs the digest-pinned tarball'
  printf '%s\n' "$found"
}

commit_range() {
  local base=${SCAN_BASE:-} head=${SCAN_HEAD:-}
  if [[ -z "$base" && -z "$head" ]]; then
    printf 'gitleaks range skipped: no commit range\n' >&2
    return 0
  fi
  if [[ "$base" == "$GITLEAKS_ZERO_SHA" ]]; then
    printf 'gitleaks range skipped: push has no ancestor\n' >&2
    return 0
  fi
  sha40 "$base" && sha40 "$head" ||
    fail 'refusing gitleaks range; expected two 40-character SHAs or an empty range'
  git -C "$root" cat-file -e "${base}^{commit}" ||
    fail 'refusing gitleaks range; base commit is not in this clone'
  git -C "$root" cat-file -e "${head}^{commit}" ||
    fail 'refusing gitleaks range; head commit is not in this clone'
  printf '%s..%s\n' "$base" "$head"
}

summarize_report() {
  local report=$1 status=0
  python3 - "$report" <<'PY' || status=$?
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.is_file() or path.stat().st_size == 0:
    raise SystemExit(0)
findings = json.loads(path.read_text(encoding="utf-8"))
if not isinstance(findings, list):
    raise SystemExit("gitleaks report was not a list")
for item in findings:
    if not isinstance(item, dict):
        continue
    rule = str(item.get("RuleID", ""))
    filename = str(item.get("File", ""))
    line = item.get("StartLine", "")
    print(f"gitleaks finding {rule} {filename}:{line}", file=sys.stderr)
PY
  rm -f -- "$report"
  return "$status"
}

scan_tree() {
  local bin=$1 dest report rc=0
  dest=$(mktemp -d "${TMPDIR:-/tmp}/yueto-gitleaks-tree.XXXXXXXX")
  report=$(mktemp "${TMPDIR:-/tmp}/yueto-gitleaks-report.XXXXXXXX")
  (
    set -euo pipefail
    while IFS= read -r -d '' file; do
      mkdir -p "$dest/$(dirname -- "$file")"
      cp -p -- "$root/$file" "$dest/$file"
    done < <(git -C "$root" ls-files -z -co --exclude-standard)
    "$bin" dir --no-banner --redact --log-level error \
      --config "$root/.gitleaks.toml" \
      --report-format json --report-path "$report" \
      "$dest"
  ) || rc=$?
  summarize_report "$report" || rc=$?
  rm -rf -- "$dest"
  return "$rc"
}

scan_commits() {
  local bin=$1 range=$2 report rc=0
  [[ -n "$range" ]] || return 0
  report=$(mktemp "${TMPDIR:-/tmp}/yueto-gitleaks-report.XXXXXXXX")
  "$bin" git --no-banner --redact --log-level error \
    --config "$root/.gitleaks.toml" \
    --log-opts="$range" \
    --report-format json --report-path "$report" \
    "$root" || rc=$?
  summarize_report "$report" || rc=$?
  return "$rc"
}

main() {
  local bin range tree_rc=0 commit_rc=0
  range=$(commit_range)
  bin=$(resolve_gitleaks)
  scan_tree "$bin" || tree_rc=$?
  scan_commits "$bin" "$range" || commit_rc=$?
  if [[ "$tree_rc" -ne 0 ]]; then
    exit "$tree_rc"
  fi
  exit "$commit_rc"
}

main "$@"
