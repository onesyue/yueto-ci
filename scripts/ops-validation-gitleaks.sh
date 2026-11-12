#!/bin/bash
# Shared by build.yml and ci-check --local; run from the source checkout.
set -euo pipefail
# yueops' credential-evidence contracts execute the real scanner at
# the fixed production path. Fetch the upstream release at an
# immutable version and authenticate its exact bytes before use.
if [ -x /usr/local/bin/gitleaks ] &&
   [ "$(/usr/local/bin/gitleaks version 2>/dev/null)" = '8.30.1' ]; then
  echo "gitleaks 8.30.1 already present"
  exit 0
fi
archive="${RUNNER_TEMP}/gitleaks_8.30.1_linux_x64.tar.gz"
extract_dir="${RUNNER_TEMP}/gitleaks-8.30.1"
# shellcheck source=scripts/ci-retry.sh
source "${GITHUB_WORKSPACE}/.ci-policy/scripts/ci-retry.sh"
vendor="${GITHUB_WORKSPACE}/.ci-policy/third_party/gitleaks_8.30.1_linux_x64.tar.gz"
if [[ -f "$vendor" ]] && printf '%s  %s\n' \
  '551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb' \
  "$vendor" | sha256sum --check --status; then
  cp "$vendor" "$archive"
else
release_url='https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz'
if ! ci_download 4 --fail --location --silent --show-error \
  --proto '=https' --proto-redir '=https' --tlsv1.2 \
  --connect-timeout 10 --max-time 180 \
  "$release_url" \
  --output "$archive"; then
  echo "GitHub release front failed; using the asset API" >&2
  rm -f -- "$archive"
  ci_release_asset_api 4 "$archive" "$release_url"
fi
fi
printf '%s  %s\n' \
  '551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb' \
  "$archive" | sha256sum --check --strict
mkdir -p "$extract_dir"
tar --extract --gzip --file "$archive" --directory "$extract_dir" gitleaks
# The evidence contract requires the scanner binary to be owned by
# the evidence owner (root in production, the invoking CI user in
# the test process), so install it owned by the current uid/gid.
install_cmd=(install -o "$(id -u)" -g "$(id -g)" -m 0755)
if [ ! -w /usr/local/bin ]; then
  command -v sudo >/dev/null 2>&1 || {
    echo "::error::installing gitleaks requires a writable /usr/local/bin or passwordless sudo"
    exit 1
  }
  install_cmd=(sudo -n "${install_cmd[@]}")
fi
"${install_cmd[@]}" "$extract_dir/gitleaks" /usr/local/bin/gitleaks
test "$(/usr/local/bin/gitleaks version)" = '8.30.1'
test "$(stat -c '%u' /usr/local/bin/gitleaks)" = "$(id -u)"
