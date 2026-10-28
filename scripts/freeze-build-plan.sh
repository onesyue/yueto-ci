#!/usr/bin/env bash
# Resolve each remaining mutable ref once for both build and validation jobs.
set -Eeuo pipefail
# shellcheck source=scripts/ci-retry.sh
source "$(dirname "${BASH_SOURCE[0]}")/ci-retry.sh"
plan=$(cat)
selections=$(jq -ce '[.matrix[], .validation_matrix[]] | unique_by([.repo, .ref])' <<<"$plan")
while IFS= read -r selection; do
  repository=$(jq -er '.repo | select(test("^onesyue/[A-Za-z0-9._-]+$"))' <<<"$selection")
  ref=$(jq -er '.ref | select(type == "string" and length > 0)' <<<"$selection")
  if [[ "$ref" =~ ^[0-9a-f]{40}$ ]]; then
    continue
  fi
  encoded_ref=$(jq -rn --arg ref "$ref" '$ref | @uri')
  sha=$(ci_download 4 --fail --silent --show-error --max-time 60 \
    -H "Authorization: Bearer ${GH_API_TOKEN:?}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/repos/${repository}/commits/${encoded_ref}" \
    | jq -er '.sha | select(type == "string" and test("^[0-9a-f]{40}$"))')
  plan=$(jq --arg repo "$repository" --arg original "$ref" --arg sha "$sha" \
    '(.matrix[], .validation_matrix[]) |=
      (if .repo == $repo and .ref == $original then .ref = $sha else . end)' <<<"$plan")
done < <(jq -c '.[]' <<<"$selections")
jq -ce 'if all(.matrix[], .validation_matrix[]; .ref | test("^[0-9a-f]{40}$"))
  then . else error("build plan has an unfrozen source") end' <<<"$plan"
