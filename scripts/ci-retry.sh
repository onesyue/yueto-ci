#!/usr/bin/env bash
# I32-E R4/R7: sourced by policy-owned callers. Unknown failures fail closed.

ci_retryable_stderr() {
  local error_file="$1"
  # Refusals take precedence even when another line mentions a timeout/5xx.
  if grep -Eiq '(^|[^0-9])4[0-9]{2}([^0-9]|$)|unauthorized|forbidden|access denied|permission denied|invalid (signature|identity|certificate|attestation)|verification failed|signature.*(invalid|mismatch|failed|reject|denied)|identity.*(mismatch|not match|not expected|reject|denied)|certificate.*(not match|not expected|expired|unknown authority)|attestation.*(reject|invalid|denied|failed)|none of the expected identities|failed to verify|failed to validate|x509:|SSL certificate problem|no matching signatures|no matching attestations' "$error_file"; then
    return 1
  fi
  grep -Eiq 'TLS handshake timeout|TLS handshake failed|i/o timeout|context deadline exceeded|connection (reset|refused)|connection timed out|operation timed out|timeout was reached|temporary failure in name resolution|could not resolve host|could not connect to server|unexpected EOF|HTTP[^[:cntrl:]]*5[0-9]{2}|status( code)?[ :]+5[0-9]{2}|requested URL returned error: 5[0-9]{2}|rekor[^[:cntrl:]]*(unreachable|unavailable)|MANIFEST_UNKNOWN|manifest unknown' "$error_file"
}

# A subshell owns temporary files/traps; failed stdout never contaminates the
# eventual JSON/attestation result. Sleep only when another attempt will occur.
ci_retry() (
  set -euo pipefail
  local attempts="$1" factor="$2" jitter="$3" attempt rc
  shift 3
  local scratch
  scratch=$(mktemp -d)
  trap 'rm -rf -- "$scratch"' EXIT
  for ((attempt=1; attempt<=attempts; attempt++)); do
    if "$@" >"$scratch/stdout" 2>"$scratch/stderr"; then
      cat "$scratch/stderr" >&2
      cat "$scratch/stdout"
      return 0
    else
      rc=$?
    fi
    cat "$scratch/stderr" >&2
    if (( attempt == attempts )) || ! ci_retryable_stderr "$scratch/stderr"; then
      return "$rc"
    fi
    echo "transient failure on attempt ${attempt}/${attempts}; retrying" >&2
    sleep $(( attempt * factor + RANDOM % jitter ))
  done
)

ci_fetch_token() {
  curl -sSf \
    -H "Authorization: bearer ${ACTIONS_ID_TOKEN_REQUEST_TOKEN}" \
    "${ACTIONS_ID_TOKEN_REQUEST_URL}&audience=sigstore" | jq -er '.value'
}

ci_keyless_once() {
  local command="$1" token
  shift
  token=$(ci_fetch_token) || return "$?"
  [[ -n "$token" ]] || return 1
  cosign "$command" --yes --identity-token "$token" "$@"
}

keyless_cosign() { ci_retry 6 3 7 ci_keyless_once "$@"; }
verify_cosign() { ci_retry 6 2 5 cosign "$@"; }

# Four total attempts (old curl --retry 3); policy actionlint keeps five.
# curl's built-in retries are disabled: in particular 408/429 must fail once.
ci_download() {
  local attempts="$1"
  shift
  ci_retry "$attempts" 2 1 curl --retry 0 "$@"
}
