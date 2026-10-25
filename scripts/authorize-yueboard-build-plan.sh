#!/usr/bin/env bash
set -euo pipefail

contract_pin="${1:-}"
source_sha="${2:-}"
promote="${3:-}"

usage() {
  echo "usage: $0 <contract-pin> <resolved-source-sha> <true|false> < plan.json" >&2
  exit 2
}

[[ "$contract_pin" =~ ^[0-9a-f]{40}$ ]] || {
  echo "::error::YueBoard native contract pin must be an exact lowercase 40-hex commit" >&2
  usage
}
[[ "$source_sha" =~ ^[0-9a-f]{40}$ ]] || {
  echo "::error::resolved YueBoard source must be an exact lowercase 40-hex commit" >&2
  usage
}
case "$promote" in
  true|false) ;;
  *)
    echo "::error::YueBoard promotion request must be true or false" >&2
    usage
    ;;
esac

plan="$(jq -ce '
  select(
    (.matrix | type) == "array" and
    (.validation_matrix | type) == "array" and
    (.has_builds | type) == "boolean"
  )
' </dev/stdin)" || {
  echo "::error::build planner did not return the required closed JSON shape" >&2
  exit 2
}

board_validators="$(jq '[.validation_matrix[] | select(.validation == "yueboard")] | length' <<<"$plan")"
board_builds="$(jq '[.matrix[] | select(.validation == "yueboard")] | length' <<<"$plan")"
board_refs="$(jq '[.validation_matrix[] | select(.validation == "yueboard") | .ref] | unique | length' <<<"$plan")"
board_repos="$(jq '[.validation_matrix[] | select(.validation == "yueboard") | .repo] | unique | length' <<<"$plan")"
board_roles="$(jq -c '[.validation_matrix[] | select(.validation == "yueboard") | .board_role] | sort' <<<"$plan")"
reviewed_roles='["components","e2e","frontends","migration","postgres","quality"]'
if [ "$board_builds" -eq 1 ] && [ "$board_refs" -eq 1 ] && [ "$board_repos" -eq 1 ] && {
  [ "$board_validators" -eq 1 ] || {
    [ "$board_validators" -eq 6 ] && [ "$board_roles" = "$reviewed_roles" ]
  }
}; then
  :
else
  echo "::error::selected YueBoard plan must contain one build and either one validator or the six reviewed roles" >&2
  exit 2
fi

if [ "$source_sha" != "$contract_pin" ] && [ "$promote" = true ]; then
  echo "::error::refusing YueBoard promotion: resolved source ${source_sha} is not the exact reviewed native contract pin ${contract_pin}" >&2
  echo "::error::advance native-node-contract.json through the signed cross-repository pin convergence before retrying promote=true" >&2
  exit 1
fi

jq -c \
  --arg source_sha "$source_sha" \
  --arg contract_pin "$contract_pin" '
    .validation_matrix |= map(
      if .validation == "yueboard" then .ref = $source_sha else . end
    )
    | .matrix |= map(
        if .validation == "yueboard" then .ref = $source_sha else . end
      )
    | if $source_sha != $contract_pin then
        .matrix |= map(select(.validation != "yueboard"))
      else . end
    | .has_builds = ((.matrix | length) > 0)
  ' <<<"$plan"

if [ "$source_sha" = "$contract_pin" ]; then
  echo "::notice::YueBoard build plan is pinned and registry-eligible: source=${source_sha}" >&2
else
  echo "::notice::YueBoard validation-only plan is non-promotable: source=${source_sha} reviewed_pin=${contract_pin}; no image build, candidate tag, built marker, sha-* tag, or latest mutation is scheduled" >&2
fi
