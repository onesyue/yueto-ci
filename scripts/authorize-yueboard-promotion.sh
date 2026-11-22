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
case "$promote" in
  true|false) ;;
  *)
    echo "::error::YueBoard promotion request must be true or false" >&2
    usage
    ;;
esac

# The pin is recorded for operators. It does not accept or reject the commit.
if [[ "$contract_pin" =~ ^[0-9a-f]{40}$ ]]; then
  echo "::notice::yueboard_contract_pin is informational source=${source_sha} pin=${contract_pin} requested=${promote}"
else
  echo "::warning::yueboard_contract_pin is informational and not a 40-hex commit; ignored source=${source_sha} requested=${promote}" >&2
fi

if [ "$promote" = true ]; then
  echo "::notice::YueBoard source is promotable=true requested=true source=${source_sha}; computed checks are verify-yueboard-commit.py"
  exit 0
fi

echo "::notice::YueBoard validation-only source is non-promotable: source=${source_sha}; no registry write is authorized"
