#!/bin/bash
# Shared by build.yml and ci-check --local; run from the source checkout.
set -euo pipefail
# Resolve checkout paths inside the executing namespace, including container jobs.
export YUEBOARD_REPO_PATH="$PWD/.ci-yueboard"
export YUETO_CI_REPO_PATH="$PWD/.ci-policy"
security_report=$(mktemp "${RUNNER_TEMP:?}/security-scan.XXXXXX.json")
trap 'rm -f -- "$security_report"' EXIT
uv lock --check
.venv/bin/python scripts/check-python-dependency-groups.py
bash scripts/security_scan.sh --json | tee "$security_report"
jq -e '.fail == 0' "$security_report" >/dev/null
.venv/bin/python -m compileall -q web checkin-api telegram-bot/yue
uv run --frozen --only-group lint ruff check .
.venv/bin/python scripts/audit-route-consistency.py
# The manual branch is selected before execution, never after a shard failure.
if [ "$OPS_ROLE" = legacy ]; then
  # 与本地 gauntlet 共用测试入口；中央显式串行，避免已复现的
  # xdist 收集时 service 包 sys.path/sys.modules 污染。
  # 覆盖与耗时取本次完整日志，不沿用旧 runner 的历史估计。
  timing_dir="${RUNNER_TEMP:?}/yueops-pytest-timing"
  invocation_id=$(.venv/bin/python -c 'import json,sys; print(json.load(open(sys.argv[1]))["invocation_id"])' "$timing_dir/metadata.json")
  pytest_rc=0
  .venv/bin/python -c 'import time; print(time.time_ns())' > "$timing_dir/pytest-start-unix-ns.txt"
  (
    policy_quarantine="$YUETO_CI_REPO_PATH/ci/quarantine.yaml"
    if [[ -e tests/quarantine.json || -L tests/quarantine.json || "${YUETO_SHARED_SELECTION:-[]}" != '[]' || -f "$policy_quarantine" ]]; then
      export YUETO_OPS_TEST_SOURCE="$PWD"
      export YUETO_CI_QUARANTINE="$policy_quarantine"
      export PYTEST_PLUGINS=ops_quarantine
      export PYTHONPATH="$PWD/.ci-policy/scripts${PYTHONPATH:+:$PYTHONPATH}"
    fi
    LENS_REPORT="$timing_dir/events.jsonl" LENS_INVOCATION_ID="$invocation_id" \
      YUEOPS_PYTEST_SERIAL=1 bash scripts/run-pytest-parallel.sh
  ) || pytest_rc=$?
  printf '%s\n' "$pytest_rc" > "$timing_dir/pytest-exit-code.txt"
  .venv/bin/python -c 'import time; print(time.time_ns())' > "$timing_dir/pytest-finish-unix-ns.txt"
  if [ "$pytest_rc" -ne 0 ]; then exit "$pytest_rc"; fi
fi
# PATH-first doubles live under /run. A noexec mount makes execve
# fail and Python then runs the real docker or systemctl.
sudo -n env PATH="$PATH" bash .ci-policy/scripts/prepare-native-run-exec.sh
sudo -n env PATH="$PATH" LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}" TZ=UTC "$PWD/.venv/bin/python" scripts/run-native-nginx-tests.py
