#!/usr/bin/env bash
set -euo pipefail

service="${1:-}"
ref_override="${2:-}"

[ -n "$service" ] || {
  echo "usage: $0 <service|group|all> [ref]" >&2
  exit 2
}

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"

# Keep Docker build inputs and source-only validators physically separate.
# Consumers must use the returned `matrix` for builds and
# `validation_matrix` for source validation; merging them would make a client
# such as YueLink look like a container service.
builds=$(jq -c --arg service "$service" --arg ref "$ref_override" '
  [
    .[]
    | select(
        $service == "all"
        or .service == $service
        or .group == $service
      )
    | if $ref != "" then .ref = $ref else . end
  ]
' "$repo_root/services.json")

validators=$(jq -c --arg service "$service" --arg ref "$ref_override" '
  [
    .[]
    | select(
        $service == "all"
        or .service == $service
        or .group == $service
      )
    | if $ref != "" then .ref = $ref else . end
  ]
' "$repo_root/validation-targets.json")

selected_count=$(jq -n \
  --argjson builds "$builds" \
  --argjson validators "$validators" \
  '($builds | length) + ($validators | length)')
[ "$selected_count" -gt 0 ] || {
  echo "unknown build service or validation target: $service" >&2
  exit 1
}

jq -nc \
  --argjson builds "$builds" \
  --argjson validators "$validators" '
    ($builds + $validators
      | unique_by(.repo + "|" + .ref + "|" + .validation)
      | map({repo, ref, validation})) as $validation_matrix
    | {
        matrix: $builds,
        validation_matrix: $validation_matrix,
        has_builds: (($builds | length) > 0)
      }
  '
