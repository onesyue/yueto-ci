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
