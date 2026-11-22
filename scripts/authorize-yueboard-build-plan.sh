#!/usr/bin/env bash
set -euo pipefail

contract_pin="${1:-}"
source_sha="${2:-}"
promote="${3:-}"

usage() {
  echo "usage: $0 <contract-pin> <resolved-source-sha> <true|false> < plan.json" >&2
  exit 2
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
reviewed_roles='["components","e2e","frontends","migration","postgres","quality","race"]'
if [ "$board_builds" -eq 1 ] && [ "$board_refs" -eq 1 ] && [ "$board_repos" -eq 1 ] && {
  [ "$board_validators" -eq 1 ] || {
    [ "$board_validators" -eq 7 ] && [ "$board_roles" = "$reviewed_roles" ]
  }
}; then
  :
else
  echo "::error::selected YueBoard plan must contain one build and either one validator or the seven reviewed roles" >&2
  exit 2
fi

if [[ "$contract_pin" =~ ^[0-9a-f]{40}$ ]]; then
  echo "::notice::yueboard_contract_pin is informational and does not remove image builds source=${source_sha} pin=${contract_pin} requested=${promote}" >&2
else
  echo "::warning::yueboard_contract_pin is informational and not a 40-hex commit; ignored source=${source_sha} requested=${promote}" >&2
fi

jq -c \
  --arg source_sha "$source_sha" '
    .validation_matrix |= map(
      if .validation == "yueboard" then .ref = $source_sha else . end
    )
    | .matrix |= map(
        if .validation == "yueboard" then .ref = $source_sha else . end
      )
    | .has_builds = ((.matrix | length) > 0)
  ' <<<"$plan"

echo "::notice::YueBoard build plan schedules source=${source_sha}; the reviewed pin does not gate image builds" >&2
