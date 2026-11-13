#!/bin/bash
# Image build only. The existing policy installers own all versions/checksums.
set -euo pipefail
[ "$(id -u)" -ne 0 ] || { echo 'install verified tools as runner' >&2; exit 1; }
policy=/opt/yueops-ci-tools
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
export RUNNER_TEMP="$scratch" GITHUB_PATH="$scratch/github-path"
export GITHUB_WORKSPACE="$policy" DOCKER_CONFIG="$scratch/docker"
touch "$GITHUB_PATH"
bash "$policy/.ci-policy/scripts/ops-validation-gitleaks.sh"
bash "$policy/.ci-policy/scripts/install-cosign.sh"
bash "$policy/.ci-policy/scripts/install-verified-buildx.sh"
# Keep only verified outputs; runtime does not depend on build-stage HOME.
sudo -n install -m 0755 "$scratch/cosign-bin/cosign" /usr/local/bin/cosign
sudo -n install -d -m 0755 /usr/local/lib/docker/cli-plugins
sudo -n install -m 0755 "$DOCKER_CONFIG/cli-plugins/docker-buildx" /usr/local/lib/docker/cli-plugins/docker-buildx
# Gitleaks stays owned by the evidence user, as its existing installer requires.
test "$(stat -c '%u' /usr/local/bin/gitleaks)" = "$(id -u)"
