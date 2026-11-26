#!/usr/bin/env bash
# Sign one per-service release file with the keyless workflow identity.
# The bundle is the signature. This does not touch the owner GPG key.
set -euo pipefail

script_dir=$(CDPATH=; cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/ci-retry.sh
source "$script_dir/ci-retry.sh"

if [[ $# -ne 1 ]]; then
  echo "::error::sign-release-blob.sh requires the release yaml path" >&2
  exit 1
fi
yaml=$1
[[ -f "$yaml" ]] || {
  echo "::error::release record is missing" >&2
  exit 1
}
parent=$(basename -- "$(dirname -- "$yaml")")
base=$(basename -- "$yaml")
[[ "$parent" == "release" ]] || {
  echo "::error::release record must live in release/" >&2
  exit 1
}
[[ "$base" != "release.yaml" ]] || {
  echo "::error::refusing to sign the root ledger name" >&2
  exit 1
}
[[ "$base" =~ ^[a-z0-9][a-z0-9-]*\.yaml$ ]] || {
  echo "::error::refusing to sign an unexpected release file name" >&2
  exit 1
}
command -v cosign >/dev/null 2>&1 || {
  echo "::error::runner is missing cosign" >&2
  exit 1
}

identity="$(python3 "$script_dir/release_pr.py" print identity)"
issuer="$(python3 "$script_dir/release_pr.py" print issuer)"
bundle="${yaml}.bundle"
rm -f -- "$bundle"
keyless_cosign sign-blob --bundle "$bundle" "$yaml"
[[ -s "$bundle" ]] || {
  echo "::error::cosign did not write a bundle" >&2
  exit 1
}
verify_cosign verify-blob \
  --bundle "$bundle" \
  --certificate-identity "$identity" \
  --certificate-oidc-issuer "$issuer" \
  "$yaml"
