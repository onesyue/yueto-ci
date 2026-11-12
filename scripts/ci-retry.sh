#!/usr/bin/env bash
# I32-E R4/R7: sourced by policy-owned callers. Unknown failures fail closed.

ci_retryable_stderr() {
  local error_file="$1"
  # Refusals take precedence even when another line mentions a timeout/5xx.
  if grep -Eiq '(^|[^0-9])4[0-9]{2}([^0-9]|$)|unauthorized|forbidden|access denied|permission denied|invalid (signature|identity|certificate|attestation)|verification failed|signature.*(invalid|mismatch|failed|reject|denied)|identity.*(mismatch|not match|not expected|reject|denied)|certificate.*(not match|not expected|expired|unknown authority)|attestation.*(reject|invalid|denied|failed)|none of the expected identities|failed to verify|failed to validate|x509:|SSL certificate problem|no matching signatures|no matching attestations' "$error_file"; then
    return 1
  fi
  grep -Eiq 'TLS handshake timeout|TLS handshake failed|i/o timeout|context deadline exceeded|connection (reset|refused|died)|connection timed out|operation timed out|timeout was reached|temporary failure in name resolution|temporary failure resolving|could not resolve host|name or service not known|network is unreachable|could not connect to server|unexpected EOF|Failure writing output to destination|HTTP[^[:cntrl:]]*5[0-9]{2}|status( code)?[ :]+5[0-9]{2}|requested URL returned error: 5[0-9]{2}|rekor[^[:cntrl:]]*(unreachable|unavailable)|MANIFEST_UNKNOWN|manifest unknown' "$error_file"
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
  local command="$1" token rc scratch
  shift
  token=$(ci_fetch_token) || return "$?"
  [[ -n "$token" ]] || return 1
  scratch=$(mktemp -d)
  if cosign "$command" --yes --identity-token "$token" "$@" >"$scratch/out" 2>"$scratch/err"; then
    cat "$scratch/err" >&2
    cat "$scratch/out"
    rm -rf -- "$scratch"
    return 0
  else
    rc=$?
  fi
  cat "$scratch/err" >&2
  # Rebuilding an input-identical image signs the same digest. Rekor 409
  # means that entry is already there; verification still has to accept it.
  if [[ "$command" == sign || "$command" == attest ]] &&
     grep -F 'equivalent entry already exists' "$scratch/err" >/dev/null; then
    rm -rf -- "$scratch"
    echo "rekor already has an equivalent entry for this digest; keeping the existing signature" >&2
    return 0
  fi
  rm -rf -- "$scratch"
  return "$rc"
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

# The releases/download front can return 504 while the tag API still redirects
# to the blob. Callers keep their own checksum. The asset URL must stay on the API.
ci_release_asset_api() {
  local attempts="$1" dest="$2" url="$3"
  local path owner repo tag name meta asset_api auth=()
  path="${url#https://github.com/}"
  [[ "$path" != "$url" ]] || return 22
  owner="${path%%/*}"
  path="${path#*/}"
  repo="${path%%/*}"
  path="${path#*/releases/download/}"
  [[ "$path" == */* ]] || return 22
  tag="${path%%/*}"
  name="${path#*/}"
  [[ -n "$owner" && -n "$repo" && -n "$tag" && -n "$name" && "$name" != */* ]] || return 22
  if [[ -n "${GITHUB_TOKEN:-}" ]]; then
    auth=(--header "Authorization: bearer ${GITHUB_TOKEN}")
  fi
  meta=$(ci_download "$attempts" --fail --silent --show-error \
    --proto '=https' --proto-redir '=https' --tlsv1.2 \
    --header "Accept: application/vnd.github+json" \
    "${auth[@]}" \
    "https://api.github.com/repos/${owner}/${repo}/releases/tags/${tag}")
  asset_api=$(printf '%s' "$meta" | python3 -c '
import json, sys
name = sys.argv[1]
payload = json.load(sys.stdin)
assets = payload.get("assets") if isinstance(payload, dict) else None
if not isinstance(assets, list):
    raise SystemExit("release assets missing")
matches = [item.get("url") for item in assets
           if isinstance(item, dict) and item.get("name") == name]
if (len(matches) != 1 or not isinstance(matches[0], str)
        or not matches[0].startswith("https://api.github.com/")):
    raise SystemExit("release asset URL missing")
print(matches[0])
' "$name")
  # Follow the asset redirect ourselves. A token on the blob host makes curl
  # fail while writing the body.
  headers=$(ci_download "$attempts" --fail --silent --show-error --dump-header - --output /dev/null \
    --proto '=https' --proto-redir '=https' --tlsv1.2 \
    --header "Accept: application/octet-stream" \
    "${auth[@]}" \
    "$asset_api")
  location=$(printf '%s\n' "$headers" | awk 'tolower($1)=="location:" {print $2}' | tr -d '\r' | tail -n 1)
  case "$location" in
    https://release-assets.githubusercontent.com/*|https://objects.githubusercontent.com/*) ;;
    *) return 22 ;;
  esac
  ci_download "$attempts" --fail --location --silent --show-error \
    --proto '=https' --proto-redir '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time 180 \
    "$location" --output "$dest"
}
