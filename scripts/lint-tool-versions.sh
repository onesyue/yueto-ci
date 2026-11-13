#!/usr/bin/env bash
# Single reviewed authority for standalone lint tools, shared by hosted/local phases.
# Source only from the exact policy checkout, never override from the environment.
unset GOLANGCI_LINT_VERSION GOLANGCI_LINT_SHA256 GOVULNCHECK_VERSION
unset SQUAWK_VERSION SQUAWK_SHA256 ACTIONLINT_VERSION ACTIONLINT_ARCHIVE_SHA256
readonly GOLANGCI_LINT_VERSION='2.14.0'
readonly GOLANGCI_LINT_SHA256='ab90aeb7b066f92a33415b638a50fe5344bbb75a0d32ad30cc248d88f81032ab'
readonly GOVULNCHECK_VERSION='v1.8.0'
readonly SQUAWK_VERSION='2.60.0'
readonly SQUAWK_SHA256='708d77899e2b43e0d21cb811023dbbcfb3b8220b0c0b7e71c6e73568be7716e5'
readonly ACTIONLINT_VERSION='1.7.12'
readonly ACTIONLINT_ARCHIVE_SHA256='8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8'
# Fail before a download or PATH fast-path when this contract is incomplete.
for lint_version in "${GOLANGCI_LINT_VERSION:-}" "${SQUAWK_VERSION:-}" "${ACTIONLINT_VERSION:-}"; do
  [[ "$lint_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'invalid lint tool version authority' >&2; return 2; }
done
[[ "${GOVULNCHECK_VERSION:-}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'invalid govulncheck version authority' >&2; return 2; }
for lint_hash in "${GOLANGCI_LINT_SHA256:-}" "${SQUAWK_SHA256:-}" "${ACTIONLINT_ARCHIVE_SHA256:-}"; do
  [[ "$lint_hash" =~ ^[0-9a-f]{64}$ ]] || { echo 'invalid lint tool checksum authority' >&2; return 2; }
done
unset lint_version lint_hash
# Read by the importing workflow/installer after sourcing.
# shellcheck disable=SC2034
readonly LINT_TOOL_VERSIONS_READY=1
