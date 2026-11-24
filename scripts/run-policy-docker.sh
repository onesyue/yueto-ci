#!/usr/bin/env bash
# Replay official policy checks in the local Linux/amd64 policy-test image.
# This is a read-only local runner. It never pushes an image, never tags a
# published digest, and never mounts or copies user credentials.
set -euo pipefail

usage() {
  echo 'usage: scripts/run-policy-docker.sh [--image NAME] [--build] [--preflight] [--prepare-only] [--keep-snapshot] [ci|quick]' >&2
  exit 2
}

image=yueto-policy-test
build=0
preflight=0
prepare_only=0
keep_snapshot=0
mode=ci

while (( $# )); do
  case $1 in
    --image)
      [[ $# -ge 2 && -n $2 ]] || usage
      image=$2
      shift 2
      ;;
    --build)
      build=1
      shift
      ;;
    --preflight)
      preflight=1
      shift
      ;;
    --prepare-only)
      prepare_only=1
      shift
      ;;
    --keep-snapshot)
      keep_snapshot=1
      shift
      ;;
    ci|quick)
      mode=$1
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      usage
      ;;
  esac
done

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd -- "$root"

if ! git -C "$root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "policy docker: $root is not a git checkout; refusing to run without verifiable git metadata" >&2
  exit 2
fi

source_head=$(git -C "$root" rev-parse HEAD)
if [[ ! "$source_head" =~ ^[0-9a-f]{40}$ ]]; then
  echo "policy docker: could not resolve a 40-character HEAD" >&2
  exit 2
fi

gitdir_file=$root/.git
snapshot=
cleanup() {
  if [[ $keep_snapshot -eq 0 && -n ${snapshot:-} && -d $snapshot ]]; then
    chmod -R u+w "$snapshot" 2>/dev/null || true
    rm -rf "$snapshot"
  fi
}
trap cleanup EXIT

is_worktree=0
if [[ -f $gitdir_file ]]; then
  is_worktree=1
elif [[ ! -d $gitdir_file ]]; then
  echo "policy docker: $root/.git is neither a directory nor a worktree pointer" >&2
  exit 2
fi

prepare_snapshot() {
  local dest bundle template
  dest=$(mktemp -d "${TMPDIR:-/tmp}/yueto-policy-snap.XXXXXX")
  bundle=$dest/src.bundle
  template=$dest/empty-template
  mkdir -p "$template"
  # Bundle current history only. This does not copy hooks, remotes, or
  # credential helpers from the user's gitdir, and does not rewrite it.
  # The clone itself is isolated from the user's system/global gitconfig.
  git -C "$root" bundle create --quiet "$bundle" HEAD
  GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_SYSTEM=/dev/null GIT_CONFIG_GLOBAL=/dev/null \
    git -c advice.detachedHead=false clone --quiet --template="$template" "$bundle" "$dest/src"
  rm -f "$bundle"
  git -C "$dest/src" remote remove origin >/dev/null 2>&1 || true
  git -C "$dest/src" config --local --unset-all credential.helper >/dev/null 2>&1 || true
  git -C "$dest/src" config --local --unset-all http.extraHeader >/dev/null 2>&1 || true
  # An empty local helper resets the helper list if this snapshot is later
  # inspected on a host that has a global credential.helper.
  git -C "$dest/src" config --local credential.helper ''
  rm -rf "$dest/src/.git/hooks"
  mkdir -p "$dest/src/.git/hooks"
  # Official image runs as uid 1000; mktemp is mode 0700.
  chmod -R a+rX "$dest"
  snapshot=$dest
}

if [[ $is_worktree -eq 1 ]]; then
  echo "policy docker: worktree detected ($(sed -n 's/^gitdir: //p' "$gitdir_file")); naive \$PWD:/policy mount would hide git metadata" >&2
  echo "policy docker: preparing a disposable credential-free snapshot with a real .git directory" >&2
  prepare_snapshot
  snap_head=$(git -C "$snapshot/src" rev-parse HEAD)
  if [[ $snap_head != "$source_head" ]]; then
    echo "policy docker: snapshot HEAD $snap_head does not match source $source_head" >&2
    exit 2
  fi
  if [[ -f $snapshot/src/.git || ! -d $snapshot/src/.git ]]; then
    echo "policy docker: snapshot is missing independent .git metadata" >&2
    exit 2
  fi
  if git -C "$snapshot/src" config --local --get-regexp '^http\.extraHeader' >/dev/null 2>&1; then
    echo "policy docker: snapshot retained http.extraHeader" >&2
    exit 2
  fi
  helper=$(git -C "$snapshot/src" config --local --get-all credential.helper || true)
  if [[ -n $helper ]]; then
    echo "policy docker: snapshot retained credential.helper=$helper" >&2
    exit 2
  fi
  mount_src=$snapshot/src
  echo "policy docker: snapshot HEAD=$snap_head (matches source); no credential helper; hooks emptied" >&2
else
  mount_src=$root
  echo "policy docker: regular checkout; mounting $root at /policy:ro" >&2
fi

if [[ $prepare_only -eq 1 ]]; then
  printf '%s\n' "$mount_src"
  if [[ $keep_snapshot -eq 1 ]]; then
    trap - EXIT
  fi
  exit 0
fi

if ! command -v docker >/dev/null; then
  echo "policy docker: docker is required for the Linux/amd64 policy-test replay" >&2
  exit 2
fi

if [[ $build -eq 1 ]]; then
  echo "policy docker: building $image locally from images/policy-test/Dockerfile (not pushed)" >&2
  docker build --platform linux/amd64 -f images/policy-test/Dockerfile -t "$image" -- "$root"
fi

if ! docker image inspect "$image" >/dev/null 2>&1; then
  echo "policy docker: image $image is not present; build it with --build (local only, never pushed)" >&2
  exit 2
fi

run_preflight() {
  echo "policy docker: preflight toolset and mount-path diagnostics in $image" >&2
  docker run --rm --platform linux/amd64 \
    -e GIT_CONFIG_COUNT=1 \
    -e GIT_CONFIG_KEY_0=safe.directory \
    -e GIT_CONFIG_VALUE_0=/policy \
    -v "$mount_src:/policy:ro" \
    -w /policy \
    "$image" \
    bash -c '
      set -euo pipefail
      missing=0
      # xz is required inside this image because official tests call tar -cJf
      # (GNU tar). It is intentionally not a host REQUIRED_TOOLS entry.
      for t in bash curl git go gpg gpgv jq node sha256sum tar xz actionlint shellcheck python3; do
        if ! command -v "$t" >/dev/null; then
          echo "policy docker preflight: missing $t" >&2
          missing=1
        else
          echo "policy docker preflight: $t=$(command -v "$t")"
        fi
      done
      python3 -c "import sys,platform; print(\"policy docker preflight: python\", sys.version.split()[0]); print(\"policy docker preflight: platform\", platform.platform())"
      if ! git -C /policy rev-parse --is-inside-work-tree >/dev/null; then
        echo "policy docker preflight: mounted /policy is not a git checkout" >&2
        missing=1
      else
        echo "policy docker preflight: mounted HEAD=$(git -C /policy rev-parse HEAD)"
        if [[ -d /policy/.git ]]; then
          echo "policy docker preflight: /policy/.git is a directory"
        else
          echo "policy docker preflight: /policy/.git is not a directory (worktree pointer was not snapshotted)" >&2
          missing=1
        fi
      fi
      exit "$missing"
    '
}

if [[ $preflight -eq 1 ]]; then
  run_preflight
  exit 0
fi

echo "policy docker: running scripts/check-policy.sh $mode in $image (read-only /policy)" >&2
# Bind only the prepared tree. Do not forward SSH, docker, or credential sockets.
docker run --rm --platform linux/amd64 \
  -e GIT_CONFIG_COUNT=1 \
  -e GIT_CONFIG_KEY_0=safe.directory \
  -e GIT_CONFIG_VALUE_0=/policy \
  -v "$mount_src:/policy:ro" \
  -w /policy \
  "$image" \
  scripts/check-policy.sh "$mode"
