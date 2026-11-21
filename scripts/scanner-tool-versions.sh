#!/usr/bin/env bash
# Reviewed versions for the weekly report-only vulnerability scanners.
# Source only from the exact policy checkout, never override from the environment.
unset DART_SDK_VERSION DART_SDK_SHA256 UV_VERSION NODE_VERSION
unset PIP_AUDIT_VERSION PNPM_VERSION PNPM_PACKAGE_MANAGER
readonly DART_SDK_VERSION='3.13.7'
readonly DART_SDK_SHA256='eb99aed266efbcb615c6ae21c12f52cfe935b9f208bccc5fea7f64c21e867229'
readonly UV_VERSION='0.10.9'
readonly NODE_VERSION='24.22.3'
readonly PIP_AUDIT_VERSION='2.10.1'
readonly PNPM_VERSION='11.27.1'
readonly PNPM_PACKAGE_MANAGER='pnpm@11.27.1+sha512.a81d4c21b9b09a4b0aebf90ef5e527d4262bdda322d26082978cb549023ac6d9cafc98b19fffaa5c71db438a65f70224edb78d7311187861cdca23c'
[[ "${DART_SDK_VERSION:-}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'invalid dart sdk version authority' >&2; return 2; }
[[ "${UV_VERSION:-}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'invalid uv version authority' >&2; return 2; }
[[ "${NODE_VERSION:-}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'invalid node version authority' >&2; return 2; }
[[ "${PIP_AUDIT_VERSION:-}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'invalid pip-audit version authority' >&2; return 2; }
[[ "${PNPM_VERSION:-}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'invalid pnpm version authority' >&2; return 2; }
[[ "${DART_SDK_SHA256:-}" =~ ^[0-9a-f]{64}$ ]] || { echo 'invalid dart sdk checksum authority' >&2; return 2; }
[[ "${PNPM_PACKAGE_MANAGER:-}" == "pnpm@${PNPM_VERSION}+sha512."* ]] || { echo 'invalid pnpm packageManager authority' >&2; return 2; }
# shellcheck disable=SC2034
readonly SCANNER_TOOL_VERSIONS_READY=1
