#!/usr/bin/env bash
# One Board role in an owned outer container, without the host Docker socket.
set -euo pipefail
: "${CI_CHECK_SOURCE:?}" "${CI_CHECK_POLICY:?}" "${CI_CHECK_JOB:?}" "${BOARD_ROLE:?}"
export GITHUB_WORKSPACE=$CI_CHECK_JOB/source
export RUNNER_TEMP=$CI_CHECK_JOB/temp
export TMPDIR=$RUNNER_TEMP
export GITHUB_PATH=$RUNNER_TEMP/github-path
export YUE_CI_PYTHON=/usr/local/bin/python3
export TZ=UTC
mkdir -p "$RUNNER_TEMP" "$GITHUB_WORKSPACE"
: > "$GITHUB_PATH"
cp -a --no-preserve=ownership "$CI_CHECK_SOURCE/." "$GITHUB_WORKSPACE/"
mkdir -p "$GITHUB_WORKSPACE/.ci-policy"
cp -a --no-preserve=ownership "$CI_CHECK_POLICY/." "$GITHUB_WORKSPACE/.ci-policy/"
policy_checkout=$GITHUB_WORKSPACE/.ci-policy
daemon_pid=
# shellcheck source=scripts/ci-check-private-daemon.sh
source "$policy_checkout/scripts/ci-check-private-daemon.sh"
cleanup() {
  ci_check_daemon_stop
  rm -rf -- "$GITHUB_WORKSPACE"
}
trap cleanup EXIT
ci_check_daemon_start
"$YUE_CI_PYTHON" "$policy_checkout/scripts/ci_check_board_role.py"
