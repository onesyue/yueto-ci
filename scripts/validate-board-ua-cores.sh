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
case "$(uname -m)" in
  x86_64) ua_arch=amd64 ;;
  aarch64|arm64) ua_arch=arm64 ;;
  *) fail 'unsupported native UA architecture' ;;
esac
[ "$(go env GOHOSTOS)" = linux ] && [ "$(go env GOHOSTARCH)" = "$ua_arch" ] \
  || fail 'native Go platform differs from the parser download platform'
ua_platform="linux/$ua_arch"
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
# Resolve only explicit input directories. Never stage a whole home or root.
module_cache=$(cd -- "$module_cache" && pwd -P)
compiler_cache=$(cd -- "$compiler_cache" && pwd -P)
core_cache=$(cd -- "$core_cache" && pwd -P)
ua_home=''
if [ -n "${HOME:-}" ] && [ -d "$HOME" ]; then
  ua_home=$(cd -- "$HOME" && pwd -P)
fi
for path in "$source_dir" "$module_cache" "$compiler_cache" "$core_cache"; do
  [ "$path" != / ] && [ "$path" != "$ua_home" ] || fail 'UA inputs must not be a root or home directory'
done
state=$(mktemp -d "${RUNNER_TEMP:?}/ua-core-ci.XXXXXX")
container_id=''
seed_id=''
volumes=()
record() {
  printf '{"action":"%s","kind":"%s","id":"%s","exit_code":%s}\n' \
    "$1" "$2" "$3" "$4" >> "$state/resources.jsonl"
}
cleanup() {
  local status=$? failed=0 resource code
  for resource in "$container_id" "$seed_id"; do
    [ -n "$resource" ] || continue
    code=0
    docker rm --force "$resource" >>"$state/cleanup.log" 2>&1 || code=$?
    record removed container "$resource" "$code" || failed=1
    [ "$code" -eq 0 ] || failed=1
  done
  for resource in "${volumes[@]-}"; do
    [ -n "$resource" ] || continue
    code=0
    docker volume rm "$resource" >>"$state/cleanup.log" 2>&1 || code=$?
    record removed volume "$resource" "$code" || failed=1
    [ "$code" -eq 0 ] || failed=1
  done
  [ "$failed" -eq 0 ] || status=1
  exit "$status"
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
if ! docker pull --platform "$ua_platform" "$UA_GO_IMAGE" >"$state/pull.stdout" 2>"$state/pull.stderr"; then
  fail 'could not pull the reviewed UA runtime image; no tag fallback is allowed'
fi

# Job-container paths need not exist on the host daemon. Copy only the four
# explicit inputs into fresh anonymous volumes through a stopped seed. No seed
# process executes. The data subdirectory preserves each input root's UID/GID;
# Match the seed user to the parser too: Docker maps the copied root to
# the destination container user even with archive mode.
for role in source cores modules compiler; do
  if ! volume=$(docker volume create --label yueto.ua-role="$role" 2>"$state/volume-$role.stderr"); then
    fail 'could not create an owned UA input volume'
  fi
  [[ "$volume" =~ ^[0-9a-f]{64}$ ]] || fail 'Docker returned an invalid UA volume identity'
  volumes+=("$volume")
  record created volume "$volume" 0
done
if ! seed_id=$(docker create --platform "$ua_platform" --network none \
    --user "$(id -u):$(id -g)" \
    --cap-drop ALL --security-opt no-new-privileges \
    --mount "type=volume,src=${volumes[0]},dst=/seed/source" \
    --mount "type=volume,src=${volumes[1]},dst=/seed/cores" \
    --mount "type=volume,src=${volumes[2]},dst=/seed/modules" \
    --mount "type=volume,src=${volumes[3]},dst=/seed/compiler" \
    "$UA_GO_IMAGE" true 2>"$state/seed-create.stderr"); then
  seed_id=''
  fail 'could not create the stopped UA input seed'
fi
if [[ ! "$seed_id" =~ ^[0-9a-f]{64}$ ]]; then
  seed_id=''
  fail 'Docker returned an invalid UA seed identity'
fi
record created container "$seed_id" 0
paths=("$source_dir" "$core_cache" "$module_cache" "$compiler_cache")
roles=(source cores modules compiler)
for index in 0 1 2 3; do
  if ! docker cp -a "${paths[$index]}" "$seed_id:/seed/${roles[$index]}/data" \
      >"$state/copy-${roles[$index]}.stdout" 2>"$state/copy-${roles[$index]}.stderr"; then
    fail 'could not stage an owned UA input; no parser was executed'
  fi
done

# Only these volumes enter the parser. Source remains read-only, no parent
# container mounts or host home are shared, and no credential is forwarded.
# Docker defaults tmpfs to noexec; Go must execute its temporary test binaries.
if ! container_id=$(docker create --platform "$ua_platform" --network none --cpus 2 --memory 4g \
    --cap-drop ALL --security-opt no-new-privileges --read-only \
    --user "$(id -u):$(id -g)" --tmpfs /tmp:rw,exec,nosuid,nodev \
    --mount "type=volume,src=${volumes[0]},dst=/source,readonly" \
    --mount "type=volume,src=${volumes[1]},dst=/cores" \
    --mount "type=volume,src=${volumes[2]},dst=/go-mod" \
    --mount "type=volume,src=${volumes[3]},dst=/go-build" \
    -e TZ=UTC -e HOME=/tmp/ua-home -e GOMODCACHE=/go-mod/data -e GOCACHE=/go-build/data \
    -e GOPROXY=off -e GOSUMDB=off -e GOTOOLCHAIN=local \
    -e UA_GO_ARCH="$ua_arch" -e CGO_ENABLED=1 -e YUEBOARD_CORE_GATE_PROCS=2 -e GOMAXPROCS=2 \
    -w /source/data "$UA_GO_IMAGE" bash -c '
      set -euo pipefail
      mkdir -p "$HOME"
      [ "$(go env GOVERSION)" = go1.27.4 ]
      [ "$(go env GOHOSTOS)" = linux ]
      [ "$(go env GOHOSTARCH)" = "$UA_GO_ARCH" ]
      bash scripts/ci/ua-core-gate.sh --cache-dir /cores/data
    ' 2>"$state/create.stderr"); then
  container_id=''
  fail 'could not create the isolated UA container'
fi
if [[ ! "$container_id" =~ ^[0-9a-f]{64}$ ]]; then
  container_id=''
  fail 'Docker returned an invalid UA container identity'
fi
record created container "$container_id" 0
timeout --signal=TERM --kill-after=15s 18m docker start --attach "$container_id"
[ "$(docker inspect --format '{{.State.Status}} {{.State.ExitCode}}' "$container_id")" = 'exited 0' ] \
  || fail 'isolated UA gate did not finish successfully'
