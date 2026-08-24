#!/usr/bin/env bash
set -euo pipefail

source_sha="${1:-}"
contract_pin="${2:-}"
promote="${3:-}"

usage() {
  echo "usage: $0 <source-sha> <contract-pin> <true|false>" >&2
  exit 2
}

[[ "$source_sha" =~ ^[0-9a-f]{40}$ ]] || {
  echo "::error::YueBoard source SHA must be an exact lowercase 40-hex commit" >&2
  usage
}
[[ "$contract_pin" =~ ^[0-9a-f]{40}$ ]] || {
  echo "::error::YueBoard native contract pin must be an exact lowercase 40-hex commit" >&2
  usage
}
case "$promote" in
  true|false) ;;
  *)
    echo "::error::YueBoard promotion request must be true or false" >&2
    usage
    ;;
esac

if [ "$source_sha" = "$contract_pin" ]; then
  echo "::notice::YueBoard source is the exact reviewed native contract pin; promotable=true requested=${promote} source=${source_sha}"
  exit 0
fi

if [ "$promote" = true ]; then
  echo "::error::refusing YueBoard promotion: source ${source_sha} is not the exact reviewed native contract pin ${contract_pin}" >&2
  echo "::error::advance native-node-contract.json through the signed cross-repository pin convergence before retrying promote=true" >&2
  exit 1
fi

echo "::notice::YueBoard validation-only source is non-promotable: source=${source_sha} reviewed_pin=${contract_pin}; validation may continue, but no registry write is authorized"
