#!/bin/bash
# Shared by build.yml and ci-check --local; run from the source checkout.
set -euo pipefail
python_lock_audit=$(mktemp "${RUNNER_TEMP:?}/python-lock-audit.XXXXXX.txt")
python_audit_cache=$(mktemp -d "${RUNNER_TEMP:?}/python-audit-cache.XXXXXX")
python_audit_reports=$(mktemp -d "${RUNNER_TEMP:?}/python-audit-reports.${GITHUB_RUN_ID:?}.${GITHUB_RUN_ATTEMPT:?}.${OPS_ROLE:?}.XXXXXX")
cleanup_reports() {
  rm -f -- "$python_lock_audit"
  rm -rf -- "$python_audit_cache"
}
trap cleanup_reports EXIT
uv export --frozen --all-groups --no-emit-local \
  --no-annotate --no-header --output-file "$python_lock_audit"
# Provider coverage differs: Mako's 2026-10-05 advisory was present
# in OSV while a fresh PyPI audit still reported zero findings.
# A provider connection fault is not a finding (ship build 46070219984,
# 2026-11-28: PyPI reset one query and the whole release refused). Retry only
# when pip-audit's final exception line names a requests connection/timeout
# error or an HTTP 5xx; findings, refusals and unknown errors keep their exit
# code on the first attempt. The whole traceback still goes to the log.
for vulnerability_service in pypi osv; do
  for audit_attempt in 1 2 3 4; do
    audit_stderr=$(mktemp)
    audit_rc=0
    uv run --frozen --only-group audit pip-audit \
      --requirement "$python_lock_audit" \
      --progress-spinner off --require-hashes --disable-pip --strict \
      --cache-dir "$python_audit_cache" \
      --vulnerability-service "$vulnerability_service" \
      --format json --output "$python_audit_reports/$vulnerability_service.json" \
      2>"$audit_stderr" || audit_rc=$?
    cat "$audit_stderr" >&2
    if [ "$audit_rc" -ne 0 ] && [ "$audit_attempt" -lt 4 ] &&
       grep -v '^[[:space:]]*$' "$audit_stderr" | tail -n 1 |
         grep -Eq '^requests\.exceptions\.(ConnectionError|ConnectTimeout|ReadTimeout|ChunkedEncodingError)\b|^requests\.exceptions\.HTTPError: 5[0-9]{2} '; then
      rm -f -- "$audit_stderr"
      echo "pip-audit ${vulnerability_service}: transient provider failure on attempt ${audit_attempt}/4; retrying" >&2
      sleep "$(( audit_attempt * ${PIP_AUDIT_RETRY_FACTOR:-5} ))"
      continue
    fi
    rm -f -- "$audit_stderr"
    [ "$audit_rc" -eq 0 ] || exit "$audit_rc"
    break
  done
  jq -e '.dependencies | type == "array" and length >= 100 and all(.[]; .vulns == [] and (has("skip_reason") | not))' \
    "$python_audit_reports/$vulnerability_service.json" >/dev/null
done
