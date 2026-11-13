#!/usr/bin/env bash
# Execute hosted Board phases from one reusable command body.
set -euo pipefail
unset CDPATH
fail() { echo "board-validation: $*" >&2; exit 2; }
[ "$#" -ge 4 ] || fail 'usage: board-validation.sh ROLE SOURCE POLICY TEMP'
role=$1
case "$role" in quality|race|postgres|migration|postgres-clean) ;; *) fail "unsupported role: $role" ;; esac
[ -d "$2" ] && [ -f "$2/go.mod" ] || fail 'source directory with go.mod is required'
[ -d "$3" ] && [ -f "$3/scripts/install-board-quality-tools.sh" ] || fail 'policy directory with quality installer is required'
[ -d "$4" ] && [ -w "$4" ] || fail 'writable temporary directory is required'
# Source commands must not inherit the caller's clone/API credential.
for secret in GH_TOKEN GITHUB_TOKEN GH_ENTERPRISE_TOKEN GITHUB_ENTERPRISE_TOKEN; do
  [ -z "${!secret:-}" ] || fail "credential environment is not allowed: $secret"
done
source_dir=$(cd -- "$2" && pwd)
policy=$(cd -- "$3" && pwd)
temp=$(cd -- "$4" && pwd)
shift 4
adapter=""
receipt=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --database-adapter) [ "$#" -ge 2 ] && [ -n "$2" ] && [ -z "$adapter" ] || fail 'adapter required exactly once'; adapter=$2; shift 2 ;;
    --receipt) [ "$#" -ge 2 ] && [ -n "$2" ] && [ -z "$receipt" ] || fail 'receipt required exactly once'; receipt=$2; shift 2 ;;
    *) fail "unsupported argument: $1" ;;
  esac
done
case "$role" in
  quality|race) [ -z "$adapter" ] && [ -z "$receipt" ] || fail 'PG arguments are not valid for quality/race' ;;
  *)
    case "$adapter" in loopback|github-service) ;; *) fail 'explicit database adapter is required' ;; esac
    [ -n "${YUE_CI_PYTHON:-}" ] && [ -x "$YUE_CI_PYTHON" ] || fail 'validated YUE_CI_PYTHON executable is required'
    if [ "$role" = postgres-clean ]; then
      [ -z "$receipt" ] || fail 'clean phase has no integration receipt'
    else
      [ -n "$receipt" ] || fail 'explicit integration receipt is required'
      receipt="$(cd -- "$(dirname -- "$receipt")" && pwd)/$(basename -- "$receipt")"
    fi
    ;;
esac
cd -- "$source_dir"
case "$role" in
  quality)
    # Preserve the old workflow step boundary: backend-only environment changes
    # must not reach the following source-owned protocol gate.
    (
      # Intentional isolation from the subsequent protocol gate.
      # shellcheck disable=SC2030
      export CGO_ENABLED=1
      # Economy contract pack (yueboard #37) diffs HEAD against
      # merge-base(HEAD, origin/master). Releasing master makes that HEAD
      # itself, so use the reviewed pre-merge master (first parent).
      if [ -z "${YUEBOARD_CONTRACT_BASELINE:-}" ] \
        && [ "$(git merge-base HEAD origin/master 2>/dev/null || true)" = "$(git rev-parse HEAD)" ] \
        && git rev-parse --verify --quiet 'HEAD^1^{commit}' >/dev/null; then
        YUEBOARD_CONTRACT_BASELINE="$(git rev-parse 'HEAD^1')"
        export YUEBOARD_CONTRACT_BASELINE
        echo "economy contract baseline: first parent $YUEBOARD_CONTRACT_BASELINE"
      fi
      go build ./...
      mapfile -t go_files < <(
        git ls-files '*.go' | grep -v '/gen/' | grep -v 'noderpc/gen'
      )
      [ "${#go_files[@]}" -gt 0 ] || {
        echo "::error::YueBoard source checkout contains no lintable Go files"
        exit 1
      }
      unformatted="$(gofmt -l "${go_files[@]}")"
      if [ -n "$unformatted" ]; then
        echo "YueBoard Go files are not gofmt-clean:" >&2
        printf '%s\n' "$unformatted" >&2
        exit 1
      fi
      make check-generated
      go vet ./...
      scripts/ci/check-server-error-logging.sh
      bash "$policy/scripts/install-board-quality-tools.sh" \
        "${temp}/board-quality-tools"
      export PATH="${temp}/board-quality-tools:${PATH}"
      govulncheck ./...
      golangci-lint run --timeout=6m ./...
      go test ./...
    )
    scripts/ci/proto-gate.sh
    ;;
  race)
    # Independent case branch: quality subshell never runs on this path.
    # shellcheck disable=SC2031
    export CGO_ENABLED=1
    [ "$(go env CGO_ENABLED)" = "1" ] || {
      echo "::error::YueBoard race validation requires CGO_ENABLED=1"
      exit 1
    }
    go test -race ./...
    ;;
  postgres|migration)
    phase=domain
    [ "$role" != migration ] || phase=remaining
    "$YUE_CI_PYTHON" "$policy/scripts/validate-yueboard-postgres.py" \
      --phase "$phase" --database-adapter "$adapter" --receipt "$receipt"
    ;;
  postgres-clean)
    "$YUE_CI_PYTHON" "$policy/scripts/pg_validation_address.py" --database-adapter "$adapter"
    (
      psql -v ON_ERROR_STOP=1 "$YUEBOARD_ADMIN_DATABASE_URL" \
        -c 'CREATE DATABASE yueboard_clean_gate'
      # Throwaway keys stay in this clean phase's child environment.
      YUEBOARD_TOKEN_ENC_KEYS="1:$(openssl rand -base64 32)"
      YUEBOARD_TOKEN_BIDX_KEY="$(openssl rand -base64 32)"
      export YUEBOARD_TOKEN_ENC_KEYS YUEBOARD_TOKEN_BIDX_KEY
      scripts/ci/clean-pg-gate.sh
    )
    ;;
esac
