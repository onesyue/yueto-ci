#!/bin/bash
# ci-check.sh <repo> <sha> [--local] [--board-ref SHA]: validation, never publication.
set -euo pipefail
unset CDPATH
ROOT=$(cd -- "$(dirname "$0")/.." && pwd)
fail() { echo "ci-check: $*" >&2; exit 2; }
usage() { fail 'usage: ci-check.sh <repo> <sha> [--local] [--board-ref SHA]'; }
[ "$#" -ge 2 ] || usage
repo=$1
raw_sha=$2
shift 2
mode=remote
board_sha=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --local) mode=--local; shift ;;
    --board-ref) [ "$#" -ge 2 ] || usage; board_sha=$2; shift 2 ;;
    *) usage ;;
  esac
done
# ci-check is always validation-only. Explicit historical context is never a
# publication default; ordinary use resolves the signed desired Board snapshot.
if [ -z "$board_sha" ]; then
  export YUETO_ROOT=${YUETO_ROOT:-$(dirname "$ROOT")}
  board_sha=$(python3 "$ROOT/scripts/ci_check_board.py" --root "$YUETO_ROOT")
fi
[[ "$board_sha" =~ ^[0-9a-f]{40}$ ]] || fail 'board ref must be an exact 40-hex commit SHA'
[ "$repo" = yueops ] || fail 'B9-9 validates yueops; other repositories are not wired here'
[ "$mode" = remote ] || [ "$mode" = --local ] || usage
[[ "$raw_sha" =~ ^[0-9a-f]{7,40}$ ]] || fail 'sha must be 7 to 40 lowercase hex characters'
if [[ "$raw_sha" =~ ^[0-9a-f]{40}$ ]]; then
  full_sha=$raw_sha
else
  full_sha=$(gh api --method GET "repos/onesyue/$repo/commits/$raw_sha" --jq .sha)
fi
[[ "$full_sha" =~ ^[0-9a-f]{40}$ ]] || fail 'could not resolve exact source SHA'
base=${CI_CHECK_MIGRATION_BASE:-}
if [ -z "$base" ]; then
  base=$(gh api --method GET "repos/onesyue/$repo/commits/$full_sha" --jq '.parents[0].sha // empty')
fi
[[ "$base" =~ ^[0-9a-f]{40}$ ]] || fail 'migration base must be a full commit SHA'
[ -z "$(git -C "$ROOT" status --porcelain --untracked-files=no)" ] || fail 'commit policy edits before validation'
policy_sha=$(git -C "$ROOT" rev-parse HEAD)
# Keep every failure log and intent receipt; cleanup removes only owned clones.
output=${CI_CHECK_OUTPUT:-$ROOT/.lane/ci-check-$(date -u +%Y%m%dT%H%M%SZ)-$$}
mkdir -p "$output"
output=$(cd "$output" && pwd)
echo "ci-check: evidence $output" >&2
if [ "$mode" = remote ]; then
  branch=$(git -C "$ROOT" symbolic-ref --quiet --short HEAD) || fail 'remote validation needs a named policy branch'
  exec python3 "$ROOT/scripts/ci_check_remote.py" --branch "$branch" --policy "$policy_sha" \
    --source "$full_sha" --base "$base" --board "$board_sha" --output "$output"
fi
command -v docker >/dev/null || fail 'docker is required for --local'
checkouts=$(mktemp -d "$output/checkouts.XXXXXX")
source=$checkouts/source
board=$checkouts/board
policy=$checkouts/policy
cleanup() { rm -rf -- "$checkouts"; }
trap cleanup EXIT
clone_at() {
  local repository=$1 revision=$2 destination=$3 local_checkout=$4
  if [ -n "$local_checkout" ]; then
    git clone --quiet --no-hardlinks --dissociate "$local_checkout" "$destination"
    git -C "$destination" remote set-url origin "https://github.com/onesyue/$repository.git"
    git -C "$destination" cat-file -e "${revision}^{commit}" 2>/dev/null || \
      git -C "$destination" fetch --quiet "https://github.com/onesyue/$repository.git" "$revision"
  else
    gh repo clone "onesyue/$repository" "$destination" -- --quiet
  fi
  # A developer clone is an object cache, never the default-branch authority.
  git -C "$destination" fetch --quiet origin refs/heads/master:refs/remotes/origin/master
  git -C "$destination" checkout --quiet --detach "$revision"
}
clone_at yueops "$full_sha" "$source" "${YUEOPS_CHECKOUT:-}"
clone_at yueboard "$board_sha" "$board" "${YUEBOARD_CHECKOUT:-}"
clone_at yueto-ci "$policy_sha" "$policy" "$ROOT"
export GITHUB_SHA=$policy_sha GITHUB_RUN_ID=1 GITHUB_RUN_ATTEMPT=1
export GITHUB_REPOSITORY=onesyue/yueto-ci RUNNER_OS=Linux RUNNER_ARCH=X64
export ImageVersion=ci-check-local
python3 - "$full_sha" "$output/targets.json" <<'PY'
import json, sys
sha, dest = sys.argv[1:]
json.dump({'matrix': [], 'validation_matrix': [{'validation': 'yueops', 'repo': 'onesyue/yueops', 'ref': sha}],
           'has_builds': False}, open(dest, 'w'))
PY
python3 "$policy/scripts/pytest-shards.py" expand --targets "$output/targets.json" \
  --source "$source" --board "$board_sha" --runner ubuntu-24.04 --capacity 20 --shards 16 \
  --validation-only > "$output/admission.json" 2> "$output/planner.log"
python3 "$policy/scripts/ci_check_local.py" --source "$source" --board "$board" \
  --policy "$policy" --admission "$output/admission.json" --output "$output/local" --base "$base"
