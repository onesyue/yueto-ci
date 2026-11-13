#!/bin/bash
# Read expected versions from the copied installers, never a second pin ledger.
set -euo pipefail
scripts=/opt/yueops-ci-tools/.ci-policy/scripts
buildx_version=$(sed -n "s/^readonly BUILDX_VERSION='\([^']*\)'$/\1/p" "$scripts/install-verified-buildx.sh")
cosign_version=$(sed -n "s/^readonly COSIGN_VERSION='\([^']*\)'$/\1/p" "$scripts/install-cosign.sh")
gitleaks_version=$(sed -n "s@^release_url='https://github.com/gitleaks/gitleaks/releases/download/v\([^/]*\)/[^']*'\$@\1@p" "$scripts/ops-validation-gitleaks.sh")
[ -n "$buildx_version" ] && [ -n "$cosign_version" ] && [ -n "$gitleaks_version" ]
test "$(/usr/local/bin/gitleaks version)" = "$gitleaks_version"
test "$(stat -c '%u' /usr/local/bin/gitleaks)" = "$(id -u)"
test "$(cosign version | awk '/^[[:space:]]*GitVersion:/ {print $2}')" = "$cosign_version"
actual=$(docker buildx version)
[[ "$actual" == "github.com/docker/buildx $buildx_version "* ]]
# GitHub container jobs may replace HOME. Prove system-wide plugin discovery.
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
actual=$(HOME="$scratch" DOCKER_CONFIG="$scratch" docker buildx version)
[[ "$actual" == "github.com/docker/buildx $buildx_version "* ]]
