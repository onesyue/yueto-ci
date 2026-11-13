#!/bin/bash
# One isolated role in the exact hosted toolchain image. No release entrypoints.
set -euo pipefail
: "${CI_CHECK_SOURCE:?}" "${CI_CHECK_BOARD:?}" "${CI_CHECK_POLICY:?}" "${CI_CHECK_JOB:?}" "${OPS_ROLE:?}"
export GITHUB_WORKSPACE=$CI_CHECK_JOB/source
export RUNNER_TEMP=$CI_CHECK_JOB/temp
export TMPDIR=$RUNNER_TEMP
export GITHUB_PATH=$RUNNER_TEMP/github-path
export GITHUB_ENV=$RUNNER_TEMP/github-env
export YUE_CI_PYTHON=/usr/local/bin/python3
export TZ=UTC
board_checkout=$GITHUB_WORKSPACE/.ci-yueboard
policy_checkout=$GITHUB_WORKSPACE/.ci-policy
mkdir -p "$RUNNER_TEMP/ops-admission"
cp "$CI_CHECK_ADMISSION" "$RUNNER_TEMP/ops-admission/ops-admission.json"
: > "$GITHUB_PATH"
: > "$GITHUB_ENV"
# Preserve the standalone clones and their fetched origin/master authority.
# Re-cloning here would replace origin/master with the template's local master.
mkdir -p "$GITHUB_WORKSPACE" "$board_checkout" "$policy_checkout"
cp -a --no-preserve=ownership "$CI_CHECK_SOURCE/." "$GITHUB_WORKSPACE/"
cp -a --no-preserve=ownership "$CI_CHECK_BOARD/." "$board_checkout/"
cp -a --no-preserve=ownership "$CI_CHECK_POLICY/." "$policy_checkout/"
daemon_pid=
# shellcheck source=scripts/ci-check-private-daemon.sh
source "$policy_checkout/scripts/ci-check-private-daemon.sh"
cleanup() {
  ci_check_daemon_stop
  # Match the artifact names consumed by the same join as hosted CI.
  if [ -d "$RUNNER_TEMP/ops-shard-evidence" ]; then
    mv "$RUNNER_TEMP/ops-shard-evidence" "$CI_CHECK_EVIDENCE/ops-shard-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT-$OPS_ROLE"
  fi
  # Preserve receipts and diagnostics, discard only this role's own checkout.
  rm -rf -- "$GITHUB_WORKSPACE"
}
trap cleanup EXIT
cd "$GITHUB_WORKSPACE"
run_step() {
  local step=$1 directory=${2:-$GITHUB_WORKSPACE}
  echo "::step::$step"
  (
    cd "$directory"
    case "$step" in
      dependencies|selection|backend|notices) export UV_PYTHON_DOWNLOADS=never ;;
    esac
    case "$step" in
      selection|backend)
        export YUEBOARD_REPO_PATH=$board_checkout YUETO_CI_REPO_PATH=$policy_checkout
        export PYTEST_ADDOPTS=--durations=25 ;;
      notices) export YUEBOARD_REPO_PATH=$board_checkout ;;
    esac
    bash "$policy_checkout/scripts/ops-validation-$step.sh"
  )
  while IFS= read -r bin; do
    [ -z "$bin" ] || export PATH="$bin:$PATH"
  done < "$GITHUB_PATH"
}
if [ "$OPS_ROLE" = join ]; then
  python3 "$policy_checkout/scripts/pytest-shards.py" join \
    --admission "$CI_CHECK_ADMISSION" --source "$GITHUB_WORKSPACE" \
    --evidence "$CI_CHECK_EVIDENCE" --validation-result "$CI_CHECK_RESULT" \
    --expected-sha "$CI_CHECK_ADMISSION_SHA"
  exit
fi
# Each GitHub role owns a runner daemon. Local roles likewise get a private
# daemon; fixture cleanup must never reach another lane's Docker containers.
ci_check_daemon_start
run_step node-toolchain
run_step dependencies
run_step gitleaks
if [ "$OPS_ROLE" != native ]; then
  run_step selection
else
  run_step notices
  run_step backend
  run_step obligations
  run_step frontend "$GITHUB_WORKSPACE/frontend"
  run_step miniapp "$GITHUB_WORKSPACE/telegram-bot/yue/miniapp"
  run_step node
  run_step migrations
  run_step terminal
fi
