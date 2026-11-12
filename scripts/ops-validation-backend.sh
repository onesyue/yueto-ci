#!/bin/bash
# Shared by build.yml and ci-check --local; run from the source checkout.
set -euo pipefail
security_report=$(mktemp "${RUNNER_TEMP:?}/security-scan.XXXXXX.json")
python_lock_audit=$(mktemp "${RUNNER_TEMP:?}/python-lock-audit.XXXXXX.txt")
python_audit_cache=$(mktemp -d "${RUNNER_TEMP:?}/python-audit-cache.XXXXXX")
python_audit_reports=$(mktemp -d "${RUNNER_TEMP:?}/python-audit-reports.${GITHUB_RUN_ID:?}.${GITHUB_RUN_ATTEMPT:?}.${OPS_ROLE:?}.XXXXXX")
cleanup_reports() {
  rm -f -- "$security_report" "$python_lock_audit"
  rm -rf -- "$python_audit_cache"
}
trap cleanup_reports EXIT
uv lock --check
.venv/bin/python scripts/check-python-dependency-groups.py
bash scripts/security_scan.sh --json | tee "$security_report"
jq -e '.fail == 0' "$security_report" >/dev/null
uv export --frozen --all-groups --no-emit-local \
  --no-annotate --no-header --output-file "$python_lock_audit"
# Provider coverage differs: Mako's 2026-10-05 advisory was present
# in OSV while a fresh PyPI audit still reported zero findings.
for vulnerability_service in pypi osv; do
  uv run --frozen --only-group audit pip-audit \
    --requirement "$python_lock_audit" \
    --progress-spinner off --require-hashes --disable-pip --strict \
    --cache-dir "$python_audit_cache" \
    --vulnerability-service "$vulnerability_service" \
    --format json --output "$python_audit_reports/$vulnerability_service.json"
  jq -e '.dependencies | type == "array" and length >= 100 and all(.[]; .vulns == [] and (has("skip_reason") | not))' \
    "$python_audit_reports/$vulnerability_service.json" >/dev/null
done
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
  LENS_REPORT="$timing_dir/events.jsonl" LENS_INVOCATION_ID="$invocation_id" \
    YUEOPS_PYTEST_SERIAL=1 bash scripts/run-pytest-parallel.sh || pytest_rc=$?
  printf '%s\n' "$pytest_rc" > "$timing_dir/pytest-exit-code.txt"
  .venv/bin/python -c 'import time; print(time.time_ns())' > "$timing_dir/pytest-finish-unix-ns.txt"
  if [ "$pytest_rc" -ne 0 ]; then exit "$pytest_rc"; fi
fi
# PATH-first doubles live under /run. A noexec mount makes execve
# fail and Python then runs the real docker or systemctl.
sudo -n env PATH="$PATH" bash .ci-policy/scripts/prepare-native-run-exec.sh
sudo -n env PATH="$PATH" LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}" TZ=UTC "$PWD/.venv/bin/python" scripts/run-native-nginx-tests.py
