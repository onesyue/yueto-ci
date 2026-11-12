#!/bin/bash
# ci-check.sh <repo> <sha> [--local]
# Dispatch build.yml validation_only and print failing pytest node ids.
# --local runs the same planner, then the published toolchain image in docker.
# YueOps only. Other repositories are a later extension. Does not promote.

set -euo pipefail
unset CDPATH

ROOT=$(cd -- "$(dirname "$0")/.." && pwd)
IMAGE=ghcr.io/onesyue/yueops-ci-toolchain@sha256:96b3439fd16effe9686cb6297026e97fac605db4d1ab8ce674aa45c121873017
SHA_RE='^[0-9a-f]{40}$'
SHORT_RE='^[0-9a-f]{7,40}$'

usage() {
  echo "usage: ci-check.sh <repo> <sha> [--local]" >&2
  exit 2
}

fail() {
  echo "ci-check: $*" >&2
  exit 2
}

[ "$#" -eq 2 ] || [ "$#" -eq 3 ] || usage
repo=$1
raw_sha=$2
mode=remote
if [ "$#" -eq 3 ]; then
  [ "$3" = "--local" ] || usage
  mode=local
fi
[ "$repo" = "yueops" ] || fail "B9-9 validates yueops; other repositories are not wired here"
[[ "$raw_sha" =~ $SHORT_RE ]] || fail "sha must be 7 to 40 lowercase hex characters"

resolve_sha() {
  local candidate=$1
  if [[ "$candidate" =~ $SHA_RE ]]; then
    printf '%s\n' "$candidate"
    return 0
  fi
  gh api --method GET "repos/onesyue/${repo}/commits/${candidate}" --jq '.sha'
}

full_sha=$(resolve_sha "$raw_sha")
[[ "$full_sha" =~ $SHA_RE ]] || fail "could not resolve ${raw_sha} to a 40-hex commit"

migration_base() {
  if [ -n "${CI_CHECK_MIGRATION_BASE:-}" ]; then
    [[ "$CI_CHECK_MIGRATION_BASE" =~ $SHA_RE ]] || fail "CI_CHECK_MIGRATION_BASE must be 40 hex"
    printf '%s\n' "$CI_CHECK_MIGRATION_BASE"
    return 0
  fi
  gh api --method GET "repos/onesyue/${repo}/commits/${full_sha}" --jq '.parents[0].sha // empty'
}

base=$(migration_base)
[[ "$base" =~ $SHA_RE ]] || fail "migration base must be an explicit 40-hex parent or CI_CHECK_MIGRATION_BASE"

ops_checkout() {
  if [ -n "${YUEOPS_CHECKOUT:-}" ]; then
    printf '%s\n' "$YUEOPS_CHECKOUT"
    return 0
  fi
  if [ -e "$ROOT/../yueops/.git" ]; then
    cd -- "$ROOT/../yueops" && pwd
    return 0
  fi
  if [ -e /Users/j/Projects/yueto/yueops/.git ]; then
    printf '%s\n' /Users/j/Projects/yueto/yueops
    return 0
  fi
  local dest
  dest=$(mktemp -d "${TMPDIR:-/tmp}/ci-check-yueops.XXXXXX")
  git clone --quiet "https://github.com/onesyue/${repo}.git" "$dest"
  printf '%s\n' "$dest"
}

prepare_source() {
  local ops src
  ops=$(ops_checkout)
  git -C "$ops" cat-file -e "${full_sha}^{commit}" 2>/dev/null || git -C "$ops" fetch --quiet origin "$full_sha"
  src=$(mktemp -d "${TMPDIR:-/tmp}/ci-check-src.XXXXXX")
  git -C "$ops" worktree add --detach "$src" "$full_sha" >/dev/null
  printf '%s\n' "$src"
}

board_pin() {
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["yueboard_contract_pin"])' \
    "$ROOT/native-node-contract.json"
}

write_targets() {
  local dest=$1
  python3 - "$full_sha" "$dest" <<'PY'
import json, sys
sha, dest = sys.argv[1:]
row = {"validation": "yueops", "repo": "onesyue/yueops", "ref": sha}
json.dump({"matrix": [], "validation_matrix": [row], "has_builds": False}, open(dest, "w"))
PY
}

planner_env() {
  export GITHUB_SHA
  GITHUB_SHA=$(git -C "$ROOT" rev-parse HEAD)
  export GITHUB_RUN_ID="${GITHUB_RUN_ID:-1}"
  export GITHUB_RUN_ATTEMPT="${GITHUB_RUN_ATTEMPT:-1}"
  export GITHUB_REPOSITORY=onesyue/yueto-ci
  export RUNNER_OS="${RUNNER_OS:-Linux}"
  export RUNNER_ARCH="${RUNNER_ARCH:-X64}"
}

run_expand() {
  local source=$1 dest=$2 targets
  targets=$(mktemp "${TMPDIR:-/tmp}/ci-check-targets.XXXXXX")
  write_targets "$targets"
  planner_env
  python3 "$ROOT/scripts/pytest-shards.py" expand \
    --targets "$targets" --source "$source" --board "$(board_pin)" \
    --runner ubuntu-24.04 --capacity 20 --shards 16 --validation-only \
    >"$dest"
  rm -f -- "$targets"
}

print_ids() {
  python3 "$ROOT/scripts/ci_check_failures.py"
}

board_checkout() {
  local pin repo dest
  pin=$(board_pin)
  [[ "$pin" =~ $SHA_RE ]] || fail "yueboard contract pin is not 40 hex"
  if [ -n "${YUEBOARD_CHECKOUT:-}" ]; then
    repo=$YUEBOARD_CHECKOUT
  elif [ -e /Users/j/Projects/yueto/yueboard/.git ]; then
    repo=/Users/j/Projects/yueto/yueboard
  else
    fail "set YUEBOARD_CHECKOUT to a yueboard clone for --local"
  fi
  git -C "$repo" cat-file -e "${pin}^{commit}" 2>/dev/null || git -C "$repo" fetch --quiet origin "$pin"
  dest=$(mktemp -d "${TMPDIR:-/tmp}/ci-check-board.XXXXXX")
  rmdir "$dest"
  git -C "$repo" worktree add --detach "$dest" "$pin" >/dev/null
  printf '%s\n' "$dest"
}

remove_worktree() {
  local path=$1 common
  [ -n "$path" ] && [ -d "$path" ] || return 0
  common=$(git -C "$path" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)
  if [ -n "$common" ]; then
    git --git-dir="$common" worktree remove --force "$path" >/dev/null 2>&1 || true
  fi
  rm -rf -- "$path"
}

local_pytest() {
  local source=$1 admission=$2 board=$3
  command -v docker >/dev/null || fail "docker is required for --local"
  docker pull "$IMAGE" >/dev/null || fail "toolchain image is not available; not rebuilding it"
  local log docker_rc=0 id_rc=0
  log=$(mktemp "${TMPDIR:-/tmp}/ci-check-pytest.XXXXXX")
  docker run --rm \
    --user runner \
    -e TZ=UTC \
    -e YUEBOARD_REPO_PATH=/board \
    -e YUEBOARD_TEST_DATABASE_URL=postgres://postgres:ci@127.0.0.1:5432/yueboard_test \
    -e YUEBOARD_TRAFFIC_TEST_DATABASE_URL=postgres://postgres:ci@127.0.0.1:5432/yueboard_test \
    -e YUEBOARD_EMAILVERIFY_TEST_DATABASE_URL=postgres://postgres:ci@127.0.0.1:5432/yueboard_test \
    -v "$source:/src:rw" \
    -v "$board:/board:ro" \
    -v "$admission:/admission.json:ro" \
    -v "$ROOT/native-node-contract.json:/contract.json:ro" \
    -w /src \
    "$IMAGE" \
    bash -s <<'EOS' >"$log" 2>&1 || docker_rc=$?
set -euo pipefail
data=$(mktemp -d)
initdb -D "$data" --username=postgres --auth=trust >/dev/null
pg_ctl -D "$data" -l "$data/log" -o "-k $data -c listen_addresses=127.0.0.1 -c port=5432" start >/dev/null
psql -h 127.0.0.1 -U postgres -d postgres -v ON_ERROR_STOP=1 -c 'CREATE DATABASE yueboard_test' >/dev/null
uv venv /tmp/ci-venv >/dev/null
# shellcheck disable=SC1091
. /tmp/ci-venv/bin/activate
uv pip install --quiet -r requirements.txt pytest
python3 - <<'PY'
import json, subprocess, sys
admission = json.load(open("/admission.json"))
plan = admission["ops_plan"]
failed = False
for assignment in plan["assignments"]:
    modules = assignment["modules"]
    if not modules:
        continue
    print(f"::shard::{assignment['id']}", flush=True)
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", "--tb=line", *modules], check=False)
    if result.returncode not in (0, 5):
        failed = True
sys.exit(1 if failed else 0)
PY
EOS
  print_ids <"$log" || id_rc=$?
  rm -f -- "$log"
  if [ "$id_rc" -ne 0 ]; then
    return "$id_rc"
  fi
  if [ "$docker_rc" -ne 0 ]; then
    echo "ci-check: local pytest failed with no pytest node ids" >&2
    return 1
  fi
}

remote_dispatch() {
  local branch since
  branch=$(git -C "$ROOT" rev-parse --abbrev-ref HEAD)
  [ "$branch" != "HEAD" ] || fail "ci-check must run from a named yueto-ci branch"
  git -C "$ROOT" rev-parse --verify --quiet "refs/remotes/origin/${branch}" >/dev/null \
    || fail "push ${branch} before dispatching; the workflow file has to be on origin"
  since=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  gh workflow run build.yml --repo onesyue/yueto-ci --ref "$branch" \
    -f service=yueops \
    -f ref="$full_sha" \
    -f migration_base="$base" \
    -f validation_only=true \
    -f promote=false \
    -f runner=ubuntu-24.04
  local id=""
  local deadline=$((SECONDS + 180))
  while [ "$SECONDS" -lt "$deadline" ]; do
    id=$(gh run list --repo onesyue/yueto-ci --workflow "Build & publish images" \
      --branch "$branch" --limit 20 \
      --json databaseId,displayTitle,createdAt,event,status \
      --jq ".[] | select(.event==\"workflow_dispatch\" and .createdAt>=\"${since}\" and (.displayTitle|tostring|contains(\"${full_sha}\"))) | .databaseId" \
      | head -n 1 || true)
    if [ -n "$id" ]; then
      break
    fi
    sleep 5
  done
  [ -n "$id" ] || fail "dispatched run for ${full_sha} did not appear"
  echo "ci-check: run ${id}" >&2
  gh run watch "$id" --repo onesyue/yueto-ci --exit-status >/dev/null || true
  local log id_rc=0 conclusion
  log=$(mktemp "${TMPDIR:-/tmp}/ci-check-remote.XXXXXX")
  gh run view "$id" --repo onesyue/yueto-ci --log-failed >"$log" || true
  print_ids <"$log" || id_rc=$?
  rm -f -- "$log"
  if [ "$id_rc" -ne 0 ]; then
    return "$id_rc"
  fi
  conclusion=$(gh run view "$id" --repo onesyue/yueto-ci --json conclusion --jq .conclusion)
  if [ "$conclusion" != "success" ]; then
    echo "ci-check: run ${id} finished ${conclusion} with no pytest node ids" >&2
    return 1
  fi
}

source=$(prepare_source)
board=""
admission=""
cleanup() {
  remove_worktree "$source"
  remove_worktree "$board"
  if [ -n "${admission:-}" ]; then
    rm -f -- "$admission"
  fi
}
trap cleanup EXIT

admission=$(mktemp "${TMPDIR:-/tmp}/ci-check-admission.XXXXXX")
run_expand "$source" "$admission"
echo "ci-check: plan accepted ${repo} ${full_sha}" >&2

if [ "$mode" = "local" ]; then
  board=$(board_checkout)
  local_pytest "$source" "$admission" "$board"
else
  remote_dispatch
fi
