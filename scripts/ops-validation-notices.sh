#!/bin/bash
# Shared by build.yml and ci-check --local; run from the source checkout.
set -euo pipefail
# Resolve checkout paths inside the executing namespace, including container jobs.
export YUEBOARD_REPO_PATH="$PWD/.ci-yueboard"
export YUETO_CI_REPO_PATH="$PWD/.ci-policy"
export YUEOPS_REQUIRE_PRODUCER_CONTRACT=1
contract_test=tests/test_yueboard_notices_contract_20261028.py
if [ ! -f "$contract_test" ]; then
  echo "::notice::$contract_test is not on this Ops ref; notices wire contract not yet adopted"
  exit 0
fi
test -d "$YUEBOARD_REPO_PATH/.git" || {
  echo "::error::pinned YueBoard checkout is missing for the notices contract" >&2
  exit 1
}
.venv/bin/python -m pytest -q -p no:cacheprovider -o addopts="" "$contract_test"
