#!/usr/bin/env bash
# Execute hosted Board phases from one reusable command body.
set -euo pipefail
unset CDPATH
fail() { echo "board-validation: $*" >&2; exit 2; }
[ "$#" -ge 4 ] || fail 'usage: board-validation.sh ROLE SOURCE POLICY TEMP'
role=$1
case "$role" in quality|race|postgres|migration|postgres-clean|frontends|components|e2e) ;; *) fail "unsupported role: $role" ;; esac
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
frontend_phase=""
result=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --database-adapter) [ "$#" -ge 2 ] && [ -n "$2" ] && [ -z "$adapter" ] || fail 'adapter required exactly once'; adapter=$2; shift 2 ;;
    --frontend-phase) [ "$#" -ge 2 ] && [ -n "$2" ] && [ -z "$frontend_phase" ] || fail 'frontend phase required exactly once'; frontend_phase=$2; shift 2 ;;
    --result) [ "$#" -ge 2 ] && [ -n "$2" ] && [ -z "$result" ] || fail 'result required exactly once'; result=$2; shift 2 ;;
    --receipt) [ "$#" -ge 2 ] && [ -n "$2" ] && [ -z "$receipt" ] || fail 'receipt required exactly once'; receipt=$2; shift 2 ;;
    *) fail "unsupported argument: $1" ;;
  esac
done
case "$role" in
  frontends|components|e2e)
    [ -z "$receipt" ] || fail 'frontend phases do not accept integration receipts'
    case "$role:$frontend_phase" in
      frontends:prepare|components:prepare|e2e:prepare|frontends:lint|frontends:design|components:test|e2e:test) ;;
      *) fail 'unsupported frontend role/phase' ;;
    esac
    if [ "$role:$frontend_phase" = e2e:test ]; then
      case "$adapter" in loopback|github-service) ;; *) fail 'explicit database adapter is required' ;; esac
      [ -n "${YUE_CI_PYTHON:-}" ] && [ -x "$YUE_CI_PYTHON" ] || fail 'validated YUE_CI_PYTHON executable is required'
    else
      [ -z "$adapter" ] || fail 'database adapter belongs only to e2e test'
      [ -z "${YUEBOARD_ADMIN_DATABASE_URL:-}${YUEBOARD_E2E_DATABASE_URL:-}${YUEBOARD_E2E_ALLOW_RESET:-}" ] || fail 'e2e database environment is not allowed in this frontend phase'
    fi
    [ -n "$result" ] && [ ! -e "$result" ] && [ ! -L "$result" ] || fail 'exclusive frontend result is required'
    result_parent=$(dirname -- "$result")
    [ ! -L "$result_parent" ] && [ -d "$result_parent" ] || fail 'result parent must be a real directory'
    result_parent=$(cd -- "$result_parent" && pwd)
    [ "$(dirname -- "$result_parent")" = "$temp" ] || fail 'result must be in an owned temporary child'
    case "$(basename -- "$result_parent")" in board-frontend.*) ;; *) fail 'unexpected frontend result directory' ;; esac
    result="$result_parent/$(basename -- "$result")"
    ;;
  *) [ -z "$frontend_phase$result" ] || fail 'frontend arguments are not valid for this role' ;;
esac
case "$role" in
  frontends|components|e2e) ;;
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
emit_frontend_result() { (set -o noclobber; printf '%s\n' "$1" > "$result"); }
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
      # Compare the source-owned HTTP contract against real prior history.
      # A master validation must not silently compare the contract to itself.
      http_base=$(git merge-base HEAD "${HTTP_CONTRACT_BASE:-origin/master}") \
        || fail 'HTTP contract baseline is unavailable'
      if [ -z "${HTTP_CONTRACT_BASE:-}" ] && [ "$http_base" = "$(git rev-parse HEAD)" ] \
        && git rev-parse --verify --quiet 'HEAD^1^{commit}' >/dev/null; then
        http_base=$(git rev-parse 'HEAD^1')
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
      make check-http-contract "HTTP_CONTRACT_BASE=$http_base"
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
  frontends|components|e2e)
    case "$role:$frontend_phase" in
      *:prepare)
        corepack enable
        if [ -f pnpm-workspace.yaml ]; then
          layout=workspace
          root_pm=$(node -p "require('./package.json').packageManager || ''")
          [ -n "$root_pm" ] || {
            echo "::error::YueBoard workspace layout without a root packageManager"
            exit 1
          }
          corepack install --global "$root_pm"
          # --ignore-scripts also skips esbuild's allow-listed postinstall; its
          # per-platform @esbuild/* optional package already ships the binary.
          pnpm install --frozen-lockfile --ignore-scripts
          pnpm --filter yueboard-web --filter yueboard-web-admin run build
          (cd web && node scripts/verify-dist.mjs dist)
          (cd web-admin && node scripts/verify-dist.mjs dist)
        else
          layout=legacy
          web_pm=$(node -p "require('./web/package.json').packageManager")
          admin_pm=$(node -p "require('./web-admin/package.json').packageManager")
          [ "$web_pm" = "$admin_pm" ] || {
            echo "YueBoard frontend package-manager versions diverged" >&2
            exit 1
          }
          corepack install --global "$web_pm"
          pnpm --dir web install --frozen-lockfile --ignore-scripts
          pnpm --dir web build
          (cd web && node scripts/verify-dist.mjs dist)
          pnpm --dir web-admin install --frozen-lockfile --ignore-scripts
          pnpm --dir web-admin build
          (cd web-admin && node scripts/verify-dist.mjs dist)
        fi
        emit_frontend_result "layout=$layout"
        echo "YueBoard frontend layout: $layout"
        # Source-owned advisory gate (same model as YueOps'
        # scripts/npm-audit-gate.py): the reviewed exception list lives in
        # the YueBoard tree, never here. A checkout without it must stop.
        # Exit 0 = pass, 1 = blocking advisory, 2 = the gate itself failed;
        # anything non-zero stops the release (2 is never a pass). The same
        # project-name call works in both layouts (workspace mode audits the
        # root lock once and requires each name to be a workspace member).
        audit_gate="scripts/ci/pnpm-audit-gate.mjs"
        [ -f "$audit_gate" ] || {
          echo "::error::source-owned pnpm audit gate is missing: $audit_gate"
          exit 1
        }
        node "$audit_gate" web web-admin
        ;;
      frontends:lint)
        [ -f pnpm-workspace.yaml ] || fail 'workspace-only phase requires workspace layout'
        for script in lint fmt:check; do
          node -e "process.exit(require('./package.json').scripts?.[process.argv[1]] ? 0 : 1)" "$script" || {
            echo "::error::YueBoard workspace layout is missing the root '$script' script"
            exit 1
          }
        done
        # Oxlint type-aware ratchet: exit 2 = the gate itself failed (tsgolint or
        # the React Compiler rules did not run), never a pass.
        pnpm run lint
        pnpm run fmt:check
        ;;
      components:test)
        [ -f pnpm-workspace.yaml ] || fail 'workspace-only phase requires workspace layout'
        node -e "process.exit(require('./package.json').scripts?.['test:components'] ? 0 : 1)" || {
          echo "::error::YueBoard workspace layout is missing the root 'test:components' script"
          exit 1
        }
        # The locked Playwright's Chromium (version comes from the root lock).
        # --with-deps needs apt as root; the self-hosted release runner keeps
        # its system libraries provisioned and gets the browser only.
        deps=()
        if [ "$(id -u)" -eq 0 ] || sudo -n true 2>/dev/null; then deps=(--with-deps); fi
        pnpm --dir web exec playwright install "${deps[@]}" chromium
        pnpm run test:components
        ;;
      e2e:test)
        [ -f pnpm-workspace.yaml ] || fail 'workspace-only phase requires workspace layout'
        "$YUE_CI_PYTHON" "$policy/scripts/pg_validation_address.py" --database-adapter "$adapter" --phase e2e
        [ -f test/e2e/playwright.config.ts ] || {
          echo "::error::YueBoard workspace layout is missing the test/e2e suite"
          exit 1
        }
        psql -v ON_ERROR_STOP=1 "$YUEBOARD_ADMIN_DATABASE_URL" \
          -c 'DROP DATABASE IF EXISTS yueboard_e2e' -c 'CREATE DATABASE yueboard_e2e'
        deps=()
        if [ "$(id -u)" -eq 0 ] || sudo -n true 2>/dev/null; then deps=(--with-deps); fi
        pnpm --dir test/e2e exec playwright install "${deps[@]}" chromium
        shots=test/e2e/specs/__screenshots__
        [ -d "$shots" ] || {
          echo "::error::YueBoard release requires committed Linux visual baselines"
          exit 1
        }
        baseline=$(find "$shots" -type f -name '*-linux.png' -print -quit)
        [ -n "$baseline" ] || {
          echo "::error::YueBoard release requires committed Linux visual baselines"
          exit 1
        }
        emit_frontend_result 'visual=compared'
        pnpm --dir test/e2e test --update-snapshots=none
        ;;
      frontends:design)
        node scripts/ci/verify-responsive.mjs
        node scripts/ci/verify-design-tokens.mjs
        node scripts/ci/verify-page-consistency.mjs
        ;;
    esac
    ;;
esac
