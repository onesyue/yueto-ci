#!/usr/bin/env bash
# Verify the promoted image signature, both SBOM formats, and SLSA provenance
# before a release pull request is rendered. Provenance can lag the registry;
# four attempts, 15 seconds apart, match the workstation retry.
set -euo pipefail

script_dir=$(CDPATH=; cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/ci-retry.sh
source "$script_dir/ci-retry.sh"

receipt=${1:?promoted receipt is required}
[[ -f "$receipt" ]] || {
  echo "::error::promoted receipt is missing" >&2
  exit 1
}
for tool in cosign gh python3; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "::error::runner is missing $tool" >&2
    exit 1
  }
done

field() {
  python3 "$script_dir/release_pr.py" field "$receipt" "$1"
}

image="$(field image)"
digest="$(field digest)"
architectures="$(field architectures)"
identity="$(python3 "$script_dir/release_pr.py" print identity)"
issuer="$(python3 "$script_dir/release_pr.py" print issuer)"

verify_cosign verify \
  --certificate-identity "$identity" \
  --certificate-oidc-issuer "$issuer" \
  "${image}@${digest}" >/dev/null

for sbom_format in cyclonedx spdxjson; do
  attestations="$(verify_cosign verify-attestation \
    --certificate-identity "$identity" \
    --certificate-oidc-issuer "$issuer" \
    --type "$sbom_format" \
    "${image}@${digest}")"
  python3 "$script_dir/verify-sbom-attestations.py" \
    --image "$image" \
    --digest "$digest" \
    --expected-architectures "$architectures" \
    --format "$sbom_format" <<<"$attestations"
done

scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
python3 "$script_dir/release_pr.py" attestation-args \
  --image "$image" \
  --digest "$digest" >"$scratch/attest-args"
mapfile -t attest_args <"$scratch/attest-args"
[[ ${#attest_args[@]} -gt 0 ]] || {
  echo "::error::missing attestation arguments" >&2
  exit 1
}

for attempt in 1 2 3 4; do
  if "${attest_args[@]}" >"$scratch/provenance.json"; then
    break
  fi
  if [[ "$attempt" -eq 4 ]]; then
    echo "::error::provenance verification failed" >&2
    exit 1
  fi
  echo "provenance not ready on attempt ${attempt}/4; retrying" >&2
  sleep 15
done

python3 "$script_dir/release_pr.py" check-provenance \
  --receipt "$receipt" \
  --attestation "$scratch/provenance.json"
