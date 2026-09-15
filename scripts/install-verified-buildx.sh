#!/usr/bin/env bash
# CI client only: no daemon restart, builder creation or production package change.
# Published 2026-09-11T15:35:46Z; GitHub release asset digest and checksums.txt agree.
set -euo pipefail
umask 077
readonly BUILDX_VERSION='v0.37.1'
readonly BUILDX_SHA256='9447199cdb435f25880548343c128a4b6650e8891ee598905d8d29d39a8e359b'

fail() { echo "::error::$*" >&2; exit 1; }
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] ||
  fail 'Buildx artifact is reviewed only for Linux x86_64 runners'
[[ -n "${RUNNER_TEMP:-}" && -d "$RUNNER_TEMP" ]] ||
  fail 'RUNNER_TEMP must identify an existing runner temporary directory'
config_dir="${DOCKER_CONFIG:-$HOME/.docker}"
plugin_dir="$config_dir/cli-plugins"
plugin="$plugin_dir/docker-buildx"
[[ ! -L "$plugin_dir" && ! -L "$plugin" ]] ||
  fail 'refusing symlinked Buildx plugin directory or binary'
[[ ! -e "$plugin" || -f "$plugin" ]] || fail 'Buildx destination is not a regular file'
# Docker searches cliPluginsExtraDirs before this user plugin directory. Refuse
# that override before even requesting plugin metadata (which executes it).
python3 - "$config_dir/config.json" <<'PY'
import json
from pathlib import Path
import sys
path = Path(sys.argv[1])
if path.exists():
    config = json.loads(path.read_text())
    if not isinstance(config, dict) or config.get("cliPluginsExtraDirs") not in (None, []):
        raise SystemExit("::error::unreviewed Docker plugin search override")
PY
mkdir -p "$plugin_dir"

download_dir=''
staged=''
cleanup() {
  if [[ -n "$staged" ]]; then rm -f -- "$staged"; fi
  if [[ -n "$download_dir" ]]; then
    rm -f -- "$download_dir/docker-buildx"
    rmdir -- "$download_dir"
  fi
}
trap cleanup EXIT

# setup-buildx-action intentionally reuses an available runner plugin. Ensure
# those bytes are reviewed before the action can create a privileged builder.
if [[ ! -f "$plugin" || ! -x "$plugin" ]] ||
   ! printf '%s  %s\n' "$BUILDX_SHA256" "$plugin" | sha256sum --check --status; then
  download_dir=$(mktemp -d "$RUNNER_TEMP/yueto-buildx.XXXXXXXX")
  curl --fail --location --silent --show-error \
    --proto '=https' --proto-redir '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 120 --retry 3 --retry-all-errors \
    "https://github.com/docker/buildx/releases/download/$BUILDX_VERSION/buildx-$BUILDX_VERSION.linux-amd64" \
    --output "$download_dir/docker-buildx"
  printf '%s  %s\n' "$BUILDX_SHA256" "$download_dir/docker-buildx" |
    sha256sum --check --strict
  staged=$(mktemp "$plugin_dir/.docker-buildx.XXXXXXXX")
  install -m 0755 "$download_dir/docker-buildx" "$staged"
  mv -f -- "$staged" "$plugin"
  staged=''
fi

# Check the actual Docker lookup too: a higher-priority shadow plugin must not
# silently return an old version despite a correct file at the expected path.
actual=$(docker buildx version)
[[ "$actual" == "github.com/docker/buildx $BUILDX_VERSION "* ]] ||
  fail "Docker resolved an unexpected Buildx version: $actual"
printf '%s\n' "$actual"
