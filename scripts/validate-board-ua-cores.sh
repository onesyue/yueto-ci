#!/usr/bin/env bash
# Prepare only verified public archives online; execute every parser offline.
set -euo pipefail
readonly UA_GO_VERSION=go1.27.4
readonly UA_GO_IMAGE='golang@sha256:4fa7c968ba93f1635670522dbb01a2c78150443e1385746924566079f36570ea'

fail() { echo "::error::$1" >&2; exit 1; }
for tool in docker go python3 timeout; do
  command -v "$tool" >/dev/null 2>&1 || fail "missing offline UA gate dependency: $tool"
done
[ "$(uname -s)" = Linux ] || fail 'offline UA gate requires Linux Docker'
source_dir=$(pwd -P)
for file in go.mod scripts/ci/core-assets.json scripts/ci/prepare-ua-cores.py scripts/ci/ua-core-gate.sh; do
  [ -f "$source_dir/$file" ] || fail "missing required Board gate input: $file"
done
required=$(awk '$1 == "toolchain" {print $2}' go.mod)
[ "$required" = "$UA_GO_VERSION" ] || fail 'Board toolchain requires a reviewed UA image-pin update'
[ "$(GOTOOLCHAIN=local go env GOVERSION)" = "$UA_GO_VERSION" ] || fail 'host Go cache toolchain differs from the reviewed UA image'
module_cache=$(go env GOMODCACHE)
compiler_cache=$(go env GOCACHE)
core_cache=${UA_CORE_CACHE:?UA_CORE_CACHE must name the task-owned parser cache}
for path in "$source_dir" "$module_cache" "$compiler_cache" "$core_cache"; do
  case "$path" in
    /*) ;;
    *) fail 'offline UA mount paths must be absolute' ;;
  esac
  case "$path" in
    *','*|*$'\n'*|*$'\r'*) fail 'offline UA mount paths cannot contain separators' ;;
  esac
done
mkdir -p "$module_cache" "$compiler_cache" "$core_cache"
state=$(mktemp -d "${RUNNER_TEMP:?}/ua-core-ci.XXXXXX")
container_id=''
cleanup() {
  if [ -n "$container_id" ]; then
    docker rm --force "$container_id" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Do not print downloader diagnostics or export supplied core paths. The Board
# helper validates archive digests again inside the isolated container.
if ! python3 scripts/ci/prepare-ua-cores.py --download-only --cache-dir "$core_cache" \
    >"$state/prepare.json" 2>"$state/prepare.stderr"; then
  fail 'official parser download/verification failed; no parser was executed'
fi
if ! docker pull "$UA_GO_IMAGE" >"$state/pull.stdout" 2>"$state/pull.stderr"; then
  fail 'could not pull the reviewed UA runtime image; no tag fallback is allowed'
fi

# Create first so cleanup owns an exact container ID, never a guessed name.
# Pass only non-secret, fixed environment settings; never inherit GH tokens.
# Docker defaults tmpfs to noexec; Go must execute its temporary test binaries.
if ! container_id=$(docker create --network none --cpus 2 --memory 4g \
    --cap-drop ALL --security-opt no-new-privileges --read-only \
    --user "$(id -u):$(id -g)" --tmpfs /tmp:rw,exec,nosuid,nodev \
    --mount "type=bind,src=$source_dir,dst=/source,readonly" \
    --mount "type=bind,src=$core_cache,dst=/cores" \
    --mount "type=bind,src=$module_cache,dst=/go-mod" \
    --mount "type=bind,src=$compiler_cache,dst=/go-build" \
    -e TZ=UTC -e HOME=/tmp/ua-home -e GOMODCACHE=/go-mod -e GOCACHE=/go-build \
    -e GOPROXY=off -e GOSUMDB=off -e GOTOOLCHAIN=local \
    -e CGO_ENABLED=1 -e YUEBOARD_CORE_GATE_PROCS=2 -e GOMAXPROCS=2 \
    -w /source "$UA_GO_IMAGE" bash -c '
      set -euo pipefail
      mkdir -p "$HOME"
      [ "$(go env GOVERSION)" = go1.27.4 ]
      bash scripts/ci/ua-core-gate.sh --cache-dir /cores
    ' 2>"$state/create.stderr"); then
  container_id=''
  fail 'could not create the isolated UA container'
fi
[[ "$container_id" =~ ^[0-9a-f]{64}$ ]] || fail 'Docker returned an invalid UA container identity'
timeout --signal=TERM --kill-after=15s 18m docker start --attach "$container_id"
[ "$(docker inspect --format '{{.State.Status}} {{.State.ExitCode}}' "$container_id")" = 'exited 0' ] \
  || fail 'isolated UA gate did not finish successfully'
